from __future__ import annotations
import reception_launcher_status as _dep_launcher_status
import os
core = _dep_launcher_status.core
app = _dep_launcher_status.app
APP_VERSION = '4.5.18'
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/version' and 'GET' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.get('/api/version')
def v4518_app_version():
    return {'version': APP_VERSION, 'pid': os.getpid()}
V4518_CSS = '\n#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}\n#v4518VersionChip{display:inline-flex!important;align-items:center!important;padding:5px 9px!important;border-radius:999px!important;background:#edf3fb!important;color:#315d86!important;font-size:10px!important;font-weight:900!important;white-space:nowrap!important}\n'
V4518_JS = '\n;(()=>{\n if(window.__v4518RealVersion)return; window.__v4518RealVersion=true;\n const FALLBACK=\'4.5.18\';\n let realVersion=FALLBACK, scheduled=false, fetching=false;\n\n function cleanOld(){\n   const h=document.querySelector(\'#connectionBadge\');\n   if(h) h.querySelectorAll(\'.v460-version,[data-version]\').forEach(x=>x.remove());\n }\n\n function updatesSection(){\n   return document.querySelector(\'[data-config-section="actualizaciones"]\');\n }\n\n function paint(){\n   cleanOld();\n   const s=updatesSection();\n   if(!s) return;\n   s.querySelectorAll(\'#currentVersionBadge,.v4517-version-chip,#v4517VersionChip\').forEach(x=>{\n     if(x.id===\'v4518VersionChip\') return;\n     x.style.display=\'none\';\n   });\n   let chip=s.querySelector(\'#v4518VersionChip\');\n   if(!chip){\n     const head=s.querySelector(\'.updater-panel .config-panel-head,.config-panel-head\');\n     if(!head) return;\n     chip=document.createElement(\'span\');\n     chip.id=\'v4518VersionChip\';\n     head.appendChild(chip);\n   }\n   const wanted=\'Recepción v\'+realVersion;\n   if(chip.textContent!==wanted) chip.textContent=wanted;\n }\n\n function schedulePaint(){\n   if(scheduled) return;\n   scheduled=true;\n   requestAnimationFrame(()=>{scheduled=false;paint()});\n }\n\n async function fetchReal(){\n   if(fetching) return;\n   fetching=true;\n   try{\n     const r=await fetch(\'/api/version?t=\'+Date.now(),{cache:\'no-store\'});\n     if(r.ok){\n       const d=await r.json();\n       const v=String(d&&d.version||\'\').trim();\n       if(v) realVersion=v;\n     }\n   }catch(_e){}\n   finally{fetching=false;schedulePaint()}\n }\n\n function boot(){\n   schedulePaint();\n   fetchReal();\n   const root=document.body||document.documentElement;\n   if(root){\n     const mo=new MutationObserver(()=>schedulePaint());\n     mo.observe(root,{subtree:true,childList:true});\n   }\n }\n\n if(document.readyState===\'loading\') document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n else boot();\n\n const os=window.show;\n if(typeof os===\'function\') window.show=function(...a){const r=os.apply(this,a);schedulePaint();setTimeout(schedulePaint,120);setTimeout(schedulePaint,450);return r};\n const ot=window.showConfigTab;\n if(typeof ot===\'function\') window.showConfigTab=function(...a){const r=ot.apply(this,a);schedulePaint();setTimeout(schedulePaint,120);setTimeout(schedulePaint,450);return r};\n\n setInterval(fetchReal,30000);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4518_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4518_JS

@app.get('/api/v4518/health')
def v4518_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'version_source': 'api/version', 'version_dom_observer': True, 'survives_tab_rerender': True, 'database_schema_changes': False}
PATCH_BOOT_OK = True
