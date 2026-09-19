from __future__ import annotations

# v4.5.19 — versión real siempre visible en la barra lateral.
# No guarda un número independiente en el frontend: consulta /api/version y
# se autorrepara si otra pantalla reconstruye el DOM.

import os
import app_patch_4518 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.19"

_mod = previous
_seen = set()
for _ in range(380):
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
    if getattr(_route, "path", None) == "/api/version" and "GET" in set(getattr(_route, "methods", set()) or set()):
        app.router.routes.remove(_route)

@app.get("/api/version")
def v4519_app_version():
    return {"version": APP_VERSION, "pid": os.getpid(), "source": "backend"}

V4519_CSS = r"""
#sidebarRealVersion{
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  width:calc(100% - 28px)!important;
  min-height:28px!important;
  box-sizing:border-box!important;
  margin:8px 14px 10px!important;
  padding:5px 10px!important;
  border:1px solid rgba(148,163,184,.28)!important;
  border-radius:11px!important;
  background:rgba(15,23,42,.16)!important;
  color:rgba(226,232,240,.78)!important;
  font-size:10px!important;
  font-weight:800!important;
  letter-spacing:.02em!important;
  text-align:center!important;
  white-space:nowrap!important;
  line-height:1.15!important;
}
#sidebarRealVersion[data-verified="1"]::before{
  content:""!important;
  width:6px!important;
  height:6px!important;
  margin-right:7px!important;
  border-radius:50%!important;
  background:#7dd3fc!important;
  box-shadow:0 0 0 3px rgba(125,211,252,.10)!important;
}
#sidebarRealVersion[data-verified="0"]{opacity:.72!important}
#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}
"""

V4519_JS = r"""
;(()=>{
 if(window.__v4519SidebarRealVersion)return;
 window.__v4519SidebarRealVersion=true;

 let realVersion='';
 let verified=false;
 let fetching=false;
 let paintQueued=false;
 let lastFetch=0;

 function oldVersionCleanup(){
   const connection=document.querySelector('#connectionBadge');
   if(connection){
     connection.querySelectorAll('.v460-version,[data-version]').forEach(x=>x.remove());
   }
 }

 function ensureSidebarVersion(){
   oldVersionCleanup();
   const historia=document.querySelector('#historiaDoctorBadge');
   const connection=document.querySelector('#connectionBadge');
   const anchor=historia||connection;
   if(!anchor)return null;

   let el=document.querySelector('#sidebarRealVersion');
   if(!el){
     el=document.createElement('div');
     el.id='sidebarRealVersion';
   }

   if(anchor.nextElementSibling!==el){
     anchor.insertAdjacentElement('afterend',el);
   }

   const text='Recepción v'+(realVersion||'…');
   if(el.textContent!==text)el.textContent=text;
   el.dataset.verified=verified?'1':'0';
   el.title=verified
     ? 'Versión confirmada directamente por el backend en ejecución.'
     : 'Comprobando versión real del backend…';
   return el;
 }

 function paint(){
   paintQueued=false;
   ensureSidebarVersion();

   const section=document.querySelector('[data-config-section="actualizaciones"]');
   if(section&&realVersion){
     const chip=section.querySelector('#v4518VersionChip');
     if(chip)chip.textContent='Recepción v'+realVersion;
   }
 }

 function queuePaint(){
   if(paintQueued)return;
   paintQueued=true;
   requestAnimationFrame(paint);
 }

 async function fetchReal(force=false){
   const now=Date.now();
   if(fetching)return;
   if(!force && now-lastFetch<5000){queuePaint();return;}
   fetching=true;
   try{
     const r=await fetch('/api/version?t='+now,{cache:'no-store',headers:{'Cache-Control':'no-cache'}});
     if(!r.ok)throw new Error('HTTP '+r.status);
     const d=await r.json();
     const v=String(d&&d.version||'').trim();
     if(v){
       realVersion=v;
       verified=true;
       lastFetch=Date.now();
     }
   }catch(_e){
     verified=false;
   }finally{
     fetching=false;
     queuePaint();
   }
 }

 function onUiChange(){
   queuePaint();
   fetchReal(false);
 }

 function boot(){
   queuePaint();
   fetchReal(true);

   const root=document.body||document.documentElement;
   if(root){
     const mo=new MutationObserver(()=>queuePaint());
     mo.observe(root,{subtree:true,childList:true});
   }

   document.addEventListener('visibilitychange',()=>{
     if(!document.hidden)fetchReal(true);
   });
   window.addEventListener('focus',()=>fetchReal(true));
 }

 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
 else boot();

 const oldShow=window.show;
 if(typeof oldShow==='function'){
   window.show=function(...args){
     const out=oldShow.apply(this,args);
     onUiChange();
     setTimeout(onUiChange,100);
     setTimeout(onUiChange,400);
     return out;
   };
 }

 const oldConfig=window.showConfigTab;
 if(typeof oldConfig==='function'){
   window.showConfigTab=function(...args){
     const out=oldConfig.apply(this,args);
     onUiChange();
     setTimeout(onUiChange,100);
     setTimeout(onUiChange,400);
     return out;
   };
 }

 setInterval(()=>fetchReal(true),30000);
})();
"""

core.V460_OVERLAY_CSS=(getattr(core,"V460_OVERLAY_CSS","") or "")+"\n"+V4519_CSS
core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4519_JS

@app.get("/api/v4519/health")
def v4519_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "sidebar_version_visible": True,
        "version_source": "backend_api_version",
        "cache_disabled": True,
        "mutation_observer": True,
        "focus_recheck": True,
        "poll_seconds": 30,
        "database_schema_changes": False,
    }

PATCH_BOOT_OK=True
