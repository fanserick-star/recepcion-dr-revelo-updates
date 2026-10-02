from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def main() -> None:
    version = str(
        json.loads((APP / "recepcion-version.json").read_text(encoding="utf-8-sig"))["version"]
    ).strip()
    assert version

    features = (APP / "features_runtime.py").read_text(encoding="utf-8-sig")
    index = (APP / "static" / "index.html").read_text(encoding="utf-8-sig")
    app_js = (APP / "static" / "app.js").read_text(encoding="utf-8-sig")
    config_js = (APP / "static" / "configuration.js").read_text(encoding="utf-8-sig")
    core = (APP / "core_runtime.py").read_text(encoding="utf-8-sig")
    remote = (APP / "remote_agenda.py").read_text(encoding="utf-8-sig")
    registry = (APP / "runtime_registry.py").read_text(encoding="utf-8-sig")

    # La versión canónica se lee una sola vez en features_runtime y se usa para
    # invalidar caché de los assets base que sí cambian entre versiones.
    assert "CURRENT_APP_VERSION = _read_current_app_version()" in features
    for asset in ("app.js", "style.css", "doctor_icon.ico"):
        assert f'"{asset}"' in features, f"Falta cache-buster canónico para {asset}"
    assert "version = CURRENT_APP_VERSION" in features

    # No se elimina HTML funcional para conseguir el cache-busting: los assets
    # siguen perteneciendo a index.html y solo cambia su query string al servir /.
    assert "/static/app.js?v=" in index
    assert "/static/style.css?v=" in index
    assert "/static/doctor_icon.ico?v=" in index

    # Protecciones de rendimiento para la PC antigua. Una limpieza no debe
    # volver a sondeos frecuentes ni pools grandes de SQLite/Neon.
    assert "const PASSIVE_CONNECTIVITY_MS=600000" in app_js
    assert "const IDLE_AFTER_MS=5*60*1000" in app_js
    assert "pool_size=3" in core and "max_overflow=1" in core
    assert "pool_size=1" in core and "pool_recycle=300" in core

    # La UI consolidada usa el launcher oficial. El actualizador ZIP interno
    # permanece por ahora como compatibilidad/rescate y no se retira durante
    # esta fase conservadora de auditoría.
    assert "configLaunchUpdater" in config_js
    assert "/api/v4483/launch-updater" in config_js
    assert "applyUpdatePackage" in app_js
    assert "/api/update/apply" in app_js
    assert '@app.post("/api/update/apply")' in core

    # Shims pequeños que parecen viejos pero siguen siendo parte del contrato
    # físico del runtime. Deben permanecer hasta una consolidación dedicada.
    assert "SEMANTIC_RUNTIME = True" in registry
    assert "Cloudflare Tunnel legado retirado" in remote
    assert 'return {"running": False, "mode": "off"}' in remote

    print("RECEPTION SAFE OPTIMIZATION GUARDRAILS OK")
    print("version", version)
    print("canonical_asset_cache_busting", True)
    print("legacy_zip_updater_preserved", True)
    print("old_pc_performance_guards_preserved", True)


if __name__ == "__main__":
    main()
