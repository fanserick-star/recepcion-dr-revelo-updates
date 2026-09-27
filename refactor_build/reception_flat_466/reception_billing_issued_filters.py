from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import re as _re
previous = _rf_layers['app_patch_4479']
core = previous.core
app = previous.app
APP_VERSION = '4.4.80'
_mod = previous
_seen = set()
for _ in range(48):
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
STATE_HOLDER_REPAIRED = False
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _needle = "sec.querySelector('.billing-filters')?.remove();"
    _replacement = "sec.querySelector('.billing-filters')?.setAttribute('hidden','');"
    if _needle in _js:
        _js = _js.replace(_needle, _replacement)
        STATE_HOLDER_REPAIRED = True
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.80';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.80';", _js)
    V4480_CSS = '\n/* v4.4.80 — filtros internos conservados pero invisibles */\n#facturacion .billing-filters{display:none!important}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.80"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4480_JS = "\n;(()=>{\n  if(window.__v4480BillingStateHotfix)return;\n  window.__v4480BillingStateHotfix=true;\n  const VERSION='4.4.80';\n\n  function preserveBillingState(){\n    const sec=document.querySelector('#facturacion');\n    if(!sec)return;\n    const filters=sec.querySelector('.billing-filters');\n    if(filters){\n      filters.hidden=true;\n      filters.style.display='none';\n    }\n    const state=document.querySelector('#bEstado');\n    if(state){\n      state.setAttribute('aria-hidden','true');\n      state.tabIndex=-1;\n    }\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;\n      el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n\n  const oldLoad=window.loadBilling;\n  if(typeof oldLoad==='function'){\n    window.loadBilling=async function(){\n      preserveBillingState();\n      const out=await oldLoad.apply(this,arguments);\n      preserveBillingState();\n      return out;\n    };\n  }\n\n  const oldSet=window.setBillingStatus;\n  if(typeof oldSet==='function'){\n    window.setBillingStatus=async function(status){\n      preserveBillingState();\n      const out=await oldSet.apply(this,arguments);\n      preserveBillingState();\n      return out;\n    };\n  }\n\n  function boot(){\n    preserveBillingState();\n    setTimeout(preserveBillingState,100);\n    setTimeout(preserveBillingState,500);\n  }\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});\n  else boot();\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4480_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4480_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.80 billing state hotfix failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4480/health')
def v4480_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'billing_state_holder_preserved': True, 'cleanup_4479_preserved': True, 'state_holder_repaired_in_bundle': STATE_HOLDER_REPAIRED, 'database_changes': False, 'backend_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
