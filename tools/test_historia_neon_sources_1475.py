"""Regression: Historia Neon selector preserves endpoint safety and 1.4.89 UI.

The legacy 1.4.75 screen intentionally showed a disabled empty backup.
After the verified emergency cutover that text became incorrect. Check the
new safety guarantees rather than forcing stale HTML or a false active label.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica/app"
cloud_path = APP / "cloud_sync.py"
active_app = (APP / "app.py").read_text(encoding="utf-8-sig")
panel = (APP / "neon_return_settings.py").read_text(encoding="utf-8")
return_engine = (APP / "neon_official_return.py").read_text(encoding="utf-8")
cloud = cloud_path.read_text(encoding="utf-8-sig")

def main():
    assert "HISTORIA_NEON_EMERGENCY_ENDPOINT_ID" in cloud
    assert 'HISTORIA_NEON_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"' in cloud
    assert "HISTORIA_NEON_ECO_MODE = True" in cloud
    assert "_should_pull_cloud" not in cloud
    assert "self._connect_cloud()" in cloud
    assert "if pending == 0 and not pull_due and not type_recovery_due:" in cloud

    assert "neon_return_settings.install(app, ROOT, DB_PATH, base)" in active_app
    assert "complete_scheduled_return(ROOT, DB_PATH)" in active_app
    assert '@app.get("/configuracion/neon", response_class=HTMLResponse)' in panel
    assert "def neon_page(request: Request):" in panel
    assert 'request.client.host not in {"127.0.0.1", "::1"}' in panel
    assert 'HISTORIA_NEON_TARGET' in panel or 'HISTORIA_NEON_TARGET' in return_engine
    assert "Comprobar diferencias" in panel
    assert "Confirmar regreso al Oficial" in panel
    assert "def _local_health(db_path):" in panel
    assert "mode=ro" in panel
    assert "SET TRANSACTION READ ONLY" in panel
    assert "_verify_complete(report)" in panel
    assert "Neon Oficial" in panel and "Neon de emergencia" in panel
    assert "No se moverán historias" in panel
    assert "No se pudo completar la comparación" in panel
    assert "input type='password'" not in panel
    ast.parse(panel)

    manifest = json.loads((APP/"update_manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    assert manifest["app_version"] == manifest["runtime_version"] == version
    assert tuple(map(int, version.split("."))) >= (1,4,89)
    assert manifest["notes"]["neon_backup_empty_unsafe_to_select"] is False
    print("HISTORIA_NEON_SOURCES_MODERN_SAFE_OK")

if __name__ == "__main__":
    main()
