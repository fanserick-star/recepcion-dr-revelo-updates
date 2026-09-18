from __future__ import annotations

# v4.4.84 — correo opcional al facturar.
# El backend/AZUR ya admite correo vacío; este parche corrige el bloqueo visual
# que ocultaba "Revisar y emitir" cuando billingMissingFields incluía correo.

import re as _re
import app_patch_4483 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.84"

_mod = previous
_seen = set()
for _ in range(64):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""
CARD_GATE_PATCHED = False

try:
    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _old = "miss=billingMissingFields(g.patient)"
    _new = "miss=(billingMissingFields(g.patient)||[]).filter(x=>!['correo','email','e-mail'].includes(String(x||'').trim().toLowerCase()))"
    if _old in _js:
        _js = _js.replace(_old, _new)
        CARD_GATE_PATCHED = True

    _js = _re.sub(r"""const\s+VERSION\s*=\s*['\"]4\.4\.\d+['\"]\s*;""", "const VERSION='4.4.84';", _js)
    _js = _re.sub(r"""const\s+V\s*=\s*['\"]4\.4\.\d+['\"]\s*;""", "const V='4.4.84';", _js)

    V4484_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{content:"v4.4.84"!important;font-size:9px!important;line-height:1!important;font-weight:850!important}
"""

    V4484_JS = r"""
;(()=>{
  if(window.__v4484OptionalBillingEmail)return;
  window.__v4484OptionalBillingEmail=true;
  const VERSION='4.4.84';
  const norm=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  const emailMissing=v=>['correo','email','e-mail'].includes(norm(v));

  const oldMissing=window.billingMissingFields;
  if(typeof oldMissing==='function'&&!oldMissing.__v4484){
    const wrapped=function(){const r=oldMissing.apply(this,arguments);return Array.isArray(r)?r.filter(v=>!emailMissing(v)):r};
    wrapped.__v4484=true;window.billingMissingFields=wrapped;
  }

  function relax(){
    document.querySelectorAll('#facturacion input[type="email"],#facturacion input[name*="correo" i]').forEach(el=>{
      el.required=false;el.removeAttribute('required');el.setAttribute('aria-required','false');
    });
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION)});
  }
  const oldEditor=window.openBillingRecipientEditor;
  if(typeof oldEditor==='function'&&!oldEditor.__v4484){
    const wrapped=function(){const r=oldEditor.apply(this,arguments);setTimeout(relax,0);setTimeout(relax,80);return r};
    wrapped.__v4484=true;window.openBillingRecipientEditor=wrapped;
  }
  relax();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',relax,{once:true});
})();
"""

    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4484_CSS
    core.V460_OVERLAY_JS = _js + "\n" + V4484_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4484/health")
def v4484_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "billing_email_optional": True,
        "billing_card_gate_patched": CARD_GATE_PATCHED,
        "database_changes": False,
        "receipt_layout_version": "4.4.69",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level="warning", workers=1)
