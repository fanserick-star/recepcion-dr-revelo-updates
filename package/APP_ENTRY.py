from __future__ import annotations

import app as core

# Este hotfix mantiene intacto app.py y añade las rutas AZUR como capa lateral.
# También corrige la versión que reporta /api/version sin tocar datos locales.
core.APP_VERSION = "4.3.17-RC3"

import azur_patch
azur_patch.install(core)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(core.app, host="127.0.0.1", port=8000, reload=False, access_log=False, log_level="warning", workers=1)
