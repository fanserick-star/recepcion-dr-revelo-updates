"""Tests for opt-in, destination-locked clinical emergency backup."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"historia-clinica"/"app"
sys.path.insert(0,str(APP))
# CI runs these pure migration checks before its FastAPI dependency install.
# Only HTTP routing needs FastAPI; use lightweight module stubs here.
import types
try:
    import fastapi  # noqa: F401
except ModuleNotFoundError:
    fastapi = types.ModuleType("fastapi")
    fastapi.HTTPException = type("HTTPException", (Exception,), {})
    fastapi.Request = type("Request", (), {})
    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = type("HTMLResponse", (), {})
    responses.JSONResponse = type("JSONResponse", (), {})
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses
import neon_emergency_copy as m


def main() -> None:
    assert m._validate_destination(
        "postgresql://neondb_owner:secret@ep-noisy-paper-arf28291.c-4.us-west-2.aws.neon.tech/neondb"
    ).startswith("postgresql")
    for host in ("ep-sweet-mud-arlsk7qa.c-4.us-west-2.aws.neon.tech",
                 "ep-other-endpoint.c-4.us-west-2.aws.neon.tech"):
        try:
            m._validate_destination("postgresql://user:secret@"+host+"/neondb")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Unsafe target accepted: "+host)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        db=root/"data"/"historia_clinica.db"
        db.parent.mkdir(parents=True)
        conn=sqlite3.connect(db)
        try:
            for table,pk in m.COPY_TABLES:
                conn.execute("CREATE TABLE "+table+" ("+pk+" TEXT PRIMARY KEY, sample TEXT)")
                conn.execute("INSERT INTO "+table+" VALUES (?,?)",(table+"-test","dummy"))
            conn.commit()
        finally:
            conn.close()
        signed=root/"data"/"documentos_firmados"
        signed.mkdir()
        (signed/"sample.pdf").write_bytes(b"%PDF-1.7\nTEST\n")
        archive,stats,_=m._make_archive(root,db)
        assert stats["patients"]==1 and stats["encounters"]==1
        assert stats["pdf_signed_files"]==1
        assert archive.is_file() and stats["archive_bytes"]>0
        with zipfile.ZipFile(archive) as z:
            assert "historia_clinica.db" in z.namelist()
            assert "documentos_firmados/sample.pdf" in z.namelist()
        assert m._table_digest_local(sqlite3.connect(db),"patients","id")[0]==1
    app_src=(APP/"app.py").read_text(encoding="utf-8")
    config_src=(APP/"documentos_clinicos.py").read_text(encoding="utf-8")
    migration_source=(APP/"neon_emergency_copy.py").read_text(encoding="utf-8")
    assert 'definitions.append("source_key TEXT PRIMARY KEY")' in migration_source
    assert 'remote_key = "source_key" if revisions_need_source_key else pk' in migration_source
    assert "neon_emergency_copy.install(app, ROOT, DB_PATH, base)" in app_src
    assert "href='/configuracion/neon/copiar'" in config_src
    assert "Copiar todos los datos desde esta PC" in config_src
    manifest=json.loads((APP/"update_manifest.json").read_text(encoding="utf-8"))
    assert tuple(map(int, manifest["version"].split("."))) >= (1, 4, 77)
    assert "neon_emergency_copy.py" in manifest["copy"]
    print("HISTORIA_NEON_EMERGENCY_LOCAL_COPY_1477_OK")


if __name__ == "__main__":
    main()
