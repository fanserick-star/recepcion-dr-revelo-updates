from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import re as _re
previous = _rf_layers['app_patch_4480']
core = previous.core
app = previous.app
APP_VERSION = '4.4.81'
_mod = previous
_seen = set()
for _ in range(52):
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
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.81';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.81';", _js)
    V4481_CSS = '\n/* v4.4.81 — Facturero Móvil eliminado también de modales */\na[href*="factureromovil" i],\nbutton[onclick*="facturero" i],\na[onclick*="facturero" i],\n[data-destination="facturero" i],\n[data-target="facturero" i]{\n  display:none!important;\n}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.81"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4481_JS = "\n;(()=>{\n  if(window.__v4481RemoveFactureroEverywhere)return;\n  window.__v4481RemoveFactureroEverywhere=true;\n  const VERSION='4.4.81';\n\n  const cleanText=v=>String(v??'')\n    .normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')\n    .replace(/\\s+/g,' ').trim().toLowerCase();\n\n  function isFacturero(el){\n    if(!el)return false;\n    const blob=[\n      cleanText(el.textContent),\n      String(el.getAttribute?.('href')||'').toLowerCase(),\n      String(el.getAttribute?.('onclick')||'').toLowerCase(),\n      String(el.dataset?.destination||'').toLowerCase(),\n      String(el.dataset?.target||'').toLowerCase()\n    ].join(' ');\n    return blob.includes('facturero movil')\n      || blob.includes('factureromovil')\n      || /\\bfacturero\\b/.test(blob);\n  }\n\n  function removeFactureroEverywhere(){\n    document.querySelectorAll('button,a').forEach(el=>{\n      if(isFacturero(el))el.remove();\n    });\n\n    document.querySelectorAll(\n      '.billing-title-actions,.modal-actions,.billing-copy-actions,.billing-actions'\n    ).forEach(box=>{\n      const visible=[...box.querySelectorAll('button,a')].filter(el=>!isFacturero(el));\n      if(!visible.length && !cleanText(box.textContent))box.style.display='none';\n    });\n\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;\n      el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n\n  function sweepSoon(){\n    removeFactureroEverywhere();\n    setTimeout(removeFactureroEverywhere,0);\n    setTimeout(removeFactureroEverywhere,60);\n    setTimeout(removeFactureroEverywhere,180);\n  }\n\n  function wrapModalFunction(name){\n    const old=window[name];\n    if(typeof old!=='function'||old.__v4481NoFacturero)return;\n    const wrapped=function(){\n      const out=old.apply(this,arguments);\n      sweepSoon();\n      if(out&&typeof out.then==='function'){\n        Promise.resolve(out).finally(sweepSoon);\n      }\n      return out;\n    };\n    wrapped.__v4481NoFacturero=true;\n    wrapped.__v4481Original=old;\n    window[name]=wrapped;\n  }\n\n  [\n    'copyBillingData',\n    'openBillingRecipientEditor',\n    'openBillingDataModal',\n    'openBillingCopyModal',\n    'showBillingData'\n  ].forEach(wrapModalFunction);\n\n  document.addEventListener('click',event=>{\n    const control=event.target?.closest?.('button,a');\n    if(control&&isFacturero(control)){\n      event.preventDefault();\n      event.stopImmediatePropagation();\n      control.remove();\n      return;\n    }\n    const trigger=event.target?.closest?.(\n      '.billing-card button,.billing-card a,#facturacion button,#facturacion a'\n    );\n    if(trigger)setTimeout(sweepSoon,0);\n  },true);\n\n  function boot(){\n    sweepSoon();\n    [\n      'copyBillingData',\n      'openBillingRecipientEditor',\n      'openBillingDataModal',\n      'openBillingCopyModal',\n      'showBillingData'\n    ].forEach(wrapModalFunction);\n  }\n  if(document.readyState==='loading'){\n    document.addEventListener('DOMContentLoaded',boot,{once:true});\n  }else{\n    boot();\n  }\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4481_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4481_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.81 remove Facturero modal patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4481/health')
def v4481_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'facturero_removed_globally': True, 'facturero_click_blocked': True, 'billing_emitidas_fix_preserved': True, 'uses_new_dom_observer': False, 'database_changes': False, 'backend_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
