from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import re as _re
previous = _rf_layers['app_patch_4478']
core = previous.core
app = previous.app
APP_VERSION = '4.4.79'
_mod = previous
_seen = set()
for _ in range(44):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
LEGACY_SERVICE_MANAGER_DISABLED = False
LEGACY_VERSION_OBSERVER_DISABLED = False
FACTURERO_DESTINATION_REMOVED = False
try:
    try:
        destinations = getattr(core, 'EXTERNAL_DESTINATIONS', None)
        if isinstance(destinations, dict):
            FACTURERO_DESTINATION_REMOVED = destinations.pop('facturero', None) is not None
    except Exception:
        FACTURERO_DESTINATION_REMOVED = False
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _prelude = 'window.__v4475FastSaveAndServiceDelete=true;\n'
    _before = _js
    _js = _js.replace('    installProcedureManager();\n    installVersionPainter();', '    /* v4.4.79: administradores visuales heredados desactivados */')
    LEGACY_SERVICE_MANAGER_DISABLED = _js != _before
    _before = _js
    _js = _js.replace('    installVersionPainter();', '    /* v4.4.79: observador heredado de versión desactivado */')
    if _js != _before:
        LEGACY_VERSION_OBSERVER_DISABLED = True
    else:
        LEGACY_VERSION_OBSERVER_DISABLED = LEGACY_SERVICE_MANAGER_DISABLED
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.79';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.79';", _js)
    V4479_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.79"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n[data-config-tab="services"],\n[data-config-section="services"],\n#v458ServicePanel{display:none!important}\n#facturacion .billing-filters,\n#v482BatchEmit{display:none!important}\n#v4470ProcedureManager,\n#v4475ProcedureManager,\n[data-config-section="procedimientos"] > .v4476-service-old{display:none!important}\n'
    V4479_JS = '\n;(()=>{\n  if(window.__v4479Cleanup)return;\n  window.__v4479Cleanup=true;\n  const VERSION=\'4.4.79\';\n\n  const txt=v=>String(v??\'\').replace(/\\s+/g,\' \').trim();\n  const norm=v=>txt(v).normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').toLowerCase();\n\n  function isFactureroControl(el){\n    const blob=[\n      txt(el?.textContent),\n      String(el?.getAttribute?.(\'href\')||\'\'),\n      String(el?.getAttribute?.(\'onclick\')||\'\'),\n      String(el?.dataset?.target||\'\'),\n      String(el?.dataset?.destination||\'\')\n    ].join(\' \').toLowerCase();\n    return blob.includes(\'facturero movil\')\n      || blob.includes(\'factureromovil\')\n      || /\\bfacturero\\b/.test(blob);\n  }\n\n  function cleanupBilling(){\n    const sec=document.querySelector(\'#facturacion\');\n    if(!sec)return;\n    [...sec.querySelectorAll(\'button,a\')].forEach(el=>{\n      if(isFactureroControl(el))el.remove();\n    });\n    const summary=sec.querySelector(\'#billingSummary\');\n    if(summary){\n      [...summary.querySelectorAll(\'button\')].forEach(btn=>{\n        if(norm(btn.textContent).includes(\'aprobada\'))btn.remove();\n      });\n    }\n    sec.querySelector(\'.billing-filters\')?.remove();\n    sec.querySelector(\'#v482BatchEmit\')?.remove();\n    [...sec.querySelectorAll(\'.billing-title-actions\')].forEach(row=>{\n      const useful=[...row.querySelectorAll(\'button,a\')].filter(el=>!isFactureroControl(el));\n      if(!useful.length)row.style.display=\'none\';\n      else row.style.display=\'\';\n    });\n  }\n\n  function cleanupConfig(){\n    const config=document.querySelector(\'#config\');\n    if(!config)return;\n    config.querySelector(\'[data-config-tab="services"]\')?.remove();\n    config.querySelector(\'[data-config-section="services"]\')?.remove();\n    config.querySelector(\'#v458ServicePanel\')?.remove();\n\n    const proc=config.querySelector(\'[data-config-section="procedimientos"]\');\n    if(proc&&proc.querySelector(\'#v4476ServicePanel\')){\n      proc.querySelector(\'#v4470ProcedureManager\')?.remove();\n      proc.querySelector(\'#v4475ProcedureManager\')?.remove();\n      [...proc.querySelectorAll(\':scope > .v4476-service-old\')].forEach(el=>el.remove());\n    }\n  }\n\n  function stabilizeVersion(){\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n\n  function cleanupAll(){\n    cleanupBilling();\n    cleanupConfig();\n    stabilizeVersion();\n  }\n\n  const stableLoadBilling=window.loadBilling;\n  if(typeof stableLoadBilling===\'function\'){\n    window.loadBilling=async function(){\n      const out=await stableLoadBilling.apply(this,arguments);\n      cleanupBilling();\n      stabilizeVersion();\n      return out;\n    };\n  }\n\n  const stableSetBillingStatus=window.setBillingStatus;\n  if(typeof stableSetBillingStatus===\'function\'){\n    window.setBillingStatus=async function(){\n      const out=await stableSetBillingStatus.apply(this,arguments);\n      cleanupBilling();\n      stabilizeVersion();\n      return out;\n    };\n  }\n\n  const stableLoadProcedures=window.loadProcedures;\n  if(typeof stableLoadProcedures===\'function\'){\n    window.loadProcedures=async function(){\n      const out=await stableLoadProcedures.apply(this,arguments);\n      cleanupConfig();\n      return out;\n    };\n  }\n\n  const stableShowConfigTab=window.showConfigTab;\n  if(typeof stableShowConfigTab===\'function\'){\n    window.showConfigTab=function(tab){\n      if(String(tab||\'\').toLowerCase()===\'services\')tab=\'sistema\';\n      const args=[...arguments];\n      args[0]=tab;\n      const out=stableShowConfigTab.apply(this,args);\n      setTimeout(cleanupConfig,0);\n      return out;\n    };\n  }\n\n  document.addEventListener(\'click\',event=>{\n    const nav=event.target?.closest?.(\n      \'[data-section="facturacion"],[data-config-tab="facturacion"],\'\n      +\'[data-section="config"],[data-config-tab="procedimientos"],\'\n      +\'[data-config-tab="sistema"]\'\n    );\n    if(nav)setTimeout(cleanupAll,30);\n  },true);\n\n  function boot(){\n    cleanupAll();\n    setTimeout(cleanupAll,120);\n    setTimeout(cleanupAll,600);\n  }\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  }else{\n    boot();\n  }\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4479_CSS
    core.V460_OVERLAY_JS = _prelude + _js + '\n' + V4479_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.79 cleanup patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4479/health')
def v4479_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'facturero_destination_removed': FACTURERO_DESTINATION_REMOVED, 'legacy_service_manager_disabled': LEGACY_SERVICE_MANAGER_DISABLED, 'legacy_version_observer_disabled': LEGACY_VERSION_OBSERVER_DISABLED, 'obsolete_services_tab_removed': True, 'obsolete_billing_filters_removed': True, 'obsolete_approved_tab_removed': True, 'batch_emit_ui_removed': True, 'azur_preserved': True, 'no_facturables_preserved': True, 'activity_trash_preserved': True, 'receipt_layout_version': '4.4.69', 'database_changes': False, 'bendo_enabled': False, 'base': '4.4.78'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
