from __future__ import annotations
import reception_update_launcher as _dep_update_launcher
import re as _re
core = _dep_update_launcher.core
app = _dep_update_launcher.app
APP_VERSION = '4.4.84'
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
CARD_GATE_PATCHED = False
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _old = 'miss=billingMissingFields(g.patient)'
    _new = "miss=(billingMissingFields(g.patient)||[]).filter(x=>!['correo','email','e-mail'].includes(String(x||'').trim().toLowerCase()))"
    if _old in _js:
        _js = _js.replace(_old, _new)
        CARD_GATE_PATCHED = True
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.84';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.84';", _js)
    V4484_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{content:"v4.4.84"!important;font-size:9px!important;line-height:1!important;font-weight:850!important}\n'
    V4484_JS = '\n;(()=>{\n  if(window.__v4484OptionalBillingEmail)return;\n  window.__v4484OptionalBillingEmail=true;\n  const VERSION=\'4.4.84\';\n  const norm=v=>String(v??\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\n  const emailMissing=v=>[\'correo\',\'email\',\'e-mail\'].includes(norm(v));\n\n  const oldMissing=window.billingMissingFields;\n  if(typeof oldMissing===\'function\'&&!oldMissing.__v4484){\n    const wrapped=function(){const r=oldMissing.apply(this,arguments);return Array.isArray(r)?r.filter(v=>!emailMissing(v)):r};\n    wrapped.__v4484=true;window.billingMissingFields=wrapped;\n  }\n\n  function relax(){\n    document.querySelectorAll(\'#facturacion input[type="email"],#facturacion input[name*="correo" i]\').forEach(el=>{\n      el.required=false;el.removeAttribute(\'required\');el.setAttribute(\'aria-required\',\'false\');\n    });\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{el.textContent=\'v\'+VERSION;el.setAttribute(\'data-version\',\'v\'+VERSION)});\n  }\n  const oldEditor=window.openBillingRecipientEditor;\n  if(typeof oldEditor===\'function\'&&!oldEditor.__v4484){\n    const wrapped=function(){const r=oldEditor.apply(this,arguments);setTimeout(relax,0);setTimeout(relax,80);return r};\n    wrapped.__v4484=true;window.openBillingRecipientEditor=wrapped;\n  }\n  relax();\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',relax,{once:true});\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4484_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4484_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4484/health')
def v4484_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'billing_email_optional': True, 'billing_card_gate_patched': CARD_GATE_PATCHED, 'database_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
