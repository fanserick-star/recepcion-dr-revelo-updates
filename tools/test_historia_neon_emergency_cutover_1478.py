"""Regression: emergency Neon activation cannot switch before verified backup."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"historia-clinica"/"app"
sys.path.insert(0,str(APP))
import types
try:
    import fastapi
except ModuleNotFoundError:
    fastapi=types.ModuleType("fastapi")
    fastapi.HTTPException=type("HTTPException",(Exception,),{})
    fastapi.Request=type("Request",(),{})
    responses=types.ModuleType("fastapi.responses")
    responses.HTMLResponse=type("HTMLResponse",(),{})
    responses.JSONResponse=type("JSONResponse",(),{})
    sys.modules["fastapi"]=fastapi
    sys.modules["fastapi.responses"]=responses
import neon_emergency_cutover as cut
import cloud_sync as sync


def main():
    assert sync.HISTORIA_NEON_ENDPOINT_ID=="ep-sweet-mud-arlsk7qa"
    assert sync.HISTORIA_NEON_EMERGENCY_ENDPOINT_ID=="ep-noisy-paper-arf28291"
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)
        (p/".env").write_text(
            "HISTORIA_DATABASE_URL=postgresql://owner:secret@ep-sweet-mud-arlsk7qa.host/neondb\n"
        )
        assert not cut._target_in_env(p)
        try:
            cut._save_cutover(p,"postgresql://owner:secret@ep-noisy-paper-arf28291.host/neondb",{})
        except RuntimeError:
            pass
        else:
            assert cut._target_in_env(p)
        assert cut._target_in_env(p)
        new=(p/".env").read_text()
        assert "HISTORIA_NEON_TARGET=emergency" in new
        assert "HISTORIA_OFFICIAL_DATABASE_URL=" in new
        assert "ep-sweet-mud-arlsk7qa" in new
        assert (p/"data/neon_oficial_antes_de_cambio.env").is_file()
    src=(APP/"cloud_sync.py").read_text(encoding="utf-8")
    assert "self.target_endpoint" in src
    assert "emergency_cutover_seeded_1478" in src
    assert "for table, pk in ALL_SYNC_TABLES.items():" in src
    assert "data[\"id\"] = (str(row[\"id\"]) if self.target_endpoint == HISTORIA_NEON_EMERGENCY_ENDPOINT_ID" in src
    assert "if table == \"patient_links\":" in src
    assert "clean_remote_cursor" in src
    assert "if endpoint_id != self.target_endpoint" in src
    active=(APP/"app.py").read_text(encoding="utf-8")
    assert "neon_emergency_cutover.install(app, ROOT, DB_PATH, base)" in active
    docs=(APP/"documentos_clinicos.py").read_text(encoding="utf-8")
    assert "href='/configuracion/neon/activar'" in docs
    assert "Activar Neon de emergencia verificado" in docs
    manifest=json.loads((APP/"update_manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"]=="1.4.78"
    assert "neon_emergency_cutover.py" in manifest["copy"]
    assert manifest["notes"]["neon_emergency_verified_cutover"]
    print("HISTORIA_NEON_CUTOVER_1478_OK")


if __name__ == "__main__":
    main()
