from __future__ import annotations

# v4.4.64 — recibo CRM-308 sin marco exterior y sin márgenes lógicos.
import app_patch_4464 as patched

core = patched.core
app = patched.app
APP_VERSION = "4.4.64"
patched.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION

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
