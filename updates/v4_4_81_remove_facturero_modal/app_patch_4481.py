from __future__ import annotations

# v4.4.81 — retira Facturero Móvil también de modales/fichas de facturas.
# - Parte de v4.4.80 y conserva el arreglo de Emitidas.
# - v4.4.79 retiraba Facturero Móvil dentro de #facturacion, pero el modal
#   "Ver datos de factura" vive fuera de esa sección y podía seguir mostrando
#   el botón heredado.
# - Bloquea y elimina cualquier control de Facturero Móvil en toda la interfaz,
#   incluyendo modales creados después de cargar la página.
# - No usa MutationObserver y no cambia backend, BD, AZUR, recibos ni guardado.

import re as _re

import app_patch_4480 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.81"

_mod = previous
_seen = set()
for _ in range(52):
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

try:
    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const VERSION='4.4.81';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const V='4.4.81';",
        _js,
    )

    V4481_CSS = r"""
/* v4.4.81 — Facturero Móvil eliminado también de modales */
a[href*="factureromovil" i],
button[onclick*="facturero" i],
a[onclick*="facturero" i],
[data-destination="facturero" i],
[data-target="facturero" i]{
  display:none!important;
}
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.81"!important;
  font-size:9px!important;line-height:1!important;font-weight:850!important
}
"""

    V4481_JS = r"""
;(()=>{
  if(window.__v4481RemoveFactureroEverywhere)return;
  window.__v4481RemoveFactureroEverywhere=true;
  const VERSION='4.4.81';

  const cleanText=v=>String(v??'')
    .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/\s+/g,' ').trim().toLowerCase();

  function isFacturero(el){
    if(!el)return false;
    const blob=[
      cleanText(el.textContent),
      String(el.getAttribute?.('href')||'').toLowerCase(),
      String(el.getAttribute?.('onclick')||'').toLowerCase(),
      String(el.dataset?.destination||'').toLowerCase(),
      String(el.dataset?.target||'').toLowerCase()
    ].join(' ');
    return blob.includes('facturero movil')
      || blob.includes('factureromovil')
      || /\bfacturero\b/.test(blob);
  }

  function removeFactureroEverywhere(){
    document.querySelectorAll('button,a').forEach(el=>{
      if(isFacturero(el))el.remove();
    });

    document.querySelectorAll(
      '.billing-title-actions,.modal-actions,.billing-copy-actions,.billing-actions'
    ).forEach(box=>{
      const visible=[...box.querySelectorAll('button,a')].filter(el=>!isFacturero(el));
      if(!visible.length && !cleanText(box.textContent))box.style.display='none';
    });

    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
  }

  function sweepSoon(){
    removeFactureroEverywhere();
    setTimeout(removeFactureroEverywhere,0);
    setTimeout(removeFactureroEverywhere,60);
    setTimeout(removeFactureroEverywhere,180);
  }

  function wrapModalFunction(name){
    const old=window[name];
    if(typeof old!=='function'||old.__v4481NoFacturero)return;
    const wrapped=function(){
      const out=old.apply(this,arguments);
      sweepSoon();
      if(out&&typeof out.then==='function'){
        Promise.resolve(out).finally(sweepSoon);
      }
      return out;
    };
    wrapped.__v4481NoFacturero=true;
    wrapped.__v4481Original=old;
    window[name]=wrapped;
  }

  [
    'copyBillingData',
    'openBillingRecipientEditor',
    'openBillingDataModal',
    'openBillingCopyModal',
    'showBillingData'
  ].forEach(wrapModalFunction);

  document.addEventListener('click',event=>{
    const control=event.target?.closest?.('button,a');
    if(control&&isFacturero(control)){
      event.preventDefault();
      event.stopImmediatePropagation();
      control.remove();
      return;
    }
    const trigger=event.target?.closest?.(
      '.billing-card button,.billing-card a,#facturacion button,#facturacion a'
    );
    if(trigger)setTimeout(sweepSoon,0);
  },true);

  function boot(){
    sweepSoon();
    [
      'copyBillingData',
      'openBillingRecipientEditor',
      'openBillingDataModal',
      'openBillingCopyModal',
      'showBillingData'
    ].forEach(wrapModalFunction);
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',boot,{once:true});
  }else{
    boot();
  }
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4481_CSS
    )
    core.V460_OVERLAY_JS = _js + "\n" + V4481_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.81 remove Facturero modal patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4481/health")
def v4481_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "facturero_removed_globally": True,
        "facturero_click_blocked": True,
        "billing_emitidas_fix_preserved": True,
        "uses_new_dom_observer": False,
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
