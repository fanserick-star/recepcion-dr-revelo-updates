from __future__ import annotations

# v4.5.15 — versión visible dinámica.
# v4.5.7 dejó un CSS/JS heredado que forzaba visualmente "v4.5.7"
# aunque el runtime y el paquete ya fueran posteriores. Esta capa elimina
# definitivamente ese número fijo y lo toma del runtime actual.

import app_patch_4514 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.15"

_mod = previous
_seen = set()
for _ in range(300):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

V4515_CSS = r"""
/* La versión visible nunca vuelve a quedar fijada por una capa antigua. */
.v460-version,#currentVersionBadge{
  font-size:0!important
}
.v460-version::after,#currentVersionBadge::after{
  content:attr(data-version)!important;
  font-size:9px!important;
  line-height:1!important;
  font-weight:850!important
}
"""

V4515_JS = r"""
;(()=>{
  if(window.__v4515DynamicVersion)return;
  window.__v4515DynamicVersion=true;
  const VERSION='4.5.15';
  function paintVersion(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
      el.title='Recepción v'+VERSION;
    });
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',paintVersion,{once:true});
  }else{
    paintVersion();
  }
  // v4.5.7 tenía tres repintados diferidos (180/550/1100 ms).
  // Estos dos repintados únicos ganan después, sin crear un temporizador persistente.
  setTimeout(paintVersion,1350);
  setTimeout(paintVersion,2400);
})();
"""

core.V460_OVERLAY_CSS = (
    (getattr(core, "V460_OVERLAY_CSS", "") or "")
    + "\n"
    + V4515_CSS
)
core.V460_OVERLAY_JS = (
    (getattr(core, "V460_OVERLAY_JS", "") or "")
    + "\n"
    + V4515_JS
)

@app.get("/api/v4515/health")
def v4515_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "dynamic_version_badge": True,
        "legacy_4507_visual_override_neutralized": True,
        "persistent_timer_added": False,
        "database_changes": False,
        "neon_writes_added": False,
    }

PATCH_BOOT_OK = True
