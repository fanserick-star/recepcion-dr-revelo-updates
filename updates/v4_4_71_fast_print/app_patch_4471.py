from __future__ import annotations

# v4.4.71 — guardado rápido con impresión desacoplada.
# - Espera únicamente a que la atención quede guardada.
# - Regresa a Inicio de inmediato y deja la impresión continuar en segundo plano.
# - Mantiene intactas las correcciones de v4.4.70 y el recibo aprobado v4.4.69.
# - Actualiza el rótulo visible de versión a 4.4.71.

import app_patch_4470 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.71"

_mod = previous
_seen = set()
for _ in range(24):
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
    V4471_JS = r"""
;(()=>{
  if(window.__v4471FastAttentionFlow)return;
  window.__v4471FastAttentionFlow=true;
  const VERSION='4.4.71';
  let saving=false;

  const text=v=>String(v??'').replace(/\s+/g,' ').trim();
  const norm=v=>text(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();

  function overlay(message){
    document.querySelector('.v4471-busy')?.remove();
    const el=document.createElement('div');
    el.className='v4470-busy v4471-busy';
    el.innerHTML=`<div class="v4470-busy-card"><div class="v4470-spinner"></div><b>${message}</b><small>Espera un momento…</small></div>`;
    document.body.appendChild(el);
    return el;
  }
  function hideOverlay(el){try{el?.remove()}catch(_e){}}

  function toast(message,warn=false){
    document.querySelector('.v4470-toast')?.remove();
    const el=document.createElement('div');
    el.className='v4470-toast'+(warn?' warn':'');
    el.textContent=message;
    document.body.appendChild(el);
    setTimeout(()=>{try{el.remove()}catch(_e){}},5200);
  }

  function goHome(){
    try{if(typeof window.closeModal==='function')window.closeModal()}catch(_e){}
    const els=[...document.querySelectorAll('nav button,nav a,.sidebar button,.sidebar a,.menu button,.menu a,button,a')];
    const home=els.find(el=>norm(el.textContent)==='INICIO');
    if(home){try{home.click();return}catch(_e){}}
    for(const id of ['inicio','home']){
      try{if(typeof window.show==='function'){window.show(id);return}}catch(_e){}
    }
  }

  function refreshHome(items,consult){
    try{
      if(typeof window.invalidateAttentionWeekCache==='function')window.invalidateAttentionWeekCache();
      if(typeof window.loadWeek==='function'){
        const d=text(consult?.fecha||items?.[0]?.fecha||'').slice(0,10);
        Promise.resolve(window.loadWeek(d||undefined,d||undefined)).catch(()=>{});
      }
      if(typeof window.refreshPendingBadges==='function'){
        Promise.resolve(window.refreshPendingBadges()).catch(()=>{});
      }
    }catch(_e){}
  }

  function paintVersion(){
    try{
      const badge=document.querySelector('#connectionBadge');
      if(badge){
        let v=badge.querySelector('.v460-version');
        if(!v){v=document.createElement('span');v.className='v460-version';badge.appendChild(v)}
        v.textContent='v'+VERSION;
      }
      const config=document.querySelector('#currentVersionBadge');
      if(config)config.textContent='v'+VERSION;
    }catch(_e){}
  }

  function install(){
    if(typeof window.saveAttention!=='function'){setTimeout(install,120);return}
    if(window.saveAttention.__v4471FastPrint)return;

    const current=window.saveAttention;
    const stable=current.__v4470Stable||current;

    const fast=async function(patientId){
      if(saving)return;
      saving=true;
      let savedBatch=null;
      const wait=overlay('Guardando atención…');
      const apiBefore=window.api;
      const globalBefore=(()=>{try{return api}catch(_e){return null}})();

      const capture=async function(url,opt={}){
        const result=await apiBefore.apply(this,arguments);
        const u=String(url||'');
        if(u==='/api/visits/batch-payment'||u==='/api/visits/batch'){
          if(result&&typeof result==='object')savedBatch=result;
        }
        return result;
      };

      try{
        window.api=capture;
        try{api=capture}catch(_e){}
        await stable.apply(this,arguments);
      }catch(err){
        hideOverlay(wait);
        saving=false;
        throw err;
      }finally{
        window.api=apiBefore;
        try{api=globalBefore||apiBefore}catch(_e){}
      }

      if(!savedBatch||savedBatch.ok===false){
        hideOverlay(wait);
        saving=false;
        return;
      }

      const items=Array.isArray(savedBatch.items)?savedBatch.items:[];
      const consult=items.find(v=>!text(v?.procedimiento));

      // Desde aquí la atención YA está confirmada. La UI queda libre de inmediato.
      goHome();
      refreshHome(items,consult);
      hideOverlay(wait);
      saving=false;

      if(!consult||Number(consult.id||0)<=0){
        toast('✓ Atención guardada.');
        return;
      }

      toast('✓ Atención guardada · Imprimiendo recibo…');

      // Intencionalmente SIN await: Windows/spooler no bloquea el regreso a Inicio.
      Promise.resolve(
        apiBefore(
          '/api/v4470/print-visit/'+Number(consult.id),
          {method:'POST',body:'{}'}
        )
      ).then(result=>{
        if(result?.printed){
          toast('✓ Recibo impreso.');
        }else{
          toast('✓ Atención guardada. ⚠ No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.',true);
        }
      }).catch(()=>{
        toast('✓ Atención guardada. ⚠ No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.',true);
      });
    };

    fast.__v4471FastPrint=true;
    fast.__v4471Stable=stable;
    window.saveAttention=fast;
  }

  paintVersion();
  setTimeout(paintVersion,250);
  setTimeout(paintVersion,900);
  setTimeout(paintVersion,2500);
  const mo=new MutationObserver(()=>paintVersion());
  try{mo.observe(document.documentElement,{childList:true,subtree:true})}catch(_e){}
  install();
})();
"""
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4471_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error("v4.4.71 fast attention patch failed: %s", PATCH_BOOT_ERROR)
    except Exception:
        pass


@app.get("/api/v4471/flow-health")
def v4471_flow_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "waits_for_save": True,
        "waits_for_printer_before_home": False,
        "background_print_after_save": True,
        "preserves_v4470_fixes": True,
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
