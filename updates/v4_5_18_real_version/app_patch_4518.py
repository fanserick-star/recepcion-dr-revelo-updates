from __future__ import annotations

# v4.5.18 — versión visible siempre tomada del backend real.
# Corrige el caso donde al cambiar entre pestañas Configuración se reconstruía
# y reaparecía una versión vieja almacenada por capas anteriores.

import os
import app_patch_4517 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.18"

_mod = previous
_seen = set()
for _ in range(360):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

# Deja una sola fuente de verdad para el launcher y para la interfaz.
for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/version" and "GET" in set(getattr(_route, "methods", set()) or set()):
        app.router.routes.remove(_route)

@app.get("/api/version")
def v4518_app_version():
    return {"version": APP_VERSION, "pid": os.getpid()}

V4518_CSS = r"""
#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}
#v4518VersionChip{display:inline-flex!important;align-items:center!important;padding:5px 9px!important;border-radius:999px!important;background:#edf3fb!important;color:#315d86!important;font-size:10px!important;font-weight:900!important;white-space:nowrap!important}
"""

V4518_JS = r"""
;(()=>{
 if(window.__v4518RealVersion)return; window.__v4518RealVersion=true;
 const FALLBACK='4.5.18';
 let realVersion=FALLBACK, scheduled=false, fetching=false;

 function cleanOld(){
   const h=document.querySelector('#connectionBadge');
   if(h) h.querySelectorAll('.v460-version,[data-version]').forEach(x=>x.remove());
 }

 function updatesSection(){
   return document.querySelector('[data-config-section="actualizaciones"]');
 }

 function paint(){
   cleanOld();
   const s=updatesSection();
   if(!s) return;
   s.querySelectorAll('#currentVersionBadge,.v4517-version-chip,#v4517VersionChip').forEach(x=>{
     if(x.id==='v4518VersionChip') return;
     x.style.display='none';
   });
   let chip=s.querySelector('#v4518VersionChip');
   if(!chip){
     const head=s.querySelector('.updater-panel .config-panel-head,.config-panel-head');
     if(!head) return;
     chip=document.createElement('span');
     chip.id='v4518VersionChip';
     head.appendChild(chip);
   }
   const wanted='Recepción v'+realVersion;
   if(chip.textContent!==wanted) chip.textContent=wanted;
 }

 function schedulePaint(){
   if(scheduled) return;
   scheduled=true;
   requestAnimationFrame(()=>{scheduled=false;paint()});
 }

 async function fetchReal(){
   if(fetching) return;
   fetching=true;
   try{
     const r=await fetch('/api/version?t='+Date.now(),{cache:'no-store'});
     if(r.ok){
       const d=await r.json();
       const v=String(d&&d.version||'').trim();
       if(v) realVersion=v;
     }
   }catch(_e){}
   finally{fetching=false;schedulePaint()}
 }

 function boot(){
   schedulePaint();
   fetchReal();
   const root=document.body||document.documentElement;
   if(root){
     const mo=new MutationObserver(()=>schedulePaint());
     mo.observe(root,{subtree:true,childList:true});
   }
 }

 if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();

 const os=window.show;
 if(typeof os==='function') window.show=function(...a){const r=os.apply(this,a);schedulePaint();setTimeout(schedulePaint,120);setTimeout(schedulePaint,450);return r};
 const ot=window.showConfigTab;
 if(typeof ot==='function') window.showConfigTab=function(...a){const r=ot.apply(this,a);schedulePaint();setTimeout(schedulePaint,120);setTimeout(schedulePaint,450);return r};

 setInterval(fetchReal,30000);
})();
"""

core.V460_OVERLAY_CSS=(getattr(core,"V460_OVERLAY_CSS","") or "")+"\n"+V4518_CSS
core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4518_JS

@app.get("/api/v4518/health")
def v4518_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "version_source": "api/version",
        "version_dom_observer": True,
        "survives_tab_rerender": True,
        "database_schema_changes": False,
    }

PATCH_BOOT_OK=True
