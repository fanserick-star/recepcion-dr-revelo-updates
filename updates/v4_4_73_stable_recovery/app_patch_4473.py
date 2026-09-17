from __future__ import annotations

# v4.4.73 — rollback de interfaz a la base estable v4.4.70.
# - NO carga v4.4.71 ni v4.4.72.
# - Recupera la interfaz que ya funcionó en el consultorio.
# - Conserva celular compartido, impresión automática, servicios/precios y recibo v4.4.69.
# - Solo corrige el rótulo de versión sustituyendo la constante ya existente; no agrega observers.

import app_patch_4470 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.73"

_mod = previous
_seen = set()
for _ in range(24):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    # v4.4.70 fue la última interfaz confirmada funcionando en la PC.
    # En vez de añadir más JavaScript, sustituimos únicamente su constante
    # visible de versión antes de que el HTML se sirva.
    _js = getattr(core, "V460_OVERLAY_JS", "") or ""
    _js = _js.replace("const VERSION='4.4.70';", "const VERSION='4.4.73';")
    core.V460_OVERLAY_JS = _js
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.73 stable recovery patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4473/recovery-health")
def v4473_recovery_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "base_ui": "4.4.70",
        "imports_v4471": False,
        "imports_v4472": False,
        "white_screen_recovery": True,
        "receipt_layout_version": "4.4.69",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )
