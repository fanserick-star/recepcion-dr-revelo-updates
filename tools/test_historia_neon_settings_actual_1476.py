"""Historia Clínica 1.4.76: Neon must appear on the REAL configuration screen."""
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
    assert "Neon Oficial · Seleccionado" in config
    assert "Neon Respaldo · No disponible" in config
    assert "href='/configuracion/neon'" in config
    assert "datos clínicos aún sin copiar" in config
    assert "return HTMLResponse(base(\"Configuración\", body, \"configuracion\"))" in config

    app = (APP / "app.py").read_text(encoding="utf-8-sig")
    assert '@app.get("/configuracion/neon", response_class=HTMLResponse)' in app
    assert "request.client.host not in" in app
    assert "name='neon-target' disabled" in app
    assert "winter-smoke-49748362" in app

    manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    assert manifest["app_version"] == manifest["runtime_version"] == version
    assert tuple(map(int, version.split("."))) >= (1, 4, 76)
    assert manifest["notes"]["neon_settings_visible_in_actual_configuration"]
    assert manifest["notes"]["neon_emergency_verified_cutover"]
    print("HISTORIA_NEON_SETTINGS_ACTUAL_1476_OK")


if __name__ == "__main__":
    main()
