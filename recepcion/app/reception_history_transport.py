from __future__ import annotations

import reception_version_sidebar as _dep_version_sidebar
import historia_bridge
import historia_lan_transport

core = _dep_version_sidebar.core
app = _dep_version_sidebar.app
APP_VERSION = str(core.APP_VERSION or "")
historia_lan_transport.install(historia_bridge)

V4520_CSS = r"""
#historiaDoctorBadge.lan{
  border-color:rgba(68,201,124,.58)!important;color:#e3faeb!important;
  background:rgba(27,116,68,.28)!important
}
#historiaDoctorBadge.lan:before{
  background:#35d174!important;box-shadow:0 0 0 3px rgba(53,209,116,.18)!important
}
"""

V4520_JS = r"""
;(()=>{
 if(window.__historyLanStatus)return;window.__historyLanStatus=true;
 const q=(s,r=document)=>r.querySelector(s);
 function ensureBadge(){const c=q('#connectionBadge');let b=q('#historiaDoctorBadge');if(!b&&c){b=document.createElement('span');b.id='historiaDoctorBadge';c.insertAdjacentElement('afterend',b)}return b}
 async function getStatus(){const r=await fetch('/api/historia-bridge/status?t='+Date.now(),{cache:'no-store',headers:{'Cache-Control':'no-cache'}});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
 async function refresh(){const b=ensureBadge();if(!b)return;try{const d=await getStatus();b.className='';const pending=Number(d.pending||0);if(d.lan_online){b.classList.add('lan');b.textContent='Historia: LAN conectada';const ms=Number(d.lan_latency_ms);b.title='PC del doctor accesible por red local'+(d.lan_host?' · '+d.lan_host:'')+(d.lan_version?' · v'+d.lan_version:'')+(Number.isFinite(ms)&&ms>=0?' · '+ms+' ms':'')+' · Pacientes en espera viajan por LAN';return}b.classList.add('error');if(pending>0){b.textContent='Historia: '+pending+' pendientes';b.title='La PC del doctor no responde todavía. Los turnos están protegidos en la cola local y se reintentarán por LAN.'}else{b.textContent='Historia: LAN sin conexión';b.title='La PC del doctor no responde en la red local. La vinculación de fichas por Neon es independiente.'}}catch(err){b.className='error';b.textContent='Historia: sin comprobar';b.title=String(err?.message||err||'')}}
 function boot(){refresh()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();window.addEventListener('focus',boot);document.addEventListener('visibilitychange',()=>{if(!document.hidden)boot()});setInterval(refresh,30000);
})();
"""
core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4520_CSS
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4520_JS

@app.get("/api/v4520/health")
def history_transport_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "lan_online": bool(state.get("lan_online")),
        "local_outbox_pending": int(state.get("pending") or 0),
        "handoff_pending": int(state.get("handoff_pending") or 0),
        "control_pending": int(state.get("control_pending") or 0),
        "waiting_queue_transport": "lan_only",
        "cloud_queue_write": False,
        "database_schema_changes": False,
    }

PATCH_BOOT_OK = True
