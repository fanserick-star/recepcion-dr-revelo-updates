from __future__ import annotations

# v4.4.62 — ajuste visual de recibo térmico 80 mm.
# Conserva v4.4.61 y uniforma PRIMERO / SUBSECUENTE con el mismo tamaño y letra.

import app_patch_4462 as patched

core = patched.core
app = patched.app
APP_VERSION = "4.4.62"
patched.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    patched.previous.APP_VERSION = APP_VERSION
    patched.previous.previous.APP_VERSION = APP_VERSION
    patched.previous.previous.previous.APP_VERSION = APP_VERSION
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
