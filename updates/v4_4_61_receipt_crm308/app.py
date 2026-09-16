from __future__ import annotations

# v4.4.61 — ajuste de recibo térmico 80 mm para Crome CRM-308.
# Conserva v4.4.60 (incluido No facturables) y añade únicamente el ajuste visual
# del recibo: logo más visible y “SUBSECUENTE” dentro del ancho imprimible.

import app_patch_4461 as patched

core = patched.core
app = patched.app
APP_VERSION = "4.4.61"
patched.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    patched.previous.APP_VERSION = APP_VERSION
    patched.previous.previous.APP_VERSION = APP_VERSION
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
