from __future__ import annotations

import app_patch_4511 as previous
import historia_bridge

core = previous.core
app = previous.app
APP_VERSION = "4.5.17"

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

for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/historia-bridge/status" and "GET" in set(getattr(_route, "methods", set()) or set()):
        app.router.routes.remove(_route)
        break

@app.get("/api/historia-bridge/status")
def v4517_historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()

V4517_CSS = r"""
#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}
#historiaDoctorBadge{display:inline-flex!important;align-items:center!important;gap:7px!important;min-height:31px!important;padding:6px 11px!important;margin-left:8px!important;border:1px solid rgba(148,163,184,.42)!important;border-radius:999px!important;background:rgba(255,255,255,.08)!important;color:#d9e4f2!important;font-size:9px!important;font-weight:850!important;white-space:nowrap!important;vertical-align:middle!important}
#historiaDoctorBadge:before{content:""!important;width:8px!important;height:8px!important;border-radius:50%!important;background:#94a3b8!important;box-shadow:0 0 0 3px rgba(148,163,184,.12)!important}
#historiaDoctorBadge.online{border-color:rgba(68,201,124,.55)!important;color:#dff8e8!important;background:rgba(28,110,66,.22)!important}
#historiaDoctorBadge.online:before{background:#35d174!important;box-shadow:0 0 0 3px rgba(53,209,116,.16)!important}
#historiaDoctorBadge.cloud{border-color:rgba(238,187,75,.52)!important;color:#fff0c7!important;background:rgba(132,91,15,.2)!important}
#historiaDoctorBadge.cloud:before{background:#efbd4c!important}
#historiaDoctorBadge.error{border-color:rgba(222,105,105,.52)!important;color:#ffe0e0!important;background:rgba(130,45,45,.2)!important}
#historiaDoctorBadge.error:before{background:#e66a6a!important}
.v4517-version-chip{display:inline-flex!important;align-items:center!important;padding:5px 9px!important;border-radius:999px!important;background:#edf3fb!important;color:#315d86!important;font-size:10px!important;font-weight:900!important}
@media(max-width:900px){#historiaDoctorBadge{display:none!important}}
"""

V4517_JS = r"""
;(()=>{
 if(window.__v4517HistoriaLink)return;window.__v4517HistoriaLink=true;
 const VERSION='4.5.17',q=(s,r=document)=>r.querySelector(s);
 function stripVersion(){const h=q('#connectionBadge');if(h)h.querySelectorAll('.v460-version,[data-version]').forEach(x=>x.remove())}
 function badge(){stripVersion();const h=q('#connectionBadge');if(!h)return null;let b=q('#historiaDoctorBadge');if(!b){b=document.createElement('span');b.id='historiaDoctorBadge';b.textContent='Historia: comprobando…';h.insertAdjacentElement('afterend',b)}return b}
 function age(s){s=Number(s);if(!Number.isFinite(s))return'';if(s<60)return'ahora';const m=Math.floor(s/60);return m<60?'hace '+m+' min':'hace '+Math.floor(m/60)+' h'}
 async function refresh(){const b=badge();if(!b)return;try{const d=await (typeof window.api==='function'?window.api('/api/historia-bridge/status'):fetch('/api/historia-bridge/status').then(r=>r.json()));b.className='';if(!d.configured){b.classList.add('error');b.textContent='Historia: sin vincular';b.title='Falta la vinculación segura con Historia Clínica.';return}if(Number(d.pending||0)>0){b.classList.add('cloud');b.textContent='Historia: '+Number(d.pending)+' por enviar';b.title='Recepción conserva estos eventos localmente y los reenviará.';return}if(d.doctor_online){b.classList.add('online');b.textContent='Historia: doctor conectado';b.title='Historia Clínica sincronizó '+age(d.doctor_last_seen_age_seconds)+'.'}else if(d.cloud_reachable){b.classList.add('cloud');b.textContent='Historia: cola en nube lista';b.title='Los atendidos quedan guardados en la nube aunque la PC del doctor esté apagada.'}else{b.classList.add('error');b.textContent='Historia: sin conexión';b.title=d.presence_error||d.last_error||''}}catch(e){b.className='error';b.textContent='Historia: sin comprobar';b.title=String(e?.message||e||'')}}
 function versionChip(){const s=document.querySelector('[data-config-section="actualizaciones"]');if(!s)return;s.querySelectorAll('#currentVersionBadge').forEach(x=>x.style.display='none');let c=q('#v4517VersionChip',s);if(!c){const h=s.querySelector('.updater-panel .config-panel-head,.config-panel-head');if(!h)return;c=document.createElement('span');c.id='v4517VersionChip';c.className='v4517-version-chip';h.appendChild(c)}c.textContent='Recepción v'+VERSION}
 function boot(){badge();versionChip();refresh()}
 const os=window.show;if(typeof os==='function')window.show=function(...a){const r=os.apply(this,a);setTimeout(()=>{badge();versionChip()},40);return r};
 const ot=window.showConfigTab;if(typeof ot==='function')window.showConfigTab=function(...a){const r=ot.apply(this,a);setTimeout(versionChip,40);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
 setTimeout(boot,350);setTimeout(boot,1400);setInterval(refresh,60000);
})();
"""

core.V460_OVERLAY_CSS=(getattr(core,"V460_OVERLAY_CSS","") or "")+"\n"+V4517_CSS
core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4517_JS

@app.get("/api/v4517/health")
def v4517_health(user=core.Depends(core.current_user)):
    return {"ok":True,"version":APP_VERSION,"historia_bridge_presence":True,"version_moved_to_settings":True,"footer_version_removed":True,"cloud_queue_survives_doctor_offline":True,"database_schema_changes":False}

PATCH_BOOT_OK=True
