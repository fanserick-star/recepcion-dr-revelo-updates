from __future__ import annotations

# v4.4.78 — botón visible en Por emitir + versión visual estable.
# - Parte de v4.4.77 y conserva descarte seguro de pre-facturas.
# - No cambia backend, base de datos, recibo ni flujo de guardado.
# - Decora las tarjetas DESPUÉS de que Facturación termina de renderizar,
#   evitando depender de que billingCardHtml siga siendo la función activa.
# - Unifica constantes VERSION/V heredadas para que el número junto a "En línea"
#   no alterne entre versiones anteriores.
# - No usa MutationObserver.

import re as _re

import app_patch_4477 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.78"

_mod = previous
_seen = set()
for _ in range(40):
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
    V4478_CSS = r"""
/* v4.4.78 — versión estable + botón seguro de descarte */
.v4478-discard-billing{
  border:1px solid #dfb4b4!important;
  background:#fff6f6!important;
  color:#963d3d!important;
}
.v4478-discard-billing:hover{
  background:#fdecec!important;
  border-color:#cf8f8f!important;
}
/* Los parches antiguos todavía pueden intentar escribir su versión unos ms.
   Ocultamos ese texto interno y mostramos una única versión estable. */
.v460-version,#currentVersionBadge{
  font-size:0!important;
}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.78";
  font-size:9px!important;
  line-height:1!important;
  font-weight:850!important;
}
"""

    V4478_JS = r"""
;(()=>{
  if(window.__v4478VisibleDiscardAndStableVersion)return;
  window.__v4478VisibleDiscardAndStableVersion=true;
  const VERSION='4.4.78';

  const state=()=>String(document.querySelector('#bEstado')?.value||'PENDIENTE').toUpperCase();

  function identityFromCard(card,index){
    if(!card)return null;
    const dsPid=Number(card.dataset.patientId||0);
    const dsFecha=String(card.dataset.fecha||'').slice(0,10);
    if(dsPid&&/^\d{4}-\d{2}-\d{2}$/.test(dsFecha)){
      return {patient_id:dsPid,fecha:dsFecha};
    }

    for(const el of [...card.querySelectorAll('[onclick]')]){
      const raw=String(el.getAttribute('onclick')||'');
      const m=/\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]/.exec(raw);
      if(m)return {patient_id:Number(m[1]),fecha:m[2]};
    }

    try{
      const groups=Array.isArray(billingGroupsCache)?billingGroupsCache:[];
      const g=groups[index];
      const pid=Number(g?.patient?.id||0);
      const fecha=String(g?.fecha||g?.items?.[0]?.visit?.fecha||'').slice(0,10);
      if(pid&&/^\d{4}-\d{2}-\d{2}$/.test(fecha)){
        return {patient_id:pid,fecha};
      }
    }catch(_e){}
    return null;
  }

  function decoratePendingCards(){
    if(state()==='EMITIDA')return;
    const cards=[...document.querySelectorAll('#billingList .billing-card')];
    cards.forEach((card,index)=>{
      if(card.classList.contains('emitida'))return;
      if(card.querySelector('.v4478-discard-billing,.v4477-discard-billing'))return;

      const id=identityFromCard(card,index);
      if(!id)return;

      let actions=card.querySelector('.billing-actions');
      if(!actions){
        const foot=card.querySelector('.billing-card-foot')||card;
        actions=document.createElement('div');
        actions.className='billing-actions';
        foot.appendChild(actions);
      }

      const btn=document.createElement('button');
      btn.type='button';
      btn.className='v4478-discard-billing';
      btn.textContent='🗑 Quitar de Por emitir';
      btn.addEventListener('click',event=>{
        event.preventDefault();
        event.stopPropagation();
        if(typeof window.v4477DiscardPendingBilling==='function'){
          window.v4477DiscardPendingBilling(id.patient_id,id.fecha,event);
        }else{
          alert('La opción para quitar esta factura todavía no está disponible. Cierra y vuelve a abrir Recepción.');
        }
      });
      actions.prepend(btn);
    });
  }

  function stabilizeVersion(){
    try{
      document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
        el.textContent='v'+VERSION;
        el.setAttribute('data-version','v'+VERSION);
      });
    }catch(_e){}
  }

  const stableLoadBilling=window.loadBilling;
  if(typeof stableLoadBilling==='function'){
    window.loadBilling=async function(){
      const out=await stableLoadBilling.apply(this,arguments);
      decoratePendingCards();
      stabilizeVersion();
      setTimeout(decoratePendingCards,40);
      setTimeout(decoratePendingCards,140);
      return out;
    };
  }

  const stableSetBillingStatus=window.setBillingStatus;
  if(typeof stableSetBillingStatus==='function'){
    window.setBillingStatus=async function(){
      const out=await stableSetBillingStatus.apply(this,arguments);
      decoratePendingCards();
      stabilizeVersion();
      setTimeout(decoratePendingCards,50);
      return out;
    };
  }

  document.addEventListener('click',event=>{
    const billingNav=event.target?.closest?.('[data-section="facturacion"],[data-config-tab="facturacion"]');
    if(billingNav){
      setTimeout(decoratePendingCards,80);
      setTimeout(decoratePendingCards,260);
    }
  },true);

  function boot(){
    stabilizeVersion();
    decoratePendingCards();
    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},180);
    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},700);
    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},1600);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
"""

    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    # Todos los escritores de versión heredados quedan de acuerdo. Esto evita
    # que timeouts antiguos alternen 4.4.70/75/76/77 antes de asentarse.
    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const VERSION='4.4.78';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const V='4.4.78';",
        _js,
    )

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4478_CSS
    )
    core.V460_OVERLAY_JS = _js + "\n" + V4478_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.78 visible discard/stable version patch failed: %s",
            PATCH_BOOT_ERROR,
        )
    except Exception:
        pass


@app.get("/api/v4478/health")
def v4478_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "pending_discard_button_post_render": True,
        "stable_visible_version": True,
        "uses_new_dom_observer": False,
        "backend_changes": False,
        "base": "4.4.77",
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
