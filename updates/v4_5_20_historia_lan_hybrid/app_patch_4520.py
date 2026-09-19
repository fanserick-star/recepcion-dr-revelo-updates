from __future__ import annotations

# v4.5.20 — LAN + Neon híbrido para Historia Clínica.
# Recepción conserva primero el evento en su cola local, intenta la entrega por
# LAN y mantiene Neon como respaldo. El mismo event_id evita duplicados.

import app_patch_4519 as previous
import historia_bridge
import historia_lan_transport

core = previous.core
app = previous.app
APP_VERSION = "4.5.20"

_mod = previous
_seen = set()
for _ in range(480):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

historia_lan_transport.install(historia_bridge)

V4520_CSS = r"""
#historiaDoctorBadge.lan{
  border-color:rgba(68,201,124,.58)!important;
  color:#e3faeb!important;
  background:rgba(27,116,68,.28)!important
}
#historiaDoctorBadge.lan:before{
  background:#35d174!important;
  box-shadow:0 0 0 3px rgba(53,209,116,.18)!important
}
"""

V4520_JS = r"""
;(()=>{
 if(window.__v4520HybridHistoria)return;
 window.__v4520HybridHistoria=true;

 const q=(s,r=document)=>r.querySelector(s);
 const VERSION='4.5.20';

 function ensureBadge(){
   const connection=q('#connectionBadge');
   let b=q('#historiaDoctorBadge');
   if(!b && connection){
     b=document.createElement('span');
     b.id='historiaDoctorBadge';
     connection.insertAdjacentElement('afterend',b);
   }
   return b;
 }

 async function getStatus(){
   const r=await fetch('/api/historia-bridge/status?t='+Date.now(),{
     cache:'no-store',
     headers:{'Cache-Control':'no-cache'}
   });
   if(!r.ok)throw new Error('HTTP '+r.status);
   return await r.json();
 }

 function age(seconds){
   seconds=Number(seconds);
   if(!Number.isFinite(seconds))return '';
   if(seconds<60)return 'ahora';
   const m=Math.floor(seconds/60);
   if(m<60)return 'hace '+m+' min';
   return 'hace '+Math.floor(m/60)+' h';
 }

 async function refresh(){
   const b=ensureBadge();
   if(!b)return;
   try{
     const d=await getStatus();
     b.className='';

     if(d.lan_online){
       b.classList.add('lan');
       b.textContent='Historia: LAN conectada';
       const ms=Number(d.lan_latency_ms);
       const latency=Number.isFinite(ms)&&ms>=0?' · '+ms+' ms':'';
       b.title='PC del doctor accesible por red local'
         +(d.lan_host?' · '+d.lan_host:'')
         +(d.lan_version?' · v'+d.lan_version:'')
         +latency
         +(d.configured?' · Neon de respaldo activo':' · falta enlazar respaldo Neon');
       return;
     }

     const pending=Number(d.pending||0);
     if(d.configured && d.cloud_reachable){
       b.classList.add('cloud');
       if(d.doctor_online){
         b.textContent='Historia: nube conectada';
         b.title='La LAN no respondió; Historia reportó presencia en Neon '+age(d.doctor_last_seen_age_seconds)+'.';
       }else{
         b.textContent=pending>0?'Historia: nube · '+pending+' por enviar':'Historia: nube lista';
         b.title='La PC del doctor no responde por LAN. Los atendidos quedan guardados en Neon.';
       }
       return;
     }

     b.classList.add('error');
     if(pending>0){
       b.textContent='Historia: '+pending+' pendientes';
       b.title='Sin LAN ni nube. Los atendidos siguen protegidos en la cola local.';
     }else{
       b.textContent='Historia: sin conexión';
       b.title='No responde por LAN y el respaldo de Neon no está disponible.';
     }
   }catch(err){
     b.className='error';
     b.textContent='Historia: sin comprobar';
     b.title=String(err?.message||err||'');
   }
 }

 async function version(){
   try{
     const r=await fetch('/api/version?t='+Date.now(),{cache:'no-store'});
     if(!r.ok)return;
     const d=await r.json();
     const holder=document.querySelector('#recepcionRealVersion');
     if(holder)holder.textContent='Recepción v'+String(d.version||VERSION);
   }catch(_e){}
 }

 function boot(){refresh();version()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
 window.addEventListener('focus',boot);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)boot()});
 setInterval(refresh,7000);
})();
"""

core.V460_OVERLAY_CSS=(getattr(core,"V460_OVERLAY_CSS","") or "")+"\n"+V4520_CSS
core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4520_JS

@app.get("/api/v4520/health")
def v4520_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "hybrid_historia": True,
        "lan_online": bool(state.get("lan_online")),
        "cloud_configured": bool(state.get("configured")),
        "local_outbox_pending": int(state.get("pending") or 0),
        "database_schema_changes": False,
    }

PATCH_BOOT_OK = True
