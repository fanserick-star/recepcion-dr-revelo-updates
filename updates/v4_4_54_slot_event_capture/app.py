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

APP_VERSION = "4.4.54"
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
            method = _payment_from_visit(visit)
            if not method:
                raise core.HTTPException(409, "La forma de pago no está registrada. Vuelve a la atención o selecciónala en Facturación antes de emitir.")
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

  const VERSION='4.4.54';
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
    const selected=paymentMap.get(key(id.patient_id,id.fecha))||'';
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
    return !paymentMap.get(key(id.patient_id,id.fecha));
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
            "const VERSION='4.4.54';",
            1,
        )
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + PAYMENT_CSS
    core.V460_OVERLAY_JS = _overlay_base + "\n" + PAYMENT_JS


    # -----------------------------------------------------------------------
    # v4.4.43 — EMITIDAS: Hoy / Últimos 7 días + horario exacto WhatsApp
    # -----------------------------------------------------------------------
    # La automatización ya calcula `due_at`; solo convertimos ese mismo valor
    # en un texto legible. No se duplica ni se cambia la lógica de envío.
    _v4443_base_wa_timeline_defs = core._wa_timeline_defs

    def _v4443_planned_label(raw_due_at: object) -> str:
        raw = str(raw_due_at or "").strip()
        if not raw:
            return ""
        try:
            dt = core.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return ""
        dias = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
        meses = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
        hour = dt.hour % 12 or 12
        ampm = "a. m." if dt.hour < 12 else "p. m."
        return f"Se enviará: {dias[dt.weekday()]} {dt.day} {meses[dt.month - 1]} · {hour}:{dt.minute:02d} {ampm}"

    def _wa_timeline_defs_v4443(fecha, hora, created_at=None):
        items = _v4443_base_wa_timeline_defs(fecha, hora, created_at)
        for item in items:
            if not isinstance(item, dict):
                continue
            planned = _v4443_planned_label(item.get("due_at"))
            if planned:
                item["planned"] = planned
        return items

    core._wa_timeline_defs = _wa_timeline_defs_v4443

    V4443_UI_CSS = r"""
#facturacion .v4443-emitted-range{
  display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
  margin:4px 0 12px;padding:8px 10px;border:1px solid #dce6f0;border-radius:12px;background:#f8fbfe
}
#facturacion .v4443-emitted-range>span{font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:#6a8096}
#facturacion .v4443-emitted-range-buttons{display:flex;gap:5px;flex-wrap:wrap}
#facturacion .v4443-emitted-range button{min-height:31px;padding:6px 10px;border:1px solid #cfdae6;border-radius:9px;background:#fff;color:#4d657e;font-size:9px;font-weight:900;cursor:pointer}
#facturacion .v4443-emitted-range button.active{border-color:#79a7d5;background:#eaf4ff;color:#245b91;box-shadow:0 0 0 2px rgba(70,128,187,.08)}
#facturacion .v4443-emitted-empty{padding:22px 16px;border:1px dashed #cfdae6;border-radius:12px;text-align:center;color:#71849a;background:#fbfcfe;font-size:11px}
.native-appointment-detail .v459-wa-copy>small{display:block!important;margin-top:3px!important;font-size:11px!important;line-height:1.3!important;font-weight:750!important;color:#5f748b!important}
@media(max-width:720px){#facturacion .v4443-emitted-range{align-items:stretch}#facturacion .v4443-emitted-range>span{width:100%}.v4443-emitted-range-buttons{width:100%}#facturacion .v4443-emitted-range button{flex:1}}
"""

    V4443_UI_JS = r"""
;(()=>{
  if(window.__v4443DailyEmitted)return;
  window.__v4443DailyEmitted=true;
  let emittedRange='today';

  const state=()=>String(document.querySelector('#bEstado')?.value||'PENDIENTE').toUpperCase();
  const isoLocal=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const todayIso=()=>isoLocal(new Date());
  const weekStartIso=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()-6);return isoLocal(d)};
  const groups=()=>{try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}catch(_e){return []}};

  function visibleGroups(mode=emittedRange){
    const all=groups(),today=todayIso(),start=weekStartIso();
    return all.filter(g=>{
      const f=String(g?.fecha||'').slice(0,10);
      return mode==='week' ? (f>=start&&f<=today) : f===today;
    });
  }

  function ensureBar(){
    const list=document.querySelector('#billingList');
    let bar=document.getElementById('v4443EmittedRange');
    if(!list||state()!=='EMITIDA'){
      bar?.remove();
      return null;
    }
    if(!bar){
      bar=document.createElement('div');
      bar.id='v4443EmittedRange';
      bar.className='v4443-emitted-range';
      list.parentElement?.insertBefore(bar,list);
    }
    const todayCount=visibleGroups('today').length,weekCount=visibleGroups('week').length;
    bar.innerHTML=`<span>Facturas emitidas</span><div class="v4443-emitted-range-buttons"><button type="button" data-range="today" class="${emittedRange==='today'?'active':''}">Hoy · ${todayCount}</button><button type="button" data-range="week" class="${emittedRange==='week'?'active':''}">Últimos 7 días · ${weekCount}</button></div>`;
    bar.querySelectorAll('button[data-range]').forEach(btn=>btn.addEventListener('click',()=>{
      emittedRange=btn.dataset.range==='week'?'week':'today';
      renderEmittedRange();
    }));
    return bar;
  }

  function renderEmittedRange(){
    if(state()!=='EMITIDA'){ensureBar();return}
    const list=document.querySelector('#billingList');if(!list)return;
    ensureBar();
    const visible=visibleGroups();
    try{
      list.innerHTML=visible.length
        ?visible.map(g=>billingCardHtml(g)).join('')
        :`<div class="v4443-emitted-empty">${emittedRange==='week'?'No hay facturas emitidas en los últimos 7 días.':'No hay facturas emitidas hoy.'}</div>`;
    }catch(_e){}
  }

  const oldLoad=window.loadBilling;
  if(typeof oldLoad==='function'){
    window.loadBilling=async function(){
      const result=await oldLoad.apply(this,arguments);
      if(state()==='EMITIDA')renderEmittedRange();else ensureBar();
      return result;
    };
  }

  const oldSet=window.setBillingStatus;
  if(typeof oldSet==='function'){
    window.setBillingStatus=async function(next){
      if(String(next||'').toUpperCase()==='EMITIDA')emittedRange='today';
      const result=await oldSet.apply(this,arguments);
      if(state()==='EMITIDA')renderEmittedRange();else ensureBar();
      return result;
    };
  }

  window.__v4443EmittedRangeTest={visibleGroups,renderEmittedRange,setRange:v=>{emittedRange=v==='week'?'week':'today';renderEmittedRange()},getRange:()=>emittedRange};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4443_UI_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4443_UI_JS


    # -----------------------------------------------------------------------
    # v4.4.44 — guardia semanal contra citas duplicadas por paciente.
    # -----------------------------------------------------------------------
    # No cambia tablas ni reemplaza agenda_create. El endpoint nuevo hace la
    # advertencia y luego delega el guardado real en la función estable 4.4.43.
    class AgendaGuardedAppointmentIn(core.BaseModel):
        patient_id: int
        fecha: _date
        hora: str
        nota: str | None = None
        allow_same_week: bool = False

    def _v4444_phone_variants(value: object) -> list[str]:
        raw = str(value or "").strip()
        clean = core.normalize_lookup_phone(raw)
        values = {x for x in (raw, clean) if x}
        if len(clean) == 10 and clean.startswith("0"):
            values.add("593" + clean[1:])
        return sorted(values)

    def _v4444_same_week_conflict(db, patient, target_date: _date):
        monday = target_date - core.timedelta(days=target_date.weekday())
        sunday = monday + core.timedelta(days=6)
        variants = _v4444_phone_variants(getattr(patient, "celular", ""))

        identity = [core.Appointment.patient_id == int(patient.id)]
        if variants:
            identity.append(core.Patient.celular.in_(variants))

        linked = db.execute(
            core.select(core.Appointment, core.Patient)
            .join(core.Patient, core.Patient.id == core.Appointment.patient_id)
            .where(
                core.Appointment.fecha >= monday,
                core.Appointment.fecha <= sunday,
                core.Appointment.origen != core.CONFIRMAFY_ATTENDED_ORIGIN,
                ~core.func.upper(core.func.coalesce(core.Appointment.estado, "")).in_(
                    ["CANCELADA", "CANCELADO", "NO_ASISTIRA", "NO_ASISTIRÁ", "REAGENDADA"]
                ),
                core.or_(*identity),
            )
            .order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id)
            .limit(1)
        ).first()
        if linked:
            appointment, owner = linked
            return {
                "source": "appointment",
                "date": appointment.fecha.isoformat(),
                "time": appointment.hora,
                "name": owner.nombre,
            }

        if variants:
            staged = db.scalar(
                core.select(core.ConfirmafyAgendaItem)
                .where(
                    core.ConfirmafyAgendaItem.fecha >= monday,
                    core.ConfirmafyAgendaItem.fecha <= sunday,
                    core.ConfirmafyAgendaItem.celular.in_(variants),
                )
                .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)
                .limit(1)
            )
            if staged:
                return {
                    "source": "staged",
                    "date": staged.fecha.isoformat(),
                    "time": staged.hora,
                    "name": staged.nombre,
                }
        return None

    @app.get("/api/agenda/week-conflict")
    def agenda_week_conflict_v4444(
        patient_id: int,
        fecha: _date,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        patient = db.get(core.Patient, int(patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        conflict = _v4444_same_week_conflict(db, patient, fecha)
        monday = fecha - core.timedelta(days=fecha.weekday())
        return {
            "conflict": conflict,
            "week_start": monday.isoformat(),
            "week_end": (monday + core.timedelta(days=6)).isoformat(),
        }

    @app.post("/api/agenda/appointments/guarded")
    def agenda_create_guarded_v4444(
        data: AgendaGuardedAppointmentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        if not core.confirmafy_phone(patient.celular):
            raise core.HTTPException(400, "Completa el celular del paciente antes de reagendar")

        stable_data = core.AppointmentIn(
            patient_id=int(data.patient_id), fecha=data.fecha, hora=data.hora, nota=data.nota
        )
        values = core.normalize_appointment_payload(stable_data)

        # La ocupación del bloque continúa siendo un bloqueo duro y se evalúa
        # ANTES de cualquier posibilidad de saltar la advertencia semanal.
        slot_conflicts = core.appointment_conflicts(db, values["fecha"], values["hora"], 20)
        if slot_conflicts:
            raise core.HTTPException(
                409,
                core.occupied_message(values["fecha"], values["hora"], slot_conflicts),
            )

        conflict = _v4444_same_week_conflict(db, patient, values["fecha"])
        if conflict and not bool(data.allow_same_week):
            return {"created": False, "same_week_conflict": conflict}

        # Reutiliza el guardado estable. Este vuelve a comprobar el horario,
        # conserva auditoría, offline/local-first, mirrors y WhatsApp existentes.
        result = core.agenda_create(stable_data, db, user)
        return {"created": True, "appointment": result}

    V4444_WEEK_GUARD_CSS = r"""
.v4444-week-guard-backdrop{position:fixed;inset:0;z-index:100000;display:grid;place-items:center;padding:18px;background:rgba(20,34,49,.48);backdrop-filter:blur(2px)}
.v4444-week-guard-card{width:min(470px,94vw);padding:20px;border-radius:18px;background:#fff;box-shadow:0 20px 60px rgba(19,38,58,.28);border:1px solid #dbe5ef}
.v4444-week-guard-card h3{margin:0 0 7px;font-size:18px;color:#263d55}.v4444-week-guard-card p{margin:0;color:#60748a;font-size:12px;line-height:1.45}
.v4444-week-guard-existing{margin:14px 0;padding:12px;border-radius:12px;background:#fff8e9;border:1px solid #ecd9a9;display:grid;gap:3px}
.v4444-week-guard-existing span{font-size:9px;font-weight:900;letter-spacing:.07em;color:#85652c}.v4444-week-guard-existing b{font-size:13px;color:#5f4b27}.v4444-week-guard-existing small{font-size:11px;color:#75664a}
.v4444-week-guard-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}.v4444-week-guard-actions button{min-height:38px;padding:8px 13px;border-radius:10px;border:1px solid #cfdbe6;background:#fff;font-weight:850;cursor:pointer}.v4444-week-guard-actions .proceed{background:#2f6698;color:#fff;border-color:#2f6698}
@media(max-width:560px){.v4444-week-guard-actions{flex-direction:column-reverse}.v4444-week-guard-actions button{width:100%}}
"""

    V4444_WEEK_GUARD_JS = r"""
;(()=>{
  if(window.__v4444WeeklyAppointmentGuard)return;
  window.__v4444WeeklyAppointmentGuard=true;

  function weeklyGuardAsk(conflict){
    return new Promise(resolve=>{
      document.querySelector('.v4444-week-guard-backdrop')?.remove();
      const root=document.createElement('div');root.className='v4444-week-guard-backdrop';
      const d=String(conflict?.date||''),t=String(conflict?.time||''),n=String(conflict?.name||'Paciente');
      root.innerHTML=`<div class="v4444-week-guard-card" role="dialog" aria-modal="true"><h3>Este paciente ya tiene una cita esta semana</h3><p>Revisa la cita existente antes de crear otra. Si realmente necesita dos citas en la misma semana, puedes continuar manualmente.</p><div class="v4444-week-guard-existing"><span>CITA YA REGISTRADA ESA SEMANA</span><b>${esc(n)}</b><small>${fmtDate(d)} · ${fmtTime(t)}</small></div><div class="v4444-week-guard-actions"><button type="button" data-action="cancel">Cancelar</button><button type="button" class="proceed" data-action="proceed">Agendar de todas formas</button></div></div>`;
      const done=value=>{root.remove();resolve(value)};
      root.querySelector('[data-action="cancel"]')?.addEventListener('click',()=>done(false));
      root.querySelector('[data-action="proceed"]')?.addEventListener('click',()=>done(true));
      root.addEventListener('click',e=>{if(e.target===root)done(false)});
      document.body.appendChild(root);
    });
  }

  window.saveAgendaAppointment=async function(appointmentId=null){
    // Editar una cita existente conserva exactamente el flujo estable 4.4.43.
    if(appointmentId){
      try{
        const p=agendaPatientCache;if(!p)throw Error('No se encontró el paciente.');
        const fecha=$('#agendaDate')?.value,hora=$('#agendaTime')?.value,nota=($('#agendaNote')?.value||'').trim();
        if(!fecha||!hora)throw Error('Selecciona fecha y hora.');
        const body={fecha,hora,nota};
        await singleFlightMutation(`appointment:${appointmentId}:${p.id}`,async()=>{await api(`/api/agenda/appointments/${appointmentId}`,{method:'PUT',body:JSON.stringify(body)});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda()},'Guardando cita…');
      }catch(e){alert(e.message)}
      return;
    }

    try{
      const p=agendaPatientCache;if(!p)throw Error('No se encontró el paciente.');
      const fecha=$('#agendaDate')?.value,hora=$('#agendaTime')?.value,nota=($('#agendaNote')?.value||'').trim();
      if(!fecha||!hora)throw Error('Selecciona fecha y hora.');
      const key=`appointment:new:${p.id}`;
      await singleFlightMutation(key,async()=>{
        const submit=async allow=>api('/api/agenda/appointments/guarded',{method:'POST',body:JSON.stringify({patient_id:p.id,fecha,hora,nota,allow_same_week:!!allow})});
        let result=await submit(false);
        if(result?.same_week_conflict){
          const proceed=await weeklyGuardAsk(result.same_week_conflict);
          if(!proceed)return;
          result=await submit(true);
        }
        if(!result?.created)throw Error('No se pudo confirmar el guardado de la cita. No se creó ninguna cita.');
        invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda();
      },'Guardando cita…');
    }catch(e){alert(e.message)}
  };

  window.__v4444WeeklyGuardTest={weeklyGuardAsk};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4444_WEEK_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4444_WEEK_GUARD_JS


    # -----------------------------------------------------------------------
    # v4.4.45 — Agenda Cloud completa en Nueva atención + identidad segura.
    # -----------------------------------------------------------------------
    # La PC continúa siendo local-first. Únicamente al abrir /api/agenda/week,
    # y solo si no hay cambios offline pendientes, se copian a SQLite las citas
    # de esa semana que ya existen en Neon. No hay migraciones ni tablas nuevas.
    _v4445_cloud_agenda_lock = core.threading.Lock()
    _v4445_cloud_agenda_at = {}

    def _v4445_sync_cloud_agenda_for_dates(dates, min_interval: float = 5.0) -> int:
        normalized = []
        for value in dates or []:
            try:
                item_date = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
            except Exception:
                continue
            if item_date not in normalized:
                normalized.append(item_date)
        normalized.sort()
        if not normalized:
            return 0
        if not core.cloud_configured() or core.FORCE_OFFLINE or not core.CloudSessionLocal:
            return 0
        # Nunca mezclamos una descarga de nube con escrituras locales todavía
        # pendientes de subir. La cola offline conserva prioridad absoluta.
        if core.queue_count() > 0:
            return 0

        key = "|".join(x.isoformat() for x in normalized)
        now = core.time.time()
        if not _v4445_cloud_agenda_lock.acquire(blocking=False):
            return 0
        try:
            last = float(_v4445_cloud_agenda_at.get(key) or 0.0)
            if last and now - last < max(1.0, float(min_interval or 5.0)):
                return 0
            if not core.check_cloud(force=False):
                return 0

            # Leemos solamente los días visibles. Las citas vinculadas traen su
            # Patient para que la FK local exista; las citas WhatsApp/sin vincular
            # se conservan como ConfirmafyAgendaItem y NO crean fichas Patient.
            with core.CloudSessionLocal() as cdb:
                linked = list(cdb.execute(
                    core.select(core.Appointment, core.Patient)
                    .join(core.Patient, core.Patient.id == core.Appointment.patient_id)
                    .where(core.Appointment.fecha.in_(normalized))
                    .order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id)
                ).all())
                staged = list(cdb.scalars(
                    core.select(core.ConfirmafyAgendaItem)
                    .where(core.ConfirmafyAgendaItem.fecha.in_(normalized))
                    .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)
                ))

            mirrored = 0
            for appointment, patient in linked:
                # Las funciones estables hacen UPSERT local y commit. Si hubiera
                # cualquier problema aislado, ellas fallan de forma segura sin
                # tumbar la Agenda.
                core.mirror_patient_to_local(patient)
                core.mirror_appointment_to_local(appointment)
                mirrored += 1

            with core.LocalSessionLocal() as ldb:
                changed = False
                for row in staged:
                    source_hash = str(getattr(row, "source_hash", "") or "").strip()
                    if not source_hash or source_hash.startswith("mobile:whatsapp-cloud-test:"):
                        continue
                    existing = ldb.scalar(
                        core.select(core.ConfirmafyAgendaItem)
                        .where(core.ConfirmafyAgendaItem.source_hash == source_hash)
                        .limit(1)
                    )
                    values = {
                        "nombre": row.nombre,
                        "celular": row.celular,
                        "fecha": row.fecha,
                        "hora": row.hora,
                        "duracion": int(row.duracion or 20),
                        "created_at": row.created_at,
                    }
                    if existing is not None:
                        dirty = False
                        for attr, value in values.items():
                            if getattr(existing, attr, None) != value:
                                setattr(existing, attr, value)
                                dirty = True
                        if dirty:
                            changed = True
                            mirrored += 1
                        continue

                    cloud_id = int(row.id)
                    # Preservar el ID de Neon es importante porque al marcar una
                    # cita staged como atendida el POST se resuelve en la nube.
                    # Si existiera una colisión local excepcional, no pisamos nada.
                    if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:
                        continue
                    ldb.add(core.ConfirmafyAgendaItem(
                        id=cloud_id,
                        source_hash=source_hash,
                        **values,
                    ))
                    changed = True
                    mirrored += 1
                if changed:
                    ldb.commit()

            _v4445_cloud_agenda_at[key] = core.time.time()
            return mirrored
        except Exception as exc:
            # Fail-open: si Neon está lento o cae, Nueva atención sigue abriendo
            # con la copia SQLite que ya tenía la PC.
            try:
                with core._state_lock:
                    core._state["last_error"] = f"No se pudo actualizar Agenda Cloud: {core._cloud_error_hint(exc)}"[:300]
            except Exception:
                pass
            return 0
        finally:
            _v4445_cloud_agenda_lock.release()

    @app.middleware("http")
    async def v4445_cloud_agenda_catchup(request, call_next):
        if request.url.path == "/api/agenda/week":
            try:
                raw_anchor = str(request.query_params.get("anchor") or "").strip()
                anchor_date = _date.fromisoformat(raw_anchor[:10])
                monday = anchor_date - core.timedelta(days=anchor_date.weekday())
                week_dates = [monday + core.timedelta(days=i) for i in range(7)]
                # Es intencionalmente síncrono antes de dibujar: así una cita que
                # acaba de entrar por WhatsApp no aparece como hueco libre.
                _v4445_sync_cloud_agenda_for_dates(week_dates)
            except Exception:
                pass
        return await call_next(request)

    V4445_STAGED_IDENTITY_CSS = r"""
.v4445-phone-match-list{display:grid;gap:9px;margin:14px 0}
.v4445-phone-match-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border:1px solid #d7e2ec;border-radius:12px;background:#f9fbfd}
.v4445-phone-match-row>div{display:grid;gap:3px;min-width:0}.v4445-phone-match-row b{font-size:12px;color:#263f59}.v4445-phone-match-row small{font-size:10px;color:#687d92}
.v4445-phone-match-row button{flex:0 0 auto;min-height:35px;padding:7px 11px;border-radius:9px;border:1px solid #2f6698;background:#2f6698;color:#fff;font-weight:850;cursor:pointer}
.v4445-phone-note{padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d3e4f5;color:#526d88;font-size:10.5px;line-height:1.4}
@media(max-width:560px){.v4445-phone-match-row{align-items:stretch;flex-direction:column}.v4445-phone-match-row button{width:100%}}
"""

    V4445_STAGED_IDENTITY_JS = r"""
;(()=>{
  if(window.__v4445StagedIdentityFix)return;
  window.__v4445StagedIdentityFix=true;

  const stableAttend=window.attendConfirmafyStaged;
  const stableNewPatient=window.newPatientFromStaged;
  if(typeof stableAttend!=='function'||typeof stableNewPatient!=='function')return;

  function phoneKey(value){
    let d=String(value||'').replace(/\D/g,'');
    if(d.startsWith('593')&&d.length>=12)d='0'+d.slice(3);
    return d;
  }
  function phoneQueries(value){
    const local=phoneKey(value),out=[];
    if(local)out.push(local);
    if(local.length===10&&local.startsWith('0'))out.push('593'+local.slice(1));
    return [...new Set(out)];
  }
  async function exactCurrentPhoneMatches(staged){
    const wanted=phoneKey(staged?.celular);
    if(!wanted)return [];
    const batches=await Promise.all(phoneQueries(staged.celular).map(q=>
      api('/api/patients?q='+encodeURIComponent(q)+'&limit=24').catch(()=>[])
    ));
    const found=new Map();
    for(const p of batches.flat()){
      if(!p||Number(p.id||0)<=0)continue;
      if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p))continue;
      if(phoneKey(p.celular)===wanted)found.set(Number(p.id),p);
    }
    return [...found.values()];
  }
  function showPhoneMatches(itemId,fecha,staged,rows){
    const target=String(fecha||staged?.fecha||toISO(new Date())).slice(0,10);
    currentStagedResolve=staged;
    const title=rows.length===1?'Encontramos una ficha con este celular':'Encontramos fichas con este celular';
    const list=rows.map(p=>`<article class="v4445-phone-match-row"><div><b>${esc(p.nombre||'Paciente')}</b><small>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</small></div><button type="button" onclick="usePatientForStaged(${Number(itemId)},${Number(p.id)},'${target}')">Usar esta ficha</button></article>`).join('');
    openModal(`<div class="staged-attend-modal v4445-phone-match"><div class="modal-form-heading"><h2>${esc(title)}</h2><p>La cita trae un celular que ya está asociado a una ficha. Revísala antes de crear otro paciente.</p></div><div class="v4445-phone-note">Si corresponde a este paciente, usa su ficha existente y podrás completar los datos que falten dentro de la atención. No se creará un duplicado.</div><div class="v4445-phone-match-list">${list}</div><div class="actions wrap-actions"><button type="button" onclick="openSubsequentStagedSearch(${Number(itemId)},'${target}')">Buscar otra ficha</button><button type="button" onclick="v4445CreateDifferentStaged(${Number(itemId)},'${target}')">Es otra persona</button><button type="button" class="cancel-btn" onclick="closeModal()">Cancelar</button></div></div>`);
  }

  window.v4445CreateDifferentStaged=function(itemId,fecha){
    return stableNewPatient(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));
  };

  window.attendConfirmafyStaged=async function(itemId,fecha){
    try{
      const staged=await getConfirmafyStagedRow(Number(itemId));
      const rows=await exactCurrentPhoneMatches(staged);
      if(rows.length){
        showPhoneMatches(Number(itemId),fecha,staged,rows);
        return;
      }
    }catch(e){
      console.warn('v4445_staged_identity_lookup_failed',e);
    }
    return stableAttend(Number(itemId),fecha);
  };

  window.__v4445IdentityTest={phoneKey,phoneQueries};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4445_STAGED_IDENTITY_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4445_STAGED_IDENTITY_JS


    # -----------------------------------------------------------------------
    # v4.4.46 — guardia de celular también al EDITAR / COMPLETAR datos.
    # -----------------------------------------------------------------------
    # v4.4.45 ya evita crear una ficha staged si el celular de la cita pertenece
    # a un paciente existente. Esta capa cubre el hueco restante: la protección
    # visual antigua omitía checkPhone() en editMode. No hay UNIQUE ni migración;
    # solo se comprueba contra OTRAS fichas antes de guardar.
    @app.get("/api/identity/phone-owner")
    def v4446_phone_owner(
        phone: str,
        exclude_id: int = 0,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        normalized = core.normalize_lookup_phone(phone)
        if not normalized or len(normalized) < 9:
            return {"duplicate": False, "patient": None}
        variants = {normalized}
        if len(normalized) == 10 and normalized.startswith("0"):
            variants.add("593" + normalized[1:])
        rows = list(db.scalars(
            core.select(core.Patient)
            .where(core.Patient.celular.in_(sorted(variants)))
            .order_by(core.Patient.id)
        ))
        for patient in rows:
            if int(exclude_id or 0) and int(patient.id) == int(exclude_id):
                continue
            if core.normalize_lookup_phone(patient.celular) == normalized:
                return {
                    "duplicate": True,
                    "patient": {
                        "id": int(patient.id),
                        "nombre": patient.nombre,
                        "cedula": patient.cedula,
                        "celular": patient.celular,
                    },
                    "normalized": normalized,
                }
        return {"duplicate": False, "patient": None, "normalized": normalized}

    V4446_PHONE_GUARD_CSS = r"""
.v4446-phone-duplicate{margin:7px 0 0;padding:10px 11px;border-radius:10px;border:1px solid #e2b66a;background:#fff7e8;color:#6d5223;display:grid;gap:3px}
.v4446-phone-duplicate b{font-size:11px;color:#8a5910}.v4446-phone-duplicate span{font-size:10px;line-height:1.35}.v4446-phone-duplicate small{font-size:9px;color:#806b49}
.v4446-phone-duplicate button{justify-self:start;margin-top:5px;min-height:30px;padding:5px 9px;border:1px solid #c99c50;border-radius:8px;background:#fff;color:#725019;font-size:9px;font-weight:900;cursor:pointer}
"""

    V4446_PHONE_GUARD_JS = r"""
;(()=>{
  if(window.__v4446PhoneDuplicateGuard)return;
  window.__v4446PhoneDuplicateGuard=true;
  let watcherSeq=0,watcherTimer=0,stagedContext=null,lastOwner=null;

  const cleanPhone=v=>String(v||'').replace(/\D/g,'');
  async function phoneOwner(value,excludeId=0){
    const q=cleanPhone(value);if(q.length<9)return null;
    try{
      const d=await api('/api/identity/phone-owner?phone='+encodeURIComponent(q)+'&exclude_id='+Number(excludeId||0));
      return d?.duplicate&&d?.patient?d.patient:null;
    }catch(_e){return null}
  }
  function warningHost(){return $('#fCel')?.closest('.form-field')||$('#fCel')?.parentElement||null}
  function clearWarning(){document.querySelector('#v4446PhoneDuplicateWarning')?.remove();lastOwner=null}
  function renderWarning(owner,allowUse=false){
    clearWarning();if(!owner)return;
    lastOwner=owner;const host=warningHost();if(!host)return;
    const box=document.createElement('div');box.id='v4446PhoneDuplicateWarning';box.className='v4446-phone-duplicate';
    const phone=formatPhoneValue(owner.celular||'')||String(owner.celular||'');
    box.innerHTML=`<b>⚠ Este celular ya está registrado</b><span>${esc(owner.nombre||'Paciente existente')}</span><small>${esc(owner.cedula||'Sin cédula')} · ${esc(phone)}</small>${allowUse?'<button type="button" id="v4446UseExistingPhoneOwner">Usar esta ficha</button>':''}`;
    host.appendChild(box);
    if(allowUse){
      box.querySelector('#v4446UseExistingPhoneOwner')?.addEventListener('click',async()=>{
        const ctx=stagedContext,hit=lastOwner;if(!ctx||!hit)return;
        await usePatientForStaged(Number(ctx.itemId),Number(hit.id),String(ctx.fecha||toISO(new Date())).slice(0,10));
      });
    }
  }
  async function checkVisiblePhone(excludeId=0,allowUse=false){
    const input=$('#fCel');if(!input)return null;
    const seq=++watcherSeq,owner=await phoneOwner(input.value,excludeId);if(seq!==watcherSeq)return null;
    renderWarning(owner,allowUse);return owner;
  }
  function installWatcher(excludeId=0,ctx=null){
    stagedContext=ctx||null;const input=$('#fCel');if(!input)return;
    const allowUse=!!ctx?.itemId;
    const run=()=>{clearTimeout(watcherTimer);watcherTimer=setTimeout(()=>checkVisiblePhone(excludeId,allowUse),220)};
    input.addEventListener('input',run);
    input.addEventListener('blur',()=>checkVisiblePhone(excludeId,allowUse));
    // Fundamental para citas: el celular puede venir precargado y no recibir input.
    setTimeout(()=>checkVisiblePhone(excludeId,allowUse),25);
  }
  async function stopIfDuplicate(excludeId=0,allowUse=false){
    const owner=await checkVisiblePhone(excludeId,allowUse);if(!owner)return false;
    alert(`⚠ Este celular ya está registrado\n\n${owner.nombre||'Paciente existente'}\n${formatPhoneValue(owner.celular||'')||owner.celular||''}\n\nNo se guardó ningún cambio. Revisa o usa la ficha existente.`);
    return true;
  }

  // BUG reportado: Completar datos desde Nueva atención entraba en editMode y
  // el código anterior saltaba la comprobación del número. Aquí se excluye solo
  // el paciente actual, por lo que mantener su propio celular sigue permitido.
  const stableEditFromAttention=window.editPatientFromAttention;
  if(typeof stableEditFromAttention==='function')window.editPatientFromAttention=async function(id){
    const r=await stableEditFromAttention.apply(this,arguments);
    setTimeout(()=>installWatcher(Number(id||0),null),35);
    return r;
  };
  const stableSaveAndReturn=window.savePatientAndReturnToAttention;
  if(typeof stableSaveAndReturn==='function')window.savePatientAndReturnToAttention=async function(id){
    if(await stopIfDuplicate(Number(id||0),false))return;
    return stableSaveAndReturn.apply(this,arguments);
  };

  // La misma defensa se aplica al editor normal de pacientes.
  const stableEditPatient=window.editPatient;
  if(typeof stableEditPatient==='function')window.editPatient=async function(id){
    const r=await stableEditPatient.apply(this,arguments);
    setTimeout(()=>installWatcher(Number(id||0),null),35);
    return r;
  };
  const stableSavePatient=window.savePatient;
  if(typeof stableSavePatient==='function')window.savePatient=async function(id){
    if(await stopIfDuplicate(Number(id||0),false))return;
    return stableSavePatient.apply(this,arguments);
  };

  // Nuevos pacientes: el aviso visual ya existía, pero ahora el guardado queda
  // protegido de verdad para que no dependa de que recepción haya visto el texto.
  const stableNewPatient=window.newPatient;
  if(typeof stableNewPatient==='function')window.newPatient=async function(){
    const r=await stableNewPatient.apply(this,arguments);setTimeout(()=>installWatcher(0,null),35);return r;
  };
  const stableSaveNewPatient=window.saveNewPatient;
  if(typeof stableSaveNewPatient==='function')window.saveNewPatient=async function(){
    if(await stopIfDuplicate(0,false))return;
    return stableSaveNewPatient.apply(this,arguments);
  };

  // Si v4.4.45 deja crear "Es otra persona", el número staged sigue protegido.
  const stableNewFromStaged=window.newPatientFromStaged;
  if(typeof stableNewFromStaged==='function')window.newPatientFromStaged=async function(itemId,fecha){
    const r=await stableNewFromStaged.apply(this,arguments);
    setTimeout(()=>installWatcher(0,{itemId:Number(itemId),fecha:String(fecha||'').slice(0,10)}),35);return r;
  };
  const stableSaveNewFromStaged=window.saveNewPatientFromStaged;
  if(typeof stableSaveNewFromStaged==='function')window.saveNewPatientFromStaged=async function(itemId,fecha){
    stagedContext={itemId:Number(itemId),fecha:String(fecha||'').slice(0,10)};
    if(await stopIfDuplicate(0,true))return;
    return stableSaveNewFromStaged.apply(this,arguments);
  };
  // v4.4.45 había capturado la función original antes de esta capa. Redirigirla
  // garantiza que "Es otra persona" también pase por la guardia nueva.
  if(typeof window.v4445CreateDifferentStaged==='function')window.v4445CreateDifferentStaged=function(itemId,fecha){
    return window.newPatientFromStaged(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));
  };

  const stableSaveFromConfirmafy=window.saveNewPatientFromConfirmafy;
  if(typeof stableSaveFromConfirmafy==='function')window.saveNewPatientFromConfirmafy=async function(){
    if(await stopIfDuplicate(0,false))return;
    return stableSaveFromConfirmafy.apply(this,arguments);
  };

  window.__v4446PhoneGuardTest={phoneOwner,checkVisiblePhone,installWatcher};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4446_PHONE_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4446_PHONE_GUARD_JS


    # -----------------------------------------------------------------------
    # v4.4.49 — Agenda local inmediata + paciente existente + hora WA correcta.
    # -----------------------------------------------------------------------
    # 1) La v4.4.45 esperaba a Neon ANTES de responder /api/agenda/week. Eso
    #    hacía lenta la Agenda en la PC antigua. Conservamos exactamente el
    #    mismo espejo Cloud->SQLite, pero lo lanzamos en segundo plano: la UI
    #    dibuja primero la copia local y se refresca después sin bloquear.
    _v4449_cloud_sync_blocking = _v4445_sync_cloud_agenda_for_dates
    _v4449_cloud_bg_guard = core.threading.Lock()
    _v4449_cloud_bg_keys: set[str] = set()

    def _v4449_cloud_sync_background(dates, min_interval: float = 5.0) -> int:
        normalized = []
        for value in dates or []:
            try:
                d = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
            except Exception:
                continue
            if d not in normalized:
                normalized.append(d)
        if not normalized:
            return 0
        key = "|".join(sorted(d.isoformat() for d in normalized))
        with _v4449_cloud_bg_guard:
            if key in _v4449_cloud_bg_keys:
                return 0
            _v4449_cloud_bg_keys.add(key)

        def worker():
            try:
                _v4449_cloud_sync_blocking(normalized, min_interval=min_interval)
            finally:
                with _v4449_cloud_bg_guard:
                    _v4449_cloud_bg_keys.discard(key)

        core.threading.Thread(
            target=worker,
            daemon=True,
            name="rp-agenda-cloud-catchup",
        ).start()
        return 0

    # El middleware v4.4.45 resuelve este nombre global en cada petición.
    # Reasignarlo cambia la espera síncrona por un disparo no bloqueante sin
    # duplicar rutas ni tocar SQLite/Neon.
    _v4445_sync_cloud_agenda_for_dates = _v4449_cloud_sync_background

    # 2) Cita agendada debe ser inmediata. Appointment.created_at se guarda en
    #    UTC naive; usarlo como hora local hacía que Ecuador (-05:00) mostrara
    #    falsamente una hora cinco horas adelante (ej. 10:45 -> 15:45).
    #    El worker Cloud sigue siendo la autoridad de envío; aquí corregimos la
    #    línea de tiempo para que diga "Al guardar la cita" y quede esperando al
    #    worker hasta que exista un evento SENT/DELIVERED/READ.
    _v4449_timeline_defs_stable = core._wa_timeline_defs

    def _v4449_timeline_defs(fecha, hora, created_at=None):
        rows = _v4449_timeline_defs_stable(fecha, hora, created_at)
        for row in rows:
            if str(row.get("key") or "") == "cita_agendada":
                row["due_at"] = (core.datetime.now() - core.timedelta(seconds=1)).isoformat()
                row["planned"] = "Al guardar la cita"
        return rows

    core._wa_timeline_defs = _v4449_timeline_defs

    V4449_AGENDA_FLOW_JS = r"""
;(()=>{
  if(window.__v4449AgendaFlowSpeed)return;
  window.__v4449AgendaFlowSpeed=true;

  const wait=(ms,fn)=>setTimeout(()=>{try{fn()}catch(_e){}},ms);

  // Nueva atención: primera pintura 100% local. Después de que el espejo Cloud
  // tuvo tiempo de terminar, una lectura LOCAL muy barata actualiza la lista.
  const stableLoadAttentionWeek=window.loadAttentionWeek;
  if(typeof stableLoadAttentionWeek==='function'){
    let seq=0;
    window.loadAttentionWeek=async function(force=false,anchorValue=null){
      const token=++seq;
      const effective=anchorValue||(typeof attentionWeekAnchor!=='undefined'?attentionWeekAnchor:null);
      const result=await stableLoadAttentionWeek.call(this,force,effective);
      if(!force){
        [1600,4800].forEach(delay=>wait(delay,()=>{
          if(token!==seq||!document.querySelector('#attentionWeekCalendar'))return;
          try{if(typeof invalidateAttentionWeekCache==='function')invalidateAttentionWeekCache()}catch(_e){}
          Promise.resolve(stableLoadAttentionWeek.call(window,true,effective)).catch(()=>{});
        }));
      }
      return result;
    };
  }

  // Agenda principal: una sola segunda lectura local. La primera ya no espera a
  // Neon gracias al backend v4.4.49.
  const stableLoadAgenda=window.loadAgenda;
  if(typeof stableLoadAgenda==='function'){
    let agendaSeq=0;
    window.loadAgenda=async function(){
      const token=++agendaSeq,args=arguments;
      const result=await stableLoadAgenda.apply(this,args);
      wait(2600,()=>{
        if(token!==agendaSeq)return;
        const sec=document.querySelector('#agenda');
        if(sec?.classList?.contains('hidden'))return;
        Promise.resolve(stableLoadAgenda.apply(window,args)).catch(()=>{});
      });
      return result;
    };
  }

  // Las citas legacy que YA tienen patient_id no son pacientes nuevos. Solo
  // los registros realmente staged/sin ficha siguen usando el flujo WhatsApp.
  const stableAttentionWeekRow=window.attentionWeekRow;
  if(typeof stableAttentionWeekRow==='function')window.attentionWeekRow=function(row){
    if(String(row?.source_type||'')==='CONFIRMAFY_LEGACY'&&Number(row?.patient?.id||0)>0){
      return stableAttentionWeekRow.call(this,{...row,source_type:'PATIENT_APPOINTMENT'});
    }
    return stableAttentionWeekRow.apply(this,arguments);
  };
  const stableNativeAgendaRowCell=window.nativeAgendaRowCell;
  if(typeof stableNativeAgendaRowCell==='function')window.nativeAgendaRowCell=function(row,date,time){
    if(String(row?.source_type||'')==='CONFIRMAFY_LEGACY'&&Number(row?.patient?.id||0)>0){
      return stableNativeAgendaRowCell.call(this,{...row,source_type:'PATIENT_APPOINTMENT'},date,time);
    }
    return stableNativeAgendaRowCell.apply(this,arguments);
  };

  const stableAttendFromAgenda=window.attendFromAgenda;
  async function openExistingUpdateAndAttend(patientId,fecha){
    const id=Number(patientId||0),today=toISO(new Date()),target=String(fecha||today).slice(0,10);
    if(!id)return stableAttendFromAgenda?.apply(window,arguments);
    if(target!==today&&!confirm(`Esta cita corresponde al ${fmtDate(target)}. ¿Registrar la atención con esa fecha?`))return;
    try{
      const p=await api('/api/patients/'+id);
      const missing=typeof missingPatientFields==='function'?missingPatientFields(p):[];
      if(!missing.length){
        return attentionFor(id,{fecha:target});
      }
      const missingText=missing.join(', ');
      openModal(`<div class="patient-form-modal v4449-existing-attend"><div class="modal-form-heading"><h2>Actualizar datos y atender</h2><p>Esta cita ya pertenece a <b>${esc(p.nombre||'este paciente')}</b>. Actualizaremos la misma ficha; no se creará otra.</p></div><div class="v4449-existing-note">Falta completar: <b>${esc(missingText)}</b></div>${patientForm(p)}<div class="actions form-actions"><button class="cancel-btn" onclick="newAttention()">Volver</button><button class="primary" onclick="v4449SaveExistingAndAttend(${id},'${target}')">Guardar cambios y atender</button></div></div>`);
      wait(35,()=>{
        try{window.__v4446PhoneGuardTest?.installWatcher?.(id,null)}catch(_e){}
        const first=missing.includes('cédula')?$('#fCedula'):(missing.includes('celular')?$('#fCel'):(missing.includes('correo')?$('#fMail'):$('#fNombre')));
        first?.focus?.();
      });
    }catch(e){alert(e.message||e)}
  }
  if(typeof stableAttendFromAgenda==='function')window.attendFromAgenda=openExistingUpdateAndAttend;

  window.v4449SaveExistingAndAttend=async function(patientId,fecha){
    const id=Number(patientId||0),target=String(fecha||toISO(new Date())).slice(0,10);
    try{
      const guard=window.__v4446PhoneGuardTest;
      if(guard?.checkVisiblePhone){
        const owner=await guard.checkVisiblePhone(id,false);
        if(owner){
          alert(`⚠ Este celular ya pertenece a otra ficha\n\n${owner.nombre||'Paciente existente'}\n\nNo se cambió esta ficha. Revisa el paciente correcto.`);
          return;
        }
      }
      const data=getPatientForm();
      await api('/api/patients/'+id,{method:'PUT',body:JSON.stringify(data)});
      try{if(typeof invalidateAttentionWeekCache==='function')invalidateAttentionWeekCache()}catch(_e){}
      await attentionFor(id,{fecha:target});
    }catch(e){alert(e.message||e)}
  };

  // Compatibilidad con citas antiguas importadas: si conservan patient_id,
  // nunca las convertimos a staged ni mostramos "Nueva ficha".
  const stableAttendLegacy=window.attendLegacyConfirmafy;
  if(typeof stableAttendLegacy==='function')window.attendLegacyConfirmafy=async function(appointmentId,fecha){
    try{
      const row=await api(`/api/agenda/appointments/${Number(appointmentId)}`);
      const patientId=Number(row?.patient?.id||row?.appointment?.patient_id||0);
      if(patientId)return window.attendFromAgenda(patientId,String(fecha||row?.appointment?.fecha||'').slice(0,10));
    }catch(_e){}
    return stableAttendLegacy.apply(this,arguments);
  };

  window.__v4449AgendaTest={openExistingUpdateAndAttend};
})();
"""

    V4449_AGENDA_FLOW_CSS = r"""
.v4449-existing-note{margin:10px 0 14px;padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d6e6f5;color:#536d86;font-size:10px;line-height:1.4}
.v4449-existing-note b{color:#274d70}
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4449_AGENDA_FLOW_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4449_AGENDA_FLOW_CSS


    # -----------------------------------------------------------------------
    # v4.4.50 — cache de pacientes coherente + histórico staged sin duplicar.
    # -----------------------------------------------------------------------
    # El buscador habitual es SQLite local-first. Si un borrado en Neon se
    # reflejaba mal en SQLite, la función antigua tragaba la excepción y podían
    # quedar fichas fantasma. Blindamos create/update/delete del espejo local y
    # reparamos en segundo plano borrados recientes confirmados por Neon.
    _v4450_stable_mirror_patient = core.mirror_patient_to_local
    _v4450_stable_mirror_delete_patient = core.mirror_delete_patient_local

    def _v4450_mirror_patient_to_local(patient) -> bool:
        try:
            _v4450_stable_mirror_patient(patient)
        except Exception:
            pass
        try:
            with core.LocalSessionLocal() as ldb:
                lp = ldb.get(core.Patient, int(patient.id))
                values = dict(
                    cedula=patient.cedula,
                    nombre=patient.nombre,
                    fecha_nacimiento=patient.fecha_nacimiento,
                    celular=patient.celular,
                    correo=patient.correo,
                    lugar=patient.lugar,
                    notas=patient.notas,
                    created_at=patient.created_at,
                )
                if lp is None:
                    ldb.add(core.Patient(id=int(patient.id), **values))
                else:
                    for key, value in values.items():
                        setattr(lp, key, value)
                ldb.commit()
            return True
        except Exception as exc:
            try:
                with core._state_lock:
                    core._state["last_error"] = f"No se pudo reflejar paciente {getattr(patient, 'id', '?')} en SQLite: {exc}"[:300]
            except Exception:
                pass
            return False

    def _v4450_force_delete_patient_local(pid: int) -> bool:
        patient_id = int(pid)
        try:
            _v4450_stable_mirror_delete_patient(patient_id)
        except Exception:
            pass
        try:
            with core.LocalSessionLocal() as ldb:
                if ldb.get(core.Patient, patient_id) is None:
                    return True
                visit_ids = [int(x) for x in ldb.scalars(
                    core.select(core.Visit.id).where(core.Visit.patient_id == patient_id)
                )]
                if visit_ids:
                    ldb.execute(core.delete(core.BillingRecord).where(core.BillingRecord.visit_id.in_(visit_ids)))
                if hasattr(core, "BillingPreference"):
                    ldb.execute(core.delete(core.BillingPreference).where(core.BillingPreference.patient_id == patient_id))
                ldb.execute(core.delete(core.Appointment).where(core.Appointment.patient_id == patient_id))
                ldb.execute(core.delete(core.Visit).where(core.Visit.patient_id == patient_id))
                ldb.execute(core.delete(core.Patient).where(core.Patient.id == patient_id))
                ldb.commit()
            with core.LocalSessionLocal() as verify:
                return verify.get(core.Patient, patient_id) is None
        except Exception as exc:
            try:
                with core._state_lock:
                    core._state["last_error"] = f"No se pudo purgar paciente {patient_id} de SQLite: {exc}"[:300]
            except Exception:
                pass
            return False

    core.mirror_patient_to_local = _v4450_mirror_patient_to_local
    core.mirror_delete_patient_local = _v4450_force_delete_patient_local

    _v4450_reconcile_lock = core.threading.Lock()

    def _v4450_reconcile_recent_deleted_patients() -> dict:
        if not _v4450_reconcile_lock.acquire(blocking=False):
            return {"ok": True, "busy": True, "purged": 0}
        try:
            if core.queue_count() > 0:
                return {"ok": True, "skipped": "offline_queue", "purged": 0}
            if not core.cloud_configured() or not core.CloudSessionLocal or not core.check_cloud(force=False):
                return {"ok": True, "skipped": "cloud_unavailable", "purged": 0}
            ids = set()
            with core.LocalSessionLocal() as ldb:
                rows = list(ldb.scalars(
                    core.select(core.Audit)
                    .where(core.Audit.action.in_(("borrar_paciente", "borrar_paciente_importado_confirmafy")))
                    .order_by(core.Audit.id.desc())
                    .limit(180)
                ))
                for row in rows:
                    match = core.re.search(r"Paciente\s+(\d+)", str(row.detail or ""), flags=core.re.I)
                    if match:
                        ids.add(int(match.group(1)))
            if not ids:
                return {"ok": True, "purged": 0}
            with core.CloudSessionLocal() as cdb:
                alive = {int(x) for x in cdb.scalars(
                    core.select(core.Patient.id).where(core.Patient.id.in_(sorted(ids)))
                )}
            purged = 0
            for pid in sorted(ids - alive):
                purged += int(_v4450_force_delete_patient_local(pid))
            return {"ok": True, "purged": purged, "checked": len(ids)}
        except Exception as exc:
            return {"ok": False, "purged": 0, "error": str(exc)[:220]}
        finally:
            _v4450_reconcile_lock.release()

    @app.post("/api/local-cache/reconcile-patients")
    def v4450_reconcile_patients(user=core.Depends(core.current_user)):
        return _v4450_reconcile_recent_deleted_patients()

    def _v4450_repair_worker():
        try:
            core.time.sleep(1.5)
            _v4450_reconcile_recent_deleted_patients()
        except Exception:
            pass

    core.threading.Thread(target=_v4450_repair_worker, daemon=True, name="rp-patient-cache-repair").start()

    # Al activar un histórico DESDE una cita staged, el celular actual de la
    # cita es la identidad operativa más fuerte. Si ya pertenece a una ficha,
    # se reutiliza y el histórico se vincula a ella. Si no, se activa una sola
    # ficha y se le guarda ese celular para que un segundo histórico no cree
    # otro paciente con el mismo número.
    @app.post("/api/historical/{hid}/activate-for-staged/{item_id}")
    def v4450_activate_historical_for_staged(
        hid: int,
        item_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        staged = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if staged is None:
            raise core.HTTPException(404, "La cita ya no está disponible")
        staged_phone = core.normalize_lookup_phone(staged.celular)
        source_key = None
        try:
            with core.LocalSessionLocal() as ldb:
                historical = ldb.get(core.HistoricalPatient, int(hid))
                if historical is not None:
                    source_key = str(historical.source_key)
        except Exception:
            source_key = None

        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, 0, db, user)
            if owner_info.get("duplicate") and owner_info.get("patient"):
                owner_id = int(owner_info["patient"]["id"])
                owner = db.get(core.Patient, owner_id)
                if owner is not None:
                    if source_key:
                        try:
                            core._historical_link_patient(source_key, owner_id)
                        except Exception:
                            pass
                    _v4450_mirror_patient_to_local(owner)
                    out = core.p_dict(owner)
                    out.update({"created": False, "reused_by_staged_phone": True})
                    return out

        result = core.activate_historical_patient(int(hid), db, user)
        patient_id = int(result.get("id") or 0)
        patient = db.get(core.Patient, patient_id) if patient_id else None
        if patient is None:
            return result

        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, int(patient.id), db, user)
            if owner_info.get("duplicate") and owner_info.get("patient"):
                target_id = int(owner_info["patient"]["id"])
                if target_id != int(patient.id):
                    linked = core.link_duplicate_patient(int(patient.id), target_id, db, user)
                    out = dict(linked.get("patient") or {})
                    out.update({"created": False, "reused_by_staged_phone": True})
                    return out
            if core.normalize_lookup_phone(patient.celular) != staged_phone:
                patient.celular = staged_phone
                core.audit(db, user, "vincular_celular_cita_historico", f"Paciente {patient.id} · cita staged {item_id}")
                db.commit()
                _v4450_mirror_patient_to_local(patient)
        out = core.p_dict(patient)
        out.update({
            "created": bool(result.get("created")),
            "historical": result.get("historical"),
            "staged_phone_linked": bool(staged_phone),
        })
        return out

    V4450_PATIENT_CACHE_JS = r"""
;(()=>{
  if(window.__v4450PatientCacheIdentity)return;
  window.__v4450PatientCacheIdentity=true;

  const currentRows=rows=>(Array.isArray(rows)?rows:[]).filter(p=>!(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)));

  // El buscador normal muestra fichas ACTUALES. El histórico sigue disponible
  // en su filtro dedicado y en el flujo explícito de subsecuente de una cita.
  const stableRenderPatientResults=renderPatientResults;
  renderPatientResults=function(rows=[],title=''){
    const keepHistorical=String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='historical' || String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='review';
    return stableRenderPatientResults.call(this,keepHistorical?rows:currentRows(rows),title);
  };

  const stableGlobalResult=globalSearchResultHtml;
  globalSearchResultHtml=function(p){
    if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p))return '';
    return stableGlobalResult.call(this,p);
  };

  function clearPatientCaches(id=0){
    try{globalSearchCache=[]}catch(_e){}
    try{if(Number(id||0)>0)agendaPatientById.delete(Number(id));else agendaPatientById.clear()}catch(_e){}
    try{if(Number(id||0)>0&&Number(agendaPatientCache?.id||0)===Number(id))agendaPatientCache=null}catch(_e){}
  }
  window.__v4450ClearPatientCaches=clearPatientCaches;

  async function reconcileLocalPatients(){
    try{return await api('/api/local-cache/reconcile-patients',{method:'POST'})}catch(_e){return null}
  }

  // Borrar pasa por Papelera recuperable y luego limpia caches/UI. Así una ficha
  // buena no se pierde de forma irreversible por un clic de limpieza.
  deletePatient=async function(id,visitCount){
    const extra=visitCount?` También se moverán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'} a la Papelera.`:'';
    if(!confirmDeletion(`¿Mover este paciente a la Papelera?${extra}\n\nPodrás restaurarlo durante 7 días.`))return;
    try{
      await singleFlightMutation(`patient:safe-delete:${id}`,async()=>{
        const result=await api('/api/safety/patients/'+Number(id),{method:'DELETE'});
        clearPatientCaches(Number(id));
        await reconcileLocalPatients();
        closeModal();show('pacientes');
        try{await searchPatients()}catch(_e){}
        try{await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()])}catch(_e){}
        const msg=result?.trash_id?'Paciente movido a Papelera. Puedes restaurarlo desde Actividad → Papelera.':'Paciente eliminado.';
        if(typeof rpNotice==='function')rpNotice(msg);
      },'Moviendo…');
    }catch(e){alert(e.message||e)}
  };

  // Histórico elegido desde WhatsApp/staged: operación atómica en backend con
  // el celular de la cita, para que dos históricos no creen dos pacientes.
  useHistoricalForStaged=async function(itemId,hid,fecha){
    try{
      const p=await api(`/api/historical/${Number(hid)}/activate-for-staged/${Number(itemId)}`,{method:'POST'});
      clearPatientCaches(Number(p?.id||0));
      try{invalidateAttentionWeekCache()}catch(_e){}
      await usePatientForStaged(Number(itemId),Number(p.id),fecha);
    }catch(e){alert(e.message||e)}
  };

  // Después de cualquier edición desde atención, limpiar caches para que el
  // nombre recién completado aparezca inmediatamente en ambos buscadores.
  const stableSaveExistingAndAttend=window.v4449SaveExistingAndAttend;
  if(typeof stableSaveExistingAndAttend==='function')window.v4449SaveExistingAndAttend=async function(patientId,fecha){
    const out=await stableSaveExistingAndAttend.apply(this,arguments);
    clearPatientCaches(Number(patientId||0));
    return out;
  };
  const stableSavePatient=savePatient;
  savePatient=async function(id,source){
    const out=await stableSavePatient.apply(this,arguments);
    clearPatientCaches(Number(id||0));
    return out;
  };
  const stableSaveAndReturn=savePatientAndReturnToAttention;
  savePatientAndReturnToAttention=async function(id){
    const out=await stableSaveAndReturn.apply(this,arguments);
    clearPatientCaches(Number(id||0));
    return out;
  };

  // Reparación no bloqueante para instalaciones que ya traían fantasmas de
  // versiones anteriores. Luego vuelve a consultar solo si hay una búsqueda visible.
  setTimeout(async()=>{
    const r=await reconcileLocalPatients();
    if(!r?.purged)return;
    clearPatientCaches();
    try{const g=document.querySelector('#globalSearch');if(g&&String(g.value||'').trim().length>=2)globalSearchPatients(true)}catch(_e){}
    try{const p=document.querySelector('#search');if(p&&String(p.value||'').trim().length>=2)searchPatients()}catch(_e){}
  },1800);

  window.__v4450PatientTest={currentRows,reconcileLocalPatients,clearPatientCaches};
})();
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4450_PATIENT_CACHE_JS


    # -----------------------------------------------------------------------
    # v4.4.51 — forma de pago nace en Nueva atención y llega intacta a SRI.
    # -----------------------------------------------------------------------
    # La pantalla de Facturación ya tenía los botones Efectivo/Transferencia,
    # pero no existía una unión real con Nueva atención. Peor: el frontend
    # pintaba Efectivo como seleccionado aunque no hubiese valor persistido.
    # Esta capa vuelve la atención la fuente de verdad y conserva la posibilidad
    # de corregir el método después en Facturación antes de emitir.

    class V4451VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str

    def _v4451_apply_payment_to_group(db, user, patient_id: int, fecha, method: str):
        method = _normalize_payment_method(method)
        sentinel = PAYMENT_SENTINELS[method]
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.patient_id == int(patient_id),
                core.Visit.fecha == fecha,
                core.BillingRecord.estado != "EMITIDA",
            )
            .order_by(core.Visit.id)
        ).all()
        if not rows:
            raise core.HTTPException(404, "No se encontró la atención recién guardada para registrar su forma de pago.")

        visits = []
        visit_ids = set()
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)
            visit_ids.add(int(visit.id))

        offline = core.is_offline_db(db)
        if offline and visit_ids:
            # La cola offline debe transportar también la forma de pago. El
            # sincronizador v4.4.51 la aplicará al Visit creado en Neon.
            queued = list(db.scalars(
                core.select(core.OfflineQueue).where(
                    core.OfflineQueue.operation == "visit.create",
                    core.OfflineQueue.local_entity_id.in_(sorted(visit_ids)),
                )
            ))
            for item in queued:
                try:
                    payload = core.json.loads(item.payload or "{}")
                except Exception:
                    payload = {}
                payload["source_row"] = sentinel
                item.payload = core.json.dumps(payload, ensure_ascii=False)

        core.audit(
            db,
            user,
            "registrar_forma_pago_atencion",
            f"Paciente {patient_id}, {fecha}: {method}",
        )
        db.commit()

        if not offline:
            for visit in visits:
                try:
                    core.mirror_visit_to_local(visit)
                except Exception:
                    pass
        return method

    # El sincronizador estable crea primero el Visit remoto. Si la operación
    # offline contiene source_row, lo fijamos en la misma transacción antes del
    # commit que ya hace process_offline_queue.
    _v4451_stable_sync_one_operation = core.sync_one_operation

    def _v4451_sync_one_operation(q, ldb, cdb):
        result_id = _v4451_stable_sync_one_operation(q, ldb, cdb)
        if str(getattr(q, "operation", "") or "") == "visit.create" and result_id is not None:
            try:
                payload = core.json.loads(getattr(q, "payload", "") or "{}")
                source_row = int(payload.get("source_row") or 0)
            except Exception:
                source_row = 0
            if source_row in set(PAYMENT_SENTINELS.values()):
                visit = cdb.get(core.Visit, int(result_id))
                if visit is not None:
                    visit.source_row = source_row
        return result_id

    core.sync_one_operation = _v4451_sync_one_operation

    @app.post("/api/visits/batch-payment")
    def v4451_create_visit_batch_payment(
        data: V4451VisitBatchPaymentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        method = _normalize_payment_method(data.payment_method)
        stable_data = core.VisitBatchIn(
            patient_id=int(data.patient_id),
            fecha=data.fecha,
            tipo=data.tipo,
            services=data.services,
            observacion=data.observacion,
        )
        result = core.create_visit_batch(stable_data, db, user)
        _v4451_apply_payment_to_group(db, user, int(data.patient_id), data.fecha, method)
        if isinstance(result, dict):
            result = dict(result)
            result["payment_method"] = method
            result["sri_payment_code"] = SRI_PAYMENT_CODES[method]
        return result

    V4451_PAYMENT_ATTENTION_JS = r"""
;(()=>{
  if(window.__v4451PaymentSourceOfTruth)return;
  window.__v4451PaymentSourceOfTruth=true;

  let attentionPaymentMethod='';

  function paymentLabel(method){
    return method==='TRANSFERENCIA'?'Transferencia bancaria':method==='EFECTIVO'?'Efectivo':'';
  }

  function renderAttentionPayment(){
    const modal=document.querySelector('.attention-form-modal');
    if(!modal)return;
    let box=modal.querySelector('#v4451AttentionPayment');
    if(!box){
      box=document.createElement('div');
      box.id='v4451AttentionPayment';
      box.className='v4451-attention-payment';
      const obs=modal.querySelector('.attention-observation');
      if(obs)obs.insertAdjacentElement('beforebegin',box);else modal.querySelector('.actions')?.insertAdjacentElement('beforebegin',box);
    }
    const selected=String(attentionPaymentMethod||'');
    box.classList.toggle('required',!selected);
    box.innerHTML=`
      <div class="v4451-pay-head">
        <div><b>Forma de pago</b><small>Obligatorio · se usará después en la factura/SRI.</small></div>
        <span>${selected?`✓ ${paymentLabel(selected)}`:'Sin seleccionar'}</span>
      </div>
      <div class="v4451-pay-options">
        <button type="button" class="v4451-pay-option ${selected==='EFECTIVO'?'selected':''}" onclick="v4451ChooseAttentionPayment('EFECTIVO')"><span>💵</span><b>Efectivo</b><small>SRI 01</small></button>
        <button type="button" class="v4451-pay-option ${selected==='TRANSFERENCIA'?'selected':''}" onclick="v4451ChooseAttentionPayment('TRANSFERENCIA')"><span>🏦</span><b>Transferencia bancaria</b><small>SRI 20</small></button>
      </div>`;
  }

  window.v4451ChooseAttentionPayment=function(method){
    const m=String(method||'').toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(m))return;
    attentionPaymentMethod=m;
    renderAttentionPayment();
  };

  const stableAttentionFor=window.attentionFor;
  if(typeof stableAttentionFor==='function')window.attentionFor=async function(id,draft=null){
    attentionPaymentMethod=String(draft?.paymentMethod||'').toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(attentionPaymentMethod))attentionPaymentMethod='';
    const out=await stableAttentionFor.apply(this,arguments);
    renderAttentionPayment();
    return out;
  };

  const stableSaveAttention=window.saveAttention;
  if(typeof stableSaveAttention==='function')window.saveAttention=async function(id){
    const method=String(attentionPaymentMethod||'').toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(method)){
      const box=document.querySelector('#v4451AttentionPayment');
      box?.classList.add('required');
      try{box?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      alert('Selecciona la forma de pago antes de guardar la atención.');
      return;
    }

    const stableApi=window.api||api;
    const intercept=async function(url,opt={}){
      if(String(url)==='/api/visits/batch'){
        let body={};
        try{body=JSON.parse(opt?.body||'{}')}catch(_e){body={}}
        body.payment_method=method;
        return stableApi('/api/visits/batch-payment',{...opt,body:JSON.stringify(body)});
      }
      return stableApi(url,opt);
    };

    // api es una función global mutable en esta aplicación. Se intercepta solo
    // durante el guardado y únicamente cambia /api/visits/batch.
    const previousApi=api;
    try{
      api=intercept;
      return await stableSaveAttention.apply(this,arguments);
    }finally{
      api=previousApi;
    }
  };

  window.__v4451PaymentTest={renderAttentionPayment,getMethod:()=>attentionPaymentMethod};
})();
"""

    V4451_PAYMENT_ATTENTION_CSS = r"""
.v4451-attention-payment{margin:12px 0 14px;padding:12px;border:1px solid #d8e4ef;border-radius:13px;background:#f8fbfe}
.v4451-attention-payment.required{border-color:#dda944;background:#fff9ed;box-shadow:0 0 0 3px rgba(221,169,68,.10)}
.v4451-pay-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:9px}
.v4451-pay-head>div{display:flex;flex-direction:column;gap:2px}.v4451-pay-head b{font-size:10px;color:#254761}.v4451-pay-head small{font-size:8px;color:#75899b}.v4451-pay-head>span{font-size:8px;font-weight:900;color:#55728a}
.v4451-pay-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.v4451-pay-option{min-height:54px;border:1px solid #ccd9e5!important;border-radius:11px!important;background:#fff!important;color:#3e5c74!important;display:grid!important;grid-template-columns:auto 1fr auto;align-items:center;gap:7px;text-align:left!important;padding:9px 11px!important;box-shadow:none!important}.v4451-pay-option>b{font-size:9px}.v4451-pay-option>small{font-size:8px;color:#7a8c9d}.v4451-pay-option.selected{border-color:#62af84!important;background:#eaf8f0!important;color:#22613d!important;box-shadow:0 0 0 2px rgba(61,143,91,.09)!important}.v4451-pay-option.selected>small{color:#397052}
@media(max-width:720px){.v4451-pay-options{grid-template-columns:1fr}.v4451-pay-head{flex-direction:column}}
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4451_PAYMENT_ATTENTION_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4451_PAYMENT_ATTENTION_CSS


    # -----------------------------------------------------------------------
    # v4.4.52 — Nueva cita rápida SIN crear ficha de paciente.
    # -----------------------------------------------------------------------
    # La agenda no debe obligar a inventar/completar una ficha clínica para
    # reservar un horario. Si recepción solo conoce nombre + celular, guardamos
    # una cita staged (sin patient_id), igual que las citas que llegan por
    # WhatsApp. La identidad se resuelve recién al atender.

    class V4452QuickAppointmentIn(core.BaseModel):
        nombre: str
        celular: str
        fecha: _date
        hora: str
        allow_same_week: bool = False

    def _v4452_quick_source_hash(nombre: str, celular: str, fecha, hora: str) -> str:
        clean_name = core.normalize_lookup_name(nombre or "PACIENTE")
        clean_phone = core.normalize_lookup_phone(celular or "")
        seed = core.uuid.uuid4().hex
        return "pc:quick:" + core.hashlib.sha1(
            f"{clean_name}|{clean_phone}|{fecha.isoformat()}|{hora}|{seed}".encode("utf-8")
        ).hexdigest()

    @app.post("/api/agenda/unlinked/guarded")
    def v4452_create_quick_unlinked_appointment(
        data: V4452QuickAppointmentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        name = " ".join(str(data.nombre or "").split()).upper()
        phone = core.re.sub(r"\D", "", str(data.celular or ""))
        if len(name) < 3:
            raise core.HTTPException(400, "Escribe el nombre del paciente")
        if len(phone) < 8 or len(phone) > 15:
            raise core.HTTPException(400, "Escribe un celular válido")

        values = core.normalize_appointment_payload(data)
        slot_conflicts = core.appointment_conflicts(
            db, values["fecha"], values["hora"], 20
        )
        if slot_conflicts:
            raise core.HTTPException(
                409,
                core.occupied_message(values["fecha"], values["hora"], slot_conflicts),
            )

        # Reutilizamos la guardia semanal ya probada, pero la identidad aquí es
        # el celular porque todavía NO existe una ficha de paciente.
        phone_identity = type(
            "V4452PhoneIdentity", (), {"id": -4452, "celular": phone}
        )()
        conflict = _v4444_same_week_conflict(db, phone_identity, values["fecha"])
        if conflict and not bool(data.allow_same_week):
            return {"created": False, "same_week_conflict": conflict}

        source_hash = _v4452_quick_source_hash(
            name, phone, values["fecha"], values["hora"]
        )
        item = core.ConfirmafyAgendaItem(
            nombre=name,
            celular=phone,
            fecha=values["fecha"],
            hora=values["hora"],
            duracion=20,
            source_hash=source_hash,
        )
        db.add(item)
        db.flush()
        offline = core.is_offline_db(db)
        if offline:
            core.add_queue(
                db,
                "confirmafy_staged.create",
                "confirmafy_staged",
                {
                    "nombre": item.nombre,
                    "celular": item.celular,
                    "fecha": item.fecha.isoformat(),
                    "hora": item.hora,
                    "source_hash": item.source_hash,
                },
                user.username,
                item.id,
            )
        core.audit(
            db,
            user,
            "crear_cita_rapida_sin_ficha",
            f"{name} · {values['fecha']} {values['hora']}",
        )
        db.commit()

        if not offline:
            try:
                db.refresh(item)
            except Exception:
                pass
            try:
                core.mirror_confirmafy_agenda_local(item)
            except Exception:
                pass
            try:
                core.schedule_whatsapp_for_contact(
                    source_type="staged",
                    source_id=item.id,
                    name=item.nombre,
                    phone=item.celular or "",
                    fecha=item.fecha,
                    hora=item.hora,
                )
            except Exception:
                pass

        return {
            "created": True,
            "staged": core.confirmafy_agenda_dict(item),
            "offline": bool(offline),
            "unlinked": True,
        }

    V4452_QUICK_APPOINTMENT_JS = r"""
;(()=>{
  if(window.__v4452QuickUnlinkedAppointment)return;
  window.__v4452QuickUnlinkedAppointment=true;

  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  const esc2=v=>typeof esc==='function'?esc(String(v??'')):String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function newAppointmentModal(){
    return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(box=>
      [...box.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva cita')
    )||null;
  }

  function parseSlotText(text){
    const raw=String(text||'').replace(/\s+/g,' ').trim();
    const dm=/(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(raw);
    const tm=/(\d{1,2}):(\d{2})\s*(a\.?\s*m\.?|p\.?\s*m\.?|am|pm)?/i.exec(raw);
    if(!dm||!tm)return null;
    const dd=Number(dm[1]),mm=Number(dm[2]),yy=Number(dm[3]);
    let hh=Number(tm[1]),mi=Number(tm[2]);
    const ap=norm(tm[3]||'').replace(/\./g,'').replace(/\s/g,'');
    if(ap==='pm'&&hh<12)hh+=12;
    if(ap==='am'&&hh===12)hh=0;
    if(!(dd>=1&&dd<=31&&mm>=1&&mm<=12&&hh>=0&&hh<=23&&mi>=0&&mi<=59))return null;
    return {fecha:`${String(yy).padStart(4,'0')}-${String(mm).padStart(2,'0')}-${String(dd).padStart(2,'0')}`,hora:`${String(hh).padStart(2,'0')}:${String(mi).padStart(2,'0')}`};
  }

  function slotFromModal(box){
    // El flujo estable guarda usando $('#agendaDate') / $('#agendaTime') a nivel
    // documento. En algunas composiciones visuales esos inputs quedan fuera del
    // .modalbox interno aunque pertenecen a la misma ventana Nueva cita.
    const dateInput=document.querySelector('#agendaDate')||box?.querySelector('input[type="date"]');
    const timeInput=document.querySelector('#agendaTime')||box?.querySelector('input[type="time"]');
    const fecha=String(dateInput?.value||'').slice(0,10),hora=String(timeInput?.value||'').slice(0,5);
    if(/^\d{4}-\d{2}-\d{2}$/.test(fecha)&&/^\d{2}:\d{2}$/.test(hora))return {fecha,hora};
    const candidates=[...box.querySelectorAll('span,button,div')]
      .map(el=>String(el.textContent||'').trim())
      .filter(t=>t.length>5&&t.length<90&&/\d{1,2}\/\d{1,2}\/\d{4}/.test(t)&&/\d{1,2}:\d{2}/.test(t))
      .sort((a,b)=>a.length-b.length);
    for(const text of candidates){const parsed=parseSlotText(text);if(parsed)return parsed}
    return parseSlotText(box?.textContent||'');
  }

  function fmtSlot(slot){
    try{return `${typeof fmtDate==='function'?fmtDate(slot.fecha):slot.fecha} · ${typeof fmtTime==='function'?fmtTime(slot.hora):slot.hora}`}
    catch(_e){return `${slot.fecha} · ${slot.hora}`}
  }

  window.v4452OpenQuickAppointment=function(){
    const source=newAppointmentModal();
    const remembered=window.__v4454SelectedAgendaSlot;
    const slot=(remembered&&Date.now()-Number(remembered.ts||0)<300000?remembered:null)||slotFromModal(source);
    if(!slot){alert('No pude identificar la fecha y hora seleccionadas. Cierra esta ventana y vuelve a tocar el horario.');return}
    openModal(`<div class="v4452-quick-modal"><div class="modal-form-heading"><h2>Crear cita nueva</h2><p>Reserva el horario solo con nombre y celular. La ficha del paciente se completará o vinculará cuando sea atendido.</p></div><div class="v4452-slot"><span>Horario seleccionado</span><b>${esc2(fmtSlot(slot))}</b></div><div class="v4452-fields"><label>Apellidos y nombres<input id="v4452QuickName" maxlength="220" autocomplete="off" placeholder="APELLIDOS Y NOMBRES" oninput="this.value=this.value.toUpperCase()"></label><label>Celular<input id="v4452QuickPhone" inputmode="numeric" maxlength="15" autocomplete="tel" placeholder="09XXXXXXXX" oninput="this.value=this.value.replace(/[^0-9]/g,'')"></label></div><div class="v4452-note">Esta acción <b>no crea una ficha de paciente</b>. La cita quedará como “sin ficha vinculada”.</div><div class="actions form-actions"><button class="cancel-btn" onclick="closeModal()">Cancelar</button><button id="v4452QuickSave" class="primary" onclick="v4452SaveQuickAppointment('${slot.fecha}','${slot.hora}',false)">Guardar cita</button></div></div>`);
    setTimeout(()=>document.querySelector('#v4452QuickName')?.focus(),30);
  };

  window.v4452SaveQuickAppointment=async function(fecha,hora,allowSameWeek=false){
    const name=String(document.querySelector('#v4452QuickName')?.value||'').trim().replace(/\s+/g,' ').toUpperCase();
    const phone=String(document.querySelector('#v4452QuickPhone')?.value||'').replace(/[^0-9]/g,'');
    if(name.length<3){alert('Escribe el nombre del paciente.');document.querySelector('#v4452QuickName')?.focus();return}
    if(phone.length<8||phone.length>15){alert('Escribe un celular válido.');document.querySelector('#v4452QuickPhone')?.focus();return}
    const btn=document.querySelector('#v4452QuickSave');if(btn){btn.disabled=true;btn.textContent='Guardando…'}
    try{
      const result=await api('/api/agenda/unlinked/guarded',{method:'POST',body:JSON.stringify({nombre:name,celular:phone,fecha,hora,allow_same_week:!!allowSameWeek})});
      if(result?.same_week_conflict&&!allowSameWeek){
        const c=result.same_week_conflict||{};
        const when=`${typeof fmtDate==='function'?fmtDate(c.date):String(c.date||'')} · ${typeof fmtTime==='function'?fmtTime(c.time):String(c.time||'')}`;
        const proceed=confirm(`Este paciente ya tiene una cita esta semana:\n\n${String(c.name||name)}\n${when}\n\n¿Agendar de todas formas?`);
        if(proceed)return v4452SaveQuickAppointment(fecha,hora,true);
        return;
      }
      if(!result?.created)throw Error('No se pudo crear la cita.');
      try{invalidateAgendaSlotCache()}catch(_e){}
      try{invalidateAttentionWeekCache()}catch(_e){}
      closeModal();
      try{agendaNativeAnchor=fecha}catch(_e){}
      if(typeof loadAgenda==='function')await loadAgenda();
      if(typeof rpNotice==='function')rpNotice('Cita creada sin ficha de paciente.');
    }catch(e){alert(e.message||e)}
    finally{const b=document.querySelector('#v4452QuickSave');if(b){b.disabled=false;b.textContent='Guardar cita'}}
  };

  function decorate(){
    const box=newAppointmentModal();if(!box)return;
    const buttons=[...box.querySelectorAll('button')];
    const old=buttons.find(b=>norm(b.textContent).includes('nuevo paciente'));
    if(old&&!old.dataset.v4452Quick){
      old.dataset.v4452Quick='1';
      old.textContent='＋ Crear cita nueva';
      old.removeAttribute('onclick');
      old.onclick=e=>{e?.preventDefault?.();e?.stopPropagation?.();window.v4452OpenQuickAppointment()};
      old.title='Agendar solo con nombre y celular, sin crear ficha de paciente';
    }
    const heading=[...box.querySelectorAll('.modal-form-heading p,p')].find(p=>norm(p.textContent).includes('selecciona primero'));
    if(heading&&!heading.dataset.v4452Copy){heading.dataset.v4452Copy='1';heading.textContent='Selecciona un paciente existente o crea una cita nueva solo con nombre y celular.'}
  }

  const obs=new MutationObserver(()=>{setTimeout(decorate,0);setTimeout(decorate,80)});
  const start=()=>{obs.observe(document.body,{childList:true,subtree:true});decorate()};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  document.addEventListener('click',()=>setTimeout(decorate,20),true);

  window.__v4452QuickTest={parseSlotText,slotFromModal,decorate};
})();
"""

    V4452_QUICK_APPOINTMENT_CSS = r"""
.v4452-quick-modal{width:min(600px,92vw);display:grid;gap:13px}.v4452-slot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;border:1px solid #cce0d3;border-radius:12px;background:#f1faf4}.v4452-slot span{font-size:8px;font-weight:900;color:#688176;text-transform:uppercase;letter-spacing:.04em}.v4452-slot b{font-size:11px;color:#285a3c}.v4452-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v4452-fields label{display:grid;gap:5px;font-size:9px;font-weight:900;color:#455f75}.v4452-fields input{width:100%;min-height:43px;border:1px solid #cad8e5;border-radius:10px;padding:9px 11px;font-size:11px;font-weight:800;box-sizing:border-box;background:#fff;color:#233e57}.v4452-fields input:focus{outline:0;border-color:#5d91c7;box-shadow:0 0 0 3px rgba(70,126,181,.10)}.v4452-note{padding:9px 11px;border-radius:10px;background:#f7f9fb;color:#65798b;font-size:8.5px;line-height:1.35}.v4452-note b{color:#415c72}@media(max-width:650px){.v4452-fields{grid-template-columns:1fr}.v4452-slot{align-items:flex-start;flex-direction:column}}
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4452_QUICK_APPOINTMENT_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4452_QUICK_APPOINTMENT_CSS


    # -----------------------------------------------------------------------
    # v4.4.54 — capturar fecha/hora en el MISMO clic del horario libre.
    # -----------------------------------------------------------------------
    # La cuadrícula estable invoca openAgendaSlotPicker(fecha, hora). Guardamos
    # esos argumentos antes de abrir la ventana de selección, evitando depender
    # del DOM/interiores del modal para reconstruir el horario.
    V4454_SLOT_EVENT_JS = r"""
;(()=>{
  if(window.__v4454SlotEventCapture)return;
  window.__v4454SlotEventCapture=true;

  function normalizeSlot(fecha,hora){
    const f=String(fecha||'').slice(0,10),h=String(hora||'').slice(0,5);
    if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||!/^\d{2}:\d{2}$/.test(h))return null;
    return {fecha:f,hora:h,ts:Date.now()};
  }
  function remember(fecha,hora){
    const slot=normalizeSlot(fecha,hora);
    if(slot)window.__v4454SelectedAgendaSlot=slot;
    return slot;
  }
  function installWrapper(){
    const current=window.openAgendaSlotPicker;
    if(typeof current!=='function'||current.__v4454Wrapped)return;
    const wrapped=function(fecha,hora){remember(fecha,hora);return current.apply(this,arguments)};
    wrapped.__v4454Wrapped=true;
    wrapped.__v4454Original=current;
    window.openAgendaSlotPicker=wrapped;
  }

  // Captura en fase capture, antes de que ejecute el onclick inline del horario.
  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('[onclick*="openAgendaSlotPicker"]');
    if(!btn)return;
    const raw=String(btn.getAttribute('onclick')||'');
    const m=/openAgendaSlotPicker\(\s*['"](\d{4}-\d{2}-\d{2})['"]\s*,\s*['"](\d{2}:\d{2})['"]\s*\)/.exec(raw);
    if(m)remember(m[1],m[2]);
  },true);

  installWrapper();
  setTimeout(installWrapper,0);
  setTimeout(installWrapper,120);
  setTimeout(installWrapper,500);
  document.addEventListener('click',()=>setTimeout(installWrapper,0),true);

  window.__v4454SlotCaptureTest={normalizeSlot,remember,installWrapper,get:()=>window.__v4454SelectedAgendaSlot||null};
})();
"""
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4454_SLOT_EVENT_JS

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
