from __future__ import annotations

# v4.4.60 — rescate de arranque: evita el reimport doble del wrapper 4.4.59.
# Mantiene el parche de No facturables, pero Uvicorn recibe el objeto app ya
# construido para que Windows no vuelva a importar toda la aplicación durante
# el arranque.

import app_patch_4459 as patched

core = patched.core
app = patched.app
APP_VERSION = "4.4.60"
patched.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    patched.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = bool(getattr(patched, "PATCH_BOOT_OK", False))
PATCH_BOOT_ERROR = str(getattr(patched, "PATCH_BOOT_ERROR", "") or "")


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
