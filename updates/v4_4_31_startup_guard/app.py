from __future__ import annotations

# v4.4.31 — ARRANQUE BLINDADO + forma de pago en Facturación.
#
# Arquitectura de seguridad:
# - app.py YA NO encadena versiones (4.4.29 -> 4.4.30 -> ...).
# - Siempre arranca sobre una copia estable y verificada de v4.4.28 que el
#   launcher instala junto con este archivo como app_base_4428.py.
# - Las mejoras se montan encima en un bloque protegido. Si una mejora falla,
#   el backend estable sigue arrancando en lugar de dejar una ventana blanca.
# - No hay descarga de código durante el import ni migraciones de base de datos.

import traceback
from datetime import date as _date

import app_base_4428 as core

APP_VERSION = "4.4.31"
core.APP_VERSION = APP_VERSION
app = core.app

FEATURE_BOOT_OK = False
FEATURE_BOOT_ERROR = ""

PAYMENT_SENTINELS = {
    "EFECTIVO": -442901,
    "TRANSFERENCIA": -442920,
}
SRI_PAYMENT_CODES = {
    "EFECTIVO": "01",
    "TRANSFERENCIA": "20",
}


def _normalize_payment_method(value: object) -> str:
    raw = " ".join(str(value or "").strip().upper().split())
    aliases = {
        "TRANSFERENCIA BANCARIA": "TRANSFERENCIA",
        "BANCO": "TRANSFERENCIA",
        "CASH": "EFECTIVO",
    }
    raw = aliases.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise core.HTTPException(
            400,
            "Selecciona la forma de pago: Efectivo o Transferencia bancaria.",
        )
    return raw


def _payment_from_visit(visit) -> str | None:
    try:
        value = int(getattr(visit, "source_row", 0) or 0)
    except Exception:
        return None
    for method, sentinel in PAYMENT_SENTINELS.items():
        if value == sentinel:
            return method
    return None


class BillingPaymentMethodIn(core.BaseModel):
    patient_id: int
    fecha: _date
    payment_method: str


try:
    @app.get("/api/startup-guard")
    def startup_guard_status():
        return {
            "ok": True,
            "version": APP_VERSION,
            "base": "4.4.28-lkg",
            "feature_boot_ok": FEATURE_BOOT_OK,
            "feature_boot_error": FEATURE_BOOT_ERROR,
            "architecture": "stable-base + fail-open-features",
        }


    @app.get("/api/billing/payment-methods")
    def billing_payment_methods(
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(core.BillingRecord.estado == "APROBADA")
            .order_by(core.Visit.fecha.desc(), core.Visit.patient_id, core.Visit.id)
        ).all()

        grouped: dict[tuple[int, str], list] = {}
        for visit, billing in rows:
            key = (int(visit.patient_id), visit.fecha.isoformat())
            grouped.setdefault(key, []).append(visit)

        items = []
        for (patient_id, fecha), visits in grouped.items():
            methods = {_payment_from_visit(v) for v in visits}
            methods.discard(None)
            method = next(iter(methods)) if len(methods) == 1 else None
            mixed = len(methods) > 1
            items.append({
                "patient_id": patient_id,
                "fecha": fecha,
                "payment_method": method,
                "mixed": mixed,
            })
        return {"items": items}


    @app.post("/api/billing/payment-method")
    def set_billing_payment_method(
        data: BillingPaymentMethodIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        if core.is_offline_db(db):
            raise core.HTTPException(
                503,
                "Conéctate a Internet para registrar la forma de pago antes de facturar.",
            )

        method = _normalize_payment_method(data.payment_method)
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.patient_id == int(data.patient_id),
                core.Visit.fecha == data.fecha,
            )
            .order_by(core.Visit.id)
        ).all()

        if not rows:
            raise core.HTTPException(404, "No se encontró esa ficha de facturación.")

        states = {str(b.estado or "").upper() for _, b in rows}
        if "EMITIDA" in states:
            raise core.HTTPException(
                409,
                "La factura ya fue emitida. Su forma de pago no se modifica.",
            )
        if states != {"APROBADA"}:
            raise core.HTTPException(
                409,
                "Primero aprueba la ficha y luego selecciona la forma de pago.",
            )

        sentinel = PAYMENT_SENTINELS[method]
        visits = []
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)

        core.audit(
            db,
            user,
            "registrar_forma_pago_facturacion",
            f"Paciente {data.patient_id}, {data.fecha}: {method}",
        )
        db.commit()

        # Facturación es local-first. Reflejar el valor inmediatamente evita que
        # la PC vieja muestre un visto atrasado después del guardado en Neon.
        for visit in visits:
            try:
                core.mirror_visit_to_local(visit)
            except Exception:
                pass

        return {
            "ok": True,
            "patient_id": int(data.patient_id),
            "fecha": data.fecha.isoformat(),
            "payment_method": method,
            "sri_payment_code": SRI_PAYMENT_CODES[method],
        }


    # Defensa final del lado servidor: aunque el navegador tuviera caché vieja
    # o alguien intentara emitir sin usar los botones, AZUR no recibe nada hasta
    # que TODAS las líneas de la ficha tengan forma de pago.
    _stable_azur_payload_for_group = core._azur_payload_for_group

    def _azur_payload_for_group_v4431(data, patient, rows):
        methods = []
        missing = False
        for _billing, visit in rows:
            method = _payment_from_visit(visit)
            if method is None:
                missing = True
            else:
                methods.append(method)

        if missing:
            raise core.HTTPException(
                400,
                "Antes de emitir, marca Efectivo o Transferencia en la ficha.",
            )

        payload = _stable_azur_payload_for_group(data, patient, rows)
        totals: dict[str, float] = {}
        for _billing, visit in rows:
            method = _payment_from_visit(visit)
            code = SRI_PAYMENT_CODES[method]
            amount = round(float(getattr(visit, "valor", 0) or 0), 2)
            totals[code] = round(totals.get(code, 0.0) + amount, 2)

        payload["pagos"] = [
            {"tipo": code, "total": amount, "tiempo": "dias", "plazo": 0}
            for code, amount in sorted(totals.items())
        ]
        return payload

    core._azur_payload_for_group = _azur_payload_for_group_v4431


    PAYMENT_CSS = r"""
/* v4.4.31 — forma de pago en Facturación */
.v4431-pay-wrap{
  display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  margin-right:auto;padding:5px 7px;border:1px solid #dce6ef;
  border-radius:11px;background:#f8fbfe;
}
.v4431-pay-label{
  font-size:8px;font-weight:950;letter-spacing:.055em;color:#71849a;
  text-transform:uppercase;margin-right:2px
}
.v4431-pay-choice{
  min-height:31px!important;padding:5px 9px!important;border-radius:9px!important;
  border:1px solid #d3deea!important;background:#fff!important;color:#48617b!important;
  font-size:9px!important;font-weight:900!important;display:inline-flex!important;
  align-items:center!important;gap:5px!important;box-shadow:none!important
}
.v4431-pay-choice .v4431-check{
  width:15px;height:15px;border:1.5px solid #aab9c8;border-radius:50%;
  display:inline-grid;place-items:center;font-size:10px;line-height:1;color:transparent;background:#fff
}
.v4431-pay-choice.selected{
  border-color:#8bc7a2!important;background:#edf9f2!important;color:#276b43!important
}
.v4431-pay-choice.selected .v4431-check{
  border-color:#3d9b67;background:#3d9b67;color:#fff
}
.v4431-pay-wrap.required{
  border-color:#dfa743!important;background:#fff8e9!important;
  box-shadow:0 0 0 3px rgba(223,167,67,.12)
}
.v4431-pay-saving{opacity:.58;pointer-events:none}
.v4431-startup-toast{
  position:fixed;right:16px;bottom:16px;z-index:10060;padding:8px 11px;
  border-radius:10px;background:#1f405f;color:#fff;font-size:9px;font-weight:800;
  box-shadow:0 8px 26px rgba(18,43,66,.22)
}
@media(max-width:720px){
  .v4431-pay-wrap{width:100%;margin:4px 0}
  .v4431-pay-choice{flex:1;justify-content:center}
}
"""

    PAYMENT_JS = r"""
;(()=>{
  if(window.__v4431BillingPayment)return;
  window.__v4431BillingPayment=true;

  const VERSION='4.4.31';
  let paymentMap=new Map();
  let refreshBusy=false;

  const key=(pid,fecha)=>`${Number(pid)}|${String(fecha||'').slice(0,10)}`;

  function identifyCard(card){
    const btn=[...card.querySelectorAll('button')].find(
      b=>String(b.getAttribute('onclick')||'').includes('previewAzurInvoice')
    );
    if(!btn)return null;
    const raw=String(btn.getAttribute('onclick')||'');
    const m=/previewAzurInvoice\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]\s*\)/.exec(raw);
    return m?{patient_id:Number(m[1]),fecha:m[2],emit:btn}:null;
  }

  function renderPicker(card){
    const id=identifyCard(card);if(!id)return;
    const k=key(id.patient_id,id.fecha);
    const selected=paymentMap.get(k)||'';
    let wrap=card.querySelector('.v4431-pay-wrap');
    if(!wrap){
      wrap=document.createElement('div');
      wrap.className='v4431-pay-wrap';
      const actions=card.querySelector('.billing-actions');
      const foot=card.querySelector('.billing-card-foot');
      if(actions)actions.insertAdjacentElement('beforebegin',wrap);
      else if(foot)foot.appendChild(wrap);
      else card.appendChild(wrap);
    }
    wrap.dataset.patientId=String(id.patient_id);
    wrap.dataset.fecha=id.fecha;
    wrap.innerHTML=`
      <span class="v4431-pay-label">Forma de pago</span>
      <button type="button" class="v4431-pay-choice ${selected==='EFECTIVO'?'selected':''}" data-pay="EFECTIVO">
        <span class="v4431-check">✓</span><span>💵 Efectivo</span>
      </button>
      <button type="button" class="v4431-pay-choice ${selected==='TRANSFERENCIA'?'selected':''}" data-pay="TRANSFERENCIA">
        <span class="v4431-check">✓</span><span>🏦 Transferencia</span>
      </button>`;
    wrap.querySelectorAll('.v4431-pay-choice').forEach(btn=>{
      btn.addEventListener('click',()=>saveChoice(wrap,String(btn.dataset.pay||'')));
    });
  }

  async function saveChoice(wrap,method){
    if(!['EFECTIVO','TRANSFERENCIA'].includes(method))return;
    const patient_id=Number(wrap.dataset.patientId||0);
    const fecha=String(wrap.dataset.fecha||'');
    if(!patient_id||!fecha)return;
    wrap.classList.add('v4431-pay-saving');
    try{
      const d=await api('/api/billing/payment-method',{
        method:'POST',
        body:JSON.stringify({patient_id,fecha,payment_method:method})
      });
      paymentMap.set(key(patient_id,fecha),String(d.payment_method||method));
      wrap.classList.remove('required');
      const card=wrap.closest('.billing-card');
      if(card)renderPicker(card);
    }catch(e){
      alert(e.message||'No se pudo guardar la forma de pago.');
    }finally{
      wrap.classList.remove('v4431-pay-saving');
    }
  }

  async function refreshPaymentMap(){
    if(refreshBusy)return;
    refreshBusy=true;
    try{
      const d=await api('/api/billing/payment-methods');
      paymentMap=new Map((d?.items||[]).map(x=>[
        key(x.patient_id,x.fecha),
        String(x.payment_method||'')
      ]));
      decorate();
    }catch(_e){}
    finally{refreshBusy=false}
  }

  function decorate(){
    document.querySelectorAll('.billing-card.aprobada').forEach(card=>renderPicker(card));
  }

  // Defensa visual: el backend también bloquea, pero aquí avisamos antes de que
  // aparezca la ventana de previsualización.
  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('button');
    if(!btn)return;
    const onclick=String(btn.getAttribute('onclick')||'');
    if(!onclick.includes('previewAzurInvoice'))return;
    const card=btn.closest('.billing-card.aprobada');
    const id=card?identifyCard(card):null;
    if(!card||!id)return;
    if(!paymentMap.get(key(id.patient_id,id.fecha))){
      e.preventDefault();
      e.stopImmediatePropagation();
      const wrap=card.querySelector('.v4431-pay-wrap');
      wrap?.classList.add('required');
      try{wrap?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      const first=wrap?.querySelector('.v4431-pay-choice');
      first?.focus();
      alert('Antes de emitir, marca Efectivo o Transferencia en esta ficha.');
    }
  },true);

  // loadBilling reemplaza el HTML de las fichas. Lo envolvemos sin modificar el
  // archivo estático estable.
  function hookBilling(){
    const fn=window.loadBilling;
    if(typeof fn!=='function')return false;
    if(fn.__v4431Hook)return true;
    const wrapped=async function(){
      const result=await fn.apply(this,arguments);
      setTimeout(refreshPaymentMap,0);
      return result;
    };
    wrapped.__v4431Hook=true;
    window.loadBilling=wrapped;
    return true;
  }

  // Corrige cualquier distintivo heredado de una versión estática anterior.
  function fixVersionLabels(){
    const direct=document.querySelector('#currentVersionBadge');
    if(direct)direct.textContent='v'+VERSION;
    document.querySelectorAll('span,small,div').forEach(el=>{
      if(el.children.length)return;
      const t=String(el.textContent||'').trim();
      if(/^v4\.4\.(?:28|29|30)$/.test(t))el.textContent='v'+VERSION;
    });
  }

  const observer=new MutationObserver(()=>{
    hookBilling();decorate();fixVersionLabels();
  });
  observer.observe(document.documentElement,{childList:true,subtree:true});

  async function boot(){
    hookBilling();fixVersionLabels();
    setTimeout(refreshPaymentMap,200);
    setTimeout(fixVersionLabels,500);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + PAYMENT_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + PAYMENT_JS

    FEATURE_BOOT_OK = True

except Exception as exc:
    # PRINCIPIO FAIL-OPEN:
    # una mejora jamás debe impedir que la recepción estable abra.
    FEATURE_BOOT_ERROR = f"{type(exc).__name__}: {exc}"[:500]
    try:
        error_path = core.Path(core.DATA_DIR) / "startup_feature_error_v4431.log"
        error_path.write_text(
            FEATURE_BOOT_ERROR + "\n\n" + traceback.format_exc(),
            encoding="utf-8",
        )
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )
