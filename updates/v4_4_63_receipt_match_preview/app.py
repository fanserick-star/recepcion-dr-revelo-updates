from __future__ import annotations

# v4.4.63 — recibo térmico: impresión directa igualada a la vista previa.
# Mantiene el arranque blindado de v4.4.60+ y carga el parche de recibos 4.4.63.

import app_patch_4463 as patched

core = patched.core
app = patched.app
APP_VERSION = "4.4.63"
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
