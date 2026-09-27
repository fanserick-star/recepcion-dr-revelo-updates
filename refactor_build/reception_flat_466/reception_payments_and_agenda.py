from __future__ import annotations
import core_runtime as core
import traceback
import re as _re
from datetime import date as _date
APP_VERSION = '4.4.58'
core.APP_VERSION = APP_VERSION
app = core.app
FEATURE_BOOT_OK = False
FEATURE_BOOT_ERROR = ''
PAYMENT_SENTINELS = {'EFECTIVO': -442901, 'TRANSFERENCIA': -442920}
SRI_PAYMENT_CODES = {'EFECTIVO': '01', 'TRANSFERENCIA': '20'}

def _normalize_payment_method(value: object) -> str:
    raw = ' '.join(str(value or '').strip().upper().split())
    aliases = {'TRANSFERENCIA BANCARIA': 'TRANSFERENCIA', 'BANCO': 'TRANSFERENCIA', 'CASH': 'EFECTIVO'}
    raw = aliases.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise core.HTTPException(400, 'Selecciona la forma de pago: Efectivo o Transferencia bancaria.')
    return raw

def _payment_from_visit(visit) -> str | None:
    try:
        value = int(getattr(visit, 'source_row', 0) or 0)
    except Exception:
        return None
    for method, sentinel in PAYMENT_SENTINELS.items():
        if value == sentinel:
            return method
    return None

def _v4455_normalize_birth_date_text(value: object) -> str | None:
    """Acepta fecha ISO o la forma visual ecuatoriana dd/mm/aaaa sin invertir día/mes."""
    text = str(value or '').strip()
    if not text:
        return None
    if _re.fullmatch('\\d{4}-\\d{2}-\\d{2}', text):
        try:
            return _date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ValueError('Fecha de nacimiento inválida. Revisa día, mes y año.') from exc
    m = _re.fullmatch('(\\d{1,2})[./-](\\d{1,2})[./-](\\d{4})', text)
    if not m:
        raise ValueError('Fecha de nacimiento inválida. Usa dd/mm/aaaa.')
    dd, mm, yyyy = (int(x) for x in m.groups())
    try:
        return _date(yyyy, mm, dd).isoformat()
    except ValueError as exc:
        raise ValueError('Fecha de nacimiento inválida. Revisa día, mes y año.') from exc

class BillingPaymentMethodIn(core.BaseModel):
    patient_id: int
    fecha: _date
    payment_method: str
try:

    @app.get('/api/startup-guard')
    def startup_guard_status():
        return {'ok': True, 'version': APP_VERSION, 'base': '4.4.28-lkg', 'feature_boot_ok': FEATURE_BOOT_OK, 'feature_boot_error': FEATURE_BOOT_ERROR, 'architecture': 'stable-base + fail-open-features'}

    @app.get('/api/billing/payment-methods')
    def billing_payment_methods(db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        rows = db.execute(core.select(core.Visit, core.BillingRecord).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.BillingRecord.estado != 'EMITIDA').order_by(core.Visit.fecha.desc(), core.Visit.patient_id, core.Visit.id)).all()
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
            items.append({'patient_id': patient_id, 'fecha': fecha, 'payment_method': method, 'mixed': mixed})
        return {'items': items}

    @app.post('/api/billing/payment-method')
    def set_billing_payment_method(data: BillingPaymentMethodIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        if core.is_offline_db(db):
            raise core.HTTPException(503, 'Conéctate a Internet para registrar la forma de pago antes de facturar.')
        method = _normalize_payment_method(data.payment_method)
        rows = db.execute(core.select(core.Visit, core.BillingRecord).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == int(data.patient_id), core.Visit.fecha == data.fecha).order_by(core.Visit.id)).all()
        if not rows:
            raise core.HTTPException(404, 'No se encontró esa ficha de facturación.')
        states = {str(b.estado or '').upper() for _, b in rows}
        if 'EMITIDA' in states:
            raise core.HTTPException(409, 'La factura ya fue emitida. Su forma de pago no se modifica.')
        sentinel = PAYMENT_SENTINELS[method]
        visits = []
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)
        core.audit(db, user, 'registrar_forma_pago_facturacion', f'Paciente {data.patient_id}, {data.fecha}: {method}')
        db.commit()
        for visit in visits:
            try:
                core.mirror_visit_to_local(visit)
            except Exception:
                pass
        return {'ok': True, 'patient_id': int(data.patient_id), 'fecha': data.fecha.isoformat(), 'payment_method': method, 'sri_payment_code': SRI_PAYMENT_CODES[method]}
    _stable_azur_payload_for_group = core._azur_payload_for_group

    def _azur_payload_for_group_v4431(data, patient, rows):
        payload = _stable_azur_payload_for_group(data, patient, rows)
        totals: dict[str, float] = {}
        for _billing, visit in rows:
            method = _payment_from_visit(visit)
            if not method:
                raise core.HTTPException(409, 'La forma de pago no está registrada. Vuelve a la atención o selecciónala en Facturación antes de emitir.')
            code = SRI_PAYMENT_CODES[method]
            amount = round(float(getattr(visit, 'valor', 0) or 0), 2)
            totals[code] = round(totals.get(code, 0.0) + amount, 2)
        payload['pagos'] = [{'tipo': code, 'total': amount, 'tiempo': 'dias', 'plazo': 0} for code, amount in sorted(totals.items())]
        return payload
    core._azur_payload_for_group = _azur_payload_for_group_v4431
    PAYMENT_CSS = '\n/* v4.4.35 — forma de pago individual, visible antes de emitir */\n.v4431-pay-wrap{\n  display:flex!important;align-items:center;gap:8px;flex-wrap:wrap;\n  width:100%;box-sizing:border-box;margin:8px 0 10px;padding:9px 10px;\n  border:1px solid #d7e2ed;border-radius:11px;background:#f8fbfe;\n}\n.v4431-pay-label{\n  min-width:86px;font-size:8px;font-weight:950;letter-spacing:.055em;\n  color:#687d93;text-transform:uppercase;margin-right:2px\n}\n.v4431-pay-choice{\n  min-height:32px!important;padding:5px 10px!important;border-radius:9px!important;\n  border:1px solid #cfdbe7!important;background:#fff!important;color:#405b75!important;\n  font-size:9px!important;font-weight:900!important;display:inline-flex!important;\n  align-items:center!important;gap:6px!important;box-shadow:none!important;cursor:pointer!important\n}\n.v4431-pay-choice .v4431-check{\n  width:16px;height:16px;border:1.5px solid #a8b7c6;border-radius:50%;\n  display:inline-grid;place-items:center;font-size:10px;line-height:1;\n  color:transparent;background:#fff\n}\n.v4431-pay-choice.selected{\n  border-color:#72ba91!important;background:#eaf8f0!important;color:#24643f!important\n}\n.v4431-pay-choice.selected .v4431-check{\n  border-color:#2f8d59;background:#2f8d59;color:#fff;font-weight:950;\n  box-shadow:0 0 0 2px rgba(47,141,89,.12)\n}\n.v4431-pay-choice.selected span:last-child{font-weight:950}\n.v4431-pay-wrap.required{\n  border-color:#dfa743!important;background:#fff8e9!important;\n  box-shadow:0 0 0 3px rgba(223,167,67,.12)\n}\n.v4431-pay-wrap.required .v4431-pay-label{color:#9b6900}\n.v4431-pay-saving{opacity:.58;pointer-events:none}\n.billing-card .v4435-pay-locked{\n  opacity:.55!important;filter:saturate(.6);cursor:not-allowed!important\n}\n.v4435-batch-button{\n  display:inline-flex!important;align-items:center!important;justify-content:center!important;\n  visibility:visible!important;opacity:1!important\n}\n.v4431-startup-toast{\n  position:fixed;right:16px;bottom:16px;z-index:10060;padding:8px 11px;\n  border-radius:10px;background:#1f405f;color:#fff;font-size:9px;font-weight:800;\n  box-shadow:0 8px 26px rgba(18,43,66,.22)\n}\n@media(max-width:720px){\n  .v4431-pay-wrap{width:100%;margin:7px 0 9px}\n  .v4431-pay-label{width:100%;min-width:0}\n  .v4431-pay-choice{flex:1;justify-content:center}\n}\n'
    PAYMENT_JS = '\n;(()=>{\n  if(window.__v4435BillingPayment)return;\n  window.__v4435BillingPayment=true;\n  window.__v4431BillingPayment=true;\n\n  const VERSION=\'4.4.58\';\n  let paymentMap=new Map();\n  let refreshBusy=false;\n  let decorateTimer=0;\n  let listObserver=null;\n\n  const key=(pid,fecha)=>`${Number(pid)}|${String(fecha||\'\').slice(0,10)}`;\n\n  function cachedGroups(){\n    try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}\n    catch(_e){return []}\n  }\n\n  function parseIdentityFromActions(card){\n    const attrs=[...card.querySelectorAll(\'button[onclick],a[onclick]\')]\n      .map(el=>String(el.getAttribute(\'onclick\')||\'\'));\n    // La interfaz puede cambiar previewAzurInvoice por “Revisar y emitir”.\n    // También sirven acciones hermanas como openBillingRecipientEditor(id, fecha).\n    for(const raw of attrs){\n      const m=/\\(\\s*(\\d+)\\s*,\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]/.exec(raw);\n      if(m)return {patient_id:Number(m[1]),fecha:m[2]};\n    }\n    return null;\n  }\n\n  function identityFromCache(card){\n    const cards=[...document.querySelectorAll(\'#billingList .billing-card\')];\n    const idx=cards.indexOf(card);\n    if(idx<0)return null;\n    const g=cachedGroups()[idx];\n    const patientId=Number(g?.patient?.id||0);\n    const fecha=String(g?.fecha||\'\').slice(0,10);\n    return patientId&&/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha)\n      ?{patient_id:patientId,fecha,group:g}:null;\n  }\n\n  function identifyCard(card){\n    if(!card)return null;\n    const dsPid=Number(card.dataset.patientId||0);\n    const dsFecha=String(card.dataset.fecha||\'\').slice(0,10);\n    let id=(dsPid&&/^\\d{4}-\\d{2}-\\d{2}$/.test(dsFecha))\n      ?{patient_id:dsPid,fecha:dsFecha}:parseIdentityFromActions(card);\n    const cached=identityFromCache(card);\n    if(!id&&cached)id=cached;\n    if(!id)return null;\n    if(!id.group&&cached&&Number(cached.patient_id)===Number(id.patient_id)&&cached.fecha===id.fecha)id.group=cached.group;\n    card.dataset.patientId=String(id.patient_id);\n    card.dataset.fecha=id.fecha;\n    return id;\n  }\n\n  function findEmitButton(card){\n    const buttons=[...card.querySelectorAll(\'button\')];\n    let btn=buttons.find(b=>String(b.getAttribute(\'onclick\')||\'\').includes(\'previewAzurInvoice\'));\n    if(btn)return btn;\n    btn=buttons.find(b=>{\n      const t=String(b.textContent||\'\').toLowerCase();\n      return (t.includes(\'revisar\')&&t.includes(\'emitir\'))||t.includes(\'emitir en azur\');\n    });\n    return btn||null;\n  }\n\n  function groupState(id,card){\n    try{\n      if(id?.group&&typeof billingGroupStatus===\'function\')return String(billingGroupStatus(id.group)||\'\').toUpperCase();\n    }catch(_e){}\n    if(card?.classList?.contains(\'aprobada\'))return \'APROBADA\';\n    return findEmitButton(card)?\'APROBADA\':\'\';\n  }\n\n  function isEmissionCard(card,id){\n    if(!id)return false;\n    return groupState(id,card)===\'APROBADA\'||!!findEmitButton(card);\n  }\n\n  function setEmitLock(card,selected){\n    const emit=findEmitButton(card);if(!emit)return;\n    const locked=false;\n    emit.disabled=false;\n    emit.classList.toggle(\'v4435-pay-locked\',locked);\n    emit.setAttribute(\'aria-disabled\',locked?\'true\':\'false\');\n    emit.title=locked?\'Selecciona Efectivo o Transferencia antes de revisar y emitir\':\'\';\n  }\n\n  function renderPicker(card){\n    const id=identifyCard(card);if(!isEmissionCard(card,id))return;\n    const selected=paymentMap.get(key(id.patient_id,id.fecha))||\'\';\n    let wrap=card.querySelector(\'.v4431-pay-wrap\');\n    if(!wrap){\n      wrap=document.createElement(\'div\');\n      wrap.className=\'v4431-pay-wrap\';\n      const foot=card.querySelector(\'.billing-card-foot\');\n      const actions=card.querySelector(\'.billing-actions\');\n      if(foot&&actions&&actions.parentElement===foot)foot.insertBefore(wrap,actions);\n      else if(actions)actions.insertAdjacentElement(\'beforebegin\',wrap);\n      else if(foot)foot.appendChild(wrap);\n      else card.appendChild(wrap);\n    }\n    wrap.dataset.patientId=String(id.patient_id);\n    wrap.dataset.fecha=id.fecha;\n    wrap.innerHTML=`\n      <span class="v4431-pay-label">Forma de pago</span>\n      <button type="button" class="v4431-pay-choice ${selected===\'EFECTIVO\'?\'selected\':\'\'}" data-pay="EFECTIVO">\n        <span class="v4431-check">✓</span><span>💵 Efectivo</span>\n      </button>\n      <button type="button" class="v4431-pay-choice ${selected===\'TRANSFERENCIA\'?\'selected\':\'\'}" data-pay="TRANSFERENCIA">\n        <span class="v4431-check">✓</span><span>🏦 Transferencia</span>\n      </button>`;\n    wrap.querySelectorAll(\'.v4431-pay-choice\').forEach(btn=>{\n      btn.addEventListener(\'click\',()=>saveChoice(wrap,String(btn.dataset.pay||\'\')));\n    });\n    setEmitLock(card,selected);\n  }\n\n  async function saveChoice(wrap,method){\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(method))return;\n    const patient_id=Number(wrap.dataset.patientId||0);\n    const fecha=String(wrap.dataset.fecha||\'\');\n    if(!patient_id||!fecha)return;\n    wrap.classList.add(\'v4431-pay-saving\');\n    try{\n      const d=await api(\'/api/billing/payment-method\',{\n        method:\'POST\',body:JSON.stringify({patient_id,fecha,payment_method:method})\n      });\n      paymentMap.set(key(patient_id,fecha),String(d.payment_method||method));\n      wrap.classList.remove(\'required\');\n      const card=wrap.closest(\'.billing-card\');\n      if(card)renderPicker(card);\n    }catch(e){alert(e.message||\'No se pudo guardar la forma de pago.\')}\n    finally{wrap.classList.remove(\'v4431-pay-saving\')}\n  }\n\n  async function refreshPaymentMap(redecorate=true){\n    if(refreshBusy)return;\n    refreshBusy=true;\n    try{\n      const d=await api(\'/api/billing/payment-methods\');\n      paymentMap=new Map((d?.items||[]).map(x=>[\n        key(x.patient_id,x.fecha),String(x.payment_method||\'\')\n      ]));\n      if(redecorate)decorate();\n    }catch(_e){}\n    finally{refreshBusy=false}\n  }\n\n  function cardMissingPayment(card){\n    const id=identifyCard(card);\n    if(!isEmissionCard(card,id))return false;\n    return !paymentMap.get(key(id.patient_id,id.fecha));\n  }\n\n  async function batchPreflight(){\n    await refreshPaymentMap(false);\n    const cards=[...document.querySelectorAll(\'#billingList .billing-card\')]\n      .filter(card=>isEmissionCard(card,identifyCard(card)));\n    const missing=cards.filter(card=>cardMissingPayment(card));\n    if(missing.length){\n      missing.forEach(card=>card.querySelector(\'.v4431-pay-wrap\')?.classList.add(\'required\'));\n      try{missing[0]?.scrollIntoView({behavior:\'smooth\',block:\'center\'})}catch(_e){}\n      alert(`Antes de emitir por lotes, selecciona Efectivo o Transferencia individualmente en ${missing.length} factura${missing.length===1?\'\':\'s\'}.`);\n      return;\n    }\n    const batchFn=(typeof window.emitAllPendingInvoices===\'function\')\n      ?window.emitAllPendingInvoices\n      :(typeof emitAllPendingInvoices===\'function\'?emitAllPendingInvoices:null);\n    if(batchFn)return batchFn();\n    alert(\'La emisión por lotes no está disponible en esta instalación.\');\n  }\n\n  function ensureBatchButton(){\n    let btn=document.getElementById(\'btnEmitAll\')||document.getElementById(\'v4435EmitAll\');\n    if(btn&&!btn.__v4435BatchClean){\n      const clean=btn.cloneNode(true);\n      clean.__v4435BatchClean=true;\n      btn.replaceWith(clean);\n      btn=clean;\n    }\n    if(!btn){\n      const host=document.querySelector(\'#facturacion .billing-title-actions\')\n        ||document.querySelector(\'#facturacion .page-title-actions\')\n        ||document.querySelector(\'#facturacion .section-title-actions\');\n      if(!host)return;\n      btn=document.createElement(\'button\');\n      btn.id=\'v4435EmitAll\';\n      btn.className=\'btn small secondary\';\n      btn.__v4435BatchClean=true;\n      host.appendChild(btn);\n    }\n    btn.type=\'button\';\n    btn.disabled=false;\n    btn.hidden=false;\n    btn.style.setProperty(\'display\',\'inline-flex\',\'important\');\n    btn.style.setProperty(\'visibility\',\'visible\',\'important\');\n    btn.style.setProperty(\'opacity\',\'1\',\'important\');\n    btn.classList.add(\'v4435-batch-button\');\n    btn.textContent=\'📦 Emitir por lotes\';\n    btn.removeAttribute(\'onclick\');\n    if(!btn.__v4435BatchHook){\n      btn.__v4435BatchHook=true;\n      btn.addEventListener(\'click\',batchPreflight);\n    }\n  }\n\n  function decorate(){\n    document.querySelectorAll(\'#billingList .billing-card\').forEach(card=>renderPicker(card));\n    ensureBatchButton();\n  }\n\n  function scheduleDecorate(){\n    clearTimeout(decorateTimer);\n    decorateTimer=setTimeout(decorate,20);\n  }\n\n  document.addEventListener(\'click\',e=>{\n    const btn=e.target?.closest?.(\'button\');if(!btn)return;\n    const card=btn.closest(\'.billing-card\');if(!card)return;\n    const emit=findEmitButton(card);if(btn!==emit)return;\n    const id=identifyCard(card);if(!id)return;\n    if(!paymentMap.get(key(id.patient_id,id.fecha))){\n      e.preventDefault();e.stopImmediatePropagation();\n      const wrap=card.querySelector(\'.v4431-pay-wrap\');\n      wrap?.classList.add(\'required\');\n      try{wrap?.scrollIntoView({behavior:\'smooth\',block:\'center\'})}catch(_e){}\n      wrap?.querySelector(\'.v4431-pay-choice\')?.focus();\n      alert(\'Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.\');\n    }\n  },true);\n\n  function hookBilling(){\n    const fn=window.loadBilling;\n    if(typeof fn!==\'function\')return false;\n    if(fn.__v4435Hook)return true;\n    const wrapped=async function(){\n      const result=await fn.apply(this,arguments);\n      await refreshPaymentMap(false);\n      scheduleDecorate();\n      return result;\n    };\n    wrapped.__v4435Hook=true;\n    window.loadBilling=wrapped;\n    return true;\n  }\n\n  function observeBillingList(){\n    const list=document.querySelector(\'#billingList\');\n    if(!list||list.__v4435Observed)return;\n    list.__v4435Observed=true;\n    listObserver=new MutationObserver(mutations=>{\n      if(mutations.some(m=>[...m.addedNodes].some(n=>n?.nodeType===1&&(n.matches?.(\'.billing-card\')||n.querySelector?.(\'.billing-card\'))))){\n        refreshPaymentMap(false).finally(scheduleDecorate);\n      }\n    });\n    listObserver.observe(list,{childList:true,subtree:false});\n  }\n\n  async function boot(){\n    hookBilling();\n    observeBillingList();\n    ensureBatchButton();\n    await refreshPaymentMap(false);\n    decorate();\n  }\n\n  window.__v4435BillingPaymentTest={decorate,identifyCard,ensureBatchButton,batchPreflight};\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  else boot();\n})();\n'
    _v459_base = core.V459_SETTINGS_JS or ''
    _v459_bad_root = "const sub=q('.config-title-row .muted','#config');"
    _v459_good_root = "const sub=q('.config-title-row .muted',q('#config')||document);"
    if _v459_bad_root in _v459_base:
        _v459_base = _v459_base.replace(_v459_bad_root, _v459_good_root, 1)
    core.V459_SETTINGS_JS = _v459_base
    _overlay_base = core.V460_OVERLAY_JS or ''
    _overlay_version_marker = "const VERSION='4.4.28';"
    if _overlay_version_marker in _overlay_base:
        _overlay_base = _overlay_base.replace(_overlay_version_marker, "const VERSION='4.4.58';", 1)
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + PAYMENT_CSS
    core.V460_OVERLAY_JS = _overlay_base + '\n' + PAYMENT_JS
    _v4443_base_wa_timeline_defs = core._wa_timeline_defs

    def _v4443_planned_label(raw_due_at: object) -> str:
        raw = str(raw_due_at or '').strip()
        if not raw:
            return ''
        try:
            dt = core.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except Exception:
            return ''
        dias = ('lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom')
        meses = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')
        hour = dt.hour % 12 or 12
        ampm = 'a. m.' if dt.hour < 12 else 'p. m.'
        return f'Se enviará: {dias[dt.weekday()]} {dt.day} {meses[dt.month - 1]} · {hour}:{dt.minute:02d} {ampm}'

    def _wa_timeline_defs_v4443(fecha, hora, created_at=None):
        items = _v4443_base_wa_timeline_defs(fecha, hora, created_at)
        for item in items:
            if not isinstance(item, dict):
                continue
            planned = _v4443_planned_label(item.get('due_at'))
            if planned:
                item['planned'] = planned
        return items
    core._wa_timeline_defs = _wa_timeline_defs_v4443
    V4443_UI_CSS = '\n#facturacion .v4443-emitted-range{\n  display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;\n  margin:4px 0 12px;padding:8px 10px;border:1px solid #dce6f0;border-radius:12px;background:#f8fbfe\n}\n#facturacion .v4443-emitted-range>span{font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:#6a8096}\n#facturacion .v4443-emitted-range-buttons{display:flex;gap:5px;flex-wrap:wrap}\n#facturacion .v4443-emitted-range button{min-height:31px;padding:6px 10px;border:1px solid #cfdae6;border-radius:9px;background:#fff;color:#4d657e;font-size:9px;font-weight:900;cursor:pointer}\n#facturacion .v4443-emitted-range button.active{border-color:#79a7d5;background:#eaf4ff;color:#245b91;box-shadow:0 0 0 2px rgba(70,128,187,.08)}\n#facturacion .v4443-emitted-empty{padding:22px 16px;border:1px dashed #cfdae6;border-radius:12px;text-align:center;color:#71849a;background:#fbfcfe;font-size:11px}\n.native-appointment-detail .v459-wa-copy>small{display:block!important;margin-top:3px!important;font-size:11px!important;line-height:1.3!important;font-weight:750!important;color:#5f748b!important}\n@media(max-width:720px){#facturacion .v4443-emitted-range{align-items:stretch}#facturacion .v4443-emitted-range>span{width:100%}.v4443-emitted-range-buttons{width:100%}#facturacion .v4443-emitted-range button{flex:1}}\n'
    V4443_UI_JS = '\n;(()=>{\n  if(window.__v4443DailyEmitted)return;\n  window.__v4443DailyEmitted=true;\n  let emittedRange=\'today\';\n\n  const state=()=>String(document.querySelector(\'#bEstado\')?.value||\'PENDIENTE\').toUpperCase();\n  const isoLocal=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,\'0\')}-${String(d.getDate()).padStart(2,\'0\')}`;\n  const todayIso=()=>isoLocal(new Date());\n  const weekStartIso=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()-6);return isoLocal(d)};\n  const groups=()=>{try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}catch(_e){return []}};\n\n  function visibleGroups(mode=emittedRange){\n    const all=groups(),today=todayIso(),start=weekStartIso();\n    return all.filter(g=>{\n      const f=String(g?.fecha||\'\').slice(0,10);\n      return mode===\'week\' ? (f>=start&&f<=today) : f===today;\n    });\n  }\n\n  function ensureBar(){\n    const list=document.querySelector(\'#billingList\');\n    let bar=document.getElementById(\'v4443EmittedRange\');\n    if(!list||state()!==\'EMITIDA\'){\n      bar?.remove();\n      return null;\n    }\n    if(!bar){\n      bar=document.createElement(\'div\');\n      bar.id=\'v4443EmittedRange\';\n      bar.className=\'v4443-emitted-range\';\n      list.parentElement?.insertBefore(bar,list);\n    }\n    const todayCount=visibleGroups(\'today\').length,weekCount=visibleGroups(\'week\').length;\n    bar.innerHTML=`<span>Facturas emitidas</span><div class="v4443-emitted-range-buttons"><button type="button" data-range="today" class="${emittedRange===\'today\'?\'active\':\'\'}">Hoy · ${todayCount}</button><button type="button" data-range="week" class="${emittedRange===\'week\'?\'active\':\'\'}">Últimos 7 días · ${weekCount}</button></div>`;\n    bar.querySelectorAll(\'button[data-range]\').forEach(btn=>btn.addEventListener(\'click\',()=>{\n      emittedRange=btn.dataset.range===\'week\'?\'week\':\'today\';\n      renderEmittedRange();\n    }));\n    return bar;\n  }\n\n  function renderEmittedRange(){\n    if(state()!==\'EMITIDA\'){ensureBar();return}\n    const list=document.querySelector(\'#billingList\');if(!list)return;\n    ensureBar();\n    const visible=visibleGroups();\n    try{\n      list.innerHTML=visible.length\n        ?visible.map(g=>billingCardHtml(g)).join(\'\')\n        :`<div class="v4443-emitted-empty">${emittedRange===\'week\'?\'No hay facturas emitidas en los últimos 7 días.\':\'No hay facturas emitidas hoy.\'}</div>`;\n    }catch(_e){}\n  }\n\n  const oldLoad=window.loadBilling;\n  if(typeof oldLoad===\'function\'){\n    window.loadBilling=async function(){\n      const result=await oldLoad.apply(this,arguments);\n      if(state()===\'EMITIDA\')renderEmittedRange();else ensureBar();\n      return result;\n    };\n  }\n\n  const oldSet=window.setBillingStatus;\n  if(typeof oldSet===\'function\'){\n    window.setBillingStatus=async function(next){\n      if(String(next||\'\').toUpperCase()===\'EMITIDA\')emittedRange=\'today\';\n      const result=await oldSet.apply(this,arguments);\n      if(state()===\'EMITIDA\')renderEmittedRange();else ensureBar();\n      return result;\n    };\n  }\n\n  window.__v4443EmittedRangeTest={visibleGroups,renderEmittedRange,setRange:v=>{emittedRange=v===\'week\'?\'week\':\'today\';renderEmittedRange()},getRange:()=>emittedRange};\n})();\n'
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4443_UI_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4443_UI_JS

    class AgendaGuardedAppointmentIn(core.BaseModel):
        patient_id: int
        fecha: _date
        hora: str
        nota: str | None = None
        allow_same_week: bool = False

    def _v4444_phone_variants(value: object) -> list[str]:
        raw = str(value or '').strip()
        clean = core.normalize_lookup_phone(raw)
        values = {x for x in (raw, clean) if x}
        if len(clean) == 10 and clean.startswith('0'):
            values.add('593' + clean[1:])
        return sorted(values)

    def _v4444_same_week_conflict(db, patient, target_date: _date):
        monday = target_date - core.timedelta(days=target_date.weekday())
        sunday = monday + core.timedelta(days=6)
        variants = _v4444_phone_variants(getattr(patient, 'celular', ''))
        identity = [core.Appointment.patient_id == int(patient.id)]
        if variants:
            identity.append(core.Patient.celular.in_(variants))
        linked = db.execute(core.select(core.Appointment, core.Patient).join(core.Patient, core.Patient.id == core.Appointment.patient_id).where(core.Appointment.fecha >= monday, core.Appointment.fecha <= sunday, core.Appointment.origen != core.CONFIRMAFY_ATTENDED_ORIGIN, ~core.func.upper(core.func.coalesce(core.Appointment.estado, '')).in_(['CANCELADA', 'CANCELADO', 'NO_ASISTIRA', 'NO_ASISTIRÁ', 'REAGENDADA']), core.or_(*identity)).order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id).limit(1)).first()
        if linked:
            appointment, owner = linked
            return {'source': 'appointment', 'date': appointment.fecha.isoformat(), 'time': appointment.hora, 'name': owner.nombre}
        if variants:
            staged = db.scalar(core.select(core.ConfirmafyAgendaItem).where(core.ConfirmafyAgendaItem.fecha >= monday, core.ConfirmafyAgendaItem.fecha <= sunday, core.ConfirmafyAgendaItem.celular.in_(variants)).order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id).limit(1))
            if staged:
                return {'source': 'staged', 'date': staged.fecha.isoformat(), 'time': staged.hora, 'name': staged.nombre}
        return None

    @app.get('/api/agenda/week-conflict')
    def agenda_week_conflict_v4444(patient_id: int, fecha: _date, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        patient = db.get(core.Patient, int(patient_id))
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        conflict = _v4444_same_week_conflict(db, patient, fecha)
        monday = fecha - core.timedelta(days=fecha.weekday())
        return {'conflict': conflict, 'week_start': monday.isoformat(), 'week_end': (monday + core.timedelta(days=6)).isoformat()}

    @app.post('/api/agenda/appointments/guarded')
    def agenda_create_guarded_v4444(data: AgendaGuardedAppointmentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        if not core.confirmafy_phone(patient.celular):
            raise core.HTTPException(400, 'Completa el celular del paciente antes de reagendar')
        stable_data = core.AppointmentIn(patient_id=int(data.patient_id), fecha=data.fecha, hora=data.hora, nota=data.nota)
        values = core.normalize_appointment_payload(stable_data)
        slot_conflicts = core.appointment_conflicts(db, values['fecha'], values['hora'], 20)
        if slot_conflicts:
            raise core.HTTPException(409, core.occupied_message(values['fecha'], values['hora'], slot_conflicts))
        conflict = _v4444_same_week_conflict(db, patient, values['fecha'])
        if conflict and (not bool(data.allow_same_week)):
            return {'created': False, 'same_week_conflict': conflict}
        result = core.agenda_create(stable_data, db, user)
        return {'created': True, 'appointment': result}
    V4444_WEEK_GUARD_CSS = '\n.v4444-week-guard-backdrop{position:fixed;inset:0;z-index:100000;display:grid;place-items:center;padding:18px;background:rgba(20,34,49,.48);backdrop-filter:blur(2px)}\n.v4444-week-guard-card{width:min(470px,94vw);padding:20px;border-radius:18px;background:#fff;box-shadow:0 20px 60px rgba(19,38,58,.28);border:1px solid #dbe5ef}\n.v4444-week-guard-card h3{margin:0 0 7px;font-size:18px;color:#263d55}.v4444-week-guard-card p{margin:0;color:#60748a;font-size:12px;line-height:1.45}\n.v4444-week-guard-existing{margin:14px 0;padding:12px;border-radius:12px;background:#fff8e9;border:1px solid #ecd9a9;display:grid;gap:3px}\n.v4444-week-guard-existing span{font-size:9px;font-weight:900;letter-spacing:.07em;color:#85652c}.v4444-week-guard-existing b{font-size:13px;color:#5f4b27}.v4444-week-guard-existing small{font-size:11px;color:#75664a}\n.v4444-week-guard-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}.v4444-week-guard-actions button{min-height:38px;padding:8px 13px;border-radius:10px;border:1px solid #cfdbe6;background:#fff;font-weight:850;cursor:pointer}.v4444-week-guard-actions .proceed{background:#2f6698;color:#fff;border-color:#2f6698}\n@media(max-width:560px){.v4444-week-guard-actions{flex-direction:column-reverse}.v4444-week-guard-actions button{width:100%}}\n'
    V4444_WEEK_GUARD_JS = '\n;(()=>{\n  if(window.__v4444WeeklyAppointmentGuard)return;\n  window.__v4444WeeklyAppointmentGuard=true;\n\n  function weeklyGuardAsk(conflict){\n    return new Promise(resolve=>{\n      document.querySelector(\'.v4444-week-guard-backdrop\')?.remove();\n      const root=document.createElement(\'div\');root.className=\'v4444-week-guard-backdrop\';\n      const d=String(conflict?.date||\'\'),t=String(conflict?.time||\'\'),n=String(conflict?.name||\'Paciente\');\n      root.innerHTML=`<div class="v4444-week-guard-card" role="dialog" aria-modal="true"><h3>Este paciente ya tiene una cita esta semana</h3><p>Revisa la cita existente antes de crear otra. Si realmente necesita dos citas en la misma semana, puedes continuar manualmente.</p><div class="v4444-week-guard-existing"><span>CITA YA REGISTRADA ESA SEMANA</span><b>${esc(n)}</b><small>${fmtDate(d)} · ${fmtTime(t)}</small></div><div class="v4444-week-guard-actions"><button type="button" data-action="cancel">Cancelar</button><button type="button" class="proceed" data-action="proceed">Agendar de todas formas</button></div></div>`;\n      const done=value=>{root.remove();resolve(value)};\n      root.querySelector(\'[data-action="cancel"]\')?.addEventListener(\'click\',()=>done(false));\n      root.querySelector(\'[data-action="proceed"]\')?.addEventListener(\'click\',()=>done(true));\n      root.addEventListener(\'click\',e=>{if(e.target===root)done(false)});\n      document.body.appendChild(root);\n    });\n  }\n\n  window.saveAgendaAppointment=async function(appointmentId=null){\n    // Editar una cita existente conserva exactamente el flujo estable 4.4.43.\n    if(appointmentId){\n      try{\n        const p=agendaPatientCache;if(!p)throw Error(\'No se encontró el paciente.\');\n        const fecha=$(\'#agendaDate\')?.value,hora=$(\'#agendaTime\')?.value,nota=($(\'#agendaNote\')?.value||\'\').trim();\n        if(!fecha||!hora)throw Error(\'Selecciona fecha y hora.\');\n        const body={fecha,hora,nota};\n        await singleFlightMutation(`appointment:${appointmentId}:${p.id}`,async()=>{await api(`/api/agenda/appointments/${appointmentId}`,{method:\'PUT\',body:JSON.stringify(body)});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda()},\'Guardando cita…\');\n      }catch(e){alert(e.message)}\n      return;\n    }\n\n    try{\n      const p=agendaPatientCache;if(!p)throw Error(\'No se encontró el paciente.\');\n      const fecha=$(\'#agendaDate\')?.value,hora=$(\'#agendaTime\')?.value,nota=($(\'#agendaNote\')?.value||\'\').trim();\n      if(!fecha||!hora)throw Error(\'Selecciona fecha y hora.\');\n      const key=`appointment:new:${p.id}`;\n      await singleFlightMutation(key,async()=>{\n        const submit=async allow=>api(\'/api/agenda/appointments/guarded\',{method:\'POST\',body:JSON.stringify({patient_id:p.id,fecha,hora,nota,allow_same_week:!!allow})});\n        let result=await submit(false);\n        if(result?.same_week_conflict){\n          const proceed=await weeklyGuardAsk(result.same_week_conflict);\n          if(!proceed)return;\n          result=await submit(true);\n        }\n        if(!result?.created)throw Error(\'No se pudo confirmar el guardado de la cita. No se creó ninguna cita.\');\n        invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda();\n      },\'Guardando cita…\');\n    }catch(e){alert(e.message)}\n  };\n\n  window.__v4444WeeklyGuardTest={weeklyGuardAsk};\n})();\n'
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4444_WEEK_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4444_WEEK_GUARD_JS
    _v4445_cloud_agenda_lock = core.threading.Lock()
    _v4445_cloud_agenda_at = {}

    def _v4445_sync_cloud_agenda_for_dates(dates, min_interval: float=5.0) -> int:
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
        if not core.cloud_configured() or core.FORCE_OFFLINE or (not core.CloudSessionLocal):
            return 0
        if core.queue_count() > 0:
            return 0
        key = '|'.join((x.isoformat() for x in normalized))
        now = core.time.time()
        if not _v4445_cloud_agenda_lock.acquire(blocking=False):
            return 0
        try:
            last = float(_v4445_cloud_agenda_at.get(key) or 0.0)
            if last and now - last < max(1.0, float(min_interval or 5.0)):
                return 0
            if not core.check_cloud(force=False):
                return 0
            with core.CloudSessionLocal() as cdb:
                linked = list(cdb.execute(core.select(core.Appointment, core.Patient).join(core.Patient, core.Patient.id == core.Appointment.patient_id).where(core.Appointment.fecha.in_(normalized)).order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id)).all())
                staged = list(cdb.scalars(core.select(core.ConfirmafyAgendaItem).where(core.ConfirmafyAgendaItem.fecha.in_(normalized)).order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)))
            mirrored = 0
            for appointment, patient in linked:
                core.mirror_patient_to_local(patient)
                core.mirror_appointment_to_local(appointment)
                mirrored += 1
            with core.LocalSessionLocal() as ldb:
                changed = False
                for row in staged:
                    source_hash = str(getattr(row, 'source_hash', '') or '').strip()
                    if not source_hash or source_hash.startswith('mobile:whatsapp-cloud-test:'):
                        continue
                    existing = ldb.scalar(core.select(core.ConfirmafyAgendaItem).where(core.ConfirmafyAgendaItem.source_hash == source_hash).limit(1))
                    values = {'nombre': row.nombre, 'celular': row.celular, 'fecha': row.fecha, 'hora': row.hora, 'duracion': int(row.duracion or 20), 'created_at': row.created_at}
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
                    if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:
                        continue
                    ldb.add(core.ConfirmafyAgendaItem(id=cloud_id, source_hash=source_hash, **values))
                    changed = True
                    mirrored += 1
                if changed:
                    ldb.commit()
            _v4445_cloud_agenda_at[key] = core.time.time()
            return mirrored
        except Exception as exc:
            try:
                with core._state_lock:
                    core._state['last_error'] = f'No se pudo actualizar Agenda Cloud: {core._cloud_error_hint(exc)}'[:300]
            except Exception:
                pass
            return 0
        finally:
            _v4445_cloud_agenda_lock.release()

    @app.middleware('http')
    async def v4445_cloud_agenda_catchup(request, call_next):
        if request.url.path == '/api/agenda/week':
            try:
                raw_anchor = str(request.query_params.get('anchor') or '').strip()
                anchor_date = _date.fromisoformat(raw_anchor[:10])
                monday = anchor_date - core.timedelta(days=anchor_date.weekday())
                week_dates = [monday + core.timedelta(days=i) for i in range(7)]
                _v4445_sync_cloud_agenda_for_dates(week_dates)
            except Exception:
                pass
        return await call_next(request)
    V4445_STAGED_IDENTITY_CSS = '\n.v4445-phone-match-list{display:grid;gap:9px;margin:14px 0}\n.v4445-phone-match-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border:1px solid #d7e2ec;border-radius:12px;background:#f9fbfd}\n.v4445-phone-match-row>div{display:grid;gap:3px;min-width:0}.v4445-phone-match-row b{font-size:12px;color:#263f59}.v4445-phone-match-row small{font-size:10px;color:#687d92}\n.v4445-phone-match-row button{flex:0 0 auto;min-height:35px;padding:7px 11px;border-radius:9px;border:1px solid #2f6698;background:#2f6698;color:#fff;font-weight:850;cursor:pointer}\n.v4445-phone-note{padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d3e4f5;color:#526d88;font-size:10.5px;line-height:1.4}\n@media(max-width:560px){.v4445-phone-match-row{align-items:stretch;flex-direction:column}.v4445-phone-match-row button{width:100%}}\n'
    V4445_STAGED_IDENTITY_JS = '\n;(()=>{\n  if(window.__v4445StagedIdentityFix)return;\n  window.__v4445StagedIdentityFix=true;\n\n  const stableAttend=window.attendConfirmafyStaged;\n  const stableNewPatient=window.newPatientFromStaged;\n  if(typeof stableAttend!==\'function\'||typeof stableNewPatient!==\'function\')return;\n\n  function phoneKey(value){\n    let d=String(value||\'\').replace(/\\D/g,\'\');\n    if(d.startsWith(\'593\')&&d.length>=12)d=\'0\'+d.slice(3);\n    return d;\n  }\n  function phoneQueries(value){\n    const local=phoneKey(value),out=[];\n    if(local)out.push(local);\n    if(local.length===10&&local.startsWith(\'0\'))out.push(\'593\'+local.slice(1));\n    return [...new Set(out)];\n  }\n  async function exactCurrentPhoneMatches(staged){\n    const wanted=phoneKey(staged?.celular);\n    if(!wanted)return [];\n    const batches=await Promise.all(phoneQueries(staged.celular).map(q=>\n      api(\'/api/patients?q=\'+encodeURIComponent(q)+\'&limit=24\').catch(()=>[])\n    ));\n    const found=new Map();\n    for(const p of batches.flat()){\n      if(!p||Number(p.id||0)<=0)continue;\n      if(typeof isHistoricalPatient===\'function\'&&isHistoricalPatient(p))continue;\n      if(phoneKey(p.celular)===wanted)found.set(Number(p.id),p);\n    }\n    return [...found.values()];\n  }\n  function showPhoneMatches(itemId,fecha,staged,rows){\n    const target=String(fecha||staged?.fecha||toISO(new Date())).slice(0,10);\n    currentStagedResolve=staged;\n    const title=rows.length===1?\'Encontramos una ficha con este celular\':\'Encontramos fichas con este celular\';\n    const list=rows.map(p=>`<article class="v4445-phone-match-row"><div><b>${esc(p.nombre||\'Paciente\')}</b><small>${esc(p.cedula||\'Sin cédula\')} · ${esc(formatPhoneValue(p.celular||\'\')||\'Sin celular\')}</small></div><button type="button" onclick="usePatientForStaged(${Number(itemId)},${Number(p.id)},\'${target}\')">Usar esta ficha</button></article>`).join(\'\');\n    openModal(`<div class="staged-attend-modal v4445-phone-match"><div class="modal-form-heading"><h2>${esc(title)}</h2><p>La cita trae un celular que ya está asociado a una ficha. Revísala antes de crear otro paciente.</p></div><div class="v4445-phone-note">Si corresponde a este paciente, usa su ficha existente y podrás completar los datos que falten dentro de la atención. No se creará un duplicado.</div><div class="v4445-phone-match-list">${list}</div><div class="actions wrap-actions"><button type="button" onclick="openSubsequentStagedSearch(${Number(itemId)},\'${target}\')">Buscar otra ficha</button><button type="button" onclick="v4445CreateDifferentStaged(${Number(itemId)},\'${target}\')">Es otra persona</button><button type="button" class="cancel-btn" onclick="closeModal()">Cancelar</button></div></div>`);\n  }\n\n  window.v4445CreateDifferentStaged=function(itemId,fecha){\n    return stableNewPatient(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));\n  };\n\n  window.attendConfirmafyStaged=async function(itemId,fecha){\n    try{\n      const staged=await getConfirmafyStagedRow(Number(itemId));\n      const rows=await exactCurrentPhoneMatches(staged);\n      if(rows.length){\n        showPhoneMatches(Number(itemId),fecha,staged,rows);\n        return;\n      }\n    }catch(e){\n      console.warn(\'v4445_staged_identity_lookup_failed\',e);\n    }\n    return stableAttend(Number(itemId),fecha);\n  };\n\n  window.__v4445IdentityTest={phoneKey,phoneQueries};\n})();\n'
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4445_STAGED_IDENTITY_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4445_STAGED_IDENTITY_JS

    @app.get('/api/identity/phone-owner')
    def v4446_phone_owner(phone: str, exclude_id: int=0, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        normalized = core.normalize_lookup_phone(phone)
        if not normalized or len(normalized) < 9:
            return {'duplicate': False, 'patient': None}
        variants = {normalized}
        if len(normalized) == 10 and normalized.startswith('0'):
            variants.add('593' + normalized[1:])
        rows = list(db.scalars(core.select(core.Patient).where(core.Patient.celular.in_(sorted(variants))).order_by(core.Patient.id)))
        for patient in rows:
            if int(exclude_id or 0) and int(patient.id) == int(exclude_id):
                continue
            if core.normalize_lookup_phone(patient.celular) == normalized:
                return {'duplicate': True, 'patient': {'id': int(patient.id), 'nombre': patient.nombre, 'cedula': patient.cedula, 'celular': patient.celular}, 'normalized': normalized}
        return {'duplicate': False, 'patient': None, 'normalized': normalized}
    V4446_PHONE_GUARD_CSS = '\n.v4446-phone-duplicate{margin:7px 0 0;padding:10px 11px;border-radius:10px;border:1px solid #e2b66a;background:#fff7e8;color:#6d5223;display:grid;gap:3px}\n.v4446-phone-duplicate b{font-size:11px;color:#8a5910}.v4446-phone-duplicate span{font-size:10px;line-height:1.35}.v4446-phone-duplicate small{font-size:9px;color:#806b49}\n.v4446-phone-duplicate button{justify-self:start;margin-top:5px;min-height:30px;padding:5px 9px;border:1px solid #c99c50;border-radius:8px;background:#fff;color:#725019;font-size:9px;font-weight:900;cursor:pointer}\n'
    V4446_PHONE_GUARD_JS = '\n;(()=>{\n  if(window.__v4446PhoneDuplicateGuard)return;\n  window.__v4446PhoneDuplicateGuard=true;\n  let watcherSeq=0,watcherTimer=0,stagedContext=null,lastOwner=null;\n\n  const cleanPhone=v=>String(v||\'\').replace(/\\D/g,\'\');\n  async function phoneOwner(value,excludeId=0){\n    const q=cleanPhone(value);if(q.length<9)return null;\n    try{\n      const d=await api(\'/api/identity/phone-owner?phone=\'+encodeURIComponent(q)+\'&exclude_id=\'+Number(excludeId||0));\n      return d?.duplicate&&d?.patient?d.patient:null;\n    }catch(_e){return null}\n  }\n  function warningHost(){return $(\'#fCel\')?.closest(\'.form-field\')||$(\'#fCel\')?.parentElement||null}\n  function clearWarning(){document.querySelector(\'#v4446PhoneDuplicateWarning\')?.remove();lastOwner=null}\n  function renderWarning(owner,allowUse=false){\n    clearWarning();if(!owner)return;\n    lastOwner=owner;const host=warningHost();if(!host)return;\n    const box=document.createElement(\'div\');box.id=\'v4446PhoneDuplicateWarning\';box.className=\'v4446-phone-duplicate\';\n    const phone=formatPhoneValue(owner.celular||\'\')||String(owner.celular||\'\');\n    box.innerHTML=`<b>⚠ Este celular ya está registrado</b><span>${esc(owner.nombre||\'Paciente existente\')}</span><small>${esc(owner.cedula||\'Sin cédula\')} · ${esc(phone)}</small>${allowUse?\'<button type="button" id="v4446UseExistingPhoneOwner">Usar esta ficha</button>\':\'\'}`;\n    host.appendChild(box);\n    if(allowUse){\n      box.querySelector(\'#v4446UseExistingPhoneOwner\')?.addEventListener(\'click\',async()=>{\n        const ctx=stagedContext,hit=lastOwner;if(!ctx||!hit)return;\n        await usePatientForStaged(Number(ctx.itemId),Number(hit.id),String(ctx.fecha||toISO(new Date())).slice(0,10));\n      });\n    }\n  }\n  async function checkVisiblePhone(excludeId=0,allowUse=false){\n    const input=$(\'#fCel\');if(!input)return null;\n    const seq=++watcherSeq,owner=await phoneOwner(input.value,excludeId);if(seq!==watcherSeq)return null;\n    renderWarning(owner,allowUse);return owner;\n  }\n  function installWatcher(excludeId=0,ctx=null){\n    stagedContext=ctx||null;const input=$(\'#fCel\');if(!input)return;\n    const allowUse=!!ctx?.itemId;\n    const run=()=>{clearTimeout(watcherTimer);watcherTimer=setTimeout(()=>checkVisiblePhone(excludeId,allowUse),220)};\n    input.addEventListener(\'input\',run);\n    input.addEventListener(\'blur\',()=>checkVisiblePhone(excludeId,allowUse));\n    // Fundamental para citas: el celular puede venir precargado y no recibir input.\n    setTimeout(()=>checkVisiblePhone(excludeId,allowUse),25);\n  }\n  async function stopIfDuplicate(excludeId=0,allowUse=false){\n    const owner=await checkVisiblePhone(excludeId,allowUse);if(!owner)return false;\n    alert(`⚠ Este celular ya está registrado\\n\\n${owner.nombre||\'Paciente existente\'}\\n${formatPhoneValue(owner.celular||\'\')||owner.celular||\'\'}\\n\\nNo se guardó ningún cambio. Revisa o usa la ficha existente.`);\n    return true;\n  }\n\n  // BUG reportado: Completar datos desde Nueva atención entraba en editMode y\n  // el código anterior saltaba la comprobación del número. Aquí se excluye solo\n  // el paciente actual, por lo que mantener su propio celular sigue permitido.\n  const stableEditFromAttention=window.editPatientFromAttention;\n  if(typeof stableEditFromAttention===\'function\')window.editPatientFromAttention=async function(id){\n    const r=await stableEditFromAttention.apply(this,arguments);\n    setTimeout(()=>installWatcher(Number(id||0),null),35);\n    return r;\n  };\n  const stableSaveAndReturn=window.savePatientAndReturnToAttention;\n  if(typeof stableSaveAndReturn===\'function\')window.savePatientAndReturnToAttention=async function(id){\n    if(await stopIfDuplicate(Number(id||0),false))return;\n    return stableSaveAndReturn.apply(this,arguments);\n  };\n\n  // La misma defensa se aplica al editor normal de pacientes.\n  const stableEditPatient=window.editPatient;\n  if(typeof stableEditPatient===\'function\')window.editPatient=async function(id){\n    const r=await stableEditPatient.apply(this,arguments);\n    setTimeout(()=>installWatcher(Number(id||0),null),35);\n    return r;\n  };\n  const stableSavePatient=window.savePatient;\n  if(typeof stableSavePatient===\'function\')window.savePatient=async function(id){\n    if(await stopIfDuplicate(Number(id||0),false))return;\n    return stableSavePatient.apply(this,arguments);\n  };\n\n  // Nuevos pacientes: el aviso visual ya existía, pero ahora el guardado queda\n  // protegido de verdad para que no dependa de que recepción haya visto el texto.\n  const stableNewPatient=window.newPatient;\n  if(typeof stableNewPatient===\'function\')window.newPatient=async function(){\n    const r=await stableNewPatient.apply(this,arguments);setTimeout(()=>installWatcher(0,null),35);return r;\n  };\n  const stableSaveNewPatient=window.saveNewPatient;\n  if(typeof stableSaveNewPatient===\'function\')window.saveNewPatient=async function(){\n    if(await stopIfDuplicate(0,false))return;\n    return stableSaveNewPatient.apply(this,arguments);\n  };\n\n  // Si v4.4.45 deja crear "Es otra persona", el número staged sigue protegido.\n  const stableNewFromStaged=window.newPatientFromStaged;\n  if(typeof stableNewFromStaged===\'function\')window.newPatientFromStaged=async function(itemId,fecha){\n    const r=await stableNewFromStaged.apply(this,arguments);\n    setTimeout(()=>installWatcher(0,{itemId:Number(itemId),fecha:String(fecha||\'\').slice(0,10)}),35);return r;\n  };\n  const stableSaveNewFromStaged=window.saveNewPatientFromStaged;\n  if(typeof stableSaveNewFromStaged===\'function\')window.saveNewPatientFromStaged=async function(itemId,fecha){\n    stagedContext={itemId:Number(itemId),fecha:String(fecha||\'\').slice(0,10)};\n    if(await stopIfDuplicate(0,true))return;\n    return stableSaveNewFromStaged.apply(this,arguments);\n  };\n  // v4.4.45 había capturado la función original antes de esta capa. Redirigirla\n  // garantiza que "Es otra persona" también pase por la guardia nueva.\n  if(typeof window.v4445CreateDifferentStaged===\'function\')window.v4445CreateDifferentStaged=function(itemId,fecha){\n    return window.newPatientFromStaged(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));\n  };\n\n  const stableSaveFromConfirmafy=window.saveNewPatientFromConfirmafy;\n  if(typeof stableSaveFromConfirmafy===\'function\')window.saveNewPatientFromConfirmafy=async function(){\n    if(await stopIfDuplicate(0,false))return;\n    return stableSaveFromConfirmafy.apply(this,arguments);\n  };\n\n  window.__v4446PhoneGuardTest={phoneOwner,checkVisiblePhone,installWatcher};\n})();\n'
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4446_PHONE_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4446_PHONE_GUARD_JS
    _v4449_cloud_sync_blocking = _v4445_sync_cloud_agenda_for_dates
    _v4449_cloud_bg_guard = core.threading.Lock()
    _v4449_cloud_bg_keys: set[str] = set()

    def _v4449_cloud_sync_background(dates, min_interval: float=5.0) -> int:
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
        key = '|'.join(sorted((d.isoformat() for d in normalized)))
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
        core.threading.Thread(target=worker, daemon=True, name='rp-agenda-cloud-catchup').start()
        return 0
    _v4445_sync_cloud_agenda_for_dates = _v4449_cloud_sync_background
    _v4449_timeline_defs_stable = core._wa_timeline_defs

    def _v4449_timeline_defs(fecha, hora, created_at=None):
        rows = _v4449_timeline_defs_stable(fecha, hora, created_at)
        for row in rows:
            if str(row.get('key') or '') == 'cita_agendada':
                row['due_at'] = (core.datetime.now() - core.timedelta(seconds=1)).isoformat()
                row['planned'] = 'Al guardar la cita'
        return rows
    core._wa_timeline_defs = _v4449_timeline_defs
    V4449_AGENDA_FLOW_JS = '\n;(()=>{\n  if(window.__v4449AgendaFlowSpeed)return;\n  window.__v4449AgendaFlowSpeed=true;\n\n  const wait=(ms,fn)=>setTimeout(()=>{try{fn()}catch(_e){}},ms);\n\n  // Nueva atención: primera pintura 100% local. Después de que el espejo Cloud\n  // tuvo tiempo de terminar, una lectura LOCAL muy barata actualiza la lista.\n  const stableLoadAttentionWeek=window.loadAttentionWeek;\n  if(typeof stableLoadAttentionWeek===\'function\'){\n    let seq=0;\n    window.loadAttentionWeek=async function(force=false,anchorValue=null){\n      const token=++seq;\n      const effective=anchorValue||(typeof attentionWeekAnchor!==\'undefined\'?attentionWeekAnchor:null);\n      const result=await stableLoadAttentionWeek.call(this,force,effective);\n      if(!force){\n        [1600,4800].forEach(delay=>wait(delay,()=>{\n          if(token!==seq||!document.querySelector(\'#attentionWeekCalendar\'))return;\n          try{if(typeof invalidateAttentionWeekCache===\'function\')invalidateAttentionWeekCache()}catch(_e){}\n          Promise.resolve(stableLoadAttentionWeek.call(window,true,effective)).catch(()=>{});\n        }));\n      }\n      return result;\n    };\n  }\n\n  // Agenda principal: una sola segunda lectura local. La primera ya no espera a\n  // Neon gracias al backend v4.4.49.\n  const stableLoadAgenda=window.loadAgenda;\n  if(typeof stableLoadAgenda===\'function\'){\n    let agendaSeq=0;\n    window.loadAgenda=async function(){\n      const token=++agendaSeq,args=arguments;\n      const result=await stableLoadAgenda.apply(this,args);\n      wait(2600,()=>{\n        if(token!==agendaSeq)return;\n        const sec=document.querySelector(\'#agenda\');\n        if(sec?.classList?.contains(\'hidden\'))return;\n        Promise.resolve(stableLoadAgenda.apply(window,args)).catch(()=>{});\n      });\n      return result;\n    };\n  }\n\n  // Las citas legacy que YA tienen patient_id no son pacientes nuevos. Solo\n  // los registros realmente staged/sin ficha siguen usando el flujo WhatsApp.\n  const stableAttentionWeekRow=window.attentionWeekRow;\n  if(typeof stableAttentionWeekRow===\'function\')window.attentionWeekRow=function(row){\n    if(String(row?.source_type||\'\')===\'CONFIRMAFY_LEGACY\'&&Number(row?.patient?.id||0)>0){\n      return stableAttentionWeekRow.call(this,{...row,source_type:\'PATIENT_APPOINTMENT\'});\n    }\n    return stableAttentionWeekRow.apply(this,arguments);\n  };\n  const stableNativeAgendaRowCell=window.nativeAgendaRowCell;\n  if(typeof stableNativeAgendaRowCell===\'function\')window.nativeAgendaRowCell=function(row,date,time){\n    if(String(row?.source_type||\'\')===\'CONFIRMAFY_LEGACY\'&&Number(row?.patient?.id||0)>0){\n      return stableNativeAgendaRowCell.call(this,{...row,source_type:\'PATIENT_APPOINTMENT\'},date,time);\n    }\n    return stableNativeAgendaRowCell.apply(this,arguments);\n  };\n\n  const stableAttendFromAgenda=window.attendFromAgenda;\n  async function openExistingUpdateAndAttend(patientId,fecha){\n    const id=Number(patientId||0),today=toISO(new Date()),target=String(fecha||today).slice(0,10);\n    if(!id)return stableAttendFromAgenda?.apply(window,arguments);\n    if(target!==today&&!confirm(`Esta cita corresponde al ${fmtDate(target)}. ¿Registrar la atención con esa fecha?`))return;\n    try{\n      const p=await api(\'/api/patients/\'+id);\n      const missing=typeof missingPatientFields===\'function\'?missingPatientFields(p):[];\n      if(!missing.length){\n        return attentionFor(id,{fecha:target});\n      }\n      const missingText=missing.join(\', \');\n      openModal(`<div class="patient-form-modal v4449-existing-attend"><div class="modal-form-heading"><h2>Actualizar datos y atender</h2><p>Esta cita ya pertenece a <b>${esc(p.nombre||\'este paciente\')}</b>. Actualizaremos la misma ficha; no se creará otra.</p></div><div class="v4449-existing-note">Falta completar: <b>${esc(missingText)}</b></div>${patientForm(p)}<div class="actions form-actions"><button class="cancel-btn" onclick="newAttention()">Volver</button><button class="primary" onclick="v4449SaveExistingAndAttend(${id},\'${target}\')">Guardar cambios y atender</button></div></div>`);\n      wait(35,()=>{\n        try{window.__v4446PhoneGuardTest?.installWatcher?.(id,null)}catch(_e){}\n        const first=missing.includes(\'cédula\')?$(\'#fCedula\'):(missing.includes(\'celular\')?$(\'#fCel\'):(missing.includes(\'correo\')?$(\'#fMail\'):$(\'#fNombre\')));\n        first?.focus?.();\n      });\n    }catch(e){alert(e.message||e)}\n  }\n  if(typeof stableAttendFromAgenda===\'function\')window.attendFromAgenda=openExistingUpdateAndAttend;\n\n  window.v4449SaveExistingAndAttend=async function(patientId,fecha){\n    const id=Number(patientId||0),target=String(fecha||toISO(new Date())).slice(0,10);\n    try{\n      const guard=window.__v4446PhoneGuardTest;\n      if(guard?.checkVisiblePhone){\n        const owner=await guard.checkVisiblePhone(id,false);\n        if(owner){\n          alert(`⚠ Este celular ya pertenece a otra ficha\\n\\n${owner.nombre||\'Paciente existente\'}\\n\\nNo se cambió esta ficha. Revisa el paciente correcto.`);\n          return;\n        }\n      }\n      const data=getPatientForm();\n      await api(\'/api/patients/\'+id,{method:\'PUT\',body:JSON.stringify(data)});\n      try{if(typeof invalidateAttentionWeekCache===\'function\')invalidateAttentionWeekCache()}catch(_e){}\n      await attentionFor(id,{fecha:target});\n    }catch(e){alert(e.message||e)}\n  };\n\n  // Compatibilidad con citas antiguas importadas: si conservan patient_id,\n  // nunca las convertimos a staged ni mostramos "Nueva ficha".\n  const stableAttendLegacy=window.attendLegacyConfirmafy;\n  if(typeof stableAttendLegacy===\'function\')window.attendLegacyConfirmafy=async function(appointmentId,fecha){\n    try{\n      const row=await api(`/api/agenda/appointments/${Number(appointmentId)}`);\n      const patientId=Number(row?.patient?.id||row?.appointment?.patient_id||0);\n      if(patientId)return window.attendFromAgenda(patientId,String(fecha||row?.appointment?.fecha||\'\').slice(0,10));\n    }catch(_e){}\n    return stableAttendLegacy.apply(this,arguments);\n  };\n\n  window.__v4449AgendaTest={openExistingUpdateAndAttend};\n})();\n'
    V4449_AGENDA_FLOW_CSS = '\n.v4449-existing-note{margin:10px 0 14px;padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d6e6f5;color:#536d86;font-size:10px;line-height:1.4}\n.v4449-existing-note b{color:#274d70}\n'
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4449_AGENDA_FLOW_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4449_AGENDA_FLOW_CSS
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
                values = dict(cedula=patient.cedula, nombre=patient.nombre, fecha_nacimiento=patient.fecha_nacimiento, celular=patient.celular, correo=patient.correo, lugar=patient.lugar, notas=patient.notas, created_at=patient.created_at)
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
                    core._state['last_error'] = f"No se pudo reflejar paciente {getattr(patient, 'id', '?')} en SQLite: {exc}"[:300]
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
                visit_ids = [int(x) for x in ldb.scalars(core.select(core.Visit.id).where(core.Visit.patient_id == patient_id))]
                if visit_ids:
                    ldb.execute(core.delete(core.BillingRecord).where(core.BillingRecord.visit_id.in_(visit_ids)))
                if hasattr(core, 'BillingPreference'):
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
                    core._state['last_error'] = f'No se pudo purgar paciente {patient_id} de SQLite: {exc}'[:300]
            except Exception:
                pass
            return False
    core.mirror_patient_to_local = _v4450_mirror_patient_to_local
    core.mirror_delete_patient_local = _v4450_force_delete_patient_local
    _v4450_reconcile_lock = core.threading.Lock()

    def _v4450_reconcile_recent_deleted_patients() -> dict:
        if not _v4450_reconcile_lock.acquire(blocking=False):
            return {'ok': True, 'busy': True, 'purged': 0}
        try:
            if core.queue_count() > 0:
                return {'ok': True, 'skipped': 'offline_queue', 'purged': 0}
            if not core.cloud_configured() or not core.CloudSessionLocal or (not core.check_cloud(force=False)):
                return {'ok': True, 'skipped': 'cloud_unavailable', 'purged': 0}
            ids = set()
            with core.LocalSessionLocal() as ldb:
                rows = list(ldb.scalars(core.select(core.Audit).where(core.Audit.action.in_(('borrar_paciente', 'borrar_paciente_importado_confirmafy'))).order_by(core.Audit.id.desc()).limit(180)))
                for row in rows:
                    match = core.re.search('Paciente\\s+(\\d+)', str(row.detail or ''), flags=core.re.I)
                    if match:
                        ids.add(int(match.group(1)))
            if not ids:
                return {'ok': True, 'purged': 0}
            with core.CloudSessionLocal() as cdb:
                alive = {int(x) for x in cdb.scalars(core.select(core.Patient.id).where(core.Patient.id.in_(sorted(ids))))}
            purged = 0
            for pid in sorted(ids - alive):
                purged += int(_v4450_force_delete_patient_local(pid))
            return {'ok': True, 'purged': purged, 'checked': len(ids)}
        except Exception as exc:
            return {'ok': False, 'purged': 0, 'error': str(exc)[:220]}
        finally:
            _v4450_reconcile_lock.release()

    @app.post('/api/local-cache/reconcile-patients')
    def v4450_reconcile_patients(user=core.Depends(core.current_user)):
        return _v4450_reconcile_recent_deleted_patients()

    def _v4450_repair_worker():
        try:
            core.time.sleep(1.5)
            _v4450_reconcile_recent_deleted_patients()
        except Exception:
            pass
    core.threading.Thread(target=_v4450_repair_worker, daemon=True, name='rp-patient-cache-repair').start()

    @app.post('/api/historical/{hid}/activate-for-staged/{item_id}')
    def v4450_activate_historical_for_staged(hid: int, item_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        staged = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if staged is None:
            raise core.HTTPException(404, 'La cita ya no está disponible')
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
            if owner_info.get('duplicate') and owner_info.get('patient'):
                owner_id = int(owner_info['patient']['id'])
                owner = db.get(core.Patient, owner_id)
                if owner is not None:
                    if source_key:
                        try:
                            core._historical_link_patient(source_key, owner_id)
                        except Exception:
                            pass
                    _v4450_mirror_patient_to_local(owner)
                    out = core.p_dict(owner)
                    out.update({'created': False, 'reused_by_staged_phone': True})
                    return out
        result = core.activate_historical_patient(int(hid), db, user)
        patient_id = int(result.get('id') or 0)
        patient = db.get(core.Patient, patient_id) if patient_id else None
        if patient is None:
            return result
        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, int(patient.id), db, user)
            if owner_info.get('duplicate') and owner_info.get('patient'):
                target_id = int(owner_info['patient']['id'])
                if target_id != int(patient.id):
                    linked = core.link_duplicate_patient(int(patient.id), target_id, db, user)
                    out = dict(linked.get('patient') or {})
                    out.update({'created': False, 'reused_by_staged_phone': True})
                    return out
            if core.normalize_lookup_phone(patient.celular) != staged_phone:
                patient.celular = staged_phone
                core.audit(db, user, 'vincular_celular_cita_historico', f'Paciente {patient.id} · cita staged {item_id}')
                db.commit()
                _v4450_mirror_patient_to_local(patient)
        out = core.p_dict(patient)
        out.update({'created': bool(result.get('created')), 'historical': result.get('historical'), 'staged_phone_linked': bool(staged_phone)})
        return out
    V4450_PATIENT_CACHE_JS = "\n;(()=>{\n  if(window.__v4450PatientCacheIdentity)return;\n  window.__v4450PatientCacheIdentity=true;\n\n  const currentRows=rows=>(Array.isArray(rows)?rows:[]).filter(p=>!(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)));\n\n  // El buscador normal muestra fichas ACTUALES. El histórico sigue disponible\n  // en su filtro dedicado y en el flujo explícito de subsecuente de una cita.\n  const stableRenderPatientResults=renderPatientResults;\n  renderPatientResults=function(rows=[],title=''){\n    const keepHistorical=String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='historical' || String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='review';\n    return stableRenderPatientResults.call(this,keepHistorical?rows:currentRows(rows),title);\n  };\n\n  const stableGlobalResult=globalSearchResultHtml;\n  globalSearchResultHtml=function(p){\n    if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p))return '';\n    return stableGlobalResult.call(this,p);\n  };\n\n  function clearPatientCaches(id=0){\n    try{globalSearchCache=[]}catch(_e){}\n    try{if(Number(id||0)>0)agendaPatientById.delete(Number(id));else agendaPatientById.clear()}catch(_e){}\n    try{if(Number(id||0)>0&&Number(agendaPatientCache?.id||0)===Number(id))agendaPatientCache=null}catch(_e){}\n  }\n  window.__v4450ClearPatientCaches=clearPatientCaches;\n\n  async function reconcileLocalPatients(){\n    try{return await api('/api/local-cache/reconcile-patients',{method:'POST'})}catch(_e){return null}\n  }\n\n  // Borrar pasa por Papelera recuperable y luego limpia caches/UI. Así una ficha\n  // buena no se pierde de forma irreversible por un clic de limpieza.\n  deletePatient=async function(id,visitCount){\n    const extra=visitCount?` También se moverán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'} a la Papelera.`:'';\n    if(!confirmDeletion(`¿Mover este paciente a la Papelera?${extra}\\n\\nPodrás restaurarlo durante 7 días.`))return;\n    try{\n      await singleFlightMutation(`patient:safe-delete:${id}`,async()=>{\n        const result=await api('/api/safety/patients/'+Number(id),{method:'DELETE'});\n        clearPatientCaches(Number(id));\n        await reconcileLocalPatients();\n        closeModal();show('pacientes');\n        try{await searchPatients()}catch(_e){}\n        try{await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()])}catch(_e){}\n        const msg=result?.trash_id?'Paciente movido a Papelera. Puedes restaurarlo desde Actividad → Papelera.':'Paciente eliminado.';\n        if(typeof rpNotice==='function')rpNotice(msg);\n      },'Moviendo…');\n    }catch(e){alert(e.message||e)}\n  };\n\n  // Histórico elegido desde WhatsApp/staged: operación atómica en backend con\n  // el celular de la cita, para que dos históricos no creen dos pacientes.\n  useHistoricalForStaged=async function(itemId,hid,fecha){\n    try{\n      const p=await api(`/api/historical/${Number(hid)}/activate-for-staged/${Number(itemId)}`,{method:'POST'});\n      clearPatientCaches(Number(p?.id||0));\n      try{invalidateAttentionWeekCache()}catch(_e){}\n      await usePatientForStaged(Number(itemId),Number(p.id),fecha);\n    }catch(e){alert(e.message||e)}\n  };\n\n  // Después de cualquier edición desde atención, limpiar caches para que el\n  // nombre recién completado aparezca inmediatamente en ambos buscadores.\n  const stableSaveExistingAndAttend=window.v4449SaveExistingAndAttend;\n  if(typeof stableSaveExistingAndAttend==='function')window.v4449SaveExistingAndAttend=async function(patientId,fecha){\n    const out=await stableSaveExistingAndAttend.apply(this,arguments);\n    clearPatientCaches(Number(patientId||0));\n    return out;\n  };\n  const stableSavePatient=savePatient;\n  savePatient=async function(id,source){\n    const out=await stableSavePatient.apply(this,arguments);\n    clearPatientCaches(Number(id||0));\n    return out;\n  };\n  const stableSaveAndReturn=savePatientAndReturnToAttention;\n  savePatientAndReturnToAttention=async function(id){\n    const out=await stableSaveAndReturn.apply(this,arguments);\n    clearPatientCaches(Number(id||0));\n    return out;\n  };\n\n  // Reparación no bloqueante para instalaciones que ya traían fantasmas de\n  // versiones anteriores. Luego vuelve a consultar solo si hay una búsqueda visible.\n  setTimeout(async()=>{\n    const r=await reconcileLocalPatients();\n    if(!r?.purged)return;\n    clearPatientCaches();\n    try{const g=document.querySelector('#globalSearch');if(g&&String(g.value||'').trim().length>=2)globalSearchPatients(true)}catch(_e){}\n    try{const p=document.querySelector('#search');if(p&&String(p.value||'').trim().length>=2)searchPatients()}catch(_e){}\n  },1800);\n\n  window.__v4450PatientTest={currentRows,reconcileLocalPatients,clearPatientCaches};\n})();\n"
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4450_PATIENT_CACHE_JS

    class V4451VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str

    def _v4451_apply_payment_to_group(db, user, patient_id: int, fecha, method: str):
        method = _normalize_payment_method(method)
        sentinel = PAYMENT_SENTINELS[method]
        rows = db.execute(core.select(core.Visit, core.BillingRecord).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == int(patient_id), core.Visit.fecha == fecha, core.BillingRecord.estado != 'EMITIDA').order_by(core.Visit.id)).all()
        if not rows:
            raise core.HTTPException(404, 'No se encontró la atención recién guardada para registrar su forma de pago.')
        visits = []
        visit_ids = set()
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)
            visit_ids.add(int(visit.id))
        offline = core.is_offline_db(db)
        if offline and visit_ids:
            queued = list(db.scalars(core.select(core.OfflineQueue).where(core.OfflineQueue.operation == 'visit.create', core.OfflineQueue.local_entity_id.in_(sorted(visit_ids)))))
            for item in queued:
                try:
                    payload = core.json.loads(item.payload or '{}')
                except Exception:
                    payload = {}
                payload['source_row'] = sentinel
                item.payload = core.json.dumps(payload, ensure_ascii=False)
        core.audit(db, user, 'registrar_forma_pago_atencion', f'Paciente {patient_id}, {fecha}: {method}')
        db.commit()
        if not offline:
            for visit in visits:
                try:
                    core.mirror_visit_to_local(visit)
                except Exception:
                    pass
        return method
    _v4451_stable_sync_one_operation = core.sync_one_operation

    def _v4451_sync_one_operation(q, ldb, cdb):
        result_id = _v4451_stable_sync_one_operation(q, ldb, cdb)
        if str(getattr(q, 'operation', '') or '') == 'visit.create' and result_id is not None:
            try:
                payload = core.json.loads(getattr(q, 'payload', '') or '{}')
                source_row = int(payload.get('source_row') or 0)
            except Exception:
                source_row = 0
            if source_row in set(PAYMENT_SENTINELS.values()):
                visit = cdb.get(core.Visit, int(result_id))
                if visit is not None:
                    visit.source_row = source_row
        return result_id
    core.sync_one_operation = _v4451_sync_one_operation

    @app.post('/api/visits/batch-payment')
    def v4451_create_visit_batch_payment(data: V4451VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        method = _normalize_payment_method(data.payment_method)
        stable_data = core.VisitBatchIn(patient_id=int(data.patient_id), fecha=data.fecha, tipo=data.tipo, services=data.services, observacion=data.observacion)
        result = core.create_visit_batch(stable_data, db, user)
        _v4451_apply_payment_to_group(db, user, int(data.patient_id), data.fecha, method)
        if isinstance(result, dict):
            result = dict(result)
            result['payment_method'] = method
            result['sri_payment_code'] = SRI_PAYMENT_CODES[method]
        return result
    V4451_PAYMENT_ATTENTION_JS = '\n;(()=>{\n  if(window.__v4451PaymentSourceOfTruth)return;\n  window.__v4451PaymentSourceOfTruth=true;\n\n  let attentionPaymentMethod=\'\';\n\n  function paymentLabel(method){\n    return method===\'TRANSFERENCIA\'?\'Transferencia bancaria\':method===\'EFECTIVO\'?\'Efectivo\':\'\';\n  }\n\n  function renderAttentionPayment(){\n    const modal=document.querySelector(\'.attention-form-modal\');\n    if(!modal)return;\n    let box=modal.querySelector(\'#v4451AttentionPayment\');\n    if(!box){\n      box=document.createElement(\'div\');\n      box.id=\'v4451AttentionPayment\';\n      box.className=\'v4451-attention-payment\';\n      const obs=modal.querySelector(\'.attention-observation\');\n      if(obs)obs.insertAdjacentElement(\'beforebegin\',box);else modal.querySelector(\'.actions\')?.insertAdjacentElement(\'beforebegin\',box);\n    }\n    const selected=String(attentionPaymentMethod||\'\');\n    box.classList.toggle(\'required\',!selected);\n    box.innerHTML=`\n      <div class="v4451-pay-head">\n        <div><b>Forma de pago</b><small>Obligatorio · se usará después en la factura/SRI.</small></div>\n        <span>${selected?`✓ ${paymentLabel(selected)}`:\'Sin seleccionar\'}</span>\n      </div>\n      <div class="v4451-pay-options">\n        <button type="button" class="v4451-pay-option ${selected===\'EFECTIVO\'?\'selected\':\'\'}" onclick="v4451ChooseAttentionPayment(\'EFECTIVO\')"><span>💵</span><b>Efectivo</b><small>SRI 01</small></button>\n        <button type="button" class="v4451-pay-option ${selected===\'TRANSFERENCIA\'?\'selected\':\'\'}" onclick="v4451ChooseAttentionPayment(\'TRANSFERENCIA\')"><span>🏦</span><b>Transferencia bancaria</b><small>SRI 20</small></button>\n      </div>`;\n  }\n\n  window.v4451ChooseAttentionPayment=function(method){\n    const m=String(method||\'\').toUpperCase();\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(m))return;\n    attentionPaymentMethod=m;\n    renderAttentionPayment();\n  };\n\n  const stableAttentionFor=window.attentionFor;\n  if(typeof stableAttentionFor===\'function\')window.attentionFor=async function(id,draft=null){\n    attentionPaymentMethod=String(draft?.paymentMethod||\'\').toUpperCase();\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(attentionPaymentMethod))attentionPaymentMethod=\'\';\n    const out=await stableAttentionFor.apply(this,arguments);\n    renderAttentionPayment();\n    return out;\n  };\n\n  const stableSaveAttention=window.saveAttention;\n  if(typeof stableSaveAttention===\'function\')window.saveAttention=async function(id){\n    const method=String(attentionPaymentMethod||\'\').toUpperCase();\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(method)){\n      const box=document.querySelector(\'#v4451AttentionPayment\');\n      box?.classList.add(\'required\');\n      try{box?.scrollIntoView({behavior:\'smooth\',block:\'center\'})}catch(_e){}\n      alert(\'Selecciona la forma de pago antes de guardar la atención.\');\n      return;\n    }\n\n    const stableApi=window.api||api;\n    const intercept=async function(url,opt={}){\n      if(String(url)===\'/api/visits/batch\'){\n        let body={};\n        try{body=JSON.parse(opt?.body||\'{}\')}catch(_e){body={}}\n        body.payment_method=method;\n        return stableApi(\'/api/visits/batch-payment\',{...opt,body:JSON.stringify(body)});\n      }\n      return stableApi(url,opt);\n    };\n\n    // api es una función global mutable en esta aplicación. Se intercepta solo\n    // durante el guardado y únicamente cambia /api/visits/batch.\n    const previousApi=api;\n    try{\n      api=intercept;\n      return await stableSaveAttention.apply(this,arguments);\n    }finally{\n      api=previousApi;\n    }\n  };\n\n  window.__v4451PaymentTest={renderAttentionPayment,getMethod:()=>attentionPaymentMethod};\n})();\n'
    V4451_PAYMENT_ATTENTION_CSS = '\n.v4451-attention-payment{margin:12px 0 14px;padding:12px;border:1px solid #d8e4ef;border-radius:13px;background:#f8fbfe}\n.v4451-attention-payment.required{border-color:#dda944;background:#fff9ed;box-shadow:0 0 0 3px rgba(221,169,68,.10)}\n.v4451-pay-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:9px}\n.v4451-pay-head>div{display:flex;flex-direction:column;gap:2px}.v4451-pay-head b{font-size:10px;color:#254761}.v4451-pay-head small{font-size:8px;color:#75899b}.v4451-pay-head>span{font-size:8px;font-weight:900;color:#55728a}\n.v4451-pay-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.v4451-pay-option{min-height:54px;border:1px solid #ccd9e5!important;border-radius:11px!important;background:#fff!important;color:#3e5c74!important;display:grid!important;grid-template-columns:auto 1fr auto;align-items:center;gap:7px;text-align:left!important;padding:9px 11px!important;box-shadow:none!important}.v4451-pay-option>b{font-size:9px}.v4451-pay-option>small{font-size:8px;color:#7a8c9d}.v4451-pay-option.selected{border-color:#62af84!important;background:#eaf8f0!important;color:#22613d!important;box-shadow:0 0 0 2px rgba(61,143,91,.09)!important}.v4451-pay-option.selected>small{color:#397052}\n@media(max-width:720px){.v4451-pay-options{grid-template-columns:1fr}.v4451-pay-head{flex-direction:column}}\n'
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4451_PAYMENT_ATTENTION_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4451_PAYMENT_ATTENTION_CSS

    class V4452QuickAppointmentIn(core.BaseModel):
        nombre: str
        celular: str
        fecha: _date
        hora: str
        allow_same_week: bool = False

    def _v4452_quick_source_hash(nombre: str, celular: str, fecha, hora: str) -> str:
        clean_name = core.normalize_lookup_name(nombre or 'PACIENTE')
        clean_phone = core.normalize_lookup_phone(celular or '')
        seed = core.uuid.uuid4().hex
        return 'pc:quick:' + core.hashlib.sha1(f'{clean_name}|{clean_phone}|{fecha.isoformat()}|{hora}|{seed}'.encode('utf-8')).hexdigest()

    @app.post('/api/agenda/unlinked/guarded')
    def v4452_create_quick_unlinked_appointment(data: V4452QuickAppointmentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        name = ' '.join(str(data.nombre or '').split()).upper()
        phone = core.re.sub('\\D', '', str(data.celular or ''))
        if len(name) < 3:
            raise core.HTTPException(400, 'Escribe el nombre del paciente')
        if len(phone) < 8 or len(phone) > 15:
            raise core.HTTPException(400, 'Escribe un celular válido')
        values = core.normalize_appointment_payload(data)
        slot_conflicts = core.appointment_conflicts(db, values['fecha'], values['hora'], 20)
        if slot_conflicts:
            raise core.HTTPException(409, core.occupied_message(values['fecha'], values['hora'], slot_conflicts))
        phone_identity = type('V4452PhoneIdentity', (), {'id': -4452, 'celular': phone})()
        conflict = _v4444_same_week_conflict(db, phone_identity, values['fecha'])
        if conflict and (not bool(data.allow_same_week)):
            return {'created': False, 'same_week_conflict': conflict}
        source_hash = _v4452_quick_source_hash(name, phone, values['fecha'], values['hora'])
        item = core.ConfirmafyAgendaItem(nombre=name, celular=phone, fecha=values['fecha'], hora=values['hora'], duracion=20, source_hash=source_hash)
        db.add(item)
        db.flush()
        offline = core.is_offline_db(db)
        if offline:
            core.add_queue(db, 'confirmafy_staged.create', 'confirmafy_staged', {'nombre': item.nombre, 'celular': item.celular, 'fecha': item.fecha.isoformat(), 'hora': item.hora, 'source_hash': item.source_hash}, user.username, item.id)
        core.audit(db, user, 'crear_cita_rapida_sin_ficha', f"{name} · {values['fecha']} {values['hora']}")
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
                core.schedule_whatsapp_for_contact(source_type='staged', source_id=item.id, name=item.nombre, phone=item.celular or '', fecha=item.fecha, hora=item.hora)
            except Exception:
                pass
        return {'created': True, 'staged': core.confirmafy_agenda_dict(item), 'offline': bool(offline), 'unlinked': True}
    V4452_QUICK_APPOINTMENT_JS = '\n;(()=>{\n  if(window.__v4452QuickUnlinkedAppointment)return;\n  window.__v4452QuickUnlinkedAppointment=true;\n\n  const norm=v=>String(v||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\n  const esc2=v=>typeof esc===\'function\'?esc(String(v??\'\')):String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n\n  function newAppointmentModal(){\n    return [...document.querySelectorAll(\'#modal .modalbox,.modal .modalbox,.modalbox\')].find(box=>\n      [...box.querySelectorAll(\'h1,h2,h3\')].some(h=>norm(h.textContent)===\'nueva cita\')\n    )||null;\n  }\n\n  function parseSlotText(text){\n    const raw=String(text||\'\').replace(/\\s+/g,\' \').trim();\n    const dm=/(\\d{1,2})\\/(\\d{1,2})\\/(\\d{4})/.exec(raw);\n    const tm=/(\\d{1,2}):(\\d{2})\\s*(a\\.?\\s*m\\.?|p\\.?\\s*m\\.?|am|pm)?/i.exec(raw);\n    if(!dm||!tm)return null;\n    const dd=Number(dm[1]),mm=Number(dm[2]),yy=Number(dm[3]);\n    let hh=Number(tm[1]),mi=Number(tm[2]);\n    const ap=norm(tm[3]||\'\').replace(/\\./g,\'\').replace(/\\s/g,\'\');\n    if(ap===\'pm\'&&hh<12)hh+=12;\n    if(ap===\'am\'&&hh===12)hh=0;\n    if(!(dd>=1&&dd<=31&&mm>=1&&mm<=12&&hh>=0&&hh<=23&&mi>=0&&mi<=59))return null;\n    return {fecha:`${String(yy).padStart(4,\'0\')}-${String(mm).padStart(2,\'0\')}-${String(dd).padStart(2,\'0\')}`,hora:`${String(hh).padStart(2,\'0\')}:${String(mi).padStart(2,\'0\')}`};\n  }\n\n  function slotFromModal(box){\n    // El flujo estable guarda usando $(\'#agendaDate\') / $(\'#agendaTime\') a nivel\n    // documento. En algunas composiciones visuales esos inputs quedan fuera del\n    // .modalbox interno aunque pertenecen a la misma ventana Nueva cita.\n    const dateInput=document.querySelector(\'#agendaDate\')||box?.querySelector(\'input[type="date"]\');\n    const timeInput=document.querySelector(\'#agendaTime\')||box?.querySelector(\'input[type="time"]\');\n    const fecha=String(dateInput?.value||\'\').slice(0,10),hora=String(timeInput?.value||\'\').slice(0,5);\n    if(/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha)&&/^\\d{2}:\\d{2}$/.test(hora))return {fecha,hora};\n    const candidates=[...box.querySelectorAll(\'span,button,div\')]\n      .map(el=>String(el.textContent||\'\').trim())\n      .filter(t=>t.length>5&&t.length<90&&/\\d{1,2}\\/\\d{1,2}\\/\\d{4}/.test(t)&&/\\d{1,2}:\\d{2}/.test(t))\n      .sort((a,b)=>a.length-b.length);\n    for(const text of candidates){const parsed=parseSlotText(text);if(parsed)return parsed}\n    return parseSlotText(box?.textContent||\'\');\n  }\n\n  function fmtSlot(slot){\n    try{return `${typeof fmtDate===\'function\'?fmtDate(slot.fecha):slot.fecha} · ${typeof fmtTime===\'function\'?fmtTime(slot.hora):slot.hora}`}\n    catch(_e){return `${slot.fecha} · ${slot.hora}`}\n  }\n\n  window.v4452OpenQuickAppointment=function(){\n    const source=newAppointmentModal();\n    const remembered=window.__v4454SelectedAgendaSlot;\n    const slot=(remembered&&Date.now()-Number(remembered.ts||0)<300000?remembered:null)||slotFromModal(source);\n    if(!slot){alert(\'No pude identificar la fecha y hora seleccionadas. Cierra esta ventana y vuelve a tocar el horario.\');return}\n    openModal(`<div class="v4452-quick-modal"><div class="modal-form-heading"><h2>Crear cita nueva</h2><p>Reserva el horario solo con nombre y celular. La ficha del paciente se completará o vinculará cuando sea atendido.</p></div><div class="v4452-slot"><span>Horario seleccionado</span><b>${esc2(fmtSlot(slot))}</b></div><div class="v4452-fields"><label>Apellidos y nombres<input id="v4452QuickName" maxlength="220" autocomplete="off" placeholder="APELLIDOS Y NOMBRES" oninput="this.value=this.value.toUpperCase()"></label><label>Celular<input id="v4452QuickPhone" inputmode="numeric" maxlength="15" autocomplete="tel" placeholder="09XXXXXXXX" oninput="this.value=this.value.replace(/[^0-9]/g,\'\')"></label></div><div class="v4452-note">Esta acción <b>no crea una ficha de paciente</b>. La cita quedará como “sin ficha vinculada”.</div><div class="actions form-actions"><button class="cancel-btn" onclick="closeModal()">Cancelar</button><button id="v4452QuickSave" class="primary" onclick="v4452SaveQuickAppointment(\'${slot.fecha}\',\'${slot.hora}\',false)">Guardar cita</button></div></div>`);\n    setTimeout(()=>document.querySelector(\'#v4452QuickName\')?.focus(),30);\n  };\n\n  window.v4452SaveQuickAppointment=async function(fecha,hora,allowSameWeek=false){\n    const name=String(document.querySelector(\'#v4452QuickName\')?.value||\'\').trim().replace(/\\s+/g,\' \').toUpperCase();\n    const phone=String(document.querySelector(\'#v4452QuickPhone\')?.value||\'\').replace(/[^0-9]/g,\'\');\n    if(name.length<3){alert(\'Escribe el nombre del paciente.\');document.querySelector(\'#v4452QuickName\')?.focus();return}\n    if(phone.length<8||phone.length>15){alert(\'Escribe un celular válido.\');document.querySelector(\'#v4452QuickPhone\')?.focus();return}\n    const btn=document.querySelector(\'#v4452QuickSave\');if(btn){btn.disabled=true;btn.textContent=\'Guardando…\'}\n    try{\n      const result=await api(\'/api/agenda/unlinked/guarded\',{method:\'POST\',body:JSON.stringify({nombre:name,celular:phone,fecha,hora,allow_same_week:!!allowSameWeek})});\n      if(result?.same_week_conflict&&!allowSameWeek){\n        const c=result.same_week_conflict||{};\n        const when=`${typeof fmtDate===\'function\'?fmtDate(c.date):String(c.date||\'\')} · ${typeof fmtTime===\'function\'?fmtTime(c.time):String(c.time||\'\')}`;\n        const proceed=confirm(`Este paciente ya tiene una cita esta semana:\\n\\n${String(c.name||name)}\\n${when}\\n\\n¿Agendar de todas formas?`);\n        if(proceed)return v4452SaveQuickAppointment(fecha,hora,true);\n        return;\n      }\n      if(!result?.created)throw Error(\'No se pudo crear la cita.\');\n      try{invalidateAgendaSlotCache()}catch(_e){}\n      try{invalidateAttentionWeekCache()}catch(_e){}\n      closeModal();\n      try{agendaNativeAnchor=fecha}catch(_e){}\n      if(typeof loadAgenda===\'function\')await loadAgenda();\n      if(typeof rpNotice===\'function\')rpNotice(\'Cita creada sin ficha de paciente.\');\n    }catch(e){alert(e.message||e)}\n    finally{const b=document.querySelector(\'#v4452QuickSave\');if(b){b.disabled=false;b.textContent=\'Guardar cita\'}}\n  };\n\n  function decorate(){\n    const box=newAppointmentModal();if(!box)return;\n    const buttons=[...box.querySelectorAll(\'button\')];\n    const old=buttons.find(b=>norm(b.textContent).includes(\'nuevo paciente\'));\n    if(old&&!old.dataset.v4452Quick){\n      old.dataset.v4452Quick=\'1\';\n      old.textContent=\'＋ Crear cita nueva\';\n      old.removeAttribute(\'onclick\');\n      old.onclick=e=>{e?.preventDefault?.();e?.stopPropagation?.();window.v4452OpenQuickAppointment()};\n      old.title=\'Agendar solo con nombre y celular, sin crear ficha de paciente\';\n    }\n    const heading=[...box.querySelectorAll(\'.modal-form-heading p,p\')].find(p=>norm(p.textContent).includes(\'selecciona primero\'));\n    if(heading&&!heading.dataset.v4452Copy){heading.dataset.v4452Copy=\'1\';heading.textContent=\'Selecciona un paciente existente o crea una cita nueva solo con nombre y celular.\'}\n  }\n\n  const obs=new MutationObserver(()=>{setTimeout(decorate,0);setTimeout(decorate,80)});\n  const start=()=>{obs.observe(document.body,{childList:true,subtree:true});decorate()};\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',start,{once:true});else start();\n  document.addEventListener(\'click\',()=>setTimeout(decorate,20),true);\n\n  window.__v4452QuickTest={parseSlotText,slotFromModal,decorate};\n})();\n'
    V4452_QUICK_APPOINTMENT_CSS = '\n.v4452-quick-modal{width:min(600px,92vw);display:grid;gap:13px}.v4452-slot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;border:1px solid #cce0d3;border-radius:12px;background:#f1faf4}.v4452-slot span{font-size:8px;font-weight:900;color:#688176;text-transform:uppercase;letter-spacing:.04em}.v4452-slot b{font-size:11px;color:#285a3c}.v4452-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v4452-fields label{display:grid;gap:5px;font-size:9px;font-weight:900;color:#455f75}.v4452-fields input{width:100%;min-height:43px;border:1px solid #cad8e5;border-radius:10px;padding:9px 11px;font-size:11px;font-weight:800;box-sizing:border-box;background:#fff;color:#233e57}.v4452-fields input:focus{outline:0;border-color:#5d91c7;box-shadow:0 0 0 3px rgba(70,126,181,.10)}.v4452-note{padding:9px 11px;border-radius:10px;background:#f7f9fb;color:#65798b;font-size:8.5px;line-height:1.35}.v4452-note b{color:#415c72}@media(max-width:650px){.v4452-fields{grid-template-columns:1fr}.v4452-slot{align-items:flex-start;flex-direction:column}}\n'
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4452_QUICK_APPOINTMENT_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + V4452_QUICK_APPOINTMENT_CSS
    V4454_SLOT_EVENT_JS = '\n;(()=>{\n  if(window.__v4454SlotEventCapture)return;\n  window.__v4454SlotEventCapture=true;\n\n  function normalizeSlot(fecha,hora){\n    const f=String(fecha||\'\').slice(0,10),h=String(hora||\'\').slice(0,5);\n    if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(f)||!/^\\d{2}:\\d{2}$/.test(h))return null;\n    return {fecha:f,hora:h,ts:Date.now()};\n  }\n  function remember(fecha,hora){\n    const slot=normalizeSlot(fecha,hora);\n    if(slot)window.__v4454SelectedAgendaSlot=slot;\n    return slot;\n  }\n  function installWrapper(){\n    const current=window.openAgendaSlotPicker;\n    if(typeof current!==\'function\'||current.__v4454Wrapped)return;\n    const wrapped=function(fecha,hora){remember(fecha,hora);return current.apply(this,arguments)};\n    wrapped.__v4454Wrapped=true;\n    wrapped.__v4454Original=current;\n    window.openAgendaSlotPicker=wrapped;\n  }\n\n  // Captura en fase capture, antes de que ejecute el onclick inline del horario.\n  document.addEventListener(\'click\',e=>{\n    const btn=e.target?.closest?.(\'[onclick*="openAgendaSlotPicker"]\');\n    if(!btn)return;\n    const raw=String(btn.getAttribute(\'onclick\')||\'\');\n    const m=/openAgendaSlotPicker\\(\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]\\s*,\\s*[\'"](\\d{2}:\\d{2})[\'"]\\s*\\)/.exec(raw);\n    if(m)remember(m[1],m[2]);\n  },true);\n\n  installWrapper();\n  setTimeout(installWrapper,0);\n  setTimeout(installWrapper,120);\n  setTimeout(installWrapper,500);\n  document.addEventListener(\'click\',()=>setTimeout(installWrapper,0),true);\n\n  window.__v4454SlotCaptureTest={normalizeSlot,remember,installWrapper,get:()=>window.__v4454SelectedAgendaSlot||null};\n})();\n'
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4454_SLOT_EVENT_JS
    _v4455_stable_normalize_patient_payload = core.normalize_patient_payload

    def _v4455_normalize_patient_payload(data):
        target = data
        raw = getattr(data, 'fecha_nacimiento', None)
        if isinstance(raw, str) and raw.strip():
            try:
                normalized = _v4455_normalize_birth_date_text(raw)
            except ValueError as exc:
                raise core.HTTPException(400, str(exc)) from exc
            if normalized and normalized != raw.strip():
                if hasattr(data, 'model_copy'):
                    target = data.model_copy(update={'fecha_nacimiento': normalized})
                elif hasattr(data, 'copy'):
                    target = data.copy(update={'fecha_nacimiento': normalized})
                else:
                    try:
                        setattr(data, 'fecha_nacimiento', normalized)
                    except Exception:
                        pass
        try:
            return _v4455_stable_normalize_patient_payload(target)
        except ValueError as exc:
            if 'date' in str(exc).lower() or 'isoformat' in str(exc).lower():
                raise core.HTTPException(400, 'Fecha de nacimiento inválida. Usa dd/mm/aaaa.') from exc
            raise
    core.normalize_patient_payload = _v4455_normalize_patient_payload
    V4455_READABLE_ERRORS_JS = "\n;(()=>{\n  if(window.__v4455ReadableErrors)return;\n  window.__v4455ReadableErrors=true;\n  const originalAlert=typeof window.alert==='function'?window.alert.bind(window):null;\n\n  function readable(value){\n    if(value==null)return 'Error inesperado.';\n    if(typeof value==='string'){\n      const t=value.trim();\n      return t&&t!=='[object Object]'?t:'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';\n    }\n    const detail=value?.detail;\n    if(Array.isArray(detail)){\n      const lines=detail.map(x=>{\n        if(typeof x==='string')return x;\n        if(x&&typeof x.msg==='string')return x.msg;\n        try{return JSON.stringify(x)}catch(_e){return String(x)}\n      }).filter(Boolean);\n      if(lines.length)return lines.join('\\n');\n    }\n    if(typeof detail==='string'&&detail.trim())return detail.trim();\n    if(detail&&typeof detail==='object'){\n      if(typeof detail.msg==='string')return detail.msg;\n      try{const s=JSON.stringify(detail);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}\n    }\n    if(typeof value?.message==='string'){\n      const m=value.message.trim();\n      if(m&&m!=='[object Object]')return m;\n      if(m==='[object Object]')return 'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';\n    }\n    try{const s=JSON.stringify(value);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}\n    return 'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';\n  }\n\n  if(originalAlert){\n    window.alert=function(message){return originalAlert(readable(message))};\n  }\n  window.__v4455ReadableErrorText=readable;\n})();\n"
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4455_READABLE_ERRORS_JS
    V4456_PATIENT_ERROR_JS = "\n;(()=>{\n  if(window.__v4456PatientErrorGuard)return;\n  window.__v4456PatientErrorGuard=true;\n  const FALLBACK='No se pudo guardar el paciente. Revisa los datos e inténtalo nuevamente.';\n  const labels={fecha_nacimiento:'Fecha de nacimiento',cedula:'Cédula o identificación',nombre:'Apellidos y nombres',celular:'Celular',correo:'Correo',lugar:'Lugar'};\n\n  function detailLine(item){\n    if(item==null)return '';\n    if(typeof item==='string')return item.trim();\n    if(typeof item!=='object')return String(item);\n    const loc=Array.isArray(item.loc)?item.loc:[];\n    const key=loc.length?String(loc[loc.length-1]||''):'';\n    let msg=typeof item.msg==='string'?item.msg.trim():'';\n    if(key==='fecha_nacimiento'&&/valid date|date or datetime|invalid character|date/i.test(msg))msg='Fecha inválida. Usa dd/mm/aaaa.';\n    const label=labels[key]||key.replaceAll('_',' ');\n    if(label&&msg)return `${label}: ${msg}`;\n    if(msg)return msg;\n    try{const s=JSON.stringify(item);return s==='{}'?'':s}catch(_e){return ''}\n  }\n\n  function structured(value){\n    if(value==null)return '';\n    if(Array.isArray(value))return value.map(detailLine).filter(Boolean).join('\\n');\n    if(typeof value==='object'){\n      if(Array.isArray(value.detail)){\n        const t=value.detail.map(detailLine).filter(Boolean).join('\\n');\n        if(t)return t;\n      }\n      if(typeof value.detail==='string'&&value.detail.trim())return value.detail.trim();\n      if(value.detail&&typeof value.detail==='object'){\n        const t=detailLine(value.detail);if(t)return t;\n      }\n      if(typeof value.message==='string'){\n        const m=value.message.trim();if(m&&m!=='[object Object]')return m;\n      }\n      try{const s=JSON.stringify(value);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}\n      return '';\n    }\n    const t=String(value).trim();return t&&t!=='[object Object]'?t:'';\n  }\n\n  function recentServerError(){\n    const x=window.__v4456LastHttpError;\n    if(!x||Date.now()-Number(x.ts||0)>10000)return '';\n    return structured(x.data);\n  }\n\n  function readable(value){\n    let t=structured(value);\n    if(!t||t==='[object Object]')t=recentServerError();\n    return t&&t!=='[object Object]'?t:FALLBACK;\n  }\n\n  if(typeof window.fetch==='function'&&!window.fetch.__v4456ErrorCapture){\n    const previousFetch=window.fetch.bind(window);\n    const wrapped=async function(...args){\n      const response=await previousFetch(...args);\n      if(response&&!response.ok){\n        try{\n          const data=await response.clone().json();\n          window.__v4456LastHttpError={data,ts:Date.now(),url:String(args[0]?.url||args[0]||'')};\n        }catch(_e){}\n      }\n      return response;\n    };\n    wrapped.__v4456ErrorCapture=true;\n    window.fetch=wrapped;\n  }\n\n  const previousNotice=typeof window.rpNotice==='function'?window.rpNotice.bind(window):null;\n  if(previousNotice){\n    window.rpNotice=function(message,title){return previousNotice(readable(message),title)};\n  }\n  const previousAlert=typeof window.alert==='function'?window.alert.bind(window):null;\n  if(previousAlert){\n    window.alert=function(message){return previousAlert(readable(message))};\n  }\n  window.__v4456ReadablePatientError=readable;\n})();\n"
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + V4456_PATIENT_ERROR_JS
    FEATURE_BOOT_OK = True
except Exception as exc:
    FEATURE_BOOT_ERROR = f'{type(exc).__name__}: {exc}'[:500]
    try:
        error_path = core.Path(core.DATA_DIR) / 'startup_feature_error_v4431.log'
        error_path.write_text(FEATURE_BOOT_ERROR + '\n\n' + traceback.format_exc(), encoding='utf-8')
    except Exception:
        pass
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
