from __future__ import annotations

import app_patch_4482 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.82"
core.APP_VERSION = APP_VERSION

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
