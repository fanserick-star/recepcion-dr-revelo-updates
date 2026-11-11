"""Regression: Historia 1.4.75 restores 1.4.73 sync and locks empty standby."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica/app"
cloud_path = APP / "cloud_sync.py"
active_app = (APP / "app.py").read_text(encoding="utf-8-sig")


def main() -> None:
    # Exact source hash of the previously validated 1.4.73 cloud synchronizer.
    actual_hash = subprocess.check_output(
        ["git", "hash-object", str(cloud_path)], cwd=ROOT, text=True
    ).strip()
    assert actual_hash == "9be18d5deb3c77e9f920a58e0f83fb0c32ec0079", actual_hash

    cloud = cloud_path.read_text(encoding="utf-8-sig")
    assert "HISTORIA_NEON_ECO_MODE = True" in cloud
    assert "HISTORIA_NEON_ENDPOINT_ID = \"ep-sweet-mud-arlsk7qa\"" in cloud
    assert "_should_pull_cloud" not in cloud
    assert "self._connect_cloud()" in cloud
    assert "if pending == 0 and not pull_due and not type_recovery_due:" in cloud

    assert '@app.get("/configuracion/neon", response_class=HTMLResponse)' in active_app
    assert "def hc1475_neon_sources(request: Request):" in active_app
    assert "request.client.host not in" in active_app
    assert "winter-smoke-49748362" in active_app
    assert "official_endpoint = _v139_cloud_sync.HISTORIA_NEON_ENDPOINT_ID" in active_app
    assert "name='neon-target' disabled" in active_app
    assert 'name=\'neon-target\' checked disabled' in active_app
    assert "Solo disponible en la PC del doctor" in active_app
    assert "mode=ro" in active_app
    assert "return base(\"Neon Oficial y Respaldo\", body, \"neon\")" in active_app
    assert "No se muestran nombres ni datos médicos" in active_app

    manifest = json.loads((APP/"update_manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    assert manifest["app_version"] == manifest["runtime_version"] == version
    # Older safety checks also apply to all later patched Historia versions.
    assert tuple(map(int, version.split("."))) >= (1, 4, 75), version
    assert manifest["notes"]["neon_active_target"] == "official"
    assert manifest["notes"]["neon_backup_empty_unsafe_to_select"] is True
    print("HISTORIA_NEON_SOURCES_1475_OK")


if __name__ == "__main__":
    main()
