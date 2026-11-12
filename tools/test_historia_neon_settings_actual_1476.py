"""Regression: real Historia settings exposes Neon selection, now modernized 1.4.89.

The 1.4.76 test used to require a disabled standby checkbox on the route in
app.py. In 1.4.89 the actual route is implemented in the dedicated UI module
and must reflect the currently active target, with guarded verification.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica/app"


def main() -> None:
    source = (APP / "documentos_clinicos.py").read_text(encoding="utf-8-sig")
    config_start = source.index('@app.get("/configuracion", response_class=HTMLResponse)')
    config_end = source.index('@app.post("/api/configuracion/compartida")', config_start)
    config = source[config_start:config_end]
    assert 'def configuration():' in config
    assert "id='estado'" in config and "id='herramientas'" in config
    assert "id='neon'" in config
    assert config.index("id='estado'") < config.index("id='neon'") < config.index("id='herramientas'")
    assert "href='#neon'>Neon: Oficial y Respaldo" in config
    assert "Neon Oficial · {'Anterior' if emergency_now_active else 'Seleccionado'}" in config
    assert "Neon Respaldo · {'Activo' if emergency_now_active else 'Disponible tras verificar'}" in config
    assert "href='/configuracion/neon'" in config
    assert "Proyecto de emergencia verificado desde la copia local" in config
    assert 'return HTMLResponse(base("Configuración", body, "configuracion"))' in config

    app = (APP / "app.py").read_text(encoding="utf-8-sig")
    panel = (APP / "neon_return_settings.py").read_text(encoding="utf-8")
    assert "neon_return_settings.install(app, ROOT, DB_PATH, base)" in app
    assert '@app.get("/configuracion/neon", response_class=HTMLResponse)' in panel
    assert "request.client.host not in" in panel
    assert "Neon de emergencia" in panel and "Neon Oficial" in panel
    assert "'● ACTIVO' if emergency_active" in panel
    assert "'● ACTIVO' if official_active" in panel
    assert "Comprobar diferencias" in panel
    assert "Confirmar regreso al Oficial" in panel
    assert "SET TRANSACTION READ ONLY" in panel
    assert "mode=ro" in panel
    assert "input type='password'" not in panel

    manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    assert manifest["app_version"] == manifest["runtime_version"] == version
    assert tuple(map(int, version.split("."))) >= (1, 4, 89)
    assert manifest["notes"]["neon_settings_visible_in_actual_configuration"]
    assert manifest["notes"]["neon_emergency_verified_cutover"]
    print("HISTORIA_NEON_SETTINGS_ACTUAL_MODERN_OK")


if __name__ == "__main__":
    main()
