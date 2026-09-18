from __future__ import annotations

# v4.4.86 — una sola acción de impresión en Inicio.
# - Quita los botones separados "Ver recibo", "Reimprimir" y "Comprobante".
# - Deja un único botón "Imprimir" con dos opciones: recibo o comprobante.
# - "Imprimir recibo" usa la reimpresión estable ya existente.
# - "Imprimir comprobante" usa el comprobante térmico de v4.4.85.
# - No cambia BD, Neon, AZUR, Agenda, atenciones ni diseños de impresión.

import re as _re

import app_patch_4485 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.86"

_mod = previous
_seen = set()
for _ in range(72):
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
HOME_ACTIONS_PATCHED = False

try:
    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")

    _pattern = r"  function homeActions\(g,fecha,primary\)\{.*?\n  function v4457ConsultationTurnMap"
    _replacement = r'''  function homeActions(g,fecha,primary){
    const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||'').trim());
    const pid=Number(g.patient?.id||0);
    const receiptDisabled=hasConsultation?'':` disabled aria-disabled="true" title="Este registro no tiene consulta médica"`;
    return `<div class="v478-home-actions"><details class="v4486-print-menu"><summary class="v4486-print-summary">${homeActionIcon('print')}<span>Imprimir</span></summary><div class="v4486-print-pop"><button type="button"${receiptDisabled} onclick="event.preventDefault();event.stopPropagation();this.closest('details')?.removeAttribute('open');reprintReceiptFromHome(${pid},'${eh(fecha)}')">${homeActionIcon('receipt')}<span>Imprimir recibo</span></button><button type="button" onclick="event.preventDefault();event.stopPropagation();this.closest('details')?.removeAttribute('open');printPaymentProofFromHome(${pid},'${eh(fecha)}')">${homeActionIcon('print')}<span>Imprimir comprobante</span></button></div></details>${homeMore(primary)}</div>`;
  }
  function v4457ConsultationTurnMap'''
    _js, _count = _re.subn(_pattern, _replacement, _js, count=1, flags=_re.S)
    HOME_ACTIONS_PATCHED = bool(_count)

    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['\"]4\.4\.\d+['\"]\s*;""",
        "const VERSION='4.4.86';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['\"]4\.4\.\d+['\"]\s*;""",
        "const V='4.4.86';",
        _js,
    )

    V4486_CSS = r"""
.v4485-payment-proof{display:none!important}
.v4486-print-menu{position:relative;display:inline-block}
.v4486-print-summary{
  list-style:none;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:5px;
  border:1px solid #dbe3ed;background:#fff;color:#425774;border-radius:8px;
  padding:6px 8px;font-size:9px;font-weight:850;min-height:29px;line-height:1;user-select:none
}
.v4486-print-summary::-webkit-details-marker{display:none}
.v4486-print-summary:hover{background:#f3f7fb}
.v4486-print-menu[open]>.v4486-print-summary{background:#edf5ff;border-color:#bad0ea;color:#315f8f}
.v4486-print-pop{
  position:absolute;right:0;top:34px;z-index:80;display:grid;gap:4px;min-width:178px;
  padding:6px;border:1px solid #d7e1ec;border-radius:10px;background:#fff;
  box-shadow:0 10px 28px rgba(35,55,80,.18)
}
.v4486-print-pop button{
  width:100%;display:flex;align-items:center;gap:7px;border:0;border-radius:8px;
  background:#fff;color:#3e536f;padding:8px 9px;font-size:9px;font-weight:850;text-align:left;white-space:nowrap
}
.v4486-print-pop button:hover{background:#f1f6fb}
.v4486-print-pop button:disabled{opacity:.42;cursor:not-allowed;background:#f7f8fa}
.v4486-print-pop .v488-home-action-svg{width:13px;height:13px;flex:0 0 13px}
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.86"!important;font-size:9px!important;line-height:1!important;font-weight:850!important
}
@media(max-width:760px){.v4486-print-pop{right:auto;left:0}}
"""

    V4486_JS = r"""
;(()=>{
  if(window.__v4486SinglePrintMenu)return;
  window.__v4486SinglePrintMenu=true;
  const VERSION='4.4.86';

  document.addEventListener('click',e=>{
    document.querySelectorAll('.v4486-print-menu[open]').forEach(menu=>{
      if(!menu.contains(e.target))menu.removeAttribute('open');
    });
  },true);

  function paint(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);
    });
  }
  paint();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});
  setTimeout(paint,250);setTimeout(paint,900);
})();
"""

    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4486_CSS
    core.V460_OVERLAY_JS = _js + "\n" + V4486_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4486/health")
def v4486_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "single_print_button": True,
        "home_actions_patched": HOME_ACTIONS_PATCHED,
        "print_choices": ["receipt", "payment_proof"],
        "payment_proof_preserved": True,
        "database_changes": False,
        "neon_writes_added": False,
        "billing_changes": False,
        "receipt_layout_version": "4.4.69",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )
