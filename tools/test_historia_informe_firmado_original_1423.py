"""Regresión del enlace Ver PDF firmado; sin pacientes reales, sin volver a firmar."""
import hashlib
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import informes_clinicos


class LocalRequest:
    base_url = "http://127.0.0.1:8000/"

    def __init__(self, host="127.0.0.1"):
        self.client = SimpleNamespace(host=host)
        self.headers = {"origin": "http://127.0.0.1:8000"}


def main():
    with tempfile.TemporaryDirectory(prefix="signed_informe_view_") as temp:
        root = Path(temp)
        db_path = root / "historia.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE patients(id TEXT PRIMARY KEY,name TEXT,national_id TEXT,birth_date TEXT,sex TEXT);
                CREATE TABLE certificates(
                    id TEXT PRIMARY KEY, patient_id TEXT, certificate_type TEXT,
                    issued_at TEXT,deleted_at TEXT,diagnosis TEXT,
                    body_text TEXT,extra_json TEXT
                );
                CREATE TABLE electronic_signatures(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_type TEXT, document_id TEXT, relative_path TEXT, pdf_sha256 TEXT
                );
                INSERT INTO patients VALUES('p1','PACIENTE FICTICIO','0000000000','1980-01-01','M');
                INSERT INTO certificates VALUES('r1','p1','report_cystoscopy','2026-10-22T09:30:00',NULL,'test','prueba','{}');
                INSERT INTO certificates VALUES('r2','p1','report_ultrasound','2026-10-22T11:30:00',NULL,'test','prueba','{}');
            """)
            out = root / "data" / "documentos_firmados" / "2026" / "10" / "original.pdf"
            out.parent.mkdir(parents=True)
            original = b"%PDF-1.4\n% signed PDF fixture (no personal data)\n"
            out.write_bytes(original)
            conn.execute(
                "INSERT INTO electronic_signatures(document_type,document_id,relative_path,pdf_sha256) VALUES(?,?,?,?)",
                ("informe", "r1", str(out.relative_to(root)), hashlib.sha256(original).hexdigest()),
            )
            conn.commit()

        app = FastAPI()
        informes_clinicos.install(app, {
            "DB_PATH": db_path,
            "ROOT": root,
            "base": lambda title, body, active: body,
        })
        def route(p):
            return next(r.endpoint for r in app.routes if getattr(r,"path","")==p)

        listed = route("/informes")().body.decode("utf-8")
        signed_part = listed.split("<tr>")[1]
        unsigned_part = listed.split("<tr>")[2]
        # El primer registro corresponde al más reciente (sin firma)
        assert "/informes/r2/vista" in unsigned_part or "/informes/r2/vista" in signed_part
        assert "/informes/r1/firmado" in listed
        assert "Ver PDF firmado" in listed
        assert "/informes/r1/vista?print_now=1" not in listed
        assert "/informes/r2/vista?print_now=1" in listed

        get_pdf = route("/informes/{report_id}/firmado")
        result = get_pdf(LocalRequest(), "r1")
        assert isinstance(result, FileResponse)
        assert Path(result.path) == out
        assert out.read_bytes() == original, "Ver nunca debe regenerar ni firmar"
        try:
            get_pdf(LocalRequest(host="192.168.1.66"), "r1")
            raise AssertionError("No debe permitirse recuperar firma desde otra PC")
        except HTTPException as ex:
            assert ex.status_code == 403
        out.write_bytes(b"%PDF-1.4\ncorrupted")
        try:
            get_pdf(LocalRequest(), "r1")
            raise AssertionError("El PDF dañado debe detectarse")
        except HTTPException as ex:
            assert ex.status_code == 409
        out.unlink()
        try:
            get_pdf(LocalRequest(), "r1")
            raise AssertionError("Un PDF extraviado no debe causar Error 500")
        except HTTPException as ex:
            assert ex.status_code == 404
        try:
            get_pdf(LocalRequest(), "r2")
            raise AssertionError("Documento no firmado")
        except HTTPException as ex:
            assert ex.status_code == 404

        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM electronic_signatures").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0] == 2
        print("HISTORIA_SIGNED_REPORT_VIEW_1423_OK")


if __name__ == "__main__":
    main()
