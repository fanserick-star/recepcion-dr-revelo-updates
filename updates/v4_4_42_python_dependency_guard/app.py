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

APP_VERSION = "4.4.36"
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
            .where(core.BillingRecord.estado != "EMITIDA")
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
        # v4.4.36: la forma de pago se puede escoger directamente en cualquier
        # ficha POR EMITIR. No se exige el estado interno APROBADA; la única
        # restricción es no modificar una factura que ya fue EMITIDA.

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
        # Si el usuario no cambia nada, la factura sale como EFECTIVO (SRI 01).
        # Transferencia solo se guarda cuando se cambia manualmente en la ficha.
        payload = _stable_azur_payload_for_group(data, patient, rows)
        totals: dict[str, float] = {}
        for _billing, visit in rows:
            method = _payment_from_visit(visit) or "EFECTIVO"
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
/* v4.4.35 — forma de pago individual, visible antes de emitir */
.v4431-pay-wrap{
  display:flex!important;align-items:center;gap:8px;flex-wrap:wrap;
  width:100%;box-sizing:border-box;margin:8px 0 10px;padding:9px 10px;
  border:1px solid #d7e2ed;border-radius:11px;background:#f8fbfe;
}
.v4431-pay-label{
  min-width:86px;font-size:8px;font-weight:950;letter-spacing:.055em;
  color:#687d93;text-transform:uppercase;margin-right:2px
}
.v4431-pay-choice{
  min-height:32px!important;padding:5px 10px!important;border-radius:9px!important;
  border:1px solid #cfdbe7!important;background:#fff!important;color:#405b75!important;
  font-size:9px!important;font-weight:900!important;display:inline-flex!important;
  align-items:center!important;gap:6px!important;box-shadow:none!important;cursor:pointer!important
}
.v4431-pay-choice .v4431-check{
  width:16px;height:16px;border:1.5px solid #a8b7c6;border-radius:50%;
  display:inline-grid;place-items:center;font-size:10px;line-height:1;
  color:transparent;background:#fff
}
.v4431-pay-choice.selected{
  border-color:#72ba91!important;background:#eaf8f0!important;color:#24643f!important
}
.v4431-pay-choice.selected .v4431-check{
  border-color:#2f8d59;background:#2f8d59;color:#fff;font-weight:950;
  box-shadow:0 0 0 2px rgba(47,141,89,.12)
}
.v4431-pay-choice.selected span:last-child{font-weight:950}
.v4431-pay-wrap.required{
  border-color:#dfa743!important;background:#fff8e9!important;
  box-shadow:0 0 0 3px rgba(223,167,67,.12)
}
.v4431-pay-wrap.required .v4431-pay-label{color:#9b6900}
.v4431-pay-saving{opacity:.58;pointer-events:none}
.billing-card .v4435-pay-locked{
  opacity:.55!important;filter:saturate(.6);cursor:not-allowed!important
}
.v4435-batch-button{
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
  visibility:visible!important;opacity:1!important
}
.v4431-startup-toast{
  position:fixed;right:16px;bottom:16px;z-index:10060;padding:8px 11px;
  border-radius:10px;background:#1f405f;color:#fff;font-size:9px;font-weight:800;
  box-shadow:0 8px 26px rgba(18,43,66,.22)
}
@media(max-width:720px){
  .v4431-pay-wrap{width:100%;margin:7px 0 9px}
  .v4431-pay-label{width:100%;min-width:0}
  .v4431-pay-choice{flex:1;justify-content:center}
}
"""

    PAYMENT_JS = r"""
;(()=>{
  if(window.__v4435BillingPayment)return;
  window.__v4435BillingPayment=true;
  window.__v4431BillingPayment=true;

  const VERSION='4.4.36';
  let paymentMap=new Map();
  let refreshBusy=false;
  let decorateTimer=0;
  let listObserver=null;

  const key=(pid,fecha)=>`${Number(pid)}|${String(fecha||'').slice(0,10)}`;

  function cachedGroups(){
    try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}
    catch(_e){return []}
  }

  function parseIdentityFromActions(card){
    const attrs=[...card.querySelectorAll('button[onclick],a[onclick]')]
      .map(el=>String(el.getAttribute('onclick')||''));
    // La interfaz puede cambiar previewAzurInvoice por “Revisar y emitir”.
    // También sirven acciones hermanas como openBillingRecipientEditor(id, fecha).
    for(const raw of attrs){
      const m=/\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]/.exec(raw);
      if(m)return {patient_id:Number(m[1]),fecha:m[2]};
    }
    return null;
  }

  function identityFromCache(card){
    const cards=[...document.querySelectorAll('#billingList .billing-card')];
    const idx=cards.indexOf(card);
    if(idx<0)return null;
    const g=cachedGroups()[idx];
    const patientId=Number(g?.patient?.id||0);
    const fecha=String(g?.fecha||'').slice(0,10);
    return patientId&&/^\d{4}-\d{2}-\d{2}$/.test(fecha)
      ?{patient_id:patientId,fecha,group:g}:null;
  }

  function identifyCard(card){
    if(!card)return null;
    const dsPid=Number(card.dataset.patientId||0);
    const dsFecha=String(card.dataset.fecha||'').slice(0,10);
    let id=(dsPid&&/^\d{4}-\d{2}-\d{2}$/.test(dsFecha))
      ?{patient_id:dsPid,fecha:dsFecha}:parseIdentityFromActions(card);
    const cached=identityFromCache(card);
    if(!id&&cached)id=cached;
    if(!id)return null;
    if(!id.group&&cached&&Number(cached.patient_id)===Number(id.patient_id)&&cached.fecha===id.fecha)id.group=cached.group;
    card.dataset.patientId=String(id.patient_id);
    card.dataset.fecha=id.fecha;
    return id;
  }

  function findEmitButton(card){
    const buttons=[...card.querySelectorAll('button')];
    let btn=buttons.find(b=>String(b.getAttribute('onclick')||'').includes('previewAzurInvoice'));
    if(btn)return btn;
    btn=buttons.find(b=>{
      const t=String(b.textContent||'').toLowerCase();
      return (t.includes('revisar')&&t.includes('emitir'))||t.includes('emitir en azur');
    });
    return btn||null;
  }

  function groupState(id,card){
    try{
      if(id?.group&&typeof billingGroupStatus==='function')return String(billingGroupStatus(id.group)||'').toUpperCase();
    }catch(_e){}
    if(card?.classList?.contains('aprobada'))return 'APROBADA';
    return findEmitButton(card)?'APROBADA':'';
  }

  function isEmissionCard(card,id){
    if(!id)return false;
    return groupState(id,card)==='APROBADA'||!!findEmitButton(card);
  }

  function setEmitLock(card,selected){
    const emit=findEmitButton(card);if(!emit)return;
    const locked=false;
    emit.disabled=false;
    emit.classList.toggle('v4435-pay-locked',locked);
    emit.setAttribute('aria-disabled',locked?'true':'false');
    emit.title=locked?'Selecciona Efectivo o Transferencia antes de revisar y emitir':'';
  }

  function renderPicker(card){
    const id=identifyCard(card);if(!isEmissionCard(card,id))return;
    const selected=paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO';
    let wrap=card.querySelector('.v4431-pay-wrap');
    if(!wrap){
      wrap=document.createElement('div');
      wrap.className='v4431-pay-wrap';
      const foot=card.querySelector('.billing-card-foot');
      const actions=card.querySelector('.billing-actions');
      if(foot&&actions&&actions.parentElement===foot)foot.insertBefore(wrap,actions);
      else if(actions)actions.insertAdjacentElement('beforebegin',wrap);
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
    setEmitLock(card,selected);
  }

  async function saveChoice(wrap,method){
    if(!['EFECTIVO','TRANSFERENCIA'].includes(method))return;
    const patient_id=Number(wrap.dataset.patientId||0);
    const fecha=String(wrap.dataset.fecha||'');
    if(!patient_id||!fecha)return;
    wrap.classList.add('v4431-pay-saving');
    try{
      const d=await api('/api/billing/payment-method',{
        method:'POST',body:JSON.stringify({patient_id,fecha,payment_method:method})
      });
      paymentMap.set(key(patient_id,fecha),String(d.payment_method||method));
      wrap.classList.remove('required');
      const card=wrap.closest('.billing-card');
      if(card)renderPicker(card);
    }catch(e){alert(e.message||'No se pudo guardar la forma de pago.')}
    finally{wrap.classList.remove('v4431-pay-saving')}
  }

  async function refreshPaymentMap(redecorate=true){
    if(refreshBusy)return;
    refreshBusy=true;
    try{
      const d=await api('/api/billing/payment-methods');
      paymentMap=new Map((d?.items||[]).map(x=>[
        key(x.patient_id,x.fecha),String(x.payment_method||'')
      ]));
      if(redecorate)decorate();
    }catch(_e){}
    finally{refreshBusy=false}
  }

  function cardMissingPayment(card){
    const id=identifyCard(card);
    if(!isEmissionCard(card,id))return false;
    return !(paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO');
  }

  async function batchPreflight(){
    await refreshPaymentMap(false);
    const cards=[...document.querySelectorAll('#billingList .billing-card')]
      .filter(card=>isEmissionCard(card,identifyCard(card)));
    const missing=cards.filter(card=>cardMissingPayment(card));
    if(missing.length){
      missing.forEach(card=>card.querySelector('.v4431-pay-wrap')?.classList.add('required'));
      try{missing[0]?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      alert(`Antes de emitir por lotes, selecciona Efectivo o Transferencia individualmente en ${missing.length} factura${missing.length===1?'':'s'}.`);
      return;
    }
    const batchFn=(typeof window.emitAllPendingInvoices==='function')
      ?window.emitAllPendingInvoices
      :(typeof emitAllPendingInvoices==='function'?emitAllPendingInvoices:null);
    if(batchFn)return batchFn();
    alert('La emisión por lotes no está disponible en esta instalación.');
  }

  function ensureBatchButton(){
    let btn=document.getElementById('btnEmitAll')||document.getElementById('v4435EmitAll');
    if(btn&&!btn.__v4435BatchClean){
      const clean=btn.cloneNode(true);
      clean.__v4435BatchClean=true;
      btn.replaceWith(clean);
      btn=clean;
    }
    if(!btn){
      const host=document.querySelector('#facturacion .billing-title-actions')
        ||document.querySelector('#facturacion .page-title-actions')
        ||document.querySelector('#facturacion .section-title-actions');
      if(!host)return;
      btn=document.createElement('button');
      btn.id='v4435EmitAll';
      btn.className='btn small secondary';
      btn.__v4435BatchClean=true;
      host.appendChild(btn);
    }
    btn.type='button';
    btn.disabled=false;
    btn.hidden=false;
    btn.style.setProperty('display','inline-flex','important');
    btn.style.setProperty('visibility','visible','important');
    btn.style.setProperty('opacity','1','important');
    btn.classList.add('v4435-batch-button');
    btn.textContent='📦 Emitir por lotes';
    btn.removeAttribute('onclick');
    if(!btn.__v4435BatchHook){
      btn.__v4435BatchHook=true;
      btn.addEventListener('click',batchPreflight);
    }
  }

  function decorate(){
    document.querySelectorAll('#billingList .billing-card').forEach(card=>renderPicker(card));
    ensureBatchButton();
  }

  function scheduleDecorate(){
    clearTimeout(decorateTimer);
    decorateTimer=setTimeout(decorate,20);
  }

  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('button');if(!btn)return;
    const card=btn.closest('.billing-card');if(!card)return;
    const emit=findEmitButton(card);if(btn!==emit)return;
    const id=identifyCard(card);if(!id)return;
    if(!paymentMap.get(key(id.patient_id,id.fecha))){
      e.preventDefault();e.stopImmediatePropagation();
      const wrap=card.querySelector('.v4431-pay-wrap');
      wrap?.classList.add('required');
      try{wrap?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      wrap?.querySelector('.v4431-pay-choice')?.focus();
      alert('Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.');
    }
  },true);

  function hookBilling(){
    const fn=window.loadBilling;
    if(typeof fn!=='function')return false;
    if(fn.__v4435Hook)return true;
    const wrapped=async function(){
      const result=await fn.apply(this,arguments);
      await refreshPaymentMap(false);
      scheduleDecorate();
      return result;
    };
    wrapped.__v4435Hook=true;
    window.loadBilling=wrapped;
    return true;
  }

  function observeBillingList(){
    const list=document.querySelector('#billingList');
    if(!list||list.__v4435Observed)return;
    list.__v4435Observed=true;
    listObserver=new MutationObserver(mutations=>{
      if(mutations.some(m=>[...m.addedNodes].some(n=>n?.nodeType===1&&(n.matches?.('.billing-card')||n.querySelector?.('.billing-card'))))){
        refreshPaymentMap(false).finally(scheduleDecorate);
      }
    });
    listObserver.observe(list,{childList:true,subtree:false});
  }

  async function boot(){
    hookBilling();
    observeBillingList();
    ensureBatchButton();
    await refreshPaymentMap(false);
    decorate();
  }

  window.__v4435BillingPaymentTest={decorate,identifyCard,ensureBatchButton,batchPreflight};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
"""

    _v459_base = core.V459_SETTINGS_JS or ""
    _v459_bad_root = "const sub=q('.config-title-row .muted','#config');"
    _v459_good_root = "const sub=q('.config-title-row .muted',q('#config')||document);"
    if _v459_bad_root in _v459_base:
        _v459_base = _v459_base.replace(_v459_bad_root, _v459_good_root, 1)
    core.V459_SETTINGS_JS = _v459_base

    _overlay_base = core.V460_OVERLAY_JS or ""
    _overlay_version_marker = "const VERSION='4.4.28';"
    if _overlay_version_marker in _overlay_base:
        _overlay_base = _overlay_base.replace(
            _overlay_version_marker,
            "const VERSION='4.4.36';",
            1,
        )
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + PAYMENT_CSS
    core.V460_OVERLAY_JS = _overlay_base + "\n" + PAYMENT_JS

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
