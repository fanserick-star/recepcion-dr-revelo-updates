"""Pruebas locales de Informes Médicos: sin datos de pacientes reales."""
import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from fastapi import FastAPI
import documentos_clinicos
import informes_clinicos


class FakeRequest:
    def __init__(self, data):
        self.data = data

    async def json(self):
        return self.data


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

        created_form = new(
            "p1", "cistoscopia", "visit1", "", 1
        ).body.decode("utf-8")
        assert "Uretra" in created_form
        assert "Guardar e imprimir" in created_form
        assert "Estrechez" not in created_form
        assert "Diagnóstico" in created_form

        fields = {
            "equipo": "Óptica de prueba",
            "uretra": "Hallazgo <script>alert('x')</script>",
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
        assert json.loads(row[4])["fields"]["uretra"] == fields["uretra"]

        preview_html = preview(rid).body.decode("utf-8")
        assert "INFORME DE CISTOSCOPIA" in preview_html
        assert "&lt;script&gt;" in preview_html
        assert "<script>alert('x')</script>" not in preview_html
        assert "DR. ARMANDO REVELO" in preview_html
        assert "PACIENTE DE PRUEBA" in preview_html

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
        print("INFORMES_CLINICOS_SMOKE_OK", rid)


if __name__ == "__main__":
    main()
