"""Regresión: documentos por ficha, PDF firmado original y botones separados.

Sólo pacientes ficticios en SQLite temporal. Sin datos de producción ni Neón.
"""
import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import firma_electronica
import patient_document_panel


class LocalRequest:
    base_url = "http://127.0.0.1:8000/"
    def __init__(self, host="127.0.0.1", origin="http://127.0.0.1:8000"):
        self.client = SimpleNamespace(host=host)
        self.headers = {"origin": origin}


def main():
    with tempfile.TemporaryDirectory(prefix="historia_ficha_documents_") as d:
        root = Path(d)
        path = root / "historia.sqlite"
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE prescriptions(
                    id TEXT PRIMARY KEY, patient_id TEXT, issued_at TEXT,
                    diagnosis TEXT, deleted_at TEXT
                );
                CREATE TABLE certificates(
                    id TEXT PRIMARY KEY, patient_id TEXT, issued_at TEXT,
                    diagnosis TEXT, certificate_type TEXT, deleted_at TEXT
                );
                INSERT INTO prescriptions VALUES('rx1','p1','2026-10-20T10:00','Tratamiento',NULL);
                INSERT INTO prescriptions VALUES('rx2','p1','2026-10-18T10:00','Receta antigua',NULL);
                INSERT INTO prescriptions VALUES('rx-other','p2','2026-10-22T10:00','No filtrar por nombre',NULL);
                INSERT INTO prescriptions VALUES('rx-deleted','p1','2026-10-19T10:00','Borrado','2026-10-19');
                INSERT INTO certificates VALUES('cyst','p1','2026-10-23T10:00','Hallazgos cisto','report_cystoscopy',NULL);
                INSERT INTO certificates VALUES('echo','p1','2026-10-22T08:00','Ecografía','report_ultrasound',NULL);
                INSERT INTO certificates VALUES('cert','p1','2026-10-21T10:00','Certificado','medical',NULL);
                INSERT INTO certificates VALUES('rest','p1','2026-10-16T10:00','Reposo','rest_isolation',NULL);
                INSERT INTO certificates VALUES('other','p2','2026-10-24T10:00','No pertenece','medical',NULL);
                INSERT INTO certificates VALUES('gone','p1','2026-10-21T09:00','Retirado','medical','2026-10-21');
            """)
            conn.commit()
        firma_electronica._ensure_audit_schema(path)
        signed_pdf = root / "data/documentos_firmados/2026/10/cyst.pdf"
        signed_pdf.parent.mkdir(parents=True,exist_ok=True)
        original = b"%PDF-1.4\nfixture sin informacion real\n"
        signed_pdf.write_bytes(original)
        with sqlite3.connect(path) as conn:
            conn.execute(
                """INSERT INTO electronic_signatures(
                    document_type,document_id,signed_at,certificate_subject,certificate_serial,
                    pdf_sha256,relative_path) VALUES(?,?,?,?,?,?,?)""",
                ("informe","cyst","2026-10-23T10:10","TEST","111",
                 hashlib.sha256(original).hexdigest(),str(signed_pdf.relative_to(root)))
            )
            conn.execute(
                """INSERT INTO electronic_signatures(
                    document_type,document_id,signed_at,certificate_subject,certificate_serial,
                    pdf_sha256,relative_path) VALUES(?,?,?,?,?,?,?)""",
                ("receta","rx1","2026-10-20T10:10","TEST","111",
                 hashlib.sha256(original).hexdigest(),str(signed_pdf.relative_to(root)))
            )
            conn.commit()

        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            docs = patient_document_panel.read_documents(conn,"p1")
            assert len(docs)==6, docs
            assert all(d["id"] not in {"rx-other","other","gone","rx-deleted"} for d in docs)
            assert docs[0]["id"]=="cyst"
            assert [d["kind"] for d in docs].count("receta")==2
            assert [d["kind"] for d in docs].count("informe")==2
            assert any(d["kind"]=="certificado" for d in docs)
            assert any(d["kind"]=="reposo" for d in docs)
            assert {d["id"] for d in docs if d["signed"]}=={"cyst","rx1"}
            assert len(patient_document_panel.read_documents(conn,"p2"))==2
            html = patient_document_panel.render_patient_documents(conn,"p1")
            assert "Documentos del paciente" in html
            assert "6 documentos" in html
            assert "2</strong> Informes" in html
            assert "2</strong> Certificados" in html
            assert "2</strong> Recetas" in html
            assert "/api/firma/original/informe/cyst" in html
            assert "/api/firma/original/receta/rx1" in html
            assert "/recetas/rx2/vista?print_now=1" in html
            assert "/informes/echo/vista" in html
            assert "/certificados/reposo/rest/vista" in html
            assert "rx-other" not in html and "gone" not in html
            assert "no-information" not in html
            assert len(patient_document_panel.read_documents(conn,"p2"))==2

        app=FastAPI()
        firma_electronica.install(app,{
            "ROOT":root,"DB_PATH":path,
            "base":lambda title,body,active:body,
            "DOCTOR_NAME":"FICTICIO"
        })
        get = next(
            route.endpoint for route in app.routes
            if getattr(route,"path","")=="/api/firma/original/{kind}/{doc_id}"
        )
        response=get(LocalRequest(),"informe","cyst")
        assert isinstance(response,FileResponse)
        assert Path(response.path)==signed_pdf
        assert signed_pdf.read_bytes()==original
        assert get(LocalRequest(),"receta","rx1").path==signed_pdf
        for kind,id_ in [("certificado","gone"),("receta","rx-deleted"),("informe","other")]:
            try:
                get(LocalRequest(),kind,id_)
                raise AssertionError((kind,id_))
            except HTTPException as exc:
                assert exc.status_code==404
        try:
            get(LocalRequest(host="192.168.0.10"),"informe","cyst")
            raise AssertionError("No remote access")
        except HTTPException as exc:
            assert exc.status_code==403
        try:
            get(LocalRequest(origin="https://evil.invalid"),"informe","cyst")
            raise AssertionError("No foreign origin")
        except HTTPException as exc:
            assert exc.status_code==403
        signed_pdf.write_bytes(b"malformed")
        try:
            get(LocalRequest(),"informe","cyst")
            raise AssertionError("Reject changed PDF")
        except HTTPException as exc:
            assert exc.status_code==409
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM electronic_signatures").fetchone()[0]==2
            assert conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]==6
            assert conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0]==4

        app_source=(root.parent / "not-real")
        real_app=Path(__file__).resolve().parents[1]/"historia-clinica/app/app.py"
        code=real_app.read_text(encoding="utf-8")
        assert "patient_documents = patient_document_panel.read_documents(conn, patient_id)" in code
        assert "documents_html = patient_document_panel.render_patient_documents(" in code
        assert "documents=patient_documents" in code
        assert "{alert_html}\n<section class=\"cp-history-window\">" in code
        assert "id=\"patient-docs-open\"" in code
        assert "📁 Documentos <strong>{document_count}</strong>" in code
        assert "id=\"patient-docs-dialog\"" in code
        assert 'aria-modal="true"' in code
        assert "{documents_html}\n  </div>\n</dialog>" in code
        assert "dialog.showModal();" in code
        assert "dialog.close()" in code
        assert "previousFocus.focus({preventScroll:true})" in code
        assert code.index('{alert_html}\n<section class="cp-history-window">') < code.index('id="patient-docs-dialog"')
        assert "cp-patient-primary-action" in code
        assert "cp-patient-secondary-actions" in code
        assert code.index("{consult_action}</div>") < code.index("{secondary_actions}")
        css=(Path(__file__).resolve().parents[1]/"historia-clinica/app/static/style.css").read_text("utf-8")
        assert "Ficha ABIERTA, no tarjetas de espera" in css
        assert "justify-content:flex-end!important" in css
        assert ".cp-patient-documents-dialog:not([open]){display:none!important}" in css
        assert ".cp-patient-documents-dialog[open]" in css
        assert ".cp-patient-documents-dialog::backdrop" in css
        assert ".cp-docs-dialog-content .cp-docs-list" in css
        print("HISTORIA_PATIENT_DOCUMENTS_ACTIONS_1426_OK")


if __name__=="__main__":
    main()
