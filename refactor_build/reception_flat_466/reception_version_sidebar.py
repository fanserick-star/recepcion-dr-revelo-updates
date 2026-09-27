from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import os
previous = _rf_layers['app_patch_4518']
core = previous.core
app = previous.app
APP_VERSION = '4.5.19'
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
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/version' and 'GET' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.get('/api/version')
def v4519_app_version():
    return {'version': APP_VERSION, 'pid': os.getpid(), 'source': 'backend'}
V4519_CSS = '\n#sidebarRealVersion{\n  display:flex!important;\n  align-items:center!important;\n  justify-content:center!important;\n  width:calc(100% - 28px)!important;\n  min-height:28px!important;\n  box-sizing:border-box!important;\n  margin:8px 14px 10px!important;\n  padding:5px 10px!important;\n  border:1px solid rgba(148,163,184,.28)!important;\n  border-radius:11px!important;\n  background:rgba(15,23,42,.16)!important;\n  color:rgba(226,232,240,.78)!important;\n  font-size:10px!important;\n  font-weight:800!important;\n  letter-spacing:.02em!important;\n  text-align:center!important;\n  white-space:nowrap!important;\n  line-height:1.15!important;\n}\n#sidebarRealVersion[data-verified="1"]::before{\n  content:""!important;\n  width:6px!important;\n  height:6px!important;\n  margin-right:7px!important;\n  border-radius:50%!important;\n  background:#7dd3fc!important;\n  box-shadow:0 0 0 3px rgba(125,211,252,.10)!important;\n}\n#sidebarRealVersion[data-verified="0"]{opacity:.72!important}\n#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}\n'
V4519_JS = '\n;(()=>{\n if(window.__v4519SidebarRealVersion)return;\n window.__v4519SidebarRealVersion=true;\n\n let realVersion=\'\';\n let verified=false;\n let fetching=false;\n let paintQueued=false;\n let lastFetch=0;\n\n function oldVersionCleanup(){\n   const connection=document.querySelector(\'#connectionBadge\');\n   if(connection){\n     connection.querySelectorAll(\'.v460-version,[data-version]\').forEach(x=>x.remove());\n   }\n }\n\n function ensureSidebarVersion(){\n   oldVersionCleanup();\n   const historia=document.querySelector(\'#historiaDoctorBadge\');\n   const connection=document.querySelector(\'#connectionBadge\');\n   const anchor=historia||connection;\n   if(!anchor)return null;\n\n   let el=document.querySelector(\'#sidebarRealVersion\');\n   if(!el){\n     el=document.createElement(\'div\');\n     el.id=\'sidebarRealVersion\';\n   }\n\n   if(anchor.nextElementSibling!==el){\n     anchor.insertAdjacentElement(\'afterend\',el);\n   }\n\n   const text=\'Recepción v\'+(realVersion||\'…\');\n   if(el.textContent!==text)el.textContent=text;\n   el.dataset.verified=verified?\'1\':\'0\';\n   el.title=verified\n     ? \'Versión confirmada directamente por el backend en ejecución.\'\n     : \'Comprobando versión real del backend…\';\n   return el;\n }\n\n function paint(){\n   paintQueued=false;\n   ensureSidebarVersion();\n\n   const section=document.querySelector(\'[data-config-section="actualizaciones"]\');\n   if(section&&realVersion){\n     const chip=section.querySelector(\'#v4518VersionChip\');\n     if(chip)chip.textContent=\'Recepción v\'+realVersion;\n   }\n }\n\n function queuePaint(){\n   if(paintQueued)return;\n   paintQueued=true;\n   requestAnimationFrame(paint);\n }\n\n async function fetchReal(force=false){\n   const now=Date.now();\n   if(fetching)return;\n   if(!force && now-lastFetch<5000){queuePaint();return;}\n   fetching=true;\n   try{\n     const r=await fetch(\'/api/version?t=\'+now,{cache:\'no-store\',headers:{\'Cache-Control\':\'no-cache\'}});\n     if(!r.ok)throw new Error(\'HTTP \'+r.status);\n     const d=await r.json();\n     const v=String(d&&d.version||\'\').trim();\n     if(v){\n       realVersion=v;\n       verified=true;\n       lastFetch=Date.now();\n     }\n   }catch(_e){\n     verified=false;\n   }finally{\n     fetching=false;\n     queuePaint();\n   }\n }\n\n function onUiChange(){\n   queuePaint();\n   fetchReal(false);\n }\n\n function boot(){\n   queuePaint();\n   fetchReal(true);\n\n   const root=document.body||document.documentElement;\n   if(root){\n     const mo=new MutationObserver(()=>queuePaint());\n     mo.observe(root,{subtree:true,childList:true});\n   }\n\n   document.addEventListener(\'visibilitychange\',()=>{\n     if(!document.hidden)fetchReal(true);\n   });\n   window.addEventListener(\'focus\',()=>fetchReal(true));\n }\n\n if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n else boot();\n\n const oldShow=window.show;\n if(typeof oldShow===\'function\'){\n   window.show=function(...args){\n     const out=oldShow.apply(this,args);\n     onUiChange();\n     setTimeout(onUiChange,100);\n     setTimeout(onUiChange,400);\n     return out;\n   };\n }\n\n const oldConfig=window.showConfigTab;\n if(typeof oldConfig===\'function\'){\n   window.showConfigTab=function(...args){\n     const out=oldConfig.apply(this,args);\n     onUiChange();\n     setTimeout(onUiChange,100);\n     setTimeout(onUiChange,400);\n     return out;\n   };\n }\n\n setInterval(()=>fetchReal(true),30000);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4519_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4519_JS

@app.get('/api/v4519/health')
def v4519_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'sidebar_version_visible': True, 'version_source': 'backend_api_version', 'cache_disabled': True, 'mutation_observer': True, 'focus_recheck': True, 'poll_seconds': 30, 'database_schema_changes': False}
PATCH_BOOT_OK = True
