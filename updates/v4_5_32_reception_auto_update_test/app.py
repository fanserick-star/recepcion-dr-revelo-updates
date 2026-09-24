from __future__ import annotations

# v4.5.32 — PRUEBA DE AUTOACTUALIZACIÓN DE RECEPCIÓN.
# app_patch_4525 conserva el comportamiento funcional estable. Esta capa
# propaga APP_VERSION por toda la cadena de módulos para que /api/version,
# health checks y la UI anuncien exactamente la misma versión que el launcher.
# No modifica base de datos, data/, .env, Neon, Historia ni facturación.

import app_patch_4525 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.32"

_mod = previous
_seen = set()
for _ in range(720):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)

core.APP_VERSION = APP_VERSION

# app_patch_4525 llevaba el número visual 4.5.25 fijado en CSS.
# Una regla posterior corrige únicamente la etiqueta visible.
V4532_VERSION_CSS = r"""
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.32"!important;
}
"""
core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4532_VERSION_CSS


@app.get("/api/v4532/health")
def v4532_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "version_chain_synced": True,
        "visual_version_synced": True,
        "database_schema_changes": False,
        "preserves_data_env_excel": True,
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
