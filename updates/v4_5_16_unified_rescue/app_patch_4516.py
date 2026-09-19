from __future__ import annotations

# v4.5.16 — rescate unificado del canal automático.
# Parte de la cadena funcional v4.5.11, preserva Historia Bridge/Bendo y
# elimina el número visual fijo que v4.5.7 seguía repintando.

import json
from pathlib import Path
import app_patch_4511 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.16"

_mod = previous
_seen = set()
for _ in range(320):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

V4516_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:attr(data-version)!important;
  font-size:9px!important;
  line-height:1!important;
  font-weight:850!important
}
"""

V4516_JS = r"""
;(()=>{
  if(window.__v4516UnifiedVersion)return;
  window.__v4516UnifiedVersion=true;
  const VERSION='4.5.16';
  function paint(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
      el.title='Recepción v'+VERSION;
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});
  else paint();
  setTimeout(paint,1400);
  setTimeout(paint,2500);
})();
"""

core.V460_OVERLAY_CSS = (getattr(core,"V460_OVERLAY_CSS","") or "") + "\n" + V4516_CSS
core.V460_OVERLAY_JS = (getattr(core,"V460_OVERLAY_JS","") or "") + "\n" + V4516_JS

# El status de actualizaciones debe usar runtime real + package local.
for _route in list(app.router.routes):
    if getattr(_route,"path",None)=="/api/program/update-now" and "POST" in set(getattr(_route,"methods",set()) or set()):
        app.router.routes.remove(_route)
        break

@app.post("/api/program/update-now")
def v4516_program_update_now():
    root=Path(str(core.BASE_DIR))
    local={}
    try:
        local=json.loads((root/"update_manifest.json").read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    package=str(local.get("version") or "").strip()
    expected=str(local.get("app_version") or local.get("runtime_version") or "").strip()
    actual=str(APP_VERSION)
    if expected and expected!=actual:
        return {
            "ok":True,"update":True,"runtime_mismatch":True,
            "current":actual,"package":package,"latest":package,
            "message":f"Actualización incompleta: paquete {package or 'local'}, runtime v{actual}."
        }
    try:
        info=core._read_update_channel_status()
        latest=str(info.get("latest") or "").strip()
        if bool(info.get("update_available")):
            return {
                "ok":True,"update":True,"current":actual,"package":package,
                "latest":latest,
                "message":f"Hay una actualización {latest} disponible. Cierra y vuelve a abrir Recepción."
            }
        return {
            "ok":True,"update":False,"current":actual,"package":package,
            "latest":latest or package or actual,
            "message":f"Programa v{actual} actualizado y coherente con el canal oficial."
        }
    except Exception as exc:
        return {"ok":False,"update":False,"current":actual,"package":package,"message":f"No se pudo consultar el canal: {str(exc)[:180]}"}

@app.get("/api/v4516/health")
def v4516_health(user=core.Depends(core.current_user)):
    return {
        "ok":True,
        "version":APP_VERSION,
        "unified_update_channel":True,
        "legacy_v3_rescue":True,
        "dynamic_version_badge":True,
        "historia_bridge_preserved":True,
        "database_changes":False,
        "neon_schema_changes":False,
    }

PATCH_BOOT_OK=True
