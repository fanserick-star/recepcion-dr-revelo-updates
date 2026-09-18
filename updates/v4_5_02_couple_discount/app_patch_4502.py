from __future__ import annotations

# v4.5.2 — descuento de pareja en Consulta.
# - Consulta normal: $40.
# - Al activar "Descuento pareja": la consulta de ESTE paciente queda en $30.
# - Solo aplica a Consulta; procedimientos conservan su precio.
# - Guarda el valor real $30 para reportes, comprobante y factura/AZUR.
# - Registra trazabilidad en observación/auditoría sin crear columnas ni migraciones.
# - No viene activado por defecto.
# - Conserva la base estable v4.5.1 y todos los diseños térmicos aprobados.

import app_patch_4501 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.2"

_mod = previous
_seen = set()
for _ in range(110):
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
BATCH_ROUTE_REPLACED = False

CONSULT_BASE = 40.0
COUPLE_DISCOUNT = 10.0
CONSULT_COUPLE_TOTAL = 30.0

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
    raw = {
        "TRANSFERENCIA BANCARIA": "TRANSFERENCIA",
        "BANCO": "TRANSFERENCIA",
        "CASH": "EFECTIVO",
    }.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise core.HTTPException(
            400,
            "Selecciona la forma de pago: Efectivo o Transferencia bancaria.",
        )
    return raw


def _remove_api_route(path: str, method: str) -> int:
    wanted = str(method or "").upper()
    removed = 0
    kept = []
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in (getattr(route, "methods", None) or set())}
        if getattr(route, "path", None) == path and wanted in methods:
            removed += 1
            continue
        kept.append(route)
    if removed:
        app.router.routes[:] = kept
        try:
            app.openapi_schema = None
        except Exception:
            pass
    return removed


def _discount_observation(original: object) -> str:
    marker = "DESCUENTO PAREJA · BASE $40.00 · DESCUENTO $10.00 · TOTAL $30.00"
    old = " ".join(str(original or "").split())
    return f"{old} | {marker}" if old else marker


try:
    class V4502VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str
        couple_discount: bool = False

    _REMOVED_BATCH_PAYMENT_ROUTES = _remove_api_route(
        "/api/visits/batch-payment", "POST"
    )
    BATCH_ROUTE_REPLACED = _REMOVED_BATCH_PAYMENT_ROUTES > 0

    @app.post("/api/visits/batch-payment")
    def v4502_create_visit_batch_payment(
        data: V4502VisitBatchPaymentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        method = _normalize_payment_method(data.payment_method)
        sentinel = PAYMENT_SENTINELS[method]

        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        if not data.services:
            raise core.HTTPException(400, "Selecciona al menos una atención")
        if len(data.services) > 20:
            raise core.HTTPException(400, "Hay demasiadas acciones seleccionadas")

        override = (data.tipo or "").strip().upper()
        if override and override not in {"N", "S"}:
            raise core.HTTPException(400, "Estado de paciente inválido")

        prior = db.scalar(
            core.select(core.func.count(core.Visit.id)).where(
                core.Visit.patient_id == int(patient.id)
            )
        ) or 0
        historical_prior = bool(
            not prior and core.historical_summary_for_patient(patient)
        )
        first_type = override or ("S" if prior or historical_prior else "N")

        normalized = []
        seen = set()
        has_consultation = False
        for item in data.services:
            procedimiento = (item.procedimiento or "").strip().upper() or None
            key = procedimiento or "CONSULTA"
            if key in seen:
                continue
            seen.add(key)

            if procedimiento is None:
                has_consultation = True
                valor = CONSULT_COUPLE_TOTAL if bool(data.couple_discount) else CONSULT_BASE
            else:
                valor = item.valor

            if valor is None:
                raise core.HTTPException(400, f"Ingresa el valor de {key}")
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                raise core.HTTPException(400, f"El valor de {key} no es válido")
            if valor < 0:
                raise core.HTTPException(400, f"El valor de {key} no es válido")
            normalized.append((procedimiento, valor))

        if not normalized:
            raise core.HTTPException(400, "Selecciona al menos una atención")

        discount_applied = bool(data.couple_discount and has_consultation)
        offline = core.is_offline_db(db)

        existing_payment_visits = list(db.scalars(
            core.select(core.Visit)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.patient_id == int(data.patient_id),
                core.Visit.fecha == data.fecha,
                core.BillingRecord.estado != "EMITIDA",
            )
            .order_by(core.Visit.id)
        ))
        for old_visit in existing_payment_visits:
            old_visit.source_row = sentinel

        created = []
        specs = []

        for index, (procedimiento, valor) in enumerate(normalized):
            tipo = first_type if index == 0 else "S"
            visit_observation = data.observacion
            if procedimiento is None and discount_applied:
                visit_observation = _discount_observation(data.observacion)

            visit = core.Visit(
                patient_id=int(data.patient_id),
                fecha=data.fecha,
                tipo=tipo,
                procedimiento=procedimiento,
                valor=valor,
                observacion=visit_observation,
                source_row=sentinel,
            )
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedimiento, valor, visit_observation))

        db.flush()

        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado="PENDIENTE")
            db.add(billing)
            billings.append(billing)

        for visit, tipo, procedimiento, valor, visit_observation in specs:
            service_name = procedimiento or "CONSULTA"
            if offline:
                payload = {
                    "patient_id": int(data.patient_id),
                    "fecha": data.fecha.isoformat(),
                    "tipo": tipo,
                    "procedimiento": procedimiento,
                    "valor": valor,
                    "observacion": visit_observation,
                    "source_row": sentinel,
                }
                core.add_queue(
                    db,
                    "visit.create",
                    "visit",
                    payload,
                    user.username,
                    int(visit.id),
                )
                core.audit(
                    db,
                    user,
                    "crear_atencion_multiple_offline",
                    f"Atención local {visit.id}, paciente {patient.id}, {service_name}",
                )
            else:
                core.audit(
                    db,
                    user,
                    "crear_atencion_multiple",
                    f"Atención {visit.id}, paciente {patient.id}, estado {tipo}, servicio {service_name}",
                )

            if procedimiento is None and discount_applied:
                core.audit(
                    db,
                    user,
                    "aplicar_descuento_pareja",
                    (
                        f"Atención {visit.id}, paciente {patient.id}: "
                        "consulta base $40.00, descuento $10.00, total $30.00"
                    ),
                )

        core.audit(
            db,
            user,
            "registrar_forma_pago_atencion",
            f"Paciente {int(data.patient_id)}, {data.fecha}: {method}",
        )

        db.commit()

        if not offline:
            mirrored = set()
            for visit in existing_payment_visits:
                try:
                    core.mirror_visit_to_local(visit)
                    mirrored.add(int(visit.id))
                except Exception:
                    pass
            for visit, billing in zip(created, billings):
                if int(visit.id) not in mirrored:
                    try:
                        core.mirror_visit_to_local(visit)
                    except Exception:
                        pass
                try:
                    core.mirror_billing_to_local(billing)
                except Exception:
                    pass

        with core.LocalSessionLocal() as summary_db:
            billing_actions = core._billing_action_counts(summary_db)
            pending_summary_local = {
                "billing": billing_actions["total"],
                "billing_pending": billing_actions["pending"],
                "billing_approved": billing_actions["approved"],
                "agenda": int(
                    summary_db.scalar(
                        core.select(core.func.count(core.Appointment.id)).where(
                            core.Appointment.estado == "PENDIENTE"
                        )
                    )
                    or 0
                ),
            }

        return {
            "ok": True,
            "count": len(created),
            "items": [core.v_dict(v) for v in created],
            "offline": offline,
            "pending": pending_summary_local,
            "payment_method": method,
            "sri_payment_code": SRI_PAYMENT_CODES[method],
            "single_commit": True,
            "couple_discount": discount_applied,
            "consultation_base": CONSULT_BASE if has_consultation else None,
            "discount_amount": COUPLE_DISCOUNT if discount_applied else 0.0,
            "consultation_total": (
                CONSULT_COUPLE_TOTAL if discount_applied and has_consultation
                else (CONSULT_BASE if has_consultation else None)
            ),
        }

    V4502_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.2"!important;font-size:9px!important;line-height:1!important;font-weight:850!important
}
.v4502-couple-discount{
  margin:9px 0 0;padding:10px 12px;border:1px solid #d9e4ee;border-radius:11px;
  background:#fff;display:flex;align-items:center;justify-content:space-between;gap:12px;
  transition:border-color .12s ease,background .12s ease,box-shadow .12s ease
}
.v4502-couple-discount.hidden{display:none!important}
.v4502-couple-discount.active{
  border-color:#69ad84;background:#edf9f2;box-shadow:0 0 0 2px rgba(72,151,103,.08)
}
.v4502-discount-copy{display:grid;gap:2px;min-width:0}
.v4502-discount-copy b{font-size:10.5px;color:#29455f}
.v4502-discount-copy small{font-size:8.5px;color:#728597;line-height:1.25}
.v4502-couple-discount.active .v4502-discount-copy b{color:#276344}
.v4502-discount-control{display:flex;align-items:center;gap:9px;white-space:nowrap;cursor:pointer;user-select:none}
.v4502-discount-control input{width:19px!important;height:19px!important;accent-color:#438f62;cursor:pointer}
.v4502-discount-price{display:grid;text-align:right;line-height:1.05}
.v4502-discount-price del{font-size:8px;color:#8997a6}
.v4502-discount-price strong{font-size:13px;color:#286846}
.v4502-couple-discount:not(.active) .v4502-discount-price strong{color:#536b80}
.v4502-discount-badge{
  display:inline-flex;margin-top:3px;padding:2px 6px;border-radius:999px;
  background:#dff2e7;color:#286a48;font-size:7.5px;font-weight:900;justify-self:end
}
.v4502-discounted .service-price{color:#26704a!important;font-weight:950!important}
@media(max-width:650px){
  .v4502-couple-discount{align-items:flex-start;flex-direction:column}
  .v4502-discount-control{width:100%;justify-content:space-between}
}
"""

    V4502_JS = r"""
;(()=>{
  if(window.__v4502CoupleDiscount)return;
  window.__v4502CoupleDiscount=true;

  const VERSION='4.5.2';
  let coupleDiscount=false;

  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();

  function modal(){
    return document.querySelector('.attention-form-modal')
      ||[...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(
        b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion')
      )
      ||null;
  }

  function consultCard(box=modal()){
    if(!box)return null;
    return [...box.querySelectorAll('button.service-card[data-service]')].find(
      b=>norm(b.dataset.service)==='consulta'
    )||box.querySelector('.consultation-card')||null;
  }

  function consultationSelected(box=modal()){
    const card=consultCard(box);
    if(!card)return false;
    const input=card.querySelector('input[type="checkbox"],input[type="radio"]');
    return !!(
      card.classList.contains('selected')
      ||card.classList.contains('is-selected')
      ||card.getAttribute('aria-pressed')==='true'
      ||input?.checked
    );
  }

  function setCardPrice(card,discounted){
    if(!card)return;
    card.classList.toggle('v4502-discounted',!!discounted);
    const price=card.querySelector('.service-price');
    if(price)price.textContent=discounted?'$30.00':'$40.00';
  }

  function render(){
    const box=modal();
    const card=consultCard(box);
    if(!box||!card)return;

    const selected=consultationSelected(box);
    if(!selected)coupleDiscount=false;

    let panel=box.querySelector('#v4502CoupleDiscount');
    if(!panel){
      panel=document.createElement('div');
      panel.id='v4502CoupleDiscount';
      panel.className='v4502-couple-discount hidden';
      panel.innerHTML=
        '<div class="v4502-discount-copy">'
        +'<b>Descuento pareja</b>'
        +'<small>Úsalo solo para la consulta del segundo paciente de la pareja.</small>'
        +'</div>'
        +'<label class="v4502-discount-control">'
        +'<input id="v4502CoupleDiscountCheck" type="checkbox">'
        +'<span class="v4502-discount-price">'
        +'<del>$40.00</del><strong>$30.00</strong>'
        +'<span class="v4502-discount-badge">$10 menos</span>'
        +'</span></label>';
      card.insertAdjacentElement('afterend',panel);

      panel.querySelector('#v4502CoupleDiscountCheck')?.addEventListener('change',e=>{
        coupleDiscount=!!e.target.checked;
        render();
      });
    }

    panel.classList.toggle('hidden',!selected);
    panel.classList.toggle('active',selected&&coupleDiscount);
    const check=panel.querySelector('#v4502CoupleDiscountCheck');
    if(check)check.checked=!!(selected&&coupleDiscount);
    setCardPrice(card,selected&&coupleDiscount);
  }

  function delayedRender(){
    setTimeout(render,0);
    setTimeout(render,90);
    setTimeout(render,230);
    setTimeout(render,380);
  }

  const stableAttentionFor=window.attentionFor;
  if(typeof stableAttentionFor==='function'){
    window.attentionFor=async function(id,draft=null){
      coupleDiscount=!!draft?.coupleDiscount;
      const out=await stableAttentionFor.apply(this,arguments);
      delayedRender();
      return out;
    };
  }

  const stableSaveAttention=window.saveAttention;
  if(typeof stableSaveAttention==='function'){
    window.saveAttention=async function(id){
      const applyDiscount=!!(coupleDiscount&&consultationSelected());
      const stableApi=window.api||api;

      const intercept=async function(url,opt={}){
        if(String(url)==='/api/visits/batch-payment'){
          let body={};
          try{body=JSON.parse(opt?.body||'{}')}catch(_e){body={}}
          body.couple_discount=applyDiscount;
          return stableApi(url,{...opt,body:JSON.stringify(body)});
        }
        return stableApi(url,opt);
      };

      const previousApi=api;
      try{
        api=intercept;
        return await stableSaveAttention.apply(this,arguments);
      }finally{
        api=previousApi;
      }
    };
  }

  document.addEventListener('click',e=>{
    const card=e.target?.closest?.('button.service-card[data-service]');
    if(card&&norm(card.dataset.service)==='consulta'){
      setTimeout(render,20);
      setTimeout(render,220);
      setTimeout(render,380);
    }
  },true);

  document.addEventListener('change',e=>{
    if(e.target?.closest?.('.attention-form-modal')){
      setTimeout(render,20);
      setTimeout(render,220);
    }
  },true);

  document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
    el.textContent='v'+VERSION;
    el.setAttribute('data-version','v'+VERSION);
  });

  window.__v4502CoupleDiscountTest={
    render,
    selected:()=>consultationSelected(),
    enabled:()=>coupleDiscount
  };
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "")
        + "\n"
        + V4502_CSS
    )
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "")
        + "\n"
        + V4502_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4502/health")
def v4502_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "batch_route_replaced": BATCH_ROUTE_REPLACED,
        "couple_discount": True,
        "consultation_base": CONSULT_BASE,
        "discount_amount": COUPLE_DISCOUNT,
        "consultation_total": CONSULT_COUPLE_TOTAL,
        "consultation_only": True,
        "default_enabled": False,
        "audit_trace": True,
        "report_trace_via_observation": True,
        "database_schema_changes": False,
        "receipt_layout_version": "4.4.69",
        "payment_proof_layout_version": "4.4.88",
        "billing_form_layout_version": "4.4.91",
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
