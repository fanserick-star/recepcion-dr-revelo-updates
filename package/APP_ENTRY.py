from __future__ import annotations

import app as core
import azur_windows_patch

core.APP_VERSION = "4.3.17-RC6"
azur_windows_patch.install(core)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(core.app, host="127.0.0.1", port=8000, reload=False, access_log=False, log_level="warning", workers=1)
