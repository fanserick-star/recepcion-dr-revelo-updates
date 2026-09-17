from __future__ import annotations

# v4.4.80 — hotfix Facturación Emitidas después de limpieza 4.4.79.
# - Conserva toda la limpieza de 4.4.79.
# - Corrige la causa del bug: 4.4.79 eliminaba del DOM .billing-filters,
#   que contiene el selector interno #bEstado usado como estado de Facturación.
# - El panel sigue oculto visualmente; ahora se conserva en DOM.
# - No cambia backend, base de datos, AZUR, recibos ni guardado de atención.

import re as _re

import app_patch_4479 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.80"

_mod = previous
_seen = set()
for _ in range(48):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""
STATE_HOLDER_REPAIRED = False

try:
    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")

    # v4.4.79 quitaba todo .billing-filters. Ese bloque es visualmente obsoleto,
    # pero dentro vive #bEstado, que las funciones estables usan para distinguir
    # POR EMITIR de EMITIDAS. Se oculta, no se elimina.
    _needle = "sec.querySelector('.billing-filters')?.remove();"
    _replacement = "sec.querySelector('.billing-filters')?.setAttribute('hidden','');"
    if _needle in _js:
        _js = _js.replace(_needle, _replacement)
        STATE_HOLDER_REPAIRED = True

    # Unifica todas las constantes de versión visibles/heredadas.
    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const VERSION='4.4.80';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const V='4.4.80';",
        _js,
    )

    V4480_CSS = r"""
/* v4.4.80 — filtros internos conservados pero invisibles */
#facturacion .billing-filters{display:none!important}
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.80"!important;
  font-size:9px!important;line-height:1!important;font-weight:850!important
}
"""

    V4480_JS = r"""
;(()=>{
  if(window.__v4480BillingStateHotfix)return;
  window.__v4480BillingStateHotfix=true;
  const VERSION='4.4.80';

  function preserveBillingState(){
    const sec=document.querySelector('#facturacion');
    if(!sec)return;
    const filters=sec.querySelector('.billing-filters');
    if(filters){
      filters.hidden=true;
      filters.style.display='none';
    }
    const state=document.querySelector('#bEstado');
    if(state){
      state.setAttribute('aria-hidden','true');
      state.tabIndex=-1;
    }
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
  }

  const oldLoad=window.loadBilling;
  if(typeof oldLoad==='function'){
    window.loadBilling=async function(){
      preserveBillingState();
      const out=await oldLoad.apply(this,arguments);
      preserveBillingState();
      return out;
    };
  }

  const oldSet=window.setBillingStatus;
  if(typeof oldSet==='function'){
    window.setBillingStatus=async function(status){
      preserveBillingState();
      const out=await oldSet.apply(this,arguments);
      preserveBillingState();
      return out;
    };
  }

  function boot(){
    preserveBillingState();
    setTimeout(preserveBillingState,100);
    setTimeout(preserveBillingState,500);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4480_CSS
    )
    core.V460_OVERLAY_JS = _js + "\n" + V4480_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.80 billing state hotfix failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4480/health")
def v4480_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "billing_state_holder_preserved": True,
        "cleanup_4479_preserved": True,
        "state_holder_repaired_in_bundle": STATE_HOLDER_REPAIRED,
        "database_changes": False,
        "backend_changes": False,
        "receipt_layout_version": "4.4.69",
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
