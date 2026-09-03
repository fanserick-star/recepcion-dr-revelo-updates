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

APP_VERSION = "4.4.49"
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

  const VERSION='4.4.49';
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
            "const VERSION='4.4.49';",
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
