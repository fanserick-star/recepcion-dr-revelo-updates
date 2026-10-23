"""Regresión de editores clínicos amplios y prevención de múltiples impresiones.

Todos los datos son sintéticos y se crean en un SQLite temporal.
No se conecta a Neón, Windows ni una impresora real.
"""
import sqlite3
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from fastapi import FastAPI
import documentos_clinicos
import informes_clinicos


def route(app, path):
    return next(
        item.endpoint for item in app.routes
        if getattr(item, "path", "") == path and "GET" in (getattr(item, "methods", ()) or ())
    )


def fake_base(title, body, active="inicio"):
    return (
        '<!doctype html><html lang="es"><head><title>' + title + '</title></head>'
        '<body class="cp-remaster-app">'
        '<header class="topbar"><a href="/">INICIO</a><a href="/configuracion">Configuración</a></header>'
        '<main>' + body + '</main>'
        '<footer>Historia Clínica</footer></body></html>'
    )


def main():
    with tempfile.TemporaryDirectory(prefix="historia_editor_1437_") as temp:
        root = Path(temp)
        db_path = root / "clinica.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE patients (
                    id TEXT PRIMARY KEY,name TEXT,national_id TEXT,birth_date TEXT,
                    sex TEXT,deleted_at TEXT
                );
                CREATE TABLE encounters (
                    id TEXT PRIMARY KEY,patient_id TEXT,queue_id TEXT,
                    note_status TEXT,deleted_at TEXT,diagnosis TEXT,
                    clinical_note TEXT
                );
                INSERT INTO patients(id,name,national_id,birth_date,sex)
                   VALUES('p1','PACIENTE FICTICIO','0000000000','1980-01-01','M');
            """)
        documentos_clinicos.ensure_schema(db_path)
        app = FastAPI()
        context = {"DB_PATH": db_path, "ROOT": root, "base": fake_base}
        documentos_clinicos.install(app, context)
        informes_clinicos.install(app, context)

        forms = {
            "rx": route(app, "/recetas/nueva")("p1").body.decode(),
            "cert": route(app, "/certificados/nuevo")("p1").body.decode(),
            "rest": route(app, "/certificados/reposo/nuevo")("p1").body.decode(),
            "report": route(app, "/informes/nuevo")("p1", "cistoscopia").body.decode(),
        }
        for key, page in forms.items():
            assert '<body class="cp-remaster-app clinical-document-editor">' in page, key
            assert 'body.clinical-document-editor > header.topbar' in page, key
            assert 'body.clinical-document-editor > footer' in page, key
            assert 'max-width:1600px' in page, key
            assert 'id="clinical-document-progress"' in page, key
            assert 'role="status" aria-live="polite"' in page, key
            assert 'REPEAT_WAIT_MS=20000' in page, key
            assert 'if(busy)' in page and 'if(printing&&remaining>0)' in page, key
            assert page.count('window.historiaDocumentAction=(function()') == 1, key
            assert 'paciente' in page.lower() or 'Paciente' in page, key

        assert "['rx-save','rx-preview','rx-print','rx-pdf']" in forms["rx"]
        assert "return await window.historiaNativePrint(j.preview_url,'recipe');" in forms["rx"]
        assert "['cert-save','cert-preview','cert-print','cert-pdf']" in forms["cert"]
        assert "return await window.historiaNativePrint(j.preview_url,'certificate');" in forms["cert"]
        assert "['rest-save','rest-preview','rest-print','rest-pdf']" in forms["rest"]
        assert "return await window.historiaNativePrint(j.preview_url,'certificate');" in forms["rest"]
        assert "['report-save','report-preview','report-print','report-sign']" in forms["report"]
        assert "return await window.historiaNativePrint(data.preview_url,'certificate');" in forms["report"]

        # El listado y la aplicación principal no deben perder su navegación.
        listing = route(app, "/recetas")().body.decode()
        assert '<body class="cp-remaster-app">' in listing
        assert 'clinical-document-editor' not in listing
        assert '<header class="topbar">' in listing
        assert 'INICIO' in listing
        assert documentos_clinicos._document_editor_shell(
            lambda title, body, active: body, "Prueba", "CONTENIDO", "recetas"
        ) == "CONTENIDO"
        print("HISTORIA_EDITOR_PRINT_GUARD_1437_OK")


if __name__ == "__main__":
    main()
