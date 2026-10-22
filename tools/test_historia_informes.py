"""Pruebas locales de Informes Médicos: sin datos de pacientes reales."""
import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from fastapi import FastAPI
import documentos_clinicos
import informes_clinicos


class FakeRequest:
    def __init__(self, data):
        self.data = data

    async def json(self):
        return self.data



class LocalDeleteRequest:
    base_url = "http://127.0.0.1:8000/"

    def __init__(self, allow=True, host="127.0.0.1", certificate=False, signed_confirm=False):
        self.client = SimpleNamespace(host=host)
        self.headers = {"origin": "http://127.0.0.1:8000"}
        if allow:
            self.headers["x-historia-delete-certificate" if certificate else "x-historia-delete-report"] = "1"
        if signed_confirm:
            self.headers["x-historia-confirm-signed-delete"] = "ELIMINAR"


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "historia.sqlite"
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE patients(
                    id TEXT PRIMARY KEY, name TEXT, national_id TEXT,
                    birth_date TEXT, sex TEXT, deleted_at TEXT
                );
                CREATE TABLE encounters(
                    id TEXT PRIMARY KEY, patient_id TEXT, deleted_at TEXT
                );
                INSERT INTO patients(id,name,national_id,birth_date,sex)
                VALUES('p1','PACIENTE DE PRUEBA','1234567890','1980-06-18','F');
                INSERT INTO patients(id,name,national_id,birth_date,sex)
                VALUES('p2','OTRO PACIENTE','9876543210','1979-01-21','M');
                INSERT INTO encounters(id,patient_id) VALUES('visit1','p1');
            """)
            conn.commit()
        documentos_clinicos.ensure_schema(path)
        app = FastAPI()
        informes_clinicos.install(
            app, {"DB_PATH": path, "base": lambda title, body, active: body}
        )
        documentos_clinicos.install(
            app, {"DB_PATH": path, "ROOT": Path(tmp), "base": lambda title, body, active: body}
        )

        def route(path, method):
            return next(
                r.endpoint for r in app.routes
                if getattr(r, "path", "") == path and method in getattr(r, "methods", {})
            )

        new = route("/informes/nuevo", "GET")
        edit = route("/informes/{report_id}/editar", "GET")
        preview = route("/informes/{report_id}/vista", "GET")
        listing = route("/informes", "GET")
        save = route("/api/informes", "POST")
        delete_report = route("/api/informes/{report_id}/eliminar", "POST")
        certificate_listing = route("/certificados", "GET")
        delete_certificate = route("/api/certificados/{cert_id}/eliminar", "POST")

        created_form = new(
            "p1", "cistoscopia", "visit1", "", 1
        ).body.decode("utf-8")
        assert "Uretra anterior" in created_form
        assert "Uretra posterior" in created_form
        assert "data-field='uretra_anterior'" in created_form
        assert "data-field='uretra_posterior'" in created_form
        assert "data-field='uretra'" not in created_form
        assert "Guardar e imprimir" in created_form
        assert "Estrechez" not in created_form
        assert "Diagnóstico" in created_form

        fields = {
            "equipo": "Óptica de prueba",
            "uretra_anterior": "Hallazgo anterior <script>alert('x')</script>",
            "uretra_posterior": "Hallazgo posterior de prueba",
            "conclusion": "Texto de prueba redactado por el médico",
        }
        payload = {
            "patient_id":"p1", "type":"cistoscopia",
            "encounter_id":"visit1", "from_consultation":True,
            "issued_date":"2026-10-21", "fields":fields,
        }
        first = response_json(asyncio.run(save(FakeRequest(payload))))
        assert first["ok"] and first["id"]
        rid = first["id"]

        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT patient_id, encounter_id,certificate_type,body_text,extra_json "
                "FROM certificates WHERE id=?", (rid,)
            ).fetchone()
        assert row[0] == "p1" and row[1] == "visit1"
        assert row[2] == "report_cystoscopy"
        assert "Óptica de prueba" in row[3]
        saved_fields = json.loads(row[4])["fields"]
        assert saved_fields["uretra_anterior"] == fields["uretra_anterior"]
        assert saved_fields["uretra_posterior"] == fields["uretra_posterior"]
        assert "uretra" not in saved_fields
        assert "URETRA ANTERIOR:" in row[3]
        assert "URETRA POSTERIOR:" in row[3]

        preview_html = preview(rid).body.decode("utf-8")
        assert "INFORME DE CISTOSCOPIA" in preview_html
        assert "<h3>Uretra anterior</h3>" in preview_html
        assert "<h3>Uretra posterior</h3>" in preview_html
        assert "&lt;script&gt;" in preview_html
        assert "<script>alert('x')</script>" not in preview_html
        assert "DR. ARMANDO REVELO" in preview_html
        assert "PACIENTE DE PRUEBA" in preview_html
        assert "padding:8mm 12mm 7mm" in preview_html
        assert "font-size:12pt" in preview_html
        assert "min-height:0;height:auto" in preview_html
        assert "padding:7mm 11mm 6mm" in preview(rid, compact=1).body.decode("utf-8")

        edit_html = edit(rid).body.decode("utf-8")
        assert "Óptica de prueba" in edit_html

        payload["report_id"] = rid
        payload["fields"]["cuello"] = "Nuevo hallazgo"
        second = response_json(asyncio.run(save(FakeRequest(payload))))
        assert second["id"] == rid
        with sqlite3.connect(path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
        assert count == 1, "La edición no puede crear duplicados"

        payload["patient_id"] = "p2"
        forbidden = asyncio.run(save(FakeRequest(payload)))
        assert forbidden.status_code == 409
        payload["patient_id"] = "p1"

        broken = dict(payload, fields={})
        empty = asyncio.run(save(FakeRequest(broken)))
        assert empty.status_code == 400

        invalid = dict(payload, type="no_valido")
        denied = asyncio.run(save(FakeRequest(invalid)))
        assert denied.status_code == 400

        # El campo genérico ya no forma parte de los informes nuevos.
        old_client = dict(payload, fields={"uretra": "No admitir este campo en informes nuevos"})
        assert asyncio.run(save(FakeRequest(old_client))).status_code == 400

        # Compatibilidad retroactiva: el contenido ya registrado como Uretra
        # permanece visible y no debe asignarse arbitrariamente a anterior/posterior.
        legacy_note = "Hallazgo histórico de uretra sin subregión"
        legacy_json = json.dumps({"version":1, "report_type":"cistoscopia",
                                  "fields":{"equipo":"Equipo antiguo", "uretra": legacy_note}},
                                 ensure_ascii=False)
        with sqlite3.connect(path) as conn:
            conn.execute("UPDATE certificates SET extra_json=?,body_text=? WHERE id=?",
                         (legacy_json, "URETRA: "+legacy_note, rid))
            conn.commit()
        legacy_form = edit(rid).body.decode("utf-8")
        assert "data-field='uretra_anterior'" in legacy_form
        assert "data-field='uretra_posterior'" in legacy_form
        assert "Uretra (registro anterior, conservado)" in legacy_form
        assert legacy_note in legacy_form
        assert "data-field='uretra'" not in legacy_form
        original_preview = preview(rid).body.decode("utf-8")
        assert "Uretra (registro anterior)" in original_preview
        assert legacy_note in original_preview

        payload["fields"] = {"uretra_anterior":"Hallazgo anterior nuevo",
                             "uretra_posterior":"Hallazgo posterior nuevo"}
        saved_legacy = response_json(asyncio.run(save(FakeRequest(payload))))
        assert saved_legacy["ok"] and saved_legacy["id"] == rid
        with sqlite3.connect(path) as conn:
            check = conn.execute("SELECT extra_json,body_text FROM certificates WHERE id=?",
                                 (rid,)).fetchone()
        retained = json.loads(check[0])["fields"]
        assert retained["uretra"] == legacy_note
        assert retained["uretra_anterior"] == "Hallazgo anterior nuevo"
        assert retained["uretra_posterior"] == "Hallazgo posterior nuevo"
        assert legacy_note in check[1]
        edited_preview = preview(rid).body.decode("utf-8")
        assert "Hallazgo anterior nuevo" in edited_preview
        assert "Hallazgo posterior nuevo" in edited_preview
        assert legacy_note in edited_preview

        ultrasound = {
            "patient_id":"p2","type":"ecografia","issued_date":"2026-10-21",
            "fields":{"estudio":"Ecografía renal","rinon_derecho":"Estudio de prueba"},
        }
        result = response_json(asyncio.run(save(FakeRequest(ultrasound))))
        assert result["ok"]
        assert "INFORME DE ECOGRAFÍA" in preview(result["id"]).body.decode("utf-8")
        history = listing("p1").body.decode("utf-8")
        assert "Cistoscopia" in history and "Ecografía" in history

        with sqlite3.connect(path) as conn:
            certs = conn.execute(
                "SELECT COUNT(*) FROM certificates WHERE certificate_type='medical'"
            ).fetchone()[0]
            assert certs == 0
        # Bloqueo de informes firmados: no se ofrece botón ni se borra por API.
        with sqlite3.connect(path) as conn:
            conn.execute("""CREATE TABLE electronic_signatures(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type TEXT,document_id TEXT,signed_at TEXT,
                certificate_subject TEXT,certificate_serial TEXT,
                pdf_sha256 TEXT,relative_path TEXT
            )""")
            conn.execute("""INSERT INTO electronic_signatures(document_type,document_id,signed_at,pdf_sha256,relative_path)
                            VALUES('informe',?,'2026-10-22T10:00:00','test','test.pdf')""", (rid,))
            conn.commit()
        signed_list = listing().body.decode("utf-8")
        assert "🔒 Firmado" in signed_list
        assert "data-report-id='" + rid + "'" in signed_list
        assert "data-signed='1'" in signed_list
        assert delete_report(rid, LocalDeleteRequest()).status_code == 409

        # Informes no firmados: acción manual desde la lista.
        list_html = listing().body.decode("utf-8")
        assert "report-delete-btn" in list_html
        assert "data-report-id='" + result["id"] + "'" in list_html
        assert delete_report(result["id"], LocalDeleteRequest(allow=False)).status_code == 403
        from fastapi import HTTPException
        try:
            delete_report(result["id"], LocalDeleteRequest(host="192.168.1.10"))
            raise AssertionError("Acceso desde otra PC no autorizado")
        except HTTPException as exc:
            assert exc.status_code == 403
        deleted = response_json(delete_report(result["id"], LocalDeleteRequest()))
        assert deleted["ok"] and deleted["id"] == result["id"]
        assert preview(result["id"]).status_code == 404
        assert delete_report(result["id"], LocalDeleteRequest()).status_code == 404
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM certificates WHERE id=?", (rid,)).fetchone()[0] == 1
        # Certificados normales y reposo ficticios, sin alterar consultas.
        with sqlite3.connect(path) as conn:
            for cid, kind in (
                ("cert-unsigned", "medical"), ("rest-unsigned", "rest_isolation"),
                ("cert-signed", "medical"), ("rest-signed", "rest_isolation"),
            ):
                conn.execute(
                    "INSERT INTO certificates(id,patient_id,encounter_id,issued_at,body_text,certificate_type) VALUES(?,?,?,?,?,?)",
                    (cid, "p1", "visit1", "2026-10-22T13:00:00", "Documento de prueba", kind),
                )
            for cid, kind in (("cert-signed", "certificado"), ("rest-signed", "reposo")):
                conn.execute(
                    "INSERT INTO electronic_signatures(document_type,document_id,signed_at,pdf_sha256,relative_path) VALUES(?,?,?,?,?)",
                    (kind, cid, "2026-10-22T13:00:00", "hash-test", "pdf-test"),
                )
            conn.commit()
        print("INFORMES_DELETE_UNSIGNED_OK")
        print("INFORMES_CLINICOS_SMOKE_OK", rid)


if __name__ == "__main__":
    main()
    from test_doctor_turn_call import main as test_doctor_call
    test_doctor_call()
    import test_historia_queue_beacon_1416  # visual contract, no DB writes
