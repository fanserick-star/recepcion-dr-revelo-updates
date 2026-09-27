from __future__ import annotations
import sys as _rf_sys
import types as _rf_types
import core_runtime as _rf_core_runtime

# Consolidated historical feature runtime. No import hooks, no embedded source strings.
_rf_layers = {'app_base_4428': _rf_core_runtime}

def _rf_module_lookup(name, default=None):
    if name in _rf_layers:
        return _rf_layers[name]
    return _rf_sys.modules.get(name, default)

# ---- app_prev_4458 ----
import traceback
import re as _re
from datetime import date as _date
_rf_alias_app_prev_4458__core = _rf_layers['app_base_4428']
APP_VERSION = '4.4.58'
_rf_alias_app_prev_4458__core.APP_VERSION = APP_VERSION
app = _rf_alias_app_prev_4458__core.app
FEATURE_BOOT_OK = False
FEATURE_BOOT_ERROR = ''
PAYMENT_SENTINELS = {'EFECTIVO': -442901, 'TRANSFERENCIA': -442920}
SRI_PAYMENT_CODES = {'EFECTIVO': '01', 'TRANSFERENCIA': '20'}

def _normalize_payment_method(value: object) -> str:
    raw = ' '.join(str(value or '').strip().upper().split())
    aliases = {'TRANSFERENCIA BANCARIA': 'TRANSFERENCIA', 'BANCO': 'TRANSFERENCIA', 'CASH': 'EFECTIVO'}
    raw = aliases.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise _rf_alias_app_prev_4458__core.HTTPException(400, 'Selecciona la forma de pago: Efectivo o Transferencia bancaria.')
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

class BillingPaymentMethodIn(_rf_alias_app_prev_4458__core.BaseModel):
    patient_id: int
    fecha: _date
    payment_method: str
try:

    @app.get('/api/startup-guard')
    def startup_guard_status():
        return {'ok': True, 'version': APP_VERSION, 'base': '4.4.28-lkg', 'feature_boot_ok': FEATURE_BOOT_OK, 'feature_boot_error': FEATURE_BOOT_ERROR, 'architecture': 'stable-base + fail-open-features'}

    @app.get('/api/billing/payment-methods')
    def billing_payment_methods(db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        rows = db.execute(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Visit, _rf_alias_app_prev_4458__core.BillingRecord).join(_rf_alias_app_prev_4458__core.BillingRecord, _rf_alias_app_prev_4458__core.BillingRecord.visit_id == _rf_alias_app_prev_4458__core.Visit.id).where(_rf_alias_app_prev_4458__core.BillingRecord.estado != 'EMITIDA').order_by(_rf_alias_app_prev_4458__core.Visit.fecha.desc(), _rf_alias_app_prev_4458__core.Visit.patient_id, _rf_alias_app_prev_4458__core.Visit.id)).all()
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
    def set_billing_payment_method(data: BillingPaymentMethodIn, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        if _rf_alias_app_prev_4458__core.is_offline_db(db):
            raise _rf_alias_app_prev_4458__core.HTTPException(503, 'Conéctate a Internet para registrar la forma de pago antes de facturar.')
        method = _normalize_payment_method(data.payment_method)
        rows = db.execute(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Visit, _rf_alias_app_prev_4458__core.BillingRecord).join(_rf_alias_app_prev_4458__core.BillingRecord, _rf_alias_app_prev_4458__core.BillingRecord.visit_id == _rf_alias_app_prev_4458__core.Visit.id).where(_rf_alias_app_prev_4458__core.Visit.patient_id == int(data.patient_id), _rf_alias_app_prev_4458__core.Visit.fecha == data.fecha).order_by(_rf_alias_app_prev_4458__core.Visit.id)).all()
        if not rows:
            raise _rf_alias_app_prev_4458__core.HTTPException(404, 'No se encontró esa ficha de facturación.')
        states = {str(b.estado or '').upper() for _, b in rows}
        if 'EMITIDA' in states:
            raise _rf_alias_app_prev_4458__core.HTTPException(409, 'La factura ya fue emitida. Su forma de pago no se modifica.')
        sentinel = PAYMENT_SENTINELS[method]
        visits = []
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)
        _rf_alias_app_prev_4458__core.audit(db, user, 'registrar_forma_pago_facturacion', f'Paciente {data.patient_id}, {data.fecha}: {method}')
        db.commit()
        for visit in visits:
            try:
                _rf_alias_app_prev_4458__core.mirror_visit_to_local(visit)
            except Exception:
                pass
        return {'ok': True, 'patient_id': int(data.patient_id), 'fecha': data.fecha.isoformat(), 'payment_method': method, 'sri_payment_code': SRI_PAYMENT_CODES[method]}
    _stable_azur_payload_for_group = _rf_alias_app_prev_4458__core._azur_payload_for_group

    def _azur_payload_for_group_v4431(data, patient, rows):
        payload = _stable_azur_payload_for_group(data, patient, rows)
        totals: dict[str, float] = {}
        for _billing, visit in rows:
            method = _payment_from_visit(visit)
            if not method:
                raise _rf_alias_app_prev_4458__core.HTTPException(409, 'La forma de pago no está registrada. Vuelve a la atención o selecciónala en Facturación antes de emitir.')
            code = SRI_PAYMENT_CODES[method]
            amount = round(float(getattr(visit, 'valor', 0) or 0), 2)
            totals[code] = round(totals.get(code, 0.0) + amount, 2)
        payload['pagos'] = [{'tipo': code, 'total': amount, 'tiempo': 'dias', 'plazo': 0} for code, amount in sorted(totals.items())]
        return payload
    _rf_alias_app_prev_4458__core._azur_payload_for_group = _azur_payload_for_group_v4431
    PAYMENT_CSS = '\n/* v4.4.35 — forma de pago individual, visible antes de emitir */\n.v4431-pay-wrap{\n  display:flex!important;align-items:center;gap:8px;flex-wrap:wrap;\n  width:100%;box-sizing:border-box;margin:8px 0 10px;padding:9px 10px;\n  border:1px solid #d7e2ed;border-radius:11px;background:#f8fbfe;\n}\n.v4431-pay-label{\n  min-width:86px;font-size:8px;font-weight:950;letter-spacing:.055em;\n  color:#687d93;text-transform:uppercase;margin-right:2px\n}\n.v4431-pay-choice{\n  min-height:32px!important;padding:5px 10px!important;border-radius:9px!important;\n  border:1px solid #cfdbe7!important;background:#fff!important;color:#405b75!important;\n  font-size:9px!important;font-weight:900!important;display:inline-flex!important;\n  align-items:center!important;gap:6px!important;box-shadow:none!important;cursor:pointer!important\n}\n.v4431-pay-choice .v4431-check{\n  width:16px;height:16px;border:1.5px solid #a8b7c6;border-radius:50%;\n  display:inline-grid;place-items:center;font-size:10px;line-height:1;\n  color:transparent;background:#fff\n}\n.v4431-pay-choice.selected{\n  border-color:#72ba91!important;background:#eaf8f0!important;color:#24643f!important\n}\n.v4431-pay-choice.selected .v4431-check{\n  border-color:#2f8d59;background:#2f8d59;color:#fff;font-weight:950;\n  box-shadow:0 0 0 2px rgba(47,141,89,.12)\n}\n.v4431-pay-choice.selected span:last-child{font-weight:950}\n.v4431-pay-wrap.required{\n  border-color:#dfa743!important;background:#fff8e9!important;\n  box-shadow:0 0 0 3px rgba(223,167,67,.12)\n}\n.v4431-pay-wrap.required .v4431-pay-label{color:#9b6900}\n.v4431-pay-saving{opacity:.58;pointer-events:none}\n.billing-card .v4435-pay-locked{\n  opacity:.55!important;filter:saturate(.6);cursor:not-allowed!important\n}\n.v4435-batch-button{\n  display:inline-flex!important;align-items:center!important;justify-content:center!important;\n  visibility:visible!important;opacity:1!important\n}\n.v4431-startup-toast{\n  position:fixed;right:16px;bottom:16px;z-index:10060;padding:8px 11px;\n  border-radius:10px;background:#1f405f;color:#fff;font-size:9px;font-weight:800;\n  box-shadow:0 8px 26px rgba(18,43,66,.22)\n}\n@media(max-width:720px){\n  .v4431-pay-wrap{width:100%;margin:7px 0 9px}\n  .v4431-pay-label{width:100%;min-width:0}\n  .v4431-pay-choice{flex:1;justify-content:center}\n}\n'
    PAYMENT_JS = '\n;(()=>{\n  if(window.__v4435BillingPayment)return;\n  window.__v4435BillingPayment=true;\n  window.__v4431BillingPayment=true;\n\n  const VERSION=\'4.4.58\';\n  let paymentMap=new Map();\n  let refreshBusy=false;\n  let decorateTimer=0;\n  let listObserver=null;\n\n  const key=(pid,fecha)=>`${Number(pid)}|${String(fecha||\'\').slice(0,10)}`;\n\n  function cachedGroups(){\n    try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}\n    catch(_e){return []}\n  }\n\n  function parseIdentityFromActions(card){\n    const attrs=[...card.querySelectorAll(\'button[onclick],a[onclick]\')]\n      .map(el=>String(el.getAttribute(\'onclick\')||\'\'));\n    // La interfaz puede cambiar previewAzurInvoice por “Revisar y emitir”.\n    // También sirven acciones hermanas como openBillingRecipientEditor(id, fecha).\n    for(const raw of attrs){\n      const m=/\\(\\s*(\\d+)\\s*,\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]/.exec(raw);\n      if(m)return {patient_id:Number(m[1]),fecha:m[2]};\n    }\n    return null;\n  }\n\n  function identityFromCache(card){\n    const cards=[...document.querySelectorAll(\'#billingList .billing-card\')];\n    const idx=cards.indexOf(card);\n    if(idx<0)return null;\n    const g=cachedGroups()[idx];\n    const patientId=Number(g?.patient?.id||0);\n    const fecha=String(g?.fecha||\'\').slice(0,10);\n    return patientId&&/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha)\n      ?{patient_id:patientId,fecha,group:g}:null;\n  }\n\n  function identifyCard(card){\n    if(!card)return null;\n    const dsPid=Number(card.dataset.patientId||0);\n    const dsFecha=String(card.dataset.fecha||\'\').slice(0,10);\n    let id=(dsPid&&/^\\d{4}-\\d{2}-\\d{2}$/.test(dsFecha))\n      ?{patient_id:dsPid,fecha:dsFecha}:parseIdentityFromActions(card);\n    const cached=identityFromCache(card);\n    if(!id&&cached)id=cached;\n    if(!id)return null;\n    if(!id.group&&cached&&Number(cached.patient_id)===Number(id.patient_id)&&cached.fecha===id.fecha)id.group=cached.group;\n    card.dataset.patientId=String(id.patient_id);\n    card.dataset.fecha=id.fecha;\n    return id;\n  }\n\n  function findEmitButton(card){\n    const buttons=[...card.querySelectorAll(\'button\')];\n    let btn=buttons.find(b=>String(b.getAttribute(\'onclick\')||\'\').includes(\'previewAzurInvoice\'));\n    if(btn)return btn;\n    btn=buttons.find(b=>{\n      const t=String(b.textContent||\'\').toLowerCase();\n      return (t.includes(\'revisar\')&&t.includes(\'emitir\'))||t.includes(\'emitir en azur\');\n    });\n    return btn||null;\n  }\n\n  function groupState(id,card){\n    try{\n      if(id?.group&&typeof billingGroupStatus===\'function\')return String(billingGroupStatus(id.group)||\'\').toUpperCase();\n    }catch(_e){}\n    if(card?.classList?.contains(\'aprobada\'))return \'APROBADA\';\n    return findEmitButton(card)?\'APROBADA\':\'\';\n  }\n\n  function isEmissionCard(card,id){\n    if(!id)return false;\n    return groupState(id,card)===\'APROBADA\'||!!findEmitButton(card);\n  }\n\n  function setEmitLock(card,selected){\n    const emit=findEmitButton(card);if(!emit)return;\n    const locked=false;\n    emit.disabled=false;\n    emit.classList.toggle(\'v4435-pay-locked\',locked);\n    emit.setAttribute(\'aria-disabled\',locked?\'true\':\'false\');\n    emit.title=locked?\'Selecciona Efectivo o Transferencia antes de revisar y emitir\':\'\';\n  }\n\n  function renderPicker(card){\n    const id=identifyCard(card);if(!isEmissionCard(card,id))return;\n    const selected=paymentMap.get(key(id.patient_id,id.fecha))||\'\';\n    let wrap=card.querySelector(\'.v4431-pay-wrap\');\n    if(!wrap){\n      wrap=document.createElement(\'div\');\n      wrap.className=\'v4431-pay-wrap\';\n      const foot=card.querySelector(\'.billing-card-foot\');\n      const actions=card.querySelector(\'.billing-actions\');\n      if(foot&&actions&&actions.parentElement===foot)foot.insertBefore(wrap,actions);\n      else if(actions)actions.insertAdjacentElement(\'beforebegin\',wrap);\n      else if(foot)foot.appendChild(wrap);\n      else card.appendChild(wrap);\n    }\n    wrap.dataset.patientId=String(id.patient_id);\n    wrap.dataset.fecha=id.fecha;\n    wrap.innerHTML=`\n      <span class="v4431-pay-label">Forma de pago</span>\n      <button type="button" class="v4431-pay-choice ${selected===\'EFECTIVO\'?\'selected\':\'\'}" data-pay="EFECTIVO">\n        <span class="v4431-check">✓</span><span>💵 Efectivo</span>\n      </button>\n      <button type="button" class="v4431-pay-choice ${selected===\'TRANSFERENCIA\'?\'selected\':\'\'}" data-pay="TRANSFERENCIA">\n        <span class="v4431-check">✓</span><span>🏦 Transferencia</span>\n      </button>`;\n    wrap.querySelectorAll(\'.v4431-pay-choice\').forEach(btn=>{\n      btn.addEventListener(\'click\',()=>saveChoice(wrap,String(btn.dataset.pay||\'\')));\n    });\n    setEmitLock(card,selected);\n  }\n\n  async function saveChoice(wrap,method){\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(method))return;\n    const patient_id=Number(wrap.dataset.patientId||0);\n    const fecha=String(wrap.dataset.fecha||\'\');\n    if(!patient_id||!fecha)return;\n    wrap.classList.add(\'v4431-pay-saving\');\n    try{\n      const d=await api(\'/api/billing/payment-method\',{\n        method:\'POST\',body:JSON.stringify({patient_id,fecha,payment_method:method})\n      });\n      paymentMap.set(key(patient_id,fecha),String(d.payment_method||method));\n      wrap.classList.remove(\'required\');\n      const card=wrap.closest(\'.billing-card\');\n      if(card)renderPicker(card);\n    }catch(e){alert(e.message||\'No se pudo guardar la forma de pago.\')}\n    finally{wrap.classList.remove(\'v4431-pay-saving\')}\n  }\n\n  async function refreshPaymentMap(redecorate=true){\n    if(refreshBusy)return;\n    refreshBusy=true;\n    try{\n      const d=await api(\'/api/billing/payment-methods\');\n      paymentMap=new Map((d?.items||[]).map(x=>[\n        key(x.patient_id,x.fecha),String(x.payment_method||\'\')\n      ]));\n      if(redecorate)decorate();\n    }catch(_e){}\n    finally{refreshBusy=false}\n  }\n\n  function cardMissingPayment(card){\n    const id=identifyCard(card);\n    if(!isEmissionCard(card,id))return false;\n    return !paymentMap.get(key(id.patient_id,id.fecha));\n  }\n\n  async function batchPreflight(){\n    await refreshPaymentMap(false);\n    const cards=[...document.querySelectorAll(\'#billingList .billing-card\')]\n      .filter(card=>isEmissionCard(card,identifyCard(card)));\n    const missing=cards.filter(card=>cardMissingPayment(card));\n    if(missing.length){\n      missing.forEach(card=>card.querySelector(\'.v4431-pay-wrap\')?.classList.add(\'required\'));\n      try{missing[0]?.scrollIntoView({behavior:\'smooth\',block:\'center\'})}catch(_e){}\n      alert(`Antes de emitir por lotes, selecciona Efectivo o Transferencia individualmente en ${missing.length} factura${missing.length===1?\'\':\'s\'}.`);\n      return;\n    }\n    const batchFn=(typeof window.emitAllPendingInvoices===\'function\')\n      ?window.emitAllPendingInvoices\n      :(typeof emitAllPendingInvoices===\'function\'?emitAllPendingInvoices:null);\n    if(batchFn)return batchFn();\n    alert(\'La emisión por lotes no está disponible en esta instalación.\');\n  }\n\n  function ensureBatchButton(){\n    let btn=document.getElementById(\'btnEmitAll\')||document.getElementById(\'v4435EmitAll\');\n    if(btn&&!btn.__v4435BatchClean){\n      const clean=btn.cloneNode(true);\n      clean.__v4435BatchClean=true;\n      btn.replaceWith(clean);\n      btn=clean;\n    }\n    if(!btn){\n      const host=document.querySelector(\'#facturacion .billing-title-actions\')\n        ||document.querySelector(\'#facturacion .page-title-actions\')\n        ||document.querySelector(\'#facturacion .section-title-actions\');\n      if(!host)return;\n      btn=document.createElement(\'button\');\n      btn.id=\'v4435EmitAll\';\n      btn.className=\'btn small secondary\';\n      btn.__v4435BatchClean=true;\n      host.appendChild(btn);\n    }\n    btn.type=\'button\';\n    btn.disabled=false;\n    btn.hidden=false;\n    btn.style.setProperty(\'display\',\'inline-flex\',\'important\');\n    btn.style.setProperty(\'visibility\',\'visible\',\'important\');\n    btn.style.setProperty(\'opacity\',\'1\',\'important\');\n    btn.classList.add(\'v4435-batch-button\');\n    btn.textContent=\'📦 Emitir por lotes\';\n    btn.removeAttribute(\'onclick\');\n    if(!btn.__v4435BatchHook){\n      btn.__v4435BatchHook=true;\n      btn.addEventListener(\'click\',batchPreflight);\n    }\n  }\n\n  function decorate(){\n    document.querySelectorAll(\'#billingList .billing-card\').forEach(card=>renderPicker(card));\n    ensureBatchButton();\n  }\n\n  function scheduleDecorate(){\n    clearTimeout(decorateTimer);\n    decorateTimer=setTimeout(decorate,20);\n  }\n\n  document.addEventListener(\'click\',e=>{\n    const btn=e.target?.closest?.(\'button\');if(!btn)return;\n    const card=btn.closest(\'.billing-card\');if(!card)return;\n    const emit=findEmitButton(card);if(btn!==emit)return;\n    const id=identifyCard(card);if(!id)return;\n    if(!paymentMap.get(key(id.patient_id,id.fecha))){\n      e.preventDefault();e.stopImmediatePropagation();\n      const wrap=card.querySelector(\'.v4431-pay-wrap\');\n      wrap?.classList.add(\'required\');\n      try{wrap?.scrollIntoView({behavior:\'smooth\',block:\'center\'})}catch(_e){}\n      wrap?.querySelector(\'.v4431-pay-choice\')?.focus();\n      alert(\'Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.\');\n    }\n  },true);\n\n  function hookBilling(){\n    const fn=window.loadBilling;\n    if(typeof fn!==\'function\')return false;\n    if(fn.__v4435Hook)return true;\n    const wrapped=async function(){\n      const result=await fn.apply(this,arguments);\n      await refreshPaymentMap(false);\n      scheduleDecorate();\n      return result;\n    };\n    wrapped.__v4435Hook=true;\n    window.loadBilling=wrapped;\n    return true;\n  }\n\n  function observeBillingList(){\n    const list=document.querySelector(\'#billingList\');\n    if(!list||list.__v4435Observed)return;\n    list.__v4435Observed=true;\n    listObserver=new MutationObserver(mutations=>{\n      if(mutations.some(m=>[...m.addedNodes].some(n=>n?.nodeType===1&&(n.matches?.(\'.billing-card\')||n.querySelector?.(\'.billing-card\'))))){\n        refreshPaymentMap(false).finally(scheduleDecorate);\n      }\n    });\n    listObserver.observe(list,{childList:true,subtree:false});\n  }\n\n  async function boot(){\n    hookBilling();\n    observeBillingList();\n    ensureBatchButton();\n    await refreshPaymentMap(false);\n    decorate();\n  }\n\n  window.__v4435BillingPaymentTest={decorate,identifyCard,ensureBatchButton,batchPreflight};\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  else boot();\n})();\n'
    _v459_base = _rf_alias_app_prev_4458__core.V459_SETTINGS_JS or ''
    _v459_bad_root = "const sub=q('.config-title-row .muted','#config');"
    _v459_good_root = "const sub=q('.config-title-row .muted',q('#config')||document);"
    if _v459_bad_root in _v459_base:
        _v459_base = _v459_base.replace(_v459_bad_root, _v459_good_root, 1)
    _rf_alias_app_prev_4458__core.V459_SETTINGS_JS = _v459_base
    _overlay_base = _rf_alias_app_prev_4458__core.V460_OVERLAY_JS or ''
    _overlay_version_marker = "const VERSION='4.4.28';"
    if _overlay_version_marker in _overlay_base:
        _overlay_base = _overlay_base.replace(_overlay_version_marker, "const VERSION='4.4.58';", 1)
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + PAYMENT_CSS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = _overlay_base + '\n' + PAYMENT_JS
    _v4443_base_wa_timeline_defs = _rf_alias_app_prev_4458__core._wa_timeline_defs

    def _v4443_planned_label(raw_due_at: object) -> str:
        raw = str(raw_due_at or '').strip()
        if not raw:
            return ''
        try:
            dt = _rf_alias_app_prev_4458__core.datetime.fromisoformat(raw.replace('Z', '+00:00'))
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
    _rf_alias_app_prev_4458__core._wa_timeline_defs = _wa_timeline_defs_v4443
    V4443_UI_CSS = '\n#facturacion .v4443-emitted-range{\n  display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;\n  margin:4px 0 12px;padding:8px 10px;border:1px solid #dce6f0;border-radius:12px;background:#f8fbfe\n}\n#facturacion .v4443-emitted-range>span{font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:#6a8096}\n#facturacion .v4443-emitted-range-buttons{display:flex;gap:5px;flex-wrap:wrap}\n#facturacion .v4443-emitted-range button{min-height:31px;padding:6px 10px;border:1px solid #cfdae6;border-radius:9px;background:#fff;color:#4d657e;font-size:9px;font-weight:900;cursor:pointer}\n#facturacion .v4443-emitted-range button.active{border-color:#79a7d5;background:#eaf4ff;color:#245b91;box-shadow:0 0 0 2px rgba(70,128,187,.08)}\n#facturacion .v4443-emitted-empty{padding:22px 16px;border:1px dashed #cfdae6;border-radius:12px;text-align:center;color:#71849a;background:#fbfcfe;font-size:11px}\n.native-appointment-detail .v459-wa-copy>small{display:block!important;margin-top:3px!important;font-size:11px!important;line-height:1.3!important;font-weight:750!important;color:#5f748b!important}\n@media(max-width:720px){#facturacion .v4443-emitted-range{align-items:stretch}#facturacion .v4443-emitted-range>span{width:100%}.v4443-emitted-range-buttons{width:100%}#facturacion .v4443-emitted-range button{flex:1}}\n'
    V4443_UI_JS = '\n;(()=>{\n  if(window.__v4443DailyEmitted)return;\n  window.__v4443DailyEmitted=true;\n  let emittedRange=\'today\';\n\n  const state=()=>String(document.querySelector(\'#bEstado\')?.value||\'PENDIENTE\').toUpperCase();\n  const isoLocal=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,\'0\')}-${String(d.getDate()).padStart(2,\'0\')}`;\n  const todayIso=()=>isoLocal(new Date());\n  const weekStartIso=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()-6);return isoLocal(d)};\n  const groups=()=>{try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}catch(_e){return []}};\n\n  function visibleGroups(mode=emittedRange){\n    const all=groups(),today=todayIso(),start=weekStartIso();\n    return all.filter(g=>{\n      const f=String(g?.fecha||\'\').slice(0,10);\n      return mode===\'week\' ? (f>=start&&f<=today) : f===today;\n    });\n  }\n\n  function ensureBar(){\n    const list=document.querySelector(\'#billingList\');\n    let bar=document.getElementById(\'v4443EmittedRange\');\n    if(!list||state()!==\'EMITIDA\'){\n      bar?.remove();\n      return null;\n    }\n    if(!bar){\n      bar=document.createElement(\'div\');\n      bar.id=\'v4443EmittedRange\';\n      bar.className=\'v4443-emitted-range\';\n      list.parentElement?.insertBefore(bar,list);\n    }\n    const todayCount=visibleGroups(\'today\').length,weekCount=visibleGroups(\'week\').length;\n    bar.innerHTML=`<span>Facturas emitidas</span><div class="v4443-emitted-range-buttons"><button type="button" data-range="today" class="${emittedRange===\'today\'?\'active\':\'\'}">Hoy · ${todayCount}</button><button type="button" data-range="week" class="${emittedRange===\'week\'?\'active\':\'\'}">Últimos 7 días · ${weekCount}</button></div>`;\n    bar.querySelectorAll(\'button[data-range]\').forEach(btn=>btn.addEventListener(\'click\',()=>{\n      emittedRange=btn.dataset.range===\'week\'?\'week\':\'today\';\n      renderEmittedRange();\n    }));\n    return bar;\n  }\n\n  function renderEmittedRange(){\n    if(state()!==\'EMITIDA\'){ensureBar();return}\n    const list=document.querySelector(\'#billingList\');if(!list)return;\n    ensureBar();\n    const visible=visibleGroups();\n    try{\n      list.innerHTML=visible.length\n        ?visible.map(g=>billingCardHtml(g)).join(\'\')\n        :`<div class="v4443-emitted-empty">${emittedRange===\'week\'?\'No hay facturas emitidas en los últimos 7 días.\':\'No hay facturas emitidas hoy.\'}</div>`;\n    }catch(_e){}\n  }\n\n  const oldLoad=window.loadBilling;\n  if(typeof oldLoad===\'function\'){\n    window.loadBilling=async function(){\n      const result=await oldLoad.apply(this,arguments);\n      if(state()===\'EMITIDA\')renderEmittedRange();else ensureBar();\n      return result;\n    };\n  }\n\n  const oldSet=window.setBillingStatus;\n  if(typeof oldSet===\'function\'){\n    window.setBillingStatus=async function(next){\n      if(String(next||\'\').toUpperCase()===\'EMITIDA\')emittedRange=\'today\';\n      const result=await oldSet.apply(this,arguments);\n      if(state()===\'EMITIDA\')renderEmittedRange();else ensureBar();\n      return result;\n    };\n  }\n\n  window.__v4443EmittedRangeTest={visibleGroups,renderEmittedRange,setRange:v=>{emittedRange=v===\'week\'?\'week\':\'today\';renderEmittedRange()},getRange:()=>emittedRange};\n})();\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4443_UI_CSS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4443_UI_JS

    class AgendaGuardedAppointmentIn(_rf_alias_app_prev_4458__core.BaseModel):
        patient_id: int
        fecha: _date
        hora: str
        nota: str | None = None
        allow_same_week: bool = False

    def _v4444_phone_variants(value: object) -> list[str]:
        raw = str(value or '').strip()
        clean = _rf_alias_app_prev_4458__core.normalize_lookup_phone(raw)
        values = {x for x in (raw, clean) if x}
        if len(clean) == 10 and clean.startswith('0'):
            values.add('593' + clean[1:])
        return sorted(values)

    def _v4444_same_week_conflict(db, patient, target_date: _date):
        monday = target_date - _rf_alias_app_prev_4458__core.timedelta(days=target_date.weekday())
        sunday = monday + _rf_alias_app_prev_4458__core.timedelta(days=6)
        variants = _v4444_phone_variants(getattr(patient, 'celular', ''))
        identity = [_rf_alias_app_prev_4458__core.Appointment.patient_id == int(patient.id)]
        if variants:
            identity.append(_rf_alias_app_prev_4458__core.Patient.celular.in_(variants))
        linked = db.execute(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Appointment, _rf_alias_app_prev_4458__core.Patient).join(_rf_alias_app_prev_4458__core.Patient, _rf_alias_app_prev_4458__core.Patient.id == _rf_alias_app_prev_4458__core.Appointment.patient_id).where(_rf_alias_app_prev_4458__core.Appointment.fecha >= monday, _rf_alias_app_prev_4458__core.Appointment.fecha <= sunday, _rf_alias_app_prev_4458__core.Appointment.origen != _rf_alias_app_prev_4458__core.CONFIRMAFY_ATTENDED_ORIGIN, ~_rf_alias_app_prev_4458__core.func.upper(_rf_alias_app_prev_4458__core.func.coalesce(_rf_alias_app_prev_4458__core.Appointment.estado, '')).in_(['CANCELADA', 'CANCELADO', 'NO_ASISTIRA', 'NO_ASISTIRÁ', 'REAGENDADA']), _rf_alias_app_prev_4458__core.or_(*identity)).order_by(_rf_alias_app_prev_4458__core.Appointment.fecha, _rf_alias_app_prev_4458__core.Appointment.hora, _rf_alias_app_prev_4458__core.Appointment.id).limit(1)).first()
        if linked:
            appointment, owner = linked
            return {'source': 'appointment', 'date': appointment.fecha.isoformat(), 'time': appointment.hora, 'name': owner.nombre}
        if variants:
            staged = db.scalar(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem).where(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.fecha >= monday, _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.fecha <= sunday, _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.celular.in_(variants)).order_by(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.fecha, _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.hora, _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.id).limit(1))
            if staged:
                return {'source': 'staged', 'date': staged.fecha.isoformat(), 'time': staged.hora, 'name': staged.nombre}
        return None

    @app.get('/api/agenda/week-conflict')
    def agenda_week_conflict_v4444(patient_id: int, fecha: _date, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        patient = db.get(_rf_alias_app_prev_4458__core.Patient, int(patient_id))
        if not patient:
            raise _rf_alias_app_prev_4458__core.HTTPException(404, 'Paciente no encontrado')
        conflict = _v4444_same_week_conflict(db, patient, fecha)
        monday = fecha - _rf_alias_app_prev_4458__core.timedelta(days=fecha.weekday())
        return {'conflict': conflict, 'week_start': monday.isoformat(), 'week_end': (monday + _rf_alias_app_prev_4458__core.timedelta(days=6)).isoformat()}

    @app.post('/api/agenda/appointments/guarded')
    def agenda_create_guarded_v4444(data: AgendaGuardedAppointmentIn, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        patient = db.get(_rf_alias_app_prev_4458__core.Patient, int(data.patient_id))
        if not patient:
            raise _rf_alias_app_prev_4458__core.HTTPException(404, 'Paciente no encontrado')
        if not _rf_alias_app_prev_4458__core.confirmafy_phone(patient.celular):
            raise _rf_alias_app_prev_4458__core.HTTPException(400, 'Completa el celular del paciente antes de reagendar')
        stable_data = _rf_alias_app_prev_4458__core.AppointmentIn(patient_id=int(data.patient_id), fecha=data.fecha, hora=data.hora, nota=data.nota)
        values = _rf_alias_app_prev_4458__core.normalize_appointment_payload(stable_data)
        slot_conflicts = _rf_alias_app_prev_4458__core.appointment_conflicts(db, values['fecha'], values['hora'], 20)
        if slot_conflicts:
            raise _rf_alias_app_prev_4458__core.HTTPException(409, _rf_alias_app_prev_4458__core.occupied_message(values['fecha'], values['hora'], slot_conflicts))
        conflict = _v4444_same_week_conflict(db, patient, values['fecha'])
        if conflict and (not bool(data.allow_same_week)):
            return {'created': False, 'same_week_conflict': conflict}
        result = _rf_alias_app_prev_4458__core.agenda_create(stable_data, db, user)
        return {'created': True, 'appointment': result}
    V4444_WEEK_GUARD_CSS = '\n.v4444-week-guard-backdrop{position:fixed;inset:0;z-index:100000;display:grid;place-items:center;padding:18px;background:rgba(20,34,49,.48);backdrop-filter:blur(2px)}\n.v4444-week-guard-card{width:min(470px,94vw);padding:20px;border-radius:18px;background:#fff;box-shadow:0 20px 60px rgba(19,38,58,.28);border:1px solid #dbe5ef}\n.v4444-week-guard-card h3{margin:0 0 7px;font-size:18px;color:#263d55}.v4444-week-guard-card p{margin:0;color:#60748a;font-size:12px;line-height:1.45}\n.v4444-week-guard-existing{margin:14px 0;padding:12px;border-radius:12px;background:#fff8e9;border:1px solid #ecd9a9;display:grid;gap:3px}\n.v4444-week-guard-existing span{font-size:9px;font-weight:900;letter-spacing:.07em;color:#85652c}.v4444-week-guard-existing b{font-size:13px;color:#5f4b27}.v4444-week-guard-existing small{font-size:11px;color:#75664a}\n.v4444-week-guard-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}.v4444-week-guard-actions button{min-height:38px;padding:8px 13px;border-radius:10px;border:1px solid #cfdbe6;background:#fff;font-weight:850;cursor:pointer}.v4444-week-guard-actions .proceed{background:#2f6698;color:#fff;border-color:#2f6698}\n@media(max-width:560px){.v4444-week-guard-actions{flex-direction:column-reverse}.v4444-week-guard-actions button{width:100%}}\n'
    V4444_WEEK_GUARD_JS = '\n;(()=>{\n  if(window.__v4444WeeklyAppointmentGuard)return;\n  window.__v4444WeeklyAppointmentGuard=true;\n\n  function weeklyGuardAsk(conflict){\n    return new Promise(resolve=>{\n      document.querySelector(\'.v4444-week-guard-backdrop\')?.remove();\n      const root=document.createElement(\'div\');root.className=\'v4444-week-guard-backdrop\';\n      const d=String(conflict?.date||\'\'),t=String(conflict?.time||\'\'),n=String(conflict?.name||\'Paciente\');\n      root.innerHTML=`<div class="v4444-week-guard-card" role="dialog" aria-modal="true"><h3>Este paciente ya tiene una cita esta semana</h3><p>Revisa la cita existente antes de crear otra. Si realmente necesita dos citas en la misma semana, puedes continuar manualmente.</p><div class="v4444-week-guard-existing"><span>CITA YA REGISTRADA ESA SEMANA</span><b>${esc(n)}</b><small>${fmtDate(d)} · ${fmtTime(t)}</small></div><div class="v4444-week-guard-actions"><button type="button" data-action="cancel">Cancelar</button><button type="button" class="proceed" data-action="proceed">Agendar de todas formas</button></div></div>`;\n      const done=value=>{root.remove();resolve(value)};\n      root.querySelector(\'[data-action="cancel"]\')?.addEventListener(\'click\',()=>done(false));\n      root.querySelector(\'[data-action="proceed"]\')?.addEventListener(\'click\',()=>done(true));\n      root.addEventListener(\'click\',e=>{if(e.target===root)done(false)});\n      document.body.appendChild(root);\n    });\n  }\n\n  window.saveAgendaAppointment=async function(appointmentId=null){\n    // Editar una cita existente conserva exactamente el flujo estable 4.4.43.\n    if(appointmentId){\n      try{\n        const p=agendaPatientCache;if(!p)throw Error(\'No se encontró el paciente.\');\n        const fecha=$(\'#agendaDate\')?.value,hora=$(\'#agendaTime\')?.value,nota=($(\'#agendaNote\')?.value||\'\').trim();\n        if(!fecha||!hora)throw Error(\'Selecciona fecha y hora.\');\n        const body={fecha,hora,nota};\n        await singleFlightMutation(`appointment:${appointmentId}:${p.id}`,async()=>{await api(`/api/agenda/appointments/${appointmentId}`,{method:\'PUT\',body:JSON.stringify(body)});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda()},\'Guardando cita…\');\n      }catch(e){alert(e.message)}\n      return;\n    }\n\n    try{\n      const p=agendaPatientCache;if(!p)throw Error(\'No se encontró el paciente.\');\n      const fecha=$(\'#agendaDate\')?.value,hora=$(\'#agendaTime\')?.value,nota=($(\'#agendaNote\')?.value||\'\').trim();\n      if(!fecha||!hora)throw Error(\'Selecciona fecha y hora.\');\n      const key=`appointment:new:${p.id}`;\n      await singleFlightMutation(key,async()=>{\n        const submit=async allow=>api(\'/api/agenda/appointments/guarded\',{method:\'POST\',body:JSON.stringify({patient_id:p.id,fecha,hora,nota,allow_same_week:!!allow})});\n        let result=await submit(false);\n        if(result?.same_week_conflict){\n          const proceed=await weeklyGuardAsk(result.same_week_conflict);\n          if(!proceed)return;\n          result=await submit(true);\n        }\n        if(!result?.created)throw Error(\'No se pudo confirmar el guardado de la cita. No se creó ninguna cita.\');\n        invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda();\n      },\'Guardando cita…\');\n    }catch(e){alert(e.message)}\n  };\n\n  window.__v4444WeeklyGuardTest={weeklyGuardAsk};\n})();\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4444_WEEK_GUARD_CSS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4444_WEEK_GUARD_JS
    _v4445_cloud_agenda_lock = _rf_alias_app_prev_4458__core.threading.Lock()
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
        if not _rf_alias_app_prev_4458__core.cloud_configured() or _rf_alias_app_prev_4458__core.FORCE_OFFLINE or (not _rf_alias_app_prev_4458__core.CloudSessionLocal):
            return 0
        if _rf_alias_app_prev_4458__core.queue_count() > 0:
            return 0
        key = '|'.join((x.isoformat() for x in normalized))
        now = _rf_alias_app_prev_4458__core.time.time()
        if not _v4445_cloud_agenda_lock.acquire(blocking=False):
            return 0
        try:
            last = float(_v4445_cloud_agenda_at.get(key) or 0.0)
            if last and now - last < max(1.0, float(min_interval or 5.0)):
                return 0
            if not _rf_alias_app_prev_4458__core.check_cloud(force=False):
                return 0
            with _rf_alias_app_prev_4458__core.CloudSessionLocal() as cdb:
                linked = list(cdb.execute(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Appointment, _rf_alias_app_prev_4458__core.Patient).join(_rf_alias_app_prev_4458__core.Patient, _rf_alias_app_prev_4458__core.Patient.id == _rf_alias_app_prev_4458__core.Appointment.patient_id).where(_rf_alias_app_prev_4458__core.Appointment.fecha.in_(normalized)).order_by(_rf_alias_app_prev_4458__core.Appointment.fecha, _rf_alias_app_prev_4458__core.Appointment.hora, _rf_alias_app_prev_4458__core.Appointment.id)).all())
                staged = list(cdb.scalars(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem).where(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.fecha.in_(normalized)).order_by(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.fecha, _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.hora, _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.id)))
            mirrored = 0
            for appointment, patient in linked:
                _rf_alias_app_prev_4458__core.mirror_patient_to_local(patient)
                _rf_alias_app_prev_4458__core.mirror_appointment_to_local(appointment)
                mirrored += 1
            with _rf_alias_app_prev_4458__core.LocalSessionLocal() as ldb:
                changed = False
                for row in staged:
                    source_hash = str(getattr(row, 'source_hash', '') or '').strip()
                    if not source_hash or source_hash.startswith('mobile:whatsapp-cloud-test:'):
                        continue
                    existing = ldb.scalar(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem).where(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem.source_hash == source_hash).limit(1))
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
                    if ldb.get(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem, cloud_id) is not None:
                        continue
                    ldb.add(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem(id=cloud_id, source_hash=source_hash, **values))
                    changed = True
                    mirrored += 1
                if changed:
                    ldb.commit()
            _v4445_cloud_agenda_at[key] = _rf_alias_app_prev_4458__core.time.time()
            return mirrored
        except Exception as exc:
            try:
                with _rf_alias_app_prev_4458__core._state_lock:
                    _rf_alias_app_prev_4458__core._state['last_error'] = f'No se pudo actualizar Agenda Cloud: {_rf_alias_app_prev_4458__core._cloud_error_hint(exc)}'[:300]
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
                monday = anchor_date - _rf_alias_app_prev_4458__core.timedelta(days=anchor_date.weekday())
                week_dates = [monday + _rf_alias_app_prev_4458__core.timedelta(days=i) for i in range(7)]
                _v4445_sync_cloud_agenda_for_dates(week_dates)
            except Exception:
                pass
        return await call_next(request)
    V4445_STAGED_IDENTITY_CSS = '\n.v4445-phone-match-list{display:grid;gap:9px;margin:14px 0}\n.v4445-phone-match-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border:1px solid #d7e2ec;border-radius:12px;background:#f9fbfd}\n.v4445-phone-match-row>div{display:grid;gap:3px;min-width:0}.v4445-phone-match-row b{font-size:12px;color:#263f59}.v4445-phone-match-row small{font-size:10px;color:#687d92}\n.v4445-phone-match-row button{flex:0 0 auto;min-height:35px;padding:7px 11px;border-radius:9px;border:1px solid #2f6698;background:#2f6698;color:#fff;font-weight:850;cursor:pointer}\n.v4445-phone-note{padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d3e4f5;color:#526d88;font-size:10.5px;line-height:1.4}\n@media(max-width:560px){.v4445-phone-match-row{align-items:stretch;flex-direction:column}.v4445-phone-match-row button{width:100%}}\n'
    V4445_STAGED_IDENTITY_JS = '\n;(()=>{\n  if(window.__v4445StagedIdentityFix)return;\n  window.__v4445StagedIdentityFix=true;\n\n  const stableAttend=window.attendConfirmafyStaged;\n  const stableNewPatient=window.newPatientFromStaged;\n  if(typeof stableAttend!==\'function\'||typeof stableNewPatient!==\'function\')return;\n\n  function phoneKey(value){\n    let d=String(value||\'\').replace(/\\D/g,\'\');\n    if(d.startsWith(\'593\')&&d.length>=12)d=\'0\'+d.slice(3);\n    return d;\n  }\n  function phoneQueries(value){\n    const local=phoneKey(value),out=[];\n    if(local)out.push(local);\n    if(local.length===10&&local.startsWith(\'0\'))out.push(\'593\'+local.slice(1));\n    return [...new Set(out)];\n  }\n  async function exactCurrentPhoneMatches(staged){\n    const wanted=phoneKey(staged?.celular);\n    if(!wanted)return [];\n    const batches=await Promise.all(phoneQueries(staged.celular).map(q=>\n      api(\'/api/patients?q=\'+encodeURIComponent(q)+\'&limit=24\').catch(()=>[])\n    ));\n    const found=new Map();\n    for(const p of batches.flat()){\n      if(!p||Number(p.id||0)<=0)continue;\n      if(typeof isHistoricalPatient===\'function\'&&isHistoricalPatient(p))continue;\n      if(phoneKey(p.celular)===wanted)found.set(Number(p.id),p);\n    }\n    return [...found.values()];\n  }\n  function showPhoneMatches(itemId,fecha,staged,rows){\n    const target=String(fecha||staged?.fecha||toISO(new Date())).slice(0,10);\n    currentStagedResolve=staged;\n    const title=rows.length===1?\'Encontramos una ficha con este celular\':\'Encontramos fichas con este celular\';\n    const list=rows.map(p=>`<article class="v4445-phone-match-row"><div><b>${esc(p.nombre||\'Paciente\')}</b><small>${esc(p.cedula||\'Sin cédula\')} · ${esc(formatPhoneValue(p.celular||\'\')||\'Sin celular\')}</small></div><button type="button" onclick="usePatientForStaged(${Number(itemId)},${Number(p.id)},\'${target}\')">Usar esta ficha</button></article>`).join(\'\');\n    openModal(`<div class="staged-attend-modal v4445-phone-match"><div class="modal-form-heading"><h2>${esc(title)}</h2><p>La cita trae un celular que ya está asociado a una ficha. Revísala antes de crear otro paciente.</p></div><div class="v4445-phone-note">Si corresponde a este paciente, usa su ficha existente y podrás completar los datos que falten dentro de la atención. No se creará un duplicado.</div><div class="v4445-phone-match-list">${list}</div><div class="actions wrap-actions"><button type="button" onclick="openSubsequentStagedSearch(${Number(itemId)},\'${target}\')">Buscar otra ficha</button><button type="button" onclick="v4445CreateDifferentStaged(${Number(itemId)},\'${target}\')">Es otra persona</button><button type="button" class="cancel-btn" onclick="closeModal()">Cancelar</button></div></div>`);\n  }\n\n  window.v4445CreateDifferentStaged=function(itemId,fecha){\n    return stableNewPatient(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));\n  };\n\n  window.attendConfirmafyStaged=async function(itemId,fecha){\n    try{\n      const staged=await getConfirmafyStagedRow(Number(itemId));\n      const rows=await exactCurrentPhoneMatches(staged);\n      if(rows.length){\n        showPhoneMatches(Number(itemId),fecha,staged,rows);\n        return;\n      }\n    }catch(e){\n      console.warn(\'v4445_staged_identity_lookup_failed\',e);\n    }\n    return stableAttend(Number(itemId),fecha);\n  };\n\n  window.__v4445IdentityTest={phoneKey,phoneQueries};\n})();\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4445_STAGED_IDENTITY_CSS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4445_STAGED_IDENTITY_JS

    @app.get('/api/identity/phone-owner')
    def v4446_phone_owner(phone: str, exclude_id: int=0, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        normalized = _rf_alias_app_prev_4458__core.normalize_lookup_phone(phone)
        if not normalized or len(normalized) < 9:
            return {'duplicate': False, 'patient': None}
        variants = {normalized}
        if len(normalized) == 10 and normalized.startswith('0'):
            variants.add('593' + normalized[1:])
        rows = list(db.scalars(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Patient).where(_rf_alias_app_prev_4458__core.Patient.celular.in_(sorted(variants))).order_by(_rf_alias_app_prev_4458__core.Patient.id)))
        for patient in rows:
            if int(exclude_id or 0) and int(patient.id) == int(exclude_id):
                continue
            if _rf_alias_app_prev_4458__core.normalize_lookup_phone(patient.celular) == normalized:
                return {'duplicate': True, 'patient': {'id': int(patient.id), 'nombre': patient.nombre, 'cedula': patient.cedula, 'celular': patient.celular}, 'normalized': normalized}
        return {'duplicate': False, 'patient': None, 'normalized': normalized}
    V4446_PHONE_GUARD_CSS = '\n.v4446-phone-duplicate{margin:7px 0 0;padding:10px 11px;border-radius:10px;border:1px solid #e2b66a;background:#fff7e8;color:#6d5223;display:grid;gap:3px}\n.v4446-phone-duplicate b{font-size:11px;color:#8a5910}.v4446-phone-duplicate span{font-size:10px;line-height:1.35}.v4446-phone-duplicate small{font-size:9px;color:#806b49}\n.v4446-phone-duplicate button{justify-self:start;margin-top:5px;min-height:30px;padding:5px 9px;border:1px solid #c99c50;border-radius:8px;background:#fff;color:#725019;font-size:9px;font-weight:900;cursor:pointer}\n'
    V4446_PHONE_GUARD_JS = '\n;(()=>{\n  if(window.__v4446PhoneDuplicateGuard)return;\n  window.__v4446PhoneDuplicateGuard=true;\n  let watcherSeq=0,watcherTimer=0,stagedContext=null,lastOwner=null;\n\n  const cleanPhone=v=>String(v||\'\').replace(/\\D/g,\'\');\n  async function phoneOwner(value,excludeId=0){\n    const q=cleanPhone(value);if(q.length<9)return null;\n    try{\n      const d=await api(\'/api/identity/phone-owner?phone=\'+encodeURIComponent(q)+\'&exclude_id=\'+Number(excludeId||0));\n      return d?.duplicate&&d?.patient?d.patient:null;\n    }catch(_e){return null}\n  }\n  function warningHost(){return $(\'#fCel\')?.closest(\'.form-field\')||$(\'#fCel\')?.parentElement||null}\n  function clearWarning(){document.querySelector(\'#v4446PhoneDuplicateWarning\')?.remove();lastOwner=null}\n  function renderWarning(owner,allowUse=false){\n    clearWarning();if(!owner)return;\n    lastOwner=owner;const host=warningHost();if(!host)return;\n    const box=document.createElement(\'div\');box.id=\'v4446PhoneDuplicateWarning\';box.className=\'v4446-phone-duplicate\';\n    const phone=formatPhoneValue(owner.celular||\'\')||String(owner.celular||\'\');\n    box.innerHTML=`<b>⚠ Este celular ya está registrado</b><span>${esc(owner.nombre||\'Paciente existente\')}</span><small>${esc(owner.cedula||\'Sin cédula\')} · ${esc(phone)}</small>${allowUse?\'<button type="button" id="v4446UseExistingPhoneOwner">Usar esta ficha</button>\':\'\'}`;\n    host.appendChild(box);\n    if(allowUse){\n      box.querySelector(\'#v4446UseExistingPhoneOwner\')?.addEventListener(\'click\',async()=>{\n        const ctx=stagedContext,hit=lastOwner;if(!ctx||!hit)return;\n        await usePatientForStaged(Number(ctx.itemId),Number(hit.id),String(ctx.fecha||toISO(new Date())).slice(0,10));\n      });\n    }\n  }\n  async function checkVisiblePhone(excludeId=0,allowUse=false){\n    const input=$(\'#fCel\');if(!input)return null;\n    const seq=++watcherSeq,owner=await phoneOwner(input.value,excludeId);if(seq!==watcherSeq)return null;\n    renderWarning(owner,allowUse);return owner;\n  }\n  function installWatcher(excludeId=0,ctx=null){\n    stagedContext=ctx||null;const input=$(\'#fCel\');if(!input)return;\n    const allowUse=!!ctx?.itemId;\n    const run=()=>{clearTimeout(watcherTimer);watcherTimer=setTimeout(()=>checkVisiblePhone(excludeId,allowUse),220)};\n    input.addEventListener(\'input\',run);\n    input.addEventListener(\'blur\',()=>checkVisiblePhone(excludeId,allowUse));\n    // Fundamental para citas: el celular puede venir precargado y no recibir input.\n    setTimeout(()=>checkVisiblePhone(excludeId,allowUse),25);\n  }\n  async function stopIfDuplicate(excludeId=0,allowUse=false){\n    const owner=await checkVisiblePhone(excludeId,allowUse);if(!owner)return false;\n    alert(`⚠ Este celular ya está registrado\\n\\n${owner.nombre||\'Paciente existente\'}\\n${formatPhoneValue(owner.celular||\'\')||owner.celular||\'\'}\\n\\nNo se guardó ningún cambio. Revisa o usa la ficha existente.`);\n    return true;\n  }\n\n  // BUG reportado: Completar datos desde Nueva atención entraba en editMode y\n  // el código anterior saltaba la comprobación del número. Aquí se excluye solo\n  // el paciente actual, por lo que mantener su propio celular sigue permitido.\n  const stableEditFromAttention=window.editPatientFromAttention;\n  if(typeof stableEditFromAttention===\'function\')window.editPatientFromAttention=async function(id){\n    const r=await stableEditFromAttention.apply(this,arguments);\n    setTimeout(()=>installWatcher(Number(id||0),null),35);\n    return r;\n  };\n  const stableSaveAndReturn=window.savePatientAndReturnToAttention;\n  if(typeof stableSaveAndReturn===\'function\')window.savePatientAndReturnToAttention=async function(id){\n    if(await stopIfDuplicate(Number(id||0),false))return;\n    return stableSaveAndReturn.apply(this,arguments);\n  };\n\n  // La misma defensa se aplica al editor normal de pacientes.\n  const stableEditPatient=window.editPatient;\n  if(typeof stableEditPatient===\'function\')window.editPatient=async function(id){\n    const r=await stableEditPatient.apply(this,arguments);\n    setTimeout(()=>installWatcher(Number(id||0),null),35);\n    return r;\n  };\n  const stableSavePatient=window.savePatient;\n  if(typeof stableSavePatient===\'function\')window.savePatient=async function(id){\n    if(await stopIfDuplicate(Number(id||0),false))return;\n    return stableSavePatient.apply(this,arguments);\n  };\n\n  // Nuevos pacientes: el aviso visual ya existía, pero ahora el guardado queda\n  // protegido de verdad para que no dependa de que recepción haya visto el texto.\n  const stableNewPatient=window.newPatient;\n  if(typeof stableNewPatient===\'function\')window.newPatient=async function(){\n    const r=await stableNewPatient.apply(this,arguments);setTimeout(()=>installWatcher(0,null),35);return r;\n  };\n  const stableSaveNewPatient=window.saveNewPatient;\n  if(typeof stableSaveNewPatient===\'function\')window.saveNewPatient=async function(){\n    if(await stopIfDuplicate(0,false))return;\n    return stableSaveNewPatient.apply(this,arguments);\n  };\n\n  // Si v4.4.45 deja crear "Es otra persona", el número staged sigue protegido.\n  const stableNewFromStaged=window.newPatientFromStaged;\n  if(typeof stableNewFromStaged===\'function\')window.newPatientFromStaged=async function(itemId,fecha){\n    const r=await stableNewFromStaged.apply(this,arguments);\n    setTimeout(()=>installWatcher(0,{itemId:Number(itemId),fecha:String(fecha||\'\').slice(0,10)}),35);return r;\n  };\n  const stableSaveNewFromStaged=window.saveNewPatientFromStaged;\n  if(typeof stableSaveNewFromStaged===\'function\')window.saveNewPatientFromStaged=async function(itemId,fecha){\n    stagedContext={itemId:Number(itemId),fecha:String(fecha||\'\').slice(0,10)};\n    if(await stopIfDuplicate(0,true))return;\n    return stableSaveNewFromStaged.apply(this,arguments);\n  };\n  // v4.4.45 había capturado la función original antes de esta capa. Redirigirla\n  // garantiza que "Es otra persona" también pase por la guardia nueva.\n  if(typeof window.v4445CreateDifferentStaged===\'function\')window.v4445CreateDifferentStaged=function(itemId,fecha){\n    return window.newPatientFromStaged(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));\n  };\n\n  const stableSaveFromConfirmafy=window.saveNewPatientFromConfirmafy;\n  if(typeof stableSaveFromConfirmafy===\'function\')window.saveNewPatientFromConfirmafy=async function(){\n    if(await stopIfDuplicate(0,false))return;\n    return stableSaveFromConfirmafy.apply(this,arguments);\n  };\n\n  window.__v4446PhoneGuardTest={phoneOwner,checkVisiblePhone,installWatcher};\n})();\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4446_PHONE_GUARD_CSS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4446_PHONE_GUARD_JS
    _v4449_cloud_sync_blocking = _v4445_sync_cloud_agenda_for_dates
    _v4449_cloud_bg_guard = _rf_alias_app_prev_4458__core.threading.Lock()
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
        _rf_alias_app_prev_4458__core.threading.Thread(target=worker, daemon=True, name='rp-agenda-cloud-catchup').start()
        return 0
    _v4445_sync_cloud_agenda_for_dates = _v4449_cloud_sync_background
    _v4449_timeline_defs_stable = _rf_alias_app_prev_4458__core._wa_timeline_defs

    def _v4449_timeline_defs(fecha, hora, created_at=None):
        rows = _v4449_timeline_defs_stable(fecha, hora, created_at)
        for row in rows:
            if str(row.get('key') or '') == 'cita_agendada':
                row['due_at'] = (_rf_alias_app_prev_4458__core.datetime.now() - _rf_alias_app_prev_4458__core.timedelta(seconds=1)).isoformat()
                row['planned'] = 'Al guardar la cita'
        return rows
    _rf_alias_app_prev_4458__core._wa_timeline_defs = _v4449_timeline_defs
    V4449_AGENDA_FLOW_JS = '\n;(()=>{\n  if(window.__v4449AgendaFlowSpeed)return;\n  window.__v4449AgendaFlowSpeed=true;\n\n  const wait=(ms,fn)=>setTimeout(()=>{try{fn()}catch(_e){}},ms);\n\n  // Nueva atención: primera pintura 100% local. Después de que el espejo Cloud\n  // tuvo tiempo de terminar, una lectura LOCAL muy barata actualiza la lista.\n  const stableLoadAttentionWeek=window.loadAttentionWeek;\n  if(typeof stableLoadAttentionWeek===\'function\'){\n    let seq=0;\n    window.loadAttentionWeek=async function(force=false,anchorValue=null){\n      const token=++seq;\n      const effective=anchorValue||(typeof attentionWeekAnchor!==\'undefined\'?attentionWeekAnchor:null);\n      const result=await stableLoadAttentionWeek.call(this,force,effective);\n      if(!force){\n        [1600,4800].forEach(delay=>wait(delay,()=>{\n          if(token!==seq||!document.querySelector(\'#attentionWeekCalendar\'))return;\n          try{if(typeof invalidateAttentionWeekCache===\'function\')invalidateAttentionWeekCache()}catch(_e){}\n          Promise.resolve(stableLoadAttentionWeek.call(window,true,effective)).catch(()=>{});\n        }));\n      }\n      return result;\n    };\n  }\n\n  // Agenda principal: una sola segunda lectura local. La primera ya no espera a\n  // Neon gracias al backend v4.4.49.\n  const stableLoadAgenda=window.loadAgenda;\n  if(typeof stableLoadAgenda===\'function\'){\n    let agendaSeq=0;\n    window.loadAgenda=async function(){\n      const token=++agendaSeq,args=arguments;\n      const result=await stableLoadAgenda.apply(this,args);\n      wait(2600,()=>{\n        if(token!==agendaSeq)return;\n        const sec=document.querySelector(\'#agenda\');\n        if(sec?.classList?.contains(\'hidden\'))return;\n        Promise.resolve(stableLoadAgenda.apply(window,args)).catch(()=>{});\n      });\n      return result;\n    };\n  }\n\n  // Las citas legacy que YA tienen patient_id no son pacientes nuevos. Solo\n  // los registros realmente staged/sin ficha siguen usando el flujo WhatsApp.\n  const stableAttentionWeekRow=window.attentionWeekRow;\n  if(typeof stableAttentionWeekRow===\'function\')window.attentionWeekRow=function(row){\n    if(String(row?.source_type||\'\')===\'CONFIRMAFY_LEGACY\'&&Number(row?.patient?.id||0)>0){\n      return stableAttentionWeekRow.call(this,{...row,source_type:\'PATIENT_APPOINTMENT\'});\n    }\n    return stableAttentionWeekRow.apply(this,arguments);\n  };\n  const stableNativeAgendaRowCell=window.nativeAgendaRowCell;\n  if(typeof stableNativeAgendaRowCell===\'function\')window.nativeAgendaRowCell=function(row,date,time){\n    if(String(row?.source_type||\'\')===\'CONFIRMAFY_LEGACY\'&&Number(row?.patient?.id||0)>0){\n      return stableNativeAgendaRowCell.call(this,{...row,source_type:\'PATIENT_APPOINTMENT\'},date,time);\n    }\n    return stableNativeAgendaRowCell.apply(this,arguments);\n  };\n\n  const stableAttendFromAgenda=window.attendFromAgenda;\n  async function openExistingUpdateAndAttend(patientId,fecha){\n    const id=Number(patientId||0),today=toISO(new Date()),target=String(fecha||today).slice(0,10);\n    if(!id)return stableAttendFromAgenda?.apply(window,arguments);\n    if(target!==today&&!confirm(`Esta cita corresponde al ${fmtDate(target)}. ¿Registrar la atención con esa fecha?`))return;\n    try{\n      const p=await api(\'/api/patients/\'+id);\n      const missing=typeof missingPatientFields===\'function\'?missingPatientFields(p):[];\n      if(!missing.length){\n        return attentionFor(id,{fecha:target});\n      }\n      const missingText=missing.join(\', \');\n      openModal(`<div class="patient-form-modal v4449-existing-attend"><div class="modal-form-heading"><h2>Actualizar datos y atender</h2><p>Esta cita ya pertenece a <b>${esc(p.nombre||\'este paciente\')}</b>. Actualizaremos la misma ficha; no se creará otra.</p></div><div class="v4449-existing-note">Falta completar: <b>${esc(missingText)}</b></div>${patientForm(p)}<div class="actions form-actions"><button class="cancel-btn" onclick="newAttention()">Volver</button><button class="primary" onclick="v4449SaveExistingAndAttend(${id},\'${target}\')">Guardar cambios y atender</button></div></div>`);\n      wait(35,()=>{\n        try{window.__v4446PhoneGuardTest?.installWatcher?.(id,null)}catch(_e){}\n        const first=missing.includes(\'cédula\')?$(\'#fCedula\'):(missing.includes(\'celular\')?$(\'#fCel\'):(missing.includes(\'correo\')?$(\'#fMail\'):$(\'#fNombre\')));\n        first?.focus?.();\n      });\n    }catch(e){alert(e.message||e)}\n  }\n  if(typeof stableAttendFromAgenda===\'function\')window.attendFromAgenda=openExistingUpdateAndAttend;\n\n  window.v4449SaveExistingAndAttend=async function(patientId,fecha){\n    const id=Number(patientId||0),target=String(fecha||toISO(new Date())).slice(0,10);\n    try{\n      const guard=window.__v4446PhoneGuardTest;\n      if(guard?.checkVisiblePhone){\n        const owner=await guard.checkVisiblePhone(id,false);\n        if(owner){\n          alert(`⚠ Este celular ya pertenece a otra ficha\\n\\n${owner.nombre||\'Paciente existente\'}\\n\\nNo se cambió esta ficha. Revisa el paciente correcto.`);\n          return;\n        }\n      }\n      const data=getPatientForm();\n      await api(\'/api/patients/\'+id,{method:\'PUT\',body:JSON.stringify(data)});\n      try{if(typeof invalidateAttentionWeekCache===\'function\')invalidateAttentionWeekCache()}catch(_e){}\n      await attentionFor(id,{fecha:target});\n    }catch(e){alert(e.message||e)}\n  };\n\n  // Compatibilidad con citas antiguas importadas: si conservan patient_id,\n  // nunca las convertimos a staged ni mostramos "Nueva ficha".\n  const stableAttendLegacy=window.attendLegacyConfirmafy;\n  if(typeof stableAttendLegacy===\'function\')window.attendLegacyConfirmafy=async function(appointmentId,fecha){\n    try{\n      const row=await api(`/api/agenda/appointments/${Number(appointmentId)}`);\n      const patientId=Number(row?.patient?.id||row?.appointment?.patient_id||0);\n      if(patientId)return window.attendFromAgenda(patientId,String(fecha||row?.appointment?.fecha||\'\').slice(0,10));\n    }catch(_e){}\n    return stableAttendLegacy.apply(this,arguments);\n  };\n\n  window.__v4449AgendaTest={openExistingUpdateAndAttend};\n})();\n'
    V4449_AGENDA_FLOW_CSS = '\n.v4449-existing-note{margin:10px 0 14px;padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d6e6f5;color:#536d86;font-size:10px;line-height:1.4}\n.v4449-existing-note b{color:#274d70}\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4449_AGENDA_FLOW_JS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4449_AGENDA_FLOW_CSS
    _v4450_stable_mirror_patient = _rf_alias_app_prev_4458__core.mirror_patient_to_local
    _v4450_stable_mirror_delete_patient = _rf_alias_app_prev_4458__core.mirror_delete_patient_local

    def _v4450_mirror_patient_to_local(patient) -> bool:
        try:
            _v4450_stable_mirror_patient(patient)
        except Exception:
            pass
        try:
            with _rf_alias_app_prev_4458__core.LocalSessionLocal() as ldb:
                lp = ldb.get(_rf_alias_app_prev_4458__core.Patient, int(patient.id))
                values = dict(cedula=patient.cedula, nombre=patient.nombre, fecha_nacimiento=patient.fecha_nacimiento, celular=patient.celular, correo=patient.correo, lugar=patient.lugar, notas=patient.notas, created_at=patient.created_at)
                if lp is None:
                    ldb.add(_rf_alias_app_prev_4458__core.Patient(id=int(patient.id), **values))
                else:
                    for key, value in values.items():
                        setattr(lp, key, value)
                ldb.commit()
            return True
        except Exception as exc:
            try:
                with _rf_alias_app_prev_4458__core._state_lock:
                    _rf_alias_app_prev_4458__core._state['last_error'] = f"No se pudo reflejar paciente {getattr(patient, 'id', '?')} en SQLite: {exc}"[:300]
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
            with _rf_alias_app_prev_4458__core.LocalSessionLocal() as ldb:
                if ldb.get(_rf_alias_app_prev_4458__core.Patient, patient_id) is None:
                    return True
                visit_ids = [int(x) for x in ldb.scalars(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Visit.id).where(_rf_alias_app_prev_4458__core.Visit.patient_id == patient_id))]
                if visit_ids:
                    ldb.execute(_rf_alias_app_prev_4458__core.delete(_rf_alias_app_prev_4458__core.BillingRecord).where(_rf_alias_app_prev_4458__core.BillingRecord.visit_id.in_(visit_ids)))
                if hasattr(_rf_alias_app_prev_4458__core, 'BillingPreference'):
                    ldb.execute(_rf_alias_app_prev_4458__core.delete(_rf_alias_app_prev_4458__core.BillingPreference).where(_rf_alias_app_prev_4458__core.BillingPreference.patient_id == patient_id))
                ldb.execute(_rf_alias_app_prev_4458__core.delete(_rf_alias_app_prev_4458__core.Appointment).where(_rf_alias_app_prev_4458__core.Appointment.patient_id == patient_id))
                ldb.execute(_rf_alias_app_prev_4458__core.delete(_rf_alias_app_prev_4458__core.Visit).where(_rf_alias_app_prev_4458__core.Visit.patient_id == patient_id))
                ldb.execute(_rf_alias_app_prev_4458__core.delete(_rf_alias_app_prev_4458__core.Patient).where(_rf_alias_app_prev_4458__core.Patient.id == patient_id))
                ldb.commit()
            with _rf_alias_app_prev_4458__core.LocalSessionLocal() as verify:
                return verify.get(_rf_alias_app_prev_4458__core.Patient, patient_id) is None
        except Exception as exc:
            try:
                with _rf_alias_app_prev_4458__core._state_lock:
                    _rf_alias_app_prev_4458__core._state['last_error'] = f'No se pudo purgar paciente {patient_id} de SQLite: {exc}'[:300]
            except Exception:
                pass
            return False
    _rf_alias_app_prev_4458__core.mirror_patient_to_local = _v4450_mirror_patient_to_local
    _rf_alias_app_prev_4458__core.mirror_delete_patient_local = _v4450_force_delete_patient_local
    _v4450_reconcile_lock = _rf_alias_app_prev_4458__core.threading.Lock()

    def _v4450_reconcile_recent_deleted_patients() -> dict:
        if not _v4450_reconcile_lock.acquire(blocking=False):
            return {'ok': True, 'busy': True, 'purged': 0}
        try:
            if _rf_alias_app_prev_4458__core.queue_count() > 0:
                return {'ok': True, 'skipped': 'offline_queue', 'purged': 0}
            if not _rf_alias_app_prev_4458__core.cloud_configured() or not _rf_alias_app_prev_4458__core.CloudSessionLocal or (not _rf_alias_app_prev_4458__core.check_cloud(force=False)):
                return {'ok': True, 'skipped': 'cloud_unavailable', 'purged': 0}
            ids = set()
            with _rf_alias_app_prev_4458__core.LocalSessionLocal() as ldb:
                rows = list(ldb.scalars(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Audit).where(_rf_alias_app_prev_4458__core.Audit.action.in_(('borrar_paciente', 'borrar_paciente_importado_confirmafy'))).order_by(_rf_alias_app_prev_4458__core.Audit.id.desc()).limit(180)))
                for row in rows:
                    match = _rf_alias_app_prev_4458__core.re.search('Paciente\\s+(\\d+)', str(row.detail or ''), flags=_rf_alias_app_prev_4458__core.re.I)
                    if match:
                        ids.add(int(match.group(1)))
            if not ids:
                return {'ok': True, 'purged': 0}
            with _rf_alias_app_prev_4458__core.CloudSessionLocal() as cdb:
                alive = {int(x) for x in cdb.scalars(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Patient.id).where(_rf_alias_app_prev_4458__core.Patient.id.in_(sorted(ids))))}
            purged = 0
            for pid in sorted(ids - alive):
                purged += int(_v4450_force_delete_patient_local(pid))
            return {'ok': True, 'purged': purged, 'checked': len(ids)}
        except Exception as exc:
            return {'ok': False, 'purged': 0, 'error': str(exc)[:220]}
        finally:
            _v4450_reconcile_lock.release()

    @app.post('/api/local-cache/reconcile-patients')
    def v4450_reconcile_patients(user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        return _v4450_reconcile_recent_deleted_patients()

    def _v4450_repair_worker():
        try:
            _rf_alias_app_prev_4458__core.time.sleep(1.5)
            _v4450_reconcile_recent_deleted_patients()
        except Exception:
            pass
    _rf_alias_app_prev_4458__core.threading.Thread(target=_v4450_repair_worker, daemon=True, name='rp-patient-cache-repair').start()

    @app.post('/api/historical/{hid}/activate-for-staged/{item_id}')
    def v4450_activate_historical_for_staged(hid: int, item_id: int, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        staged = db.get(_rf_alias_app_prev_4458__core.ConfirmafyAgendaItem, int(item_id))
        if staged is None:
            raise _rf_alias_app_prev_4458__core.HTTPException(404, 'La cita ya no está disponible')
        staged_phone = _rf_alias_app_prev_4458__core.normalize_lookup_phone(staged.celular)
        source_key = None
        try:
            with _rf_alias_app_prev_4458__core.LocalSessionLocal() as ldb:
                historical = ldb.get(_rf_alias_app_prev_4458__core.HistoricalPatient, int(hid))
                if historical is not None:
                    source_key = str(historical.source_key)
        except Exception:
            source_key = None
        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, 0, db, user)
            if owner_info.get('duplicate') and owner_info.get('patient'):
                owner_id = int(owner_info['patient']['id'])
                owner = db.get(_rf_alias_app_prev_4458__core.Patient, owner_id)
                if owner is not None:
                    if source_key:
                        try:
                            _rf_alias_app_prev_4458__core._historical_link_patient(source_key, owner_id)
                        except Exception:
                            pass
                    _v4450_mirror_patient_to_local(owner)
                    out = _rf_alias_app_prev_4458__core.p_dict(owner)
                    out.update({'created': False, 'reused_by_staged_phone': True})
                    return out
        result = _rf_alias_app_prev_4458__core.activate_historical_patient(int(hid), db, user)
        patient_id = int(result.get('id') or 0)
        patient = db.get(_rf_alias_app_prev_4458__core.Patient, patient_id) if patient_id else None
        if patient is None:
            return result
        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, int(patient.id), db, user)
            if owner_info.get('duplicate') and owner_info.get('patient'):
                target_id = int(owner_info['patient']['id'])
                if target_id != int(patient.id):
                    linked = _rf_alias_app_prev_4458__core.link_duplicate_patient(int(patient.id), target_id, db, user)
                    out = dict(linked.get('patient') or {})
                    out.update({'created': False, 'reused_by_staged_phone': True})
                    return out
            if _rf_alias_app_prev_4458__core.normalize_lookup_phone(patient.celular) != staged_phone:
                patient.celular = staged_phone
                _rf_alias_app_prev_4458__core.audit(db, user, 'vincular_celular_cita_historico', f'Paciente {patient.id} · cita staged {item_id}')
                db.commit()
                _v4450_mirror_patient_to_local(patient)
        out = _rf_alias_app_prev_4458__core.p_dict(patient)
        out.update({'created': bool(result.get('created')), 'historical': result.get('historical'), 'staged_phone_linked': bool(staged_phone)})
        return out
    V4450_PATIENT_CACHE_JS = "\n;(()=>{\n  if(window.__v4450PatientCacheIdentity)return;\n  window.__v4450PatientCacheIdentity=true;\n\n  const currentRows=rows=>(Array.isArray(rows)?rows:[]).filter(p=>!(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)));\n\n  // El buscador normal muestra fichas ACTUALES. El histórico sigue disponible\n  // en su filtro dedicado y en el flujo explícito de subsecuente de una cita.\n  const stableRenderPatientResults=renderPatientResults;\n  renderPatientResults=function(rows=[],title=''){\n    const keepHistorical=String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='historical' || String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='review';\n    return stableRenderPatientResults.call(this,keepHistorical?rows:currentRows(rows),title);\n  };\n\n  const stableGlobalResult=globalSearchResultHtml;\n  globalSearchResultHtml=function(p){\n    if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p))return '';\n    return stableGlobalResult.call(this,p);\n  };\n\n  function clearPatientCaches(id=0){\n    try{globalSearchCache=[]}catch(_e){}\n    try{if(Number(id||0)>0)agendaPatientById.delete(Number(id));else agendaPatientById.clear()}catch(_e){}\n    try{if(Number(id||0)>0&&Number(agendaPatientCache?.id||0)===Number(id))agendaPatientCache=null}catch(_e){}\n  }\n  window.__v4450ClearPatientCaches=clearPatientCaches;\n\n  async function reconcileLocalPatients(){\n    try{return await api('/api/local-cache/reconcile-patients',{method:'POST'})}catch(_e){return null}\n  }\n\n  // Borrar pasa por Papelera recuperable y luego limpia caches/UI. Así una ficha\n  // buena no se pierde de forma irreversible por un clic de limpieza.\n  deletePatient=async function(id,visitCount){\n    const extra=visitCount?` También se moverán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'} a la Papelera.`:'';\n    if(!confirmDeletion(`¿Mover este paciente a la Papelera?${extra}\\n\\nPodrás restaurarlo durante 7 días.`))return;\n    try{\n      await singleFlightMutation(`patient:safe-delete:${id}`,async()=>{\n        const result=await api('/api/safety/patients/'+Number(id),{method:'DELETE'});\n        clearPatientCaches(Number(id));\n        await reconcileLocalPatients();\n        closeModal();show('pacientes');\n        try{await searchPatients()}catch(_e){}\n        try{await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()])}catch(_e){}\n        const msg=result?.trash_id?'Paciente movido a Papelera. Puedes restaurarlo desde Actividad → Papelera.':'Paciente eliminado.';\n        if(typeof rpNotice==='function')rpNotice(msg);\n      },'Moviendo…');\n    }catch(e){alert(e.message||e)}\n  };\n\n  // Histórico elegido desde WhatsApp/staged: operación atómica en backend con\n  // el celular de la cita, para que dos históricos no creen dos pacientes.\n  useHistoricalForStaged=async function(itemId,hid,fecha){\n    try{\n      const p=await api(`/api/historical/${Number(hid)}/activate-for-staged/${Number(itemId)}`,{method:'POST'});\n      clearPatientCaches(Number(p?.id||0));\n      try{invalidateAttentionWeekCache()}catch(_e){}\n      await usePatientForStaged(Number(itemId),Number(p.id),fecha);\n    }catch(e){alert(e.message||e)}\n  };\n\n  // Después de cualquier edición desde atención, limpiar caches para que el\n  // nombre recién completado aparezca inmediatamente en ambos buscadores.\n  const stableSaveExistingAndAttend=window.v4449SaveExistingAndAttend;\n  if(typeof stableSaveExistingAndAttend==='function')window.v4449SaveExistingAndAttend=async function(patientId,fecha){\n    const out=await stableSaveExistingAndAttend.apply(this,arguments);\n    clearPatientCaches(Number(patientId||0));\n    return out;\n  };\n  const stableSavePatient=savePatient;\n  savePatient=async function(id,source){\n    const out=await stableSavePatient.apply(this,arguments);\n    clearPatientCaches(Number(id||0));\n    return out;\n  };\n  const stableSaveAndReturn=savePatientAndReturnToAttention;\n  savePatientAndReturnToAttention=async function(id){\n    const out=await stableSaveAndReturn.apply(this,arguments);\n    clearPatientCaches(Number(id||0));\n    return out;\n  };\n\n  // Reparación no bloqueante para instalaciones que ya traían fantasmas de\n  // versiones anteriores. Luego vuelve a consultar solo si hay una búsqueda visible.\n  setTimeout(async()=>{\n    const r=await reconcileLocalPatients();\n    if(!r?.purged)return;\n    clearPatientCaches();\n    try{const g=document.querySelector('#globalSearch');if(g&&String(g.value||'').trim().length>=2)globalSearchPatients(true)}catch(_e){}\n    try{const p=document.querySelector('#search');if(p&&String(p.value||'').trim().length>=2)searchPatients()}catch(_e){}\n  },1800);\n\n  window.__v4450PatientTest={currentRows,reconcileLocalPatients,clearPatientCaches};\n})();\n"
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4450_PATIENT_CACHE_JS

    class V4451VisitBatchPaymentIn(_rf_alias_app_prev_4458__core.VisitBatchIn):
        payment_method: str

    def _v4451_apply_payment_to_group(db, user, patient_id: int, fecha, method: str):
        method = _normalize_payment_method(method)
        sentinel = PAYMENT_SENTINELS[method]
        rows = db.execute(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.Visit, _rf_alias_app_prev_4458__core.BillingRecord).join(_rf_alias_app_prev_4458__core.BillingRecord, _rf_alias_app_prev_4458__core.BillingRecord.visit_id == _rf_alias_app_prev_4458__core.Visit.id).where(_rf_alias_app_prev_4458__core.Visit.patient_id == int(patient_id), _rf_alias_app_prev_4458__core.Visit.fecha == fecha, _rf_alias_app_prev_4458__core.BillingRecord.estado != 'EMITIDA').order_by(_rf_alias_app_prev_4458__core.Visit.id)).all()
        if not rows:
            raise _rf_alias_app_prev_4458__core.HTTPException(404, 'No se encontró la atención recién guardada para registrar su forma de pago.')
        visits = []
        visit_ids = set()
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)
            visit_ids.add(int(visit.id))
        offline = _rf_alias_app_prev_4458__core.is_offline_db(db)
        if offline and visit_ids:
            queued = list(db.scalars(_rf_alias_app_prev_4458__core.select(_rf_alias_app_prev_4458__core.OfflineQueue).where(_rf_alias_app_prev_4458__core.OfflineQueue.operation == 'visit.create', _rf_alias_app_prev_4458__core.OfflineQueue.local_entity_id.in_(sorted(visit_ids)))))
            for item in queued:
                try:
                    payload = _rf_alias_app_prev_4458__core.json.loads(item.payload or '{}')
                except Exception:
                    payload = {}
                payload['source_row'] = sentinel
                item.payload = _rf_alias_app_prev_4458__core.json.dumps(payload, ensure_ascii=False)
        _rf_alias_app_prev_4458__core.audit(db, user, 'registrar_forma_pago_atencion', f'Paciente {patient_id}, {fecha}: {method}')
        db.commit()
        if not offline:
            for visit in visits:
                try:
                    _rf_alias_app_prev_4458__core.mirror_visit_to_local(visit)
                except Exception:
                    pass
        return method
    _v4451_stable_sync_one_operation = _rf_alias_app_prev_4458__core.sync_one_operation

    def _v4451_sync_one_operation(q, ldb, cdb):
        result_id = _v4451_stable_sync_one_operation(q, ldb, cdb)
        if str(getattr(q, 'operation', '') or '') == 'visit.create' and result_id is not None:
            try:
                payload = _rf_alias_app_prev_4458__core.json.loads(getattr(q, 'payload', '') or '{}')
                source_row = int(payload.get('source_row') or 0)
            except Exception:
                source_row = 0
            if source_row in set(PAYMENT_SENTINELS.values()):
                visit = cdb.get(_rf_alias_app_prev_4458__core.Visit, int(result_id))
                if visit is not None:
                    visit.source_row = source_row
        return result_id
    _rf_alias_app_prev_4458__core.sync_one_operation = _v4451_sync_one_operation

    @app.post('/api/visits/batch-payment')
    def v4451_create_visit_batch_payment(data: V4451VisitBatchPaymentIn, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        method = _normalize_payment_method(data.payment_method)
        stable_data = _rf_alias_app_prev_4458__core.VisitBatchIn(patient_id=int(data.patient_id), fecha=data.fecha, tipo=data.tipo, services=data.services, observacion=data.observacion)
        result = _rf_alias_app_prev_4458__core.create_visit_batch(stable_data, db, user)
        _v4451_apply_payment_to_group(db, user, int(data.patient_id), data.fecha, method)
        if isinstance(result, dict):
            result = dict(result)
            result['payment_method'] = method
            result['sri_payment_code'] = SRI_PAYMENT_CODES[method]
        return result
    V4451_PAYMENT_ATTENTION_JS = '\n;(()=>{\n  if(window.__v4451PaymentSourceOfTruth)return;\n  window.__v4451PaymentSourceOfTruth=true;\n\n  let attentionPaymentMethod=\'\';\n\n  function paymentLabel(method){\n    return method===\'TRANSFERENCIA\'?\'Transferencia bancaria\':method===\'EFECTIVO\'?\'Efectivo\':\'\';\n  }\n\n  function renderAttentionPayment(){\n    const modal=document.querySelector(\'.attention-form-modal\');\n    if(!modal)return;\n    let box=modal.querySelector(\'#v4451AttentionPayment\');\n    if(!box){\n      box=document.createElement(\'div\');\n      box.id=\'v4451AttentionPayment\';\n      box.className=\'v4451-attention-payment\';\n      const obs=modal.querySelector(\'.attention-observation\');\n      if(obs)obs.insertAdjacentElement(\'beforebegin\',box);else modal.querySelector(\'.actions\')?.insertAdjacentElement(\'beforebegin\',box);\n    }\n    const selected=String(attentionPaymentMethod||\'\');\n    box.classList.toggle(\'required\',!selected);\n    box.innerHTML=`\n      <div class="v4451-pay-head">\n        <div><b>Forma de pago</b><small>Obligatorio · se usará después en la factura/SRI.</small></div>\n        <span>${selected?`✓ ${paymentLabel(selected)}`:\'Sin seleccionar\'}</span>\n      </div>\n      <div class="v4451-pay-options">\n        <button type="button" class="v4451-pay-option ${selected===\'EFECTIVO\'?\'selected\':\'\'}" onclick="v4451ChooseAttentionPayment(\'EFECTIVO\')"><span>💵</span><b>Efectivo</b><small>SRI 01</small></button>\n        <button type="button" class="v4451-pay-option ${selected===\'TRANSFERENCIA\'?\'selected\':\'\'}" onclick="v4451ChooseAttentionPayment(\'TRANSFERENCIA\')"><span>🏦</span><b>Transferencia bancaria</b><small>SRI 20</small></button>\n      </div>`;\n  }\n\n  window.v4451ChooseAttentionPayment=function(method){\n    const m=String(method||\'\').toUpperCase();\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(m))return;\n    attentionPaymentMethod=m;\n    renderAttentionPayment();\n  };\n\n  const stableAttentionFor=window.attentionFor;\n  if(typeof stableAttentionFor===\'function\')window.attentionFor=async function(id,draft=null){\n    attentionPaymentMethod=String(draft?.paymentMethod||\'\').toUpperCase();\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(attentionPaymentMethod))attentionPaymentMethod=\'\';\n    const out=await stableAttentionFor.apply(this,arguments);\n    renderAttentionPayment();\n    return out;\n  };\n\n  const stableSaveAttention=window.saveAttention;\n  if(typeof stableSaveAttention===\'function\')window.saveAttention=async function(id){\n    const method=String(attentionPaymentMethod||\'\').toUpperCase();\n    if(![\'EFECTIVO\',\'TRANSFERENCIA\'].includes(method)){\n      const box=document.querySelector(\'#v4451AttentionPayment\');\n      box?.classList.add(\'required\');\n      try{box?.scrollIntoView({behavior:\'smooth\',block:\'center\'})}catch(_e){}\n      alert(\'Selecciona la forma de pago antes de guardar la atención.\');\n      return;\n    }\n\n    const stableApi=window.api||api;\n    const intercept=async function(url,opt={}){\n      if(String(url)===\'/api/visits/batch\'){\n        let body={};\n        try{body=JSON.parse(opt?.body||\'{}\')}catch(_e){body={}}\n        body.payment_method=method;\n        return stableApi(\'/api/visits/batch-payment\',{...opt,body:JSON.stringify(body)});\n      }\n      return stableApi(url,opt);\n    };\n\n    // api es una función global mutable en esta aplicación. Se intercepta solo\n    // durante el guardado y únicamente cambia /api/visits/batch.\n    const previousApi=api;\n    try{\n      api=intercept;\n      return await stableSaveAttention.apply(this,arguments);\n    }finally{\n      api=previousApi;\n    }\n  };\n\n  window.__v4451PaymentTest={renderAttentionPayment,getMethod:()=>attentionPaymentMethod};\n})();\n'
    V4451_PAYMENT_ATTENTION_CSS = '\n.v4451-attention-payment{margin:12px 0 14px;padding:12px;border:1px solid #d8e4ef;border-radius:13px;background:#f8fbfe}\n.v4451-attention-payment.required{border-color:#dda944;background:#fff9ed;box-shadow:0 0 0 3px rgba(221,169,68,.10)}\n.v4451-pay-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:9px}\n.v4451-pay-head>div{display:flex;flex-direction:column;gap:2px}.v4451-pay-head b{font-size:10px;color:#254761}.v4451-pay-head small{font-size:8px;color:#75899b}.v4451-pay-head>span{font-size:8px;font-weight:900;color:#55728a}\n.v4451-pay-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.v4451-pay-option{min-height:54px;border:1px solid #ccd9e5!important;border-radius:11px!important;background:#fff!important;color:#3e5c74!important;display:grid!important;grid-template-columns:auto 1fr auto;align-items:center;gap:7px;text-align:left!important;padding:9px 11px!important;box-shadow:none!important}.v4451-pay-option>b{font-size:9px}.v4451-pay-option>small{font-size:8px;color:#7a8c9d}.v4451-pay-option.selected{border-color:#62af84!important;background:#eaf8f0!important;color:#22613d!important;box-shadow:0 0 0 2px rgba(61,143,91,.09)!important}.v4451-pay-option.selected>small{color:#397052}\n@media(max-width:720px){.v4451-pay-options{grid-template-columns:1fr}.v4451-pay-head{flex-direction:column}}\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4451_PAYMENT_ATTENTION_JS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4451_PAYMENT_ATTENTION_CSS

    class V4452QuickAppointmentIn(_rf_alias_app_prev_4458__core.BaseModel):
        nombre: str
        celular: str
        fecha: _date
        hora: str
        allow_same_week: bool = False

    def _v4452_quick_source_hash(nombre: str, celular: str, fecha, hora: str) -> str:
        clean_name = _rf_alias_app_prev_4458__core.normalize_lookup_name(nombre or 'PACIENTE')
        clean_phone = _rf_alias_app_prev_4458__core.normalize_lookup_phone(celular or '')
        seed = _rf_alias_app_prev_4458__core.uuid.uuid4().hex
        return 'pc:quick:' + _rf_alias_app_prev_4458__core.hashlib.sha1(f'{clean_name}|{clean_phone}|{fecha.isoformat()}|{hora}|{seed}'.encode('utf-8')).hexdigest()

    @app.post('/api/agenda/unlinked/guarded')
    def v4452_create_quick_unlinked_appointment(data: V4452QuickAppointmentIn, db=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.get_db), user=_rf_alias_app_prev_4458__core.Depends(_rf_alias_app_prev_4458__core.current_user)):
        name = ' '.join(str(data.nombre or '').split()).upper()
        phone = _rf_alias_app_prev_4458__core.re.sub('\\D', '', str(data.celular or ''))
        if len(name) < 3:
            raise _rf_alias_app_prev_4458__core.HTTPException(400, 'Escribe el nombre del paciente')
        if len(phone) < 8 or len(phone) > 15:
            raise _rf_alias_app_prev_4458__core.HTTPException(400, 'Escribe un celular válido')
        values = _rf_alias_app_prev_4458__core.normalize_appointment_payload(data)
        slot_conflicts = _rf_alias_app_prev_4458__core.appointment_conflicts(db, values['fecha'], values['hora'], 20)
        if slot_conflicts:
            raise _rf_alias_app_prev_4458__core.HTTPException(409, _rf_alias_app_prev_4458__core.occupied_message(values['fecha'], values['hora'], slot_conflicts))
        phone_identity = type('V4452PhoneIdentity', (), {'id': -4452, 'celular': phone})()
        conflict = _v4444_same_week_conflict(db, phone_identity, values['fecha'])
        if conflict and (not bool(data.allow_same_week)):
            return {'created': False, 'same_week_conflict': conflict}
        source_hash = _v4452_quick_source_hash(name, phone, values['fecha'], values['hora'])
        item = _rf_alias_app_prev_4458__core.ConfirmafyAgendaItem(nombre=name, celular=phone, fecha=values['fecha'], hora=values['hora'], duracion=20, source_hash=source_hash)
        db.add(item)
        db.flush()
        offline = _rf_alias_app_prev_4458__core.is_offline_db(db)
        if offline:
            _rf_alias_app_prev_4458__core.add_queue(db, 'confirmafy_staged.create', 'confirmafy_staged', {'nombre': item.nombre, 'celular': item.celular, 'fecha': item.fecha.isoformat(), 'hora': item.hora, 'source_hash': item.source_hash}, user.username, item.id)
        _rf_alias_app_prev_4458__core.audit(db, user, 'crear_cita_rapida_sin_ficha', f"{name} · {values['fecha']} {values['hora']}")
        db.commit()
        if not offline:
            try:
                db.refresh(item)
            except Exception:
                pass
            try:
                _rf_alias_app_prev_4458__core.mirror_confirmafy_agenda_local(item)
            except Exception:
                pass
            try:
                _rf_alias_app_prev_4458__core.schedule_whatsapp_for_contact(source_type='staged', source_id=item.id, name=item.nombre, phone=item.celular or '', fecha=item.fecha, hora=item.hora)
            except Exception:
                pass
        return {'created': True, 'staged': _rf_alias_app_prev_4458__core.confirmafy_agenda_dict(item), 'offline': bool(offline), 'unlinked': True}
    V4452_QUICK_APPOINTMENT_JS = '\n;(()=>{\n  if(window.__v4452QuickUnlinkedAppointment)return;\n  window.__v4452QuickUnlinkedAppointment=true;\n\n  const norm=v=>String(v||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\n  const esc2=v=>typeof esc===\'function\'?esc(String(v??\'\')):String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n\n  function newAppointmentModal(){\n    return [...document.querySelectorAll(\'#modal .modalbox,.modal .modalbox,.modalbox\')].find(box=>\n      [...box.querySelectorAll(\'h1,h2,h3\')].some(h=>norm(h.textContent)===\'nueva cita\')\n    )||null;\n  }\n\n  function parseSlotText(text){\n    const raw=String(text||\'\').replace(/\\s+/g,\' \').trim();\n    const dm=/(\\d{1,2})\\/(\\d{1,2})\\/(\\d{4})/.exec(raw);\n    const tm=/(\\d{1,2}):(\\d{2})\\s*(a\\.?\\s*m\\.?|p\\.?\\s*m\\.?|am|pm)?/i.exec(raw);\n    if(!dm||!tm)return null;\n    const dd=Number(dm[1]),mm=Number(dm[2]),yy=Number(dm[3]);\n    let hh=Number(tm[1]),mi=Number(tm[2]);\n    const ap=norm(tm[3]||\'\').replace(/\\./g,\'\').replace(/\\s/g,\'\');\n    if(ap===\'pm\'&&hh<12)hh+=12;\n    if(ap===\'am\'&&hh===12)hh=0;\n    if(!(dd>=1&&dd<=31&&mm>=1&&mm<=12&&hh>=0&&hh<=23&&mi>=0&&mi<=59))return null;\n    return {fecha:`${String(yy).padStart(4,\'0\')}-${String(mm).padStart(2,\'0\')}-${String(dd).padStart(2,\'0\')}`,hora:`${String(hh).padStart(2,\'0\')}:${String(mi).padStart(2,\'0\')}`};\n  }\n\n  function slotFromModal(box){\n    // El flujo estable guarda usando $(\'#agendaDate\') / $(\'#agendaTime\') a nivel\n    // documento. En algunas composiciones visuales esos inputs quedan fuera del\n    // .modalbox interno aunque pertenecen a la misma ventana Nueva cita.\n    const dateInput=document.querySelector(\'#agendaDate\')||box?.querySelector(\'input[type="date"]\');\n    const timeInput=document.querySelector(\'#agendaTime\')||box?.querySelector(\'input[type="time"]\');\n    const fecha=String(dateInput?.value||\'\').slice(0,10),hora=String(timeInput?.value||\'\').slice(0,5);\n    if(/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha)&&/^\\d{2}:\\d{2}$/.test(hora))return {fecha,hora};\n    const candidates=[...box.querySelectorAll(\'span,button,div\')]\n      .map(el=>String(el.textContent||\'\').trim())\n      .filter(t=>t.length>5&&t.length<90&&/\\d{1,2}\\/\\d{1,2}\\/\\d{4}/.test(t)&&/\\d{1,2}:\\d{2}/.test(t))\n      .sort((a,b)=>a.length-b.length);\n    for(const text of candidates){const parsed=parseSlotText(text);if(parsed)return parsed}\n    return parseSlotText(box?.textContent||\'\');\n  }\n\n  function fmtSlot(slot){\n    try{return `${typeof fmtDate===\'function\'?fmtDate(slot.fecha):slot.fecha} · ${typeof fmtTime===\'function\'?fmtTime(slot.hora):slot.hora}`}\n    catch(_e){return `${slot.fecha} · ${slot.hora}`}\n  }\n\n  window.v4452OpenQuickAppointment=function(){\n    const source=newAppointmentModal();\n    const remembered=window.__v4454SelectedAgendaSlot;\n    const slot=(remembered&&Date.now()-Number(remembered.ts||0)<300000?remembered:null)||slotFromModal(source);\n    if(!slot){alert(\'No pude identificar la fecha y hora seleccionadas. Cierra esta ventana y vuelve a tocar el horario.\');return}\n    openModal(`<div class="v4452-quick-modal"><div class="modal-form-heading"><h2>Crear cita nueva</h2><p>Reserva el horario solo con nombre y celular. La ficha del paciente se completará o vinculará cuando sea atendido.</p></div><div class="v4452-slot"><span>Horario seleccionado</span><b>${esc2(fmtSlot(slot))}</b></div><div class="v4452-fields"><label>Apellidos y nombres<input id="v4452QuickName" maxlength="220" autocomplete="off" placeholder="APELLIDOS Y NOMBRES" oninput="this.value=this.value.toUpperCase()"></label><label>Celular<input id="v4452QuickPhone" inputmode="numeric" maxlength="15" autocomplete="tel" placeholder="09XXXXXXXX" oninput="this.value=this.value.replace(/[^0-9]/g,\'\')"></label></div><div class="v4452-note">Esta acción <b>no crea una ficha de paciente</b>. La cita quedará como “sin ficha vinculada”.</div><div class="actions form-actions"><button class="cancel-btn" onclick="closeModal()">Cancelar</button><button id="v4452QuickSave" class="primary" onclick="v4452SaveQuickAppointment(\'${slot.fecha}\',\'${slot.hora}\',false)">Guardar cita</button></div></div>`);\n    setTimeout(()=>document.querySelector(\'#v4452QuickName\')?.focus(),30);\n  };\n\n  window.v4452SaveQuickAppointment=async function(fecha,hora,allowSameWeek=false){\n    const name=String(document.querySelector(\'#v4452QuickName\')?.value||\'\').trim().replace(/\\s+/g,\' \').toUpperCase();\n    const phone=String(document.querySelector(\'#v4452QuickPhone\')?.value||\'\').replace(/[^0-9]/g,\'\');\n    if(name.length<3){alert(\'Escribe el nombre del paciente.\');document.querySelector(\'#v4452QuickName\')?.focus();return}\n    if(phone.length<8||phone.length>15){alert(\'Escribe un celular válido.\');document.querySelector(\'#v4452QuickPhone\')?.focus();return}\n    const btn=document.querySelector(\'#v4452QuickSave\');if(btn){btn.disabled=true;btn.textContent=\'Guardando…\'}\n    try{\n      const result=await api(\'/api/agenda/unlinked/guarded\',{method:\'POST\',body:JSON.stringify({nombre:name,celular:phone,fecha,hora,allow_same_week:!!allowSameWeek})});\n      if(result?.same_week_conflict&&!allowSameWeek){\n        const c=result.same_week_conflict||{};\n        const when=`${typeof fmtDate===\'function\'?fmtDate(c.date):String(c.date||\'\')} · ${typeof fmtTime===\'function\'?fmtTime(c.time):String(c.time||\'\')}`;\n        const proceed=confirm(`Este paciente ya tiene una cita esta semana:\\n\\n${String(c.name||name)}\\n${when}\\n\\n¿Agendar de todas formas?`);\n        if(proceed)return v4452SaveQuickAppointment(fecha,hora,true);\n        return;\n      }\n      if(!result?.created)throw Error(\'No se pudo crear la cita.\');\n      try{invalidateAgendaSlotCache()}catch(_e){}\n      try{invalidateAttentionWeekCache()}catch(_e){}\n      closeModal();\n      try{agendaNativeAnchor=fecha}catch(_e){}\n      if(typeof loadAgenda===\'function\')await loadAgenda();\n      if(typeof rpNotice===\'function\')rpNotice(\'Cita creada sin ficha de paciente.\');\n    }catch(e){alert(e.message||e)}\n    finally{const b=document.querySelector(\'#v4452QuickSave\');if(b){b.disabled=false;b.textContent=\'Guardar cita\'}}\n  };\n\n  function decorate(){\n    const box=newAppointmentModal();if(!box)return;\n    const buttons=[...box.querySelectorAll(\'button\')];\n    const old=buttons.find(b=>norm(b.textContent).includes(\'nuevo paciente\'));\n    if(old&&!old.dataset.v4452Quick){\n      old.dataset.v4452Quick=\'1\';\n      old.textContent=\'＋ Crear cita nueva\';\n      old.removeAttribute(\'onclick\');\n      old.onclick=e=>{e?.preventDefault?.();e?.stopPropagation?.();window.v4452OpenQuickAppointment()};\n      old.title=\'Agendar solo con nombre y celular, sin crear ficha de paciente\';\n    }\n    const heading=[...box.querySelectorAll(\'.modal-form-heading p,p\')].find(p=>norm(p.textContent).includes(\'selecciona primero\'));\n    if(heading&&!heading.dataset.v4452Copy){heading.dataset.v4452Copy=\'1\';heading.textContent=\'Selecciona un paciente existente o crea una cita nueva solo con nombre y celular.\'}\n  }\n\n  const obs=new MutationObserver(()=>{setTimeout(decorate,0);setTimeout(decorate,80)});\n  const start=()=>{obs.observe(document.body,{childList:true,subtree:true});decorate()};\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',start,{once:true});else start();\n  document.addEventListener(\'click\',()=>setTimeout(decorate,20),true);\n\n  window.__v4452QuickTest={parseSlotText,slotFromModal,decorate};\n})();\n'
    V4452_QUICK_APPOINTMENT_CSS = '\n.v4452-quick-modal{width:min(600px,92vw);display:grid;gap:13px}.v4452-slot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;border:1px solid #cce0d3;border-radius:12px;background:#f1faf4}.v4452-slot span{font-size:8px;font-weight:900;color:#688176;text-transform:uppercase;letter-spacing:.04em}.v4452-slot b{font-size:11px;color:#285a3c}.v4452-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v4452-fields label{display:grid;gap:5px;font-size:9px;font-weight:900;color:#455f75}.v4452-fields input{width:100%;min-height:43px;border:1px solid #cad8e5;border-radius:10px;padding:9px 11px;font-size:11px;font-weight:800;box-sizing:border-box;background:#fff;color:#233e57}.v4452-fields input:focus{outline:0;border-color:#5d91c7;box-shadow:0 0 0 3px rgba(70,126,181,.10)}.v4452-note{padding:9px 11px;border-radius:10px;background:#f7f9fb;color:#65798b;font-size:8.5px;line-height:1.35}.v4452-note b{color:#415c72}@media(max-width:650px){.v4452-fields{grid-template-columns:1fr}.v4452-slot{align-items:flex-start;flex-direction:column}}\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4452_QUICK_APPOINTMENT_JS
    _rf_alias_app_prev_4458__core.V460_OVERLAY_CSS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_CSS or '') + '\n' + V4452_QUICK_APPOINTMENT_CSS
    V4454_SLOT_EVENT_JS = '\n;(()=>{\n  if(window.__v4454SlotEventCapture)return;\n  window.__v4454SlotEventCapture=true;\n\n  function normalizeSlot(fecha,hora){\n    const f=String(fecha||\'\').slice(0,10),h=String(hora||\'\').slice(0,5);\n    if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(f)||!/^\\d{2}:\\d{2}$/.test(h))return null;\n    return {fecha:f,hora:h,ts:Date.now()};\n  }\n  function remember(fecha,hora){\n    const slot=normalizeSlot(fecha,hora);\n    if(slot)window.__v4454SelectedAgendaSlot=slot;\n    return slot;\n  }\n  function installWrapper(){\n    const current=window.openAgendaSlotPicker;\n    if(typeof current!==\'function\'||current.__v4454Wrapped)return;\n    const wrapped=function(fecha,hora){remember(fecha,hora);return current.apply(this,arguments)};\n    wrapped.__v4454Wrapped=true;\n    wrapped.__v4454Original=current;\n    window.openAgendaSlotPicker=wrapped;\n  }\n\n  // Captura en fase capture, antes de que ejecute el onclick inline del horario.\n  document.addEventListener(\'click\',e=>{\n    const btn=e.target?.closest?.(\'[onclick*="openAgendaSlotPicker"]\');\n    if(!btn)return;\n    const raw=String(btn.getAttribute(\'onclick\')||\'\');\n    const m=/openAgendaSlotPicker\\(\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]\\s*,\\s*[\'"](\\d{2}:\\d{2})[\'"]\\s*\\)/.exec(raw);\n    if(m)remember(m[1],m[2]);\n  },true);\n\n  installWrapper();\n  setTimeout(installWrapper,0);\n  setTimeout(installWrapper,120);\n  setTimeout(installWrapper,500);\n  document.addEventListener(\'click\',()=>setTimeout(installWrapper,0),true);\n\n  window.__v4454SlotCaptureTest={normalizeSlot,remember,installWrapper,get:()=>window.__v4454SelectedAgendaSlot||null};\n})();\n'
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4454_SLOT_EVENT_JS
    _v4455_stable_normalize_patient_payload = _rf_alias_app_prev_4458__core.normalize_patient_payload

    def _v4455_normalize_patient_payload(data):
        target = data
        raw = getattr(data, 'fecha_nacimiento', None)
        if isinstance(raw, str) and raw.strip():
            try:
                normalized = _v4455_normalize_birth_date_text(raw)
            except ValueError as exc:
                raise _rf_alias_app_prev_4458__core.HTTPException(400, str(exc)) from exc
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
                raise _rf_alias_app_prev_4458__core.HTTPException(400, 'Fecha de nacimiento inválida. Usa dd/mm/aaaa.') from exc
            raise
    _rf_alias_app_prev_4458__core.normalize_patient_payload = _v4455_normalize_patient_payload
    V4455_READABLE_ERRORS_JS = "\n;(()=>{\n  if(window.__v4455ReadableErrors)return;\n  window.__v4455ReadableErrors=true;\n  const originalAlert=typeof window.alert==='function'?window.alert.bind(window):null;\n\n  function readable(value){\n    if(value==null)return 'Error inesperado.';\n    if(typeof value==='string'){\n      const t=value.trim();\n      return t&&t!=='[object Object]'?t:'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';\n    }\n    const detail=value?.detail;\n    if(Array.isArray(detail)){\n      const lines=detail.map(x=>{\n        if(typeof x==='string')return x;\n        if(x&&typeof x.msg==='string')return x.msg;\n        try{return JSON.stringify(x)}catch(_e){return String(x)}\n      }).filter(Boolean);\n      if(lines.length)return lines.join('\\n');\n    }\n    if(typeof detail==='string'&&detail.trim())return detail.trim();\n    if(detail&&typeof detail==='object'){\n      if(typeof detail.msg==='string')return detail.msg;\n      try{const s=JSON.stringify(detail);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}\n    }\n    if(typeof value?.message==='string'){\n      const m=value.message.trim();\n      if(m&&m!=='[object Object]')return m;\n      if(m==='[object Object]')return 'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';\n    }\n    try{const s=JSON.stringify(value);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}\n    return 'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';\n  }\n\n  if(originalAlert){\n    window.alert=function(message){return originalAlert(readable(message))};\n  }\n  window.__v4455ReadableErrorText=readable;\n})();\n"
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4455_READABLE_ERRORS_JS
    V4456_PATIENT_ERROR_JS = "\n;(()=>{\n  if(window.__v4456PatientErrorGuard)return;\n  window.__v4456PatientErrorGuard=true;\n  const FALLBACK='No se pudo guardar el paciente. Revisa los datos e inténtalo nuevamente.';\n  const labels={fecha_nacimiento:'Fecha de nacimiento',cedula:'Cédula o identificación',nombre:'Apellidos y nombres',celular:'Celular',correo:'Correo',lugar:'Lugar'};\n\n  function detailLine(item){\n    if(item==null)return '';\n    if(typeof item==='string')return item.trim();\n    if(typeof item!=='object')return String(item);\n    const loc=Array.isArray(item.loc)?item.loc:[];\n    const key=loc.length?String(loc[loc.length-1]||''):'';\n    let msg=typeof item.msg==='string'?item.msg.trim():'';\n    if(key==='fecha_nacimiento'&&/valid date|date or datetime|invalid character|date/i.test(msg))msg='Fecha inválida. Usa dd/mm/aaaa.';\n    const label=labels[key]||key.replaceAll('_',' ');\n    if(label&&msg)return `${label}: ${msg}`;\n    if(msg)return msg;\n    try{const s=JSON.stringify(item);return s==='{}'?'':s}catch(_e){return ''}\n  }\n\n  function structured(value){\n    if(value==null)return '';\n    if(Array.isArray(value))return value.map(detailLine).filter(Boolean).join('\\n');\n    if(typeof value==='object'){\n      if(Array.isArray(value.detail)){\n        const t=value.detail.map(detailLine).filter(Boolean).join('\\n');\n        if(t)return t;\n      }\n      if(typeof value.detail==='string'&&value.detail.trim())return value.detail.trim();\n      if(value.detail&&typeof value.detail==='object'){\n        const t=detailLine(value.detail);if(t)return t;\n      }\n      if(typeof value.message==='string'){\n        const m=value.message.trim();if(m&&m!=='[object Object]')return m;\n      }\n      try{const s=JSON.stringify(value);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}\n      return '';\n    }\n    const t=String(value).trim();return t&&t!=='[object Object]'?t:'';\n  }\n\n  function recentServerError(){\n    const x=window.__v4456LastHttpError;\n    if(!x||Date.now()-Number(x.ts||0)>10000)return '';\n    return structured(x.data);\n  }\n\n  function readable(value){\n    let t=structured(value);\n    if(!t||t==='[object Object]')t=recentServerError();\n    return t&&t!=='[object Object]'?t:FALLBACK;\n  }\n\n  if(typeof window.fetch==='function'&&!window.fetch.__v4456ErrorCapture){\n    const previousFetch=window.fetch.bind(window);\n    const wrapped=async function(...args){\n      const response=await previousFetch(...args);\n      if(response&&!response.ok){\n        try{\n          const data=await response.clone().json();\n          window.__v4456LastHttpError={data,ts:Date.now(),url:String(args[0]?.url||args[0]||'')};\n        }catch(_e){}\n      }\n      return response;\n    };\n    wrapped.__v4456ErrorCapture=true;\n    window.fetch=wrapped;\n  }\n\n  const previousNotice=typeof window.rpNotice==='function'?window.rpNotice.bind(window):null;\n  if(previousNotice){\n    window.rpNotice=function(message,title){return previousNotice(readable(message),title)};\n  }\n  const previousAlert=typeof window.alert==='function'?window.alert.bind(window):null;\n  if(previousAlert){\n    window.alert=function(message){return previousAlert(readable(message))};\n  }\n  window.__v4456ReadablePatientError=readable;\n})();\n"
    _rf_alias_app_prev_4458__core.V460_OVERLAY_JS = (_rf_alias_app_prev_4458__core.V460_OVERLAY_JS or '') + '\n' + V4456_PATIENT_ERROR_JS
    FEATURE_BOOT_OK = True
except Exception as exc:
    FEATURE_BOOT_ERROR = f'{type(exc).__name__}: {exc}'[:500]
    try:
        error_path = _rf_alias_app_prev_4458__core.Path(_rf_alias_app_prev_4458__core.DATA_DIR) / 'startup_feature_error_v4431.log'
        error_path.write_text(FEATURE_BOOT_ERROR + '\n\n' + traceback.format_exc(), encoding='utf-8')
    except Exception:
        pass
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=_rf_alias_app_prev_4458__core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_prev_4458 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_prev_4458, '__name__', 'app_prev_4458')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_prev_4458, 'APP_VERSION', globals()['APP_VERSION'])
if 'AgendaGuardedAppointmentIn' in globals(): setattr(_rf_snapshot_app_prev_4458, 'AgendaGuardedAppointmentIn', globals()['AgendaGuardedAppointmentIn'])
if 'BillingPaymentMethodIn' in globals(): setattr(_rf_snapshot_app_prev_4458, 'BillingPaymentMethodIn', globals()['BillingPaymentMethodIn'])
if 'FEATURE_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_prev_4458, 'FEATURE_BOOT_ERROR', globals()['FEATURE_BOOT_ERROR'])
if 'FEATURE_BOOT_OK' in globals(): setattr(_rf_snapshot_app_prev_4458, 'FEATURE_BOOT_OK', globals()['FEATURE_BOOT_OK'])
if 'PAYMENT_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'PAYMENT_CSS', globals()['PAYMENT_CSS'])
if 'PAYMENT_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'PAYMENT_JS', globals()['PAYMENT_JS'])
if 'PAYMENT_SENTINELS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'PAYMENT_SENTINELS', globals()['PAYMENT_SENTINELS'])
if 'SRI_PAYMENT_CODES' in globals(): setattr(_rf_snapshot_app_prev_4458, 'SRI_PAYMENT_CODES', globals()['SRI_PAYMENT_CODES'])
if 'V4443_UI_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4443_UI_CSS', globals()['V4443_UI_CSS'])
if 'V4443_UI_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4443_UI_JS', globals()['V4443_UI_JS'])
if 'V4444_WEEK_GUARD_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4444_WEEK_GUARD_CSS', globals()['V4444_WEEK_GUARD_CSS'])
if 'V4444_WEEK_GUARD_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4444_WEEK_GUARD_JS', globals()['V4444_WEEK_GUARD_JS'])
if 'V4445_STAGED_IDENTITY_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4445_STAGED_IDENTITY_CSS', globals()['V4445_STAGED_IDENTITY_CSS'])
if 'V4445_STAGED_IDENTITY_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4445_STAGED_IDENTITY_JS', globals()['V4445_STAGED_IDENTITY_JS'])
if 'V4446_PHONE_GUARD_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4446_PHONE_GUARD_CSS', globals()['V4446_PHONE_GUARD_CSS'])
if 'V4446_PHONE_GUARD_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4446_PHONE_GUARD_JS', globals()['V4446_PHONE_GUARD_JS'])
if 'V4449_AGENDA_FLOW_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4449_AGENDA_FLOW_CSS', globals()['V4449_AGENDA_FLOW_CSS'])
if 'V4449_AGENDA_FLOW_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4449_AGENDA_FLOW_JS', globals()['V4449_AGENDA_FLOW_JS'])
if 'V4450_PATIENT_CACHE_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4450_PATIENT_CACHE_JS', globals()['V4450_PATIENT_CACHE_JS'])
if 'V4451VisitBatchPaymentIn' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4451VisitBatchPaymentIn', globals()['V4451VisitBatchPaymentIn'])
if 'V4451_PAYMENT_ATTENTION_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4451_PAYMENT_ATTENTION_CSS', globals()['V4451_PAYMENT_ATTENTION_CSS'])
if 'V4451_PAYMENT_ATTENTION_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4451_PAYMENT_ATTENTION_JS', globals()['V4451_PAYMENT_ATTENTION_JS'])
if 'V4452QuickAppointmentIn' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4452QuickAppointmentIn', globals()['V4452QuickAppointmentIn'])
if 'V4452_QUICK_APPOINTMENT_CSS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4452_QUICK_APPOINTMENT_CSS', globals()['V4452_QUICK_APPOINTMENT_CSS'])
if 'V4452_QUICK_APPOINTMENT_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4452_QUICK_APPOINTMENT_JS', globals()['V4452_QUICK_APPOINTMENT_JS'])
if 'V4454_SLOT_EVENT_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4454_SLOT_EVENT_JS', globals()['V4454_SLOT_EVENT_JS'])
if 'V4455_READABLE_ERRORS_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4455_READABLE_ERRORS_JS', globals()['V4455_READABLE_ERRORS_JS'])
if 'V4456_PATIENT_ERROR_JS' in globals(): setattr(_rf_snapshot_app_prev_4458, 'V4456_PATIENT_ERROR_JS', globals()['V4456_PATIENT_ERROR_JS'])
if '_azur_payload_for_group_v4431' in globals(): setattr(_rf_snapshot_app_prev_4458, '_azur_payload_for_group_v4431', globals()['_azur_payload_for_group_v4431'])
if '_date' in globals(): setattr(_rf_snapshot_app_prev_4458, '_date', globals()['_date'])
if '_normalize_payment_method' in globals(): setattr(_rf_snapshot_app_prev_4458, '_normalize_payment_method', globals()['_normalize_payment_method'])
if '_overlay_base' in globals(): setattr(_rf_snapshot_app_prev_4458, '_overlay_base', globals()['_overlay_base'])
if '_overlay_version_marker' in globals(): setattr(_rf_snapshot_app_prev_4458, '_overlay_version_marker', globals()['_overlay_version_marker'])
if '_payment_from_visit' in globals(): setattr(_rf_snapshot_app_prev_4458, '_payment_from_visit', globals()['_payment_from_visit'])
if '_re' in globals(): setattr(_rf_snapshot_app_prev_4458, '_re', globals()['_re'])
if '_stable_azur_payload_for_group' in globals(): setattr(_rf_snapshot_app_prev_4458, '_stable_azur_payload_for_group', globals()['_stable_azur_payload_for_group'])
if '_v4443_base_wa_timeline_defs' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4443_base_wa_timeline_defs', globals()['_v4443_base_wa_timeline_defs'])
if '_v4443_planned_label' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4443_planned_label', globals()['_v4443_planned_label'])
if '_v4444_phone_variants' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4444_phone_variants', globals()['_v4444_phone_variants'])
if '_v4444_same_week_conflict' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4444_same_week_conflict', globals()['_v4444_same_week_conflict'])
if '_v4445_cloud_agenda_at' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4445_cloud_agenda_at', globals()['_v4445_cloud_agenda_at'])
if '_v4445_cloud_agenda_lock' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4445_cloud_agenda_lock', globals()['_v4445_cloud_agenda_lock'])
if '_v4445_sync_cloud_agenda_for_dates' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4445_sync_cloud_agenda_for_dates', globals()['_v4445_sync_cloud_agenda_for_dates'])
if '_v4449_cloud_bg_guard' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4449_cloud_bg_guard', globals()['_v4449_cloud_bg_guard'])
if '_v4449_cloud_bg_keys' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4449_cloud_bg_keys', globals()['_v4449_cloud_bg_keys'])
if '_v4449_cloud_sync_background' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4449_cloud_sync_background', globals()['_v4449_cloud_sync_background'])
if '_v4449_cloud_sync_blocking' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4449_cloud_sync_blocking', globals()['_v4449_cloud_sync_blocking'])
if '_v4449_timeline_defs' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4449_timeline_defs', globals()['_v4449_timeline_defs'])
if '_v4449_timeline_defs_stable' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4449_timeline_defs_stable', globals()['_v4449_timeline_defs_stable'])
if '_v4450_force_delete_patient_local' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_force_delete_patient_local', globals()['_v4450_force_delete_patient_local'])
if '_v4450_mirror_patient_to_local' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_mirror_patient_to_local', globals()['_v4450_mirror_patient_to_local'])
if '_v4450_reconcile_lock' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_reconcile_lock', globals()['_v4450_reconcile_lock'])
if '_v4450_reconcile_recent_deleted_patients' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_reconcile_recent_deleted_patients', globals()['_v4450_reconcile_recent_deleted_patients'])
if '_v4450_repair_worker' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_repair_worker', globals()['_v4450_repair_worker'])
if '_v4450_stable_mirror_delete_patient' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_stable_mirror_delete_patient', globals()['_v4450_stable_mirror_delete_patient'])
if '_v4450_stable_mirror_patient' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4450_stable_mirror_patient', globals()['_v4450_stable_mirror_patient'])
if '_v4451_apply_payment_to_group' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4451_apply_payment_to_group', globals()['_v4451_apply_payment_to_group'])
if '_v4451_stable_sync_one_operation' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4451_stable_sync_one_operation', globals()['_v4451_stable_sync_one_operation'])
if '_v4451_sync_one_operation' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4451_sync_one_operation', globals()['_v4451_sync_one_operation'])
if '_v4452_quick_source_hash' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4452_quick_source_hash', globals()['_v4452_quick_source_hash'])
if '_v4455_normalize_birth_date_text' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4455_normalize_birth_date_text', globals()['_v4455_normalize_birth_date_text'])
if '_v4455_normalize_patient_payload' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4455_normalize_patient_payload', globals()['_v4455_normalize_patient_payload'])
if '_v4455_stable_normalize_patient_payload' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v4455_stable_normalize_patient_payload', globals()['_v4455_stable_normalize_patient_payload'])
if '_v459_bad_root' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v459_bad_root', globals()['_v459_bad_root'])
if '_v459_base' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v459_base', globals()['_v459_base'])
if '_v459_good_root' in globals(): setattr(_rf_snapshot_app_prev_4458, '_v459_good_root', globals()['_v459_good_root'])
if '_wa_timeline_defs_v4443' in globals(): setattr(_rf_snapshot_app_prev_4458, '_wa_timeline_defs_v4443', globals()['_wa_timeline_defs_v4443'])
if 'agenda_create_guarded_v4444' in globals(): setattr(_rf_snapshot_app_prev_4458, 'agenda_create_guarded_v4444', globals()['agenda_create_guarded_v4444'])
if 'agenda_week_conflict_v4444' in globals(): setattr(_rf_snapshot_app_prev_4458, 'agenda_week_conflict_v4444', globals()['agenda_week_conflict_v4444'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_prev_4458, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_prev_4458, 'app', globals()['app'])
if 'billing_payment_methods' in globals(): setattr(_rf_snapshot_app_prev_4458, 'billing_payment_methods', globals()['billing_payment_methods'])
if '_rf_alias_app_prev_4458__core' in globals(): setattr(_rf_snapshot_app_prev_4458, 'core', globals()['_rf_alias_app_prev_4458__core'])
if 'error_path' in globals(): setattr(_rf_snapshot_app_prev_4458, 'error_path', globals()['error_path'])
if 'exc' in globals(): setattr(_rf_snapshot_app_prev_4458, 'exc', globals()['exc'])
if 'set_billing_payment_method' in globals(): setattr(_rf_snapshot_app_prev_4458, 'set_billing_payment_method', globals()['set_billing_payment_method'])
if 'startup_guard_status' in globals(): setattr(_rf_snapshot_app_prev_4458, 'startup_guard_status', globals()['startup_guard_status'])
if 'traceback' in globals(): setattr(_rf_snapshot_app_prev_4458, 'traceback', globals()['traceback'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_prev_4458, 'uvicorn', globals()['uvicorn'])
if 'v4445_cloud_agenda_catchup' in globals(): setattr(_rf_snapshot_app_prev_4458, 'v4445_cloud_agenda_catchup', globals()['v4445_cloud_agenda_catchup'])
if 'v4446_phone_owner' in globals(): setattr(_rf_snapshot_app_prev_4458, 'v4446_phone_owner', globals()['v4446_phone_owner'])
if 'v4450_activate_historical_for_staged' in globals(): setattr(_rf_snapshot_app_prev_4458, 'v4450_activate_historical_for_staged', globals()['v4450_activate_historical_for_staged'])
if 'v4450_reconcile_patients' in globals(): setattr(_rf_snapshot_app_prev_4458, 'v4450_reconcile_patients', globals()['v4450_reconcile_patients'])
if 'v4451_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_prev_4458, 'v4451_create_visit_batch_payment', globals()['v4451_create_visit_batch_payment'])
if 'v4452_create_quick_unlinked_appointment' in globals(): setattr(_rf_snapshot_app_prev_4458, 'v4452_create_quick_unlinked_appointment', globals()['v4452_create_quick_unlinked_appointment'])
_rf_layers['app_prev_4458'] = _rf_snapshot_app_prev_4458

# ---- app_patch_4459 ----
from datetime import date as _date
import traceback as _traceback
_rf_alias_app_patch_4459__previous = _rf_layers['app_prev_4458']
core = _rf_alias_app_patch_4459__previous.core
app = _rf_alias_app_patch_4459__previous.app
APP_VERSION = '4.4.59'
_rf_alias_app_patch_4459__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
NON_BILLABLE_STATE = 'NO_FACTURABLE'
NON_BILLABLE_REASON = 'Paciente sin cédula/identificación'
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''

class BillingNonBillableIn(core.BaseModel):
    patient_id: int
    fecha: _date

def _state(value):
    return str(value or '').strip().upper()

def _clear(record):
    record.approved_at = None
    record.numero_factura = None
    record.emitted_at = None
try:
    _stable_sync = core.sync_one_operation

    def _sync(q, ldb, cdb):
        if q.operation not in {'billing.nonbillable', 'billing.restore'}:
            return _stable_sync(q, ldb, cdb)
        old = cdb.get(core.SyncOperation, q.token)
        if old:
            return old.result_id
        payload = core.json.loads(q.payload or '{}')
        local_visit_id = int(payload['visit_id'])
        visit_id = core.resolve_cloud_id(ldb, 'visit', local_visit_id)
        b = cdb.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id == visit_id))
        if not b:
            b = core.BillingRecord(visit_id=visit_id, estado='PENDIENTE')
            cdb.add(b)
            cdb.flush()
        if _state(b.estado) == 'EMITIDA':
            raise RuntimeError('Una factura emitida no puede cambiar a No facturable')
        if q.operation == 'billing.nonbillable':
            b.estado = NON_BILLABLE_STATE
        elif _state(b.estado) == NON_BILLABLE_STATE:
            b.estado = 'PENDIENTE'
        _clear(b)
        core.audit(cdb, q.username, 'sincronizar_no_facturable', f'Atención {visit_id}: {b.estado}')
        cdb.add(core.SyncOperation(token=q.token, operation=q.operation, result_id=b.id))
        return b.id
    core.sync_one_operation = _sync

    def _change(data, target, db, user):
        pid, fecha = (int(data.patient_id), data.fecha)
        patient = db.get(core.Patient, pid)
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        if target == NON_BILLABLE_STATE and str(getattr(patient, 'cedula', '') or '').strip():
            raise core.HTTPException(409, 'Esta opción es solo para pacientes sin cédula/identificación.')
        rows = core.billing_group_records(db, pid, fecha)
        if not rows:
            raise core.HTTPException(409, 'Esta factura ya fue emitida o ya no está disponible.')
        offline = bool(core.is_offline_db(db))
        touched = []
        for b, v in rows:
            before = _state(b.estado)
            if target == NON_BILLABLE_STATE:
                if before not in {'PENDIENTE', 'APROBADA', NON_BILLABLE_STATE}:
                    continue
                b.estado = NON_BILLABLE_STATE
                op = 'billing.nonbillable'
            else:
                if before != NON_BILLABLE_STATE:
                    continue
                b.estado = 'PENDIENTE'
                op = 'billing.restore'
            _clear(b)
            touched.append(b)
            if offline and before != _state(b.estado):
                core.add_queue(db, op, 'billing', {'visit_id': int(v.id)}, user.username, b.id)
        if not touched:
            raise core.HTTPException(409, 'La ficha ya no está en un estado que pueda modificarse.')
        core.audit(db, user, 'marcar_no_facturable' if target == NON_BILLABLE_STATE else 'restaurar_factura_pendiente', f'Paciente {pid}, {fecha}: {target}')
        db.commit()
        if not offline:
            for b in touched:
                try:
                    core.mirror_billing_to_local(b)
                except Exception:
                    pass
        return {'ok': True, 'state': target, 'patient_id': pid, 'fecha': fecha.isoformat(), 'reason': NON_BILLABLE_REASON if target == NON_BILLABLE_STATE else None, 'offline': offline}

    @app.post('/api/billing/non-billable')
    def mark_non_billable(data: BillingNonBillableIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        return _change(data, NON_BILLABLE_STATE, db, user)

    @app.post('/api/billing/non-billable/restore')
    def restore_non_billable(data: BillingNonBillableIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        return _change(data, 'PENDIENTE', db, user)

    @app.get('/api/billing/non-billable')
    def list_non_billable(db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        rows = db.execute(core.select(core.BillingRecord, core.Visit, core.Patient).join(core.Visit, core.BillingRecord.visit_id == core.Visit.id).join(core.Patient, core.Visit.patient_id == core.Patient.id).where(core.Visit.fecha >= core.BILLING_QUEUE_START_DATE, core.BillingRecord.estado == NON_BILLABLE_STATE).order_by(core.Visit.fecha.desc(), core.Visit.id.desc())).all()
        groups = {}
        for b, v, p in rows:
            key = (int(p.id), v.fecha)
            g = groups.setdefault(key, {'patient': core.p_dict(p), 'fecha': v.fecha.isoformat(), 'reason': NON_BILLABLE_REASON, 'items': [], 'total': 0.0})
            g['items'].append({'billing': core.billing_dict(b), 'visit': core.v_dict(v), 'patient': core.p_dict(p)})
            try:
                g['total'] += float(v.valor or 0)
            except Exception:
                pass
        out = list(groups.values())
        for g in out:
            g['total'] = round(g['total'], 2)
        return {'groups': out, 'count': len(out)}
    CSS = '\n#facturacion .billing-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}\n#facturacion .v4459-tab.active{border-color:#c5965f!important;background:#fff6ea!important;color:#7a542a!important}\n#facturacion .v4459-mark{border-color:#e2c7a5!important;background:#fff8ee!important;color:#79552c!important}\n#facturacion .v4459-status{background:#fff1df!important;color:#8a5b25!important}\n#facturacion .v4459-reason{margin:9px 0;padding:9px 11px;border:1px solid #ead4b8;border-radius:10px;background:#fff8ef;color:#76542d;font-size:11px;font-weight:800}\n#facturacion .v4459-empty{padding:26px 18px;border:1px dashed #d5dee8;border-radius:13px;text-align:center;color:#6d8197}\n#facturacion .v4459-restore{border-color:#bdd4c5!important;background:#eef9f1!important;color:#2f6842!important}\n@media(max-width:760px){#facturacion .billing-summary{grid-template-columns:1fr!important}}\n'
    JS = '\n;(()=>{\nif(window.__v4459)return;window.__v4459=true;let archive=false,cache=[],timer=0;\nconst n=v=>String(v||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\nconst e=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\nconst fd=v=>{try{return fmtDate(v)}catch(_){return String(v||\'\')}};const cash=v=>{try{return money(Number(v||0))}catch(_){return `$${Number(v||0).toFixed(2)}`}};\nfunction id(card){const p=Number(card?.dataset?.patientId||0),f=String(card?.dataset?.fecha||\'\').slice(0,10);if(p&&/^\\d{4}-\\d{2}-\\d{2}$/.test(f))return[p,f];for(const x of [...(card?.querySelectorAll?.(\'[onclick]\')||[])]){const m=/\\(\\s*(\\d+)\\s*,\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]/.exec(String(x.getAttribute(\'onclick\')||\'\'));if(m)return[Number(m[1]),m[2]]}return null}\nfunction noid(card){return n(card?.querySelector?.(\'.billing-meta\')?.textContent).includes(\'sin cedula\')}\nfunction tab(){const s=document.querySelector(\'#billingSummary\');if(!s)return;let b=document.getElementById(\'v4459Tab\');if(!b){b=document.createElement(\'button\');b.id=\'v4459Tab\';b.className=\'v4459-tab\';b.innerHTML=\'<span>No facturables</span><b id="v4459Count">0</b>\';b.onclick=open;s.appendChild(b)}[...s.querySelectorAll(\'button\')].forEach(x=>{if(x===b)x.classList.toggle(\'active\',archive);else if(archive)x.classList.remove(\'active\')});return b}\nasync function count(){try{const d=await api(\'/api/billing/non-billable\');cache=d.groups||[];tab();const c=document.getElementById(\'v4459Count\');if(c)c.textContent=String(d.count||0);return d}catch(_){return null}}\nfunction decorate(){if(archive)return;document.querySelectorAll(\'#billingList .billing-card\').forEach(card=>{if(card.classList.contains(\'emitida\')||!noid(card))return;const k=id(card),h=card.querySelector(\'.billing-actions\');if(!k||!h||h.querySelector(\'.v4459-mark\'))return;const b=document.createElement(\'button\');b.className=\'v4459-mark\';b.textContent=\'🚫 No se puede facturar\';b.onclick=()=>mark(...k);h.prepend(b)})}\nasync function mark(pid,fecha){if(!confirm(\'¿Marcar como No facturable?\\n\\nSaldrá de Por emitir y de los recordatorios. La atención no se borrará.\'))return;try{await api(\'/api/billing/non-billable\',{method:\'POST\',body:JSON.stringify({patient_id:pid,fecha})});archive=false;await window.loadBilling?.();await count();refresh()}catch(x){alert(x.message||\'No se pudo marcar.\')}}\nasync function restore(pid,fecha){if(!confirm(\'¿Volver esta ficha a Por emitir?\'))return;try{await api(\'/api/billing/non-billable/restore\',{method:\'POST\',body:JSON.stringify({patient_id:pid,fecha})});await open();refresh()}catch(x){alert(x.message||\'No se pudo restaurar.\')}}\nfunction refresh(){for(const k of [\'loadPendingSummary\',\'refreshPendingSummary\',\'loadHome\',\'refreshHome\'])try{if(typeof window[k]===\'function\')Promise.resolve(window[k]()).catch(()=>{})}catch(_){}}\nfunction services(g){try{return billingServicesHtml({items:g.items||[],patient:g.patient,fecha:g.fecha})}catch(_){return(g.items||[]).map(x=>`<div class="billing-line"><span>${e(x.visit?.tipo||\'Atención\')}</span><strong>${cash(x.visit?.valor)}</strong></div>`).join(\'\')}}\nfunction render(){const list=document.querySelector(\'#billingList\');if(!list)return;archive=true;tab();if(!cache.length){list.innerHTML=\'<div class="v4459-empty">No hay fichas marcadas como No facturables.</div>\';return}list.innerHTML=cache.map(g=>{const p=g.patient||{},f=String(g.fecha||\'\').slice(0,10);return`<article class="billing-card pendiente" data-patient-id="${p.id}" data-fecha="${e(f)}"><div class="billing-card-head"><div><div class="billing-patient-name">${e(p.nombre||\'Paciente\')}</div><div class="billing-meta"><span><b>Cédula:</b> ${e(p.cedula||\'Sin cédula\')}</span><span><b>Fecha:</b> ${fd(f)}</span></div></div><span class="billing-status v4459-status">NO FACTURABLE</span></div><div class="v4459-reason">Motivo: Paciente sin cédula/identificación</div><div class="billing-lines">${services(g)}</div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${cash(g.total)}</strong></div><div class="billing-actions"><button class="v4459-restore">↩ Volver a pendientes</button></div></div></article>`}).join(\'\');list.querySelectorAll(\'.billing-card\').forEach(c=>{const k=id(c);if(k)c.querySelector(\'.v4459-restore\').onclick=()=>restore(...k)})}\nasync function open(){archive=true;const s=document.querySelector(\'#bEstado\');if(s)s.value=\'PENDIENTE\';const d=await count();if(d)render()}\nfunction later(){clearTimeout(timer);timer=setTimeout(()=>{tab();decorate()},30)}\nconst old=window.loadBilling;if(typeof old===\'function\'){window.loadBilling=async function(){archive=false;const r=await old.apply(this,arguments);tab();await count();decorate();return r}}\nconst oldSet=window.setBillingStatus;if(typeof oldSet===\'function\'){window.setBillingStatus=async function(){archive=false;const r=await oldSet.apply(this,arguments);tab();await count();decorate();return r}}\nconst start=()=>{tab();count().finally(later);const l=document.querySelector(\'#billingList\');if(l)new MutationObserver(later).observe(l,{childList:true})};\nif(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',start,{once:true});else start();\n})();\n'
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or '') + '\n' + CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or '') + '\n' + JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        _rf_alias_app_patch_4459__previous.FEATURE_BOOT_ERROR = (str(getattr(_rf_alias_app_patch_4459__previous, 'FEATURE_BOOT_ERROR', '') or '') + ' | v4.4.59: ' + PATCH_BOOT_ERROR).strip(' |')[:1200]
    except Exception:
        pass
    try:
        core.logging.getLogger(__name__).error('v4.4.59 patch failed: %s\n%s', PATCH_BOOT_ERROR, _traceback.format_exc())
    except Exception:
        pass

@app.get('/api/v4459/non-billable-health')
def v4459_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'schema_migration': False, 'attention_changed': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4459 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4459, '__name__', 'app_patch_4459')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4459, 'APP_VERSION', globals()['APP_VERSION'])
if 'BillingNonBillableIn' in globals(): setattr(_rf_snapshot_app_patch_4459, 'BillingNonBillableIn', globals()['BillingNonBillableIn'])
if 'CSS' in globals(): setattr(_rf_snapshot_app_patch_4459, 'CSS', globals()['CSS'])
if 'JS' in globals(): setattr(_rf_snapshot_app_patch_4459, 'JS', globals()['JS'])
if 'NON_BILLABLE_REASON' in globals(): setattr(_rf_snapshot_app_patch_4459, 'NON_BILLABLE_REASON', globals()['NON_BILLABLE_REASON'])
if 'NON_BILLABLE_STATE' in globals(): setattr(_rf_snapshot_app_patch_4459, 'NON_BILLABLE_STATE', globals()['NON_BILLABLE_STATE'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4459, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4459, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_change' in globals(): setattr(_rf_snapshot_app_patch_4459, '_change', globals()['_change'])
if '_clear' in globals(): setattr(_rf_snapshot_app_patch_4459, '_clear', globals()['_clear'])
if '_date' in globals(): setattr(_rf_snapshot_app_patch_4459, '_date', globals()['_date'])
if '_stable_sync' in globals(): setattr(_rf_snapshot_app_patch_4459, '_stable_sync', globals()['_stable_sync'])
if '_state' in globals(): setattr(_rf_snapshot_app_patch_4459, '_state', globals()['_state'])
if '_sync' in globals(): setattr(_rf_snapshot_app_patch_4459, '_sync', globals()['_sync'])
if '_traceback' in globals(): setattr(_rf_snapshot_app_patch_4459, '_traceback', globals()['_traceback'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4459, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4459, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4459, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4459, 'exc', globals()['exc'])
if 'list_non_billable' in globals(): setattr(_rf_snapshot_app_patch_4459, 'list_non_billable', globals()['list_non_billable'])
if 'mark_non_billable' in globals(): setattr(_rf_snapshot_app_patch_4459, 'mark_non_billable', globals()['mark_non_billable'])
if '_rf_alias_app_patch_4459__previous' in globals(): setattr(_rf_snapshot_app_patch_4459, 'previous', globals()['_rf_alias_app_patch_4459__previous'])
if 'restore_non_billable' in globals(): setattr(_rf_snapshot_app_patch_4459, 'restore_non_billable', globals()['restore_non_billable'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4459, 'uvicorn', globals()['uvicorn'])
if 'v4459_health' in globals(): setattr(_rf_snapshot_app_patch_4459, 'v4459_health', globals()['v4459_health'])
_rf_layers['app_patch_4459'] = _rf_snapshot_app_patch_4459

# ---- app_patch_4461 ----
import os
_rf_alias_app_patch_4461__previous = _rf_layers['app_patch_4459']
core = _rf_alias_app_patch_4461__previous.core
app = _rf_alias_app_patch_4461__previous.app
APP_VERSION = '4.4.61'
_rf_alias_app_patch_4461__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4461__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _print_receipt_windows_v4461(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, Image, StringFormat, StringAlignment, RectangleF, Color
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 600)
        doc.DefaultPageSettings.Margins = Margins(7, 7, 7, 7)
        fonts = []
        image_holder = {'img': None}

        def font(size, bold=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_title = font(11, True)
        f_label = font(7.4, True)
        f_text = font(8.4, True)
        f_name = font(9.3, True)
        f_turn = font(11, True)
        f_check = font(6.7, True)
        pen = Pen(Color.Black, 1.0)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            y = 0.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            logo_box = 46.0
            if os.path.exists(logo_path):
                try:
                    image_holder['img'] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder['img'], 0.0, 0.0, logo_box, logo_box)
                except Exception:
                    image_holder['img'] = None
            title_x = 49.0
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(title_x, 4.0, max(20.0, width - title_x), 42.0), center)
            y = 49.0
            g.DrawLine(pen, 0.0, y, width, y)

            def row(label, value, value_font=None, dotted=False):
                nonlocal y
                y += 7.0
                g.DrawString(str(label), f_label, Brushes.Black, 0.0, y)
                g.DrawString(str(value or ''), value_font or f_text, Brushes.Black, 86.0, y - 1.0)
                y += 18.0
                g.DrawLine(pen, 0.0, y, width, y)
            row('Fecha:', payload.fecha, f_text)
            y += 7.0
            g.DrawString('Nombre', f_label, Brushes.Black, RectangleF(0.0, y, width, 14.0), center)
            y += 13.0
            name = str(payload.nombre or 'SIN NOMBRE').upper()
            name_fmt = StringFormat()
            name_fmt.Alignment = StringAlignment.Center
            name_size = g.MeasureString(name, f_name, int(width))
            g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, max(24.0, float(name_size.Height) + 3.0)), name_fmt)
            y += max(22.0, float(name_size.Height) + 5.0)
            g.DrawLine(pen, 0.0, y, width, y)
            if payload.is_new and payload.fecha_nacimiento:
                row('Nacimiento:', payload.fecha_nacimiento, f_text)
            if show_blood_pressure:
                y += 7.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, 0.0, y + 5.0)
                g.DrawRectangle(pen, 105.0, y, 52.0, 22.0)
                y += 29.0
                g.DrawLine(pen, 0.0, y, width, y)
            row('Teléfono:', payload.celular or 'Sin registrar', f_text)
            if payload.turno:
                row('Turno:', str(payload.turno), f_turn)
            y += 9.0
            box = 15.0
            left_x = 10.0
            right_label = 'SUBSECUENTE'
            right_label_w = float(g.MeasureString(right_label, f_check).Width)
            right_group_w = box + 4.0 + right_label_w
            right_x = max(width / 2.0 - 2.0, width - right_group_w - 2.0)
            groups = ((left_x, 'PRIMERO', bool(payload.is_new)), (right_x, right_label, not bool(payload.is_new)))
            for x, label, checked in groups:
                g.DrawRectangle(pen, x, y, box, box)
                if checked:
                    g.DrawString('X', f_text, Brushes.Black, x + 2.0, y - 1.5)
                label_x = x + box + 4.0
                label_w = max(1.0, width - label_x - 1.0)
                g.DrawString(label, f_check, Brushes.Black, RectangleF(label_x, y + 1.0, label_w, 16.0))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            try:
                pen.Dispose()
            except Exception:
                pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4461
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.61 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4461/receipt-health')
def v4461_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'schema_migration': False, 'receipt_only': True, 'paper_width_mm': 80}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4461 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4461, '__name__', 'app_patch_4461')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4461, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4461, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4461, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_print_receipt_windows_v4461' in globals(): setattr(_rf_snapshot_app_patch_4461, '_print_receipt_windows_v4461', globals()['_print_receipt_windows_v4461'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4461, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4461, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4461, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4461, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4461, 'os', globals()['os'])
if '_rf_alias_app_patch_4461__previous' in globals(): setattr(_rf_snapshot_app_patch_4461, 'previous', globals()['_rf_alias_app_patch_4461__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4461, 'uvicorn', globals()['uvicorn'])
if 'v4461_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4461, 'v4461_receipt_health', globals()['v4461_receipt_health'])
_rf_layers['app_patch_4461'] = _rf_snapshot_app_patch_4461

# ---- app_patch_4462 ----
import os
_rf_alias_app_patch_4462__previous = _rf_layers['app_patch_4461']
core = _rf_alias_app_patch_4462__previous.core
app = _rf_alias_app_patch_4462__previous.app
APP_VERSION = '4.4.62'
_rf_alias_app_patch_4462__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4462__previous.previous.APP_VERSION = APP_VERSION
    _rf_alias_app_patch_4462__previous.previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _print_receipt_windows_v4462(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, Image, StringFormat, StringAlignment, RectangleF, Color
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 600)
        doc.DefaultPageSettings.Margins = Margins(7, 7, 7, 7)
        fonts = []
        image_holder = {'img': None}

        def font(size, bold=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_title = font(11, True)
        f_label = font(7.4, True)
        f_text = font(8.4, True)
        f_name = font(9.3, True)
        f_turn = font(11, True)
        f_check = font(6.7, True)
        pen = Pen(Color.Black, 1.0)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            y = 0.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            logo_box = 46.0
            if os.path.exists(logo_path):
                try:
                    image_holder['img'] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder['img'], 0.0, 0.0, logo_box, logo_box)
                except Exception:
                    image_holder['img'] = None
            title_x = 49.0
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(title_x, 4.0, max(20.0, width - title_x), 42.0), center)
            y = 49.0
            g.DrawLine(pen, 0.0, y, width, y)

            def row(label, value, value_font=None, dotted=False):
                nonlocal y
                y += 7.0
                g.DrawString(str(label), f_label, Brushes.Black, 0.0, y)
                g.DrawString(str(value or ''), value_font or f_text, Brushes.Black, 86.0, y - 1.0)
                y += 18.0
                g.DrawLine(pen, 0.0, y, width, y)
            row('Fecha:', payload.fecha, f_text)
            y += 7.0
            g.DrawString('Nombre', f_label, Brushes.Black, RectangleF(0.0, y, width, 14.0), center)
            y += 13.0
            name = str(payload.nombre or 'SIN NOMBRE').upper()
            name_fmt = StringFormat()
            name_fmt.Alignment = StringAlignment.Center
            name_size = g.MeasureString(name, f_name, int(width))
            g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, max(24.0, float(name_size.Height) + 3.0)), name_fmt)
            y += max(22.0, float(name_size.Height) + 5.0)
            g.DrawLine(pen, 0.0, y, width, y)
            if payload.is_new and payload.fecha_nacimiento:
                row('Nacimiento:', payload.fecha_nacimiento, f_text)
            if show_blood_pressure:
                y += 7.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, 0.0, y + 5.0)
                g.DrawRectangle(pen, 105.0, y, 52.0, 22.0)
                y += 29.0
                g.DrawLine(pen, 0.0, y, width, y)
            row('Teléfono:', payload.celular or 'Sin registrar', f_text)
            if payload.turno:
                row('Turno:', str(payload.turno), f_turn)
            y += 9.0
            box = 15.0
            gap = 4.0
            label_height = 16.0
            options = (('PRIMERO', bool(payload.is_new), width * 0.25), ('SUBSECUENTE', not bool(payload.is_new), width * 0.75))
            for label, checked, half_center in options:
                label_w = float(g.MeasureString(label, f_check).Width)
                group_w = box + gap + label_w
                x = half_center - group_w / 2.0
                x = max(1.0, min(x, width - group_w - 1.0))
                g.DrawRectangle(pen, x, y, box, box)
                if checked:
                    g.DrawString('X', f_text, Brushes.Black, x + 2.0, y - 1.5)
                g.DrawString(label, f_check, Brushes.Black, RectangleF(x + box + gap, y + 1.0, label_w + 3.0, label_height))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            try:
                pen.Dispose()
            except Exception:
                pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4462
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.62 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4462/receipt-health')
def v4462_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'schema_migration': False, 'receipt_only': True, 'uniform_patient_type_row': True, 'paper_width_mm': 80}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4462 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4462, '__name__', 'app_patch_4462')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4462, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4462, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4462, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_print_receipt_windows_v4462' in globals(): setattr(_rf_snapshot_app_patch_4462, '_print_receipt_windows_v4462', globals()['_print_receipt_windows_v4462'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4462, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4462, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4462, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4462, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4462, 'os', globals()['os'])
if '_rf_alias_app_patch_4462__previous' in globals(): setattr(_rf_snapshot_app_patch_4462, 'previous', globals()['_rf_alias_app_patch_4462__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4462, 'uvicorn', globals()['uvicorn'])
if 'v4462_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4462, 'v4462_receipt_health', globals()['v4462_receipt_health'])
_rf_layers['app_patch_4462'] = _rf_snapshot_app_patch_4462

# ---- app_patch_4463 ----
import os
_rf_alias_app_patch_4463__previous = _rf_layers['app_patch_4462']
core = _rf_alias_app_patch_4463__previous.core
app = _rf_alias_app_patch_4463__previous.app
APP_VERSION = '4.4.63'
_rf_alias_app_patch_4463__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4463__previous.previous.APP_VERSION = APP_VERSION
    _rf_alias_app_patch_4463__previous.previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _receipt_name_lines_v4463(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _print_receipt_windows_v4463(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, Image, StringFormat, StringAlignment, RectangleF, Color
        from System.Drawing.Drawing2D import DashStyle
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 600)
        doc.DefaultPageSettings.Margins = Margins(4, 4, 4, 4)
        fonts = []
        image_holder = {'img': None}

        def font(size, bold=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_title = font(12.5, True)
        f_label = font(9.2, True)
        f_value = font(10.5, True)
        f_name_label = font(8.5, True)
        f_name = font(11.5, True)
        f_turn = font(13.0, True)
        f_status = font(9.0, True)
        outer_pen = Pen(Color.Black, 1.2)
        solid_pen = Pen(Color.Black, 1.0)
        dotted_pen = Pen(Color.FromArgb(105, 105, 105), 1.0)
        dotted_pen.DashStyle = DashStyle.Dot
        check_pen = Pen(Color.Black, 1.5)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            left = 7.0
            right = max(left + 40.0, width - 7.0)
            content_w = right - left
            y = 6.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            logo_box = 43.0
            if os.path.exists(logo_path):
                try:
                    image_holder['img'] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder['img'], left + 2.0, y + 1.0, logo_box, logo_box)
                except Exception:
                    image_holder['img'] = None
            title_x = left + 49.0
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(title_x, y + 1.0, max(24.0, right - title_x), 46.0), center)
            y += 52.0
            g.DrawLine(solid_pen, left, y, right, y)

            def dotted_separator():
                g.DrawLine(dotted_pen, left, y, right, y)

            def row(label, value, value_x=104.0, value_font=None, height=31.0):
                nonlocal y
                top = y
                y += 8.0
                g.DrawString(str(label), f_label, Brushes.Black, left + 1.0, y)
                vx = left + float(value_x)
                g.DrawString(str(value or ''), value_font or f_value, Brushes.Black, RectangleF(vx, y - 1.0, max(20.0, right - vx), height - 10.0))
                y = top + height
                dotted_separator()
            row('Fecha:', payload.fecha, 91.0, f_value, 31.0)
            y += 10.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(left, y, content_w, 14.0), center)
            y += 15.0
            surname, given = _receipt_name_lines_v4463(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(left, y, content_w, 20.0), center)
            y += 20.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(left, y, content_w, 20.0), center)
                y += 20.0
            y += 8.0
            g.DrawLine(solid_pen, left, y, right, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                row('Fecha de nacimiento:', payload.fecha_nacimiento, 154.0, f_value, 34.0)
            if show_blood_pressure:
                top = y
                y += 8.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, left + 1.0, y + 4.0)
                box_w = 84.0
                box_h = 31.0
                box_x = max(left + 151.0, right - box_w - 7.0)
                g.DrawRectangle(solid_pen, box_x, y, box_w, box_h)
                y = top + 47.0
                dotted_separator()
            row('Teléfono:', payload.celular or 'Sin registrar', 96.0, f_value, 31.0)
            if payload.turno:
                row('Turno:', str(payload.turno), 96.0, f_turn, 34.0)
            y += 15.0
            box = 22.0
            gap = 6.0
            options = (('PRIMERO', bool(payload.is_new), left + content_w * 0.25), ('SUBSECUENTE', not bool(payload.is_new), left + content_w * 0.75))
            for label, checked, half_center in options:
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                x = half_center - group_w / 2.0
                x = max(left + 1.0, min(x, right - group_w - 1.0))
                g.DrawRectangle(solid_pen, x, y, box, box)
                if checked:
                    g.DrawLine(check_pen, x + 5.0, y + 12.0, x + 9.0, y + 17.0)
                    g.DrawLine(check_pen, x + 9.0, y + 17.0, x + 18.0, y + 5.0)
                g.DrawString(label, f_status, Brushes.Black, RectangleF(x + box + gap, y + 2.0, label_w + 4.0, 20.0))
            y += 31.0
            g.DrawRectangle(outer_pen, left - 3.0, 2.0, content_w + 6.0, max(20.0, y + 5.0))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            for p in (outer_pen, solid_pen, dotted_pen, check_pen):
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4463
    PREVIEW_FIX_JS = '\n;(()=>{\n  if(window.__v4463ReceiptPreview)return;\n  window.__v4463ReceiptPreview=true;\n\n  function install(){\n    if(typeof window.attentionSlipHtml!==\'function\' || typeof window.printAttentionSlipData!==\'function\'){\n      setTimeout(install,120);\n      return;\n    }\n    if(window.printAttentionSlipData.__v4463)return;\n\n    const patched=function(visit,patient,dayNumber=null){\n      const card=window.attentionSlipHtml(visit,patient,dayNumber);\n      document.querySelector(\'#receiptPrintFrame\')?.remove();\n\n      const frame=document.createElement(\'iframe\');\n      frame.id=\'receiptPrintFrame\';\n      frame.title=\'Impresión de recibo\';\n      frame.setAttribute(\'aria-hidden\',\'true\');\n      Object.assign(frame.style,{\n        position:\'fixed\',right:\'-10000px\',bottom:\'0\',\n        width:\'80mm\',height:\'160mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'\n      });\n      document.body.appendChild(frame);\n\n      const doc=frame.contentDocument||frame.contentWindow?.document;\n      if(!doc){frame.remove();alert(\'No se pudo preparar la impresión. Intenta nuevamente.\');return}\n\n      let printing=false,cleaned=false;\n      const cleanup=()=>{if(cleaned)return;cleaned=true;setTimeout(()=>frame.remove(),120)};\n      const doPrint=()=>{\n        if(printing||cleaned)return;\n        printing=true;\n        try{\n          const win=frame.contentWindow;\n          if(!win)throw Error(\'Ventana de impresión no disponible\');\n          try{win.addEventListener(\'afterprint\',cleanup,{once:true})}catch{}\n          win.focus();win.print();setTimeout(cleanup,120000);\n        }catch{\n          frame.remove();alert(\'No se pudo abrir la impresión. Intenta nuevamente.\');\n        }\n      };\n      const printWhenReady=()=>{\n        const img=doc.querySelector(\'.receipt-brand-icon\');\n        if(img&&!img.complete){\n          let fired=false;\n          const ready=()=>{if(fired)return;fired=true;setTimeout(doPrint,80)};\n          img.addEventListener(\'load\',ready,{once:true});\n          img.addEventListener(\'error\',ready,{once:true});\n          setTimeout(ready,700);\n        }else setTimeout(doPrint,80);\n      };\n\n      frame.onload=printWhenReady;\n      doc.open();\n      doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Recibo de consulta médica</title><style>\n        *{box-sizing:border-box}\n        html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Helvetica,sans-serif}\n        body{width:76mm;padding:0;margin:0 auto}\n        .attention-slip{width:100%;border:1.2px solid #111;padding:3mm 2.5mm;background:#fff}\n        .receipt-brand-row{display:grid;grid-template-columns:12mm 1fr;gap:2mm;align-items:center;padding-bottom:2.6mm;border-bottom:1px solid #222}\n        .receipt-brand-icon{width:11mm;height:11mm;object-fit:contain;filter:grayscale(1) contrast(1.35)}\n        .receipt-title{text-align:center;font-size:12.5pt;font-weight:900;line-height:1.12;letter-spacing:.2px}\n        .receipt-date-row,.receipt-line-row,.receipt-turn-row,.receipt-pressure-row{display:flex;align-items:center;gap:2mm;padding:2.1mm 0;border-bottom:1px dotted #777}\n        .receipt-date-row span,.receipt-line-row span,.receipt-turn-row span,.receipt-pressure-row span:first-child{font-size:9.2pt;font-weight:800;white-space:nowrap}\n        .receipt-date-row strong,.receipt-line-row strong,.receipt-turn-row strong{font-size:10.5pt;font-weight:800;overflow-wrap:anywhere}\n        .receipt-turn-row strong{font-size:13pt}\n        .receipt-name-block{padding:2.8mm 0;border-bottom:1px solid #222;text-align:center}\n        .receipt-name-block span{display:block;font-size:8.5pt;font-weight:800;margin-bottom:1.2mm}\n        .receipt-name-block strong{display:block;font-size:11.5pt;line-height:1.2;font-weight:900;overflow-wrap:anywhere}\n        .receipt-name-block strong em{display:block;font-style:normal}\n        .receipt-name-block strong em+em{margin-top:.7mm}\n        .receipt-pressure-box{display:inline-block;width:22mm;height:8mm;border:1.2px solid #111;margin-left:1mm;background:#fff}\n        .receipt-status-row{display:flex!important;align-items:center;justify-content:space-between;gap:2mm;padding-top:4mm}\n        .receipt-check-item{display:flex!important;align-items:center;justify-content:center;gap:1.5mm;font-size:9pt;white-space:nowrap;flex:0 0 auto;min-width:0}\n        .receipt-check-box{display:inline-flex;width:5.5mm;height:5.5mm;border:1.5px solid #111;align-items:center;justify-content:center;font-size:12pt;font-weight:900;line-height:1;flex:0 0 5.5mm}\n        @media print{\n          body{width:76mm;padding:0}\n          @page{size:80mm auto;margin:2mm}\n        }\n      </style></head><body>${card}</body></html>`);\n      doc.close();\n      setTimeout(printWhenReady,350);\n    };\n\n    patched.__v4463=true;\n    window.printAttentionSlipData=patched;\n  }\n\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_FIX_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.63 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4463/receipt-health')
def v4463_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'schema_migration': False, 'receipt_only': True, 'direct_matches_preview': True, 'preview_subsequent_clip_fixed': True, 'paper_width_mm': 80}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4463 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4463, '__name__', 'app_patch_4463')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4463, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4463, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4463, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PREVIEW_FIX_JS' in globals(): setattr(_rf_snapshot_app_patch_4463, 'PREVIEW_FIX_JS', globals()['PREVIEW_FIX_JS'])
if '_print_receipt_windows_v4463' in globals(): setattr(_rf_snapshot_app_patch_4463, '_print_receipt_windows_v4463', globals()['_print_receipt_windows_v4463'])
if '_receipt_name_lines_v4463' in globals(): setattr(_rf_snapshot_app_patch_4463, '_receipt_name_lines_v4463', globals()['_receipt_name_lines_v4463'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4463, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4463, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4463, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4463, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4463, 'os', globals()['os'])
if '_rf_alias_app_patch_4463__previous' in globals(): setattr(_rf_snapshot_app_patch_4463, 'previous', globals()['_rf_alias_app_patch_4463__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4463, 'uvicorn', globals()['uvicorn'])
if 'v4463_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4463, 'v4463_receipt_health', globals()['v4463_receipt_health'])
_rf_layers['app_patch_4463'] = _rf_snapshot_app_patch_4463

# ---- app_patch_4464 ----
import os
_rf_alias_app_patch_4464__previous = _rf_layers['app_patch_4463']
core = _rf_alias_app_patch_4464__previous.core
app = _rf_alias_app_patch_4464__previous.app
APP_VERSION = '4.4.64'
_rf_alias_app_patch_4464__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4464__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _receipt_name_lines_v4464(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _print_receipt_windows_v4464(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, Image, StringFormat, StringAlignment, RectangleF, Color
        from System.Drawing.Drawing2D import DashStyle
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 600)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        fonts = []
        image_holder = {'img': None}

        def font(size, bold=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_title = font(12.5, True)
        f_label = font(9.2, True)
        f_value = font(10.5, True)
        f_name_label = font(8.5, True)
        f_name = font(11.5, True)
        f_turn = font(13.0, True)
        f_status = font(8.5, True)
        solid_pen = Pen(Color.Black, 1.0)
        dotted_pen = Pen(Color.FromArgb(105, 105, 105), 1.0)
        dotted_pen.DashStyle = DashStyle.Dot
        check_pen = Pen(Color.Black, 1.5)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            left = 2.0
            right = max(left + 80.0, width - 2.0)
            content_w = right - left
            y = 6.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            logo_box = 43.0
            if os.path.exists(logo_path):
                try:
                    image_holder['img'] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder['img'], left + 2.0, y + 1.0, logo_box, logo_box)
                except Exception:
                    image_holder['img'] = None
            title_x = left + 49.0
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(title_x, y + 1.0, max(24.0, right - title_x), 46.0), center)
            y += 52.0
            g.DrawLine(solid_pen, left, y, right, y)

            def dotted_separator():
                g.DrawLine(dotted_pen, left, y, right, y)

            def row(label, value, value_x=104.0, value_font=None, height=31.0):
                nonlocal y
                top = y
                y += 8.0
                g.DrawString(str(label), f_label, Brushes.Black, left + 1.0, y)
                vx = left + float(value_x)
                g.DrawString(str(value or ''), value_font or f_value, Brushes.Black, RectangleF(vx, y - 1.0, max(20.0, right - vx - 2.0), height - 10.0))
                y = top + height
                dotted_separator()
            row('Fecha:', payload.fecha, 91.0, f_value, 31.0)
            y += 10.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(left, y, content_w, 14.0), center)
            y += 15.0
            surname, given = _receipt_name_lines_v4464(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(left, y, content_w, 20.0), center)
            y += 20.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(left, y, content_w, 20.0), center)
                y += 20.0
            y += 8.0
            g.DrawLine(solid_pen, left, y, right, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                row('Fecha de nacimiento:', payload.fecha_nacimiento, 154.0, f_value, 34.0)
            if show_blood_pressure:
                top = y
                y += 8.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, left + 1.0, y + 4.0)
                box_w = 82.0
                box_h = 31.0
                box_x = max(left + 151.0, right - box_w - 5.0)
                g.DrawRectangle(solid_pen, box_x, y, box_w, box_h)
                y = top + 47.0
                dotted_separator()
            row('Teléfono:', payload.celular or 'Sin registrar', 96.0, f_value, 31.0)
            if payload.turno:
                row('Turno:', str(payload.turno), 96.0, f_turn, 34.0)
            y += 15.0
            box = 21.0
            gap = 5.0
            first_label = 'PRIMERO'
            second_label = 'SUBSECUENTE'
            first_w = float(g.MeasureString(first_label, f_status).Width)
            second_w = float(g.MeasureString(second_label, f_status).Width)
            first_group = box + gap + first_w
            second_group = box + gap + second_w
            x1 = left + max(2.0, (content_w * 0.42 - first_group) / 2.0)
            x2 = max(left + content_w * 0.47, right - second_group - 12.0)
            for x, label, checked, label_w in ((x1, first_label, bool(payload.is_new), first_w), (x2, second_label, not bool(payload.is_new), second_w)):
                g.DrawRectangle(solid_pen, x, y, box, box)
                if checked:
                    g.DrawLine(check_pen, x + 5.0, y + 11.0, x + 9.0, y + 16.0)
                    g.DrawLine(check_pen, x + 9.0, y + 16.0, x + 17.0, y + 5.0)
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 2.0)
            y += 32.0
            g.DrawLine(solid_pen, left, y, right, y)
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            for p in (solid_pen, dotted_pen, check_pen):
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4464
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.64 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4464/receipt-health')
def v4464_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'schema_migration': False, 'receipt_only': True, 'paper_width_mm': 80, 'logical_margins_mm': 0, 'outer_frame': False, 'subsequent_safe_right_padding': True}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4464 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4464, '__name__', 'app_patch_4464')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4464, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4464, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4464, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_print_receipt_windows_v4464' in globals(): setattr(_rf_snapshot_app_patch_4464, '_print_receipt_windows_v4464', globals()['_print_receipt_windows_v4464'])
if '_receipt_name_lines_v4464' in globals(): setattr(_rf_snapshot_app_patch_4464, '_receipt_name_lines_v4464', globals()['_receipt_name_lines_v4464'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4464, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4464, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4464, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4464, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4464, 'os', globals()['os'])
if '_rf_alias_app_patch_4464__previous' in globals(): setattr(_rf_snapshot_app_patch_4464, 'previous', globals()['_rf_alias_app_patch_4464__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4464, 'uvicorn', globals()['uvicorn'])
if 'v4464_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4464, 'v4464_receipt_health', globals()['v4464_receipt_health'])
_rf_layers['app_patch_4464'] = _rf_snapshot_app_patch_4464

# ---- app_patch_4465 ----
import os
_rf_alias_app_patch_4465__previous = _rf_layers['app_patch_4464']
core = _rf_alias_app_patch_4465__previous.core
app = _rf_alias_app_patch_4465__previous.app
APP_VERSION = '4.4.65'
_rf_alias_app_patch_4465__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4465__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _receipt_name_lines_v4465(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _thermal_logo_bitmap_v4465(path):
        """Devuelve una versión B/N de alto contraste apta para 203 dpi."""
        from System.Drawing import Bitmap, Color
        src = Bitmap(path)
        try:
            out = Bitmap(src.Width, src.Height)
            for yy in range(src.Height):
                for xx in range(src.Width):
                    c = src.GetPixel(xx, yy)
                    is_ink = c.A > 20 and min(c.R, c.G, c.B) < 238
                    out.SetPixel(xx, yy, Color.Black if is_ink else Color.White)
            return out
        finally:
            src.Dispose()

    def _print_receipt_windows_v4465(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, StringFormat, StringAlignment, RectangleF, Color
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode
        from System.Drawing.Text import TextRenderingHint
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 620)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        fonts = []
        image_holder = {'img': None}

        def font(size, bold=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_title = font(12.0, True)
        f_label = font(8.8, True)
        f_value = font(10.2, True)
        f_name_label = font(8.3, True)
        f_name = font(11.2, True)
        f_turn = font(12.8, True)
        f_status = font(8.25, True)
        border_pen = Pen(Color.Black, 1.2)
        solid_pen = Pen(Color.Black, 1.0)
        dotted_pen = Pen(Color.FromArgb(85, 85, 85), 1.0)
        dotted_pen.DashStyle = DashStyle.Dot
        check_pen = Pen(Color.Black, 1.6)

        def on_print_page(sender, e):
            g = e.Graphics
            try:
                g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
                g.InterpolationMode = InterpolationMode.NearestNeighbor
                g.PixelOffsetMode = PixelOffsetMode.Half
            except Exception:
                pass
            page_w = float(e.PageBounds.Width)
            outer_left = 6.0
            outer_right = max(outer_left + 240.0, page_w - 8.0)
            outer_w = outer_right - outer_left
            inner_left = outer_left + 7.0
            inner_right = outer_right - 7.0
            inner_w = inner_right - inner_left
            y = 7.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            if os.path.exists(logo_path):
                try:
                    image_holder['img'] = _thermal_logo_bitmap_v4465(logo_path)
                    g.DrawImage(image_holder['img'], inner_left + 2.0, y + 1.0, 34.0, 34.0)
                except Exception:
                    image_holder['img'] = None
            title_x = inner_left + 42.0
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(title_x, y, max(30.0, inner_right - title_x), 39.0), center)
            y += 41.0
            g.DrawLine(solid_pen, inner_left, y, inner_right, y)

            def dotted_separator():
                g.DrawLine(dotted_pen, inner_left, y, inner_right, y)

            def draw_row(label, value, value_x, value_font=None, height=29.0):
                nonlocal y
                top = y
                y += 7.0
                g.DrawString(str(label), f_label, Brushes.Black, inner_left, y)
                vx = inner_left + float(value_x)
                g.DrawString(str(value or ''), value_font or f_value, Brushes.Black, RectangleF(vx, y - 1.0, max(18.0, inner_right - vx), height - 9.0))
                y = top + height
                dotted_separator()
            draw_row('Fecha:', payload.fecha, 83.0, f_value, 29.0)
            y += 8.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(inner_left, y, inner_w, 13.0), center)
            y += 13.0
            surname, given = _receipt_name_lines_v4465(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(inner_left, y, inner_w, 19.0), center)
            y += 19.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(inner_left, y, inner_w, 19.0), center)
                y += 19.0
            y += 6.0
            g.DrawLine(solid_pen, inner_left, y, inner_right, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                draw_row('Fecha de nacimiento:', payload.fecha_nacimiento, 142.0, f_value, 32.0)
            if show_blood_pressure:
                top = y
                y += 7.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, inner_left, y + 4.0)
                box_w = 72.0
                box_h = 28.0
                box_x = inner_right - box_w
                g.DrawRectangle(solid_pen, box_x, y, box_w, box_h)
                y = top + 43.0
                dotted_separator()
            draw_row('Teléfono:', payload.celular or 'Sin registrar', 91.0, f_value, 29.0)
            if payload.turno:
                draw_row('Turno:', str(payload.turno), 91.0, f_turn, 32.0)
            y += 12.0
            box = 19.0
            gap = 5.0
            col_gap = 4.0
            col_w = (inner_w - col_gap) / 2.0

            def draw_option(col_left, label, checked):
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                x = col_left + max(0.0, (col_w - group_w) / 2.0)
                max_x = col_left + col_w - group_w
                x = min(x, max_x)
                g.DrawRectangle(solid_pen, x, y, box, box)
                if checked:
                    g.DrawLine(check_pen, x + 4.0, y + 10.0, x + 8.0, y + 15.0)
                    g.DrawLine(check_pen, x + 8.0, y + 15.0, x + 16.0, y + 4.0)
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 1.0)
            draw_option(inner_left, 'PRIMERO', bool(payload.is_new))
            draw_option(inner_left + col_w + col_gap, 'SUBSECUENTE', not bool(payload.is_new))
            y += box + 10.0
            g.DrawRectangle(border_pen, outer_left, 3.0, outer_w, max(20.0, y + 4.0))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            for p in (border_pen, solid_pen, dotted_pen, check_pen):
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4465
    PREVIEW_FIX_JS = '\n;(()=>{\n  if(window.__v4465ReceiptPreview)return;\n  window.__v4465ReceiptPreview=true;\n\n  function install(){\n    if(typeof window.attentionSlipHtml!==\'function\' || typeof window.printAttentionSlipData!==\'function\'){\n      setTimeout(install,120);return;\n    }\n    const patched=function(visit,patient,dayNumber=null){\n      const card=window.attentionSlipHtml(visit,patient,dayNumber);\n      document.querySelector(\'#receiptPrintFrame\')?.remove();\n      const frame=document.createElement(\'iframe\');\n      frame.id=\'receiptPrintFrame\';frame.title=\'Impresión de recibo\';frame.setAttribute(\'aria-hidden\',\'true\');\n      Object.assign(frame.style,{position:\'fixed\',right:\'-10000px\',bottom:\'0\',width:\'80mm\',height:\'160mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'});\n      document.body.appendChild(frame);\n      const doc=frame.contentDocument||frame.contentWindow?.document;\n      if(!doc){frame.remove();alert(\'No se pudo preparar la impresión. Intenta nuevamente.\');return}\n      let printing=false,cleaned=false;\n      const cleanup=()=>{if(cleaned)return;cleaned=true;setTimeout(()=>frame.remove(),120)};\n      const doPrint=()=>{if(printing||cleaned)return;printing=true;try{const win=frame.contentWindow;if(!win)throw Error(\'Ventana de impresión no disponible\');try{win.addEventListener(\'afterprint\',cleanup,{once:true})}catch{}win.focus();win.print();setTimeout(cleanup,120000)}catch{frame.remove();alert(\'No se pudo abrir la impresión. Intenta nuevamente.\')}};\n      const printWhenReady=()=>{const img=doc.querySelector(\'.receipt-brand-icon\');if(img&&!img.complete){let fired=false;const ready=()=>{if(fired)return;fired=true;setTimeout(doPrint,80)};img.addEventListener(\'load\',ready,{once:true});img.addEventListener(\'error\',ready,{once:true});setTimeout(ready,700)}else setTimeout(doPrint,80)};\n      frame.onload=printWhenReady;\n      doc.open();\n      doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Recibo de consulta médica</title><style>\n        *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Helvetica,sans-serif}\n        body{width:72mm;padding:0;margin:0 auto}.attention-slip{width:100%;border:1.2px solid #111;padding:3mm 2.5mm;background:#fff}\n        .receipt-brand-row{display:grid;grid-template-columns:10.5mm 1fr;gap:1.5mm;align-items:center;padding-bottom:2.4mm;border-bottom:1px solid #222}\n        .receipt-brand-icon{width:9.5mm;height:9.5mm;object-fit:contain;filter:grayscale(1) contrast(3.2)}\n        .receipt-title{text-align:center;font-size:12pt;font-weight:900;line-height:1.08;letter-spacing:.1px}\n        .receipt-date-row,.receipt-line-row,.receipt-turn-row,.receipt-pressure-row{display:flex;align-items:center;gap:1.6mm;padding:2mm 0;border-bottom:1px dotted #777}\n        .receipt-date-row span,.receipt-line-row span,.receipt-turn-row span,.receipt-pressure-row span:first-child{font-size:8.8pt;font-weight:800;white-space:nowrap}\n        .receipt-date-row strong,.receipt-line-row strong,.receipt-turn-row strong{font-size:10.2pt;font-weight:800;overflow-wrap:anywhere}.receipt-turn-row strong{font-size:12.8pt}\n        .receipt-name-block{padding:2.6mm 0;border-bottom:1px solid #222;text-align:center}.receipt-name-block span{display:block;font-size:8.3pt;font-weight:800;margin-bottom:1mm}.receipt-name-block strong{display:block;font-size:11.2pt;line-height:1.18;font-weight:900;overflow-wrap:anywhere}.receipt-name-block strong em{display:block;font-style:normal}.receipt-name-block strong em+em{margin-top:.6mm}\n        .receipt-pressure-row{justify-content:space-between}.receipt-pressure-box{display:inline-block;width:19mm;height:7.5mm;border:1.2px solid #111;margin-left:auto;background:#fff}\n        .receipt-status-row{display:grid!important;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1mm;padding-top:3.5mm}.receipt-check-item{display:flex!important;align-items:center;justify-content:center;gap:1mm;font-size:8.25pt;white-space:nowrap;min-width:0}.receipt-check-box{display:inline-flex;width:5mm;height:5mm;border:1.4px solid #111;align-items:center;justify-content:center;font-size:11pt;font-weight:900;line-height:1;flex:0 0 5mm}\n        @media print{body{width:72mm;padding:0}@page{size:80mm auto;margin:4mm}}\n      </style></head><body>${card}</body></html>`);\n      doc.close();setTimeout(printWhenReady,350);\n    };\n    patched.__v4465=true;window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_FIX_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.65 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4465/receipt-health')
def v4465_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'schema_migration': False, 'receipt_only': True, 'direct_matches_preview': True, 'safe_print_width_mm': 72, 'font': 'Arial Bold', 'text_rendering': 'SingleBitPerPixelGridFit', 'thermal_logo_monochrome': True}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4465 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4465, '__name__', 'app_patch_4465')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4465, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4465, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4465, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PREVIEW_FIX_JS' in globals(): setattr(_rf_snapshot_app_patch_4465, 'PREVIEW_FIX_JS', globals()['PREVIEW_FIX_JS'])
if '_print_receipt_windows_v4465' in globals(): setattr(_rf_snapshot_app_patch_4465, '_print_receipt_windows_v4465', globals()['_print_receipt_windows_v4465'])
if '_receipt_name_lines_v4465' in globals(): setattr(_rf_snapshot_app_patch_4465, '_receipt_name_lines_v4465', globals()['_receipt_name_lines_v4465'])
if '_thermal_logo_bitmap_v4465' in globals(): setattr(_rf_snapshot_app_patch_4465, '_thermal_logo_bitmap_v4465', globals()['_thermal_logo_bitmap_v4465'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4465, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4465, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4465, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4465, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4465, 'os', globals()['os'])
if '_rf_alias_app_patch_4465__previous' in globals(): setattr(_rf_snapshot_app_patch_4465, 'previous', globals()['_rf_alias_app_patch_4465__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4465, 'uvicorn', globals()['uvicorn'])
if 'v4465_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4465, 'v4465_receipt_health', globals()['v4465_receipt_health'])
_rf_layers['app_patch_4465'] = _rf_snapshot_app_patch_4465

# ---- app_patch_4466 ----
import io
import os
_rf_alias_app_patch_4466__previous = _rf_layers['app_patch_4465']
core = _rf_alias_app_patch_4466__previous.core
app = _rf_alias_app_patch_4466__previous.app
APP_VERSION = '4.4.66'
_rf_alias_app_patch_4466__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4466__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _name_lines_v4466(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _thermal_logo_v4466(path):
        """Recorta el blanco del PNG y devuelve un isotipo B/N 96x96."""
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Bitmap, Color, Graphics, Rectangle, Brushes, GraphicsUnit
        from System.Drawing.Drawing2D import InterpolationMode, PixelOffsetMode
        src = Bitmap(path)
        try:
            min_x, min_y = (src.Width, src.Height)
            max_x = max_y = -1
            for yy in range(src.Height):
                for xx in range(src.Width):
                    c = src.GetPixel(xx, yy)
                    if c.A > 20 and min(c.R, c.G, c.B) < 235:
                        min_x = min(min_x, xx)
                        min_y = min(min_y, yy)
                        max_x = max(max_x, xx)
                        max_y = max(max_y, yy)
            if max_x < min_x or max_y < min_y:
                return None
            crop_w = max_x - min_x + 1
            crop_h = max_y - min_y + 1
            out = Bitmap(96, 96)
            g = Graphics.FromImage(out)
            try:
                g.Clear(Color.White)
                g.InterpolationMode = InterpolationMode.HighQualityBicubic
                g.PixelOffsetMode = PixelOffsetMode.HighQuality
                scale = min(82.0 / crop_w, 82.0 / crop_h)
                dw = max(1, int(crop_w * scale))
                dh = max(1, int(crop_h * scale))
                dx = (96 - dw) // 2
                dy = (96 - dh) // 2
                g.DrawImage(src, Rectangle(dx, dy, dw, dh), Rectangle(min_x, min_y, crop_w, crop_h), GraphicsUnit.Pixel)
            finally:
                g.Dispose()
            for yy in range(out.Height):
                for xx in range(out.Width):
                    c = out.GetPixel(xx, yy)
                    lum = (int(c.R) * 299 + int(c.G) * 587 + int(c.B) * 114) // 1000
                    out.SetPixel(xx, yy, Color.Black if lum < 205 else Color.White)
            return out
        finally:
            src.Dispose()

    def _render_receipt_png_v4466(payload, show_blood_pressure=True):
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System import Array, Byte
        from System.IO import MemoryStream
        from System.Drawing import Bitmap, Graphics, Color, Font, FontStyle, GraphicsUnit, Brushes, Pen, Rectangle, RectangleF, StringFormat, StringAlignment
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode, SmoothingMode
        from System.Drawing.Text import TextRenderingHint
        from System.Drawing.Imaging import ImageFormat, PixelFormat
        W, H = (576, 820)
        bmp = Bitmap(W, H, PixelFormat.Format24bppRgb)
        g = Graphics.FromImage(bmp)
        fonts = []
        logo = None
        try:
            g.Clear(Color.White)
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            g.SmoothingMode = getattr(SmoothingMode, 'None')

            def font(px, bold=True):
                f = Font('Arial', float(px), FontStyle.Bold if bold else FontStyle.Regular, GraphicsUnit.Pixel)
                fonts.append(f)
                return f
            f_title = font(31)
            f_label = font(23)
            f_value = font(27)
            f_name_label = font(21)
            f_name = font(30)
            f_turn = font(34)
            f_status = font(21)
            solid = Pen(Color.Black, 2.0)
            border = Pen(Color.Black, 2.2)
            dotted = Pen(Color.FromArgb(80, 80, 80), 1.5)
            dotted.DashStyle = DashStyle.Dot
            check = Pen(Color.Black, 3.0)
            outer_l, outer_r = (7.0, W - 7.0)
            inner_l, inner_r = (22.0, W - 22.0)
            inner_w = inner_r - inner_l
            y = 13.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            if os.path.exists(logo_path):
                try:
                    logo = _thermal_logo_v4466(logo_path)
                    if logo is not None:
                        g.DrawImage(logo, 26.0, y + 1.0, 74.0, 74.0)
                except Exception:
                    logo = None
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(110.0, y + 3.0, inner_r - 110.0, 75.0), center)
            y += 83.0
            g.DrawLine(solid, inner_l, y, inner_r, y)

            def separator():
                g.DrawLine(dotted, inner_l, y, inner_r, y)

            def row(label, value, value_x, vf=None, height=56.0, lf=None):
                nonlocal y
                top = y
                y += 14.0
                g.DrawString(str(label), lf or f_label, Brushes.Black, inner_l, y)
                vx = float(value_x)
                g.DrawString(str(value or ''), vf or f_value, Brushes.Black, RectangleF(vx, y - 2.0, inner_r - vx, 36.0))
                y = top + height
                separator()
            row('Fecha:', payload.fecha, 235.0, f_value, 55.0)
            y += 16.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(inner_l, y, inner_w, 28.0), center)
            y += 28.0
            surname, given = _name_lines_v4466(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(inner_l, y, inner_w, 39.0), center)
            y += 39.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(inner_l, y, inner_w, 39.0), center)
                y += 39.0
            y += 12.0
            g.DrawLine(solid, inner_l, y, inner_r, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                birth_label = font(21)
                row('Fecha de nacimiento:', payload.fecha_nacimiento, 350.0, f_value, 60.0, birth_label)
            if show_blood_pressure:
                top = y
                y += 15.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, inner_l, y + 8.0)
                bw, bh = (148.0, 58.0)
                g.DrawRectangle(solid, inner_r - bw, y, bw, bh)
                y = top + 84.0
                separator()
            row('Teléfono:', payload.celular or 'Sin registrar', 225.0, f_value, 57.0)
            if payload.turno:
                row('Turno:', str(payload.turno), 225.0, f_turn, 62.0)
            y += 20.0
            box = 39.0
            gap = 11.0
            col_gap = 12.0
            col_w = (inner_w - col_gap) / 2.0

            def option(col_l, label, checked):
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                x = col_l + max(0.0, (col_w - group_w) / 2.0)
                x = min(x, col_l + col_w - group_w)
                g.DrawRectangle(solid, x, y, box, box)
                if checked:
                    g.DrawLine(check, x + 8.0, y + 21.0, x + 17.0, y + 31.0)
                    g.DrawLine(check, x + 17.0, y + 31.0, x + 33.0, y + 8.0)
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 6.0)
            option(inner_l, 'PRIMERO', bool(payload.is_new))
            option(inner_l + col_w + col_gap, 'SUBSECUENTE', not bool(payload.is_new))
            y += box + 24.0
            final_h = int(min(H, y + 13.0))
            g.DrawRectangle(border, outer_l, 5.0, outer_r - outer_l, final_h - 10.0)
            cropped = bmp.Clone(Rectangle(0, 0, W, final_h), PixelFormat.Format24bppRgb)
            try:
                ms = MemoryStream()
                cropped.Save(ms, ImageFormat.Png)
                data = bytes(bytearray(ms.ToArray()))
                ms.Dispose()
                return data
            finally:
                cropped.Dispose()
        finally:
            try:
                g.Dispose()
            except Exception:
                pass
            if logo is not None:
                try:
                    logo.Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            try:
                bmp.Dispose()
            except Exception:
                pass

    def _print_receipt_windows_v4466(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Image, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        png = _render_receipt_png_v4466(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 700)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        holder = {'stream': None, 'img': None}

        def on_print_page(sender, e):
            from System import Array, Byte
            arr = Array[Byte](bytearray(png))
            holder['stream'] = MemoryStream(arr)
            holder['img'] = Image.FromStream(holder['stream'])
            target_w = 283.5
            target_h = target_w * float(holder['img'].Height) / float(holder['img'].Width)
            x = max(0.0, (float(e.PageBounds.Width) - target_w) / 2.0)
            e.Graphics.DrawImage(holder['img'], RectangleF(x, 0.0, target_w, target_h))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if holder.get('img') is not None:
                try:
                    holder['img'].Dispose()
                except Exception:
                    pass
            if holder.get('stream') is not None:
                try:
                    holder['stream'].Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4466
    from fastapi import Response

    @app.post('/api/v4466/receipt-image')
    def v4466_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4466(data, bool(prefs.get('show_blood_pressure', True)))
        return Response(content=png, media_type='image/png', headers={'Cache-Control': 'no-store'})
    PREVIEW_JS = '\n;(()=>{\n  if(window.__v4466ReceiptRaster)return;\n  window.__v4466ReceiptRaster=true;\n  function install(){\n    if(typeof window.printAttentionSlipData!==\'function\' || typeof window.receiptPrintPayload!==\'function\'){\n      setTimeout(install,100);return;\n    }\n    const patched=async function(visit,patient,dayNumber=null){\n      try{\n        const payload=window.receiptPrintPayload(visit,patient,dayNumber);\n        const r=await fetch(\'/api/v4466/receipt-image\',{method:\'POST\',credentials:\'same-origin\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(payload)});\n        if(!r.ok)throw Error(\'HTTP \'+r.status);\n        const blob=await r.blob();\n        const url=URL.createObjectURL(blob);\n        document.querySelector(\'#receiptPrintFrame\')?.remove();\n        const frame=document.createElement(\'iframe\');\n        frame.id=\'receiptPrintFrame\';frame.title=\'Impresión de recibo\';frame.setAttribute(\'aria-hidden\',\'true\');\n        Object.assign(frame.style,{position:\'fixed\',right:\'-10000px\',bottom:\'0\',width:\'80mm\',height:\'180mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'});\n        document.body.appendChild(frame);\n        const doc=frame.contentDocument||frame.contentWindow?.document;\n        if(!doc)throw Error(\'Sin documento de impresión\');\n        let cleaned=false;\n        const cleanup=()=>{if(cleaned)return;cleaned=true;try{URL.revokeObjectURL(url)}catch{}setTimeout(()=>frame.remove(),120)};\n        doc.open();\n        doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>\n          *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;width:80mm}body{display:flex;justify-content:center;align-items:flex-start}\n          img{display:block;width:72mm;height:auto;margin:0;padding:0}\n          @media print{@page{size:80mm auto;margin:0}html,body{width:80mm;margin:0;padding:0}img{width:72mm;margin:0 auto}}\n        </style></head><body><img id="rimg" src="${url}"></body></html>`);\n        doc.close();\n        const img=doc.getElementById(\'rimg\');\n        const go=()=>setTimeout(()=>{try{const w=frame.contentWindow;w.addEventListener(\'afterprint\',cleanup,{once:true});w.focus();w.print();setTimeout(cleanup,120000)}catch(e){cleanup();alert(\'No se pudo imprimir el recibo.\')}},80);\n        if(img&& !img.complete){img.addEventListener(\'load\',go,{once:true});img.addEventListener(\'error\',go,{once:true});setTimeout(go,800)}else go();\n      }catch(e){\n        alert(\'No se pudo preparar el recibo unificado. Se usará el formato anterior.\');\n        try{return window.__v4465PrintFallback?.(visit,patient,dayNumber)}catch{}\n      }\n    };\n    window.__v4465PrintFallback=window.printAttentionSlipData;\n    patched.__v4466=true;\n    window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.66 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4466/receipt-health')
def v4466_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'same_raster_for_preview_and_direct': True, 'thermal_width_px': 576, 'thermal_width_mm': 72, 'logo_cropped_monochrome': True}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4466 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4466, '__name__', 'app_patch_4466')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4466, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4466, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4466, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PREVIEW_JS' in globals(): setattr(_rf_snapshot_app_patch_4466, 'PREVIEW_JS', globals()['PREVIEW_JS'])
if 'Response' in globals(): setattr(_rf_snapshot_app_patch_4466, 'Response', globals()['Response'])
if '_name_lines_v4466' in globals(): setattr(_rf_snapshot_app_patch_4466, '_name_lines_v4466', globals()['_name_lines_v4466'])
if '_print_receipt_windows_v4466' in globals(): setattr(_rf_snapshot_app_patch_4466, '_print_receipt_windows_v4466', globals()['_print_receipt_windows_v4466'])
if '_render_receipt_png_v4466' in globals(): setattr(_rf_snapshot_app_patch_4466, '_render_receipt_png_v4466', globals()['_render_receipt_png_v4466'])
if '_thermal_logo_v4466' in globals(): setattr(_rf_snapshot_app_patch_4466, '_thermal_logo_v4466', globals()['_thermal_logo_v4466'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4466, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4466, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4466, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4466, 'exc', globals()['exc'])
if 'io' in globals(): setattr(_rf_snapshot_app_patch_4466, 'io', globals()['io'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4466, 'os', globals()['os'])
if '_rf_alias_app_patch_4466__previous' in globals(): setattr(_rf_snapshot_app_patch_4466, 'previous', globals()['_rf_alias_app_patch_4466__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4466, 'uvicorn', globals()['uvicorn'])
if 'v4466_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4466, 'v4466_receipt_health', globals()['v4466_receipt_health'])
if 'v4466_receipt_image' in globals(): setattr(_rf_snapshot_app_patch_4466, 'v4466_receipt_image', globals()['v4466_receipt_image'])
_rf_layers['app_patch_4466'] = _rf_snapshot_app_patch_4466

# ---- app_patch_4467 ----
import os
_rf_alias_app_patch_4467__previous = _rf_layers['app_patch_4466']
core = _rf_alias_app_patch_4467__previous.core
app = _rf_alias_app_patch_4467__previous.app
APP_VERSION = '4.4.67'
_rf_alias_app_patch_4467__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4467__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _name_lines_v4467(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _render_receipt_png_v4467(payload, show_blood_pressure=True):
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Bitmap, Graphics, Color, Font, FontStyle, GraphicsUnit, Brushes, Pen, Rectangle, RectangleF, StringFormat, StringAlignment
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode, SmoothingMode
        from System.Drawing.Text import TextRenderingHint
        from System.Drawing.Imaging import ImageFormat, PixelFormat
        W, H = (576, 860)
        bmp = Bitmap(W, H, PixelFormat.Format24bppRgb)
        g = Graphics.FromImage(bmp)
        fonts = []
        logo = None
        pens = []
        try:
            g.Clear(Color.White)
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            try:
                g.SmoothingMode = getattr(SmoothingMode, 'None')
            except Exception:
                pass

            def font(px, bold=True):
                f = Font('Arial', float(px), FontStyle.Bold if bold else FontStyle.Regular, GraphicsUnit.Pixel)
                fonts.append(f)
                return f
            f_title = font(30)
            f_label = font(26)
            f_value = font(30)
            f_name_label = font(23)
            f_name = font(35)
            f_turn = font(38)
            f_status = font(22)
            solid = Pen(Color.Black, 2.0)
            pens.append(solid)
            dotted = Pen(Color.FromArgb(65, 65, 65), 1.7)
            pens.append(dotted)
            dotted.DashStyle = DashStyle.Dot
            check = Pen(Color.Black, 3.2)
            pens.append(check)
            inner_l, inner_r = (12.0, W - 12.0)
            inner_w = inner_r - inner_l
            y = 10.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            if os.path.exists(logo_path):
                try:
                    logo = _rf_alias_app_patch_4467__previous._thermal_logo_v4466(logo_path)
                    if logo is not None:
                        g.DrawImage(logo, 17.0, y + 1.0, 82.0, 82.0)
                except Exception:
                    logo = None
            g.DrawString('RECIBO DE\nCONSULTA MÉDICA', f_title, Brushes.Black, RectangleF(102.0, y + 4.0, W - 114.0, 78.0), center)
            y += 88.0
            g.DrawLine(solid, inner_l, y, inner_r, y)

            def separator():
                g.DrawLine(dotted, inner_l, y, inner_r, y)

            def row(label, value, value_x, vf=None, height=61.0, lf=None):
                nonlocal y
                top = y
                y += 16.0
                g.DrawString(str(label), lf or f_label, Brushes.Black, inner_l, y)
                vx = float(value_x)
                g.DrawString(str(value or ''), vf or f_value, Brushes.Black, RectangleF(vx, y - 3.0, inner_r - vx, 42.0))
                y = top + height
                separator()
            row('Fecha:', payload.fecha, 218.0, f_value, 60.0)
            y += 17.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(inner_l, y, inner_w, 30.0), center)
            y += 30.0
            surname, given = _name_lines_v4467(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(inner_l, y, inner_w, 43.0), center)
            y += 43.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(inner_l, y, inner_w, 43.0), center)
                y += 43.0
            y += 11.0
            g.DrawLine(solid, inner_l, y, inner_r, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                birth_label = font(24)
                row('Fecha de nacimiento:', payload.fecha_nacimiento, 340.0, f_value, 65.0, birth_label)
            if show_blood_pressure:
                top = y
                y += 16.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, inner_l, y + 9.0)
                bw, bh = (142.0, 60.0)
                g.DrawRectangle(solid, inner_r - bw, y, bw, bh)
                y = top + 88.0
                separator()
            row('Teléfono:', payload.celular or 'Sin registrar', 215.0, f_value, 61.0)
            if payload.turno:
                row('Turno:', str(payload.turno), 215.0, f_turn, 67.0)
            y += 21.0
            box = 40.0
            gap = 10.0
            col_gap = 10.0
            col_w = (inner_w - col_gap) / 2.0

            def option(col_l, label, checked):
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                x = col_l + max(0.0, (col_w - group_w) / 2.0)
                x = min(x, col_l + col_w - group_w)
                g.DrawRectangle(solid, x, y, box, box)
                if checked:
                    g.DrawLine(check, x + 8.0, y + 22.0, x + 17.0, y + 32.0)
                    g.DrawLine(check, x + 17.0, y + 32.0, x + 34.0, y + 8.0)
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 7.0)
            option(inner_l, 'PRIMERO', bool(payload.is_new))
            option(inner_l + col_w + col_gap, 'SUBSECUENTE', not bool(payload.is_new))
            y += box + 16.0
            final_h = int(min(H, y + 8.0))
            cropped = bmp.Clone(Rectangle(0, 0, W, final_h), PixelFormat.Format24bppRgb)
            try:
                ms = MemoryStream()
                cropped.Save(ms, ImageFormat.Png)
                data = bytes(bytearray(ms.ToArray()))
                ms.Dispose()
                return data
            finally:
                cropped.Dispose()
        finally:
            try:
                g.Dispose()
            except Exception:
                pass
            if logo is not None:
                try:
                    logo.Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            for p in pens:
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                bmp.Dispose()
            except Exception:
                pass

    def _print_receipt_windows_v4467(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Image, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        png = _render_receipt_png_v4467(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm', 315, 760)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        holder = {'stream': None, 'img': None}

        def on_print_page(sender, e):
            from System import Array, Byte
            arr = Array[Byte](bytearray(png))
            holder['stream'] = MemoryStream(arr)
            holder['img'] = Image.FromStream(holder['stream'])
            target_w = 283.5
            target_h = target_w * float(holder['img'].Height) / float(holder['img'].Width)
            x = max(0.0, (float(e.PageBounds.Width) - target_w) / 2.0)
            e.Graphics.DrawImage(holder['img'], RectangleF(x, 0.0, target_w, target_h))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if holder.get('img') is not None:
                try:
                    holder['img'].Dispose()
                except Exception:
                    pass
            if holder.get('stream') is not None:
                try:
                    holder['stream'].Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4467
    from fastapi import Response

    @app.post('/api/v4467/receipt-image')
    def v4467_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4467(data, bool(prefs.get('show_blood_pressure', True)))
        return Response(content=png, media_type='image/png', headers={'Cache-Control': 'no-store'})
    PREVIEW_JS = '\n;(()=>{\n  if(window.__v4467ReceiptRaster)return;\n  window.__v4467ReceiptRaster=true;\n  function install(){\n    if(typeof window.printAttentionSlipData!==\'function\'||typeof window.receiptPrintPayload!==\'function\'){\n      setTimeout(install,100);return;\n    }\n    const patched=async function(visit,patient,dayNumber=null){\n      try{\n        const payload=window.receiptPrintPayload(visit,patient,dayNumber);\n        const r=await fetch(\'/api/v4467/receipt-image\',{\n          method:\'POST\',credentials:\'same-origin\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify(payload)\n        });\n        if(!r.ok)throw Error(\'HTTP \'+r.status);\n        const blob=await r.blob();const url=URL.createObjectURL(blob);\n        document.querySelector(\'#receiptPrintFrame\')?.remove();\n        const frame=document.createElement(\'iframe\');frame.id=\'receiptPrintFrame\';frame.title=\'Impresión de recibo\';frame.setAttribute(\'aria-hidden\',\'true\');\n        Object.assign(frame.style,{position:\'fixed\',right:\'-10000px\',bottom:\'0\',width:\'80mm\',height:\'190mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'});\n        document.body.appendChild(frame);\n        const doc=frame.contentDocument||frame.contentWindow?.document;if(!doc)throw Error(\'Sin documento de impresión\');\n        let cleaned=false;const cleanup=()=>{if(cleaned)return;cleaned=true;try{URL.revokeObjectURL(url)}catch{}setTimeout(()=>frame.remove(),120)};\n        doc.open();doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>\n          *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;width:80mm}\n          body{display:flex;justify-content:center;align-items:flex-start}\n          img{display:block;width:72mm;height:auto;margin:0;padding:0}\n          @media print{@page{size:80mm auto;margin:0}html,body{width:80mm;margin:0;padding:0}img{width:72mm;margin:0 auto}}\n        </style></head><body><img id="rimg" src="${url}"></body></html>`);doc.close();\n        const img=doc.getElementById(\'rimg\');\n        const go=()=>setTimeout(()=>{try{const w=frame.contentWindow;w.addEventListener(\'afterprint\',cleanup,{once:true});w.focus();w.print();setTimeout(cleanup,120000)}catch(e){cleanup();alert(\'No se pudo imprimir el recibo.\')}},80);\n        if(img&&!img.complete){img.addEventListener(\'load\',go,{once:true});img.addEventListener(\'error\',go,{once:true});setTimeout(go,800)}else go();\n      }catch(e){\n        alert(\'No se pudo preparar el recibo. Se usará el formato anterior.\');\n        try{return window.__v4466PrintFallback?.(visit,patient,dayNumber)}catch{}\n      }\n    };\n    window.__v4466PrintFallback=window.printAttentionSlipData;\n    patched.__v4467=true;window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.67 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4467/receipt-health')
def v4467_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'same_raster_for_preview_and_direct': True, 'thermal_width_px': 576, 'thermal_width_mm': 72, 'outer_border': False, 'larger_legacy_typography': True, 'subsecuente_safe': True}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4467 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4467, '__name__', 'app_patch_4467')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4467, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4467, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4467, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PREVIEW_JS' in globals(): setattr(_rf_snapshot_app_patch_4467, 'PREVIEW_JS', globals()['PREVIEW_JS'])
if 'Response' in globals(): setattr(_rf_snapshot_app_patch_4467, 'Response', globals()['Response'])
if '_name_lines_v4467' in globals(): setattr(_rf_snapshot_app_patch_4467, '_name_lines_v4467', globals()['_name_lines_v4467'])
if '_print_receipt_windows_v4467' in globals(): setattr(_rf_snapshot_app_patch_4467, '_print_receipt_windows_v4467', globals()['_print_receipt_windows_v4467'])
if '_render_receipt_png_v4467' in globals(): setattr(_rf_snapshot_app_patch_4467, '_render_receipt_png_v4467', globals()['_render_receipt_png_v4467'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4467, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4467, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4467, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4467, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4467, 'os', globals()['os'])
if '_rf_alias_app_patch_4467__previous' in globals(): setattr(_rf_snapshot_app_patch_4467, 'previous', globals()['_rf_alias_app_patch_4467__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4467, 'uvicorn', globals()['uvicorn'])
if 'v4467_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4467, 'v4467_receipt_health', globals()['v4467_receipt_health'])
if 'v4467_receipt_image' in globals(): setattr(_rf_snapshot_app_patch_4467, 'v4467_receipt_image', globals()['v4467_receipt_image'])
_rf_layers['app_patch_4467'] = _rf_snapshot_app_patch_4467

# ---- app_patch_4468 ----
import os
_rf_alias_app_patch_4468__previous = _rf_layers['app_patch_4467']
core = _rf_alias_app_patch_4468__previous.core
app = _rf_alias_app_patch_4468__previous.app
APP_VERSION = '4.4.68'
_rf_alias_app_patch_4468__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4468__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _name_lines_v4468(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        if len(parts) == 2:
            return (' '.join(parts), '')
        if len(parts) == 3:
            return (' '.join(parts[:2]), parts[2])
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _render_receipt_png_v4468(payload, show_blood_pressure=True):
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Bitmap, Graphics, Color, Font, FontStyle, GraphicsUnit, Brushes, Pen, Rectangle, RectangleF, StringFormat, StringAlignment
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode, SmoothingMode
        from System.Drawing.Text import TextRenderingHint
        from System.Drawing.Imaging import ImageFormat, PixelFormat
        W, H = (576, 1120)
        bmp = Bitmap(W, H, PixelFormat.Format24bppRgb)
        g = Graphics.FromImage(bmp)
        fonts = []
        logo = None
        pens = []
        try:
            g.Clear(Color.White)
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            try:
                g.SmoothingMode = getattr(SmoothingMode, 'None')
            except Exception:
                pass

            def font(px, bold=True, family='Arial'):
                f = Font(family, float(px), FontStyle.Bold if bold else FontStyle.Regular, GraphicsUnit.Pixel)
                fonts.append(f)
                return f
            f_title = font(36, True, 'Arial Black')
            f_label = font(29, True)
            f_value = font(33, True)
            f_name_label = font(25, True)
            f_name_pref = 42
            f_turn = font(42, True)
            f_status = font(24, True)
            solid = Pen(Color.Black, 2.2)
            pens.append(solid)
            dotted = Pen(Color.FromArgb(55, 55, 55), 1.8)
            pens.append(dotted)
            dotted.DashStyle = DashStyle.Dot
            check = Pen(Color.Black, 3.4)
            pens.append(check)
            inner_l, inner_r = (10.0, W - 10.0)
            inner_w = inner_r - inner_l
            y = 12.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            def fit_bold(text, preferred_px, min_px, max_width, family='Arial Black'):
                px = float(preferred_px)
                f = font(px, True, family)
                while px > float(min_px) and float(g.MeasureString(str(text), f).Width) > float(max_width):
                    px -= 1.0
                    f = font(px, True, family)
                return f
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            if os.path.exists(logo_path):
                try:
                    logo_func = getattr(getattr(_rf_alias_app_patch_4468__previous, 'previous', None), '_thermal_logo_v4466', None)
                    if logo_func:
                        logo = logo_func(logo_path)
                    if logo is not None:
                        g.DrawImage(logo, 13.0, y + 4.0, 92.0, 92.0)
                except Exception:
                    logo = None
            title_text = 'RECIBO DE\nCONSULTA MÉDICA'
            g.DrawString(title_text, f_title, Brushes.Black, RectangleF(108.0, y + 6.0, W - 120.0, 94.0), center)
            y += 104.0
            g.DrawLine(solid, inner_l, y, inner_r, y)

            def separator():
                g.DrawLine(dotted, inner_l, y, inner_r, y)

            def row(label, value, value_x, vf=None, height=70.0, lf=None):
                nonlocal y
                top = y
                y += 18.0
                g.DrawString(str(label), lf or f_label, Brushes.Black, inner_l, y)
                vx = float(value_x)
                g.DrawString(str(value or ''), vf or f_value, Brushes.Black, RectangleF(vx, y - 4.0, inner_r - vx, 48.0))
                y = top + height
                separator()
            row('Fecha:', payload.fecha, 212.0, f_value, 69.0)
            y += 21.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(inner_l, y, inner_w, 34.0), center)
            y += 34.0
            surname, given = _name_lines_v4468(payload.nombre)
            name_font_1 = fit_bold(surname, f_name_pref, 32, inner_w - 8.0)
            g.DrawString(surname, name_font_1, Brushes.Black, RectangleF(inner_l, y, inner_w, 52.0), center)
            y += 52.0
            if given:
                name_font_2 = fit_bold(given, f_name_pref, 32, inner_w - 8.0)
                g.DrawString(given, name_font_2, Brushes.Black, RectangleF(inner_l, y, inner_w, 52.0), center)
                y += 52.0
            y += 17.0
            g.DrawLine(solid, inner_l, y, inner_r, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                birth_label = fit_bold('Fecha de nacimiento:', 26, 23, 320.0, 'Arial')
                row('Fecha de nacimiento:', payload.fecha_nacimiento, 342.0, f_value, 74.0, birth_label)
            if show_blood_pressure:
                top = y
                y += 18.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, inner_l, y + 10.0)
                bw, bh = (148.0, 67.0)
                g.DrawRectangle(solid, inner_r - bw, y, bw, bh)
                y = top + 98.0
                separator()
            row('Teléfono:', payload.celular or 'Sin registrar', 215.0, f_value, 70.0)
            if payload.turno:
                row('Turno:', str(payload.turno), 215.0, f_turn, 77.0)
            y += 27.0
            box = 44.0
            gap = 10.0
            col_gap = 8.0
            col_w = (inner_w - col_gap) / 2.0

            def option(col_l, label, checked):
                label_font = f_status
                label_w = float(g.MeasureString(label, label_font).Width)
                if box + gap + label_w > col_w:
                    label_font = fit_bold(label, 24, 20, col_w - box - gap - 2.0, 'Arial')
                    label_w = float(g.MeasureString(label, label_font).Width)
                group_w = box + gap + label_w
                x = col_l + max(0.0, (col_w - group_w) / 2.0)
                x = min(x, col_l + col_w - group_w)
                g.DrawRectangle(solid, x, y, box, box)
                if checked:
                    g.DrawLine(check, x + 9.0, y + 24.0, x + 19.0, y + 35.0)
                    g.DrawLine(check, x + 19.0, y + 35.0, x + 37.0, y + 8.0)
                g.DrawString(label, label_font, Brushes.Black, x + box + gap, y + 8.0)
            option(inner_l, 'PRIMERO', bool(payload.is_new))
            option(inner_l + col_w + col_gap, 'SUBSECUENTE', not bool(payload.is_new))
            y += box + 26.0
            final_h = int(min(H, y + 12.0))
            cropped = bmp.Clone(Rectangle(0, 0, W, final_h), PixelFormat.Format24bppRgb)
            try:
                ms = MemoryStream()
                cropped.Save(ms, ImageFormat.Png)
                data = bytes(bytearray(ms.ToArray()))
                ms.Dispose()
                return data
            finally:
                cropped.Dispose()
        finally:
            try:
                g.Dispose()
            except Exception:
                pass
            if logo is not None:
                try:
                    logo.Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            for p in pens:
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                bmp.Dispose()
            except Exception:
                pass

    def _print_receipt_windows_v4468(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Image, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        png = _render_receipt_png_v4468(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm largo', 315, 1050)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        holder = {'stream': None, 'img': None}

        def on_print_page(sender, e):
            from System import Array, Byte
            arr = Array[Byte](bytearray(png))
            holder['stream'] = MemoryStream(arr)
            holder['img'] = Image.FromStream(holder['stream'])
            target_w = 283.5
            target_h = target_w * float(holder['img'].Height) / float(holder['img'].Width)
            x = max(0.0, (float(e.PageBounds.Width) - target_w) / 2.0)
            e.Graphics.DrawImage(holder['img'], RectangleF(x, 0.0, target_w, target_h))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if holder.get('img') is not None:
                try:
                    holder['img'].Dispose()
                except Exception:
                    pass
            if holder.get('stream') is not None:
                try:
                    holder['stream'].Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4468
    from fastapi import Response

    @app.post('/api/v4468/receipt-image')
    def v4468_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4468(data, bool(prefs.get('show_blood_pressure', True)))
        return Response(content=png, media_type='image/png', headers={'Cache-Control': 'no-store'})
    PREVIEW_JS = '\n;(()=>{\n  if(window.__v4468ReceiptRaster)return;\n  window.__v4468ReceiptRaster=true;\n  function install(){\n    if(typeof window.printAttentionSlipData!==\'function\'||typeof window.receiptPrintPayload!==\'function\'){\n      setTimeout(install,100);return;\n    }\n    const patched=async function(visit,patient,dayNumber=null){\n      try{\n        const payload=window.receiptPrintPayload(visit,patient,dayNumber);\n        const r=await fetch(\'/api/v4468/receipt-image\',{\n          method:\'POST\',credentials:\'same-origin\',\n          headers:{\'Content-Type\':\'application/json\'},\n          body:JSON.stringify(payload)\n        });\n        if(!r.ok)throw Error(\'HTTP \'+r.status);\n        const blob=await r.blob();\n        const url=URL.createObjectURL(blob);\n        document.querySelector(\'#receiptPrintFrame\')?.remove();\n        const frame=document.createElement(\'iframe\');\n        frame.id=\'receiptPrintFrame\';\n        frame.title=\'Impresión de recibo\';\n        frame.setAttribute(\'aria-hidden\',\'true\');\n        Object.assign(frame.style,{\n          position:\'fixed\',right:\'-10000px\',bottom:\'0\',\n          width:\'80mm\',height:\'260mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'\n        });\n        document.body.appendChild(frame);\n        const doc=frame.contentDocument||frame.contentWindow?.document;\n        if(!doc)throw Error(\'Sin documento de impresión\');\n        let cleaned=false;\n        const cleanup=()=>{\n          if(cleaned)return;cleaned=true;\n          try{URL.revokeObjectURL(url)}catch{}\n          setTimeout(()=>frame.remove(),120)\n        };\n        doc.open();\n        doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>\n          *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;width:80mm}\n          body{display:flex;justify-content:center;align-items:flex-start}\n          img{display:block;width:72mm;height:auto;margin:0;padding:0}\n          @media print{\n            @page{size:80mm auto;margin:0}\n            html,body{width:80mm;margin:0;padding:0}\n            img{width:72mm;margin:0 auto}\n          }\n        </style></head><body><img id="rimg" src="${url}"></body></html>`);\n        doc.close();\n        const img=doc.getElementById(\'rimg\');\n        const go=()=>setTimeout(()=>{\n          try{\n            const w=frame.contentWindow;\n            w.addEventListener(\'afterprint\',cleanup,{once:true});\n            w.focus();w.print();setTimeout(cleanup,120000)\n          }catch(e){\n            cleanup();alert(\'No se pudo imprimir el recibo.\')\n          }\n        },80);\n        if(img&&!img.complete){\n          img.addEventListener(\'load\',go,{once:true});\n          img.addEventListener(\'error\',go,{once:true});\n          setTimeout(go,900)\n        }else go();\n      }catch(e){\n        alert(\'No se pudo preparar el recibo. Se usará el formato anterior.\');\n        try{return window.__v4467PrintFallback?.(visit,patient,dayNumber)}catch{}\n      }\n    };\n    window.__v4467PrintFallback=window.printAttentionSlipData;\n    patched.__v4468=true;\n    window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.68 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4468/receipt-health')
def v4468_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'same_raster_for_preview_and_direct': True, 'thermal_width_px': 576, 'thermal_width_mm': 72, 'longer_receipt': True, 'larger_fonts': True, 'title_bold_large': True, 'name_bold_large': True, 'outer_border': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4468 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4468, '__name__', 'app_patch_4468')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4468, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4468, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4468, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PREVIEW_JS' in globals(): setattr(_rf_snapshot_app_patch_4468, 'PREVIEW_JS', globals()['PREVIEW_JS'])
if 'Response' in globals(): setattr(_rf_snapshot_app_patch_4468, 'Response', globals()['Response'])
if '_name_lines_v4468' in globals(): setattr(_rf_snapshot_app_patch_4468, '_name_lines_v4468', globals()['_name_lines_v4468'])
if '_print_receipt_windows_v4468' in globals(): setattr(_rf_snapshot_app_patch_4468, '_print_receipt_windows_v4468', globals()['_print_receipt_windows_v4468'])
if '_render_receipt_png_v4468' in globals(): setattr(_rf_snapshot_app_patch_4468, '_render_receipt_png_v4468', globals()['_render_receipt_png_v4468'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4468, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4468, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4468, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4468, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4468, 'os', globals()['os'])
if '_rf_alias_app_patch_4468__previous' in globals(): setattr(_rf_snapshot_app_patch_4468, 'previous', globals()['_rf_alias_app_patch_4468__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4468, 'uvicorn', globals()['uvicorn'])
if 'v4468_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4468, 'v4468_receipt_health', globals()['v4468_receipt_health'])
if 'v4468_receipt_image' in globals(): setattr(_rf_snapshot_app_patch_4468, 'v4468_receipt_image', globals()['v4468_receipt_image'])
_rf_layers['app_patch_4468'] = _rf_snapshot_app_patch_4468

# ---- app_patch_4469 ----
import os
_rf_alias_app_patch_4469__previous = _rf_layers['app_patch_4468']
core = _rf_alias_app_patch_4469__previous.core
app = _rf_alias_app_patch_4469__previous.app
APP_VERSION = '4.4.69'
_rf_alias_app_patch_4469__previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    _rf_alias_app_patch_4469__previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:
    _render_v4468 = _rf_alias_app_patch_4469__previous._render_receipt_png_v4468

    def _render_receipt_png_v4469(payload, show_blood_pressure=True):
        """Mantiene el diseño de 4.4.68, usando mejor los 576 puntos imprimibles."""
        base_png = _render_v4468(payload, show_blood_pressure)
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System import Array, Byte
        from System.IO import MemoryStream
        from System.Drawing import Bitmap, Graphics, Color, Rectangle, GraphicsUnit
        from System.Drawing.Drawing2D import InterpolationMode, PixelOffsetMode, SmoothingMode
        from System.Drawing.Imaging import ImageFormat, PixelFormat
        source_stream = None
        src = None
        out = None
        g = None
        out_stream = None
        try:
            arr = Array[Byte](bytearray(base_png))
            source_stream = MemoryStream(arr)
            src = Bitmap(source_stream)
            crop_left = 8
            crop_right = 8
            crop_width = max(1, int(src.Width) - crop_left - crop_right)
            out = Bitmap(576, int(src.Height), PixelFormat.Format24bppRgb)
            g = Graphics.FromImage(out)
            g.Clear(Color.White)
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            try:
                g.SmoothingMode = getattr(SmoothingMode, 'None')
            except Exception:
                pass
            g.DrawImage(src, Rectangle(0, 0, 576, int(src.Height)), Rectangle(crop_left, 0, crop_width, int(src.Height)), GraphicsUnit.Pixel)
            out_stream = MemoryStream()
            out.Save(out_stream, ImageFormat.Png)
            return bytes(bytearray(out_stream.ToArray()))
        finally:
            try:
                if g is not None:
                    g.Dispose()
            except Exception:
                pass
            try:
                if out is not None:
                    out.Dispose()
            except Exception:
                pass
            try:
                if src is not None:
                    src.Dispose()
            except Exception:
                pass
            try:
                if source_stream is not None:
                    source_stream.Dispose()
            except Exception:
                pass
            try:
                if out_stream is not None:
                    out_stream.Dispose()
            except Exception:
                pass

    def _print_receipt_windows_v4469(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System import Array, Byte
        from System.IO import MemoryStream
        from System.Drawing import Image, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        png = _render_receipt_png_v4469(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm largo', 315, 1050)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        holder = {'stream': None, 'img': None}

        def on_print_page(sender, e):
            arr = Array[Byte](bytearray(png))
            holder['stream'] = MemoryStream(arr)
            holder['img'] = Image.FromStream(holder['stream'])
            target_w = 283.5
            target_h = target_w * float(holder['img'].Height) / float(holder['img'].Width)
            x = 9.84
            e.Graphics.DrawImage(holder['img'], RectangleF(x, 0.0, target_w, target_h))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if holder.get('img') is not None:
                try:
                    holder['img'].Dispose()
                except Exception:
                    pass
            if holder.get('stream') is not None:
                try:
                    holder['stream'].Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4469
    from fastapi import Response

    @app.post('/api/v4469/receipt-image')
    def v4469_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4469(data, bool(prefs.get('show_blood_pressure', True)))
        return Response(content=png, media_type='image/png', headers={'Cache-Control': 'no-store'})
    PREVIEW_JS = '\n;(()=>{\n  if(window.__v4469ReceiptRaster)return;\n  window.__v4469ReceiptRaster=true;\n  function install(){\n    if(typeof window.printAttentionSlipData!==\'function\'||typeof window.receiptPrintPayload!==\'function\'){\n      setTimeout(install,100);return;\n    }\n    const patched=async function(visit,patient,dayNumber=null){\n      try{\n        const payload=window.receiptPrintPayload(visit,patient,dayNumber);\n        const r=await fetch(\'/api/v4469/receipt-image\',{\n          method:\'POST\',credentials:\'same-origin\',\n          headers:{\'Content-Type\':\'application/json\'},\n          body:JSON.stringify(payload)\n        });\n        if(!r.ok)throw Error(\'HTTP \'+r.status);\n        const blob=await r.blob();\n        const url=URL.createObjectURL(blob);\n        document.querySelector(\'#receiptPrintFrame\')?.remove();\n        const frame=document.createElement(\'iframe\');\n        frame.id=\'receiptPrintFrame\';\n        frame.title=\'Impresión de recibo\';\n        frame.setAttribute(\'aria-hidden\',\'true\');\n        Object.assign(frame.style,{\n          position:\'fixed\',right:\'-10000px\',bottom:\'0\',\n          width:\'80mm\',height:\'260mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'\n        });\n        document.body.appendChild(frame);\n        const doc=frame.contentDocument||frame.contentWindow?.document;\n        if(!doc)throw Error(\'Sin documento de impresión\');\n        let cleaned=false;\n        const cleanup=()=>{\n          if(cleaned)return;cleaned=true;\n          try{URL.revokeObjectURL(url)}catch{}\n          setTimeout(()=>frame.remove(),120)\n        };\n        doc.open();\n        doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>\n          *{box-sizing:border-box}\n          html,body{margin:0;padding:0;background:#fff;width:80mm}\n          body{display:block}\n          img{display:block;width:72mm;height:auto;margin-left:2.5mm;margin-right:5.5mm;padding:0}\n          @media print{\n            @page{size:80mm auto;margin:0}\n            html,body{width:80mm;margin:0;padding:0}\n            img{width:72mm;height:auto;margin-left:2.5mm;margin-right:5.5mm}\n          }\n        </style></head><body><img id="rimg" src="${url}"></body></html>`);\n        doc.close();\n        const img=doc.getElementById(\'rimg\');\n        const go=()=>setTimeout(()=>{\n          try{\n            const w=frame.contentWindow;\n            w.addEventListener(\'afterprint\',cleanup,{once:true});\n            w.focus();w.print();setTimeout(cleanup,120000)\n          }catch(e){\n            cleanup();alert(\'No se pudo imprimir el recibo.\')\n          }\n        },80);\n        if(img&&!img.complete){\n          img.addEventListener(\'load\',go,{once:true});\n          img.addEventListener(\'error\',go,{once:true});\n          setTimeout(go,900)\n        }else go();\n      }catch(e){\n        alert(\'No se pudo preparar el recibo. Se usará el formato anterior.\');\n        try{return window.__v4468PrintFallback?.(visit,patient,dayNumber)}catch{}\n      }\n    };\n    window.__v4468PrintFallback=window.printAttentionSlipData;\n    patched.__v4469=true;\n    window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.69 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4469/receipt-health')
def v4469_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'same_raster_for_preview_and_direct': True, 'thermal_width_px': 576, 'thermal_width_mm': 72, 'paper_left_offset_mm': 2.5, 'horizontal_content_expansion_percent': 2.9, 'keeps_v4468_typography_and_height': True, 'outer_border': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4469 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4469, '__name__', 'app_patch_4469')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4469, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4469, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4469, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PREVIEW_JS' in globals(): setattr(_rf_snapshot_app_patch_4469, 'PREVIEW_JS', globals()['PREVIEW_JS'])
if 'Response' in globals(): setattr(_rf_snapshot_app_patch_4469, 'Response', globals()['Response'])
if '_print_receipt_windows_v4469' in globals(): setattr(_rf_snapshot_app_patch_4469, '_print_receipt_windows_v4469', globals()['_print_receipt_windows_v4469'])
if '_render_receipt_png_v4469' in globals(): setattr(_rf_snapshot_app_patch_4469, '_render_receipt_png_v4469', globals()['_render_receipt_png_v4469'])
if '_render_v4468' in globals(): setattr(_rf_snapshot_app_patch_4469, '_render_v4468', globals()['_render_v4468'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4469, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4469, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4469, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4469, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4469, 'os', globals()['os'])
if '_rf_alias_app_patch_4469__previous' in globals(): setattr(_rf_snapshot_app_patch_4469, 'previous', globals()['_rf_alias_app_patch_4469__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4469, 'uvicorn', globals()['uvicorn'])
if 'v4469_receipt_health' in globals(): setattr(_rf_snapshot_app_patch_4469, 'v4469_receipt_health', globals()['v4469_receipt_health'])
if 'v4469_receipt_image' in globals(): setattr(_rf_snapshot_app_patch_4469, 'v4469_receipt_image', globals()['v4469_receipt_image'])
_rf_layers['app_patch_4469'] = _rf_snapshot_app_patch_4469

# ---- app_patch_4470 ----
_rf_alias_app_patch_4470__previous = _rf_layers['app_patch_4469']
core = _rf_alias_app_patch_4470__previous.core
app = _rf_alias_app_patch_4470__previous.app
APP_VERSION = '4.4.70'
_mod = _rf_alias_app_patch_4470__previous
_seen = set()
for _ in range(20):
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

    class _V4470PrintVisitIn(core.BaseModel):
        pass

    def _v4470_is_consultation(visit) -> bool:
        return not str(getattr(visit, 'procedimiento', None) or '').strip()

    def _v4470_consultation_turn(db, visit) -> int | None:
        rows = list(db.scalars(core.select(core.Visit).where(core.Visit.fecha == visit.fecha).order_by(core.Visit.id)))
        first_by_patient = {}
        for row in rows:
            if not _v4470_is_consultation(row):
                continue
            first_by_patient.setdefault(int(row.patient_id), int(row.id))
        ordered = [pid for pid, _first_id in sorted(first_by_patient.items(), key=lambda item: item[1])]
        try:
            return ordered.index(int(visit.patient_id)) + 1
        except ValueError:
            return None

    def _v4470_is_first_consultation(db, visit) -> bool:
        prior = int(db.scalar(core.select(core.func.count(core.Visit.id)).where(core.Visit.patient_id == int(visit.patient_id), core.Visit.id < int(visit.id), core.func.length(core.func.trim(core.func.coalesce(core.Visit.procedimiento, ''))) == 0)) or 0)
        return prior == 0

    @app.post('/api/v4470/print-visit/{visit_id}')
    def v4470_print_visit(visit_id: int, data: _V4470PrintVisitIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        visit = db.get(core.Visit, int(visit_id))
        if not visit:
            return {'ok': True, 'printed': False, 'reason': 'visit_not_found', 'message': 'Atención guardada, pero no se encontró el registro para imprimir.'}
        if not _v4470_is_consultation(visit):
            return {'ok': True, 'printed': False, 'reason': 'procedure_only', 'message': 'Atención guardada. Los procedimientos no generan recibo.'}
        patient = db.get(core.Patient, int(visit.patient_id))
        if not patient:
            return {'ok': True, 'printed': False, 'reason': 'patient_not_found', 'message': 'Atención guardada, pero no se encontró el paciente para imprimir.'}
        turn = _v4470_consultation_turn(db, visit)
        is_new = _v4470_is_first_consultation(db, visit)
        birth = None
        if getattr(patient, 'fecha_nacimiento', None):
            try:
                birth = patient.fecha_nacimiento.strftime('%d/%m/%Y')
            except Exception:
                birth = str(patient.fecha_nacimiento)
        payload = core.ReceiptPrintIn(fecha=visit.fecha.strftime('%d/%m/%Y'), nombre=str(patient.nombre or '').strip().upper(), fecha_nacimiento=birth, celular=str(patient.celular or '').strip() or None, turno=turn, is_new=is_new)
        prefs = core._app_preferences()
        printer = str(prefs.get('printer') or '').strip()
        try:
            used = core._print_receipt_windows(payload, printer, bool(prefs.get('show_blood_pressure', True)))
            return {'ok': True, 'printed': True, 'printer': used, 'turno': turn, 'message': 'Atención guardada. Recibo enviado a la impresora.'}
        except Exception as exc:
            try:
                core.logging.getLogger(__name__).warning('v4.4.70: atención %s guardada, impresión falló: %s', visit_id, exc)
            except Exception:
                pass
            return {'ok': True, 'printed': False, 'reason': 'printer_error', 'turno': turn, 'error': str(exc)[:240], 'message': 'Atención guardada. No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.'}

    @app.get('/api/v4470/version')
    def v4470_version(user=core.Depends(core.current_user)):
        return {'version': APP_VERSION}
    V4470_CSS = '\n.v4470-busy{position:fixed;inset:0;z-index:2147483500;background:rgba(245,249,253,.94);display:grid;place-items:center;padding:24px;backdrop-filter:blur(2px)}\n.v4470-busy-card{min-width:290px;max-width:430px;padding:24px 26px;border-radius:18px;background:#fff;border:1px solid #d9e5ef;box-shadow:0 18px 55px rgba(28,58,85,.18);text-align:center;color:#27445f}\n.v4470-spinner{width:42px;height:42px;margin:0 auto 14px;border:4px solid #d9e7f2;border-top-color:#3e789f;border-radius:50%;animation:v4470spin .8s linear infinite}\n@keyframes v4470spin{to{transform:rotate(360deg)}}\n.v4470-busy-card b{display:block;font-size:15px;line-height:1.25;margin-bottom:5px}.v4470-busy-card small{display:block;font-size:11px;color:#70859a}\n.v4470-toast{position:fixed;right:18px;bottom:18px;z-index:2147483501;max-width:420px;padding:12px 14px;border-radius:12px;background:#225f42;color:#fff;box-shadow:0 10px 30px rgba(25,62,45,.24);font-size:12px;font-weight:800}.v4470-toast.warn{background:#8a6419}\n.v4470-phone-shared{margin-top:6px;padding:7px 9px;border:1px solid #dfc36e;border-radius:9px;background:#fff9e8;color:#705617;font-size:10px;line-height:1.35}.v4470-phone-shared b{display:block;margin-bottom:2px}\n.v4470-proc-manager{margin-top:14px;padding:13px;border:1px solid #d6e1eb;border-radius:13px;background:#fbfdff}.v4470-proc-manager-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:9px}.v4470-proc-manager-head h4{margin:0;font-size:13px;color:#294b68}.v4470-proc-manager-head small{display:block;margin-top:2px;color:#71869a}.v4470-proc-list{display:grid;gap:6px}.v4470-proc-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:9px;align-items:center;padding:8px 9px;border:1px solid #e2eaf1;border-radius:10px;background:#fff}.v4470-proc-row b{font-size:11px;color:#314f68}.v4470-proc-row span{font-size:11px;font-weight:800;color:#577087;white-space:nowrap}.v4470-proc-delete{border:1px solid #dfb3b3!important;background:#fff6f6!important;color:#9a3838!important;border-radius:8px!important;padding:6px 9px!important;font-size:10px!important;font-weight:900!important}\n@media(max-width:640px){.v4470-proc-row{grid-template-columns:minmax(0,1fr) auto}.v4470-proc-row span{grid-column:1}}\n'
    V4470_JS = '\n;(()=>{\n  if(window.__v4470WorkflowFix)return;\n  window.__v4470WorkflowFix=true;\n  const VERSION=\'4.4.70\';\n  let attentionBusy=false,procBusy=false;\n  const text=v=>String(v??\'\').replace(/\\s+/g,\' \').trim();\n  const norm=v=>text(v).normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').toUpperCase();\n  const phoneKey=v=>{let d=String(v||\'\').replace(/\\D/g,\'\');if(d.length===12&&d.startsWith(\'593\'))d=\'0\'+d.slice(3);return d};\n  const sleep=ms=>new Promise(r=>setTimeout(r,ms));\n  function baseApi(){const fn=window.api;return fn?.__v4470Base||fn}\n\n  function installPhoneSharing(){\n    if(typeof window.api!==\'function\'){setTimeout(installPhoneSharing,120);return}\n    if(window.api.__v4470SharedPhone)return;\n    const stable=window.api;\n    const shim=async function(url,opt={}){\n      const u=String(url||\'\');\n      if(u.startsWith(\'/api/identity/phone-owner\'))return {duplicate:false,patient:null,normalized:\'\'};\n      return stable.apply(this,arguments);\n    };\n    shim.__v4470SharedPhone=true;shim.__v4470Base=stable;window.api=shim;try{api=shim}catch(_e){}\n  }\n\n  function currentPatientId(){\n    const modal=document.querySelector(\'#modal,.modal,.modal-backdrop\')||document;\n    const attrs=[...modal.querySelectorAll(\'button[onclick],a[onclick]\')].map(x=>String(x.getAttribute(\'onclick\')||\'\'));\n    for(const raw of attrs){const m=/(?:savePatient|savePatientAndReturnToAttention|editPatientFromAttention)\\s*\\(\\s*(\\d+)/.exec(raw);if(m)return Number(m[1]||0)}\n    return 0;\n  }\n  async function passivePhoneWarning(){\n    const input=document.querySelector(\'#fCel\');if(!input)return;\n    const host=input.closest(\'.form-field\')||input.parentElement;host?.querySelector(\'.v4470-phone-shared\')?.remove();\n    const wanted=phoneKey(input.value);if(wanted.length<9)return;const call=baseApi();if(typeof call!==\'function\')return;\n    let rows=[];try{const vars=[wanted];if(wanted.length===10&&wanted.startsWith(\'0\'))vars.push(\'593\'+wanted.slice(1));const batches=await Promise.all(vars.map(q=>call(\'/api/patients?q=\'+encodeURIComponent(q)+\'&limit=30\').catch(()=>[])));rows=batches.flat()}catch(_e){return}\n    const exclude=currentPatientId(),found=new Map();\n    for(const p of rows){if(!p||Number(p.id||0)<=0||Number(p.id)===exclude)continue;if(phoneKey(p.celular)===wanted)found.set(Number(p.id),p)}\n    const hits=[...found.values()];if(!hits.length||!host)return;\n    const names=hits.slice(0,3).map(p=>text(p.nombre)||\'Paciente\').join(\', \'),note=document.createElement(\'div\');\n    note.className=\'v4470-phone-shared\';note.innerHTML=`<b>ℹ Celular compartido</b>Este número también está registrado para ${names}. Puedes guardarlo igualmente si corresponde a esta persona.`;host.appendChild(note);\n  }\n  function installPhoneWatcher(){\n    const attach=()=>{const input=document.querySelector(\'#fCel\');if(!input||input.dataset.v4470PhoneWatcher)return;input.dataset.v4470PhoneWatcher=\'1\';let timer=0;const run=()=>{clearTimeout(timer);timer=setTimeout(passivePhoneWarning,330)};input.addEventListener(\'input\',run);input.addEventListener(\'blur\',run);setTimeout(run,80)};\n    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();\n  }\n\n  function busyOverlay(message){document.querySelector(\'.v4470-busy\')?.remove();const el=document.createElement(\'div\');el.className=\'v4470-busy\';el.innerHTML=`<div class="v4470-busy-card"><div class="v4470-spinner"></div><b>${message}</b><small>Espera un momento…</small></div>`;document.body.appendChild(el);return el}\n  function busyText(el,message){const b=el?.querySelector(\'b\');if(b)b.textContent=message}function hideBusy(el){try{el?.remove()}catch(_e){}}\n  function toast(message,warn=false){document.querySelector(\'.v4470-toast\')?.remove();const el=document.createElement(\'div\');el.className=\'v4470-toast\'+(warn?\' warn\':\'\');el.textContent=message;document.body.appendChild(el);setTimeout(()=>el.remove(),5200)}\n  function goHome(){try{if(typeof window.closeModal===\'function\')window.closeModal()}catch(_e){}const els=[...document.querySelectorAll(\'nav button,nav a,.sidebar button,.sidebar a,.menu button,.menu a,button,a\')];const home=els.find(el=>norm(el.textContent)===\'INICIO\');if(home){try{home.click();return}catch(_e){}}for(const id of [\'inicio\',\'home\']){try{if(typeof window.show===\'function\'){window.show(id);return}}catch(_e){}}}\n\n  function installAttentionFlow(){\n    if(typeof window.saveAttention!==\'function\'){setTimeout(installAttentionFlow,120);return}if(window.saveAttention.__v4470AutoPrint)return;\n    const stableSave=window.saveAttention;\n    const patched=async function(patientId){\n      if(attentionBusy)return;attentionBusy=true;let savedBatch=null;const overlay=busyOverlay(\'Guardando atención e imprimiendo recibo…\');const apiBefore=window.api;const globalBefore=(()=>{try{return api}catch(_e){return null}})();\n      const capture=async function(url,opt={}){const result=await apiBefore.apply(this,arguments);const u=String(url||\'\');if(u===\'/api/visits/batch-payment\'||u===\'/api/visits/batch\'){if(result&&typeof result===\'object\')savedBatch=result}return result};\n      try{window.api=capture;try{api=capture}catch(_e){}await stableSave.apply(this,arguments)}catch(err){hideBusy(overlay);attentionBusy=false;throw err}finally{window.api=apiBefore;try{api=globalBefore||apiBefore}catch(_e){}}\n      try{\n        if(!savedBatch||savedBatch.ok===false){hideBusy(overlay);attentionBusy=false;return}\n        const items=Array.isArray(savedBatch.items)?savedBatch.items:[],consult=items.find(v=>!text(v?.procedimiento));let printResult=null;\n        if(consult&&Number(consult.id||0)>0){busyText(overlay,\'Atención guardada. Imprimiendo recibo…\');try{printResult=await apiBefore(\'/api/v4470/print-visit/\'+Number(consult.id),{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:\'{}\'})}catch(e){printResult={printed:false}}}\n        goHome();try{if(typeof window.invalidateAttentionWeekCache===\'function\')window.invalidateAttentionWeekCache();if(typeof window.loadWeek===\'function\'){const d=text(consult?.fecha||items[0]?.fecha||\'\').slice(0,10);Promise.resolve(window.loadWeek(d||undefined,d||undefined)).catch(()=>{})}if(typeof window.refreshPendingBadges===\'function\')Promise.resolve(window.refreshPendingBadges()).catch(()=>{})}catch(_e){}\n        hideBusy(overlay);if(consult){if(printResult?.printed)toast(\'✓ Atención guardada. Recibo enviado a la impresora.\');else toast(\'✓ Atención guardada. ⚠ No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.\',true)}else toast(\'✓ Atención guardada.\');\n      }finally{attentionBusy=false}\n    };\n    patched.__v4470AutoPrint=true;patched.__v4470Stable=stableSave;window.saveAttention=patched;\n  }\n\n  async function renderProcedureManager(){\n    const sec=document.querySelector(\'[data-config-section="procedimientos"]\');if(!sec||procBusy)return;procBusy=true;\n    try{const call=window.api;if(typeof call!==\'function\')return;const rows=await call(\'/api/procedures\');let box=sec.querySelector(\'#v4470ProcedureManager\');if(!box){box=document.createElement(\'div\');box.id=\'v4470ProcedureManager\';box.className=\'v4470-proc-manager\';sec.appendChild(box)}const list=Array.isArray(rows)?rows:[];\n      box.innerHTML=`<div class="v4470-proc-manager-head"><div><h4>Eliminar servicios</h4><small>Si un servicio ya tiene historial, se archiva y las atenciones antiguas se conservan.</small></div></div><div class="v4470-proc-list">${list.map(p=>`<div class="v4470-proc-row" data-id="${Number(p.id)}"><b>${text(p.nombre)}</b><span>${p.valor_default==null?\'Sin precio\':\'$\'+Number(p.valor_default).toFixed(2)}</span><button type="button" class="v4470-proc-delete" data-delete="${Number(p.id)}">Eliminar</button></div>`).join(\'\')||\'<small>No hay servicios activos.</small>\'}</div>`;\n      box.querySelectorAll(\'[data-delete]\').forEach(btn=>btn.addEventListener(\'click\',async()=>{const id=Number(btn.dataset.delete||0),row=list.find(x=>Number(x.id)===id);if(!id)return;if(!confirm(`¿Eliminar "${text(row?.nombre)||\'este servicio\'}"?\\n\\nSi tiene atenciones anteriores, se archivará para no alterar el historial.`))return;btn.disabled=true;try{const d=await call(\'/api/procedures/\'+id,{method:\'DELETE\'});toast(d?.message||\'Servicio eliminado.\');try{if(typeof window.loadProcedures===\'function\')await window.loadProcedures()}catch(_e){}await sleep(60);box.remove();renderProcedureManager()}catch(e){alert(e?.message||e);btn.disabled=false}}));\n    }catch(_e){}finally{procBusy=false}\n  }\n  function installProcedureManager(){\n    const attempt=()=>{const sec=document.querySelector(\'[data-config-section="procedimientos"]\');if(sec&&!sec.querySelector(\'#v4470ProcedureManager\'))renderProcedureManager();if(typeof window.loadProcedures===\'function\'&&!window.loadProcedures.__v4470Manager){const stable=window.loadProcedures;const wrapped=async function(){const r=await stable.apply(this,arguments);setTimeout(renderProcedureManager,40);return r};wrapped.__v4470Manager=true;window.loadProcedures=wrapped}};\n    new MutationObserver(()=>setTimeout(attempt,30)).observe(document.documentElement,{childList:true,subtree:true});attempt();\n  }\n\n  function paintVersion(){const expected=\'v\'+VERSION;document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{if(text(el.textContent)!==expected)el.textContent=expected});const badge=document.querySelector(\'#connectionBadge\');if(badge){let v=badge.querySelector(\'.v460-version\');if(!v){v=document.createElement(\'span\');v.className=\'v460-version\';badge.appendChild(v)}if(text(v.textContent)!==expected)v.textContent=expected}}\n  function installVersionPainter(){let scheduled=false;const run=()=>{if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;paintVersion()},20)};new MutationObserver(run).observe(document.documentElement,{childList:true,subtree:true,characterData:true});paintVersion();setTimeout(paintVersion,250);setTimeout(paintVersion,900)}\n\n  function boot(){installPhoneSharing();installPhoneWatcher();installAttentionFlow();installProcedureManager();installVersionPainter()}\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});else boot();\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4470_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4470_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.70 workflow patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4470/health')
def v4470_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'shared_phone_allowed': True, 'automatic_receipt_after_consultation': True, 'attention_survives_printer_error': True, 'procedure_delete_manager': True, 'dynamic_version_badge': True, 'receipt_design': 'v4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4470 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4470, '__name__', 'app_patch_4470')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4470, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4470, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4470, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4470_CSS' in globals(): setattr(_rf_snapshot_app_patch_4470, 'V4470_CSS', globals()['V4470_CSS'])
if 'V4470_JS' in globals(): setattr(_rf_snapshot_app_patch_4470, 'V4470_JS', globals()['V4470_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4470, '_', globals()['_'])
if '_V4470PrintVisitIn' in globals(): setattr(_rf_snapshot_app_patch_4470, '_V4470PrintVisitIn', globals()['_V4470PrintVisitIn'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4470, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4470, '_seen', globals()['_seen'])
if '_v4470_consultation_turn' in globals(): setattr(_rf_snapshot_app_patch_4470, '_v4470_consultation_turn', globals()['_v4470_consultation_turn'])
if '_v4470_is_consultation' in globals(): setattr(_rf_snapshot_app_patch_4470, '_v4470_is_consultation', globals()['_v4470_is_consultation'])
if '_v4470_is_first_consultation' in globals(): setattr(_rf_snapshot_app_patch_4470, '_v4470_is_first_consultation', globals()['_v4470_is_first_consultation'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4470, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4470, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4470, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4470, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4470__previous' in globals(): setattr(_rf_snapshot_app_patch_4470, 'previous', globals()['_rf_alias_app_patch_4470__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4470, 'uvicorn', globals()['uvicorn'])
if 'v4470_health' in globals(): setattr(_rf_snapshot_app_patch_4470, 'v4470_health', globals()['v4470_health'])
if 'v4470_print_visit' in globals(): setattr(_rf_snapshot_app_patch_4470, 'v4470_print_visit', globals()['v4470_print_visit'])
if 'v4470_version' in globals(): setattr(_rf_snapshot_app_patch_4470, 'v4470_version', globals()['v4470_version'])
_rf_layers['app_patch_4470'] = _rf_snapshot_app_patch_4470

# ---- app_patch_4473 ----
_rf_alias_app_patch_4473__previous = _rf_layers['app_patch_4470']
core = _rf_alias_app_patch_4473__previous.core
app = _rf_alias_app_patch_4473__previous.app
APP_VERSION = '4.4.73'
_mod = _rf_alias_app_patch_4473__previous
_seen = set()
for _ in range(24):
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
    _js = _js.replace("const VERSION='4.4.70';", "const VERSION='4.4.73';")
    core.V460_OVERLAY_JS = _js
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.73 stable recovery patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4473/recovery-health')
def v4473_recovery_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'base_ui': '4.4.70', 'imports_v4471': False, 'imports_v4472': False, 'white_screen_recovery': True, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4473 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4473, '__name__', 'app_patch_4473')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4473, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4473, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4473, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4473, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4473, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4473, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4473, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4473, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4473, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4473, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4473, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4473__previous' in globals(): setattr(_rf_snapshot_app_patch_4473, 'previous', globals()['_rf_alias_app_patch_4473__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4473, 'uvicorn', globals()['uvicorn'])
if 'v4473_recovery_health' in globals(): setattr(_rf_snapshot_app_patch_4473, 'v4473_recovery_health', globals()['v4473_recovery_health'])
_rf_layers['app_patch_4473'] = _rf_snapshot_app_patch_4473

# ---- app_patch_4474 ----
import os
import queue
import threading
import time
_rf_alias_app_patch_4474__previous = _rf_layers['app_patch_4473']
core = _rf_alias_app_patch_4474__previous.core
app = _rf_alias_app_patch_4474__previous.app
APP_VERSION = '4.4.74'
_mod = _rf_alias_app_patch_4474__previous
_seen = set()
for _ in range(24):
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
_PRINT_QUEUE = queue.Queue(maxsize=16)
_PRINT_LOCK = threading.Lock()
_PRINT_STATE = {'queued_total': 0, 'printed_total': 0, 'failed_total': 0, 'last_status': 'idle', 'last_error': '', 'last_printer': '', 'last_finished_at': 0.0}
try:
    _stable_print_receipt_windows = core._print_receipt_windows

    def _record_state(**values):
        with _PRINT_LOCK:
            _PRINT_STATE.update(values)

    def _resolve_printer_name_fast(printer_name: str='') -> str:
        chosen = str(printer_name or '').strip()
        if chosen:
            return chosen
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        try:
            import clr
            clr.AddReference('System.Drawing')
            from System.Drawing.Printing import PrinterSettings
            chosen = str(PrinterSettings().PrinterName or '').strip()
        except Exception as exc:
            raise RuntimeError(f'No se pudo consultar la impresora predeterminada: {exc}') from exc
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        return chosen

    def _print_worker():
        while True:
            payload, printer_name, show_blood_pressure = _PRINT_QUEUE.get()
            try:
                _record_state(last_status='printing', last_error='', last_printer=str(printer_name or ''))
                used = _stable_print_receipt_windows(payload, printer_name, show_blood_pressure)
                with _PRINT_LOCK:
                    _PRINT_STATE['printed_total'] += 1
                    _PRINT_STATE['last_status'] = 'printed'
                    _PRINT_STATE['last_error'] = ''
                    _PRINT_STATE['last_printer'] = str(used or printer_name or '')
                    _PRINT_STATE['last_finished_at'] = time.time()
            except Exception as exc:
                with _PRINT_LOCK:
                    _PRINT_STATE['failed_total'] += 1
                    _PRINT_STATE['last_status'] = 'error'
                    _PRINT_STATE['last_error'] = str(exc)[:240]
                    _PRINT_STATE['last_finished_at'] = time.time()
                try:
                    core.logging.getLogger(__name__).warning('v4.4.74: fallo de impresión en segundo plano: %s', exc)
                except Exception:
                    pass
            finally:
                _PRINT_QUEUE.task_done()
    _PRINT_THREAD = threading.Thread(target=_print_worker, name='rp-receipt-printer', daemon=True)
    _PRINT_THREAD.start()

    def _print_receipt_windows_v4474(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        """Encola el recibo y devuelve enseguida; el worker habla con Windows."""
        chosen = _resolve_printer_name_fast(printer_name)
        try:
            _PRINT_QUEUE.put_nowait((payload, chosen, bool(show_blood_pressure)))
        except queue.Full as exc:
            raise RuntimeError('Hay demasiados recibos esperando impresión. Reintenta en unos segundos.') from exc
        with _PRINT_LOCK:
            _PRINT_STATE['queued_total'] += 1
            _PRINT_STATE['last_status'] = 'queued'
            _PRINT_STATE['last_error'] = ''
            _PRINT_STATE['last_printer'] = chosen
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4474
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _js.replace("const VERSION='4.4.73';", "const VERSION='4.4.74';")
    core.V460_OVERLAY_JS = _js
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.74 background print patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4474/print-queue-health')
def v4474_print_queue_health(user=core.Depends(core.current_user)):
    with _PRINT_LOCK:
        state = dict(_PRINT_STATE)
    state.update({'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'boot_error': PATCH_BOOT_ERROR, 'queue_depth': _PRINT_QUEUE.qsize(), 'worker_alive': bool(globals().get('_PRINT_THREAD') and _PRINT_THREAD.is_alive()), 'base_ui': '4.4.73 / v4.4.70 flow', 'changes_save_attention_js': False, 'uses_dom_observer': False, 'background_print': True, 'single_worker': True, 'receipt_layout_version': '4.4.69'})
    return state
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4474 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4474, '__name__', 'app_patch_4474')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4474, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4474, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4474, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4474, '_', globals()['_'])
if '_PRINT_LOCK' in globals(): setattr(_rf_snapshot_app_patch_4474, '_PRINT_LOCK', globals()['_PRINT_LOCK'])
if '_PRINT_QUEUE' in globals(): setattr(_rf_snapshot_app_patch_4474, '_PRINT_QUEUE', globals()['_PRINT_QUEUE'])
if '_PRINT_STATE' in globals(): setattr(_rf_snapshot_app_patch_4474, '_PRINT_STATE', globals()['_PRINT_STATE'])
if '_PRINT_THREAD' in globals(): setattr(_rf_snapshot_app_patch_4474, '_PRINT_THREAD', globals()['_PRINT_THREAD'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4474, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4474, '_mod', globals()['_mod'])
if '_print_receipt_windows_v4474' in globals(): setattr(_rf_snapshot_app_patch_4474, '_print_receipt_windows_v4474', globals()['_print_receipt_windows_v4474'])
if '_print_worker' in globals(): setattr(_rf_snapshot_app_patch_4474, '_print_worker', globals()['_print_worker'])
if '_record_state' in globals(): setattr(_rf_snapshot_app_patch_4474, '_record_state', globals()['_record_state'])
if '_resolve_printer_name_fast' in globals(): setattr(_rf_snapshot_app_patch_4474, '_resolve_printer_name_fast', globals()['_resolve_printer_name_fast'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4474, '_seen', globals()['_seen'])
if '_stable_print_receipt_windows' in globals(): setattr(_rf_snapshot_app_patch_4474, '_stable_print_receipt_windows', globals()['_stable_print_receipt_windows'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4474, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4474, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4474, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4474, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4474, 'os', globals()['os'])
if '_rf_alias_app_patch_4474__previous' in globals(): setattr(_rf_snapshot_app_patch_4474, 'previous', globals()['_rf_alias_app_patch_4474__previous'])
if 'queue' in globals(): setattr(_rf_snapshot_app_patch_4474, 'queue', globals()['queue'])
if 'threading' in globals(): setattr(_rf_snapshot_app_patch_4474, 'threading', globals()['threading'])
if 'time' in globals(): setattr(_rf_snapshot_app_patch_4474, 'time', globals()['time'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4474, 'uvicorn', globals()['uvicorn'])
if 'v4474_print_queue_health' in globals(): setattr(_rf_snapshot_app_patch_4474, 'v4474_print_queue_health', globals()['v4474_print_queue_health'])
_rf_layers['app_patch_4474'] = _rf_snapshot_app_patch_4474

# ---- app_patch_4475 ----
_rf_alias_app_patch_4475__previous = _rf_layers['app_patch_4474']
core = _rf_alias_app_patch_4475__previous.core
app = _rf_alias_app_patch_4475__previous.app
APP_VERSION = '4.4.75'
_mod = _rf_alias_app_patch_4475__previous
_seen = set()
for _ in range(28):
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
PAYMENT_SENTINELS = {'EFECTIVO': -442901, 'TRANSFERENCIA': -442920}
SRI_PAYMENT_CODES = {'EFECTIVO': '01', 'TRANSFERENCIA': '20'}

def _normalize_payment_method(value: object) -> str:
    raw = ' '.join(str(value or '').strip().upper().split())
    aliases = {'TRANSFERENCIA BANCARIA': 'TRANSFERENCIA', 'BANCO': 'TRANSFERENCIA', 'CASH': 'EFECTIVO'}
    raw = aliases.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise core.HTTPException(400, 'Selecciona la forma de pago: Efectivo o Transferencia bancaria.')
    return raw

def _remove_api_route(path: str, method: str) -> int:
    """Quita una ruta anterior exacta antes de registrar su reemplazo."""
    wanted = str(method or '').upper()
    removed = 0
    kept = []
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in getattr(route, 'methods', None) or set()}
        if getattr(route, 'path', None) == path and wanted in methods:
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
try:

    class V4475VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str
    _REMOVED_BATCH_PAYMENT_ROUTES = _remove_api_route('/api/visits/batch-payment', 'POST')

    @app.post('/api/visits/batch-payment')
    def v4475_create_visit_batch_payment(data: V4475VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        method = _normalize_payment_method(data.payment_method)
        sentinel = PAYMENT_SENTINELS[method]
        p = db.get(core.Patient, int(data.patient_id))
        if not p:
            raise core.HTTPException(404, 'Paciente no encontrado')
        if not data.services:
            raise core.HTTPException(400, 'Selecciona al menos una atención')
        if len(data.services) > 20:
            raise core.HTTPException(400, 'Hay demasiadas acciones seleccionadas')
        override = (data.tipo or '').strip().upper()
        if override and override not in {'N', 'S'}:
            raise core.HTTPException(400, 'Estado de paciente inválido')
        prior = db.scalar(core.select(core.func.count(core.Visit.id)).where(core.Visit.patient_id == int(p.id))) or 0
        historical_prior = bool(not prior and core.historical_summary_for_patient(p))
        first_type = override or ('S' if prior or historical_prior else 'N')
        normalized = []
        seen = set()
        for item in data.services:
            procedimiento = (item.procedimiento or '').strip().upper() or None
            key = procedimiento or 'CONSULTA'
            if key in seen:
                continue
            seen.add(key)
            valor = 40.0 if procedimiento is None else item.valor
            if valor is None:
                raise core.HTTPException(400, f'Ingresa el valor de {key}')
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                raise core.HTTPException(400, f'El valor de {key} no es válido')
            if valor < 0:
                raise core.HTTPException(400, f'El valor de {key} no es válido')
            normalized.append((procedimiento, valor))
        if not normalized:
            raise core.HTTPException(400, 'Selecciona al menos una atención')
        offline = core.is_offline_db(db)
        existing_payment_visits = list(db.scalars(core.select(core.Visit).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == int(data.patient_id), core.Visit.fecha == data.fecha, core.BillingRecord.estado != 'EMITIDA').order_by(core.Visit.id)))
        for old_visit in existing_payment_visits:
            old_visit.source_row = sentinel
        created = []
        specs = []
        for index, (procedimiento, valor) in enumerate(normalized):
            tipo = first_type if index == 0 else 'S'
            visit = core.Visit(patient_id=int(data.patient_id), fecha=data.fecha, tipo=tipo, procedimiento=procedimiento, valor=valor, observacion=data.observacion, source_row=sentinel)
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedimiento, valor))
        db.flush()
        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado='PENDIENTE')
            db.add(billing)
            billings.append(billing)
        for visit, tipo, procedimiento, valor in specs:
            service_name = procedimiento or 'CONSULTA'
            if offline:
                payload = {'patient_id': int(data.patient_id), 'fecha': data.fecha.isoformat(), 'tipo': tipo, 'procedimiento': procedimiento, 'valor': valor, 'observacion': data.observacion, 'source_row': sentinel}
                core.add_queue(db, 'visit.create', 'visit', payload, user.username, int(visit.id))
                core.audit(db, user, 'crear_atencion_multiple_offline', f'Atención local {visit.id}, paciente {p.id}, {service_name}')
            else:
                core.audit(db, user, 'crear_atencion_multiple', f'Atención {visit.id}, paciente {p.id}, estado {tipo}, servicio {service_name}')
        core.audit(db, user, 'registrar_forma_pago_atencion', f'Paciente {int(data.patient_id)}, {data.fecha}: {method}')
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
            pending_summary_local = {'billing': billing_actions['total'], 'billing_pending': billing_actions['pending'], 'billing_approved': billing_actions['approved'], 'agenda': int(summary_db.scalar(core.select(core.func.count(core.Appointment.id)).where(core.Appointment.estado == 'PENDIENTE')) or 0)}
        return {'ok': True, 'count': len(created), 'items': [core.v_dict(v) for v in created], 'offline': offline, 'pending': pending_summary_local, 'payment_method': method, 'sri_payment_code': SRI_PAYMENT_CODES[method], 'single_commit': True}

    @app.post('/api/v4475/procedures/{procedure_id}/delete')
    def v4475_delete_procedure(procedure_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        if core.is_offline_db(db):
            raise core.HTTPException(503, 'Eliminar o archivar procedimientos requiere conexión a Internet')
        proc = db.get(core.Procedure, int(procedure_id))
        if not proc:
            raise core.HTTPException(404, 'Procedimiento no encontrado')
        used = int(db.scalar(core.select(core.func.count(core.Visit.id)).where(core.func.upper(core.func.coalesce(core.Visit.procedimiento, '')) == str(proc.nombre or '').upper())) or 0)
        name = str(proc.nombre or '').strip() or f'Servicio {procedure_id}'
        if used:
            proc.activo = 0
            core.audit(db, user, 'archivar_procedimiento', f'{name}; {used} atención(es) históricas')
            db.commit()
            try:
                core.mirror_procedure_local(proc)
            except Exception:
                pass
            return {'ok': True, 'archived': True, 'used': used, 'message': 'Servicio archivado. Ya no aparecerá en nuevas atenciones y el historial se conserva.'}
        db.delete(proc)
        core.audit(db, user, 'eliminar_procedimiento', name)
        db.commit()
        try:
            with core.LocalSessionLocal() as ldb:
                local = ldb.get(core.Procedure, int(procedure_id))
                if local:
                    ldb.delete(local)
                ldb.commit()
        except Exception:
            pass
        return {'ok': True, 'archived': False, 'used': 0, 'message': 'Servicio eliminado.'}
    V4475_JS = '\n;(()=>{\n  if(window.__v4475FastSaveAndServiceDelete)return;\n  window.__v4475FastSaveAndServiceDelete=true;\n  const VERSION=\'4.4.75\';\n  let managerBusy=false;\n\n  const text=v=>String(v??\'\').replace(/\\s+/g,\' \').trim();\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\n    \'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'\n  }[c]));\n\n  function call(url,opt={}){\n    const fn=window.api;\n    if(typeof fn!==\'function\')return Promise.reject(new Error(\'API no disponible\'));\n    return fn(url,opt);\n  }\n\n  function serviceHost(){\n    return document.querySelector(\'[data-config-section="procedimientos"]\')\n      || document.querySelector(\'[data-config-section="services"]\')\n      || document.querySelector(\'#v458ServicePanel\')?.closest(\'.config-section\')\n      || document.querySelector(\'#v458ServicePanel\')?.parentElement\n      || null;\n  }\n\n  async function deleteService(id,name,button,rowEl){\n    if(!id)return;\n    if(!confirm(`¿Eliminar "${name||\'este servicio\'}"?\\n\\nSi tiene atenciones anteriores, se archivará y el historial se conservará.`))return;\n    if(button)button.disabled=true;\n    try{\n      const out=await call(\'/api/v4475/procedures/\'+Number(id)+\'/delete\',{\n        method:\'POST\',body:\'{}\'\n      });\n      rowEl?.remove();\n      try{\n        if(typeof window.loadProcedures===\'function\')await window.loadProcedures();\n      }catch(_e){}\n      setTimeout(mountManager,80);\n      const message=out?.message||\'Servicio eliminado.\';\n      if(typeof window.rpNotice===\'function\')window.rpNotice(message);\n      else alert(message);\n    }catch(e){\n      if(button)button.disabled=false;\n      alert(e?.message||String(e));\n    }\n  }\n\n  // Corrige también los botones creados por v4.4.70. El listener en captura\n  // evita que el handler antiguo intente usar DELETE después de esta acción.\n  document.addEventListener(\'click\',e=>{\n    const btn=e.target?.closest?.(\'.v4470-proc-delete\');\n    if(!btn||btn.classList.contains(\'v4475-delete\'))return;\n    e.preventDefault();\n    e.stopImmediatePropagation();\n    const row=btn.closest(\'.v4470-proc-row\');\n    const id=Number(btn.dataset.delete||row?.dataset.id||0);\n    const name=text(row?.querySelector(\'b\')?.textContent||\'Servicio\');\n    deleteService(id,name,btn,row);\n  },true);\n\n  async function mountManager(){\n    if(managerBusy)return;\n    const host=serviceHost();\n    if(!host)return;\n    // Si el administrador viejo ya está visible, no duplicamos la lista:\n    // sus botones quedaron reparados por el listener anterior.\n    if(host.querySelector(\'#v4470ProcedureManager\'))return;\n\n    managerBusy=true;\n    try{\n      const rows=await call(\'/api/procedures\');\n      let box=host.querySelector(\'#v4475ProcedureManager\');\n      if(!box){\n        box=document.createElement(\'div\');\n        box.id=\'v4475ProcedureManager\';\n        box.className=\'v4470-proc-manager\';\n        host.appendChild(box);\n      }\n      const list=Array.isArray(rows)?rows:[];\n      box.innerHTML=`<div class="v4470-proc-manager-head"><div><h4>Eliminar servicios y precios</h4><small>Los servicios con historial se archivan; las atenciones antiguas no cambian.</small></div></div>\n        <div class="v4470-proc-list">${\n          list.map(p=>`<div class="v4470-proc-row" data-v4475-id="${Number(p.id)}">\n            <b>${esc(p.nombre)}</b>\n            <span>${p.valor_default==null?\'Sin precio\':\'$\'+Number(p.valor_default).toFixed(2)}</span>\n            <button type="button" class="v4470-proc-delete v4475-delete" data-v4475-delete="${Number(p.id)}">Eliminar</button>\n          </div>`).join(\'\')||\'<small>No hay servicios activos.</small>\'\n        }</div>`;\n      box.querySelectorAll(\'[data-v4475-delete]\').forEach(btn=>{\n        btn.addEventListener(\'click\',e=>{\n          e.preventDefault();e.stopPropagation();\n          const row=btn.closest(\'.v4470-proc-row\');\n          const id=Number(btn.dataset.v4475Delete||0);\n          const name=text(row?.querySelector(\'b\')?.textContent||\'Servicio\');\n          deleteService(id,name,btn,row);\n        });\n      });\n    }catch(_e){\n      // La pantalla de configuración sigue operativa aunque Neon esté temporalmente caído.\n    }finally{\n      managerBusy=false;\n    }\n  }\n\n  function hookLoader(){\n    const fn=window.loadProcedures;\n    if(typeof fn!==\'function\'||fn.__v4475DeleteHook)return;\n    const wrapped=async function(){\n      const out=await fn.apply(this,arguments);\n      setTimeout(mountManager,60);\n      return out;\n    };\n    wrapped.__v4475DeleteHook=true;\n    window.loadProcedures=wrapped;\n  }\n\n  document.addEventListener(\'click\',e=>{\n    const tab=e.target?.closest?.(\'[data-config-tab]\');\n    const key=String(tab?.dataset?.configTab||\'\').toLowerCase();\n    if(key===\'procedimientos\'||key===\'services\'){\n      setTimeout(()=>{hookLoader();mountManager()},90);\n    }\n  });\n\n  function boot(){\n    hookLoader();\n    mountManager();\n    setTimeout(()=>{hookLoader();mountManager()},400);\n    setTimeout(()=>{hookLoader();mountManager()},1400);\n  }\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  else boot();\n\n  // Igual que v4.4.73/74: solo sustitución estática de texto, sin observer nuevo.\n  try{\n    const badges=document.querySelectorAll(\'.v460-version,#currentVersionBadge\');\n    badges.forEach(el=>{if(text(el.textContent)!==\'v\'+VERSION)el.textContent=\'v\'+VERSION});\n  }catch(_e){}\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '').replace("const VERSION='4.4.74';", "const VERSION='4.4.75';") + '\n' + V4475_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.75 fast save/service delete patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4475/health')
def v4475_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'batch_payment_single_commit': True, 'service_delete_post_endpoint': True, 'background_print_preserved': True, 'base_ui': '4.4.74 / stable 4.4.73', 'uses_new_dom_observer': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4475 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4475, '__name__', 'app_patch_4475')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4475, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4475, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4475, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PAYMENT_SENTINELS' in globals(): setattr(_rf_snapshot_app_patch_4475, 'PAYMENT_SENTINELS', globals()['PAYMENT_SENTINELS'])
if 'SRI_PAYMENT_CODES' in globals(): setattr(_rf_snapshot_app_patch_4475, 'SRI_PAYMENT_CODES', globals()['SRI_PAYMENT_CODES'])
if 'V4475VisitBatchPaymentIn' in globals(): setattr(_rf_snapshot_app_patch_4475, 'V4475VisitBatchPaymentIn', globals()['V4475VisitBatchPaymentIn'])
if 'V4475_JS' in globals(): setattr(_rf_snapshot_app_patch_4475, 'V4475_JS', globals()['V4475_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4475, '_', globals()['_'])
if '_REMOVED_BATCH_PAYMENT_ROUTES' in globals(): setattr(_rf_snapshot_app_patch_4475, '_REMOVED_BATCH_PAYMENT_ROUTES', globals()['_REMOVED_BATCH_PAYMENT_ROUTES'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4475, '_mod', globals()['_mod'])
if '_normalize_payment_method' in globals(): setattr(_rf_snapshot_app_patch_4475, '_normalize_payment_method', globals()['_normalize_payment_method'])
if '_remove_api_route' in globals(): setattr(_rf_snapshot_app_patch_4475, '_remove_api_route', globals()['_remove_api_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4475, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4475, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4475, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4475, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4475, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4475__previous' in globals(): setattr(_rf_snapshot_app_patch_4475, 'previous', globals()['_rf_alias_app_patch_4475__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4475, 'uvicorn', globals()['uvicorn'])
if 'v4475_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_patch_4475, 'v4475_create_visit_batch_payment', globals()['v4475_create_visit_batch_payment'])
if 'v4475_delete_procedure' in globals(): setattr(_rf_snapshot_app_patch_4475, 'v4475_delete_procedure', globals()['v4475_delete_procedure'])
if 'v4475_health' in globals(): setattr(_rf_snapshot_app_patch_4475, 'v4475_health', globals()['v4475_health'])
_rf_layers['app_patch_4475'] = _rf_snapshot_app_patch_4475

# ---- app_patch_4476 ----
import json as _json
from datetime import date as _date, datetime as _datetime, timedelta as _timedelta
_rf_alias_app_patch_4476__previous = _rf_layers['app_patch_4475']
core = _rf_alias_app_patch_4476__previous.core
app = _rf_alias_app_patch_4476__previous.app
APP_VERSION = '4.4.76'
_mod = _rf_alias_app_patch_4476__previous
_seen = set()
for _ in range(32):
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

def _remove_api_route(path: str, method: str) -> int:
    wanted = str(method or '').upper()
    kept = []
    removed = 0
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in getattr(route, 'methods', None) or set()}
        if getattr(route, 'path', None) == path and wanted in methods:
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

def _active_patient_trash_snapshots() -> list[dict]:
    out = []
    try:
        with core.LocalSessionLocal() as ldb:
            try:
                core._ops_ensure_trash_table(ldb)
            except Exception:
                pass
            rows = list(ldb.scalars(core.select(core.TrashItem).where(core.TrashItem.entity_type == 'patient', core.TrashItem.restored_at.is_(None))))
            for item in rows:
                try:
                    snap = _json.loads(item.snapshot_json or '{}')
                except Exception:
                    continue
                patient = snap.get('patient') if isinstance(snap, dict) else None
                if not isinstance(patient, dict):
                    continue
                try:
                    pid = int(patient.get('id') or item.entity_id or 0)
                except Exception:
                    pid = 0
                if not pid:
                    continue
                out.append({'trash_id': int(item.id), 'patient_id': pid, 'snapshot': snap, 'deleted_at': item.deleted_at})
    except Exception:
        return []
    return out

def _active_trashed_patient_ids() -> set[int]:
    return {int(x['patient_id']) for x in _active_patient_trash_snapshots()}

def _json_date(value):
    if isinstance(value, (_date, _datetime)):
        return value.isoformat()
    return value

def _patient_snapshot(patient) -> dict:
    return {'id': int(patient.id), 'cedula': getattr(patient, 'cedula', None), 'nombre': getattr(patient, 'nombre', None), 'fecha_nacimiento': _json_date(getattr(patient, 'fecha_nacimiento', None)), 'celular': getattr(patient, 'celular', None), 'correo': getattr(patient, 'correo', None), 'lugar': getattr(patient, 'lugar', None), 'notas': getattr(patient, 'notas', None), 'created_at': _json_date(getattr(patient, 'created_at', None))}

def _fiscal_line_snapshot(visit, billing) -> dict:
    return {'visit': {'id': int(visit.id), 'patient_id': int(visit.patient_id), 'fecha': _json_date(visit.fecha), 'tipo': visit.tipo, 'procedimiento': visit.procedimiento, 'valor': float(visit.valor) if visit.valor is not None else None, 'observacion': visit.observacion, 'source_row': getattr(visit, 'source_row', None), 'created_at': _json_date(getattr(visit, 'created_at', None))}, 'billing': {'id': int(billing.id), 'visit_id': int(billing.visit_id), 'estado': billing.estado, 'numero_factura': billing.numero_factura, 'approved_at': _json_date(billing.approved_at), 'emitted_at': _json_date(billing.emitted_at), 'created_at': _json_date(getattr(billing, 'created_at', None))}}

def _emission_payload(record) -> dict:
    try:
        value = _json.loads(record.response_json or '{}')
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def _save_emission_payload(record, payload: dict) -> None:
    record.response_json = _json.dumps(payload, ensure_ascii=False, default=_json_date)

def _preserve_patient_fiscal_history(db, patient) -> int:
    """Adjunta a AzurEmission un snapshot mínimo antes de borrar el paciente."""
    pid = int(patient.id)
    rows = db.execute(core.select(core.BillingRecord, core.Visit).join(core.Visit, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == pid, core.BillingRecord.estado == 'EMITIDA').order_by(core.Visit.fecha, core.Visit.id)).all()
    if not rows:
        return 0
    emissions = list(db.scalars(core.select(core.AzurEmission).where(core.AzurEmission.patient_id == pid).order_by(core.AzurEmission.fecha, core.AzurEmission.id)))
    if not emissions:
        return 0
    p_snap = _patient_snapshot(patient)
    changed = 0
    for emission in emissions:
        payload = _emission_payload(emission)
        ids = set()
        for raw in payload.get('_billing_visit_ids') or []:
            try:
                ids.add(int(raw))
            except Exception:
                pass
        matched = []
        for billing, visit in rows:
            if visit.fecha != emission.fecha:
                continue
            same_invoice = bool(emission.numero_factura and billing.numero_factura and (str(emission.numero_factura) == str(billing.numero_factura)))
            if ids and int(visit.id) not in ids and (not same_invoice):
                continue
            if not ids and emission.numero_factura and billing.numero_factura and (not same_invoice):
                continue
            matched.append(_fiscal_line_snapshot(visit, billing))
        if not matched:
            continue
        payload['_patient_snapshot'] = p_snap
        payload['_billing_snapshot'] = matched
        payload['_snapshot_version'] = '4.4.76'
        _save_emission_payload(emission, payload)
        changed += 1
    return changed

def _trash_emitted_lines(entry: dict) -> list[dict]:
    snap = entry.get('snapshot') or {}
    patient = snap.get('patient') or {}
    result = []
    for visit in snap.get('visits') or []:
        if not isinstance(visit, dict):
            continue
        billing = visit.get('billing') or {}
        if str(billing.get('estado') or '').upper() != 'EMITIDA':
            continue
        result.append({'patient': patient, 'visit': {k: v for k, v in visit.items() if k != 'billing'}, 'billing': billing})
    return result

def _backfill_active_trash_to_emissions(db) -> int:
    """Repara también pacientes borrados antes de instalar 4.4.76."""
    entries = _active_patient_trash_snapshots()
    if not entries:
        return 0
    changed_records = []
    for entry in entries:
        pid = int(entry['patient_id'])
        lines = _trash_emitted_lines(entry)
        if not lines:
            continue
        dates = sorted({str(x['visit'].get('fecha') or '')[:10] for x in lines if str(x['visit'].get('fecha') or '')[:10]})
        parsed_dates = []
        for raw in dates:
            try:
                parsed_dates.append(_date.fromisoformat(raw))
            except Exception:
                pass
        if not parsed_dates:
            continue
        emissions = list(db.scalars(core.select(core.AzurEmission).where(core.AzurEmission.patient_id == pid, core.AzurEmission.fecha.in_(parsed_dates))))
        for emission in emissions:
            payload = _emission_payload(emission)
            if payload.get('_patient_snapshot') and payload.get('_billing_snapshot'):
                continue
            matched = []
            for line in lines:
                v = line['visit']
                b = line['billing']
                if str(v.get('fecha') or '')[:10] != emission.fecha.isoformat():
                    continue
                same_invoice = bool(emission.numero_factura and b.get('numero_factura') and (str(emission.numero_factura) == str(b.get('numero_factura'))))
                if emission.numero_factura and b.get('numero_factura') and (not same_invoice):
                    continue
                matched.append({'visit': v, 'billing': b})
            if not matched:
                continue
            payload['_patient_snapshot'] = entry['snapshot'].get('patient') or {}
            payload['_billing_snapshot'] = matched
            payload['_snapshot_version'] = '4.4.76-backfill'
            _save_emission_payload(emission, payload)
            changed_records.append(emission)
    if changed_records:
        try:
            db.commit()
        except Exception:
            db.rollback()
            return 0
        if not core.is_offline_db(db):
            for record in changed_records:
                try:
                    core.mirror_azur_emission_to_local(record)
                except Exception:
                    pass
    return len(changed_records)

def _date_allowed(value, desde=None, hasta=None, *, default_history=True) -> bool:
    try:
        d = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
    except Exception:
        return False
    if desde and d < desde:
        return False
    if hasta and d > hasta:
        return False
    if default_history and (not desde) and (not hasta):
        if d < _date.today() - _timedelta(days=6):
            return False
    return True

def _archived_emitted_items(db, desde=None, hasta=None) -> list[dict]:
    """Reconstruye facturas emitidas de pacientes eliminados sin revivirlos."""
    hidden = _active_trashed_patient_ids()
    if not hidden:
        return []
    emissions = list(db.scalars(core.select(core.AzurEmission).where(core.AzurEmission.patient_id.in_(sorted(hidden))).order_by(core.AzurEmission.fecha.desc(), core.AzurEmission.id.desc())))
    by_patient_date = {}
    for emission in emissions:
        by_patient_date.setdefault((int(emission.patient_id), emission.fecha.isoformat()), []).append(emission)
    items = []
    seen = set()
    for emission in emissions:
        if not _date_allowed(emission.fecha, desde, hasta):
            continue
        payload = _emission_payload(emission)
        patient = payload.get('_patient_snapshot')
        lines = payload.get('_billing_snapshot')
        if not isinstance(patient, dict) or not isinstance(lines, list):
            continue
        az = core.azur_emission_dict(emission)
        for line in lines:
            if not isinstance(line, dict):
                continue
            visit = line.get('visit') or {}
            billing = line.get('billing') or {}
            if str(billing.get('estado') or '').upper() != 'EMITIDA':
                continue
            invoice = str(billing.get('numero_factura') or emission.numero_factura or '')
            key = (int(patient.get('id') or emission.patient_id or 0), int(visit.get('id') or 0), int(billing.get('id') or 0), invoice)
            if key in seen:
                continue
            seen.add(key)
            items.append({'billing': billing, 'visit': visit, 'patient': patient, 'azur': az, 'billing_group_key': f"{int(patient.get('id') or emission.patient_id)}:{str(visit.get('fecha') or emission.fecha.isoformat())[:10]}:EMITIDA:{invoice or int(emission.id)}", 'archived_deleted_patient': True})
    for entry in _active_patient_trash_snapshots():
        pid = int(entry['patient_id'])
        for line in _trash_emitted_lines(entry):
            patient = line['patient']
            visit = line['visit']
            billing = line['billing']
            raw_date = str(visit.get('fecha') or '')[:10]
            if not _date_allowed(raw_date, desde, hasta):
                continue
            invoice = str(billing.get('numero_factura') or '')
            key = (pid, int(visit.get('id') or 0), int(billing.get('id') or 0), invoice)
            if key in seen:
                continue
            seen.add(key)
            az_candidates = by_patient_date.get((pid, raw_date), [])
            az = None
            for emission in az_candidates:
                if invoice and str(emission.numero_factura or '') == invoice:
                    az = emission
                    break
            if az is None and az_candidates:
                az = az_candidates[0]
            items.append({'billing': billing, 'visit': visit, 'patient': patient, 'azur': core.azur_emission_dict(az) if az else None, 'billing_group_key': f"{pid}:{raw_date}:EMITIDA:{invoice or int(billing.get('id') or 0)}", 'archived_deleted_patient': True})
    return items

def _billing_counts(db, archived_items: list[dict] | None=None) -> dict:
    hidden = _active_trashed_patient_ids()
    rows = db.execute(core.select(core.BillingRecord, core.Visit).join(core.Visit, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.fecha >= core.BILLING_QUEUE_START_DATE)).all()
    pending = set()
    emitted = set()
    for billing, visit in rows:
        pid = int(visit.patient_id)
        if pid in hidden:
            continue
        state = str(billing.estado or '').upper()
        if state in {'PENDIENTE', 'APROBADA'}:
            pending.add((pid, visit.fecha.isoformat()))
        elif state == 'EMITIDA':
            inv = str(billing.numero_factura or '').strip()
            emitted.add((pid, visit.fecha.isoformat(), inv or f'visit-{int(visit.id)}'))
    for item in archived_items or []:
        p = item.get('patient') or {}
        v = item.get('visit') or {}
        b = item.get('billing') or {}
        try:
            pid = int(p.get('id') or v.get('patient_id') or 0)
        except Exception:
            pid = 0
        fecha = str(v.get('fecha') or '')[:10]
        inv = str(b.get('numero_factura') or '').strip()
        if pid and fecha:
            emitted.add((pid, fecha, inv or f"visit-{int(v.get('id') or 0)}"))
    rejected = set()
    try:
        emissions = list(db.scalars(core.select(core.AzurEmission).where(core.AzurEmission.estado == 'RECHAZADA')))
        for x in emissions:
            if int(x.patient_id) not in hidden:
                rejected.add((int(x.patient_id), x.fecha.isoformat(), int(x.id)))
    except Exception:
        pass
    return {'PENDIENTE': len(pending), 'APROBADA': 0, 'EMITIDA': len(emitted), 'RECHAZADA': len(rejected)}

def _billing_action_counts_v4476(db) -> dict[str, int]:
    hidden = _active_trashed_patient_ids()
    rows = db.execute(core.select(core.Visit.patient_id, core.Visit.fecha, core.BillingRecord.estado).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.fecha >= core.BILLING_QUEUE_START_DATE)).all()
    keys = {(int(pid), fecha) for pid, fecha, estado in rows if int(pid) not in hidden and str(estado or '').upper() in {'PENDIENTE', 'APROBADA'}}
    total = len(keys)
    return {'pending': total, 'approved': 0, 'total': total}
try:
    core._billing_action_counts = _billing_action_counts_v4476
    _stable_billing_group_records = core.billing_group_records

    def _billing_group_records_v4476(db, patient_id: int, fecha):
        if int(patient_id) in _active_trashed_patient_ids():
            return []
        return _stable_billing_group_records(db, int(patient_id), fecha)
    core.billing_group_records = _billing_group_records_v4476
    _stable_billing_list = core.billing_list
    _remove_api_route('/api/billing', 'GET')

    @app.get('/api/billing')
    def v4476_billing_list(estado: str='TODAS', desde: _date | None=None, hasta: _date | None=None, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        try:
            _backfill_active_trash_to_emissions(db)
        except Exception:
            pass
        result = dict(_stable_billing_list(estado, desde, hasta, db, user) or {})
        requested = str(estado or 'TODAS').strip().upper()
        hidden = _active_trashed_patient_ids()
        visible = []
        for item in list(result.get('items') or []):
            try:
                pid = int((item.get('patient') or {}).get('id') or 0)
            except Exception:
                pid = 0
            if pid in hidden:
                continue
            visible.append(item)
        archived = []
        if requested == 'EMITIDA':
            archived = _archived_emitted_items(db, desde, hasta)
            dedupe = set()
            merged = []
            for item in visible + archived:
                p = item.get('patient') or {}
                v = item.get('visit') or {}
                b = item.get('billing') or {}
                key = (int(p.get('id') or v.get('patient_id') or 0), int(v.get('id') or 0), int(b.get('id') or 0), str(b.get('numero_factura') or ''))
                if key in dedupe:
                    continue
                dedupe.add(key)
                merged.append(item)
            visible = merged
        result['items'] = visible
        result['counts'] = _billing_counts(db, archived if requested == 'EMITIDA' else None)
        result['v4476_deleted_patients_filtered'] = True
        result['v4476_archived_emitted_history'] = bool(archived)
        return result
    _stable_safe_delete_patient = core.ops_safe_delete_patient
    _remove_api_route('/api/safety/patients/{pid}', 'DELETE')

    @app.delete('/api/safety/patients/{pid}')
    def v4476_safe_delete_patient(pid: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        patient = db.get(core.Patient, int(pid))
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        try:
            _preserve_patient_fiscal_history(db, patient)
            db.flush()
        except Exception as exc:
            try:
                core.logging.getLogger(__name__).warning('v4.4.76: no se pudo preparar snapshot fiscal de paciente %s: %s', pid, exc)
            except Exception:
                pass
        return _stable_safe_delete_patient(int(pid), db, user)
    _stable_safe_delete_visit = core.ops_safe_delete_visit
    _remove_api_route('/api/safety/visits/{visit_id}', 'DELETE')

    @app.delete('/api/safety/visits/{visit_id}')
    def v4476_safe_delete_visit(visit_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        visit = db.get(core.Visit, int(visit_id))
        if not visit:
            raise core.HTTPException(404, 'Atención no encontrada')
        billing = db.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id == int(visit_id)))
        if billing and str(billing.estado or '').upper() == 'EMITIDA':
            raise core.HTTPException(409, 'Esta atención ya tiene una factura emitida y no se puede borrar. El historial fiscal debe conservarse.')
        return _stable_safe_delete_visit(int(visit_id), db, user)

    @app.get('/api/v4476/billing/prior-emissions')
    def v4476_prior_emissions(patient_id: int, fecha: _date, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        rows = list(db.scalars(core.select(core.AzurEmission).where(core.AzurEmission.patient_id == int(patient_id), core.AzurEmission.fecha == fecha).order_by(core.AzurEmission.id.desc())))
        sent = [x for x in rows if str(x.clave_acceso or '').strip() or str(x.numero_factura or '').strip()]
        return {'count': len(sent), 'items': [{'id': int(x.id), 'estado': x.estado, 'numero_factura': x.numero_factura, 'has_clave_acceso': bool(x.clave_acceso)} for x in sent]}

    class V4476ProcedureUpsertIn(core.BaseModel):
        nombre: str
        valor_default: float | None = None

    @app.post('/api/v4476/procedures/upsert')
    def v4476_procedure_upsert(data: V4476ProcedureUpsertIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        if core.is_offline_db(db):
            raise core.HTTPException(503, 'Agregar o reactivar servicios requiere conexión a Internet')
        name = ' '.join(str(data.nombre or '').split()).upper()
        if not name:
            raise core.HTTPException(400, 'Escribe el nombre del servicio')
        price = data.valor_default
        if price is not None:
            try:
                price = float(price)
            except Exception:
                raise core.HTTPException(400, 'El precio no es válido')
            if price < 0:
                raise core.HTTPException(400, 'El precio no es válido')
        proc = db.scalar(core.select(core.Procedure).where(core.Procedure.nombre == name))
        if proc:
            if int(getattr(proc, 'activo', 1) or 0) == 1:
                raise core.HTTPException(409, 'Ese servicio ya existe')
            proc.activo = 1
            proc.valor_default = price
            core.audit(db, user, 'reactivar_procedimiento', name)
            db.commit()
            try:
                core.mirror_procedure_local(proc)
            except Exception:
                pass
            return {'ok': True, 'restored': True, 'id': int(proc.id), 'nombre': proc.nombre, 'valor_default': float(proc.valor_default) if proc.valor_default is not None else None}
        proc = core.Procedure(nombre=name, valor_default=price, activo=1)
        db.add(proc)
        core.audit(db, user, 'crear_procedimiento', name)
        db.commit()
        try:
            core.mirror_procedure_local(proc)
        except Exception:
            pass
        return {'ok': True, 'restored': False, 'id': int(proc.id), 'nombre': proc.nombre, 'valor_default': float(proc.valor_default) if proc.valor_default is not None else None}
    V4476_CSS = '\n/* v4.4.76 — Servicios y precios: una sola vista, sin tres columnas duplicadas */\n[data-config-section="procedimientos"] > .v4476-service-old{\n  display:none!important;\n}\n#v4476ServicePanel{\n  width:100%;box-sizing:border-box;display:block!important;\n  padding:0!important;margin:0!important\n}\n.v4476-service-shell{\n  width:100%;box-sizing:border-box;border:1px solid #d7e3ed;border-radius:16px;\n  background:#fff;overflow:hidden;box-shadow:0 5px 18px rgba(35,67,94,.05)\n}\n.v4476-service-head{\n  display:flex;align-items:flex-start;justify-content:space-between;gap:14px;\n  padding:16px 18px;border-bottom:1px solid #e5edf4;background:#f8fbfe\n}\n.v4476-service-head h3{margin:0!important;font-size:15px!important;color:#294a66!important}\n.v4476-service-head p{margin:3px 0 0!important;font-size:10px!important;color:#71869a!important}\n.v4476-service-count{\n  min-width:34px;height:28px;padding:0 9px;border-radius:999px;background:#eaf3fb;\n  color:#315f84;display:grid;place-items:center;font-size:11px;font-weight:950\n}\n.v4476-service-new{\n  display:grid;grid-template-columns:minmax(0,1fr) 130px auto;gap:8px;\n  padding:13px 18px;border-bottom:1px solid #e9eff5;background:#fff\n}\n.v4476-service-new input,.v4476-service-search,.v4476-service-price{\n  min-height:36px!important;border:1px solid #ccd9e5!important;border-radius:9px!important;\n  background:#fff!important;color:#304b63!important;padding:7px 9px!important;\n  font-size:11px!important;box-sizing:border-box!important\n}\n.v4476-service-new button,.v4476-service-actions button{\n  min-height:34px!important;border-radius:9px!important;padding:7px 11px!important;\n  font-size:10px!important;font-weight:900!important;cursor:pointer!important\n}\n.v4476-service-add{\n  border:1px solid #72a98a!important;background:#eaf7ef!important;color:#286447!important\n}\n.v4476-service-tools{padding:10px 18px;border-bottom:1px solid #edf2f6;background:#fbfdff}\n.v4476-service-search{width:100%!important}\n.v4476-service-list{display:grid;grid-template-columns:1fr;gap:0}\n.v4476-service-row{\n  display:flex;align-items:center;justify-content:space-between;gap:16px;\n  padding:11px 18px;border-bottom:1px solid #edf2f6;background:#fff\n}\n.v4476-service-row:last-child{border-bottom:0}\n.v4476-service-name{min-width:0;flex:1}\n.v4476-service-name b{\n  display:block;font-size:11px;color:#304d66;white-space:normal;overflow-wrap:anywhere\n}\n.v4476-service-name small{display:block;margin-top:2px;font-size:8px;color:#8797a6}\n.v4476-service-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}\n.v4476-service-price{width:105px!important;text-align:right;font-weight:850}\n.v4476-service-save{\n  border:1px solid #b8cada!important;background:#f6f9fc!important;color:#3e607b!important\n}\n.v4476-service-delete{\n  border:1px solid #dfb4b4!important;background:#fff6f6!important;color:#963d3d!important\n}\n.v4476-service-empty{padding:25px 18px;text-align:center;color:#778b9e;font-size:11px}\n.v4476-service-note{\n  padding:10px 18px;background:#fbfdff;border-top:1px solid #edf2f6;\n  color:#7a8c9d;font-size:9px;line-height:1.4\n}\n.v4476-archived-billing-note{\n  margin:9px 0;padding:8px 10px;border-radius:9px;border:1px solid #d7e2ec;\n  background:#f7fafc;color:#64788d;font-size:10px;font-weight:750\n}\n@media(max-width:720px){\n  .v4476-service-new{grid-template-columns:1fr}\n  .v4476-service-row{align-items:flex-start;flex-direction:column;gap:8px}\n  .v4476-service-actions{width:100%;justify-content:flex-start}\n  .v4476-service-price{flex:1;width:auto!important;min-width:110px}\n}\n'
    V4476_JS = '\n;(()=>{\n  if(window.__v4476BillingAndServices)return;\n  window.__v4476BillingAndServices=true;\n  const VERSION=\'4.4.76\';\n  let serviceRows=[];\n  let serviceBusy=false;\n\n  const text=v=>String(v??\'\').replace(/\\s+/g,\' \').trim();\n  const norm=v=>text(v).normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').toLowerCase();\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\n    \'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'\n  }[c]));\n  const money=v=>{\n    const n=Number(v);\n    return Number.isFinite(n)?\'$\'+n.toFixed(2):\'Sin precio\';\n  };\n  const apiCall=(url,opt={})=>{\n    const fn=window.api;\n    return typeof fn===\'function\'?fn(url,opt):Promise.reject(new Error(\'API no disponible\'));\n  };\n\n  // -----------------------------------------------------------------------\n  // Facturación: emitidas reales + pacientes borrados fuera de Por emitir.\n  // -----------------------------------------------------------------------\n  function emittedKey(item){\n    const p=item?.patient||{},v=item?.visit||{},b=item?.billing||{},a=item?.azur||{};\n    return [\n      Number(p.id||v.patient_id||0),\n      String(v.fecha||\'\').slice(0,10),\n      String(b.numero_factura||a.numero_factura||b.emitted_at||b.id||\'\')\n    ].join(\'|\');\n  }\n\n  function groupEmitted(items){\n    const map=new Map();\n    for(const item of (Array.isArray(items)?items:[])){\n      const key=emittedKey(item);\n      let g=map.get(key);\n      if(!g){\n        g={\n          patient:item.patient||{},\n          fecha:String(item?.visit?.fecha||\'\').slice(0,10),\n          items:[],\n          archived_deleted:!!item.archived_deleted_patient\n        };\n        map.set(key,g);\n      }\n      g.items.push(item);\n      if(item.archived_deleted_patient)g.archived_deleted=true;\n    }\n    return [...map.values()].sort((a,b)=>{\n      const da=String(a.fecha||\'\'),db=String(b.fecha||\'\');\n      if(da!==db)return db.localeCompare(da);\n      const ia=Number(a.items?.[0]?.billing?.id||0),ib=Number(b.items?.[0]?.billing?.id||0);\n      return ib-ia;\n    });\n  }\n\n  function updateEmittedCount(count){\n    const box=document.querySelector(\'#billingSummary\');if(!box)return;\n    const btn=[...box.querySelectorAll(\'button\')].find(b=>norm(b.textContent).includes(\'emitida\'));\n    if(!btn)return;\n    const n=btn.querySelector(\'b\');\n    if(n)n.textContent=String(Number(count||0));\n  }\n\n  async function renderEmittedHistory(){\n    const state=String(document.querySelector(\'#bEstado\')?.value||\'\').toUpperCase();\n    if(state!==\'EMITIDA\')return;\n    const list=document.querySelector(\'#billingList\');if(!list)return;\n    try{\n      const d=await apiCall(\'/api/billing?estado=EMITIDA\');\n      const groups=groupEmitted(d?.items||[]);\n      try{billingGroupsCache=groups}catch(_e){}\n      list.innerHTML=groups.length\n        ?groups.map(g=>{\n            let html=\'\';\n            try{html=typeof window.billingCardHtml===\'function\'?window.billingCardHtml(g):\'\'}catch(_e){html=\'\'}\n            if(!html){\n              const total=(g.items||[]).reduce((s,x)=>s+Number(x?.visit?.valor||0),0);\n              const inv=String(g.items?.[0]?.billing?.numero_factura||g.items?.[0]?.azur?.numero_factura||\'\');\n              html=`<article class="billing-card emitida"><div class="billing-card-head"><div><div class="billing-patient-name">${esc(g.patient?.nombre||\'Paciente\')}</div><div class="billing-meta"><span><b>Cédula:</b> ${esc(g.patient?.cedula||\'Sin cédula\')}</span><span><b>Fecha:</b> ${esc(g.fecha)}</span></div></div><span class="billing-status emitida">EMITIDA</span></div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${money(total)}</strong></div>${inv?`<div class="billing-invoice-number"><span>Factura</span><b>${esc(inv)}</b></div>`:\'\'}</div></article>`;\n            }\n            return html;\n          }).join(\'\')\n        :\'<div class="billing-empty">No hay facturas emitidas en los últimos 7 días.</div>\';\n      [...list.querySelectorAll(\'.billing-card\')].forEach((card,i)=>{\n        const g=groups[i];\n        if(!g?.archived_deleted)return;\n        card.dataset.v4476Archived=\'1\';\n        const note=document.createElement(\'div\');\n        note.className=\'v4476-archived-billing-note\';\n        note.textContent=\'Histórico fiscal conservado · este paciente fue eliminado de Recepción.\';\n        const lines=card.querySelector(\'.billing-lines\');\n        if(lines)lines.insertAdjacentElement(\'beforebegin\',note);\n        else card.querySelector(\'.billing-card-foot\')?.insertAdjacentElement(\'beforebegin\',note);\n        // Evitar acciones que intenten abrir una ficha que ya no existe.\n        card.querySelector(\'.billing-actions\')?.remove();\n      });\n      updateEmittedCount(groups.length);\n    }catch(e){\n      console.warn(\'v4476_emitted_history_failed\',e);\n    }\n  }\n\n  const stableLoadBilling=window.loadBilling;\n  if(typeof stableLoadBilling===\'function\'){\n    window.loadBilling=async function(){\n      const out=await stableLoadBilling.apply(this,arguments);\n      if(String(document.querySelector(\'#bEstado\')?.value||\'\').toUpperCase()===\'EMITIDA\'){\n        await renderEmittedHistory();\n      }\n      return out;\n    };\n  }\n\n  const stableSetBillingStatus=window.setBillingStatus;\n  if(typeof stableSetBillingStatus===\'function\'){\n    window.setBillingStatus=async function(next){\n      const out=await stableSetBillingStatus.apply(this,arguments);\n      if(String(next||\'\').toUpperCase()===\'EMITIDA\')await renderEmittedHistory();\n      return out;\n    };\n  }\n\n  // Doble factura el mismo día: no bloquea un cobro legítimo adicional, pero\n  // exige una advertencia extra para evitar repetir una factura por accidente.\n  const stableApproveBilling=window.approveBilling;\n  if(typeof stableApproveBilling===\'function\'){\n    window.approveBilling=async function(patientId,fecha){\n      try{\n        const d=await apiCall(\n          \'/api/v4476/billing/prior-emissions?patient_id=\'+Number(patientId)\n          +\'&fecha=\'+encodeURIComponent(String(fecha||\'\').slice(0,10))\n        );\n        if(Number(d?.count||0)>0){\n          const nums=(d.items||[]).map(x=>x.numero_factura).filter(Boolean).join(\', \');\n          const msg=`Este paciente ya tiene ${Number(d.count)} factura${Number(d.count)===1?\'\':\'s\'} enviada${Number(d.count)===1?\'\':\'s\'} en esta fecha${nums?\': \'+nums:\'\'}.\\n\\nLa ficha actual es una atención adicional POR EMITIR. ¿Confirmas que realmente deseas generar otra factura?`;\n          const ok=typeof window.rpConfirm===\'function\'\n            ?await window.rpConfirm(msg,\'Confirmar factura adicional\')\n            :window.confirm(msg);\n          if(!ok)return;\n        }\n      }catch(_e){}\n      return stableApproveBilling.apply(this,arguments);\n    };\n  }\n\n  // -----------------------------------------------------------------------\n  // Servicios y precios: un panel único, sin tres columnas redundantes.\n  // -----------------------------------------------------------------------\n  function serviceSection(){\n    return document.querySelector(\'[data-config-section="procedimientos"]\')\n      ||document.querySelector(\'[data-config-section="services"]\')\n      ||null;\n  }\n\n  function markOldServiceUi(section){\n    if(!section)return;\n    [...section.children].forEach(el=>{\n      if(el.id===\'v4476ServicePanel\')return;\n      el.classList.add(\'v4476-service-old\');\n    });\n  }\n\n  function filteredServices(){\n    const q=norm(document.querySelector(\'#v4476ServiceSearch\')?.value||\'\');\n    if(!q)return serviceRows;\n    return serviceRows.filter(x=>norm(x.nombre).includes(q));\n  }\n\n  function renderServiceRows(){\n    const list=document.querySelector(\'#v4476ServiceList\');if(!list)return;\n    const rows=filteredServices();\n    list.innerHTML=rows.length?rows.map(p=>`\n      <div class="v4476-service-row" data-service-id="${Number(p.id)}">\n        <div class="v4476-service-name">\n          <b>${esc(p.nombre||\'SERVICIO\')}</b>\n          <small>${p.valor_default==null?\'Sin precio configurado\':\'Precio actual \'+money(p.valor_default)}</small>\n        </div>\n        <div class="v4476-service-actions">\n          <input class="v4476-service-price" type="number" min="0" step="0.01"\n            value="${p.valor_default==null?\'\':Number(p.valor_default).toFixed(2)}"\n            aria-label="Precio de ${esc(p.nombre||\'servicio\')}">\n          <button type="button" class="v4476-service-save" data-save-service="${Number(p.id)}">Guardar precio</button>\n          <button type="button" class="v4476-service-delete" data-delete-service="${Number(p.id)}">Eliminar</button>\n        </div>\n      </div>`).join(\'\')\n      :\'<div class="v4476-service-empty">No hay servicios que coincidan.</div>\';\n  }\n\n  async function fetchServices(){\n    const rows=await apiCall(\'/api/procedures\');\n    serviceRows=Array.isArray(rows)?rows:[];\n    const count=document.querySelector(\'#v4476ServiceCount\');\n    if(count)count.textContent=String(serviceRows.length);\n    renderServiceRows();\n  }\n\n  async function mountServicePanel(){\n    if(serviceBusy)return;\n    const section=serviceSection();if(!section)return;\n    serviceBusy=true;\n    try{\n      markOldServiceUi(section);\n      let panel=document.querySelector(\'#v4476ServicePanel\');\n      if(!panel){\n        panel=document.createElement(\'div\');\n        panel.id=\'v4476ServicePanel\';\n        section.appendChild(panel);\n      }\n      panel.innerHTML=`\n        <div class="v4476-service-shell">\n          <div class="v4476-service-head">\n            <div><h3>Servicios y precios</h3><p>Agrega, cambia el precio o elimina desde una sola lista.</p></div>\n            <span id="v4476ServiceCount" class="v4476-service-count">0</span>\n          </div>\n          <div class="v4476-service-new">\n            <input id="v4476NewServiceName" autocomplete="off" placeholder="NOMBRE DEL SERVICIO">\n            <input id="v4476NewServicePrice" type="number" min="0" step="0.01" placeholder="PRECIO">\n            <button id="v4476AddService" type="button" class="v4476-service-add">+ Agregar</button>\n          </div>\n          <div class="v4476-service-tools">\n            <input id="v4476ServiceSearch" class="v4476-service-search" autocomplete="off" placeholder="BUSCAR SERVICIO">\n          </div>\n          <div id="v4476ServiceList" class="v4476-service-list"><div class="v4476-service-empty">Cargando servicios…</div></div>\n          <div class="v4476-service-note">Si un servicio ya fue usado, “Eliminar” lo archiva: desaparece de nuevas atenciones, pero nunca modifica el historial anterior.</div>\n        </div>`;\n\n      panel.oninput=e=>{\n        if(e.target?.id===\'v4476ServiceSearch\')renderServiceRows();\n      };\n      panel.onclick=async e=>{\n        const add=e.target?.closest?.(\'#v4476AddService\');\n        const save=e.target?.closest?.(\'[data-save-service]\');\n        const del=e.target?.closest?.(\'[data-delete-service]\');\n        if(add){\n          const name=text(panel.querySelector(\'#v4476NewServiceName\')?.value||\'\');\n          const priceRaw=text(panel.querySelector(\'#v4476NewServicePrice\')?.value||\'\');\n          if(!name){alert(\'Escribe el nombre del servicio.\');return}\n          const price=priceRaw===\'\'?null:Number(priceRaw);\n          if(price!==null&&(!Number.isFinite(price)||price<0)){alert(\'Escribe un precio válido.\');return}\n          add.disabled=true;\n          try{\n            const r=await apiCall(\'/api/v4476/procedures/upsert\',{\n              method:\'POST\',body:JSON.stringify({nombre:name,valor_default:price})\n            });\n            panel.querySelector(\'#v4476NewServiceName\').value=\'\';\n            panel.querySelector(\'#v4476NewServicePrice\').value=\'\';\n            await fetchServices();\n            if(typeof window.rpNotice===\'function\')window.rpNotice(r?.restored?\'Servicio reactivado.\':\'Servicio agregado.\');\n          }catch(err){alert(err?.message||String(err))}\n          finally{add.disabled=false}\n          return;\n        }\n        if(save){\n          const row=save.closest(\'.v4476-service-row\');\n          const id=Number(save.dataset.saveService||0);\n          const input=row?.querySelector(\'.v4476-service-price\');\n          const raw=text(input?.value||\'\');\n          const value=raw===\'\'?null:Number(raw);\n          if(value!==null&&(!Number.isFinite(value)||value<0)){alert(\'Escribe un precio válido.\');return}\n          save.disabled=true;\n          try{\n            await apiCall(\'/api/procedures/\'+id,{\n              method:\'PUT\',body:JSON.stringify({valor_default:value})\n            });\n            await fetchServices();\n            if(typeof window.rpNotice===\'function\')window.rpNotice(\'Precio actualizado.\');\n          }catch(err){alert(err?.message||String(err));save.disabled=false}\n          return;\n        }\n        if(del){\n          const row=del.closest(\'.v4476-service-row\');\n          const id=Number(del.dataset.deleteService||0);\n          const item=serviceRows.find(x=>Number(x.id)===id);\n          const name=text(item?.nombre||row?.querySelector(\'b\')?.textContent||\'este servicio\');\n          if(!window.confirm(`¿Eliminar "${name}"?\\n\\nSi ya tiene historial se archivará y las atenciones anteriores se conservarán.`))return;\n          del.disabled=true;\n          try{\n            const r=await apiCall(\'/api/v4475/procedures/\'+id+\'/delete\',{method:\'POST\',body:\'{}\'});\n            await fetchServices();\n            if(typeof window.rpNotice===\'function\')window.rpNotice(r?.message||\'Servicio eliminado.\');\n          }catch(err){alert(err?.message||String(err));del.disabled=false}\n        }\n      };\n\n      await fetchServices();\n    }catch(e){\n      console.warn(\'v4476_service_panel_failed\',e);\n    }finally{\n      serviceBusy=false;\n    }\n  }\n\n  document.addEventListener(\'click\',e=>{\n    const tab=e.target?.closest?.(\'[data-config-tab]\');\n    const key=String(tab?.dataset?.configTab||\'\').toLowerCase();\n    if(key===\'procedimientos\'||key===\'services\')setTimeout(mountServicePanel,70);\n  });\n\n  const stableLoadProcedures=window.loadProcedures;\n  if(typeof stableLoadProcedures===\'function\'){\n    window.loadProcedures=async function(){\n      const out=await stableLoadProcedures.apply(this,arguments);\n      setTimeout(mountServicePanel,30);\n      return out;\n    };\n  }\n\n  function boot(){\n    setTimeout(mountServicePanel,100);\n    setTimeout(mountServicePanel,700);\n    setTimeout(mountServicePanel,1800);\n    if(String(document.querySelector(\'#bEstado\')?.value||\'\').toUpperCase()===\'EMITIDA\'){\n      setTimeout(renderEmittedHistory,120);\n    }\n  }\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  else boot();\n\n  // Versión: sustitución simple, sin observers.\n  try{\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      if(text(el.textContent)!==\'v\'+VERSION)el.textContent=\'v\'+VERSION;\n    });\n  }catch(_e){}\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4476_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '').replace("const VERSION='4.4.75';", "const VERSION='4.4.76';") + '\n' + V4476_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.76 billing/services patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4476/health')
def v4476_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'deleted_patient_hidden_from_pending_billing': True, 'emitted_history_survives_patient_delete': True, 'emitted_invoices_grouped_by_invoice_number': True, 'same_day_duplicate_invoice_warning': True, 'emitted_visit_delete_blocked': True, 'single_service_price_panel': True, 'fast_save_preserved': True, 'background_print_preserved': True, 'uses_new_dom_observer': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4476 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4476, '__name__', 'app_patch_4476')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4476, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4476, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4476, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4476ProcedureUpsertIn' in globals(): setattr(_rf_snapshot_app_patch_4476, 'V4476ProcedureUpsertIn', globals()['V4476ProcedureUpsertIn'])
if 'V4476_CSS' in globals(): setattr(_rf_snapshot_app_patch_4476, 'V4476_CSS', globals()['V4476_CSS'])
if 'V4476_JS' in globals(): setattr(_rf_snapshot_app_patch_4476, 'V4476_JS', globals()['V4476_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4476, '_', globals()['_'])
if '_active_patient_trash_snapshots' in globals(): setattr(_rf_snapshot_app_patch_4476, '_active_patient_trash_snapshots', globals()['_active_patient_trash_snapshots'])
if '_active_trashed_patient_ids' in globals(): setattr(_rf_snapshot_app_patch_4476, '_active_trashed_patient_ids', globals()['_active_trashed_patient_ids'])
if '_archived_emitted_items' in globals(): setattr(_rf_snapshot_app_patch_4476, '_archived_emitted_items', globals()['_archived_emitted_items'])
if '_backfill_active_trash_to_emissions' in globals(): setattr(_rf_snapshot_app_patch_4476, '_backfill_active_trash_to_emissions', globals()['_backfill_active_trash_to_emissions'])
if '_billing_action_counts_v4476' in globals(): setattr(_rf_snapshot_app_patch_4476, '_billing_action_counts_v4476', globals()['_billing_action_counts_v4476'])
if '_billing_counts' in globals(): setattr(_rf_snapshot_app_patch_4476, '_billing_counts', globals()['_billing_counts'])
if '_billing_group_records_v4476' in globals(): setattr(_rf_snapshot_app_patch_4476, '_billing_group_records_v4476', globals()['_billing_group_records_v4476'])
if '_date' in globals(): setattr(_rf_snapshot_app_patch_4476, '_date', globals()['_date'])
if '_date_allowed' in globals(): setattr(_rf_snapshot_app_patch_4476, '_date_allowed', globals()['_date_allowed'])
if '_datetime' in globals(): setattr(_rf_snapshot_app_patch_4476, '_datetime', globals()['_datetime'])
if '_emission_payload' in globals(): setattr(_rf_snapshot_app_patch_4476, '_emission_payload', globals()['_emission_payload'])
if '_fiscal_line_snapshot' in globals(): setattr(_rf_snapshot_app_patch_4476, '_fiscal_line_snapshot', globals()['_fiscal_line_snapshot'])
if '_json' in globals(): setattr(_rf_snapshot_app_patch_4476, '_json', globals()['_json'])
if '_json_date' in globals(): setattr(_rf_snapshot_app_patch_4476, '_json_date', globals()['_json_date'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4476, '_mod', globals()['_mod'])
if '_patient_snapshot' in globals(): setattr(_rf_snapshot_app_patch_4476, '_patient_snapshot', globals()['_patient_snapshot'])
if '_preserve_patient_fiscal_history' in globals(): setattr(_rf_snapshot_app_patch_4476, '_preserve_patient_fiscal_history', globals()['_preserve_patient_fiscal_history'])
if '_remove_api_route' in globals(): setattr(_rf_snapshot_app_patch_4476, '_remove_api_route', globals()['_remove_api_route'])
if '_save_emission_payload' in globals(): setattr(_rf_snapshot_app_patch_4476, '_save_emission_payload', globals()['_save_emission_payload'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4476, '_seen', globals()['_seen'])
if '_stable_billing_group_records' in globals(): setattr(_rf_snapshot_app_patch_4476, '_stable_billing_group_records', globals()['_stable_billing_group_records'])
if '_stable_billing_list' in globals(): setattr(_rf_snapshot_app_patch_4476, '_stable_billing_list', globals()['_stable_billing_list'])
if '_stable_safe_delete_patient' in globals(): setattr(_rf_snapshot_app_patch_4476, '_stable_safe_delete_patient', globals()['_stable_safe_delete_patient'])
if '_stable_safe_delete_visit' in globals(): setattr(_rf_snapshot_app_patch_4476, '_stable_safe_delete_visit', globals()['_stable_safe_delete_visit'])
if '_timedelta' in globals(): setattr(_rf_snapshot_app_patch_4476, '_timedelta', globals()['_timedelta'])
if '_trash_emitted_lines' in globals(): setattr(_rf_snapshot_app_patch_4476, '_trash_emitted_lines', globals()['_trash_emitted_lines'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4476, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4476, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4476, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4476, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4476__previous' in globals(): setattr(_rf_snapshot_app_patch_4476, 'previous', globals()['_rf_alias_app_patch_4476__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4476, 'uvicorn', globals()['uvicorn'])
if 'v4476_billing_list' in globals(): setattr(_rf_snapshot_app_patch_4476, 'v4476_billing_list', globals()['v4476_billing_list'])
if 'v4476_health' in globals(): setattr(_rf_snapshot_app_patch_4476, 'v4476_health', globals()['v4476_health'])
if 'v4476_prior_emissions' in globals(): setattr(_rf_snapshot_app_patch_4476, 'v4476_prior_emissions', globals()['v4476_prior_emissions'])
if 'v4476_procedure_upsert' in globals(): setattr(_rf_snapshot_app_patch_4476, 'v4476_procedure_upsert', globals()['v4476_procedure_upsert'])
if 'v4476_safe_delete_patient' in globals(): setattr(_rf_snapshot_app_patch_4476, 'v4476_safe_delete_patient', globals()['v4476_safe_delete_patient'])
if 'v4476_safe_delete_visit' in globals(): setattr(_rf_snapshot_app_patch_4476, 'v4476_safe_delete_visit', globals()['v4476_safe_delete_visit'])
_rf_layers['app_patch_4476'] = _rf_snapshot_app_patch_4476

# ---- app_patch_4477 ----
from datetime import date as _date
_rf_alias_app_patch_4477__previous = _rf_layers['app_patch_4476']
core = _rf_alias_app_patch_4477__previous.core
app = _rf_alias_app_patch_4477__previous.app
APP_VERSION = '4.4.77'
_mod = _rf_alias_app_patch_4477__previous
_seen = set()
for _ in range(36):
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

    class V4477DiscardBillingIn(core.BaseModel):
        patient_id: int
        fecha: _date
    _stable_billing_group_records = core.billing_group_records

    def _billing_group_records_v4477(db, patient_id: int, fecha):
        rows = _stable_billing_group_records(db, int(patient_id), fecha)
        return [(billing, visit) for billing, visit in rows if str(getattr(billing, 'estado', '') or '').upper() != 'DESCARTADA']
    core.billing_group_records = _billing_group_records_v4477

    @app.post('/api/v4477/billing/discard')
    def v4477_discard_pending_billing(data: V4477DiscardBillingIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        if core.is_offline_db(db):
            raise core.HTTPException(503, 'Quitar una factura de Por emitir requiere conexión a Internet.')
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        rows = _stable_billing_group_records(db, int(data.patient_id), data.fecha)
        rows = [(billing, visit) for billing, visit in rows if str(getattr(billing, 'estado', '') or '').upper() in {'PENDIENTE', 'APROBADA'}]
        if not rows:
            raise core.HTTPException(404, 'Esta factura ya no está en Por emitir.')
        group_key = core._azur_group_key_for_rows(int(data.patient_id), data.fecha, rows)
        emission = db.scalar(core.select(core.AzurEmission).where(core.AzurEmission.group_key == group_key))
        if emission and (str(getattr(emission, 'clave_acceso', '') or '').strip() or str(getattr(emission, 'numero_factura', '') or '').strip()):
            raise core.HTTPException(409, 'Esta factura ya fue enviada a AZUR y no puede eliminarse de Por emitir.')
        touched = []
        for billing, _visit in rows:
            billing.estado = 'DESCARTADA'
            billing.approved_at = None
            billing.numero_factura = None
            billing.emitted_at = None
            touched.append(billing)
        core.audit(db, user, 'descartar_factura_pendiente', f'Paciente {int(data.patient_id)}, fecha {data.fecha}, líneas {len(touched)}')
        db.commit()
        for billing in touched:
            try:
                core.mirror_billing_to_local(billing)
            except Exception:
                pass
        return {'ok': True, 'patient_id': int(data.patient_id), 'fecha': data.fecha.isoformat(), 'discarded': len(touched), 'message': 'Factura quitada de Por emitir. La atención y el paciente se conservaron.'}
    V4477_CSS = '\n.v4477-discard-billing{\n  border:1px solid #dfb4b4!important;\n  background:#fff6f6!important;\n  color:#963d3d!important;\n}\n.v4477-discard-billing:hover{\n  background:#fdecec!important;\n  border-color:#cf8f8f!important;\n}\n'
    V4477_JS = '\n;(()=>{\n  if(window.__v4477DiscardPendingBilling)return;\n  window.__v4477DiscardPendingBilling=true;\n  const VERSION=\'4.4.77\';\n\n  const apiCall=(url,opt={})=>{\n    const fn=window.api;\n    return typeof fn===\'function\'\n      ?fn(url,opt)\n      :Promise.reject(new Error(\'API no disponible\'));\n  };\n\n  window.v4477DiscardPendingBilling=async function(patientId,fecha,event){\n    try{event?.preventDefault?.();event?.stopPropagation?.()}catch(_e){}\n    const msg=\'¿Quitar esta factura de Por emitir?\\n\\n\'\n      +\'La atención y el paciente NO se borrarán. \'\n      +\'Solo desaparecerá de la cola de facturación.\\n\\n\'\n      +\'Si ya fue enviada a AZUR, el sistema no permitirá quitarla.\';\n    const ok=typeof window.rpConfirm===\'function\'\n      ?await window.rpConfirm(msg,\'Quitar de Por emitir\')\n      :window.confirm(msg);\n    if(!ok)return;\n\n    try{\n      const out=await apiCall(\'/api/v4477/billing/discard\',{\n        method:\'POST\',\n        body:JSON.stringify({\n          patient_id:Number(patientId),\n          fecha:String(fecha||\'\').slice(0,10)\n        })\n      });\n      try{if(typeof window.loadBilling===\'function\')await window.loadBilling()}catch(_e){}\n      try{if(typeof window.refreshPendingBadges===\'function\')await window.refreshPendingBadges()}catch(_e){}\n      const message=out?.message||\'Factura quitada de Por emitir.\';\n      if(typeof window.rpNotice===\'function\')window.rpNotice(message);\n      else alert(message);\n    }catch(e){\n      alert(e?.message||String(e));\n    }\n  };\n\n  const stableBillingCardHtml=window.billingCardHtml;\n  if(typeof stableBillingCardHtml===\'function\'){\n    window.billingCardHtml=function(group){\n      let html=stableBillingCardHtml.apply(this,arguments);\n      const view=String(document.querySelector(\'#bEstado\')?.value||\'PENDIENTE\').toUpperCase();\n      if(view===\'EMITIDA\'||!html)return html;\n\n      const patientId=Number(group?.patient?.id||0);\n      const fecha=String(group?.fecha||group?.items?.[0]?.visit?.fecha||\'\').slice(0,10);\n      if(!patientId||!/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha))return html;\n\n      const button=`<button type="button" class="v4477-discard-billing" onclick="v4477DiscardPendingBilling(${patientId},\'${fecha}\',event)">🗑 Quitar de Por emitir</button>`;\n      const marker=\'<div class="billing-actions">\';\n      if(html.includes(marker)){\n        html=html.replace(marker,marker+button);\n      }else{\n        html=html.replace(\'</article>\',`<div class="billing-actions">${button}</div></article>`);\n      }\n      return html;\n    };\n  }\n\n  try{\n    const badges=document.querySelectorAll(\'.v460-version,#currentVersionBadge\');\n    badges.forEach(el=>{el.textContent=\'v\'+VERSION});\n  }catch(_e){}\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4477_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '').replace("const VERSION='4.4.76';", "const VERSION='4.4.77';") + '\n' + V4477_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.77 discard pending billing patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4477/health')
def v4477_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'discard_pending_billing': True, 'discard_preserves_visit': True, 'discard_excluded_from_future_azur': True, 'base': '4.4.76', 'uses_new_dom_observer': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4477 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4477, '__name__', 'app_patch_4477')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4477, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4477, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4477, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4477DiscardBillingIn' in globals(): setattr(_rf_snapshot_app_patch_4477, 'V4477DiscardBillingIn', globals()['V4477DiscardBillingIn'])
if 'V4477_CSS' in globals(): setattr(_rf_snapshot_app_patch_4477, 'V4477_CSS', globals()['V4477_CSS'])
if 'V4477_JS' in globals(): setattr(_rf_snapshot_app_patch_4477, 'V4477_JS', globals()['V4477_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4477, '_', globals()['_'])
if '_billing_group_records_v4477' in globals(): setattr(_rf_snapshot_app_patch_4477, '_billing_group_records_v4477', globals()['_billing_group_records_v4477'])
if '_date' in globals(): setattr(_rf_snapshot_app_patch_4477, '_date', globals()['_date'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4477, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4477, '_seen', globals()['_seen'])
if '_stable_billing_group_records' in globals(): setattr(_rf_snapshot_app_patch_4477, '_stable_billing_group_records', globals()['_stable_billing_group_records'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4477, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4477, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4477, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4477, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4477__previous' in globals(): setattr(_rf_snapshot_app_patch_4477, 'previous', globals()['_rf_alias_app_patch_4477__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4477, 'uvicorn', globals()['uvicorn'])
if 'v4477_discard_pending_billing' in globals(): setattr(_rf_snapshot_app_patch_4477, 'v4477_discard_pending_billing', globals()['v4477_discard_pending_billing'])
if 'v4477_health' in globals(): setattr(_rf_snapshot_app_patch_4477, 'v4477_health', globals()['v4477_health'])
_rf_layers['app_patch_4477'] = _rf_snapshot_app_patch_4477

# ---- app_patch_4478 ----
import re as _re
_rf_alias_app_patch_4478__previous = _rf_layers['app_patch_4477']
core = _rf_alias_app_patch_4478__previous.core
app = _rf_alias_app_patch_4478__previous.app
APP_VERSION = '4.4.78'
_mod = _rf_alias_app_patch_4478__previous
_seen = set()
for _ in range(40):
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
    V4478_CSS = '\n/* v4.4.78 — versión estable + botón seguro de descarte */\n.v4478-discard-billing{\n  border:1px solid #dfb4b4!important;\n  background:#fff6f6!important;\n  color:#963d3d!important;\n}\n.v4478-discard-billing:hover{\n  background:#fdecec!important;\n  border-color:#cf8f8f!important;\n}\n/* Los parches antiguos todavía pueden intentar escribir su versión unos ms.\n   Ocultamos ese texto interno y mostramos una única versión estable. */\n.v460-version,#currentVersionBadge{\n  font-size:0!important;\n}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.78";\n  font-size:9px!important;\n  line-height:1!important;\n  font-weight:850!important;\n}\n'
    V4478_JS = '\n;(()=>{\n  if(window.__v4478VisibleDiscardAndStableVersion)return;\n  window.__v4478VisibleDiscardAndStableVersion=true;\n  const VERSION=\'4.4.78\';\n\n  const state=()=>String(document.querySelector(\'#bEstado\')?.value||\'PENDIENTE\').toUpperCase();\n\n  function identityFromCard(card,index){\n    if(!card)return null;\n    const dsPid=Number(card.dataset.patientId||0);\n    const dsFecha=String(card.dataset.fecha||\'\').slice(0,10);\n    if(dsPid&&/^\\d{4}-\\d{2}-\\d{2}$/.test(dsFecha)){\n      return {patient_id:dsPid,fecha:dsFecha};\n    }\n\n    for(const el of [...card.querySelectorAll(\'[onclick]\')]){\n      const raw=String(el.getAttribute(\'onclick\')||\'\');\n      const m=/\\(\\s*(\\d+)\\s*,\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]/.exec(raw);\n      if(m)return {patient_id:Number(m[1]),fecha:m[2]};\n    }\n\n    try{\n      const groups=Array.isArray(billingGroupsCache)?billingGroupsCache:[];\n      const g=groups[index];\n      const pid=Number(g?.patient?.id||0);\n      const fecha=String(g?.fecha||g?.items?.[0]?.visit?.fecha||\'\').slice(0,10);\n      if(pid&&/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha)){\n        return {patient_id:pid,fecha};\n      }\n    }catch(_e){}\n    return null;\n  }\n\n  function decoratePendingCards(){\n    if(state()===\'EMITIDA\')return;\n    const cards=[...document.querySelectorAll(\'#billingList .billing-card\')];\n    cards.forEach((card,index)=>{\n      if(card.classList.contains(\'emitida\'))return;\n      if(card.querySelector(\'.v4478-discard-billing,.v4477-discard-billing\'))return;\n\n      const id=identityFromCard(card,index);\n      if(!id)return;\n\n      let actions=card.querySelector(\'.billing-actions\');\n      if(!actions){\n        const foot=card.querySelector(\'.billing-card-foot\')||card;\n        actions=document.createElement(\'div\');\n        actions.className=\'billing-actions\';\n        foot.appendChild(actions);\n      }\n\n      const btn=document.createElement(\'button\');\n      btn.type=\'button\';\n      btn.className=\'v4478-discard-billing\';\n      btn.textContent=\'🗑 Quitar de Por emitir\';\n      btn.addEventListener(\'click\',event=>{\n        event.preventDefault();\n        event.stopPropagation();\n        if(typeof window.v4477DiscardPendingBilling===\'function\'){\n          window.v4477DiscardPendingBilling(id.patient_id,id.fecha,event);\n        }else{\n          alert(\'La opción para quitar esta factura todavía no está disponible. Cierra y vuelve a abrir Recepción.\');\n        }\n      });\n      actions.prepend(btn);\n    });\n  }\n\n  function stabilizeVersion(){\n    try{\n      document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n        el.textContent=\'v\'+VERSION;\n        el.setAttribute(\'data-version\',\'v\'+VERSION);\n      });\n    }catch(_e){}\n  }\n\n  const stableLoadBilling=window.loadBilling;\n  if(typeof stableLoadBilling===\'function\'){\n    window.loadBilling=async function(){\n      const out=await stableLoadBilling.apply(this,arguments);\n      decoratePendingCards();\n      stabilizeVersion();\n      setTimeout(decoratePendingCards,40);\n      setTimeout(decoratePendingCards,140);\n      return out;\n    };\n  }\n\n  const stableSetBillingStatus=window.setBillingStatus;\n  if(typeof stableSetBillingStatus===\'function\'){\n    window.setBillingStatus=async function(){\n      const out=await stableSetBillingStatus.apply(this,arguments);\n      decoratePendingCards();\n      stabilizeVersion();\n      setTimeout(decoratePendingCards,50);\n      return out;\n    };\n  }\n\n  document.addEventListener(\'click\',event=>{\n    const billingNav=event.target?.closest?.(\'[data-section="facturacion"],[data-config-tab="facturacion"]\');\n    if(billingNav){\n      setTimeout(decoratePendingCards,80);\n      setTimeout(decoratePendingCards,260);\n    }\n  },true);\n\n  function boot(){\n    stabilizeVersion();\n    decoratePendingCards();\n    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},180);\n    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},700);\n    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},1600);\n  }\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  else boot();\n})();\n'
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.78';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.78';", _js)
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4478_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4478_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.78 visible discard/stable version patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4478/health')
def v4478_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'pending_discard_button_post_render': True, 'stable_visible_version': True, 'uses_new_dom_observer': False, 'backend_changes': False, 'base': '4.4.77'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4478 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4478, '__name__', 'app_patch_4478')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4478, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4478, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4478, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4478_CSS' in globals(): setattr(_rf_snapshot_app_patch_4478, 'V4478_CSS', globals()['V4478_CSS'])
if 'V4478_JS' in globals(): setattr(_rf_snapshot_app_patch_4478, 'V4478_JS', globals()['V4478_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4478, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4478, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4478, '_mod', globals()['_mod'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4478, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4478, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4478, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4478, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4478, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4478, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4478__previous' in globals(): setattr(_rf_snapshot_app_patch_4478, 'previous', globals()['_rf_alias_app_patch_4478__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4478, 'uvicorn', globals()['uvicorn'])
if 'v4478_health' in globals(): setattr(_rf_snapshot_app_patch_4478, 'v4478_health', globals()['v4478_health'])
_rf_layers['app_patch_4478'] = _rf_snapshot_app_patch_4478

# ---- app_patch_4479 ----
import re as _re
_rf_alias_app_patch_4479__previous = _rf_layers['app_patch_4478']
core = _rf_alias_app_patch_4479__previous.core
app = _rf_alias_app_patch_4479__previous.app
APP_VERSION = '4.4.79'
_mod = _rf_alias_app_patch_4479__previous
_seen = set()
for _ in range(44):
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
LEGACY_SERVICE_MANAGER_DISABLED = False
LEGACY_VERSION_OBSERVER_DISABLED = False
FACTURERO_DESTINATION_REMOVED = False
try:
    try:
        destinations = getattr(core, 'EXTERNAL_DESTINATIONS', None)
        if isinstance(destinations, dict):
            FACTURERO_DESTINATION_REMOVED = destinations.pop('facturero', None) is not None
    except Exception:
        FACTURERO_DESTINATION_REMOVED = False
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _prelude = 'window.__v4475FastSaveAndServiceDelete=true;\n'
    _before = _js
    _js = _js.replace('    installProcedureManager();\n    installVersionPainter();', '    /* v4.4.79: administradores visuales heredados desactivados */')
    LEGACY_SERVICE_MANAGER_DISABLED = _js != _before
    _before = _js
    _js = _js.replace('    installVersionPainter();', '    /* v4.4.79: observador heredado de versión desactivado */')
    if _js != _before:
        LEGACY_VERSION_OBSERVER_DISABLED = True
    else:
        LEGACY_VERSION_OBSERVER_DISABLED = LEGACY_SERVICE_MANAGER_DISABLED
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.79';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.79';", _js)
    V4479_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.79"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n[data-config-tab="services"],\n[data-config-section="services"],\n#v458ServicePanel{display:none!important}\n#facturacion .billing-filters,\n#v482BatchEmit{display:none!important}\n#v4470ProcedureManager,\n#v4475ProcedureManager,\n[data-config-section="procedimientos"] > .v4476-service-old{display:none!important}\n'
    V4479_JS = '\n;(()=>{\n  if(window.__v4479Cleanup)return;\n  window.__v4479Cleanup=true;\n  const VERSION=\'4.4.79\';\n\n  const txt=v=>String(v??\'\').replace(/\\s+/g,\' \').trim();\n  const norm=v=>txt(v).normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').toLowerCase();\n\n  function isFactureroControl(el){\n    const blob=[\n      txt(el?.textContent),\n      String(el?.getAttribute?.(\'href\')||\'\'),\n      String(el?.getAttribute?.(\'onclick\')||\'\'),\n      String(el?.dataset?.target||\'\'),\n      String(el?.dataset?.destination||\'\')\n    ].join(\' \').toLowerCase();\n    return blob.includes(\'facturero movil\')\n      || blob.includes(\'factureromovil\')\n      || /\\bfacturero\\b/.test(blob);\n  }\n\n  function cleanupBilling(){\n    const sec=document.querySelector(\'#facturacion\');\n    if(!sec)return;\n    [...sec.querySelectorAll(\'button,a\')].forEach(el=>{\n      if(isFactureroControl(el))el.remove();\n    });\n    const summary=sec.querySelector(\'#billingSummary\');\n    if(summary){\n      [...summary.querySelectorAll(\'button\')].forEach(btn=>{\n        if(norm(btn.textContent).includes(\'aprobada\'))btn.remove();\n      });\n    }\n    sec.querySelector(\'.billing-filters\')?.remove();\n    sec.querySelector(\'#v482BatchEmit\')?.remove();\n    [...sec.querySelectorAll(\'.billing-title-actions\')].forEach(row=>{\n      const useful=[...row.querySelectorAll(\'button,a\')].filter(el=>!isFactureroControl(el));\n      if(!useful.length)row.style.display=\'none\';\n      else row.style.display=\'\';\n    });\n  }\n\n  function cleanupConfig(){\n    const config=document.querySelector(\'#config\');\n    if(!config)return;\n    config.querySelector(\'[data-config-tab="services"]\')?.remove();\n    config.querySelector(\'[data-config-section="services"]\')?.remove();\n    config.querySelector(\'#v458ServicePanel\')?.remove();\n\n    const proc=config.querySelector(\'[data-config-section="procedimientos"]\');\n    if(proc&&proc.querySelector(\'#v4476ServicePanel\')){\n      proc.querySelector(\'#v4470ProcedureManager\')?.remove();\n      proc.querySelector(\'#v4475ProcedureManager\')?.remove();\n      [...proc.querySelectorAll(\':scope > .v4476-service-old\')].forEach(el=>el.remove());\n    }\n  }\n\n  function stabilizeVersion(){\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n\n  function cleanupAll(){\n    cleanupBilling();\n    cleanupConfig();\n    stabilizeVersion();\n  }\n\n  const stableLoadBilling=window.loadBilling;\n  if(typeof stableLoadBilling===\'function\'){\n    window.loadBilling=async function(){\n      const out=await stableLoadBilling.apply(this,arguments);\n      cleanupBilling();\n      stabilizeVersion();\n      return out;\n    };\n  }\n\n  const stableSetBillingStatus=window.setBillingStatus;\n  if(typeof stableSetBillingStatus===\'function\'){\n    window.setBillingStatus=async function(){\n      const out=await stableSetBillingStatus.apply(this,arguments);\n      cleanupBilling();\n      stabilizeVersion();\n      return out;\n    };\n  }\n\n  const stableLoadProcedures=window.loadProcedures;\n  if(typeof stableLoadProcedures===\'function\'){\n    window.loadProcedures=async function(){\n      const out=await stableLoadProcedures.apply(this,arguments);\n      cleanupConfig();\n      return out;\n    };\n  }\n\n  const stableShowConfigTab=window.showConfigTab;\n  if(typeof stableShowConfigTab===\'function\'){\n    window.showConfigTab=function(tab){\n      if(String(tab||\'\').toLowerCase()===\'services\')tab=\'sistema\';\n      const args=[...arguments];\n      args[0]=tab;\n      const out=stableShowConfigTab.apply(this,args);\n      setTimeout(cleanupConfig,0);\n      return out;\n    };\n  }\n\n  document.addEventListener(\'click\',event=>{\n    const nav=event.target?.closest?.(\n      \'[data-section="facturacion"],[data-config-tab="facturacion"],\'\n      +\'[data-section="config"],[data-config-tab="procedimientos"],\'\n      +\'[data-config-tab="sistema"]\'\n    );\n    if(nav)setTimeout(cleanupAll,30);\n  },true);\n\n  function boot(){\n    cleanupAll();\n    setTimeout(cleanupAll,120);\n    setTimeout(cleanupAll,600);\n  }\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  }else{\n    boot();\n  }\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4479_CSS
    core.V460_OVERLAY_JS = _prelude + _js + '\n' + V4479_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.79 cleanup patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4479/health')
def v4479_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'facturero_destination_removed': FACTURERO_DESTINATION_REMOVED, 'legacy_service_manager_disabled': LEGACY_SERVICE_MANAGER_DISABLED, 'legacy_version_observer_disabled': LEGACY_VERSION_OBSERVER_DISABLED, 'obsolete_services_tab_removed': True, 'obsolete_billing_filters_removed': True, 'obsolete_approved_tab_removed': True, 'batch_emit_ui_removed': True, 'azur_preserved': True, 'no_facturables_preserved': True, 'activity_trash_preserved': True, 'receipt_layout_version': '4.4.69', 'database_changes': False, 'bendo_enabled': False, 'base': '4.4.78'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4479 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4479, '__name__', 'app_patch_4479')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4479, 'APP_VERSION', globals()['APP_VERSION'])
if 'FACTURERO_DESTINATION_REMOVED' in globals(): setattr(_rf_snapshot_app_patch_4479, 'FACTURERO_DESTINATION_REMOVED', globals()['FACTURERO_DESTINATION_REMOVED'])
if 'LEGACY_SERVICE_MANAGER_DISABLED' in globals(): setattr(_rf_snapshot_app_patch_4479, 'LEGACY_SERVICE_MANAGER_DISABLED', globals()['LEGACY_SERVICE_MANAGER_DISABLED'])
if 'LEGACY_VERSION_OBSERVER_DISABLED' in globals(): setattr(_rf_snapshot_app_patch_4479, 'LEGACY_VERSION_OBSERVER_DISABLED', globals()['LEGACY_VERSION_OBSERVER_DISABLED'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4479, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4479, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4479_CSS' in globals(): setattr(_rf_snapshot_app_patch_4479, 'V4479_CSS', globals()['V4479_CSS'])
if 'V4479_JS' in globals(): setattr(_rf_snapshot_app_patch_4479, 'V4479_JS', globals()['V4479_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4479, '_', globals()['_'])
if '_before' in globals(): setattr(_rf_snapshot_app_patch_4479, '_before', globals()['_before'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4479, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4479, '_mod', globals()['_mod'])
if '_prelude' in globals(): setattr(_rf_snapshot_app_patch_4479, '_prelude', globals()['_prelude'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4479, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4479, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4479, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4479, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4479, 'core', globals()['core'])
if 'destinations' in globals(): setattr(_rf_snapshot_app_patch_4479, 'destinations', globals()['destinations'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4479, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4479__previous' in globals(): setattr(_rf_snapshot_app_patch_4479, 'previous', globals()['_rf_alias_app_patch_4479__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4479, 'uvicorn', globals()['uvicorn'])
if 'v4479_health' in globals(): setattr(_rf_snapshot_app_patch_4479, 'v4479_health', globals()['v4479_health'])
_rf_layers['app_patch_4479'] = _rf_snapshot_app_patch_4479

# ---- app_patch_4480 ----
import re as _re
_rf_alias_app_patch_4480__previous = _rf_layers['app_patch_4479']
core = _rf_alias_app_patch_4480__previous.core
app = _rf_alias_app_patch_4480__previous.app
APP_VERSION = '4.4.80'
_mod = _rf_alias_app_patch_4480__previous
_seen = set()
for _ in range(48):
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
STATE_HOLDER_REPAIRED = False
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _needle = "sec.querySelector('.billing-filters')?.remove();"
    _replacement = "sec.querySelector('.billing-filters')?.setAttribute('hidden','');"
    if _needle in _js:
        _js = _js.replace(_needle, _replacement)
        STATE_HOLDER_REPAIRED = True
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.80';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.80';", _js)
    V4480_CSS = '\n/* v4.4.80 — filtros internos conservados pero invisibles */\n#facturacion .billing-filters{display:none!important}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.80"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4480_JS = "\n;(()=>{\n  if(window.__v4480BillingStateHotfix)return;\n  window.__v4480BillingStateHotfix=true;\n  const VERSION='4.4.80';\n\n  function preserveBillingState(){\n    const sec=document.querySelector('#facturacion');\n    if(!sec)return;\n    const filters=sec.querySelector('.billing-filters');\n    if(filters){\n      filters.hidden=true;\n      filters.style.display='none';\n    }\n    const state=document.querySelector('#bEstado');\n    if(state){\n      state.setAttribute('aria-hidden','true');\n      state.tabIndex=-1;\n    }\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;\n      el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n\n  const oldLoad=window.loadBilling;\n  if(typeof oldLoad==='function'){\n    window.loadBilling=async function(){\n      preserveBillingState();\n      const out=await oldLoad.apply(this,arguments);\n      preserveBillingState();\n      return out;\n    };\n  }\n\n  const oldSet=window.setBillingStatus;\n  if(typeof oldSet==='function'){\n    window.setBillingStatus=async function(status){\n      preserveBillingState();\n      const out=await oldSet.apply(this,arguments);\n      preserveBillingState();\n      return out;\n    };\n  }\n\n  function boot(){\n    preserveBillingState();\n    setTimeout(preserveBillingState,100);\n    setTimeout(preserveBillingState,500);\n  }\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});\n  else boot();\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4480_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4480_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.80 billing state hotfix failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4480/health')
def v4480_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'billing_state_holder_preserved': True, 'cleanup_4479_preserved': True, 'state_holder_repaired_in_bundle': STATE_HOLDER_REPAIRED, 'database_changes': False, 'backend_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4480 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4480, '__name__', 'app_patch_4480')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4480, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4480, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4480, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'STATE_HOLDER_REPAIRED' in globals(): setattr(_rf_snapshot_app_patch_4480, 'STATE_HOLDER_REPAIRED', globals()['STATE_HOLDER_REPAIRED'])
if 'V4480_CSS' in globals(): setattr(_rf_snapshot_app_patch_4480, 'V4480_CSS', globals()['V4480_CSS'])
if 'V4480_JS' in globals(): setattr(_rf_snapshot_app_patch_4480, 'V4480_JS', globals()['V4480_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4480, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4480, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4480, '_mod', globals()['_mod'])
if '_needle' in globals(): setattr(_rf_snapshot_app_patch_4480, '_needle', globals()['_needle'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4480, '_re', globals()['_re'])
if '_replacement' in globals(): setattr(_rf_snapshot_app_patch_4480, '_replacement', globals()['_replacement'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4480, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4480, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4480, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4480, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4480, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4480__previous' in globals(): setattr(_rf_snapshot_app_patch_4480, 'previous', globals()['_rf_alias_app_patch_4480__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4480, 'uvicorn', globals()['uvicorn'])
if 'v4480_health' in globals(): setattr(_rf_snapshot_app_patch_4480, 'v4480_health', globals()['v4480_health'])
_rf_layers['app_patch_4480'] = _rf_snapshot_app_patch_4480

# ---- app_patch_4481 ----
import re as _re
_rf_alias_app_patch_4481__previous = _rf_layers['app_patch_4480']
core = _rf_alias_app_patch_4481__previous.core
app = _rf_alias_app_patch_4481__previous.app
APP_VERSION = '4.4.81'
_mod = _rf_alias_app_patch_4481__previous
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

_rf_snapshot_app_patch_4481 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4481, '__name__', 'app_patch_4481')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4481, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4481, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4481, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4481_CSS' in globals(): setattr(_rf_snapshot_app_patch_4481, 'V4481_CSS', globals()['V4481_CSS'])
if 'V4481_JS' in globals(): setattr(_rf_snapshot_app_patch_4481, 'V4481_JS', globals()['V4481_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4481, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4481, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4481, '_mod', globals()['_mod'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4481, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4481, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4481, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4481, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4481, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4481, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4481__previous' in globals(): setattr(_rf_snapshot_app_patch_4481, 'previous', globals()['_rf_alias_app_patch_4481__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4481, 'uvicorn', globals()['uvicorn'])
if 'v4481_health' in globals(): setattr(_rf_snapshot_app_patch_4481, 'v4481_health', globals()['v4481_health'])
_rf_layers['app_patch_4481'] = _rf_snapshot_app_patch_4481

# ---- app_patch_4482 ----
import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path
_rf_alias_app_patch_4482__previous = _rf_layers['app_patch_4481']
core = _rf_alias_app_patch_4482__previous.core
app = _rf_alias_app_patch_4482__previous.app
APP_VERSION = '4.4.82'
_mod = _rf_alias_app_patch_4482__previous
_seen = set()
for _ in range(56):
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
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.82';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.82';", _js)
    V4482_CSS = '\n/* v4.4.82 — actualización pasa por el launcher oficial */\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.82"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4482_JS = '\n;(()=>{\n  if(window.__v4482LauncherUpdateRepair)return;\n  window.__v4482LauncherUpdateRepair=true;\n  const VERSION=\'4.4.82\';\n\n  async function launchOfficialUpdater(){\n    const status=document.querySelector(\'#updateStatus\');\n    try{\n      if(status)status.textContent=\'Abriendo el actualizador seguro…\';\n      const r=await fetch(\'/api/v4482/launch-updater\',{\n        method:\'POST\',\n        headers:{\'Content-Type\':\'application/json\'},\n        body:\'{}\',\n        cache:\'no-store\'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||\'No se pudo abrir el actualizador.\');\n      if(status)status.textContent=\'Actualizador abierto. Si hay una versión nueva, se instalará automáticamente.\';\n      return d;\n    }catch(e){\n      if(status)status.textContent=e?.message||String(e);\n      throw e;\n    }\n  }\n\n  function installRestartOverride(){\n    window.restartReception=launchOfficialUpdater;\n    document.querySelectorAll(\'button[onclick*="restartReception"]\').forEach(btn=>{\n      btn.textContent=\'⬆ Instalar actualización\';\n      btn.title=\'Abre el launcher oficial para comprobar e instalar la versión nueva\';\n    });\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n\n  installRestartOverride();\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\'DOMContentLoaded\',installRestartOverride,{once:true});\n  }\n  setTimeout(installRestartOverride,250);\n  setTimeout(installRestartOverride,900);\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4482_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4482_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.82 launcher update repair failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.post('/api/v4482/launch-updater')
def v4482_launch_updater(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta acción solo se ejecuta desde la PC de Recepción')
    launcher = _Path(core.BASE_DIR) / 'ABRIR_RECEPCION.py'
    if not launcher.is_file():
        raise core.HTTPException(500, 'No se encontró ABRIR_RECEPCION.py')
    python_candidates = [_Path(core.BASE_DIR) / '.venv' / 'Scripts' / 'pythonw.exe', _Path(core.BASE_DIR) / '.venv' / 'Scripts' / 'python.exe', _Path(_sys.executable)]
    python_exe = next((p for p in python_candidates if p.is_file()), None)
    if python_exe is None:
        raise core.HTTPException(500, 'No se encontró el Python de Recepción')
    flags = 0
    if _os.name == 'nt':
        flags = getattr(_subprocess, 'CREATE_NO_WINDOW', 0) | getattr(_subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    try:
        _subprocess.Popen([str(python_exe), str(launcher)], cwd=str(core.BASE_DIR), env=_os.environ.copy(), stdin=_subprocess.DEVNULL, stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL, creationflags=flags, close_fds=True)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo abrir el actualizador: {type(exc).__name__}')
    return {'ok': True, 'version': APP_VERSION, 'launcher_started': True, 'message': 'Se abrió el launcher oficial de Recepción.'}

@app.get('/api/v4482/health')
def v4482_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'restart_button_uses_launcher': True, 'billing_emitidas_fix_preserved': True, 'facturero_removed_globally': True, 'database_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4482 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4482, '__name__', 'app_patch_4482')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4482, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4482, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4482, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4482_CSS' in globals(): setattr(_rf_snapshot_app_patch_4482, 'V4482_CSS', globals()['V4482_CSS'])
if 'V4482_JS' in globals(): setattr(_rf_snapshot_app_patch_4482, 'V4482_JS', globals()['V4482_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4482, '_', globals()['_'])
if '_Path' in globals(): setattr(_rf_snapshot_app_patch_4482, '_Path', globals()['_Path'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4482, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4482, '_mod', globals()['_mod'])
if '_os' in globals(): setattr(_rf_snapshot_app_patch_4482, '_os', globals()['_os'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4482, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4482, '_seen', globals()['_seen'])
if '_subprocess' in globals(): setattr(_rf_snapshot_app_patch_4482, '_subprocess', globals()['_subprocess'])
if '_sys' in globals(): setattr(_rf_snapshot_app_patch_4482, '_sys', globals()['_sys'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4482, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4482, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4482, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4482, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4482__previous' in globals(): setattr(_rf_snapshot_app_patch_4482, 'previous', globals()['_rf_alias_app_patch_4482__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4482, 'uvicorn', globals()['uvicorn'])
if 'v4482_health' in globals(): setattr(_rf_snapshot_app_patch_4482, 'v4482_health', globals()['v4482_health'])
if 'v4482_launch_updater' in globals(): setattr(_rf_snapshot_app_patch_4482, 'v4482_launch_updater', globals()['v4482_launch_updater'])
_rf_layers['app_patch_4482'] = _rf_snapshot_app_patch_4482

# ---- app_patch_4483 ----
import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path
_rf_alias_app_patch_4483__previous = _rf_layers['app_patch_4482']
core = _rf_alias_app_patch_4483__previous.core
app = _rf_alias_app_patch_4483__previous.app
APP_VERSION = '4.4.83'
_mod = _rf_alias_app_patch_4483__previous
_seen = set()
for _ in range(60):
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

def _launch_official_launcher():
    launcher = _Path(core.BASE_DIR) / 'ABRIR_RECEPCION.py'
    if not launcher.is_file():
        raise core.HTTPException(500, 'No se encontró ABRIR_RECEPCION.py')
    candidates = [_Path(core.BASE_DIR) / '.venv' / 'Scripts' / 'pythonw.exe', _Path(core.BASE_DIR) / '.venv' / 'Scripts' / 'python.exe', _Path(_sys.executable)]
    py = next((p for p in candidates if p.is_file()), None)
    if py is None:
        raise core.HTTPException(500, 'No se encontró el Python de Recepción')
    flags = 0
    if _os.name == 'nt':
        flags = getattr(_subprocess, 'CREATE_NO_WINDOW', 0) | getattr(_subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    try:
        _subprocess.Popen([str(py), str(launcher)], cwd=str(core.BASE_DIR), env=_os.environ.copy(), stdin=_subprocess.DEVNULL, stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL, creationflags=flags, close_fds=True)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo abrir el actualizador: {type(exc).__name__}')
    return {'ok': True, 'launcher_started': True, 'version': APP_VERSION}
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.83';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.83';", _js)
    V4483_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.83"!important;\n  font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4483_JS = '\n;(()=>{\n  if(window.__v4483MandatoryUpdater)return;\n  window.__v4483MandatoryUpdater=true;\n  const VERSION=\'4.4.83\';\n\n  async function installUpdate(){\n    const status=document.querySelector(\'#updateStatus\');\n    try{\n      if(status)status.textContent=\'Abriendo actualizador seguro…\';\n      const r=await fetch(\'/api/v4483/launch-updater\',{\n        method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:\'{}\',cache:\'no-store\'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||\'No se pudo abrir el actualizador.\');\n      if(status)status.textContent=\'Actualizador abierto. Las versiones obligatorias se instalan antes de continuar.\';\n      return d;\n    }catch(e){\n      if(status)status.textContent=e?.message||String(e);\n      throw e;\n    }\n  }\n\n  function wire(){\n    window.restartReception=installUpdate;\n    document.querySelectorAll(\'button[onclick*="restartReception"]\').forEach(btn=>{\n      btn.textContent=\'⬆ Instalar actualización\';\n      btn.title=\'Comprueba e instala mediante el launcher oficial\';\n    });\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION; el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n\n  wire();\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',wire,{once:true});\n  setTimeout(wire,250);setTimeout(wire,900);\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4483_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4483_JS
    app.router.routes[:] = [route for route in app.router.routes if not (getattr(route, 'path', None) == '/api/app/restart' and 'POST' in (getattr(route, 'methods', set()) or set()))]
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.post('/api/app/restart')
def restart_v4483(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta acción solo se ejecuta desde la PC de Recepción')
    return _launch_official_launcher()

@app.post('/api/v4483/launch-updater')
def launch_updater_v4483(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta acción solo se ejecuta desde la PC de Recepción')
    return _launch_official_launcher()

@app.get('/api/v4483/health')
def v4483_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'mandatory_update_gate': True, 'legacy_restart_redirected_to_launcher': True, 'automatic_backup_retention': 1, 'database_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4483 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4483, '__name__', 'app_patch_4483')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4483, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4483, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4483, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4483_CSS' in globals(): setattr(_rf_snapshot_app_patch_4483, 'V4483_CSS', globals()['V4483_CSS'])
if 'V4483_JS' in globals(): setattr(_rf_snapshot_app_patch_4483, 'V4483_JS', globals()['V4483_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4483, '_', globals()['_'])
if '_Path' in globals(): setattr(_rf_snapshot_app_patch_4483, '_Path', globals()['_Path'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4483, '_js', globals()['_js'])
if '_launch_official_launcher' in globals(): setattr(_rf_snapshot_app_patch_4483, '_launch_official_launcher', globals()['_launch_official_launcher'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4483, '_mod', globals()['_mod'])
if '_os' in globals(): setattr(_rf_snapshot_app_patch_4483, '_os', globals()['_os'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4483, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4483, '_seen', globals()['_seen'])
if '_subprocess' in globals(): setattr(_rf_snapshot_app_patch_4483, '_subprocess', globals()['_subprocess'])
if '_sys' in globals(): setattr(_rf_snapshot_app_patch_4483, '_sys', globals()['_sys'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4483, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4483, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4483, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4483, 'exc', globals()['exc'])
if 'launch_updater_v4483' in globals(): setattr(_rf_snapshot_app_patch_4483, 'launch_updater_v4483', globals()['launch_updater_v4483'])
if '_rf_alias_app_patch_4483__previous' in globals(): setattr(_rf_snapshot_app_patch_4483, 'previous', globals()['_rf_alias_app_patch_4483__previous'])
if 'restart_v4483' in globals(): setattr(_rf_snapshot_app_patch_4483, 'restart_v4483', globals()['restart_v4483'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4483, 'uvicorn', globals()['uvicorn'])
if 'v4483_health' in globals(): setattr(_rf_snapshot_app_patch_4483, 'v4483_health', globals()['v4483_health'])
_rf_layers['app_patch_4483'] = _rf_snapshot_app_patch_4483

# ---- app_patch_4484 ----
import re as _re
_rf_alias_app_patch_4484__previous = _rf_layers['app_patch_4483']
core = _rf_alias_app_patch_4484__previous.core
app = _rf_alias_app_patch_4484__previous.app
APP_VERSION = '4.4.84'
_mod = _rf_alias_app_patch_4484__previous
_seen = set()
for _ in range(64):
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

_rf_snapshot_app_patch_4484 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4484, '__name__', 'app_patch_4484')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4484, 'APP_VERSION', globals()['APP_VERSION'])
if 'CARD_GATE_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4484, 'CARD_GATE_PATCHED', globals()['CARD_GATE_PATCHED'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4484, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4484, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4484_CSS' in globals(): setattr(_rf_snapshot_app_patch_4484, 'V4484_CSS', globals()['V4484_CSS'])
if 'V4484_JS' in globals(): setattr(_rf_snapshot_app_patch_4484, 'V4484_JS', globals()['V4484_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4484, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4484, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4484, '_mod', globals()['_mod'])
if '_new' in globals(): setattr(_rf_snapshot_app_patch_4484, '_new', globals()['_new'])
if '_old' in globals(): setattr(_rf_snapshot_app_patch_4484, '_old', globals()['_old'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4484, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4484, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4484, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4484, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4484, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4484, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4484__previous' in globals(): setattr(_rf_snapshot_app_patch_4484, 'previous', globals()['_rf_alias_app_patch_4484__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4484, 'uvicorn', globals()['uvicorn'])
if 'v4484_health' in globals(): setattr(_rf_snapshot_app_patch_4484, 'v4484_health', globals()['v4484_health'])
_rf_layers['app_patch_4484'] = _rf_snapshot_app_patch_4484

# ---- app_patch_4485 ----
import os as _os
import re as _re
from datetime import date as _date, datetime as _datetime
_rf_alias_app_patch_4485__previous = _rf_layers['app_patch_4484']
core = _rf_alias_app_patch_4485__previous.core
app = _rf_alias_app_patch_4485__previous.app
APP_VERSION = '4.4.85'
_mod = _rf_alias_app_patch_4485__previous
_seen = set()
for _ in range(68):
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
HOME_BUTTON_PATCHED = False
_PAYMENT_SENTINELS = {-442901: 'EFECTIVO', -442920: 'TRANSFERENCIA BANCARIA'}

def _payment_method_for_visits(visits) -> str:
    methods = set()
    for visit in visits:
        try:
            source_row = int(getattr(visit, 'source_row', 0) or 0)
        except Exception:
            source_row = 0
        method = _PAYMENT_SENTINELS.get(source_row)
        if method:
            methods.add(method)
    if len(methods) == 1:
        return next(iter(methods))
    if len(methods) > 1:
        return 'PAGO MIXTO'
    return 'NO REGISTRADA'

def _payment_proof_lines(visits) -> list[tuple[str, float]]:
    lines: list[tuple[str, float]] = []
    for visit in visits:
        desc = ' '.join(str(getattr(visit, 'procedimiento', None) or '').split())
        if not desc:
            desc = 'CONSULTA MÉDICA'
        try:
            value = round(float(getattr(visit, 'valor', 0) or 0), 2)
        except Exception:
            value = 0.0
        lines.append((desc.upper(), value))
    return lines

def _print_payment_proof_windows(*, patient_name: str, proof_ref: str, service_date: _date, lines: list[tuple[str, float]], payment_method: str, printer_name: str='') -> str:
    if _os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    estimated_h = 410 + max(0, len(lines) - 1) * 34
    doc.DocumentName = 'Comprobante de pago'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Comprobante 80 mm', 315, max(430, min(950, int(estimated_h))))
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {'img': None}

    def font(size: float, bold: bool=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.4, True)
    f_ref = font(7.2, True)
    f_label = font(7.2, True)
    f_text = font(8.3, False)
    f_name = font(10.2, True)
    f_item = font(7.8, False)
    f_item_bold = font(7.8, True)
    f_total_label = font(9.4, True)
    f_total = font(14.2, True)
    f_paid = font(12.0, True)
    f_footer = font(6.5, False)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near
    right = StringFormat()
    right.Alignment = StringAlignment.Far
    right.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width):
        g.DrawLine(pen, 0.0, float(y), float(width), float(y))

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if _os.path.exists(logo_path):
            try:
                image_holder['img'] = Image.FromFile(logo_path)
                g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder['img'] = None
        title_x = 42.0 if image_holder['img'] is not None else 0.0
        title_w = width - title_x
        g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
        y = 43.0
        draw_line(g, y, width)
        y += 9.0
        g.DrawString('COMPROBANTE DE PAGO', f_title, Brushes.Black, RectangleF(0.0, y, width, 19.0), center)
        y += 21.0
        g.DrawString(f'REF. {proof_ref}', f_ref, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
        y += 18.0
        draw_line(g, y, width)
        y += 8.0
        printed_time = _datetime.now().strftime('%H:%M')
        g.DrawString('Fecha:', f_label, Brushes.Black, 0.0, y)
        g.DrawString(service_date.strftime('%d/%m/%Y'), f_text, Brushes.Black, 49.0, y - 1.0)
        g.DrawString('Hora:', f_label, Brushes.Black, width - 95.0, y)
        g.DrawString(printed_time, f_text, Brushes.Black, width - 56.0, y - 1.0)
        y += 22.0
        g.DrawString('PACIENTE', f_label, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
        y += 13.0
        name = ' '.join(str(patient_name or 'SIN NOMBRE').split()).upper()
        measured = g.MeasureString(name, f_name, int(width))
        name_h = max(24.0, min(46.0, float(measured.Height) + 4.0))
        g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, name_h), center)
        y += name_h + 3.0
        draw_line(g, y, width)
        y += 8.0
        g.DrawString('CONCEPTO', f_label, Brushes.Black, 0.0, y)
        g.DrawString('VALOR', f_label, Brushes.Black, RectangleF(width - 74.0, y, 74.0, 14.0), right)
        y += 16.0
        for desc, value in lines:
            item_rect = RectangleF(0.0, y, width - 78.0, 40.0)
            size = g.MeasureString(str(desc), f_item, int(width - 78.0))
            item_h = max(18.0, min(38.0, float(size.Height) + 2.0))
            g.DrawString(str(desc), f_item, Brushes.Black, item_rect)
            g.DrawString(f'${float(value):.2f}', f_item_bold, Brushes.Black, RectangleF(width - 75.0, y, 75.0, 18.0), right)
            y += item_h + 3.0
        draw_line(g, y, width)
        total = round(sum((float(value or 0) for _desc, value in lines)), 2)
        y += 9.0
        g.DrawString('TOTAL PAGADO', f_total_label, Brushes.Black, 0.0, y + 3.0)
        g.DrawString(f'${total:.2f}', f_total, Brushes.Black, RectangleF(width - 110.0, y, 110.0, 24.0), right)
        y += 30.0
        g.DrawString('Forma de pago:', f_label, Brushes.Black, 0.0, y)
        y += 14.0
        g.DrawString(str(payment_method or 'NO REGISTRADA'), f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        y += 24.0
        draw_line(g, y, width)
        y += 10.0
        g.DrawString('PAGADO', f_paid, Brushes.Black, RectangleF(0.0, y, width, 22.0), center)
        y += 26.0
        g.DrawString('Gracias por su confianza.', f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 16.0), center)
        y += 20.0
        g.DrawString('Comprobante interno de pago.\nNo reemplaza la factura electrónica.', f_footer, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_print_page
        except Exception:
            pass
        if image_holder.get('img') is not None:
            try:
                image_holder['img'].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
            right.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen

@app.post('/api/v4485/payment-proof/{patient_id}/{fecha}')
def v4485_print_payment_proof(patient_id: int, fecha: str, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    try:
        target_date = _date.fromisoformat(str(fecha or '')[:10])
    except Exception:
        raise core.HTTPException(400, 'Fecha inválida para el comprobante')
    patient = db.get(core.Patient, int(patient_id))
    if not patient:
        raise core.HTTPException(404, 'Paciente no encontrado')
    visits = list(db.scalars(core.select(core.Visit).where(core.Visit.patient_id == int(patient_id), core.Visit.fecha == target_date).order_by(core.Visit.id.asc())))
    if not visits:
        raise core.HTTPException(404, 'No hay atenciones registradas para ese paciente en esa fecha')
    lines = _payment_proof_lines(visits)
    total = round(sum((value for _desc, value in lines)), 2)
    if total <= 0:
        raise core.HTTPException(400, 'No hay un valor pagado para imprimir el comprobante')
    first_id = min((abs(int(getattr(v, 'id', 0) or 0)) for v in visits))
    proof_ref = f'CP-{first_id:06d}'
    payment_method = _payment_method_for_visits(visits)
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = _print_payment_proof_windows(patient_name=str(getattr(patient, 'nombre', '') or '').strip(), proof_ref=proof_ref, service_date=target_date, lines=lines, payment_method=payment_method, printer_name=printer)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo imprimir el comprobante: {exc}')
    return {'ok': True, 'printed': True, 'printer': used, 'reference': proof_ref, 'patient_id': int(patient_id), 'fecha': target_date.isoformat(), 'total': total, 'payment_method': payment_method, 'message': 'Comprobante de pago enviado a la impresora.'}
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _old_tail = '${homeMore(primary)}</div>`}'
    _new_tail = '<button type="button" class="v4485-payment-proof" onclick="printPaymentProofFromHome(${pid},\'${eh(fecha)}\')">${homeActionIcon(\'receipt\')}<span>Comprobante</span></button>${homeMore(primary)}</div>`}'
    if _old_tail in _js:
        _js = _js.replace(_old_tail, _new_tail, 1)
        HOME_BUTTON_PATCHED = True
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.85';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.85';", _js)
    V4485_CSS = '\n.v4485-payment-proof{\n  border-color:#b8d7c4!important;\n  background:#f2fbf5!important;\n  color:#2f6e49!important;\n}\n.v4485-payment-proof:hover{background:#e5f6eb!important}\n.v4485-pay-toast{\n  position:fixed;right:18px;bottom:18px;z-index:2147483600;\n  max-width:390px;padding:11px 14px;border-radius:11px;\n  background:#225f42;color:#fff;box-shadow:0 10px 30px rgba(25,62,45,.22);\n  font-size:11px;font-weight:850\n}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.85"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4485_JS = "\n;(()=>{\n  if(window.__v4485PaymentProof)return;\n  window.__v4485PaymentProof=true;\n  const VERSION='4.4.85';\n\n  function toast(msg){\n    document.querySelector('.v4485-pay-toast')?.remove();\n    const el=document.createElement('div');\n    el.className='v4485-pay-toast';\n    el.textContent=String(msg||'Comprobante enviado a la impresora.');\n    document.body.appendChild(el);\n    setTimeout(()=>el.remove(),4200);\n  }\n\n  window.printPaymentProofFromHome=async function(patientId,fecha){\n    const id=Number(patientId||0),day=String(fecha||'').slice(0,10);\n    if(!id||!day)return;\n    const buttons=[...document.querySelectorAll('.v4485-payment-proof')];\n    buttons.forEach(b=>b.disabled=true);\n    try{\n      const r=await fetch(`/api/v4485/payment-proof/${id}/${encodeURIComponent(day)}`,{\n        method:'POST',credentials:'same-origin',\n        headers:{'Content-Type':'application/json'},\n        body:'{}',\n        cache:'no-store'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||'No se pudo imprimir el comprobante.');\n      toast(`✓ ${d.message||'Comprobante de pago enviado a la impresora.'}`);\n    }catch(e){\n      alert(e?.message||String(e));\n    }finally{\n      buttons.forEach(b=>b.disabled=false);\n    }\n  };\n\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4485_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4485_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4485/health')
def v4485_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'payment_proof': True, 'home_button_patched': HOME_BUTTON_PATCHED, 'automatic_print': False, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4485 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4485, '__name__', 'app_patch_4485')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4485, 'APP_VERSION', globals()['APP_VERSION'])
if 'HOME_BUTTON_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4485, 'HOME_BUTTON_PATCHED', globals()['HOME_BUTTON_PATCHED'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4485, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4485, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4485_CSS' in globals(): setattr(_rf_snapshot_app_patch_4485, 'V4485_CSS', globals()['V4485_CSS'])
if 'V4485_JS' in globals(): setattr(_rf_snapshot_app_patch_4485, 'V4485_JS', globals()['V4485_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4485, '_', globals()['_'])
if '_PAYMENT_SENTINELS' in globals(): setattr(_rf_snapshot_app_patch_4485, '_PAYMENT_SENTINELS', globals()['_PAYMENT_SENTINELS'])
if '_date' in globals(): setattr(_rf_snapshot_app_patch_4485, '_date', globals()['_date'])
if '_datetime' in globals(): setattr(_rf_snapshot_app_patch_4485, '_datetime', globals()['_datetime'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4485, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4485, '_mod', globals()['_mod'])
if '_new_tail' in globals(): setattr(_rf_snapshot_app_patch_4485, '_new_tail', globals()['_new_tail'])
if '_old_tail' in globals(): setattr(_rf_snapshot_app_patch_4485, '_old_tail', globals()['_old_tail'])
if '_os' in globals(): setattr(_rf_snapshot_app_patch_4485, '_os', globals()['_os'])
if '_payment_method_for_visits' in globals(): setattr(_rf_snapshot_app_patch_4485, '_payment_method_for_visits', globals()['_payment_method_for_visits'])
if '_payment_proof_lines' in globals(): setattr(_rf_snapshot_app_patch_4485, '_payment_proof_lines', globals()['_payment_proof_lines'])
if '_print_payment_proof_windows' in globals(): setattr(_rf_snapshot_app_patch_4485, '_print_payment_proof_windows', globals()['_print_payment_proof_windows'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4485, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4485, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4485, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4485, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4485, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4485, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4485__previous' in globals(): setattr(_rf_snapshot_app_patch_4485, 'previous', globals()['_rf_alias_app_patch_4485__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4485, 'uvicorn', globals()['uvicorn'])
if 'v4485_health' in globals(): setattr(_rf_snapshot_app_patch_4485, 'v4485_health', globals()['v4485_health'])
if 'v4485_print_payment_proof' in globals(): setattr(_rf_snapshot_app_patch_4485, 'v4485_print_payment_proof', globals()['v4485_print_payment_proof'])
_rf_layers['app_patch_4485'] = _rf_snapshot_app_patch_4485

# ---- app_patch_4486 ----
import re as _re
_rf_alias_app_patch_4486__previous = _rf_layers['app_patch_4485']
core = _rf_alias_app_patch_4486__previous.core
app = _rf_alias_app_patch_4486__previous.app
APP_VERSION = '4.4.86'
_mod = _rf_alias_app_patch_4486__previous
_seen = set()
for _ in range(72):
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
HOME_ACTIONS_PATCHED = False
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _pattern = '  function homeActions\\(g,fecha,primary\\)\\{.*?\\n  function v4457ConsultationTurnMap'
    _replacement = '  function homeActions(g,fecha,primary){\n    const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||\'\').trim());\n    const pid=Number(g.patient?.id||0);\n    const receiptDisabled=hasConsultation?\'\':` disabled aria-disabled="true" title="Este registro no tiene consulta médica"`;\n    return `<div class="v478-home-actions"><details class="v4486-print-menu"><summary class="v4486-print-summary">${homeActionIcon(\'print\')}<span>Imprimir</span></summary><div class="v4486-print-pop"><button type="button"${receiptDisabled} onclick="event.preventDefault();event.stopPropagation();this.closest(\'details\')?.removeAttribute(\'open\');reprintReceiptFromHome(${pid},\'${eh(fecha)}\')">${homeActionIcon(\'receipt\')}<span>Imprimir recibo</span></button><button type="button" onclick="event.preventDefault();event.stopPropagation();this.closest(\'details\')?.removeAttribute(\'open\');printPaymentProofFromHome(${pid},\'${eh(fecha)}\')">${homeActionIcon(\'print\')}<span>Imprimir comprobante</span></button></div></details>${homeMore(primary)}</div>`;\n  }\n  function v4457ConsultationTurnMap'
    _js, _count = _re.subn(_pattern, _replacement, _js, count=1, flags=_re.S)
    HOME_ACTIONS_PATCHED = bool(_count)
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.86';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.86';", _js)
    V4486_CSS = '\n.v4485-payment-proof{display:none!important}\n.v4486-print-menu{position:relative;display:inline-block}\n.v4486-print-summary{\n  list-style:none;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:5px;\n  border:1px solid #dbe3ed;background:#fff;color:#425774;border-radius:8px;\n  padding:6px 8px;font-size:9px;font-weight:850;min-height:29px;line-height:1;user-select:none\n}\n.v4486-print-summary::-webkit-details-marker{display:none}\n.v4486-print-summary:hover{background:#f3f7fb}\n.v4486-print-menu[open]>.v4486-print-summary{background:#edf5ff;border-color:#bad0ea;color:#315f8f}\n.v4486-print-pop{\n  position:absolute;right:0;top:34px;z-index:80;display:grid;gap:4px;min-width:178px;\n  padding:6px;border:1px solid #d7e1ec;border-radius:10px;background:#fff;\n  box-shadow:0 10px 28px rgba(35,55,80,.18)\n}\n.v4486-print-pop button{\n  width:100%;display:flex;align-items:center;gap:7px;border:0;border-radius:8px;\n  background:#fff;color:#3e536f;padding:8px 9px;font-size:9px;font-weight:850;text-align:left;white-space:nowrap\n}\n.v4486-print-pop button:hover{background:#f1f6fb}\n.v4486-print-pop button:disabled{opacity:.42;cursor:not-allowed;background:#f7f8fa}\n.v4486-print-pop .v488-home-action-svg{width:13px;height:13px;flex:0 0 13px}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.86"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n@media(max-width:760px){.v4486-print-pop{right:auto;left:0}}\n'
    V4486_JS = "\n;(()=>{\n  if(window.__v4486SinglePrintMenu)return;\n  window.__v4486SinglePrintMenu=true;\n  const VERSION='4.4.86';\n\n  document.addEventListener('click',e=>{\n    document.querySelectorAll('.v4486-print-menu[open]').forEach(menu=>{\n      if(!menu.contains(e.target))menu.removeAttribute('open');\n    });\n  },true);\n\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4486_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4486_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4486/health')
def v4486_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'single_print_button': True, 'home_actions_patched': HOME_ACTIONS_PATCHED, 'print_choices': ['receipt', 'payment_proof'], 'payment_proof_preserved': True, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4486 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4486, '__name__', 'app_patch_4486')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4486, 'APP_VERSION', globals()['APP_VERSION'])
if 'HOME_ACTIONS_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4486, 'HOME_ACTIONS_PATCHED', globals()['HOME_ACTIONS_PATCHED'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4486, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4486, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4486_CSS' in globals(): setattr(_rf_snapshot_app_patch_4486, 'V4486_CSS', globals()['V4486_CSS'])
if 'V4486_JS' in globals(): setattr(_rf_snapshot_app_patch_4486, 'V4486_JS', globals()['V4486_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4486, '_', globals()['_'])
if '_count' in globals(): setattr(_rf_snapshot_app_patch_4486, '_count', globals()['_count'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4486, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4486, '_mod', globals()['_mod'])
if '_pattern' in globals(): setattr(_rf_snapshot_app_patch_4486, '_pattern', globals()['_pattern'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4486, '_re', globals()['_re'])
if '_replacement' in globals(): setattr(_rf_snapshot_app_patch_4486, '_replacement', globals()['_replacement'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4486, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4486, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4486, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4486, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4486, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4486__previous' in globals(): setattr(_rf_snapshot_app_patch_4486, 'previous', globals()['_rf_alias_app_patch_4486__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4486, 'uvicorn', globals()['uvicorn'])
if 'v4486_health' in globals(): setattr(_rf_snapshot_app_patch_4486, 'v4486_health', globals()['v4486_health'])
_rf_layers['app_patch_4486'] = _rf_snapshot_app_patch_4486

# ---- app_patch_4487 ----
import re as _re
_rf_alias_app_patch_4487__previous = _rf_layers['app_patch_4486']
core = _rf_alias_app_patch_4487__previous.core
app = _rf_alias_app_patch_4487__previous.app
APP_VERSION = '4.4.87'
_mod = _rf_alias_app_patch_4487__previous
_seen = set()
for _ in range(76):
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
PAYMENT_RENDER_PATCHED = False
try:
    _payment_mod = getattr(_rf_alias_app_patch_4487__previous, 'previous', None)
    if _payment_mod is None:
        raise RuntimeError('No se encontró la capa del comprobante v4.4.85')

    def _print_payment_proof_windows_v4487(*, patient_name: str, proof_ref: str, service_date, lines, payment_method: str, printer_name: str='') -> str:
        import os as _os
        from datetime import datetime as _datetime
        if _os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        estimated_h = 410 + max(0, len(lines) - 1) * 34
        doc.DocumentName = 'Comprobante de pago'
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize('Comprobante 80 mm', 315, max(430, min(950, int(estimated_h))))
        doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
        fonts = []
        image_holder = {'img': None}

        def font(size: float, bold: bool=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_doctor = font(9.4, True)
        f_specialty = font(7.0, False)
        f_title = font(11.4, True)
        f_ref = font(7.2, True)
        f_label = font(7.2, True)
        f_text = font(8.3, False)
        f_name = font(10.2, True)
        f_item = font(7.8, False)
        f_item_bold = font(7.8, True)
        f_total_label = font(9.4, True)
        f_total = font(14.2, True)
        f_paid = font(12.0, True)
        f_footer = font(6.5, False)
        pen = Pen(Color.Black, 1.0)
        center = StringFormat()
        center.Alignment = StringAlignment.Center
        center.LineAlignment = StringAlignment.Near
        right = StringFormat()
        right.Alignment = StringAlignment.Far
        right.LineAlignment = StringAlignment.Near

        def draw_line(g, y, width):
            g.DrawLine(pen, 0.0, float(y), float(width), float(y))

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            safe_right = max(210.0, width - 22.0)
            y = 0.0
            logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
            if _os.path.exists(logo_path):
                try:
                    image_holder['img'] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
                except Exception:
                    image_holder['img'] = None
            title_x = 42.0 if image_holder['img'] is not None else 0.0
            title_w = width - title_x
            g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
            g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
            y = 43.0
            draw_line(g, y, width)
            y += 9.0
            g.DrawString('COMPROBANTE DE PAGO', f_title, Brushes.Black, RectangleF(0.0, y, width, 19.0), center)
            y += 21.0
            g.DrawString(f'REF. {proof_ref}', f_ref, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
            y += 18.0
            draw_line(g, y, width)
            y += 8.0
            printed_time = _datetime.now().strftime('%H:%M')
            g.DrawString('Fecha:', f_label, Brushes.Black, 0.0, y)
            g.DrawString(service_date.strftime('%d/%m/%Y'), f_text, Brushes.Black, 49.0, y - 1.0)
            g.DrawString('Hora:', f_label, Brushes.Black, safe_right - 88.0, y)
            g.DrawString(printed_time, f_text, Brushes.Black, safe_right - 48.0, y - 1.0)
            y += 22.0
            g.DrawString('PACIENTE', f_label, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
            y += 13.0
            name = ' '.join(str(patient_name or 'SIN NOMBRE').split()).upper()
            measured = g.MeasureString(name, f_name, int(width))
            name_h = max(24.0, min(46.0, float(measured.Height) + 4.0))
            g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, name_h), center)
            y += name_h + 3.0
            draw_line(g, y, width)
            y += 8.0
            g.DrawString('CONCEPTO', f_label, Brushes.Black, 0.0, y)
            g.DrawString('VALOR', f_label, Brushes.Black, RectangleF(safe_right - 72.0, y, 72.0, 14.0), right)
            y += 16.0
            for desc, value in lines:
                item_rect = RectangleF(0.0, y, max(120.0, safe_right - 82.0), 40.0)
                size = g.MeasureString(str(desc), f_item_bold, int(max(120.0, safe_right - 82.0)))
                item_h = max(18.0, min(38.0, float(size.Height) + 2.0))
                g.DrawString(str(desc), f_item_bold, Brushes.Black, item_rect)
                g.DrawString(f'${float(value):.2f}', f_item_bold, Brushes.Black, RectangleF(safe_right - 74.0, y, 74.0, 18.0), right)
                y += item_h + 3.0
            draw_line(g, y, width)
            total = round(sum((float(value or 0) for _desc, value in lines)), 2)
            y += 9.0
            g.DrawString('TOTAL PAGADO', f_total_label, Brushes.Black, 0.0, y + 3.0)
            g.DrawString(f'${total:.2f}', f_total, Brushes.Black, RectangleF(safe_right - 112.0, y, 112.0, 24.0), right)
            y += 30.0
            g.DrawString('Forma de pago:', f_label, Brushes.Black, 0.0, y)
            y += 14.0
            g.DrawString(str(payment_method or 'NO REGISTRADA'), f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
            y += 24.0
            draw_line(g, y, width)
            y += 10.0
            g.DrawString('PAGADO', f_paid, Brushes.Black, RectangleF(0.0, y, width, 22.0), center)
            y += 26.0
            g.DrawString('Gracias por su confianza.', f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 16.0), center)
            y += 20.0
            g.DrawString('Comprobante interno de pago.\nNo reemplaza la factura electrónica.', f_footer, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            try:
                pen.Dispose()
            except Exception:
                pass
            try:
                center.Dispose()
                right.Dispose()
            except Exception:
                pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    _payment_mod._print_payment_proof_windows = _print_payment_proof_windows_v4487
    PAYMENT_RENDER_PATCHED = True
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.87';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.87';", _js)
    V4487_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.87"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4487_JS = "\n;(()=>{\n  if(window.__v4487PaymentProofSafeRight)return;\n  window.__v4487PaymentProofSafeRight=true;\n  const VERSION='4.4.87';\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4487_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4487_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4487/health')
def v4487_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'payment_render_patched': PAYMENT_RENDER_PATCHED, 'safe_right_shift_units': 22, 'approx_safe_right_shift_mm': 5.6, 'concept_bold': True, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4487 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4487, '__name__', 'app_patch_4487')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4487, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4487, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4487, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PAYMENT_RENDER_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4487, 'PAYMENT_RENDER_PATCHED', globals()['PAYMENT_RENDER_PATCHED'])
if 'V4487_CSS' in globals(): setattr(_rf_snapshot_app_patch_4487, 'V4487_CSS', globals()['V4487_CSS'])
if 'V4487_JS' in globals(): setattr(_rf_snapshot_app_patch_4487, 'V4487_JS', globals()['V4487_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4487, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4487, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4487, '_mod', globals()['_mod'])
if '_payment_mod' in globals(): setattr(_rf_snapshot_app_patch_4487, '_payment_mod', globals()['_payment_mod'])
if '_print_payment_proof_windows_v4487' in globals(): setattr(_rf_snapshot_app_patch_4487, '_print_payment_proof_windows_v4487', globals()['_print_payment_proof_windows_v4487'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4487, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4487, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4487, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4487, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4487, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4487, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4487__previous' in globals(): setattr(_rf_snapshot_app_patch_4487, 'previous', globals()['_rf_alias_app_patch_4487__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4487, 'uvicorn', globals()['uvicorn'])
if 'v4487_health' in globals(): setattr(_rf_snapshot_app_patch_4487, 'v4487_health', globals()['v4487_health'])
_rf_layers['app_patch_4487'] = _rf_snapshot_app_patch_4487

# ---- app_patch_4488 ----
import re as _re
_rf_alias_app_patch_4488__previous = _rf_layers['app_patch_4487']
core = _rf_alias_app_patch_4488__previous.core
app = _rf_alias_app_patch_4488__previous.app
APP_VERSION = '4.4.88'
_mod = _rf_alias_app_patch_4488__previous
_seen = set()
for _ in range(80):
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
PAYMENT_RENDER_PATCHED = False
try:
    _payment_mod = getattr(getattr(_rf_alias_app_patch_4488__previous, 'previous', None), 'previous', None)
    if _payment_mod is None:
        raise RuntimeError('No se encontró la capa del comprobante v4.4.85')

    def _print_payment_proof_windows_v4488(*, patient_name: str, proof_ref: str, service_date, lines, payment_method: str, printer_name: str='') -> str:
        import os as _os
        from datetime import datetime as _datetime
        if _os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        estimated_h = 360 + max(0, len(lines) - 1) * 34
        doc.DocumentName = 'Comprobante de pago'
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize('Comprobante 80 mm', 315, max(380, min(900, int(estimated_h))))
        doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
        fonts = []
        image_holder = {'img': None}

        def font(size: float, bold: bool=False):
            f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f
        f_doctor = font(9.4, True)
        f_specialty = font(7.0, False)
        f_title = font(11.4, True)
        f_ref = font(7.2, True)
        f_label = font(7.2, True)
        f_text = font(8.3, False)
        f_name = font(10.2, True)
        f_item = font(7.8, False)
        f_item_bold = font(7.8, True)
        f_total_label = font(9.4, True)
        f_total = font(14.2, True)
        f_footer = font(6.5, False)
        pen = Pen(Color.Black, 1.0)
        center = StringFormat()
        center.Alignment = StringAlignment.Center
        center.LineAlignment = StringAlignment.Near
        right = StringFormat()
        right.Alignment = StringAlignment.Far
        right.LineAlignment = StringAlignment.Near

        def draw_line(g, y, width):
            g.DrawLine(pen, 0.0, float(y), float(width), float(y))

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            safe_right = max(210.0, width - 22.0)
            y = 0.0
            logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
            if _os.path.exists(logo_path):
                try:
                    image_holder['img'] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
                except Exception:
                    image_holder['img'] = None
            title_x = 42.0 if image_holder['img'] is not None else 0.0
            title_w = width - title_x
            g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
            g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
            y = 43.0
            draw_line(g, y, width)
            y += 9.0
            g.DrawString('COMPROBANTE DE PAGO', f_title, Brushes.Black, RectangleF(0.0, y, width, 19.0), center)
            y += 21.0
            g.DrawString(f'REF. {proof_ref}', f_ref, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
            y += 18.0
            draw_line(g, y, width)
            y += 8.0
            printed_time = _datetime.now().strftime('%H:%M')
            g.DrawString('Fecha:', f_label, Brushes.Black, 0.0, y)
            g.DrawString(service_date.strftime('%d/%m/%Y'), f_text, Brushes.Black, 49.0, y - 1.0)
            g.DrawString('Hora:', f_label, Brushes.Black, safe_right - 88.0, y)
            g.DrawString(printed_time, f_text, Brushes.Black, safe_right - 48.0, y - 1.0)
            y += 22.0
            g.DrawString('PACIENTE', f_label, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
            y += 13.0
            name = ' '.join(str(patient_name or 'SIN NOMBRE').split()).upper()
            measured = g.MeasureString(name, f_name, int(width))
            name_h = max(24.0, min(46.0, float(measured.Height) + 4.0))
            g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, name_h), center)
            y += name_h + 3.0
            draw_line(g, y, width)
            y += 8.0
            g.DrawString('CONCEPTO', f_label, Brushes.Black, 0.0, y)
            g.DrawString('VALOR', f_label, Brushes.Black, RectangleF(safe_right - 72.0, y, 72.0, 14.0), right)
            y += 16.0
            for desc, value in lines:
                item_rect = RectangleF(0.0, y, max(120.0, safe_right - 82.0), 40.0)
                size = g.MeasureString(str(desc), f_item_bold, int(max(120.0, safe_right - 82.0)))
                item_h = max(18.0, min(38.0, float(size.Height) + 2.0))
                g.DrawString(str(desc), f_item_bold, Brushes.Black, item_rect)
                g.DrawString(f'${float(value):.2f}', f_item_bold, Brushes.Black, RectangleF(safe_right - 74.0, y, 74.0, 18.0), right)
                y += item_h + 3.0
            draw_line(g, y, width)
            total = round(sum((float(value or 0) for _desc, value in lines)), 2)
            y += 9.0
            g.DrawString('TOTAL PAGADO', f_total_label, Brushes.Black, 0.0, y + 3.0)
            g.DrawString(f'${total:.2f}', f_total, Brushes.Black, RectangleF(safe_right - 112.0, y, 112.0, 24.0), right)
            y += 30.0
            g.DrawString('Forma de pago:', f_label, Brushes.Black, 0.0, y)
            y += 14.0
            g.DrawString(str(payment_method or 'NO REGISTRADA'), f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
            y += 24.0
            draw_line(g, y, width)
            y += 12.0
            g.DrawString('Comprobante interno de pago.\nNo reemplaza la factura electrónica.', f_footer, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get('img') is not None:
                try:
                    image_holder['img'].Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            try:
                pen.Dispose()
            except Exception:
                pass
            try:
                center.Dispose()
                right.Dispose()
            except Exception:
                pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    _payment_mod._print_payment_proof_windows = _print_payment_proof_windows_v4488
    PAYMENT_RENDER_PATCHED = True
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.88';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.88';", _js)
    V4488_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.88"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4488_JS = "\n;(()=>{\n  if(window.__v4488PaymentProofCompact)return;\n  window.__v4488PaymentProofCompact=true;\n  const VERSION='4.4.88';\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4488_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4488_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4488/health')
def v4488_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'payment_render_patched': PAYMENT_RENDER_PATCHED, 'safe_right_shift_units': 22, 'approx_safe_right_shift_mm': 5.6, 'concept_bold': True, 'removed_paid_label': True, 'removed_thank_you': True, 'legal_footer_preserved': True, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4488 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4488, '__name__', 'app_patch_4488')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4488, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4488, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4488, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PAYMENT_RENDER_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4488, 'PAYMENT_RENDER_PATCHED', globals()['PAYMENT_RENDER_PATCHED'])
if 'V4488_CSS' in globals(): setattr(_rf_snapshot_app_patch_4488, 'V4488_CSS', globals()['V4488_CSS'])
if 'V4488_JS' in globals(): setattr(_rf_snapshot_app_patch_4488, 'V4488_JS', globals()['V4488_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4488, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4488, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4488, '_mod', globals()['_mod'])
if '_payment_mod' in globals(): setattr(_rf_snapshot_app_patch_4488, '_payment_mod', globals()['_payment_mod'])
if '_print_payment_proof_windows_v4488' in globals(): setattr(_rf_snapshot_app_patch_4488, '_print_payment_proof_windows_v4488', globals()['_print_payment_proof_windows_v4488'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4488, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4488, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4488, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4488, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4488, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4488, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4488__previous' in globals(): setattr(_rf_snapshot_app_patch_4488, 'previous', globals()['_rf_alias_app_patch_4488__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4488, 'uvicorn', globals()['uvicorn'])
if 'v4488_health' in globals(): setattr(_rf_snapshot_app_patch_4488, 'v4488_health', globals()['v4488_health'])
_rf_layers['app_patch_4488'] = _rf_snapshot_app_patch_4488

# ---- app_patch_4489 ----
import os as _os
import re as _re
_rf_alias_app_patch_4489__previous = _rf_layers['app_patch_4488']
core = _rf_alias_app_patch_4489__previous.core
app = _rf_alias_app_patch_4489__previous.app
APP_VERSION = '4.4.89'
_mod = _rf_alias_app_patch_4489__previous
_seen = set()
for _ in range(84):
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

def _print_billing_data_form_windows(printer_name: str='') -> str:
    if _os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    doc.DocumentName = 'Datos para factura'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Formulario factura 80 mm', 315, 600)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {'img': None}

    def font(size: float, bold: bool=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.0, True)
    f_intro = font(7.2, False)
    f_label = font(7.5, True)
    f_note = font(6.4, False)
    f_footer = font(7.0, True)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width, x1=0.0, x2=None):
        g.DrawLine(pen, float(x1), float(y), float(width if x2 is None else x2), float(y))

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if _os.path.exists(logo_path):
            try:
                image_holder['img'] = Image.FromFile(logo_path)
                g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder['img'] = None
        title_x = 42.0 if image_holder['img'] is not None else 0.0
        title_w = width - title_x
        g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
        y = 43.0
        draw_line(g, y, width)
        y += 10.0
        g.DrawString('DATOS PARA FACTURA', f_title, Brushes.Black, RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        g.DrawString('Complete los datos de la persona o empresa\na quien desea facturar.', f_intro, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        y += 34.0
        draw_line(g, y, width)

        def field(label: str, lines: int=1, note: str=''):
            nonlocal y
            y += 10.0
            g.DrawString(label, f_label, Brushes.Black, 0.0, y)
            if note:
                g.DrawString(note, f_note, Brushes.Black, RectangleF(0.0, y + 12.0, width, 12.0))
                y += 13.0
            y += 18.0
            for _ in range(lines):
                draw_line(g, y, width - 4.0, 0.0, width - 4.0)
                y += 21.0
        field('CÉDULA / RUC:')
        field('NOMBRES / RAZÓN SOCIAL:', 2)
        field('DIRECCIÓN:', 2)
        field('TELÉFONO:')
        field('CORREO:', 2, '(OPCIONAL)')
        y += 2.0
        draw_line(g, y, width)
        y += 12.0
        g.DrawString('ENTREGAR EN RECEPCIÓN', f_footer, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_print_page
        except Exception:
            pass
        if image_holder.get('img') is not None:
            try:
                image_holder['img'].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen

@app.post('/api/v4489/print-billing-data-form')
def v4489_print_billing_data_form(user=core.Depends(core.current_user)):
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = _print_billing_data_form_windows(printer)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo imprimir el formulario: {exc}')
    return {'ok': True, 'printed': True, 'printer': used, 'message': 'Formulario para datos de factura enviado a la impresora.'}
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.89';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.89';", _js)
    V4489_CSS = '\n.v4489-billing-form-print{\n  margin-top:10px;padding:10px 11px;border:1px dashed #b8cbe0;border-radius:10px;\n  background:#f7fbff;display:flex;align-items:center;justify-content:space-between;gap:10px\n}\n.v4489-billing-form-print div{min-width:0}\n.v4489-billing-form-print b{display:block;font-size:10px;color:#334f70;margin-bottom:2px}\n.v4489-billing-form-print small{display:block;font-size:8px;line-height:1.3;color:#70839a}\n.v4489-billing-form-print button{\n  flex:0 0 auto;border:1px solid #b9cee4;background:#fff;color:#355f88;border-radius:8px;\n  padding:7px 9px;font-size:9px;font-weight:850;cursor:pointer\n}\n.v4489-billing-form-print button:hover{background:#edf5ff}\n.v4489-billing-form-print button:disabled{opacity:.55;cursor:wait}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.89"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4489_JS = '\n;(()=>{\n  if(window.__v4489BillingDataForm)return;\n  window.__v4489BillingDataForm=true;\n  const VERSION=\'4.4.89\';\n\n  async function printBillingDataForm(btn){\n    if(btn)btn.disabled=true;\n    try{\n      const r=await fetch(\'/api/v4489/print-billing-data-form\',{\n        method:\'POST\',\n        credentials:\'same-origin\',\n        headers:{\'Content-Type\':\'application/json\'},\n        body:\'{}\',\n        cache:\'no-store\'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||\'No se pudo imprimir el formulario.\');\n      const old=btn?.textContent;\n      if(btn){btn.textContent=\'✓ Enviado\';setTimeout(()=>{btn.textContent=old||\'Imprimir formulario\';},1600)}\n    }catch(e){\n      alert(e?.message||String(e));\n    }finally{\n      if(btn)btn.disabled=false;\n    }\n  }\n  window.printBillingDataForm=printBillingDataForm;\n\n  function inject(){\n    const alt=document.querySelector(\'#billingRecipientAlt\');\n    if(!alt||alt.querySelector(\'.v4489-billing-form-print\'))return;\n    const help=alt.querySelector(\'.billing-recipient-help\');\n    const box=document.createElement(\'div\');\n    box.className=\'v4489-billing-form-print\';\n    box.innerHTML=\'<div><b>¿El paciente llenará otros datos?</b><small>Imprime una hoja térmica para que escriba los datos de facturación.</small></div><button type="button">🖨 Imprimir formulario</button>\';\n    box.querySelector(\'button\')?.addEventListener(\'click\',function(){printBillingDataForm(this)});\n    if(help)alt.insertBefore(box,help);else alt.appendChild(box);\n  }\n\n  const oldOpen=window.openBillingRecipientEditor;\n  if(typeof oldOpen===\'function\'&&!oldOpen.__v4489){\n    const wrapped=async function(){\n      const r=await oldOpen.apply(this,arguments);\n      setTimeout(inject,0);setTimeout(inject,70);\n      return r;\n    };\n    wrapped.__v4489=true;\n    window.openBillingRecipientEditor=wrapped;\n  }\n\n  function paint(){\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4489_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4489_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4489/health')
def v4489_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'billing_data_form': True, 'only_in_alternate_recipient_ui': True, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4489 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4489, '__name__', 'app_patch_4489')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4489, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4489, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4489, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4489_CSS' in globals(): setattr(_rf_snapshot_app_patch_4489, 'V4489_CSS', globals()['V4489_CSS'])
if 'V4489_JS' in globals(): setattr(_rf_snapshot_app_patch_4489, 'V4489_JS', globals()['V4489_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4489, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4489, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4489, '_mod', globals()['_mod'])
if '_os' in globals(): setattr(_rf_snapshot_app_patch_4489, '_os', globals()['_os'])
if '_print_billing_data_form_windows' in globals(): setattr(_rf_snapshot_app_patch_4489, '_print_billing_data_form_windows', globals()['_print_billing_data_form_windows'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4489, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4489, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4489, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4489, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4489, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4489, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4489__previous' in globals(): setattr(_rf_snapshot_app_patch_4489, 'previous', globals()['_rf_alias_app_patch_4489__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4489, 'uvicorn', globals()['uvicorn'])
if 'v4489_health' in globals(): setattr(_rf_snapshot_app_patch_4489, 'v4489_health', globals()['v4489_health'])
if 'v4489_print_billing_data_form' in globals(): setattr(_rf_snapshot_app_patch_4489, 'v4489_print_billing_data_form', globals()['v4489_print_billing_data_form'])
_rf_layers['app_patch_4489'] = _rf_snapshot_app_patch_4489

# ---- app_patch_4490 ----
import os as _os
import re as _re
_rf_alias_app_patch_4490__previous = _rf_layers['app_patch_4489']
core = _rf_alias_app_patch_4490__previous.core
app = _rf_alias_app_patch_4490__previous.app
APP_VERSION = '4.4.90'
_mod = _rf_alias_app_patch_4490__previous
_seen = set()
for _ in range(88):
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
FORM_RENDER_PATCHED = False

def _print_billing_data_form_windows_v4490(printer_name: str='') -> str:
    if _os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    doc.DocumentName = 'Datos para factura'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Formulario factura 80 mm', 315, 500)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {'img': None}

    def font(size: float, bold: bool=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.0, True)
    f_intro = font(7.2, False)
    f_label = font(7.5, True)
    f_footer = font(7.0, True)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width, x1=0.0, x2=None):
        g.DrawLine(pen, float(x1), float(y), float(width if x2 is None else x2), float(y))

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if _os.path.exists(logo_path):
            try:
                image_holder['img'] = Image.FromFile(logo_path)
                g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder['img'] = None
        title_x = 42.0 if image_holder['img'] is not None else 0.0
        title_w = width - title_x
        g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
        y = 43.0
        draw_line(g, y, width)
        y += 10.0
        g.DrawString('DATOS PARA FACTURA', f_title, Brushes.Black, RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        g.DrawString('Complete los datos de la persona o empresa\na quien desea facturar.', f_intro, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        y += 34.0
        draw_line(g, y, width)

        def field(label: str, lines: int=1):
            nonlocal y
            y += 11.0
            g.DrawString(label, f_label, Brushes.Black, 0.0, y)
            y += 27.0
            for _ in range(lines):
                draw_line(g, y, width - 4.0, 0.0, width - 4.0)
                y += 22.0
        field('CÉDULA / RUC:')
        field('NOMBRE / RAZÓN SOCIAL:')
        field('DIRECCIÓN:', 2)
        field('TELÉFONO:')
        field('CORREO (OPCIONAL):')
        y += 8.0
        g.DrawString('ENTREGAR EN RECEPCIÓN', f_footer, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_print_page
        except Exception:
            pass
        if image_holder.get('img') is not None:
            try:
                image_holder['img'].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen
try:
    _rf_alias_app_patch_4490__previous._print_billing_data_form_windows = _print_billing_data_form_windows_v4490
    FORM_RENDER_PATCHED = True
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.90';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.90';", _js)
    V4490_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.90"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4490_JS = "\n;(()=>{\n  if(window.__v4490BillingDataFormCompact)return;\n  window.__v4490BillingDataFormCompact=true;\n  const VERSION='4.4.90';\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4490_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4490_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4490/health')
def v4490_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'form_render_patched': FORM_RENDER_PATCHED, 'cedula_lines': 1, 'name_lines': 1, 'address_lines': 2, 'phone_lines': 1, 'email_lines': 1, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4490 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4490, '__name__', 'app_patch_4490')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4490, 'APP_VERSION', globals()['APP_VERSION'])
if 'FORM_RENDER_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4490, 'FORM_RENDER_PATCHED', globals()['FORM_RENDER_PATCHED'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4490, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4490, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4490_CSS' in globals(): setattr(_rf_snapshot_app_patch_4490, 'V4490_CSS', globals()['V4490_CSS'])
if 'V4490_JS' in globals(): setattr(_rf_snapshot_app_patch_4490, 'V4490_JS', globals()['V4490_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4490, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4490, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4490, '_mod', globals()['_mod'])
if '_os' in globals(): setattr(_rf_snapshot_app_patch_4490, '_os', globals()['_os'])
if '_print_billing_data_form_windows_v4490' in globals(): setattr(_rf_snapshot_app_patch_4490, '_print_billing_data_form_windows_v4490', globals()['_print_billing_data_form_windows_v4490'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4490, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4490, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4490, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4490, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4490, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4490, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4490__previous' in globals(): setattr(_rf_snapshot_app_patch_4490, 'previous', globals()['_rf_alias_app_patch_4490__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4490, 'uvicorn', globals()['uvicorn'])
if 'v4490_health' in globals(): setattr(_rf_snapshot_app_patch_4490, 'v4490_health', globals()['v4490_health'])
_rf_layers['app_patch_4490'] = _rf_snapshot_app_patch_4490

# ---- app_patch_4491 ----
import os as _os
import re as _re
_rf_alias_app_patch_4491__previous = _rf_layers['app_patch_4490']
core = _rf_alias_app_patch_4491__previous.core
app = _rf_alias_app_patch_4491__previous.app
APP_VERSION = '4.4.91'
_mod = _rf_alias_app_patch_4491__previous
_seen = set()
for _ in range(92):
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
FORM_RENDER_PATCHED = False

def _print_billing_data_form_windows_v4491(printer_name: str='') -> str:
    if _os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    doc.DocumentName = 'Datos para factura'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Formulario factura 80 mm', 315, 485)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {'img': None}

    def font(size: float, bold: bool=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.0, True)
    f_intro = font(7.2, False)
    f_label = font(7.5, True)
    f_footer = font(7.0, True)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width):
        g.DrawLine(pen, 0.0, float(y), float(width), float(y))

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if _os.path.exists(logo_path):
            try:
                image_holder['img'] = Image.FromFile(logo_path)
                g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder['img'] = None
        title_x = 42.0 if image_holder['img'] is not None else 0.0
        title_w = width - title_x
        g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
        y = 43.0
        draw_line(g, y, width)
        y += 10.0
        g.DrawString('DATOS PARA FACTURA', f_title, Brushes.Black, RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        g.DrawString('Complete los datos de la persona o empresa\na quien desea facturar.', f_intro, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        y += 34.0
        draw_line(g, y, width)

        def field(label: str, spaces: int=1):
            nonlocal y
            y += 11.0
            g.DrawString(label, f_label, Brushes.Black, 0.0, y)
            y += 32.0
            if spaces > 1:
                y += 24.0 * (spaces - 1)
        field('CÉDULA / RUC:')
        field('NOMBRE / RAZÓN SOCIAL:')
        field('DIRECCIÓN:', 2)
        field('TELÉFONO:')
        field('CORREO (OPCIONAL):')
        y += 6.0
        g.DrawString('ENTREGAR EN RECEPCIÓN', f_footer, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_print_page
        except Exception:
            pass
        if image_holder.get('img') is not None:
            try:
                image_holder['img'].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen
try:
    _rf_alias_app_patch_4491__previous._print_billing_data_form_windows_v4490 = _print_billing_data_form_windows_v4491
    _rf_alias_app_patch_4491__previous.previous._print_billing_data_form_windows = _print_billing_data_form_windows_v4491
    FORM_RENDER_PATCHED = True
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.91';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.91';", _js)
    V4491_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.91"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4491_JS = "\n;(()=>{\n  if(window.__v4491BillingDataFormNoLines)return;\n  window.__v4491BillingDataFormNoLines=true;\n  const VERSION='4.4.91';\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4491_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4491_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4491/health')
def v4491_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'form_render_patched': FORM_RENDER_PATCHED, 'writing_lines_removed': True, 'address_extra_space': True, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4491 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4491, '__name__', 'app_patch_4491')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4491, 'APP_VERSION', globals()['APP_VERSION'])
if 'FORM_RENDER_PATCHED' in globals(): setattr(_rf_snapshot_app_patch_4491, 'FORM_RENDER_PATCHED', globals()['FORM_RENDER_PATCHED'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4491, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4491, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4491_CSS' in globals(): setattr(_rf_snapshot_app_patch_4491, 'V4491_CSS', globals()['V4491_CSS'])
if 'V4491_JS' in globals(): setattr(_rf_snapshot_app_patch_4491, 'V4491_JS', globals()['V4491_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4491, '_', globals()['_'])
if '_js' in globals(): setattr(_rf_snapshot_app_patch_4491, '_js', globals()['_js'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4491, '_mod', globals()['_mod'])
if '_os' in globals(): setattr(_rf_snapshot_app_patch_4491, '_os', globals()['_os'])
if '_print_billing_data_form_windows_v4491' in globals(): setattr(_rf_snapshot_app_patch_4491, '_print_billing_data_form_windows_v4491', globals()['_print_billing_data_form_windows_v4491'])
if '_re' in globals(): setattr(_rf_snapshot_app_patch_4491, '_re', globals()['_re'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4491, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4491, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4491, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4491, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4491, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4491__previous' in globals(): setattr(_rf_snapshot_app_patch_4491, 'previous', globals()['_rf_alias_app_patch_4491__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4491, 'uvicorn', globals()['uvicorn'])
if 'v4491_health' in globals(): setattr(_rf_snapshot_app_patch_4491, 'v4491_health', globals()['v4491_health'])
_rf_layers['app_patch_4491'] = _rf_snapshot_app_patch_4491

# ---- app_patch_4501 ----
import json
import os
import shutil
import sys
import time
from pathlib import Path
_rf_alias_app_patch_4501__previous = _rf_layers['app_patch_4491']
core = _rf_alias_app_patch_4501__previous.core
app = _rf_alias_app_patch_4501__previous.app
APP_VERSION = '4.5.1'
_mod = _rf_alias_app_patch_4501__previous
_seen = set()
for _ in range(96):
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
REMOVED_REDUNDANT_JS_BLOCKS = 0
REMOVED_REDUNDANT_TIMEOUTS = 0

def _strip_redundant_version_overlays():
    """Quita solo capas que repintaban versión/actualizador.

    No toca el JS funcional del formulario v4.4.89 ni facturación, agenda,
    atenciones, WhatsApp, pacientes o impresión.
    """
    global REMOVED_REDUNDANT_JS_BLOCKS, REMOVED_REDUNDANT_TIMEOUTS
    js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    targets = [('app_patch_4482', 'V4482_JS'), ('app_patch_4483', 'V4483_JS'), ('app_patch_4487', 'V4487_JS'), ('app_patch_4488', 'V4488_JS'), ('app_patch_4490', 'V4490_JS'), ('app_patch_4491', 'V4491_JS')]
    blocks = 0
    timers = 0
    for module_name, attr in targets:
        mod = _rf_module_lookup(module_name)
        block = getattr(mod, attr, '') if mod is not None else ''
        if block and block in js:
            timers += block.count('setTimeout(')
            js = js.replace(block, '')
            blocks += 1
    core.V460_OVERLAY_JS = js
    REMOVED_REDUNDANT_JS_BLOCKS = blocks
    REMOVED_REDUNDANT_TIMEOUTS = timers

def _safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0

def _local_db_status() -> dict:
    db_path = Path(str(getattr(core, 'OFFLINE_DB_PATH', Path(str(core.DATA_DIR)) / 'offline_cache.db')))
    ok = False
    error = ''
    try:
        with core.LocalSessionLocal() as db:
            db.execute(core.text('SELECT 1'))
        ok = True
    except Exception as exc:
        error = str(exc)[:220]
    pending = None
    try:
        pending = int(core.queue_count())
    except Exception:
        pass
    return {'ok': ok, 'name': db_path.name, 'exists': db_path.exists(), 'size_bytes': _safe_size(db_path), 'pending_sync': pending, 'error': error}

def _neon_status(deep: bool=False) -> dict:
    if deep:
        try:
            return core._probe_neon_service()
        except Exception as exc:
            return {'status': 'ERROR', 'detail': str(exc)[:220]}
    try:
        if not core.cloud_configured():
            return {'status': 'NO CONFIGURADO', 'detail': 'DATABASE_URL no está configurado en esta PC.'}
    except Exception:
        return {'status': 'SIN COMPROBAR', 'detail': 'No se pudo leer la configuración de Neon.'}
    try:
        lock = getattr(core, '_state_lock', None)
        state = getattr(core, '_state', {}) or {}
        if lock is not None:
            with lock:
                state = dict(state)
        else:
            state = dict(state)
        online = state.get('online')
        err = str(state.get('last_error') or '')[:180]
        if online is True:
            return {'status': 'ONLINE', 'detail': 'Último estado conocido: conectado.'}
        if online is False:
            return {'status': 'OFFLINE', 'detail': err or 'Último estado conocido: sin conexión.'}
    except Exception:
        pass
    return {'status': 'SIN COMPROBAR', 'detail': 'Pulsa Revisar sistema para comprobar Neon.'}

def _printer_status() -> dict:
    info = core._windows_printer_info()
    prefs = core._app_preferences()
    selected = str(prefs.get('printer') or info.get('default_printer') or '').strip()
    printers = list(info.get('printers') or [])
    queue_state = {}
    qmod = _rf_module_lookup('app_patch_4474')
    try:
        lock = getattr(qmod, '_PRINT_LOCK', None)
        raw = getattr(qmod, '_PRINT_STATE', {}) or {}
        if lock is not None:
            with lock:
                queue_state = dict(raw)
        else:
            queue_state = dict(raw)
        q = getattr(qmod, '_PRINT_QUEUE', None)
        t = getattr(qmod, '_PRINT_THREAD', None)
        queue_state['queue_depth'] = int(q.qsize()) if q is not None else 0
        queue_state['worker_alive'] = bool(t and t.is_alive())
    except Exception:
        queue_state = {}
    return {'ok': bool(info.get('supported') and selected and (not printers or selected in printers)), 'selected': selected, 'default': str(info.get('default_printer') or ''), 'available_count': len(printers), 'error': str(info.get('error') or '')[:220], 'queue': queue_state}

def _backup_status() -> dict:
    backup_dir = Path(str(getattr(core, 'BACKUP_DIR', Path(str(core.DATA_DIR)) / 'backups')))
    try:
        files = sorted(backup_dir.glob('recepcion_backup_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        files = []
    latest = files[0] if files else None
    value = ''
    try:
        with core.LocalSessionLocal() as db:
            row = db.get(core.CacheMeta, 'last_backup')
            value = str(getattr(row, 'value', '') or '')
    except Exception:
        pass
    if not value and latest:
        try:
            value = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(latest.stat().st_mtime))
        except Exception:
            pass
    return {'ok': bool(value or latest), 'last_backup': value, 'count': len(files), 'latest_size_bytes': _safe_size(latest) if latest else 0}

def _update_status(deep: bool=False) -> dict:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    local = {}
    state = {}
    try:
        local = json.loads((root / 'update_manifest.json').read_text(encoding='utf-8-sig'))
    except Exception:
        pass
    try:
        state_path = data / 'auto_update_state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8-sig'))
    except Exception:
        pass
    out = {'ok': True, 'local': str(local.get('version') or APP_VERSION), 'launcher_version': str(local.get('launcher_version') or ''), 'last_check_ok': state.get('last_check_ok'), 'last_error': str(state.get('last_error') or '')[:220], 'last_installed_version': str(state.get('last_installed_version') or ''), 'startup_rollback': bool(state.get('startup_rollback'))}
    if deep:
        try:
            live = core._read_update_channel_status()
            out.update({'latest': live.get('latest'), 'update_available': bool(live.get('update_available')), 'latency_ms': live.get('latency_ms')})
        except Exception as exc:
            out['ok'] = False
            out['error'] = str(exc)[:220]
    return out

def _old_temp_candidates() -> list[Path]:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    now = time.time()
    out = []
    staging = data / 'update_staging'
    if staging.exists():
        try:
            for item in staging.iterdir():
                try:
                    if now - item.stat().st_mtime >= 24 * 60 * 60:
                        out.append(item)
                except Exception:
                    pass
        except Exception:
            pass
    for pattern in ('*.tmp', '*.rollback_tmp', '*.startup_rollback_tmp', '*.new_*'):
        try:
            for item in root.glob(pattern):
                try:
                    if now - item.stat().st_mtime >= 60 * 60:
                        out.append(item)
                except Exception:
                    pass
        except Exception:
            pass
    return out

def _trim_log(path: Path, keep_bytes: int=384 * 1024) -> int:
    try:
        if not path.is_file() or path.stat().st_size <= keep_bytes * 2:
            return 0
        raw = path.read_bytes()
        path.write_bytes(raw[-keep_bytes:])
        return max(0, len(raw) - keep_bytes)
    except Exception:
        return 0

def _safe_housekeeping() -> dict:
    data = Path(str(core.DATA_DIR))
    removed_files = 0
    removed_dirs = 0
    freed = 0
    for path in _old_temp_candidates():
        try:
            if path.is_file():
                freed += _safe_size(path)
                path.unlink()
                removed_files += 1
            elif path.is_dir():
                size = 0
                for item in path.rglob('*'):
                    if item.is_file():
                        size += _safe_size(item)
                shutil.rmtree(path, ignore_errors=False)
                freed += size
                removed_dirs += 1
        except Exception:
            pass
    for log_name in ('backend_startup.log', 'launcher_errors.log'):
        freed += _trim_log(data / log_name)
    try:
        bdir = Path(str(getattr(core, 'BACKUP_DIR', data / 'backups')))
        backups = sorted(bdir.glob('recepcion_backup_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[10:]:
            try:
                freed += _safe_size(old)
                old.unlink()
                removed_files += 1
            except Exception:
                pass
    except Exception:
        pass
    return {'ok': True, 'removed_files': removed_files, 'removed_dirs': removed_dirs, 'freed_bytes': int(freed), 'protected_data_untouched': True}

def _print_test_ticket(printer_name: str='') -> str:
    if os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    doc.DocumentName = 'Prueba impresora Recepción'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Prueba 80 mm', 315, 255)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    logo = {'img': None}

    def font(size, bold=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_head = font(9.4, True)
    f_sub = font(7.0)
    f_ok = font(12.0, True)
    f_body = font(7.2)
    f_small = font(6.3)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near
    stamp = time.strftime('%d/%m/%Y %H:%M')

    def on_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        logo_path = os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if os.path.exists(logo_path):
            try:
                logo['img'] = Image.FromFile(logo_path)
                g.DrawImage(logo['img'], 0.0, 1.0, 34.0, 34.0)
            except Exception:
                logo['img'] = None
        x = 39.0 if logo['img'] is not None else 0.0
        g.DrawString('DR. ARMANDO REVELO', f_head, Brushes.Black, RectangleF(x, 2.0, width - x, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_sub, Brushes.Black, RectangleF(x, 18.0, width - x, 13.0), center)
        y = 42.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 12.0
        g.DrawString('IMPRESORA OK', f_ok, Brushes.Black, RectangleF(0.0, y, width, 22.0), center)
        y += 29.0
        g.DrawString(f'Recepción v{APP_VERSION}', f_body, Brushes.Black, RectangleF(0.0, y, width, 15.0), center)
        y += 18.0
        g.DrawString(stamp, f_body, Brushes.Black, RectangleF(0.0, y, width, 15.0), center)
        y += 22.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 8.0
        g.DrawString('80 mm · margen y corte', f_small, Brushes.Black, RectangleF(0.0, y, width, 14.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_page
        except Exception:
            pass
        if logo.get('img') is not None:
            try:
                logo['img'].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen

@app.get('/api/v4501/system-status')
def v4501_system_status(deep: bool=False, user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'optimization': {'stable_runtime_chain': True, 'experimental_runtime_consolidation': False, 'redundant_js_blocks_removed': REMOVED_REDUNDANT_JS_BLOCKS, 'redundant_timeouts_removed': REMOVED_REDUNDANT_TIMEOUTS, 'new_mutation_observers': 0, 'persistent_timers_added': 0}, 'local': _local_db_status(), 'neon': _neon_status(bool(deep)), 'printer': _printer_status(), 'updater': _update_status(bool(deep)), 'backup': _backup_status(), 'cleanup': {'candidates': len(_old_temp_candidates())}}

@app.post('/api/v4501/maintenance/cleanup')
def v4501_cleanup(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'La limpieza solo se ejecuta desde la PC de Recepción')
    return _safe_housekeeping()

@app.post('/api/v4501/printing/test')
def v4501_print_test(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta prueba solo se ejecuta desde la PC de Recepción')
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = _print_test_ticket(printer)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo imprimir la prueba: {exc}')
    return {'ok': True, 'printer': used, 'paper_width_mm': 80, 'version': APP_VERSION}
V4501_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.1"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n.v4486-print-menu>summary,.home-actions button,.attention-actions button{\n  min-height:32px;border-radius:8px!important;font-weight:750\n}\n.v4501-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}\n.v4501-card{border:1px solid #dfe6ef;border-radius:12px;padding:12px;background:#fbfcfe;min-height:100px}\n.v4501-card .top{display:flex;align-items:center;justify-content:space-between;gap:8px}\n.v4501-card b{font-size:14px;color:#263a55}\n.v4501-card small{display:block;margin-top:7px;color:#6f7f95;line-height:1.35}\n.v4501-pill{font-size:9px;font-weight:850;border-radius:999px;padding:4px 7px;background:#edf1f6;color:#66768b}\n.v4501-pill.ok{background:#e7f7ed;color:#176f3c}\n.v4501-pill.warn{background:#fff4db;color:#8a6118}\n.v4501-pill.err{background:#ffe9e8;color:#9d3933}\n.v4501-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}\n.v4501-actions button{min-height:34px;border-radius:9px;padding:7px 11px;font-weight:750}\n.v4501-note{padding:10px 12px;border-radius:10px;background:#f1f6fb;color:#5b6f86;font-size:12px;line-height:1.4}\n@media(max-width:1050px){.v4501-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n@media(max-width:720px){.v4501-grid{grid-template-columns:1fr}}\n'
V4501_JS = '\n;(()=>{\n  if(window.__v4501StableMaintenance)return;\n  window.__v4501StableMaintenance=true;\n  const VERSION=\'4.5.1\';\n  const q=(s,r=document)=>r.querySelector(s);\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n  const call=async(url,opt={})=>{\n    if(typeof window.api===\'function\')return window.api(url,opt);\n    const r=await fetch(url,{headers:{\'Content-Type\':\'application/json\',...(opt.headers||{})},...opt});\n    const d=await r.json().catch(()=>({}));\n    if(!r.ok)throw Error(d.detail||d.message||\'No se pudo completar la operación\');\n    return d;\n  };\n  const fmtBytes=n=>{\n    n=Number(n||0);\n    if(n<1024)return n+\' B\';\n    if(n<1048576)return (n/1024).toFixed(1)+\' KB\';\n    return (n/1048576).toFixed(1)+\' MB\';\n  };\n  const cls=v=>{\n    v=String(v||\'\').toUpperCase();\n    if(v===\'OK\'||v===\'ONLINE\'||v===\'IDLE\'||v===\'PRINTED\')return \'ok\';\n    if(v===\'ERROR\'||v===\'OFFLINE\')return \'err\';\n    return \'warn\';\n  };\n\n  function paint(){\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n    document.querySelectorAll(\'button[onclick*="restartReception"]\').forEach(btn=>{\n      btn.textContent=\'⬆ Instalar actualización\';\n      btn.title=\'Abre el actualizador seguro\';\n    });\n  }\n\n  async function launchUpdater(){\n    const status=q(\'#updateStatus\');\n    try{\n      if(status)status.textContent=\'Abriendo actualizador seguro…\';\n      const d=await call(\'/api/v4483/launch-updater\',{method:\'POST\',body:\'{}\'});\n      if(status)status.textContent=\'Actualizador abierto.\';\n      return d;\n    }catch(e){\n      if(status)status.textContent=e?.message||String(e);\n      alert(e?.message||String(e));\n      throw e;\n    }\n  }\n  window.restartReception=launchUpdater;\n\n  function card(label,state,detail){\n    return \'<div class="v4501-card"><div class="top"><b>\'+esc(label)+\'</b><span class="v4501-pill \'+cls(state)+\'">\'+esc(state||\'—\')+\'</span></div><small>\'+esc(detail||\'\')+\'</small></div>\';\n  }\n\n  function render(d){\n    const host=q(\'#v4501Grid\');\n    if(!host)return;\n    const l=d.local||{},n=d.neon||{},p=d.printer||{},u=d.updater||{},b=d.backup||{},o=d.optimization||{},queue=p.queue||{};\n    host.innerHTML=[\n      card(\'Base local\',l.ok?\'OK\':\'ERROR\',(l.name||\'SQLite\')+\' · \'+fmtBytes(l.size_bytes)+(l.pending_sync!=null?\' · \'+l.pending_sync+\' pendiente(s)\':\'\')),\n      card(\'Neon\',n.status||\'SIN COMPROBAR\',n.detail||\'\'),\n      card(\'Impresora\',p.ok?\'OK\':\'REVISAR\',(p.selected||\'Sin impresora seleccionada\')+(queue.queue_depth!=null?\' · cola \'+queue.queue_depth:\'\')),\n      card(\'Actualizador\',u.ok!==false?\'OK\':\'REVISAR\',\'Local \'+(u.local||VERSION)+(u.latest?\' · Canal \'+u.latest:\'\')+(u.last_error?\' · \'+u.last_error:\'\')),\n      card(\'Respaldo\',b.ok?\'OK\':\'SIN COPIA\',b.last_backup?\'Último: \'+b.last_backup+\' · \'+(b.count||0)+\' copia(s)\':\'Todavía no hay respaldo local registrado.\'),\n      card(\'Optimización\',\'OK\',(o.redundant_js_blocks_removed||0)+\' overlays y \'+(o.redundant_timeouts_removed||0)+\' esperas redundantes retiradas\')\n    ].join(\'\');\n    const note=q(\'#v4501Note\');\n    if(note)note.textContent=\'Recepción v\'+VERSION+\'. La limpieza no toca pacientes, atenciones, agenda, .env, BASE DE DATOS 2026.xlsx ni las bases SQLite.\';\n  }\n\n  async function refresh(deep,btn){\n    if(btn){btn.disabled=true;btn.textContent=deep?\'Revisando…\':\'Actualizando…\'}\n    try{\n      render(await call(\'/api/v4501/system-status?deep=\'+(deep?\'true\':\'false\')));\n    }catch(e){\n      const note=q(\'#v4501Note\');\n      if(note)note.textContent=e?.message||String(e);\n    }finally{\n      if(btn){btn.disabled=false;btn.textContent=deep?\'↻ Revisar sistema\':\'Actualizar\'}\n    }\n  }\n\n  async function action(kind,btn){\n    if(btn)btn.disabled=true;\n    try{\n      if(kind===\'print\'){\n        await call(\'/api/v4501/printing/test\',{method:\'POST\',body:\'{}\'});\n        if(typeof window.rpNotice===\'function\')window.rpNotice(\'Prueba enviada a la impresora.\');\n      }else if(kind===\'backup\'){\n        await call(\'/api/backup/now\',{method:\'POST\',body:\'{}\'});\n        if(typeof window.rpNotice===\'function\')window.rpNotice(\'Respaldo creado correctamente.\');\n      }else if(kind===\'cleanup\'){\n        const d=await call(\'/api/v4501/maintenance/cleanup\',{method:\'POST\',body:\'{}\'});\n        const msg=\'Limpieza terminada: \'+(d.removed_files||0)+\' archivo(s), \'+(d.removed_dirs||0)+\' carpeta(s), \'+fmtBytes(d.freed_bytes||0)+\' liberados.\';\n        if(typeof window.rpNotice===\'function\')window.rpNotice(msg);else alert(msg);\n      }\n      await refresh(false,null);\n    }catch(e){\n      alert(e?.message||String(e));\n    }finally{\n      if(btn)btn.disabled=false;\n    }\n  }\n\n  function mount(){\n    paint();\n    const config=q(\'#config\'),tabs=q(\'.config-tabs\',config);\n    if(!config||!tabs)return;\n\n    let sec=q(\'[data-config-section="maintenance"]\',config);\n    if(!sec){\n      sec=document.createElement(\'div\');\n      sec.dataset.configSection=\'maintenance\';\n      sec.className=\'config-section hidden\';\n      sec.innerHTML=\'<div class="panel"><div class="config-panel-head"><div><h2>Mantenimiento</h2><p>Estado local, impresora, respaldo y limpieza segura del programa.</p></div></div><div id="v4501Grid" class="v4501-grid"></div><div class="v4501-actions"><button type="button" class="primary" data-v4501="review">↻ Revisar sistema</button><button type="button" data-v4501="print">🖨 Imprimir prueba</button><button type="button" data-v4501="backup">Crear respaldo</button><button type="button" data-v4501="cleanup">Limpiar temporales</button></div><div id="v4501Note" class="v4501-note">Cargando estado local…</div></div>\';\n      config.appendChild(sec);\n      q(\'[data-v4501="review"]\',sec)?.addEventListener(\'click\',function(){refresh(true,this)});\n      q(\'[data-v4501="print"]\',sec)?.addEventListener(\'click\',function(){action(\'print\',this)});\n      q(\'[data-v4501="backup"]\',sec)?.addEventListener(\'click\',function(){action(\'backup\',this)});\n      q(\'[data-v4501="cleanup"]\',sec)?.addEventListener(\'click\',function(){action(\'cleanup\',this)});\n    }\n\n    let btn=q(\'[data-config-tab="maintenance"]\',tabs);\n    if(!btn){\n      btn=document.createElement(\'button\');\n      btn.type=\'button\';\n      btn.dataset.configTab=\'maintenance\';\n      btn.textContent=\'Mantenimiento\';\n      tabs.appendChild(btn);\n      btn.addEventListener(\'click\',()=>{\n        if(typeof window.showConfigTab===\'function\')window.showConfigTab(\'maintenance\',btn);\n        refresh(false,null);\n      });\n    }\n  }\n\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',mount,{once:true});\n  else mount();\n  setTimeout(mount,500);\n})();\n'
try:
    _strip_redundant_version_overlays()
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4501_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4501_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4501/health')
def v4501_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'stable_runtime_chain': True, 'experimental_runtime_consolidation': False, 'redundant_js_blocks_removed': REMOVED_REDUNDANT_JS_BLOCKS, 'redundant_timeouts_removed': REMOVED_REDUNDANT_TIMEOUTS, 'new_mutation_observers': 0, 'persistent_timers_added': 0, 'maintenance_tab': True, 'printer_test': True, 'safe_cleanup': True, 'database_changes': False, 'neon_writes_added': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4501 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4501, '__name__', 'app_patch_4501')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4501, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4501, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4501, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'Path' in globals(): setattr(_rf_snapshot_app_patch_4501, 'Path', globals()['Path'])
if 'REMOVED_REDUNDANT_JS_BLOCKS' in globals(): setattr(_rf_snapshot_app_patch_4501, 'REMOVED_REDUNDANT_JS_BLOCKS', globals()['REMOVED_REDUNDANT_JS_BLOCKS'])
if 'REMOVED_REDUNDANT_TIMEOUTS' in globals(): setattr(_rf_snapshot_app_patch_4501, 'REMOVED_REDUNDANT_TIMEOUTS', globals()['REMOVED_REDUNDANT_TIMEOUTS'])
if 'V4501_CSS' in globals(): setattr(_rf_snapshot_app_patch_4501, 'V4501_CSS', globals()['V4501_CSS'])
if 'V4501_JS' in globals(): setattr(_rf_snapshot_app_patch_4501, 'V4501_JS', globals()['V4501_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4501, '_', globals()['_'])
if '_backup_status' in globals(): setattr(_rf_snapshot_app_patch_4501, '_backup_status', globals()['_backup_status'])
if '_local_db_status' in globals(): setattr(_rf_snapshot_app_patch_4501, '_local_db_status', globals()['_local_db_status'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4501, '_mod', globals()['_mod'])
if '_neon_status' in globals(): setattr(_rf_snapshot_app_patch_4501, '_neon_status', globals()['_neon_status'])
if '_old_temp_candidates' in globals(): setattr(_rf_snapshot_app_patch_4501, '_old_temp_candidates', globals()['_old_temp_candidates'])
if '_print_test_ticket' in globals(): setattr(_rf_snapshot_app_patch_4501, '_print_test_ticket', globals()['_print_test_ticket'])
if '_printer_status' in globals(): setattr(_rf_snapshot_app_patch_4501, '_printer_status', globals()['_printer_status'])
if '_safe_housekeeping' in globals(): setattr(_rf_snapshot_app_patch_4501, '_safe_housekeeping', globals()['_safe_housekeeping'])
if '_safe_size' in globals(): setattr(_rf_snapshot_app_patch_4501, '_safe_size', globals()['_safe_size'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4501, '_seen', globals()['_seen'])
if '_strip_redundant_version_overlays' in globals(): setattr(_rf_snapshot_app_patch_4501, '_strip_redundant_version_overlays', globals()['_strip_redundant_version_overlays'])
if '_trim_log' in globals(): setattr(_rf_snapshot_app_patch_4501, '_trim_log', globals()['_trim_log'])
if '_update_status' in globals(): setattr(_rf_snapshot_app_patch_4501, '_update_status', globals()['_update_status'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4501, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4501, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4501, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4501, 'exc', globals()['exc'])
if 'json' in globals(): setattr(_rf_snapshot_app_patch_4501, 'json', globals()['json'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4501, 'os', globals()['os'])
if '_rf_alias_app_patch_4501__previous' in globals(): setattr(_rf_snapshot_app_patch_4501, 'previous', globals()['_rf_alias_app_patch_4501__previous'])
if 'shutil' in globals(): setattr(_rf_snapshot_app_patch_4501, 'shutil', globals()['shutil'])
if 'sys' in globals(): setattr(_rf_snapshot_app_patch_4501, 'sys', globals()['sys'])
if 'time' in globals(): setattr(_rf_snapshot_app_patch_4501, 'time', globals()['time'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4501, 'uvicorn', globals()['uvicorn'])
if 'v4501_cleanup' in globals(): setattr(_rf_snapshot_app_patch_4501, 'v4501_cleanup', globals()['v4501_cleanup'])
if 'v4501_health' in globals(): setattr(_rf_snapshot_app_patch_4501, 'v4501_health', globals()['v4501_health'])
if 'v4501_print_test' in globals(): setattr(_rf_snapshot_app_patch_4501, 'v4501_print_test', globals()['v4501_print_test'])
if 'v4501_system_status' in globals(): setattr(_rf_snapshot_app_patch_4501, 'v4501_system_status', globals()['v4501_system_status'])
_rf_layers['app_patch_4501'] = _rf_snapshot_app_patch_4501

# ---- app_patch_4502 ----
_rf_alias_app_patch_4502__previous = _rf_layers['app_patch_4501']
core = _rf_alias_app_patch_4502__previous.core
app = _rf_alias_app_patch_4502__previous.app
APP_VERSION = '4.5.2'
_mod = _rf_alias_app_patch_4502__previous
_seen = set()
for _ in range(110):
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
BATCH_ROUTE_REPLACED = False
CONSULT_BASE = 40.0
COUPLE_DISCOUNT = 10.0
CONSULT_COUPLE_TOTAL = 30.0
PAYMENT_SENTINELS = {'EFECTIVO': -442901, 'TRANSFERENCIA': -442920}
SRI_PAYMENT_CODES = {'EFECTIVO': '01', 'TRANSFERENCIA': '20'}

def _normalize_payment_method(value: object) -> str:
    raw = ' '.join(str(value or '').strip().upper().split())
    raw = {'TRANSFERENCIA BANCARIA': 'TRANSFERENCIA', 'BANCO': 'TRANSFERENCIA', 'CASH': 'EFECTIVO'}.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise core.HTTPException(400, 'Selecciona la forma de pago: Efectivo o Transferencia bancaria.')
    return raw

def _remove_api_route(path: str, method: str) -> int:
    wanted = str(method or '').upper()
    removed = 0
    kept = []
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in getattr(route, 'methods', None) or set()}
        if getattr(route, 'path', None) == path and wanted in methods:
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
    marker = 'DESCUENTO PAREJA · BASE $40.00 · DESCUENTO $10.00 · TOTAL $30.00'
    old = ' '.join(str(original or '').split())
    return f'{old} | {marker}' if old else marker
try:

    class V4502VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str
        couple_discount: bool = False
    _REMOVED_BATCH_PAYMENT_ROUTES = _remove_api_route('/api/visits/batch-payment', 'POST')
    BATCH_ROUTE_REPLACED = _REMOVED_BATCH_PAYMENT_ROUTES > 0

    @app.post('/api/visits/batch-payment')
    def v4502_create_visit_batch_payment(data: V4502VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        method = _normalize_payment_method(data.payment_method)
        sentinel = PAYMENT_SENTINELS[method]
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        if not data.services:
            raise core.HTTPException(400, 'Selecciona al menos una atención')
        if len(data.services) > 20:
            raise core.HTTPException(400, 'Hay demasiadas acciones seleccionadas')
        override = (data.tipo or '').strip().upper()
        if override and override not in {'N', 'S'}:
            raise core.HTTPException(400, 'Estado de paciente inválido')
        prior = db.scalar(core.select(core.func.count(core.Visit.id)).where(core.Visit.patient_id == int(patient.id))) or 0
        historical_prior = bool(not prior and core.historical_summary_for_patient(patient))
        first_type = override or ('S' if prior or historical_prior else 'N')
        normalized = []
        seen = set()
        has_consultation = False
        for item in data.services:
            procedimiento = (item.procedimiento or '').strip().upper() or None
            key = procedimiento or 'CONSULTA'
            if key in seen:
                continue
            seen.add(key)
            if procedimiento is None:
                has_consultation = True
                valor = CONSULT_COUPLE_TOTAL if bool(data.couple_discount) else CONSULT_BASE
            else:
                valor = item.valor
            if valor is None:
                raise core.HTTPException(400, f'Ingresa el valor de {key}')
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                raise core.HTTPException(400, f'El valor de {key} no es válido')
            if valor < 0:
                raise core.HTTPException(400, f'El valor de {key} no es válido')
            normalized.append((procedimiento, valor))
        if not normalized:
            raise core.HTTPException(400, 'Selecciona al menos una atención')
        discount_applied = bool(data.couple_discount and has_consultation)
        offline = core.is_offline_db(db)
        existing_payment_visits = list(db.scalars(core.select(core.Visit).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == int(data.patient_id), core.Visit.fecha == data.fecha, core.BillingRecord.estado != 'EMITIDA').order_by(core.Visit.id)))
        for old_visit in existing_payment_visits:
            old_visit.source_row = sentinel
        created = []
        specs = []
        for index, (procedimiento, valor) in enumerate(normalized):
            tipo = first_type if index == 0 else 'S'
            visit_observation = data.observacion
            if procedimiento is None and discount_applied:
                visit_observation = _discount_observation(data.observacion)
            visit = core.Visit(patient_id=int(data.patient_id), fecha=data.fecha, tipo=tipo, procedimiento=procedimiento, valor=valor, observacion=visit_observation, source_row=sentinel)
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedimiento, valor, visit_observation))
        db.flush()
        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado='PENDIENTE')
            db.add(billing)
            billings.append(billing)
        for visit, tipo, procedimiento, valor, visit_observation in specs:
            service_name = procedimiento or 'CONSULTA'
            if offline:
                payload = {'patient_id': int(data.patient_id), 'fecha': data.fecha.isoformat(), 'tipo': tipo, 'procedimiento': procedimiento, 'valor': valor, 'observacion': visit_observation, 'source_row': sentinel}
                core.add_queue(db, 'visit.create', 'visit', payload, user.username, int(visit.id))
                core.audit(db, user, 'crear_atencion_multiple_offline', f'Atención local {visit.id}, paciente {patient.id}, {service_name}')
            else:
                core.audit(db, user, 'crear_atencion_multiple', f'Atención {visit.id}, paciente {patient.id}, estado {tipo}, servicio {service_name}')
            if procedimiento is None and discount_applied:
                core.audit(db, user, 'aplicar_descuento_pareja', f'Atención {visit.id}, paciente {patient.id}: consulta base $40.00, descuento $10.00, total $30.00')
        core.audit(db, user, 'registrar_forma_pago_atencion', f'Paciente {int(data.patient_id)}, {data.fecha}: {method}')
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
            pending_summary_local = {'billing': billing_actions['total'], 'billing_pending': billing_actions['pending'], 'billing_approved': billing_actions['approved'], 'agenda': int(summary_db.scalar(core.select(core.func.count(core.Appointment.id)).where(core.Appointment.estado == 'PENDIENTE')) or 0)}
        return {'ok': True, 'count': len(created), 'items': [core.v_dict(v) for v in created], 'offline': offline, 'pending': pending_summary_local, 'payment_method': method, 'sri_payment_code': SRI_PAYMENT_CODES[method], 'single_commit': True, 'couple_discount': discount_applied, 'consultation_base': CONSULT_BASE if has_consultation else None, 'discount_amount': COUPLE_DISCOUNT if discount_applied else 0.0, 'consultation_total': CONSULT_COUPLE_TOTAL if discount_applied and has_consultation else CONSULT_BASE if has_consultation else None}
    V4502_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.2"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n.v4502-couple-discount{\n  margin:9px 0 0;padding:10px 12px;border:1px solid #d9e4ee;border-radius:11px;\n  background:#fff;display:flex;align-items:center;justify-content:space-between;gap:12px;\n  transition:border-color .12s ease,background .12s ease,box-shadow .12s ease\n}\n.v4502-couple-discount.hidden{display:none!important}\n.v4502-couple-discount.active{\n  border-color:#69ad84;background:#edf9f2;box-shadow:0 0 0 2px rgba(72,151,103,.08)\n}\n.v4502-discount-copy{display:grid;gap:2px;min-width:0}\n.v4502-discount-copy b{font-size:10.5px;color:#29455f}\n.v4502-discount-copy small{font-size:8.5px;color:#728597;line-height:1.25}\n.v4502-couple-discount.active .v4502-discount-copy b{color:#276344}\n.v4502-discount-control{display:flex;align-items:center;gap:9px;white-space:nowrap;cursor:pointer;user-select:none}\n.v4502-discount-control input{width:19px!important;height:19px!important;accent-color:#438f62;cursor:pointer}\n.v4502-discount-price{display:grid;text-align:right;line-height:1.05}\n.v4502-discount-price del{font-size:8px;color:#8997a6}\n.v4502-discount-price strong{font-size:13px;color:#286846}\n.v4502-couple-discount:not(.active) .v4502-discount-price strong{color:#536b80}\n.v4502-discount-badge{\n  display:inline-flex;margin-top:3px;padding:2px 6px;border-radius:999px;\n  background:#dff2e7;color:#286a48;font-size:7.5px;font-weight:900;justify-self:end\n}\n.v4502-discounted .service-price{color:#26704a!important;font-weight:950!important}\n@media(max-width:650px){\n  .v4502-couple-discount{align-items:flex-start;flex-direction:column}\n  .v4502-discount-control{width:100%;justify-content:space-between}\n}\n'
    V4502_JS = '\n;(()=>{\n  if(window.__v4502CoupleDiscount)return;\n  window.__v4502CoupleDiscount=true;\n\n  const VERSION=\'4.5.2\';\n  let coupleDiscount=false;\n\n  const norm=v=>String(v||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\n\n  function modal(){\n    return document.querySelector(\'.attention-form-modal\')\n      ||[...document.querySelectorAll(\'#modal .modalbox,.modal .modalbox,.modalbox\')].find(\n        b=>[...b.querySelectorAll(\'h1,h2,h3\')].some(h=>norm(h.textContent)===\'nueva atencion\')\n      )\n      ||null;\n  }\n\n  function consultCard(box=modal()){\n    if(!box)return null;\n    return [...box.querySelectorAll(\'button.service-card[data-service]\')].find(\n      b=>norm(b.dataset.service)===\'consulta\'\n    )||box.querySelector(\'.consultation-card\')||null;\n  }\n\n  function consultationSelected(box=modal()){\n    const card=consultCard(box);\n    if(!card)return false;\n    const input=card.querySelector(\'input[type="checkbox"],input[type="radio"]\');\n    return !!(\n      card.classList.contains(\'selected\')\n      ||card.classList.contains(\'is-selected\')\n      ||card.getAttribute(\'aria-pressed\')===\'true\'\n      ||input?.checked\n    );\n  }\n\n  function setCardPrice(card,discounted){\n    if(!card)return;\n    card.classList.toggle(\'v4502-discounted\',!!discounted);\n    const price=card.querySelector(\'.service-price\');\n    if(price)price.textContent=discounted?\'$30.00\':\'$40.00\';\n  }\n\n  function render(){\n    const box=modal();\n    const card=consultCard(box);\n    if(!box||!card)return;\n\n    const selected=consultationSelected(box);\n    if(!selected)coupleDiscount=false;\n\n    let panel=box.querySelector(\'#v4502CoupleDiscount\');\n    if(!panel){\n      panel=document.createElement(\'div\');\n      panel.id=\'v4502CoupleDiscount\';\n      panel.className=\'v4502-couple-discount hidden\';\n      panel.innerHTML=\n        \'<div class="v4502-discount-copy">\'\n        +\'<b>Descuento pareja</b>\'\n        +\'<small>Úsalo solo para la consulta del segundo paciente de la pareja.</small>\'\n        +\'</div>\'\n        +\'<label class="v4502-discount-control">\'\n        +\'<input id="v4502CoupleDiscountCheck" type="checkbox">\'\n        +\'<span class="v4502-discount-price">\'\n        +\'<del>$40.00</del><strong>$30.00</strong>\'\n        +\'<span class="v4502-discount-badge">$10 menos</span>\'\n        +\'</span></label>\';\n      card.insertAdjacentElement(\'afterend\',panel);\n\n      panel.querySelector(\'#v4502CoupleDiscountCheck\')?.addEventListener(\'change\',e=>{\n        coupleDiscount=!!e.target.checked;\n        render();\n      });\n    }\n\n    panel.classList.toggle(\'hidden\',!selected);\n    panel.classList.toggle(\'active\',selected&&coupleDiscount);\n    const check=panel.querySelector(\'#v4502CoupleDiscountCheck\');\n    if(check)check.checked=!!(selected&&coupleDiscount);\n    setCardPrice(card,selected&&coupleDiscount);\n  }\n\n  function delayedRender(){\n    setTimeout(render,0);\n    setTimeout(render,90);\n    setTimeout(render,230);\n    setTimeout(render,380);\n  }\n\n  const stableAttentionFor=window.attentionFor;\n  if(typeof stableAttentionFor===\'function\'){\n    window.attentionFor=async function(id,draft=null){\n      coupleDiscount=!!draft?.coupleDiscount;\n      const out=await stableAttentionFor.apply(this,arguments);\n      delayedRender();\n      return out;\n    };\n  }\n\n  const stableSaveAttention=window.saveAttention;\n  if(typeof stableSaveAttention===\'function\'){\n    window.saveAttention=async function(id){\n      const applyDiscount=!!(coupleDiscount&&consultationSelected());\n      const stableApi=window.api||api;\n\n      const intercept=async function(url,opt={}){\n        if(String(url)===\'/api/visits/batch-payment\'){\n          let body={};\n          try{body=JSON.parse(opt?.body||\'{}\')}catch(_e){body={}}\n          body.couple_discount=applyDiscount;\n          return stableApi(url,{...opt,body:JSON.stringify(body)});\n        }\n        return stableApi(url,opt);\n      };\n\n      const previousApi=api;\n      try{\n        api=intercept;\n        return await stableSaveAttention.apply(this,arguments);\n      }finally{\n        api=previousApi;\n      }\n    };\n  }\n\n  document.addEventListener(\'click\',e=>{\n    const card=e.target?.closest?.(\'button.service-card[data-service]\');\n    if(card&&norm(card.dataset.service)===\'consulta\'){\n      setTimeout(render,20);\n      setTimeout(render,220);\n      setTimeout(render,380);\n    }\n  },true);\n\n  document.addEventListener(\'change\',e=>{\n    if(e.target?.closest?.(\'.attention-form-modal\')){\n      setTimeout(render,20);\n      setTimeout(render,220);\n    }\n  },true);\n\n  document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n    el.textContent=\'v\'+VERSION;\n    el.setAttribute(\'data-version\',\'v\'+VERSION);\n  });\n\n  window.__v4502CoupleDiscountTest={\n    render,\n    selected:()=>consultationSelected(),\n    enabled:()=>coupleDiscount\n  };\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4502_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4502_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4502/health')
def v4502_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'batch_route_replaced': BATCH_ROUTE_REPLACED, 'couple_discount': True, 'consultation_base': CONSULT_BASE, 'discount_amount': COUPLE_DISCOUNT, 'consultation_total': CONSULT_COUPLE_TOTAL, 'consultation_only': True, 'default_enabled': False, 'audit_trace': True, 'report_trace_via_observation': True, 'database_schema_changes': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4502 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4502, '__name__', 'app_patch_4502')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4502, 'APP_VERSION', globals()['APP_VERSION'])
if 'BATCH_ROUTE_REPLACED' in globals(): setattr(_rf_snapshot_app_patch_4502, 'BATCH_ROUTE_REPLACED', globals()['BATCH_ROUTE_REPLACED'])
if 'CONSULT_BASE' in globals(): setattr(_rf_snapshot_app_patch_4502, 'CONSULT_BASE', globals()['CONSULT_BASE'])
if 'CONSULT_COUPLE_TOTAL' in globals(): setattr(_rf_snapshot_app_patch_4502, 'CONSULT_COUPLE_TOTAL', globals()['CONSULT_COUPLE_TOTAL'])
if 'COUPLE_DISCOUNT' in globals(): setattr(_rf_snapshot_app_patch_4502, 'COUPLE_DISCOUNT', globals()['COUPLE_DISCOUNT'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4502, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4502, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PAYMENT_SENTINELS' in globals(): setattr(_rf_snapshot_app_patch_4502, 'PAYMENT_SENTINELS', globals()['PAYMENT_SENTINELS'])
if 'SRI_PAYMENT_CODES' in globals(): setattr(_rf_snapshot_app_patch_4502, 'SRI_PAYMENT_CODES', globals()['SRI_PAYMENT_CODES'])
if 'V4502VisitBatchPaymentIn' in globals(): setattr(_rf_snapshot_app_patch_4502, 'V4502VisitBatchPaymentIn', globals()['V4502VisitBatchPaymentIn'])
if 'V4502_CSS' in globals(): setattr(_rf_snapshot_app_patch_4502, 'V4502_CSS', globals()['V4502_CSS'])
if 'V4502_JS' in globals(): setattr(_rf_snapshot_app_patch_4502, 'V4502_JS', globals()['V4502_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4502, '_', globals()['_'])
if '_REMOVED_BATCH_PAYMENT_ROUTES' in globals(): setattr(_rf_snapshot_app_patch_4502, '_REMOVED_BATCH_PAYMENT_ROUTES', globals()['_REMOVED_BATCH_PAYMENT_ROUTES'])
if '_discount_observation' in globals(): setattr(_rf_snapshot_app_patch_4502, '_discount_observation', globals()['_discount_observation'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4502, '_mod', globals()['_mod'])
if '_normalize_payment_method' in globals(): setattr(_rf_snapshot_app_patch_4502, '_normalize_payment_method', globals()['_normalize_payment_method'])
if '_remove_api_route' in globals(): setattr(_rf_snapshot_app_patch_4502, '_remove_api_route', globals()['_remove_api_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4502, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4502, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4502, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4502, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4502, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4502__previous' in globals(): setattr(_rf_snapshot_app_patch_4502, 'previous', globals()['_rf_alias_app_patch_4502__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4502, 'uvicorn', globals()['uvicorn'])
if 'v4502_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_patch_4502, 'v4502_create_visit_batch_payment', globals()['v4502_create_visit_batch_payment'])
if 'v4502_health' in globals(): setattr(_rf_snapshot_app_patch_4502, 'v4502_health', globals()['v4502_health'])
_rf_layers['app_patch_4502'] = _rf_snapshot_app_patch_4502

# ---- app_patch_4504 ----
import base64
import json
import re
import sys
from datetime import date as _date
_rf_alias_app_patch_4504__previous = _rf_layers['app_patch_4502']
core = _rf_alias_app_patch_4504__previous.core
app = _rf_alias_app_patch_4504__previous.app
APP_VERSION = '4.5.4'
_mod = _rf_alias_app_patch_4504__previous
_seen = set()
for _ in range(120):
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
ROUTES_REPLACED = 0
PAYMENT_SENTINELS = {'EFECTIVO': -442901, 'TRANSFERENCIA': -442920, 'TARJETA_DEBITO': -442916, 'TARJETA_CREDITO': -442919, 'MIXTO': -442999}
SRI_CODES = {'EFECTIVO': '01', 'TRANSFERENCIA': '20', 'TARJETA_DEBITO': '16', 'TARJETA_CREDITO': '19'}
PAYMENT_LABELS = {'EFECTIVO': 'EFECTIVO', 'TRANSFERENCIA': 'TRANSFERENCIA BANCARIA', 'TARJETA_DEBITO': 'TARJETA DE DÉBITO', 'TARJETA_CREDITO': 'TARJETA DE CRÉDITO', 'MIXTO': 'PAGO MIXTO'}
CARD_METHODS = {'TARJETA_DEBITO', 'TARJETA_CREDITO'}
PAY_RE = re.compile('\\s*(?:\\|\\s*)?\\[\\[RP_PAY_V1:([A-Za-z0-9_-]+)\\]\\]')

def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0

def _normalize_method(value: object, allow_mixed: bool=True) -> str:
    raw = ' '.join(str(value or '').strip().upper().split())
    aliases = {'TRANSFERENCIA BANCARIA': 'TRANSFERENCIA', 'BANCO': 'TRANSFERENCIA', 'CASH': 'EFECTIVO', 'DEBITO': 'TARJETA_DEBITO', 'DÉBITO': 'TARJETA_DEBITO', 'TARJETA DE DEBITO': 'TARJETA_DEBITO', 'TARJETA DE DÉBITO': 'TARJETA_DEBITO', 'CREDITO': 'TARJETA_CREDITO', 'CRÉDITO': 'TARJETA_CREDITO', 'TARJETA DE CREDITO': 'TARJETA_CREDITO', 'TARJETA DE CRÉDITO': 'TARJETA_CREDITO', 'PAGO MIXTO': 'MIXTO'}
    raw = aliases.get(raw, raw)
    valid = set(PAYMENT_SENTINELS)
    if not allow_mixed:
        valid.discard('MIXTO')
    if raw == 'TARJETA':
        raise core.HTTPException(400, 'Selecciona si la tarjeta es Débito o Crédito.')
    if raw not in valid:
        raise core.HTTPException(400, 'Selecciona Efectivo, Transferencia, Tarjeta o Pago mixto.')
    return raw

def _clean_voucher(value: object) -> str:
    raw = ' '.join(str(value or '').strip().split())
    if len(raw) > 40:
        raise core.HTTPException(400, 'El voucher/autorización es demasiado largo.')
    return raw

def _card_details(method: str, plan=None, installments=None, voucher=None) -> dict:
    if method not in CARD_METHODS:
        return {}
    out = {'voucher': _clean_voucher(voucher)}
    if method == 'TARJETA_DEBITO':
        out['plan'] = None
        out['installments'] = None
        return out
    raw_plan = ' '.join(str(plan or 'CORRIENTE').strip().upper().split())
    raw_plan = {'DIFERIDA': 'DIFERIDO', 'CUOTAS': 'DIFERIDO'}.get(raw_plan, raw_plan)
    if raw_plan not in {'CORRIENTE', 'DIFERIDO'}:
        raise core.HTTPException(400, 'Selecciona Corriente o Diferido.')
    out['plan'] = raw_plan
    if raw_plan == 'DIFERIDO':
        try:
            qty = int(installments or 0)
        except Exception:
            qty = 0
        if qty < 2 or qty > 99:
            raise core.HTTPException(400, 'Ingresa una cantidad válida de cuotas.')
        out['installments'] = qty
    else:
        out['installments'] = 1
    return out

class V4504PaymentPart(core.BaseModel):
    method: str
    amount: float
    card_plan: str | None = None
    installments: int | None = None
    voucher: str | None = None

class V4504VisitBatchPaymentIn(core.VisitBatchIn):
    payment_method: str
    couple_discount: bool = False
    payment_parts: list[V4504PaymentPart] = []
    card_plan: str | None = None
    installments: int | None = None
    voucher: str | None = None

class V4504BillingPaymentIn(core.BaseModel):
    patient_id: int
    fecha: _date
    payment_method: str
    payment_parts: list[V4504PaymentPart] = []
    card_plan: str | None = None
    installments: int | None = None
    voucher: str | None = None

def _make_payment_info(method: object, total: float, payment_parts=None, card_plan=None, installments=None, voucher=None) -> dict:
    total = _money(total)
    if total <= 0:
        raise core.HTTPException(400, 'El total a cobrar debe ser mayor a cero.')
    method = _normalize_method(method)
    if method != 'MIXTO':
        part = {'method': method, 'amount': total, 'sri_code': SRI_CODES[method]}
        part.update(_card_details(method, card_plan, installments, voucher))
        return {'version': 1, 'method': method, 'total': total, 'parts': [part]}
    raw_parts = list(payment_parts or [])
    if len(raw_parts) < 2 or len(raw_parts) > 4:
        raise core.HTTPException(400, 'Pago mixto requiere entre 2 y 4 partes.')
    parts = []
    methods = set()
    running = 0.0
    for raw in raw_parts:
        part_method = _normalize_method(getattr(raw, 'method', None), False)
        amount = _money(getattr(raw, 'amount', 0))
        if amount <= 0:
            raise core.HTTPException(400, 'Cada parte del pago mixto debe ser mayor a cero.')
        methods.add(part_method)
        running = _money(running + amount)
        part = {'method': part_method, 'amount': amount, 'sri_code': SRI_CODES[part_method]}
        part.update(_card_details(part_method, getattr(raw, 'card_plan', None), getattr(raw, 'installments', None), getattr(raw, 'voucher', None)))
        parts.append(part)
    if len(methods) < 2:
        raise core.HTTPException(400, 'Pago mixto debe combinar dos formas distintas.')
    if abs(running - total) > 0.009:
        raise core.HTTPException(400, 'El pago mixto suma $' + f'{running:.2f}' + ', pero el total es $' + f'{total:.2f}' + '.')
    return {'version': 1, 'method': 'MIXTO', 'total': total, 'parts': parts}

def _encode_marker(info: dict) -> str:
    raw = json.dumps(info, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    token = base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')
    return '[[RP_PAY_V1:' + token + ']]'

def _strip_marker(value: object) -> str:
    text = PAY_RE.sub('', str(value or ''))
    text = re.sub('\\s*\\|\\s*\\|\\s*', ' | ', text)
    return text.strip(' |')

def _with_marker(value: object, info: dict | None):
    clean = _strip_marker(value)
    if not info:
        return clean or None
    marker = _encode_marker(info)
    return clean + ' | ' + marker if clean else marker

def _decode_marker(value: object):
    match = PAY_RE.search(str(value or ''))
    if not match:
        return None
    try:
        token = match.group(1)
        token += '=' * ((4 - len(token) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(token.encode('ascii')).decode('utf-8'))
        return data if isinstance(data, dict) else None
    except Exception:
        return None

def _payment_info_from_visits(visits):
    rows = sorted(list(visits or []), key=lambda v: abs(int(getattr(v, 'id', 0) or 0)))
    total = _money(sum((_money(getattr(v, 'valor', 0)) for v in rows)))
    for visit in rows:
        info = _decode_marker(getattr(visit, 'observacion', None))
        if info:
            info = dict(info)
            info['total'] = total
            if info.get('method') != 'MIXTO' and info.get('parts'):
                info['parts'][0]['amount'] = total
            return info
    reverse = {value: method for method, value in PAYMENT_SENTINELS.items()}
    totals = {}
    for visit in rows:
        try:
            method = reverse.get(int(getattr(visit, 'source_row', 0) or 0))
        except Exception:
            method = None
        if method and method != 'MIXTO':
            totals[method] = _money(totals.get(method, 0) + _money(getattr(visit, 'valor', 0)))
    if len(totals) == 1:
        method = next(iter(totals))
        return {'version': 0, 'method': method, 'total': total, 'parts': [{'method': method, 'amount': total, 'sri_code': SRI_CODES[method]}]}
    if len(totals) > 1:
        return {'version': 0, 'method': 'MIXTO', 'total': total, 'parts': [{'method': method, 'amount': amount, 'sri_code': SRI_CODES[method]} for method, amount in totals.items()]}
    return None

def _payment_label_from_visits(visits):
    info = _payment_info_from_visits(visits)
    method = str((info or {}).get('method') or '')
    return PAYMENT_LABELS.get(method, 'NO REGISTRADA')

def _apply_payment(visits, info: dict):
    rows = sorted(list(visits or []), key=lambda v: abs(int(getattr(v, 'id', 0) or 0)))
    sentinel = PAYMENT_SENTINELS[str(info.get('method') or '')]
    for index, visit in enumerate(rows):
        visit.source_row = sentinel
        visit.observacion = _with_marker(getattr(visit, 'observacion', None), info if index == 0 else None)

def _remove_route(path: str, method: str) -> int:
    wanted = str(method).upper()
    kept = []
    removed = 0
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in getattr(route, 'methods', None) or set()}
        if getattr(route, 'path', None) == path and wanted in methods:
            removed += 1
        else:
            kept.append(route)
    if removed:
        app.router.routes[:] = kept
        try:
            app.openapi_schema = None
        except Exception:
            pass
    return removed

def _update_offline_payload(db, visit):
    try:
        queued = list(db.scalars(core.select(core.OfflineQueue).where(core.OfflineQueue.operation == 'visit.create', core.OfflineQueue.local_entity_id == int(visit.id))))
        for item in queued:
            try:
                payload = core.json.loads(item.payload or '{}')
            except Exception:
                payload = {}
            payload['source_row'] = visit.source_row
            payload['observacion'] = visit.observacion
            item.payload = core.json.dumps(payload, ensure_ascii=False)
    except Exception:
        pass
try:
    legacy = _rf_module_lookup('app_prev_4458')
    if legacy is not None:
        try:
            legacy.PAYMENT_SENTINELS.update(PAYMENT_SENTINELS)
            legacy.SRI_PAYMENT_CODES.update(SRI_CODES)
        except Exception:
            pass
    ROUTES_REPLACED += _remove_route('/api/visits/batch-payment', 'POST')
    ROUTES_REPLACED += _remove_route('/api/billing/payment-method', 'POST')
    ROUTES_REPLACED += _remove_route('/api/billing/payment-methods', 'GET')

    @app.post('/api/visits/batch-payment')
    def v4504_create_visit_batch_payment(data: V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, 'Paciente no encontrado')
        if not data.services:
            raise core.HTTPException(400, 'Selecciona al menos una atención')
        if len(data.services) > 20:
            raise core.HTTPException(400, 'Hay demasiadas acciones seleccionadas')
        override = (data.tipo or '').strip().upper()
        if override and override not in {'N', 'S'}:
            raise core.HTTPException(400, 'Estado de paciente inválido')
        prior = db.scalar(core.select(core.func.count(core.Visit.id)).where(core.Visit.patient_id == int(patient.id))) or 0
        historical_prior = bool(not prior and core.historical_summary_for_patient(patient))
        first_type = override or ('S' if prior or historical_prior else 'N')
        normalized = []
        seen = set()
        has_consultation = False
        for item in data.services:
            procedure = (item.procedimiento or '').strip().upper() or None
            key = procedure or 'CONSULTA'
            if key in seen:
                continue
            seen.add(key)
            if procedure is None:
                has_consultation = True
                value = _rf_alias_app_patch_4504__previous.CONSULT_COUPLE_TOTAL if bool(data.couple_discount) else _rf_alias_app_patch_4504__previous.CONSULT_BASE
            else:
                if item.valor is None:
                    raise core.HTTPException(400, 'Ingresa el valor de ' + key)
                value = item.valor
            value = _money(value)
            if value < 0:
                raise core.HTTPException(400, 'Valor inválido para ' + key)
            normalized.append((procedure, value))
        if not normalized:
            raise core.HTTPException(400, 'Selecciona al menos una atención')
        existing = list(db.scalars(core.select(core.Visit).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == int(data.patient_id), core.Visit.fecha == data.fecha, core.BillingRecord.estado != 'EMITIDA').order_by(core.Visit.id)))
        requested_method = _normalize_method(data.payment_method)
        if requested_method == 'MIXTO' and existing:
            raise core.HTTPException(409, 'Este paciente ya tiene cobros abiertos del mismo día. Guarda con una forma simple y ajusta Pago mixto desde Facturación.')
        new_total = _money(sum((value for _procedure, value in normalized)))
        info = _make_payment_info(requested_method, new_total, data.payment_parts, data.card_plan, data.installments, data.voucher)
        discount_applied = bool(data.couple_discount and has_consultation)
        offline = core.is_offline_db(db)
        created = []
        specs = []
        for index, (procedure, value) in enumerate(normalized):
            tipo = first_type if index == 0 else 'S'
            observation = data.observacion
            if procedure is None and discount_applied:
                observation = _rf_alias_app_patch_4504__previous._discount_observation(data.observacion)
            visit = core.Visit(patient_id=int(data.patient_id), fecha=data.fecha, tipo=tipo, procedimiento=procedure, valor=value, observacion=observation, source_row=PAYMENT_SENTINELS[info['method']])
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedure, value))
        db.flush()
        all_open = [*existing, *created]
        group_total = _money(sum((_money(v.valor) for v in all_open)))
        if info['method'] != 'MIXTO':
            info = _make_payment_info(info['method'], group_total, None, data.card_plan, data.installments, data.voucher)
        _apply_payment(all_open, info)
        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado='PENDIENTE')
            db.add(billing)
            billings.append(billing)
        for visit, tipo, procedure, value in specs:
            service_name = procedure or 'CONSULTA'
            if offline:
                payload = {'patient_id': int(data.patient_id), 'fecha': data.fecha.isoformat(), 'tipo': tipo, 'procedimiento': procedure, 'valor': value, 'observacion': visit.observacion, 'source_row': visit.source_row}
                core.add_queue(db, 'visit.create', 'visit', payload, user.username, int(visit.id))
                core.audit(db, user, 'crear_atencion_multiple_offline', 'Atención local ' + str(visit.id) + ', paciente ' + str(patient.id) + ', ' + service_name)
            else:
                core.audit(db, user, 'crear_atencion_multiple', 'Atención ' + str(visit.id) + ', paciente ' + str(patient.id) + ', servicio ' + service_name)
            if procedure is None and discount_applied:
                core.audit(db, user, 'aplicar_descuento_pareja', 'Consulta base $40.00, descuento $10.00, total $30.00')
        if offline:
            for visit in all_open:
                _update_offline_payload(db, visit)
        detail = PAYMENT_LABELS[info['method']]
        if info['method'] == 'MIXTO':
            detail += ' · ' + ' + '.join((PAYMENT_LABELS[p['method']] + ' $' + f"{_money(p['amount']):.2f}" for p in info['parts']))
        core.audit(db, user, 'registrar_forma_pago_atencion', detail)
        db.commit()
        if not offline:
            for visit in all_open:
                try:
                    core.mirror_visit_to_local(visit)
                except Exception:
                    pass
            for billing in billings:
                try:
                    core.mirror_billing_to_local(billing)
                except Exception:
                    pass
        return {'ok': True, 'count': len(created), 'items': [core.v_dict(v) for v in created], 'offline': offline, 'payment_method': info['method'], 'payment_label': PAYMENT_LABELS[info['method']], 'payment_parts': info['parts'], 'couple_discount': discount_applied, 'consultation_total': _rf_alias_app_patch_4504__previous.CONSULT_COUPLE_TOTAL if discount_applied and has_consultation else _rf_alias_app_patch_4504__previous.CONSULT_BASE if has_consultation else None}

    @app.get('/api/billing/payment-methods')
    def v4504_billing_payment_methods(db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        rows = db.execute(core.select(core.Visit, core.BillingRecord).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.BillingRecord.estado != 'EMITIDA').order_by(core.Visit.fecha.desc(), core.Visit.patient_id, core.Visit.id)).all()
        grouped = {}
        for visit, _billing in rows:
            grouped.setdefault((int(visit.patient_id), visit.fecha.isoformat()), []).append(visit)
        items = []
        for (patient_id, fecha), visits in grouped.items():
            info = _payment_info_from_visits(visits)
            method = str((info or {}).get('method') or '')
            items.append({'patient_id': patient_id, 'fecha': fecha, 'payment_method': method or None, 'payment_label': PAYMENT_LABELS.get(method), 'payment_parts': list((info or {}).get('parts') or []), 'mixed': method == 'MIXTO', 'total': _money(sum((_money(v.valor) for v in visits)))})
        return {'items': items}

    @app.post('/api/billing/payment-method')
    def v4504_set_billing_payment_method(data: V4504BillingPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        if core.is_offline_db(db):
            raise core.HTTPException(503, 'Conéctate a Internet para cambiar la forma de pago desde Facturación.')
        rows = db.execute(core.select(core.Visit, core.BillingRecord).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.patient_id == int(data.patient_id), core.Visit.fecha == data.fecha).order_by(core.Visit.id)).all()
        if not rows:
            raise core.HTTPException(404, 'No se encontró esa ficha de facturación.')
        if 'EMITIDA' in {str(b.estado or '').upper() for _v, b in rows}:
            raise core.HTTPException(409, 'La factura ya fue emitida.')
        visits = [visit for visit, _billing in rows]
        total = _money(sum((_money(v.valor) for v in visits)))
        info = _make_payment_info(data.payment_method, total, data.payment_parts, data.card_plan, data.installments, data.voucher)
        _apply_payment(visits, info)
        core.audit(db, user, 'registrar_forma_pago_facturacion', PAYMENT_LABELS[info['method']])
        db.commit()
        for visit in visits:
            try:
                core.mirror_visit_to_local(visit)
            except Exception:
                pass
        return {'ok': True, 'payment_method': info['method'], 'payment_label': PAYMENT_LABELS[info['method']], 'payment_parts': info['parts']}
    base_payload = (getattr(legacy, '_stable_azur_payload_for_group', None) if legacy is not None else None) or core._azur_payload_for_group

    def v4504_azur_payload_for_group(data, patient, rows):
        payload = base_payload(data, patient, rows)
        visits = [visit for _billing, visit in rows]
        total = _money(sum((_money(v.valor) for v in visits)))
        info = _payment_info_from_visits(visits)
        if not info:
            raise core.HTTPException(409, 'La forma de pago no está registrada.')
        if info.get('method') == 'MIXTO':
            parts = list(info.get('parts') or [])
            running = _money(sum((_money(p.get('amount')) for p in parts)))
            if not parts or abs(running - total) > 0.009:
                raise core.HTTPException(409, 'El Pago mixto no coincide con el total. Corrígelo antes de emitir.')
            totals = {}
            for part in parts:
                code = str(part.get('sri_code') or SRI_CODES.get(part.get('method')) or '')
                amount = _money(part.get('amount'))
                if code and amount > 0:
                    totals[code] = _money(totals.get(code, 0) + amount)
        else:
            method = str(info.get('method') or '')
            code = SRI_CODES.get(method)
            if not code:
                raise core.HTTPException(409, 'Forma de pago inválida.')
            totals = {code: total}
        payload['pagos'] = [{'tipo': code, 'total': amount, 'tiempo': 'dias', 'plazo': 0} for code, amount in sorted(totals.items())]
        return payload
    core._azur_payload_for_group = v4504_azur_payload_for_group
    proof_mod = _rf_module_lookup('app_patch_4485')
    if proof_mod is not None:
        proof_mod._PAYMENT_SENTINELS = {value: PAYMENT_LABELS[method] for method, value in PAYMENT_SENTINELS.items()}
        proof_mod._payment_method_for_visits = _payment_label_from_visits

    @app.get('/api/v4504/day-summary')
    def v4504_day_summary(fecha: str, user=core.Depends(core.current_user)):
        try:
            target = _date.fromisoformat(str(fecha or '')[:10])
        except Exception:
            raise core.HTTPException(400, 'Fecha inválida')
        with core.LocalSessionLocal() as db:
            visits = list(db.scalars(core.select(core.Visit).where(core.Visit.fecha == target).order_by(core.Visit.patient_id, core.Visit.id)))
            grouped = {}
            for visit in visits:
                grouped.setdefault(int(visit.patient_id), []).append(visit)
            amounts = {'efectivo': 0.0, 'transferencia': 0.0, 'tarjeta': 0.0}
            mixed_groups = 0
            discount_count = 0
            for group in grouped.values():
                info = _payment_info_from_visits(group)
                if info:
                    if info.get('method') == 'MIXTO':
                        mixed_groups += 1
                    for part in info.get('parts') or []:
                        method = str(part.get('method') or '')
                        amount = _money(part.get('amount'))
                        if method == 'EFECTIVO':
                            amounts['efectivo'] = _money(amounts['efectivo'] + amount)
                        elif method == 'TRANSFERENCIA':
                            amounts['transferencia'] = _money(amounts['transferencia'] + amount)
                        elif method in CARD_METHODS:
                            amounts['tarjeta'] = _money(amounts['tarjeta'] + amount)
                discount_count += sum((1 for v in group if 'DESCUENTO PAREJA' in str(v.observacion or '').upper()))
            pending_rows = db.execute(core.select(core.Visit, core.BillingRecord).join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id).where(core.Visit.fecha == target, core.BillingRecord.estado != 'EMITIDA')).all()
            pending_ids = {int(v.patient_id) for v, _b in pending_rows}
            missing_id = 0
            for pid in pending_ids:
                patient = db.get(core.Patient, pid)
                if patient and (not str(patient.cedula or '').strip()):
                    missing_id += 1
        return {'ok': True, 'fecha': target.isoformat(), 'payments': amounts, 'mixed_groups': mixed_groups, 'discounts': {'count': discount_count, 'amount': _money(discount_count * _rf_alias_app_patch_4504__previous.COUPLE_DISCOUNT)}, 'pending': {'billing_groups': len(pending_ids), 'missing_identification': missing_id}, 'local_only': True}
    V4504_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{content:"v4.5.4"!important;font-size:9px!important;line-height:1!important;font-weight:850!important}\n#v4451AttentionPayment{display:none!important}\n.modalbox.attention-form-modal{border-radius:17px!important;box-shadow:0 22px 58px rgba(29,51,79,.18)!important}\n.attention-form-modal .service-card{border-radius:12px!important}\n.v4504-pay{margin:12px 0 10px;padding:13px;border:1px solid #d8e3ee;border-radius:14px;background:#f8fbff}\n.v4504-pay.required{border-color:#d9a23d;background:#fffaf0;box-shadow:0 0 0 3px rgba(217,162,61,.09)}\n.v4504-pay-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}\n.v4504-pay-head b{font-size:11px;color:#203c5b}\n.v4504-pay-head small{display:block;margin-top:2px;font-size:8px;color:#71859a}\n.v4504-pay-state{padding:4px 8px;border-radius:999px;background:#edf2f7;color:#66788d;font-size:8px;font-weight:900;white-space:nowrap}\n.v4504-pay-state.ready{background:#e5f5eb;color:#286b46}\n.v4504-pay-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}\n.v4504-pay-option{min-height:52px!important;border:1px solid #d0dce8!important;border-radius:11px!important;background:#fff!important;color:#3f5871!important;padding:8px 9px!important;box-shadow:none!important;display:grid!important;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:7px;text-align:left!important}\n.v4504-pay-option>span{grid-row:1/3;font-size:17px;align-self:center}\n.v4504-pay-option>b{font-size:9px}\n.v4504-pay-option>small{font-size:7.5px;color:#8190a1}\n.v4504-pay-option.selected{border-color:#6ea88a!important;background:#edf8f2!important;color:#245e41!important}\n.v4504-details{margin-top:9px;padding:10px;border:1px solid #e1e8f0;border-radius:11px;background:#fff}\n.v4504-details.hidden{display:none!important}\n.v4504-segment{display:flex;gap:6px;flex-wrap:wrap}\n.v4504-segment button{min-height:30px!important;padding:5px 9px!important;border-radius:8px!important;border:1px solid #d4dee8!important;background:#fff!important;color:#52677e!important;font-size:8px!important;font-weight:850!important;box-shadow:none!important}\n.v4504-segment button.selected{background:#eaf4ff!important;border-color:#89add2!important;color:#285d92!important}\n.v4504-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:9px}\n.v4504-fields label{display:block;margin-bottom:4px;font-size:7.5px;font-weight:850;color:#75879a}\n.v4504-fields input{width:100%;height:34px!important;border-radius:8px!important;font-size:9px!important}\n.v4504-mixed{display:grid;grid-template-columns:1.2fr .8fr 1.2fr .8fr;gap:7px}\n.v4504-mixed label{display:block;margin-bottom:4px;font-size:7.5px;font-weight:850;color:#75879a}\n.v4504-mixed select,.v4504-mixed input{width:100%;height:34px!important;border-radius:8px!important;font-size:9px!important}\n.v4504-summary{margin:10px 0 12px;border:1px solid #d8e3ed;border-radius:14px;background:#fff;overflow:hidden}\n.v4504-summary-head{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;background:#f4f8fc;border-bottom:1px solid #e1e8ef}\n.v4504-summary-head b{font-size:9px;color:#657b92}\n.v4504-summary-head strong{font-size:18px;color:#1f4f7e}\n.v4504-summary-body{display:grid;grid-template-columns:1fr auto;gap:5px 12px;padding:10px 12px;font-size:9px;color:#536a82}\n.v4504-summary-body b{text-align:right;color:#2e536f}\n.v4504-discount{color:#347150!important}\n.v4504-day-strip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:7px 0 10px;padding:7px 9px;border:1px solid #e0e7ef;border-radius:10px;background:#fbfcfe}\n.v4504-day-strip>span:first-child{font-size:7.5px;font-weight:950;color:#718399;letter-spacing:.08em}\n.v4504-day-pill{display:inline-flex;gap:4px;padding:4px 7px;border:1px solid #dce5ee;border-radius:999px;background:#fff;color:#536a82;font-size:8px;font-weight:800}\n.v4504-day-pill b{color:#274e76}\n.v4504-day-pill.warn{border-color:#ecd4a1;background:#fff8e8;color:#8b641d}\n#facturacion .v4431-pay-wrap{display:none!important}\n#facturacion .billing-card{border-radius:14px!important}\n.v4504-billpay{margin:8px 0 10px;padding:9px;border:1px solid #d9e3ed;border-radius:11px;background:#f9fbfd}\n.v4504-billpay-head{display:flex;justify-content:space-between;margin-bottom:7px}\n.v4504-billpay-head span{font-size:8px;font-weight:950;color:#64798f}\n.v4504-billpay-head b{font-size:9px;color:#315978}\n.v4504-billchoices{display:flex;gap:5px;flex-wrap:wrap}\n.v4504-billchoices button{min-height:29px!important;padding:5px 8px!important;border-radius:8px!important;border:1px solid #d2dde8!important;background:#fff!important;color:#536a82!important;font-size:8px!important;font-weight:850!important;box-shadow:none!important}\n.v4504-billchoices button.selected{background:#eaf7ef!important;border-color:#79b291!important;color:#286344!important}\n@media(max-width:760px){\n .v4504-pay-options{grid-template-columns:repeat(2,minmax(0,1fr))}\n .v4504-fields,.v4504-mixed{grid-template-columns:1fr 1fr}\n}\n'
    V4504_JS = '\n;(()=>{\n if(window.__v4504Payments)return;\n window.__v4504Payments=true;\n const VERSION=\'4.5.4\';\n let mode=\'\',cardType=\'DEBITO\',cardPlan=\'CORRIENTE\',installments=3,voucher=\'\';\n let mixA=\'EFECTIVO\',mixB=\'TARJETA_DEBITO\',mixAmount=\'\';\n let billingMap=new Map(),billingBusy=false;\n const q=(s,r=document)=>r.querySelector(s);\n const qa=(s,r=document)=>[...r.querySelectorAll(s)];\n const norm=v=>String(v||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\n const money=n=>\'$\'+Number(n||0).toFixed(2);\n const key=(p,f)=>Number(p)+\'|\'+String(f||\'\').slice(0,10);\n const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n const label=m=>({EFECTIVO:\'Efectivo\',TRANSFERENCIA:\'Transferencia\',TARJETA_DEBITO:\'Débito\',TARJETA_CREDITO:\'Crédito\',MIXTO:\'Pago mixto\'}[m]||m||\'\');\n\n function box(){\n   return document.querySelector(\'.attention-form-modal\')\n    ||[...document.querySelectorAll(\'#modal .modalbox,.modal .modalbox,.modalbox\')].find(\n      b=>[...b.querySelectorAll(\'h1,h2,h3\')].some(\n        h=>norm(h.textContent)===\'nueva atencion\'\n      )\n    )||null;\n }\n\n function cards(){\n   const b=box();\n   return b\n    ?[...new Set([\n      ...b.querySelectorAll(\'button.service-card.selected\'),\n      ...b.querySelectorAll(\'button.service-card.is-selected\')\n    ])]\n    :[];\n }\n\n function editableCardValue(c){\n   const b=box();\n   if(!b||!c)return 0;\n   const service=norm(\n     c.dataset?.service\n     ||q(\'strong,b\',c)?.textContent\n     ||\'\'\n   );\n   if(!service)return 0;\n\n   const candidates=[\n     ...b.querySelectorAll(\n       \'input[type="number"],input[inputmode="decimal"]\'\n     )\n   ].filter(input=>\n     !input.closest(\n       \'#v4504Payment,#v4504Summary,#v4525Bendo\'\n     )\n   );\n\n   // Los procedimientos sin precio fijo muestran el importe en un editor\n   // FUERA de la tarjeta: "Valor de FULGURACIÓN", etc. Vinculamos el input\n   // por el nombre real del procedimiento para no confundirlo con pagos.\n   for(const input of candidates){\n     let node=input.parentElement;\n     for(let depth=0;node&&node!==b&&depth<7;depth++,node=node.parentElement){\n       const text=norm(node.textContent||\'\');\n       if(\n         text.includes(\'valor de \'+service)\n         ||(text.includes(\'valor\')&&text.includes(service))\n       ){\n         const value=Number(String(input.value||\'\').replace(\',\',\'.\'));\n         if(Number.isFinite(value)&&value>0){\n           return Math.round(value*100)/100;\n         }\n       }\n     }\n   }\n\n   // Respaldo conservador: si hay exactamente un procedimiento seleccionado\n   // sin precio fijo y un solo campo numérico operativo, ese campo le pertenece.\n   const editableSelected=cards().filter(card=>{\n     const raw=String(q(\'.service-price\',card)?.textContent||\'\');\n     const fixed=Number(\n       raw.replace(\',\',\'.\').replace(/[^\\d.]/g,\'\')||0\n     );\n     return !(fixed>0);\n   });\n   if(editableSelected.length===1&&editableSelected[0]===c&&candidates.length===1){\n     const value=Number(String(candidates[0].value||\'\').replace(\',\',\'.\'));\n     if(Number.isFinite(value)&&value>0){\n       return Math.round(value*100)/100;\n     }\n   }\n   return 0;\n }\n\n function cardVal(c){\n   let text=String(q(\'.service-price\',c)?.textContent||\'\')\n    .replace(\',\',\'.\')\n    .replace(/[^\\d.]/g,\'\');\n   let value=Number(text||0);\n   if(!value)value=Number(q(\'input[type="number"]\',c)?.value||0);\n   if(!value)value=editableCardValue(c);\n   return Number.isFinite(value)\n    ?Math.round(value*100)/100\n    :0;\n }\n\n function total(){\n   return Math.round(\n     cards().reduce((sum,c)=>sum+cardVal(c),0)*100\n   )/100;\n }\n\n function discounted(){\n   try{\n     return !!window.__v4502CoupleDiscountTest?.enabled?.();\n   }catch(_e){\n     return false;\n   }\n }\n\n function serverMethod(){\n   if(mode===\'EFECTIVO\'||mode===\'TRANSFERENCIA\')return mode;\n   if(mode===\'TARJETA\')return cardType===\'CREDITO\'?\'TARJETA_CREDITO\':\'TARJETA_DEBITO\';\n   if(mode===\'MIXTO\')return \'MIXTO\';\n   return \'\';\n }\n\n function paymentText(){\n   const method=serverMethod();\n   if(method===\'TARJETA_CREDITO\'){\n     return cardPlan===\'DIFERIDO\'\n      ?\'Crédito diferido · \'+Number(installments||0)+\' cuotas\'\n      :\'Tarjeta crédito · corriente\';\n   }\n   if(method===\'MIXTO\'){\n     const first=Number(mixAmount||0);\n     const second=Math.max(0,total()-first);\n     return \'Mixto · \'+label(mixA)+\' \'+money(first)\n      +\' + \'+label(mixB)+\' \'+money(second);\n   }\n   return label(method)||\'Sin seleccionar\';\n }\n\n function buildPayload(){\n   const amount=total();\n   const method=serverMethod();\n   if(!method)throw Error(\'Selecciona la forma de pago.\');\n   if(amount<=0)throw Error(\'Selecciona al menos una atención con valor.\');\n\n   const payload={payment_method:method};\n\n   if(method===\'TARJETA_DEBITO\'||method===\'TARJETA_CREDITO\'){\n     payload.card_plan=method===\'TARJETA_CREDITO\'?cardPlan:null;\n     payload.installments=(\n       method===\'TARJETA_CREDITO\'\n       &&cardPlan===\'DIFERIDO\'\n     )?Number(installments||0):1;\n     payload.voucher=String(voucher||\'\').trim();\n   }\n\n   if(method===\'MIXTO\'){\n     const first=Math.round(Number(mixAmount||0)*100)/100;\n     const second=Math.round((amount-first)*100)/100;\n     if(first<=0||second<=0){\n       throw Error(\'En Pago mixto ambos valores deben ser mayores a $0.\');\n     }\n     if(mixA===mixB){\n       throw Error(\'Selecciona dos formas distintas.\');\n     }\n     const makePart=(partMethod,value)=>{\n       const part={\n         method:partMethod,\n         amount:value\n       };\n       if(partMethod===\'TARJETA_DEBITO\'||partMethod===\'TARJETA_CREDITO\'){\n         part.card_plan=partMethod===\'TARJETA_CREDITO\'?cardPlan:null;\n         part.installments=(\n           partMethod===\'TARJETA_CREDITO\'\n           &&cardPlan===\'DIFERIDO\'\n         )?Number(installments||0):(partMethod===\'TARJETA_CREDITO\'?1:null);\n         part.voucher=String(voucher||\'\').trim();\n       }\n       return part;\n     };\n     payload.payment_parts=[\n       makePart(mixA,first),\n       makePart(mixB,second)\n     ];\n   }\n\n   return payload;\n }\n\n function optionButton(value,icon,title,small){\n   return \'<button type="button" class="v4504-pay-option \'\n    +(mode===value?\'selected\':\'\')\n    +\'" data-mode="\'+value+\'"><span>\'+icon+\'</span><b>\'\n    +title+\'</b><small>\'+small+\'</small></button>\';\n }\n\n function render(){\n   const b=box();\n   if(!b)return;\n\n   let host=q(\'#v4504Payment\',b);\n   if(!host){\n     host=document.createElement(\'section\');\n     host.id=\'v4504Payment\';\n     host.className=\'v4504-pay\';\n     const old=q(\'#v4451AttentionPayment\',b);\n     if(old){\n       old.insertAdjacentElement(\'afterend\',host);\n     }else{\n       (q(\'.v492-sticky-actions\',b)||q(\'.actions\',b))\n        ?.insertAdjacentElement(\'beforebegin\',host);\n     }\n   }\n\n   host.classList.toggle(\'required\',!mode);\n   host.innerHTML=\n    \'<div class="v4504-pay-head"><div><b>Forma de pago</b>\'\n    +\'<small>Obligatorio · preparado para datáfono y factura/SRI.</small>\'\n    +\'</div><span class="v4504-pay-state \'+(mode?\'ready\':\'\')+\'">\'\n    +(mode?\'✓ \'+paymentText():\'Sin seleccionar\')\n    +\'</span></div><div class="v4504-pay-options">\'\n    +optionButton(\'EFECTIVO\',\'💵\',\'Efectivo\',\'SRI 01\')\n    +optionButton(\'TRANSFERENCIA\',\'🏦\',\'Transferencia\',\'SRI 20\')\n    +optionButton(\'TARJETA\',\'💳\',\'Tarjeta\',\'Débito / Crédito\')\n    +optionButton(\'MIXTO\',\'◫\',\'Pago mixto\',\'Combina 2 formas\')\n    +\'</div><div id="v4504Card" class="v4504-details \'\n    +((mode===\'TARJETA\'||(mode===\'MIXTO\'&&(\n      mixA.indexOf(\'TARJETA\')===0||mixB.indexOf(\'TARJETA\')===0\n    )))?\'\':\'hidden\')\n    +\'"></div><div id="v4504Mixed" class="v4504-details \'\n    +(mode===\'MIXTO\'?\'\':\'hidden\')\n    +\'"></div>\';\n\n   qa(\'[data-mode]\',host).forEach(\n     button=>button.addEventListener(\'click\',()=>{\n       mode=button.dataset.mode||\'\';\n       render();\n     })\n   );\n\n   renderCard();\n   renderMixed();\n   renderSummary();\n }\n\n function renderCard(){\n   const host=q(\'#v4504Card\');\n   if(!host||host.classList.contains(\'hidden\'))return;\n\n   const credit=(\n     mode===\'TARJETA\'\n      ?cardType===\'CREDITO\'\n      :(mixA===\'TARJETA_CREDITO\'||mixB===\'TARJETA_CREDITO\')\n   );\n\n   host.innerHTML=\n    (mode===\'TARJETA\'\n      ?\'<div class="v4504-segment">\'\n       +\'<button type="button" data-ct="DEBITO" class="\'\n       +(cardType===\'DEBITO\'?\'selected\':\'\')\n       +\'">Débito · SRI 16</button>\'\n       +\'<button type="button" data-ct="CREDITO" class="\'\n       +(cardType===\'CREDITO\'?\'selected\':\'\')\n       +\'">Crédito · SRI 19</button></div>\'\n      :\'\')\n    +(credit\n      ?\'<div class="v4504-segment" style="margin-top:7px">\'\n       +\'<button type="button" data-cp="CORRIENTE" class="\'\n       +(cardPlan===\'CORRIENTE\'?\'selected\':\'\')\n       +\'">Corriente</button>\'\n       +\'<button type="button" data-cp="DIFERIDO" class="\'\n       +(cardPlan===\'DIFERIDO\'?\'selected\':\'\')\n       +\'">Diferido</button></div>\'\n      :\'\')\n    +\'<div class="v4504-fields">\'\n    +(credit&&cardPlan===\'DIFERIDO\'\n      ?\'<div><label>Cuotas</label><input id="v4504Cuotas" type="number" min="2" max="99" value="\'\n       +Number(installments||3)+\'"></div>\'\n      :\'\')\n    +\'<div><label>Voucher / autorización</label>\'\n    +\'<input id="v4504Voucher" maxlength="40" placeholder="Opcional" value="\'\n    +esc(voucher)+\'"></div>\'\n    +\'<div><label>Seguridad</label>\'\n    +\'<input disabled value="No se guarda tarjeta ni CVV"></div></div>\';\n\n   qa(\'[data-ct]\',host).forEach(\n     button=>button.addEventListener(\'click\',()=>{\n       cardType=button.dataset.ct;\n       render();\n     })\n   );\n   qa(\'[data-cp]\',host).forEach(\n     button=>button.addEventListener(\'click\',()=>{\n       cardPlan=button.dataset.cp;\n       render();\n     })\n   );\n   q(\'#v4504Cuotas\',host)?.addEventListener(\n     \'input\',\n     event=>{\n       installments=Number(event.target.value||0);\n       renderSummary();\n     }\n   );\n   q(\'#v4504Voucher\',host)?.addEventListener(\n     \'input\',\n     event=>{\n       voucher=event.target.value;\n     }\n   );\n }\n\n function options(selected){\n   return [\n     \'EFECTIVO\',\n     \'TRANSFERENCIA\',\n     \'TARJETA_DEBITO\',\n     \'TARJETA_CREDITO\'\n   ].map(\n     value=>\'<option value="\'+value+\'" \'\n      +(value===selected?\'selected\':\'\')\n      +\'>\'+label(value)+\'</option>\'\n   ).join(\'\');\n }\n\n function renderMixed(){\n   const host=q(\'#v4504Mixed\');\n   if(!host||mode!==\'MIXTO\')return;\n\n   const rest=Math.max(\n     0,\n     Math.round(\n       (total()-Number(mixAmount||0))*100\n     )/100\n   );\n\n   host.innerHTML=\n    \'<div class="v4504-mixed">\'\n    +\'<div><label>Forma 1</label><select id="v4504MixA">\'\n    +options(mixA)+\'</select></div>\'\n    +\'<div><label>Valor 1</label><input id="v4504MixAmount" type="number" min="0.01" step="0.01" value="\'\n    +esc(mixAmount)+\'"></div>\'\n    +\'<div><label>Forma 2</label><select id="v4504MixB">\'\n    +options(mixB)+\'</select></div>\'\n    +\'<div><label>Valor 2</label><input disabled value="\'\n    +rest.toFixed(2)+\'"></div></div>\'\n    +\'<small style="display:block;margin-top:7px;color:#71859a;font-size:8px">\'\n    +\'El segundo valor se calcula automáticamente para que el total cuadre.\'\n    +\'</small>\';\n\n   q(\'#v4504MixA\',host)?.addEventListener(\n     \'change\',\n     event=>{\n       mixA=event.target.value;\n       render();\n     }\n   );\n   q(\'#v4504MixB\',host)?.addEventListener(\n     \'change\',\n     event=>{\n       mixB=event.target.value;\n       render();\n     }\n   );\n   q(\'#v4504MixAmount\',host)?.addEventListener(\n     \'input\',\n     event=>{\n       mixAmount=event.target.value;\n       renderCard();\n       renderSummary();\n     }\n   );\n }\n\n function renderSummary(){\n   const b=box();\n   if(!b)return;\n\n   let summary=q(\'#v4504Summary\',b);\n   if(!summary){\n     summary=document.createElement(\'section\');\n     summary.id=\'v4504Summary\';\n     summary.className=\'v4504-summary\';\n     (q(\'.v492-sticky-actions\',b)||q(\'.actions\',b))\n      ?.insertAdjacentElement(\'beforebegin\',summary);\n   }\n\n   const selected=cards();\n   const amount=total();\n   let rows=selected.length\n    ?selected.map(\n      card=>\'<span>\'\n       +esc(\n         String(\n           card.dataset.service\n           ||q(\'strong,b\',card)?.textContent\n           ||\'Atención\'\n         )\n       )\n       +\'</span><b>\'+money(cardVal(card))+\'</b>\'\n     ).join(\'\')\n    :\'<span>Selecciona una atención</span><b>—</b>\';\n\n   if(discounted()){\n     rows+=\'<span class="v4504-discount">Descuento pareja</span>\'\n      +\'<b class="v4504-discount">−$10.00</b>\';\n   }\n\n   rows+=\'<span>Forma de pago</span><b>\'\n    +esc(paymentText())+\'</b>\';\n\n   summary.innerHTML=\n    \'<div class="v4504-summary-head">\'\n    +\'<b>RESUMEN ANTES DE GUARDAR</b>\'\n    +\'<strong>\'+money(amount)+\'</strong></div>\'\n    +\'<div class="v4504-summary-body">\'\n    +rows+\'</div>\';\n }\n\n function delayed(){\n   setTimeout(render,0);\n   setTimeout(render,100);\n   setTimeout(render,260);\n }\n\n const stableAttentionFor=window.attentionFor;\n if(typeof stableAttentionFor===\'function\'){\n   window.attentionFor=async function(){\n     mode=\'\';\n     cardType=\'DEBITO\';\n     cardPlan=\'CORRIENTE\';\n     installments=3;\n     voucher=\'\';\n     mixA=\'EFECTIVO\';\n     mixB=\'TARJETA_DEBITO\';\n     mixAmount=\'\';\n     const result=await stableAttentionFor.apply(\n       this,\n       arguments\n     );\n     delayed();\n     return result;\n   };\n }\n\n const stableSave=window.saveAttention;\n if(typeof stableSave===\'function\'){\n   window.saveAttention=async function(){\n     let paymentPayload;\n     try{\n       paymentPayload=buildPayload();\n     }catch(error){\n       q(\'#v4504Payment\')?.classList.add(\'required\');\n       alert(error?.message||String(error));\n       return;\n     }\n\n     try{\n       window.v4451ChooseAttentionPayment?.(\n         paymentPayload.payment_method===\'TRANSFERENCIA\'\n          ?\'TRANSFERENCIA\'\n          :\'EFECTIVO\'\n       );\n     }catch(_e){}\n\n     const stableApi=window.api||api;\n     const intercept=async function(url,opt={}){\n       if(String(url)===\'/api/visits/batch-payment\'){\n         let body={};\n         try{\n           body=JSON.parse(opt?.body||\'{}\');\n         }catch(_e){\n           body={};\n         }\n         Object.assign(body,paymentPayload);\n         return stableApi(\n           url,\n           {\n             ...opt,\n             body:JSON.stringify(body)\n           }\n         );\n       }\n       return stableApi(url,opt);\n     };\n\n     const previousApi=api;\n     try{\n       api=intercept;\n       return await stableSave.apply(\n         this,\n         arguments\n       );\n     }finally{\n       api=previousApi;\n     }\n   };\n }\n\n document.addEventListener(\n   \'click\',\n   event=>{\n     if(\n       event.target?.closest?.(\n         \'.attention-form-modal .service-card\'\n       )\n     ){\n       setTimeout(render,30);\n       setTimeout(render,170);\n     }\n   },\n   true\n );\n\n document.addEventListener(\n   \'change\',\n   event=>{\n     if(\n       event.target?.closest?.(\n         \'.attention-form-modal\'\n       )\n     ){\n       setTimeout(render,30);\n     }\n   },\n   true\n );\n\n function cachedGroups(){\n   try{\n     return Array.isArray(billingGroupsCache)\n      ?billingGroupsCache\n      :[];\n   }catch(_e){\n     return [];\n   }\n }\n\n function identity(card){\n   let pid=Number(\n     card.dataset.patientId||0\n   );\n   let fecha=String(\n     card.dataset.fecha||\'\'\n   ).slice(0,10);\n\n   const list=qa(\n     \'#billingList .billing-card\'\n   );\n   const index=list.indexOf(card);\n   const group=(\n     index>=0\n      ?cachedGroups()[index]\n      :null\n   );\n\n   if(!pid){\n     pid=Number(\n       group?.patient?.id||0\n     );\n   }\n   if(!fecha){\n     fecha=String(\n       group?.fecha||\'\'\n     ).slice(0,10);\n   }\n\n   if(!pid||!fecha){\n     return null;\n   }\n\n   card.dataset.patientId=String(pid);\n   card.dataset.fecha=fecha;\n\n   return {\n     pid,\n     fecha,\n     total:Number(group?.total||0)\n   };\n }\n\n async function loadBillingPayments(){\n   if(billingBusy)return;\n   billingBusy=true;\n   try{\n     const data=await api(\n       \'/api/billing/payment-methods\'\n     );\n     billingMap=new Map(\n       (data?.items||[]).map(\n         item=>[\n           key(\n             item.patient_id,\n             item.fecha\n           ),\n           item\n         ]\n       )\n     );\n     decorateBilling();\n   }catch(_e){\n   }finally{\n     billingBusy=false;\n   }\n }\n\n async function saveBilling(\n   card,\n   method,\n   extra={}\n ){\n   const id=identity(card);\n   if(!id)return;\n   try{\n     await api(\n       \'/api/billing/payment-method\',\n       {\n         method:\'POST\',\n         body:JSON.stringify({\n           patient_id:id.pid,\n           fecha:id.fecha,\n           payment_method:method,\n           ...extra\n         })\n       }\n     );\n     await loadBillingPayments();\n   }catch(error){\n     alert(\n       error?.message\n       ||String(error)\n     );\n   }\n }\n\n function decorateBill(card){\n   const id=identity(card);\n   if(!id)return;\n\n   const data=billingMap.get(\n     key(id.pid,id.fecha)\n   )||{};\n   const selected=String(\n     data.payment_method||\'\'\n   );\n\n   let host=q(\n     \'.v4504-billpay\',\n     card\n   );\n   if(!host){\n     host=document.createElement(\'div\');\n     host.className=\'v4504-billpay\';\n     const actions=q(\n       \'.billing-actions\',\n       card\n     );\n     if(actions){\n       actions.insertAdjacentElement(\n         \'beforebegin\',\n         host\n       );\n     }else{\n       card.appendChild(host);\n     }\n   }\n\n   const button=(method,text)=>\n    \'<button type="button" data-bm="\'\n    +method+\'" class="\'\n    +(selected===method?\'selected\':\'\')\n    +\'">\'+text+\'</button>\';\n\n   host.innerHTML=\n    \'<div class="v4504-billpay-head">\'\n    +\'<span>Forma de pago</span><b>\'\n    +esc(data.payment_label||\'Sin seleccionar\')\n    +\'</b></div><div class="v4504-billchoices">\'\n    +button(\'EFECTIVO\',\'💵 Efectivo\')\n    +button(\'TRANSFERENCIA\',\'🏦 Transferencia\')\n    +button(\'TARJETA_DEBITO\',\'💳 Débito\')\n    +button(\'TARJETA_CREDITO\',\'💳 Crédito\')\n    +button(\'MIXTO\',\'◫ Mixto\')\n    +\'</div>\';\n\n   qa(\n     \'[data-bm]\',\n     host\n   ).forEach(\n     buttonEl=>buttonEl.addEventListener(\n       \'click\',\n       ()=>{\n         const method=buttonEl.dataset.bm;\n\n         if(method===\'MIXTO\'){\n           const amount=Number(\n             data.total||id.total||0\n           );\n           const raw=prompt(\n             \'Valor de la primera parte del pago mixto (total \'\n             +money(amount)+\')\',\n             \'\'\n           );\n           if(raw===null)return;\n\n           const first=Math.round(\n             Number(raw||0)*100\n           )/100;\n           const second=Math.round(\n             (amount-first)*100\n           )/100;\n\n           if(first<=0||second<=0){\n             alert(\n               \'El valor debe ser mayor a $0 y menor al total.\'\n             );\n             return;\n           }\n\n           const firstMethod=prompt(\n             \'Primera forma: EFECTIVO, TRANSFERENCIA, TARJETA_DEBITO o TARJETA_CREDITO\',\n             \'EFECTIVO\'\n           );\n           if(!firstMethod)return;\n\n           const secondMethod=prompt(\n             \'Segunda forma: EFECTIVO, TRANSFERENCIA, TARJETA_DEBITO o TARJETA_CREDITO\',\n             \'TARJETA_DEBITO\'\n           );\n           if(!secondMethod)return;\n\n           const makePart=(partMethod,value)=>({\n             method:String(partMethod).toUpperCase(),\n             amount:value,\n             card_plan:String(partMethod).toUpperCase()===\'TARJETA_CREDITO\'\n              ?\'CORRIENTE\'\n              :null,\n             installments:String(partMethod).toUpperCase()===\'TARJETA_CREDITO\'\n              ?1\n              :null\n           });\n\n           saveBilling(\n             card,\n             \'MIXTO\',\n             {\n               payment_parts:[\n                 makePart(\n                   firstMethod,\n                   first\n                 ),\n                 makePart(\n                   secondMethod,\n                   second\n                 )\n               ]\n             }\n           );\n         }else{\n           saveBilling(\n             card,\n             method,\n             method===\'TARJETA_CREDITO\'\n              ?{\n                card_plan:\'CORRIENTE\',\n                installments:1\n               }\n              :{}\n           );\n         }\n       }\n     )\n   );\n }\n\n function decorateBilling(){\n   qa(\n     \'#billingList .billing-card\'\n   ).forEach(\n     decorateBill\n   );\n }\n\n const stableLoadBilling=window.loadBilling;\n if(typeof stableLoadBilling===\'function\'){\n   window.loadBilling=async function(){\n     const result=await stableLoadBilling.apply(\n       this,\n       arguments\n     );\n     await loadBillingPayments();\n     return result;\n   };\n }\n\n async function dayStrip(iso){\n   try{\n     const day=String(\n       iso||\'\'\n     ).slice(0,10);\n\n     const data=await api(\n       \'/api/v4504/day-summary?fecha=\'\n       +encodeURIComponent(day)\n     );\n\n     const title=q(\n       \'#selectedDayTitle\'\n     );\n     if(!title)return;\n\n     let strip=q(\n       \'#v4504DayStrip\'\n     );\n     if(!strip){\n       strip=document.createElement(\'div\');\n       strip.id=\'v4504DayStrip\';\n       strip.className=\'v4504-day-strip\';\n       title.insertAdjacentElement(\n         \'afterend\',\n         strip\n       );\n     }\n\n     const payments=data.payments||{};\n     const pending=data.pending||{};\n     const discounts=data.discounts||{};\n\n     let html=\n      \'<span>COBROS</span>\'\n      +\'<span class="v4504-day-pill">💵 <b>\'\n      +money(payments.efectivo)\n      +\'</b></span>\'\n      +\'<span class="v4504-day-pill">🏦 <b>\'\n      +money(payments.transferencia)\n      +\'</b></span>\'\n      +\'<span class="v4504-day-pill">💳 <b>\'\n      +money(payments.tarjeta)\n      +\'</b></span>\';\n\n     if(Number(data.mixed_groups||0)){\n       html+=\'<span class="v4504-day-pill">◫ \'\n        +Number(data.mixed_groups)\n        +\' mixto(s)</span>\';\n     }\n\n     if(Number(discounts.count||0)){\n       html+=\'<span class="v4504-day-pill">− \'\n        +Number(discounts.count)\n        +\' descuento(s) · <b>\'\n        +money(discounts.amount)\n        +\'</b></span>\';\n     }\n\n     if(Number(pending.billing_groups||0)){\n       html+=\'<span class="v4504-day-pill warn">\'\n        +\'Por facturar: <b>\'\n        +Number(pending.billing_groups)\n        +\'</b></span>\';\n     }\n\n     if(Number(pending.missing_identification||0)){\n       html+=\'<span class="v4504-day-pill warn">\'\n        +\'Sin identificación: <b>\'\n        +Number(pending.missing_identification)\n        +\'</b></span>\';\n     }\n\n     strip.innerHTML=html;\n   }catch(_e){}\n }\n\n const stableRenderHome=window.renderHomeDayPayload;\n if(typeof stableRenderHome===\'function\'){\n   window.renderHomeDayPayload=function(\n     iso,\n     data\n   ){\n     const result=stableRenderHome.apply(\n       this,\n       arguments\n     );\n     setTimeout(\n       ()=>dayStrip(iso),\n       20\n     );\n     return result;\n   };\n }\n\n function boot(){\n   qa(\n     \'.v460-version,#currentVersionBadge\'\n   ).forEach(\n     element=>{\n       element.textContent=\'v\'+VERSION;\n       element.setAttribute(\n         \'data-version\',\n         \'v\'+VERSION\n       );\n     }\n   );\n   delayed();\n   if(q(\'#billingList\')){\n     loadBillingPayments();\n   }\n }\n\n if(document.readyState===\'loading\'){\n   document.addEventListener(\n     \'DOMContentLoaded\',\n     boot,\n     {once:true}\n   );\n }else{\n   boot();\n }\n\n window.__v4504PaymentTest={\n   total,\n   payload:buildPayload,\n   render,\n   refreshBilling:loadBillingPayments\n };\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4504_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4504_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4504/health')
def v4504_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'routes_replaced': ROUTES_REPLACED, 'sri_codes': {'cash': '01', 'transfer': '20', 'debit': '16', 'credit': '19'}, 'mixed_payment': True, 'card_sensitive_data_stored': False, 'voucher_optional': True, 'credit_current_or_deferred': True, 'azur_payment_breakdown': True, 'day_payment_strip': True, 'cash_closing': False, 'database_schema_changes': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4504 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4504, '__name__', 'app_patch_4504')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4504, 'APP_VERSION', globals()['APP_VERSION'])
if 'CARD_METHODS' in globals(): setattr(_rf_snapshot_app_patch_4504, 'CARD_METHODS', globals()['CARD_METHODS'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4504, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4504, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'PAYMENT_LABELS' in globals(): setattr(_rf_snapshot_app_patch_4504, 'PAYMENT_LABELS', globals()['PAYMENT_LABELS'])
if 'PAYMENT_SENTINELS' in globals(): setattr(_rf_snapshot_app_patch_4504, 'PAYMENT_SENTINELS', globals()['PAYMENT_SENTINELS'])
if 'PAY_RE' in globals(): setattr(_rf_snapshot_app_patch_4504, 'PAY_RE', globals()['PAY_RE'])
if 'ROUTES_REPLACED' in globals(): setattr(_rf_snapshot_app_patch_4504, 'ROUTES_REPLACED', globals()['ROUTES_REPLACED'])
if 'SRI_CODES' in globals(): setattr(_rf_snapshot_app_patch_4504, 'SRI_CODES', globals()['SRI_CODES'])
if 'V4504BillingPaymentIn' in globals(): setattr(_rf_snapshot_app_patch_4504, 'V4504BillingPaymentIn', globals()['V4504BillingPaymentIn'])
if 'V4504PaymentPart' in globals(): setattr(_rf_snapshot_app_patch_4504, 'V4504PaymentPart', globals()['V4504PaymentPart'])
if 'V4504VisitBatchPaymentIn' in globals(): setattr(_rf_snapshot_app_patch_4504, 'V4504VisitBatchPaymentIn', globals()['V4504VisitBatchPaymentIn'])
if 'V4504_CSS' in globals(): setattr(_rf_snapshot_app_patch_4504, 'V4504_CSS', globals()['V4504_CSS'])
if 'V4504_JS' in globals(): setattr(_rf_snapshot_app_patch_4504, 'V4504_JS', globals()['V4504_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4504, '_', globals()['_'])
if '_apply_payment' in globals(): setattr(_rf_snapshot_app_patch_4504, '_apply_payment', globals()['_apply_payment'])
if '_card_details' in globals(): setattr(_rf_snapshot_app_patch_4504, '_card_details', globals()['_card_details'])
if '_clean_voucher' in globals(): setattr(_rf_snapshot_app_patch_4504, '_clean_voucher', globals()['_clean_voucher'])
if '_date' in globals(): setattr(_rf_snapshot_app_patch_4504, '_date', globals()['_date'])
if '_decode_marker' in globals(): setattr(_rf_snapshot_app_patch_4504, '_decode_marker', globals()['_decode_marker'])
if '_encode_marker' in globals(): setattr(_rf_snapshot_app_patch_4504, '_encode_marker', globals()['_encode_marker'])
if '_make_payment_info' in globals(): setattr(_rf_snapshot_app_patch_4504, '_make_payment_info', globals()['_make_payment_info'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4504, '_mod', globals()['_mod'])
if '_money' in globals(): setattr(_rf_snapshot_app_patch_4504, '_money', globals()['_money'])
if '_normalize_method' in globals(): setattr(_rf_snapshot_app_patch_4504, '_normalize_method', globals()['_normalize_method'])
if '_payment_info_from_visits' in globals(): setattr(_rf_snapshot_app_patch_4504, '_payment_info_from_visits', globals()['_payment_info_from_visits'])
if '_payment_label_from_visits' in globals(): setattr(_rf_snapshot_app_patch_4504, '_payment_label_from_visits', globals()['_payment_label_from_visits'])
if '_remove_route' in globals(): setattr(_rf_snapshot_app_patch_4504, '_remove_route', globals()['_remove_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4504, '_seen', globals()['_seen'])
if '_strip_marker' in globals(): setattr(_rf_snapshot_app_patch_4504, '_strip_marker', globals()['_strip_marker'])
if '_update_offline_payload' in globals(): setattr(_rf_snapshot_app_patch_4504, '_update_offline_payload', globals()['_update_offline_payload'])
if '_with_marker' in globals(): setattr(_rf_snapshot_app_patch_4504, '_with_marker', globals()['_with_marker'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4504, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4504, 'app', globals()['app'])
if 'base64' in globals(): setattr(_rf_snapshot_app_patch_4504, 'base64', globals()['base64'])
if 'base_payload' in globals(): setattr(_rf_snapshot_app_patch_4504, 'base_payload', globals()['base_payload'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4504, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4504, 'exc', globals()['exc'])
if 'json' in globals(): setattr(_rf_snapshot_app_patch_4504, 'json', globals()['json'])
if 'legacy' in globals(): setattr(_rf_snapshot_app_patch_4504, 'legacy', globals()['legacy'])
if '_rf_alias_app_patch_4504__previous' in globals(): setattr(_rf_snapshot_app_patch_4504, 'previous', globals()['_rf_alias_app_patch_4504__previous'])
if 'proof_mod' in globals(): setattr(_rf_snapshot_app_patch_4504, 'proof_mod', globals()['proof_mod'])
if 're' in globals(): setattr(_rf_snapshot_app_patch_4504, 're', globals()['re'])
if 'sys' in globals(): setattr(_rf_snapshot_app_patch_4504, 'sys', globals()['sys'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4504, 'uvicorn', globals()['uvicorn'])
if 'v4504_azur_payload_for_group' in globals(): setattr(_rf_snapshot_app_patch_4504, 'v4504_azur_payload_for_group', globals()['v4504_azur_payload_for_group'])
if 'v4504_billing_payment_methods' in globals(): setattr(_rf_snapshot_app_patch_4504, 'v4504_billing_payment_methods', globals()['v4504_billing_payment_methods'])
if 'v4504_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_patch_4504, 'v4504_create_visit_batch_payment', globals()['v4504_create_visit_batch_payment'])
if 'v4504_day_summary' in globals(): setattr(_rf_snapshot_app_patch_4504, 'v4504_day_summary', globals()['v4504_day_summary'])
if 'v4504_health' in globals(): setattr(_rf_snapshot_app_patch_4504, 'v4504_health', globals()['v4504_health'])
if 'v4504_set_billing_payment_method' in globals(): setattr(_rf_snapshot_app_patch_4504, 'v4504_set_billing_payment_method', globals()['v4504_set_billing_payment_method'])
_rf_layers['app_patch_4504'] = _rf_snapshot_app_patch_4504

# ---- app_patch_4505 ----
import os
_rf_alias_app_patch_4505__previous = _rf_layers['app_patch_4504']
core = _rf_alias_app_patch_4505__previous.core
app = _rf_alias_app_patch_4505__previous.app
APP_VERSION = '4.5.5'
_mod = _rf_alias_app_patch_4505__previous
_seen = set()
for _ in range(130):
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
    V4505_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.5"!important;\n  font-size:9px!important;\n  line-height:1!important;\n  font-weight:850!important\n}\n\n/* Forma de pago: más grande y clara */\n.v4504-pay-head b{\n  font-size:14px!important;\n  line-height:1.15!important;\n  letter-spacing:-.01em!important\n}\n.v4504-pay-head small{\n  font-size:9px!important;\n  line-height:1.35!important\n}\n.v4504-pay-state{\n  font-size:9px!important;\n  padding:5px 9px!important\n}\n.v4504-pay-option{\n  min-height:56px!important;\n  padding:9px 10px!important\n}\n.v4504-pay-option>span{\n  font-size:18px!important\n}\n.v4504-pay-option>b{\n  font-size:12px!important;\n  line-height:1.1!important\n}\n.v4504-pay-option>small{\n  font-size:8.5px!important;\n  line-height:1.15!important\n}\n\n/* Tarjeta queda visualmente preparada, pero la operación será del datáfono. */\n.v4504-pay-option[data-mode="TARJETA"]{\n  position:relative!important;\n  border-style:dashed!important;\n  background:#f8fafc!important\n}\n.v4504-pay-option[data-mode="TARJETA"] b{\n  font-size:0!important\n}\n.v4504-pay-option[data-mode="TARJETA"] b::after{\n  content:"Tarjeta";\n  font-size:12px!important;\n  font-weight:900\n}\n.v4504-pay-option[data-mode="TARJETA"] small{\n  font-size:0!important\n}\n.v4504-pay-option[data-mode="TARJETA"] small::after{\n  content:"Con datáfono";\n  font-size:8.5px!important;\n  color:#72859a!important\n}\n#v4504Card{\n  display:none!important\n}\n\n/* Procedimientos y servicios: más compactos que los cobros. */\n.attention-form-modal .service-card[data-service]{\n  min-height:0!important;\n  padding:8px 9px!important;\n  border-radius:10px!important\n}\n.attention-form-modal .service-card[data-service] b,\n.attention-form-modal .service-card[data-service] strong{\n  font-size:9.5px!important;\n  line-height:1.15!important\n}\n.attention-form-modal .service-card[data-service] .service-price{\n  font-size:10px!important;\n  line-height:1.1!important\n}\n.attention-form-modal .service-card[data-service] small,\n.attention-form-modal .service-card[data-service] .muted{\n  font-size:7.5px!important;\n  line-height:1.2!important\n}\n\n/* Facturación: forma de pago también gana jerarquía. */\n.v4504-billpay-head span{\n  font-size:10px!important\n}\n.v4504-billpay-head b{\n  font-size:10.5px!important\n}\n.v4504-billchoices button{\n  font-size:9.5px!important;\n  min-height:31px!important\n}\n\n/* Nota discreta del futuro datáfono. */\n.v4505-dataphone-note{\n  margin-top:8px;\n  padding:8px 10px;\n  border:1px dashed #cbd8e5;\n  border-radius:10px;\n  background:#f9fbfd;\n  color:#61758a;\n  font-size:8.5px;\n  line-height:1.35\n}\n.v4505-dataphone-note b{\n  color:#355a78\n}\n'
    V4505_JS = '\n;(()=>{\n  if(window.__v4505VisualAndDataphone)return;\n  window.__v4505VisualAndDataphone=true;\n  const VERSION=\'4.5.5\';\n\n  function paymentHost(){\n    return document.querySelector(\'.attention-form-modal #v4504Payment\');\n  }\n\n  function paintDataphoneNote(){\n    const host=paymentHost();\n    if(!host)return;\n\n    const card=host.querySelector(\'[data-mode="TARJETA"]\');\n    if(card){\n      card.setAttribute(\'aria-disabled\',\'true\');\n      card.setAttribute(\n        \'title\',\n        \'La tarjeta se habilitará cuando el datáfono esté conectado al programa.\'\n      );\n    }\n\n    let note=host.querySelector(\'.v4505-dataphone-note\');\n    if(!note){\n      note=document.createElement(\'div\');\n      note.className=\'v4505-dataphone-note\';\n      note.innerHTML=\n        \'<b>💳 Datáfono:</b> cuando llegue el equipo, Tarjeta enviará el valor \'\n        +\'directamente al terminal y el programa recibirá aprobación, tipo de \'\n        +\'tarjeta y autorización automáticamente. No tendrás que escribir esos datos.\';\n      host.appendChild(note);\n    }\n  }\n\n  function notifyDataphonePending(){\n    const msg=\n      \'Tarjeta quedará automatizada con el datáfono. \'\n      +\'Para conectarlo necesito el modelo del equipo y el proveedor/adquirente \'\n      +\'cuando lo reciban.\';\n    if(typeof window.rpToast===\'function\'){\n      try{window.rpToast(msg,\'info\');return}catch(_e){}\n    }\n    alert(msg);\n  }\n\n  // Bloquea el flujo manual de tarjeta de v4.5.4.\n  document.addEventListener(\'click\',event=>{\n    // v4.5.24 compatibilidad: Bendo manual reemplazó el flujo automático\n    // planificado en v4.5.5. No interceptar ningún clic cuando el flujo\n    // Bendo actual ya está instalado.\n    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;\n    const card=event.target?.closest?.(\n      \'.attention-form-modal [data-mode="TARJETA"]\'\n    );\n    if(!card)return;\n    event.preventDefault();\n    event.stopPropagation();\n    event.stopImmediatePropagation();\n    notifyDataphonePending();\n  },true);\n\n  // Facturación tampoco permite registrar tarjeta manualmente.\n  document.addEventListener(\'click\',event=>{\n    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;\n    const paymentButton=event.target?.closest?.(\n      \'#billingList .v4504-billchoices [data-bm]\'\n    );\n    if(!paymentButton)return;\n    const method=String(paymentButton.dataset.bm||\'\');\n    if(method!==\'TARJETA_DEBITO\'&&method!==\'TARJETA_CREDITO\')return;\n    event.preventDefault();\n    event.stopPropagation();\n    event.stopImmediatePropagation();\n    notifyDataphonePending();\n  },true);\n\n  // En Pago mixto, por ahora solo Efectivo + Transferencia.\n  document.addEventListener(\'change\',event=>{\n    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;\n    const select=event.target;\n    if(!select?.matches?.(\'#v4504MixA,#v4504MixB\'))return;\n    if(!String(select.value||\'\').startsWith(\'TARJETA_\'))return;\n\n    event.preventDefault();\n    event.stopPropagation();\n    event.stopImmediatePropagation();\n\n    if(select.id===\'v4504MixA\'){\n      select.value=\'EFECTIVO\';\n    }else{\n      select.value=\'TRANSFERENCIA\';\n    }\n    notifyDataphonePending();\n  },true);\n\n  // Filtra visualmente las opciones de tarjeta en mixto sin observers persistentes.\n  function compactMixed(){\n    document.querySelectorAll(\n      \'#v4504MixA option[value^="TARJETA_"],#v4504MixB option[value^="TARJETA_"]\'\n    ).forEach(option=>{\n      option.disabled=true;\n      option.hidden=true;\n    });\n  }\n\n  function refresh(){\n    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;\n    paintDataphoneNote();\n    compactMixed();\n    document.querySelectorAll(\n      \'.v460-version,#currentVersionBadge\'\n    ).forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n\n  const stableAttentionFor=window.attentionFor;\n  if(typeof stableAttentionFor===\'function\'){\n    window.attentionFor=async function(){\n      const result=await stableAttentionFor.apply(this,arguments);\n      if(window.__v4507BendoManual||window.__v4523BendoOperation)return result;\n      setTimeout(refresh,60);\n      return result;\n    };\n  }\n\n  document.addEventListener(\'click\',event=>{\n    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;\n    if(\n      event.target?.closest?.(\n        \'.attention-form-modal .service-card,[data-mode="MIXTO"],[data-mode="EFECTIVO"],[data-mode="TRANSFERENCIA"]\'\n      )\n    ){\n      setTimeout(refresh,60);\n    }\n  },true);\n\n  function boot(){\n    refresh();\n  }\n\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\n      \'DOMContentLoaded\',\n      boot,\n      {once:true}\n    );\n  }else{\n    boot();\n  }\n\n  window.__v4505DataphoneState={\n    automatic:true,\n    connected:false,\n    manualCardEntry:false,\n    needs:[\'modelo del datáfono\',\'proveedor/adquirente\',\'método de integración\']\n  };\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4505_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4505_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4505/dataphone/status')
def v4505_dataphone_status(user=core.Depends(core.current_user)):
    provider = str(os.getenv('RP_DATAPHONE_PROVIDER') or '').strip()
    model = str(os.getenv('RP_DATAPHONE_MODEL') or '').strip()
    return {'ok': True, 'version': APP_VERSION, 'automatic_flow_designed': True, 'connected': False, 'manual_card_entry': False, 'provider': provider or None, 'model': model or None, 'needs_device_details': not bool(provider and model), 'message': 'Compatibilidad v4.5.5: este aviso quedó obsoleto; el flujo vigente es Bendo manual asistido. No se requiere modelo/proveedor para automatización porque no se usa integración automática.'}

@app.get('/api/v4505/health')
def v4505_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'payment_typography_enlarged': True, 'services_typography_compacted': True, 'manual_card_entry_disabled': True, 'dataphone_automatic_flow_planned': True, 'cash_closing': False, 'database_changes': False, 'database_schema_changes': False, 'neon_writes_added': False, 'azur_contract_changes': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4505 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4505, '__name__', 'app_patch_4505')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4505, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4505, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4505, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4505_CSS' in globals(): setattr(_rf_snapshot_app_patch_4505, 'V4505_CSS', globals()['V4505_CSS'])
if 'V4505_JS' in globals(): setattr(_rf_snapshot_app_patch_4505, 'V4505_JS', globals()['V4505_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4505, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4505, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4505, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4505, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4505, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4505, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4505, 'exc', globals()['exc'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4505, 'os', globals()['os'])
if '_rf_alias_app_patch_4505__previous' in globals(): setattr(_rf_snapshot_app_patch_4505, 'previous', globals()['_rf_alias_app_patch_4505__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4505, 'uvicorn', globals()['uvicorn'])
if 'v4505_dataphone_status' in globals(): setattr(_rf_snapshot_app_patch_4505, 'v4505_dataphone_status', globals()['v4505_dataphone_status'])
if 'v4505_health' in globals(): setattr(_rf_snapshot_app_patch_4505, 'v4505_health', globals()['v4505_health'])
_rf_layers['app_patch_4505'] = _rf_snapshot_app_patch_4505

# ---- app_patch_4506 ----
import json
import os
import urllib.error
import urllib.parse
import urllib.request
_rf_alias_app_patch_4506__previous = _rf_layers['app_patch_4505']
core = _rf_alias_app_patch_4506__previous.core
app = _rf_alias_app_patch_4506__previous.app
APP_VERSION = '4.5.6'
_mod = _rf_alias_app_patch_4506__previous
_seen = set()
for _ in range(140):
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
DP_ENV = {'provider': 'RP_DATAPHONE_PROVIDER', 'model': 'RP_DATAPHONE_MODEL', 'environment': 'RP_DATAPHONE_ENVIRONMENT', 'api_base_url': 'RP_DATAPHONE_API_BASE_URL', 'api_key': 'RP_DATAPHONE_API_KEY', 'merchant_id': 'RP_DATAPHONE_MERCHANT_ID', 'terminal_id': 'RP_DATAPHONE_TERMINAL_ID', 'auth_header': 'RP_DATAPHONE_AUTH_HEADER', 'auth_scheme': 'RP_DATAPHONE_AUTH_SCHEME', 'health_path': 'RP_DATAPHONE_HEALTH_PATH', 'create_payment_path': 'RP_DATAPHONE_CREATE_PAYMENT_PATH', 'status_path_template': 'RP_DATAPHONE_STATUS_PATH_TEMPLATE', 'create_body_template': 'RP_DATAPHONE_CREATE_BODY_TEMPLATE', 'response_id_field': 'RP_DATAPHONE_RESPONSE_ID_FIELD', 'response_status_field': 'RP_DATAPHONE_RESPONSE_STATUS_FIELD', 'approved_values': 'RP_DATAPHONE_APPROVED_VALUES', 'declined_values': 'RP_DATAPHONE_DECLINED_VALUES', 'webhook_public_url': 'RP_DATAPHONE_WEBHOOK_PUBLIC_URL', 'webhook_secret': 'RP_DATAPHONE_WEBHOOK_SECRET'}
DEFAULTS = {'provider': 'BENDO', 'model': 'Bendo Smart', 'environment': 'PRODUCCION', 'api_base_url': '', 'api_key': '', 'merchant_id': '', 'terminal_id': '', 'auth_header': 'Authorization', 'auth_scheme': 'Bearer', 'health_path': '', 'create_payment_path': '', 'status_path_template': '', 'create_body_template': '{"amount":"{amount}","currency":"USD","reference":"{reference}","merchant_id":"{merchant_id}","terminal_id":"{terminal_id}"}', 'response_id_field': 'id', 'response_status_field': 'status', 'approved_values': 'APPROVED,COMPLETED,SUCCESS', 'declined_values': 'DECLINED,FAILED,REJECTED,CANCELLED', 'webhook_public_url': '', 'webhook_secret': ''}

class V4506DataphoneConfigIn(core.BaseModel):
    provider: str = 'BENDO'
    model: str = 'Bendo Smart'
    environment: str = 'PRODUCCION'
    api_base_url: str = ''
    api_key: str | None = None
    merchant_id: str = ''
    terminal_id: str = ''
    auth_header: str = 'Authorization'
    auth_scheme: str = 'Bearer'
    health_path: str = ''
    create_payment_path: str = ''
    status_path_template: str = ''
    create_body_template: str = DEFAULTS['create_body_template']
    response_id_field: str = 'id'
    response_status_field: str = 'status'
    approved_values: str = DEFAULTS['approved_values']
    declined_values: str = DEFAULTS['declined_values']
    webhook_public_url: str = ''
    webhook_secret: str | None = None

def _dp_value(name: str) -> str:
    env = DP_ENV[name]
    raw = str(os.getenv(env) or '').strip()
    if raw:
        return raw
    return str(DEFAULTS.get(name, '') or '')

def _dp_mask(value: str) -> str:
    raw = str(value or '')
    if not raw:
        return ''
    if len(raw) <= 6:
        return '•' * len(raw)
    return raw[:3] + '•' * max(4, len(raw) - 6) + raw[-3:]

def _dp_clean_url(value: object, *, allow_blank: bool=True) -> str:
    raw = str(value or '').strip().rstrip('/')
    if not raw and allow_blank:
        return ''
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        raise core.HTTPException(400, 'La URL de la API no es válida.')
    if parsed.scheme.lower() != 'https' or not parsed.netloc:
        raise core.HTTPException(400, 'La API del datáfono debe usar una dirección HTTPS válida.')
    return raw

def _dp_path(value: object, *, allow_template: bool=False) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    if raw.startswith('http://') or raw.startswith('https://'):
        raise core.HTTPException(400, 'En las rutas escribe solo /ruta; la URL base se configura aparte.')
    if not raw.startswith('/'):
        raw = '/' + raw
    if len(raw) > 500:
        raise core.HTTPException(400, 'La ruta es demasiado larga.')
    if not allow_template and '{' in raw:
        raise core.HTTPException(400, 'Esta ruta no admite variables.')
    return raw

def _dp_payload() -> dict:
    api_key = _dp_value('api_key')
    webhook_secret = _dp_value('webhook_secret')
    base_url = _dp_value('api_base_url')
    create_path = _dp_value('create_payment_path')
    status_path = _dp_value('status_path_template')
    merchant = _dp_value('merchant_id')
    terminal = _dp_value('terminal_id')
    credentials_ready = bool(base_url and api_key)
    identity_ready = bool(merchant or terminal)
    contract_ready = bool(create_path and status_path)
    return {'provider': _dp_value('provider') or 'BENDO', 'model': _dp_value('model') or 'Bendo Smart', 'environment': _dp_value('environment') or 'PRODUCCION', 'api_base_url': base_url, 'api_key_saved': bool(api_key), 'api_key_masked': _dp_mask(api_key), 'merchant_id': merchant, 'terminal_id': terminal, 'auth_header': _dp_value('auth_header') or 'Authorization', 'auth_scheme': _dp_value('auth_scheme') or 'Bearer', 'health_path': _dp_value('health_path'), 'create_payment_path': create_path, 'status_path_template': status_path, 'create_body_template': _dp_value('create_body_template'), 'response_id_field': _dp_value('response_id_field') or 'id', 'response_status_field': _dp_value('response_status_field') or 'status', 'approved_values': _dp_value('approved_values'), 'declined_values': _dp_value('declined_values'), 'webhook_public_url': _dp_value('webhook_public_url'), 'webhook_secret_saved': bool(webhook_secret), 'webhook_secret_masked': _dp_mask(webhook_secret), 'credentials_ready': credentials_ready, 'identity_ready': identity_ready, 'contract_ready': contract_ready, 'automatic_charge_ready': bool(credentials_ready and identity_ready and contract_ready), 'card_manual_entry': False, 'public_docs_confirm_terminal_push': False, 'official_api_notification_expected': True, 'requires_official_contract': not contract_ready, 'schema_version': 1}

def _dp_headers() -> dict:
    headers = {'Accept': 'application/json', 'User-Agent': f'Recepcion-Dr-Revelo/{APP_VERSION}', 'Cache-Control': 'no-cache'}
    key = _dp_value('api_key')
    if key:
        header = _dp_value('auth_header') or 'Authorization'
        scheme = _dp_value('auth_scheme')
        headers[header] = (scheme + ' ' + key).strip() if scheme else key
    merchant = _dp_value('merchant_id')
    terminal = _dp_value('terminal_id')
    if merchant:
        headers['X-Merchant-Id'] = merchant
    if terminal:
        headers['X-Terminal-Id'] = terminal
    return headers

def _dp_render_template(template: str, *, amount: float, reference: str) -> dict:
    raw = str(template or DEFAULTS['create_body_template'])
    replacements = {'{amount}': f'{float(amount):.2f}', '{reference}': str(reference or ''), '{merchant_id}': _dp_value('merchant_id'), '{terminal_id}': _dp_value('terminal_id')}
    for key, value in replacements.items():
        raw = raw.replace(key, value)
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise core.HTTPException(400, 'La plantilla JSON de creación no es válida: ' + str(exc))
    if not isinstance(data, dict):
        raise core.HTTPException(400, 'La plantilla de creación debe ser un objeto JSON.')
    return data
try:

    @app.get('/api/v4506/dataphone/config')
    def v4506_dataphone_config(request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Configuración disponible solo en esta PC.')
        return {'ok': True, **_dp_payload()}

    @app.post('/api/v4506/dataphone/config')
    def v4506_save_dataphone_config(data: V4506DataphoneConfigIn, request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Configuración disponible solo en esta PC.')
        provider = ' '.join(str(data.provider or 'BENDO').strip().upper().split())
        model = ' '.join(str(data.model or 'Bendo Smart').strip().split())
        environment = ' '.join(str(data.environment or 'PRODUCCION').strip().upper().split())
        if environment not in {'PRODUCCION', 'SANDBOX', 'PRUEBAS'}:
            raise core.HTTPException(400, 'Entorno inválido.')
        base_url = _dp_clean_url(data.api_base_url)
        health_path = _dp_path(data.health_path)
        create_path = _dp_path(data.create_payment_path)
        status_path = _dp_path(data.status_path_template, allow_template=True)
        auth_header = str(data.auth_header or 'Authorization').strip()
        auth_scheme = str(data.auth_scheme or 'Bearer').strip()
        merchant_id = str(data.merchant_id or '').strip()
        terminal_id = str(data.terminal_id or '').strip()
        webhook_url = _dp_clean_url(data.webhook_public_url, allow_blank=True)
        template = str(data.create_body_template or DEFAULTS['create_body_template']).strip()
        _dp_render_template(template, amount=40.0, reference='TEST-CONFIG')
        values = {DP_ENV['provider']: provider, DP_ENV['model']: model, DP_ENV['environment']: environment, DP_ENV['api_base_url']: base_url, DP_ENV['merchant_id']: merchant_id, DP_ENV['terminal_id']: terminal_id, DP_ENV['auth_header']: auth_header, DP_ENV['auth_scheme']: auth_scheme, DP_ENV['health_path']: health_path, DP_ENV['create_payment_path']: create_path, DP_ENV['status_path_template']: status_path, DP_ENV['create_body_template']: template, DP_ENV['response_id_field']: str(data.response_id_field or 'id').strip(), DP_ENV['response_status_field']: str(data.response_status_field or 'status').strip(), DP_ENV['approved_values']: str(data.approved_values or DEFAULTS['approved_values']).strip(), DP_ENV['declined_values']: str(data.declined_values or DEFAULTS['declined_values']).strip(), DP_ENV['webhook_public_url']: webhook_url}
        new_key = str(data.api_key or '').strip()
        if new_key:
            values[DP_ENV['api_key']] = new_key
        new_webhook_secret = str(data.webhook_secret or '').strip()
        if new_webhook_secret:
            values[DP_ENV['webhook_secret']] = new_webhook_secret
        core._upsert_local_env(values)
        for env_name, value in values.items():
            os.environ[env_name] = value
        return {'ok': True, 'message': 'Configuración del datáfono guardada en esta PC.', **_dp_payload()}

    @app.post('/api/v4506/dataphone/validate')
    def v4506_validate_dataphone(request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Disponible solo en esta PC.')
        cfg = _dp_payload()
        checks = [{'key': 'device', 'ok': bool(cfg['model']), 'label': 'Equipo', 'detail': cfg['model'] or 'Falta modelo'}, {'key': 'api', 'ok': bool(cfg['api_base_url'] and cfg['api_key_saved']), 'label': 'Credenciales API', 'detail': 'Guardadas' if cfg['api_base_url'] and cfg['api_key_saved'] else 'Pendientes de Bendo'}, {'key': 'identity', 'ok': bool(cfg['merchant_id'] or cfg['terminal_id']), 'label': 'Comercio / terminal', 'detail': 'Identificado' if cfg['merchant_id'] or cfg['terminal_id'] else 'Pendiente de vinculación'}, {'key': 'contract', 'ok': bool(cfg['create_payment_path'] and cfg['status_path_template']), 'label': 'Contrato de cobro automático', 'detail': 'Rutas configuradas' if cfg['create_payment_path'] and cfg['status_path_template'] else 'Pendiente de documentación oficial'}]
        return {'ok': True, 'ready': all((x['ok'] for x in checks)), 'checks': checks, 'message': 'Todo listo para activar el cobro automático.' if all((x['ok'] for x in checks)) else 'La estructura está preparada; faltan datos oficiales del terminal/API.'}

    @app.post('/api/v4506/dataphone/test')
    def v4506_test_dataphone(request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Disponible solo en esta PC.')
        base = _dp_value('api_base_url')
        key = _dp_value('api_key')
        health = _dp_value('health_path')
        if not base or not key:
            raise core.HTTPException(400, 'Primero guarda la URL y credencial API entregadas por Bendo.')
        if not health:
            return {'ok': True, 'authenticated': False, 'network_tested': False, 'message': 'Credenciales guardadas. Falta la ruta oficial de prueba/estado para comprobar la API sin generar un cobro.'}
        url = base.rstrip('/') + '/' + health.lstrip('/')
        req = urllib.request.Request(url, headers=_dp_headers(), method='GET')
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                code = int(getattr(response, 'status', 200) or 200)
                response.read(64000)
            return {'ok': 200 <= code < 300, 'authenticated': 200 <= code < 300, 'network_tested': True, 'http_status': code, 'message': 'Bendo respondió correctamente. No se generó ningún cobro.'}
        except urllib.error.HTTPError as exc:
            raise core.HTTPException(502, 'Bendo respondió HTTP ' + str(exc.code) + '. Revisa credenciales o la ruta de prueba.')
        except Exception as exc:
            raise core.HTTPException(502, 'No se pudo comprobar la API: ' + str(exc)[:180])

    @app.post('/api/v4506/dataphone/payment-preview')
    def v4506_dataphone_payment_preview(amount: float, reference: str, request: core.Request, user=core.Depends(core.current_user)):
        if not core._is_loopback_client(request):
            raise core.HTTPException(403, 'Disponible solo en esta PC.')
        if amount <= 0:
            raise core.HTTPException(400, 'El valor debe ser mayor a cero.')
        body = _dp_render_template(_dp_value('create_body_template'), amount=amount, reference=reference)
        return {'ok': True, 'sent': False, 'amount': round(float(amount), 2), 'reference': str(reference or ''), 'endpoint': _dp_value('api_base_url').rstrip('/') + '/' + _dp_value('create_payment_path').lstrip('/') if _dp_value('api_base_url') and _dp_value('create_payment_path') else None, 'body_preview': body, 'message': 'Vista previa solamente. No se envió ningún cobro al datáfono.'}
    V4506_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.6"!important;\n  font-size:9px!important;\n  line-height:1!important;\n  font-weight:850!important\n}\n\n/* Corrige la Consulta: v4.5.5 había compactado TODAS las service-card. */\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"],\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"]{\n  min-height:64px!important;\n  height:auto!important;\n  padding:12px 40px!important;\n  border-radius:13px!important;\n  display:flex!important;\n  align-items:center!important\n}\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] b,\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] strong,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] b,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] strong{\n  font-size:12px!important;\n  line-height:1.15!important\n}\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] .service-price,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] .service-price{\n  font-size:11px!important\n}\n\n/* Solo los procedimientos quedan compactos. */\n.attention-form-modal .procedures-service-section .service-card[data-service]{\n  min-height:48px!important;\n  padding:7px 8px!important;\n  border-radius:9px!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service] b,\n.attention-form-modal .procedures-service-section .service-card[data-service] strong{\n  font-size:9px!important;\n  line-height:1.1!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service] .service-price{\n  font-size:9px!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service] small{\n  font-size:7px!important\n}\n\n/* Forma de pago: prioridad visual mayor. */\n.v4504-pay{\n  padding:14px!important\n}\n.v4504-pay-head b{\n  font-size:16px!important\n}\n.v4504-pay-head small{\n  font-size:9.5px!important\n}\n.v4504-pay-option{\n  min-height:61px!important;\n  padding:10px 11px!important\n}\n.v4504-pay-option>span{\n  font-size:20px!important\n}\n.v4504-pay-option>b,\n.v4504-pay-option[data-mode="TARJETA"] b::after{\n  font-size:13px!important\n}\n.v4504-pay-option>small,\n.v4504-pay-option[data-mode="TARJETA"] small::after{\n  font-size:9px!important\n}\n\n/* Configuración Bendo Smart */\n.v4506-dp-section{\n  max-width:980px!important\n}\n.v4506-dp-hero{\n  display:grid;\n  grid-template-columns:minmax(0,1fr) auto;\n  gap:16px;\n  align-items:center;\n  padding:16px 17px;\n  border:1px solid #d9e4ef;\n  border-radius:15px;\n  background:linear-gradient(135deg,#f7fbff 0%,#eef6ff 100%);\n  margin-bottom:12px\n}\n.v4506-dp-hero h3{\n  margin:0 0 4px;\n  font-size:18px;\n  color:#223d5a\n}\n.v4506-dp-hero p{\n  margin:0;\n  color:#647991;\n  font-size:11px;\n  line-height:1.4\n}\n.v4506-dp-pill{\n  padding:6px 10px;\n  border-radius:999px;\n  font-size:9px;\n  font-weight:900;\n  background:#fff3d6;\n  color:#8a6012;\n  border:1px solid #ead49f;\n  white-space:nowrap\n}\n.v4506-dp-pill.ready{\n  background:#e7f7ed;\n  color:#216943;\n  border-color:#b9dfc6\n}\n.v4506-dp-grid{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:10px\n}\n.v4506-dp-card{\n  border:1px solid #dfe7ef;\n  border-radius:13px;\n  background:#fff;\n  padding:13px 14px\n}\n.v4506-dp-card.full{\n  grid-column:1/-1\n}\n.v4506-dp-card h4{\n  margin:0 0 3px;\n  color:#304c69;\n  font-size:13px\n}\n.v4506-dp-card>p{\n  margin:0 0 10px;\n  color:#75879a;\n  font-size:9px;\n  line-height:1.35\n}\n.v4506-dp-fields{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:9px\n}\n.v4506-dp-field{\n  min-width:0\n}\n.v4506-dp-field.full{\n  grid-column:1/-1\n}\n.v4506-dp-field label{\n  display:block;\n  margin:0 0 4px;\n  color:#6e8094;\n  font-size:8px;\n  font-weight:900;\n  text-transform:uppercase;\n  letter-spacing:.04em\n}\n.v4506-dp-field input,\n.v4506-dp-field select,\n.v4506-dp-field textarea{\n  width:100%!important;\n  min-height:35px!important;\n  font-size:10px!important;\n  border-radius:9px!important\n}\n.v4506-dp-field textarea{\n  min-height:80px!important;\n  font-family:Consolas,monospace!important;\n  resize:vertical\n}\n.v4506-dp-actions{\n  display:flex;\n  gap:7px;\n  flex-wrap:wrap;\n  margin-top:11px\n}\n.v4506-dp-actions button{\n  min-height:34px!important;\n  border-radius:9px!important\n}\n.v4506-dp-checks{\n  display:grid;\n  grid-template-columns:repeat(4,minmax(0,1fr));\n  gap:7px\n}\n.v4506-dp-check{\n  padding:9px 10px;\n  border:1px solid #e1e7ee;\n  border-radius:10px;\n  background:#fbfcfe\n}\n.v4506-dp-check b{\n  display:block;\n  font-size:9px;\n  color:#3f5972\n}\n.v4506-dp-check small{\n  display:block;\n  margin-top:3px;\n  font-size:8px;\n  color:#7a8b9e;\n  line-height:1.25\n}\n.v4506-dp-check.ok{\n  border-color:#bfe0ca;\n  background:#f2faf5\n}\n.v4506-dp-check.ok b{\n  color:#276846\n}\n.v4506-dp-info{\n  margin-top:10px;\n  padding:9px 11px;\n  border-radius:10px;\n  background:#f4f7fa;\n  color:#5f7388;\n  font-size:9px;\n  line-height:1.4\n}\n.v4506-dp-info strong{\n  color:#34546f\n}\n.v4506-dp-status{\n  margin-top:9px;\n  min-height:18px;\n  font-size:9px;\n  color:#63788f\n}\n.v4506-dp-status.ok{color:#2c744e}\n.v4506-dp-status.err{color:#a4413b}\n@media(max-width:780px){\n  .v4506-dp-grid,.v4506-dp-fields{grid-template-columns:1fr}\n  .v4506-dp-checks{grid-template-columns:repeat(2,minmax(0,1fr))}\n  .v4506-dp-hero{grid-template-columns:1fr}\n}\n'
    V4506_JS = '\n;(()=>{\n  if(window.__v4506DataphoneConfig)return;\n  window.__v4506DataphoneConfig=true;\n  const VERSION=\'4.5.6\';\n  const q=(s,r=document)=>r.querySelector(s);\n  const qa=(s,r=document)=>[...r.querySelectorAll(s)];\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\n    \'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'\n  }[c]));\n\n  async function call(url,opt={}){\n    if(typeof window.api===\'function\')return window.api(url,opt);\n    const response=await fetch(url,{\n      headers:{\'Content-Type\':\'application/json\',...(opt.headers||{})},\n      ...opt\n    });\n    const data=await response.json().catch(()=>({}));\n    if(!response.ok)throw Error(data.detail||data.message||\'Error\');\n    return data;\n  }\n\n  function ensureTab(){\n    const config=q(\'#config\');\n    const tabs=q(\'.config-tabs\',config);\n    if(!config||!tabs)return null;\n\n    let section=q(\'[data-config-section="dataphone"]\',config);\n    if(!section){\n      section=document.createElement(\'div\');\n      section.dataset.configSection=\'dataphone\';\n      section.className=\'config-section hidden v4506-dp-section\';\n      const fact=q(\'[data-config-section="facturacion"]\',config);\n      (fact||config.lastElementChild)?.after?.(section);\n      if(!section.parentElement)config.appendChild(section);\n    }\n\n    let button=q(\'[data-config-tab="dataphone"]\',tabs);\n    if(!button){\n      button=document.createElement(\'button\');\n      button.type=\'button\';\n      button.dataset.configTab=\'dataphone\';\n      button.textContent=\'Datáfono\';\n      const factButton=q(\'[data-config-tab="facturacion"]\',tabs);\n      factButton?.after(button)||tabs.appendChild(button);\n      button.onclick=()=>{\n        window.showConfigTab?.(\'dataphone\',button);\n        loadConfig();\n      };\n    }\n    return section;\n  }\n\n  function field(id,label,value=\'\',type=\'text\',extra=\'\'){\n    return \'<div class="v4506-dp-field \'+(extra.includes(\'full\')?\'full\':\'\')+\'">\'\n      +\'<label for="\'+id+\'">\'+label+\'</label>\'\n      +\'<input id="\'+id+\'" type="\'+type+\'" value="\'+esc(value)+\'" \'+extra.replace(\'full\',\'\')+\'>\'\n      +\'</div>\';\n  }\n\n  function render(data){\n    const section=ensureTab();\n    if(!section)return;\n\n    const ready=!!data.automatic_charge_ready;\n    section.innerHTML=\n      \'<div class="v4506-dp-hero">\'\n      +\'<div><h3>💳 Bendo Smart</h3>\'\n      +\'<p>Integración preparada para que Recepción envíe el valor al datáfono y reciba el resultado automáticamente cuando Bendo entregue el contrato técnico y credenciales.</p></div>\'\n      +\'<span class="v4506-dp-pill \'+(ready?\'ready\':\'\')+\'">\'\n      +(ready?\'LISTO PARA ACTIVAR\':\'ESPERANDO DATOS DE BENDO\')\n      +\'</span></div>\'\n\n      +\'<div id="v4506DpChecks" class="v4506-dp-checks"></div>\'\n\n      +\'<div class="v4506-dp-grid" style="margin-top:10px">\'\n      +\'<section class="v4506-dp-card"><h4>Equipo y comercio</h4>\'\n      +\'<p>Estos datos identifican el terminal físico y la cuenta de Bendo.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpProvider\',\'Proveedor\',data.provider||\'BENDO\',\'text\',\'readonly\')\n      +field(\'dpModel\',\'Modelo\',data.model||\'Bendo Smart\')\n      +\'<div class="v4506-dp-field"><label>Entorno</label><select id="dpEnvironment">\'\n      +\'<option value="PRODUCCION" \'+(data.environment===\'PRODUCCION\'?\'selected\':\'\')+\'>Producción</option>\'\n      +\'<option value="SANDBOX" \'+(data.environment===\'SANDBOX\'?\'selected\':\'\')+\'>Sandbox</option>\'\n      +\'<option value="PRUEBAS" \'+(data.environment===\'PRUEBAS\'?\'selected\':\'\')+\'>Pruebas</option>\'\n      +\'</select></div>\'\n      +field(\'dpMerchant\',\'Merchant / comercio ID\',data.merchant_id||\'\')\n      +field(\'dpTerminal\',\'Terminal ID\',data.terminal_id||\'\')\n      +\'</div></section>\'\n\n      +\'<section class="v4506-dp-card"><h4>Credenciales API</h4>\'\n      +\'<p>Se guardan únicamente en el .env local de esta PC; nunca en Neon ni GitHub.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpBaseUrl\',\'API base URL\',data.api_base_url||\'\',\'url\',\'full placeholder="https://..."\')\n      +field(\'dpApiKey\',\'API key / token\',\'\',\'password\',\'placeholder="\'+(data.api_key_saved?\'Ya guardada · deja vacío para conservarla\':\'Pendiente\')+\'"\')\n      +field(\'dpAuthHeader\',\'Header\',data.auth_header||\'Authorization\')\n      +field(\'dpAuthScheme\',\'Esquema\',data.auth_scheme||\'Bearer\')\n      +field(\'dpHealthPath\',\'Ruta de prueba\',data.health_path||\'\',\'text\',\'full placeholder="/health o ruta oficial equivalente"\')\n      +\'</div></section>\'\n\n      +\'<section class="v4506-dp-card full"><h4>Contrato de cobro automático</h4>\'\n      +\'<p>Dejé la capa lista sin inventar rutas. Aquí solo se copian las rutas que Bendo entregue oficialmente.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpCreatePath\',\'Crear cobro\',data.create_payment_path||\'\',\'text\',\'placeholder="/..."\')\n      +field(\'dpStatusPath\',\'Consultar estado\',data.status_path_template||\'\',\'text\',\'placeholder="/payments/{transaction_id}"\')\n      +field(\'dpResponseId\',\'Campo ID respuesta\',data.response_id_field||\'id\')\n      +field(\'dpResponseStatus\',\'Campo estado respuesta\',data.response_status_field||\'status\')\n      +field(\'dpApproved\',\'Estados aprobados\',data.approved_values||\'APPROVED,COMPLETED,SUCCESS\')\n      +field(\'dpDeclined\',\'Estados rechazados\',data.declined_values||\'DECLINED,FAILED,REJECTED,CANCELLED\')\n      +\'<div class="v4506-dp-field full"><label>Plantilla JSON para crear cobro</label>\'\n      +\'<textarea id="dpBodyTemplate">\'+esc(data.create_body_template||\'\')+\'</textarea></div>\'\n      +\'</div></section>\'\n\n      +\'<section class="v4506-dp-card full"><h4>Notificación / webhook</h4>\'\n      +\'<p>Bendo establece la API como medio oficial de notificación de transacciones exitosas. Dejamos también preparado este bloque por si el contrato técnico usa webhook.</p>\'\n      +\'<div class="v4506-dp-fields">\'\n      +field(\'dpWebhookUrl\',\'URL pública de callback\',data.webhook_public_url||\'\',\'url\',\'placeholder="https://..."\')\n      +field(\'dpWebhookSecret\',\'Webhook secret\',\'\',\'password\',\'placeholder="\'+(data.webhook_secret_saved?\'Ya guardado · deja vacío para conservarlo\':\'Pendiente\')+\'"\')\n      +\'</div></section>\'\n      +\'</div>\'\n\n      +\'<div class="v4506-dp-actions">\'\n      +\'<button id="dpSave" type="button" class="primary">Guardar configuración</button>\'\n      +\'<button id="dpValidate" type="button">✓ Validar estructura</button>\'\n      +\'<button id="dpTest" type="button">↻ Probar API sin cobrar</button>\'\n      +\'</div>\'\n      +\'<div class="v4506-dp-info">\'\n      +\'<strong>Automatización prevista:</strong> Recepción calcula el total → envía el cobro → Bendo Smart procesa la tarjeta → la API confirma el resultado → Recepción registra Débito/Crédito, autorización y estado. \'\n      +\'No se guardará número de tarjeta ni CVV.\'\n      +\'</div>\'\n      +\'<div id="dpStatus" class="v4506-dp-status"></div>\';\n\n    q(\'#dpSave\',section)?.addEventListener(\'click\',saveConfig);\n    q(\'#dpValidate\',section)?.addEventListener(\'click\',validateConfig);\n    q(\'#dpTest\',section)?.addEventListener(\'click\',testApi);\n    validateConfig(false);\n  }\n\n  function payload(){\n    return {\n      provider:q(\'#dpProvider\')?.value||\'BENDO\',\n      model:q(\'#dpModel\')?.value||\'Bendo Smart\',\n      environment:q(\'#dpEnvironment\')?.value||\'PRODUCCION\',\n      api_base_url:q(\'#dpBaseUrl\')?.value||\'\',\n      api_key:q(\'#dpApiKey\')?.value||\'\',\n      merchant_id:q(\'#dpMerchant\')?.value||\'\',\n      terminal_id:q(\'#dpTerminal\')?.value||\'\',\n      auth_header:q(\'#dpAuthHeader\')?.value||\'Authorization\',\n      auth_scheme:q(\'#dpAuthScheme\')?.value||\'Bearer\',\n      health_path:q(\'#dpHealthPath\')?.value||\'\',\n      create_payment_path:q(\'#dpCreatePath\')?.value||\'\',\n      status_path_template:q(\'#dpStatusPath\')?.value||\'\',\n      create_body_template:q(\'#dpBodyTemplate\')?.value||\'\',\n      response_id_field:q(\'#dpResponseId\')?.value||\'id\',\n      response_status_field:q(\'#dpResponseStatus\')?.value||\'status\',\n      approved_values:q(\'#dpApproved\')?.value||\'\',\n      declined_values:q(\'#dpDeclined\')?.value||\'\',\n      webhook_public_url:q(\'#dpWebhookUrl\')?.value||\'\',\n      webhook_secret:q(\'#dpWebhookSecret\')?.value||\'\'\n    };\n  }\n\n  function status(text,tone=\'\'){\n    const el=q(\'#dpStatus\');\n    if(!el)return;\n    el.className=\'v4506-dp-status \'+tone;\n    el.textContent=text||\'\';\n  }\n\n  async function loadConfig(){\n    try{\n      const data=await call(\'/api/v4506/dataphone/config\');\n      render(data);\n    }catch(error){\n      status(error?.message||String(error),\'err\');\n    }\n  }\n\n  async function saveConfig(){\n    const button=q(\'#dpSave\');\n    try{\n      if(button){button.disabled=true;button.textContent=\'Guardando…\'}\n      const data=await call(\'/api/v4506/dataphone/config\',{\n        method:\'POST\',\n        body:JSON.stringify(payload())\n      });\n      render(data);\n      status(\'✓ Configuración guardada.\',\'ok\');\n    }catch(error){\n      status(error?.message||String(error),\'err\');\n    }finally{\n      if(button){button.disabled=false;button.textContent=\'Guardar configuración\'}\n    }\n  }\n\n  async function validateConfig(showMessage=true){\n    try{\n      const data=await call(\'/api/v4506/dataphone/validate\',{method:\'POST\',body:\'{}\'});\n      const host=q(\'#v4506DpChecks\');\n      if(host){\n        host.innerHTML=(data.checks||[]).map(item=>\n          \'<div class="v4506-dp-check \'+(item.ok?\'ok\':\'\')+\'">\'\n          +\'<b>\'+(item.ok?\'✓ \':\'○ \')+esc(item.label)+\'</b>\'\n          +\'<small>\'+esc(item.detail)+\'</small></div>\'\n        ).join(\'\');\n      }\n      if(showMessage)status(data.message||\'\',data.ready?\'ok\':\'\');\n    }catch(error){\n      if(showMessage)status(error?.message||String(error),\'err\');\n    }\n  }\n\n  async function testApi(){\n    const button=q(\'#dpTest\');\n    try{\n      if(button){button.disabled=true;button.textContent=\'Probando…\'}\n      const data=await call(\'/api/v4506/dataphone/test\',{method:\'POST\',body:\'{}\'});\n      status(data.message||\'Prueba completada.\',data.ok?\'ok\':\'\');\n    }catch(error){\n      status(error?.message||String(error),\'err\');\n    }finally{\n      if(button){button.disabled=false;button.textContent=\'↻ Probar API sin cobrar\'}\n    }\n  }\n\n  function fixConsultation(){\n    const consult=q(\n      \'.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"],\'\n      +\'.attention-form-modal .consultation-service-section .service-card[data-service="consulta"]\'\n    );\n    if(consult){\n      consult.style.removeProperty(\'min-height\');\n      consult.style.removeProperty(\'height\');\n    }\n  }\n\n  function boot(){\n    qa(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n    ensureTab();\n    fixConsultation();\n  }\n\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  }else{\n    boot();\n  }\n  setTimeout(boot,220);\n  setTimeout(boot,650);\n\n  document.addEventListener(\'click\',event=>{\n    if(event.target?.closest?.(\'.attention-form-modal\')){\n      setTimeout(fixConsultation,25);\n      setTimeout(fixConsultation,140);\n    }\n  },true);\n\n  window.loadDataphoneConfig=loadConfig;\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4506_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4506_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4506/health')
def v4506_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'consultation_card_restored': True, 'procedures_compact': True, 'payment_typography_enlarged': True, 'dataphone_provider': 'BENDO', 'dataphone_model': 'Bendo Smart', 'dataphone_config_tab': True, 'dataphone_test_without_charge': True, 'dataphone_api_contract_not_invented': True, 'manual_card_entry': False, 'database_changes': False, 'database_schema_changes': False, 'neon_writes_added': False, 'azur_contract_changes': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4506 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4506, '__name__', 'app_patch_4506')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4506, 'APP_VERSION', globals()['APP_VERSION'])
if 'DEFAULTS' in globals(): setattr(_rf_snapshot_app_patch_4506, 'DEFAULTS', globals()['DEFAULTS'])
if 'DP_ENV' in globals(): setattr(_rf_snapshot_app_patch_4506, 'DP_ENV', globals()['DP_ENV'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4506, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4506, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4506DataphoneConfigIn' in globals(): setattr(_rf_snapshot_app_patch_4506, 'V4506DataphoneConfigIn', globals()['V4506DataphoneConfigIn'])
if 'V4506_CSS' in globals(): setattr(_rf_snapshot_app_patch_4506, 'V4506_CSS', globals()['V4506_CSS'])
if 'V4506_JS' in globals(): setattr(_rf_snapshot_app_patch_4506, 'V4506_JS', globals()['V4506_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4506, '_', globals()['_'])
if '_dp_clean_url' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_clean_url', globals()['_dp_clean_url'])
if '_dp_headers' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_headers', globals()['_dp_headers'])
if '_dp_mask' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_mask', globals()['_dp_mask'])
if '_dp_path' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_path', globals()['_dp_path'])
if '_dp_payload' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_payload', globals()['_dp_payload'])
if '_dp_render_template' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_render_template', globals()['_dp_render_template'])
if '_dp_value' in globals(): setattr(_rf_snapshot_app_patch_4506, '_dp_value', globals()['_dp_value'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4506, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4506, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4506, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4506, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4506, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4506, 'exc', globals()['exc'])
if 'json' in globals(): setattr(_rf_snapshot_app_patch_4506, 'json', globals()['json'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4506, 'os', globals()['os'])
if '_rf_alias_app_patch_4506__previous' in globals(): setattr(_rf_snapshot_app_patch_4506, 'previous', globals()['_rf_alias_app_patch_4506__previous'])
if 'urllib' in globals(): setattr(_rf_snapshot_app_patch_4506, 'urllib', globals()['urllib'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4506, 'uvicorn', globals()['uvicorn'])
if 'v4506_dataphone_config' in globals(): setattr(_rf_snapshot_app_patch_4506, 'v4506_dataphone_config', globals()['v4506_dataphone_config'])
if 'v4506_dataphone_payment_preview' in globals(): setattr(_rf_snapshot_app_patch_4506, 'v4506_dataphone_payment_preview', globals()['v4506_dataphone_payment_preview'])
if 'v4506_health' in globals(): setattr(_rf_snapshot_app_patch_4506, 'v4506_health', globals()['v4506_health'])
if 'v4506_save_dataphone_config' in globals(): setattr(_rf_snapshot_app_patch_4506, 'v4506_save_dataphone_config', globals()['v4506_save_dataphone_config'])
if 'v4506_test_dataphone' in globals(): setattr(_rf_snapshot_app_patch_4506, 'v4506_test_dataphone', globals()['v4506_test_dataphone'])
if 'v4506_validate_dataphone' in globals(): setattr(_rf_snapshot_app_patch_4506, 'v4506_validate_dataphone', globals()['v4506_validate_dataphone'])
_rf_layers['app_patch_4506'] = _rf_snapshot_app_patch_4506

# ---- app_patch_4507 ----
_rf_alias_app_patch_4507__previous = _rf_layers['app_patch_4506']
core = _rf_alias_app_patch_4507__previous.core
app = _rf_alias_app_patch_4507__previous.app
APP_VERSION = '4.5.7'
_mod = _rf_alias_app_patch_4507__previous
_seen = set()
for _ in range(150):
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
    V4507_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.7"!important;\n  font-size:9px!important;\n  line-height:1!important;\n  font-weight:850!important\n}\n\n/* Consulta conserva presencia; procedimientos siguen compactos. */\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"],\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"]{\n  min-height:66px!important;\n  padding:13px 42px!important;\n  border-radius:13px!important\n}\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] b,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] b,\n.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] strong,\n.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] strong{\n  font-size:12.5px!important\n}\n.attention-form-modal .procedures-service-section .service-card[data-service]{\n  min-height:46px!important;\n  padding:7px 8px!important\n}\n\n/* La forma de pago tiene mayor jerarquía. */\n.v4504-pay{\n  padding:15px!important;\n  border-radius:15px!important\n}\n.v4504-pay-head b{\n  font-size:16px!important\n}\n.v4504-pay-head small{\n  font-size:9.5px!important\n}\n.v4504-pay-option{\n  min-height:63px!important;\n  padding:10px 12px!important\n}\n.v4504-pay-option>span{\n  font-size:21px!important\n}\n.v4504-pay-option>b,\n.v4504-pay-option[data-v4507-card="1"] b{\n  font-size:13px!important;\n  line-height:1.1!important\n}\n.v4504-pay-option>small,\n.v4504-pay-option[data-v4507-card="1"] small{\n  font-size:9px!important;\n  line-height:1.2!important\n}\n.v4504-pay-option[data-v4507-card="1"]{\n  border-style:solid!important;\n  background:#fff!important;\n  cursor:pointer!important\n}\n.v4504-pay-option[data-v4507-card="1"].selected{\n  border-color:#6d9fd0!important;\n  background:#eef6ff!important;\n  color:#255b8d!important;\n  box-shadow:0 0 0 2px rgba(68,123,177,.09)!important\n}\n.v4505-dataphone-note{\n  display:none!important\n}\n#v4504Card{\n  display:none!important\n}\n\n/* Flujo manual Bendo. */\n.v4507-bendo-flow{\n  margin-top:10px;\n  border:1px solid #cbdceb;\n  border-radius:14px;\n  background:linear-gradient(180deg,#f8fbff 0%,#ffffff 100%);\n  overflow:hidden\n}\n.v4507-bendo-top{\n  display:grid;\n  grid-template-columns:minmax(0,1fr) auto;\n  align-items:center;\n  gap:14px;\n  padding:13px 14px;\n  background:#eef6ff;\n  border-bottom:1px solid #dce8f2\n}\n.v4507-bendo-top small{\n  display:block;\n  color:#6e8297;\n  font-size:8.5px;\n  font-weight:800;\n  text-transform:uppercase;\n  letter-spacing:.05em\n}\n.v4507-bendo-top strong{\n  display:block;\n  margin-top:2px;\n  color:#234d73;\n  font-size:14px\n}\n.v4507-bendo-amount{\n  min-width:126px;\n  text-align:center;\n  padding:7px 12px;\n  border-radius:11px;\n  background:#173f65;\n  color:#fff\n}\n.v4507-bendo-amount span{\n  display:block;\n  font-size:7.5px;\n  font-weight:800;\n  opacity:.76;\n  letter-spacing:.08em\n}\n.v4507-bendo-amount b{\n  display:block;\n  margin-top:1px;\n  font-size:24px;\n  line-height:1.05\n}\n.v4507-bendo-body{\n  padding:12px 14px\n}\n.v4507-bendo-steps{\n  display:grid;\n  grid-template-columns:repeat(3,minmax(0,1fr));\n  gap:7px;\n  margin-bottom:10px\n}\n.v4507-bendo-step{\n  min-height:56px;\n  padding:8px 9px;\n  border:1px solid #e0e7ef;\n  border-radius:10px;\n  background:#fbfcfe\n}\n.v4507-bendo-step span{\n  display:block;\n  color:#315d84;\n  font-size:8px;\n  font-weight:950\n}\n.v4507-bendo-step b{\n  display:block;\n  margin-top:3px;\n  color:#536b82;\n  font-size:9px;\n  line-height:1.25\n}\n.v4507-bendo-options{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:8px\n}\n.v4507-bendo-options button,\n.v4507-bendo-plan button{\n  min-height:34px!important;\n  border:1px solid #d1dde8!important;\n  border-radius:9px!important;\n  background:#fff!important;\n  color:#4b647c!important;\n  font-size:9px!important;\n  font-weight:900!important;\n  box-shadow:none!important\n}\n.v4507-bendo-options button.selected,\n.v4507-bendo-plan button.selected{\n  border-color:#7aa7cf!important;\n  background:#eaf4ff!important;\n  color:#235c8e!important\n}\n.v4507-bendo-plan{\n  display:flex;\n  gap:6px;\n  margin-top:8px\n}\n.v4507-bendo-fields{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:8px;\n  margin-top:9px\n}\n.v4507-bendo-field label{\n  display:block;\n  margin-bottom:4px;\n  color:#73869a;\n  font-size:7.5px;\n  font-weight:900;\n  text-transform:uppercase\n}\n.v4507-bendo-field input{\n  width:100%;\n  height:34px!important;\n  border-radius:8px!important;\n  font-size:9px!important\n}\n.v4507-bendo-actions{\n  display:flex;\n  gap:7px;\n  margin-top:10px;\n  align-items:center;\n  flex-wrap:wrap\n}\n.v4507-bendo-actions button{\n  min-height:36px!important;\n  border-radius:9px!important;\n  font-size:9px!important;\n  font-weight:900!important\n}\n.v4507-bendo-actions .approve{\n  background:#2f7a51!important;\n  border-color:#2f7a51!important;\n  color:#fff!important\n}\n.v4507-bendo-actions .approve.done{\n  background:#e7f7ed!important;\n  border-color:#a9d8b9!important;\n  color:#246440!important\n}\n.v4507-bendo-result{\n  flex:1;\n  min-width:190px;\n  text-align:right;\n  color:#718397;\n  font-size:8.5px\n}\n.v4507-bendo-result.ok{\n  color:#276a46;\n  font-weight:850\n}\n.v4507-bendo-warning{\n  margin-top:9px;\n  padding:7px 9px;\n  border-radius:9px;\n  background:#fff8e9;\n  color:#82621e;\n  font-size:8px;\n  line-height:1.35\n}\n\n/* Configuración: modo real Bendo. */\n.v4507-config{\n  max-width:980px!important\n}\n.v4507-config-hero{\n  display:grid;\n  grid-template-columns:minmax(0,1fr) auto;\n  gap:16px;\n  align-items:center;\n  padding:17px;\n  border:1px solid #d9e4ef;\n  border-radius:15px;\n  background:linear-gradient(135deg,#f6fbff 0%,#eef6ff 100%);\n  margin-bottom:12px\n}\n.v4507-config-hero h3{\n  margin:0 0 4px;\n  color:#203d59;\n  font-size:18px\n}\n.v4507-config-hero p{\n  margin:0;\n  color:#657b91;\n  font-size:10px;\n  line-height:1.45\n}\n.v4507-status-pill{\n  padding:6px 10px;\n  border-radius:999px;\n  border:1px solid #ead5a5;\n  background:#fff5df;\n  color:#855f19;\n  font-size:9px;\n  font-weight:950;\n  white-space:nowrap\n}\n.v4507-config-grid{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:10px\n}\n.v4507-config-card{\n  padding:14px;\n  border:1px solid #dfe7ef;\n  border-radius:13px;\n  background:#fff\n}\n.v4507-config-card.full{\n  grid-column:1/-1\n}\n.v4507-config-card h4{\n  margin:0 0 4px;\n  color:#304d68;\n  font-size:13px\n}\n.v4507-config-card p{\n  margin:0;\n  color:#72859a;\n  font-size:9px;\n  line-height:1.45\n}\n.v4507-flow{\n  display:grid;\n  grid-template-columns:repeat(4,minmax(0,1fr));\n  gap:7px;\n  margin-top:11px\n}\n.v4507-flow>div{\n  position:relative;\n  padding:10px;\n  border:1px solid #e1e7ee;\n  border-radius:10px;\n  background:#fafcfe\n}\n.v4507-flow span{\n  display:block;\n  color:#2f628f;\n  font-size:8px;\n  font-weight:950\n}\n.v4507-flow b{\n  display:block;\n  margin-top:3px;\n  color:#536a81;\n  font-size:9px;\n  line-height:1.3\n}\n.v4507-config-list{\n  display:grid;\n  gap:7px;\n  margin-top:9px\n}\n.v4507-config-row{\n  display:flex;\n  justify-content:space-between;\n  gap:12px;\n  align-items:center;\n  padding:8px 9px;\n  border:1px solid #e2e8ef;\n  border-radius:9px;\n  background:#fbfcfe\n}\n.v4507-config-row span{\n  color:#62778d;\n  font-size:9px\n}\n.v4507-config-row b{\n  color:#324f6a;\n  font-size:9px;\n  text-align:right\n}\n.v4507-future{\n  margin-top:10px;\n  padding:9px 10px;\n  border:1px dashed #cdd9e5;\n  border-radius:10px;\n  background:#f8fafc;\n  color:#64798f;\n  font-size:8.5px;\n  line-height:1.4\n}\n@media(max-width:780px){\n  .v4507-bendo-top,.v4507-config-hero{grid-template-columns:1fr}\n  .v4507-bendo-steps{grid-template-columns:1fr}\n  .v4507-config-grid,.v4507-flow{grid-template-columns:1fr}\n  .v4507-bendo-fields{grid-template-columns:1fr}\n}\n'
    V4507_JS = '\n;(()=>{\n  if(window.__v4507BendoManual)return;\n  window.__v4507BendoManual=true;\n  const VERSION=\'4.5.7\';\n  const q=(s,r=document)=>r.querySelector(s);\n  const qa=(s,r=document)=>[...r.querySelectorAll(s)];\n  const money=n=>\'$\'+Number(n||0).toFixed(2);\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\n    \'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'\n  }[c]));\n\n  let internalBaseClick=false;\n  let state={\n    active:false,\n    cardType:\'\',\n    creditPlan:\'CORRIENTE\',\n    installments:3,\n    voucher:\'\',\n    approved:false,\n    approvedAmount:null\n  };\n\n  function amount(){\n    try{\n      const value=window.__v4504PaymentTest?.total?.();\n      return Math.round(Number(value||0)*100)/100;\n    }catch(_e){\n      return 0;\n    }\n  }\n\n  function resetBendo(){\n    state={\n      active:false,\n      cardType:\'\',\n      creditPlan:\'CORRIENTE\',\n      installments:3,\n      voucher:\'\',\n      approved:false,\n      approvedAmount:null\n    };\n  }\n\n  function invalidateIfAmountChanged(){\n    const current=amount();\n    if(\n      state.approved\n      &&Math.abs(Number(state.approvedAmount||0)-current)>0.009\n    ){\n      state.approved=false;\n      state.approvedAmount=null;\n    }\n  }\n\n  function actualPayload(){\n    const total=amount();\n    if(!state.active)return null;\n    if(total<=0)throw Error(\'Selecciona primero la consulta o procedimiento.\');\n    if(!state.cardType)throw Error(\'Selecciona si el pago fue con tarjeta Débito o Crédito.\');\n    if(!state.approved)throw Error(\'Confirma que el pago fue APROBADO en el Bendo Smart.\');\n    if(Math.abs(Number(state.approvedAmount||0)-total)>0.009){\n      state.approved=false;\n      state.approvedAmount=null;\n      throw Error(\'El valor cambió después de aprobar el cobro. Vuelve a confirmar el pago en Bendo.\');\n    }\n\n    const method=state.cardType===\'CREDITO\'\n      ?\'TARJETA_CREDITO\'\n      :\'TARJETA_DEBITO\';\n\n    const payload={\n      payment_method:method,\n      voucher:String(state.voucher||\'\').trim()\n    };\n\n    if(method===\'TARJETA_CREDITO\'){\n      payload.card_plan=state.creditPlan;\n      payload.installments=(\n        state.creditPlan===\'DIFERIDO\'\n          ?Number(state.installments||0)\n          :1\n      );\n      if(\n        state.creditPlan===\'DIFERIDO\'\n        &&(\n          !Number.isInteger(payload.installments)\n          ||payload.installments<2\n          ||payload.installments>99\n        )\n      ){\n        throw Error(\'Ingresa una cantidad válida de cuotas para el crédito diferido.\');\n      }\n    }\n    return payload;\n  }\n\n  function chooseBaseCash(){\n    const host=q(\'.attention-form-modal #v4504Payment\');\n    const cash=q(\'[data-mode="EFECTIVO"]\',host);\n    if(!cash)return false;\n    internalBaseClick=true;\n    try{\n      cash.click();\n      return true;\n    }finally{\n      internalBaseClick=false;\n    }\n  }\n\n  function selectBendo(){\n    state.active=true;\n    state.approved=false;\n    state.approvedAmount=null;\n    patchPayment();\n  }\n\n  function cardButton(){\n    const host=q(\'.attention-form-modal #v4504Payment\');\n    if(!host)return null;\n\n    let current=q(\'[data-v4507-card="1"]\',host);\n    if(current)return current;\n\n    const legacy=q(\'[data-mode="TARJETA"]\',host);\n    if(!legacy)return null;\n\n    const clone=legacy.cloneNode(true);\n    clone.removeAttribute(\'data-mode\');\n    clone.removeAttribute(\'aria-disabled\');\n    clone.dataset.v4507Card=\'1\';\n    clone.classList.remove(\'selected\');\n    clone.setAttribute(\n      \'title\',\n      \'Cobro manual en Bendo Smart\'\n    );\n    const title=q(\'b\',clone);\n    const small=q(\'small\',clone);\n    if(title)title.textContent=\'Tarjeta\';\n    if(small)small.textContent=\'Bendo Smart · manual\';\n    clone.addEventListener(\'click\',event=>{\n      event.preventDefault();\n      event.stopPropagation();\n      selectBendo();\n    });\n    legacy.replaceWith(clone);\n    return clone;\n  }\n\n  function renderFlow(){\n    const host=q(\'.attention-form-modal #v4504Payment\');\n    if(!host)return;\n\n    let flow=q(\'#v4507BendoFlow\',host);\n    if(!state.active){\n      flow?.remove();\n      return;\n    }\n\n    invalidateIfAmountChanged();\n    const total=amount();\n\n    if(!flow){\n      flow=document.createElement(\'div\');\n      flow.id=\'v4507BendoFlow\';\n      flow.className=\'v4507-bendo-flow\';\n      const options=q(\'.v4504-pay-options\',host);\n      options?.insertAdjacentElement(\'afterend\',flow);\n    }\n\n    flow.innerHTML=\n      \'<div class="v4507-bendo-top">\'\n      +\'<div><small>COBRO CON TARJETA</small>\'\n      +\'<strong>Bendo Smart · operación manual</strong></div>\'\n      +\'<div class="v4507-bendo-amount"><span>DIGITAR EN BENDO</span>\'\n      +\'<b>\'+money(total)+\'</b></div></div>\'\n\n      +\'<div class="v4507-bendo-body">\'\n      +\'<div class="v4507-bendo-steps">\'\n      +\'<div class="v4507-bendo-step"><span>1 · MONTO</span><b>Digita \'+money(total)+\' en el Bendo Smart.</b></div>\'\n      +\'<div class="v4507-bendo-step"><span>2 · COBRAR</span><b>El paciente paga directamente en el equipo.</b></div>\'\n      +\'<div class="v4507-bendo-step"><span>3 · CONFIRMAR</span><b>Solo guarda si Bendo muestra pago aprobado.</b></div>\'\n      +\'</div>\'\n\n      +\'<div class="v4507-bendo-options">\'\n      +\'<button type="button" data-v4507-cardtype="DEBITO" class="\'\n      +(state.cardType===\'DEBITO\'?\'selected\':\'\')\n      +\'">Tarjeta de débito · SRI 16</button>\'\n      +\'<button type="button" data-v4507-cardtype="CREDITO" class="\'\n      +(state.cardType===\'CREDITO\'?\'selected\':\'\')\n      +\'">Tarjeta de crédito · SRI 19</button>\'\n      +\'</div>\'\n\n      +(state.cardType===\'CREDITO\'\n        ?\'<div class="v4507-bendo-plan">\'\n         +\'<button type="button" data-v4507-plan="CORRIENTE" class="\'\n         +(state.creditPlan===\'CORRIENTE\'?\'selected\':\'\')\n         +\'">Corriente</button>\'\n         +\'<button type="button" data-v4507-plan="DIFERIDO" class="\'\n         +(state.creditPlan===\'DIFERIDO\'?\'selected\':\'\')\n         +\'">Diferido</button></div>\'\n        :\'\')\n\n      +\'<div class="v4507-bendo-fields">\'\n      +(state.cardType===\'CREDITO\'&&state.creditPlan===\'DIFERIDO\'\n        ?\'<div class="v4507-bendo-field"><label>Cuotas</label>\'\n         +\'<input id="v4507Installments" type="number" min="2" max="99" value="\'\n         +Number(state.installments||3)+\'"></div>\'\n        :\'\')\n      +\'<div class="v4507-bendo-field"><label>Voucher / autorización</label>\'\n      +\'<input id="v4507Voucher" maxlength="40" placeholder="Opcional" value="\'\n      +esc(state.voucher)+\'"></div>\'\n      +\'</div>\'\n\n      +\'<div class="v4507-bendo-actions">\'\n      +\'<button type="button" id="v4507Approve" class="approve \'\n      +(state.approved?\'done\':\'\')+\'">\'\n      +(state.approved?\'✓ Pago aprobado confirmado\':\'✓ Confirmar PAGO APROBADO\')\n      +\'</button>\'\n      +\'<button type="button" id="v4507CancelCard">Cambiar forma de pago</button>\'\n      +\'<span class="v4507-bendo-result \'+(state.approved?\'ok\':\'\')+\'">\'\n      +(state.approved\n        ?\'✓ Listo para guardar la atención\'\n        :\'Esperando confirmación del Bendo Smart\')\n      +\'</span></div>\'\n\n      +\'<div class="v4507-bendo-warning">\'\n      +\'Recepción no controla el terminal ni guarda número de tarjeta/CVV. \'\n      +\'La confirmación indica que verificaste visualmente el resultado en Bendo.\'\n      +\'</div></div>\';\n\n    qa(\'[data-v4507-cardtype]\',flow).forEach(button=>{\n      button.addEventListener(\'click\',()=>{\n        state.cardType=button.dataset.v4507Cardtype||\'\';\n        state.approved=false;\n        state.approvedAmount=null;\n        renderFlow();\n      });\n    });\n\n    qa(\'[data-v4507-plan]\',flow).forEach(button=>{\n      button.addEventListener(\'click\',()=>{\n        state.creditPlan=button.dataset.v4507Plan||\'CORRIENTE\';\n        state.approved=false;\n        state.approvedAmount=null;\n        renderFlow();\n      });\n    });\n\n    q(\'#v4507Installments\',flow)?.addEventListener(\'input\',event=>{\n      state.installments=Number(event.target.value||0);\n      state.approved=false;\n      state.approvedAmount=null;\n    });\n\n    q(\'#v4507Voucher\',flow)?.addEventListener(\'input\',event=>{\n      state.voucher=event.target.value;\n    });\n\n    q(\'#v4507Approve\',flow)?.addEventListener(\'click\',()=>{\n      if(!state.cardType){\n        alert(\'Selecciona primero Débito o Crédito.\');\n        return;\n      }\n      if(\n        state.cardType===\'CREDITO\'\n        &&state.creditPlan===\'DIFERIDO\'\n        &&(\n          !Number.isInteger(Number(state.installments))\n          ||Number(state.installments)<2\n        )\n      ){\n        alert(\'Ingresa la cantidad de cuotas.\');\n        return;\n      }\n      if(total<=0){\n        alert(\'Selecciona primero la consulta o procedimiento.\');\n        return;\n      }\n      state.approved=true;\n      state.approvedAmount=total;\n      renderFlow();\n    });\n\n    q(\'#v4507CancelCard\',flow)?.addEventListener(\'click\',()=>{\n      resetBendo();\n      patchPayment();\n    });\n  }\n\n  function patchPayment(){\n    const host=q(\'.attention-form-modal #v4504Payment\');\n    if(!host)return;\n\n    const card=cardButton();\n    if(!card)return;\n\n    qa(\'.v4504-pay-option\',host).forEach(button=>{\n      if(state.active){\n        button.classList.toggle(\n          \'selected\',\n          button.dataset.v4507Card===\'1\'\n        );\n      }\n    });\n\n    const status=q(\'.v4504-pay-state\',host);\n    if(status&&state.active){\n      status.classList.add(\'ready\');\n      status.textContent=state.approved\n        ?\'✓ Tarjeta · Bendo aprobado\'\n        :\'Tarjeta · pendiente de cobro\';\n    }\n\n    renderFlow();\n  }\n\n  // Si el usuario selecciona otra forma, se abandona el flujo Bendo.\n  document.addEventListener(\'click\',event=>{\n    if(internalBaseClick)return;\n    const other=event.target?.closest?.(\n      \'.attention-form-modal [data-mode="EFECTIVO"],\'\n      +\'.attention-form-modal [data-mode="TRANSFERENCIA"],\'\n      +\'.attention-form-modal [data-mode="MIXTO"]\'\n    );\n    if(!other)return;\n    resetBendo();\n    setTimeout(patchPayment,60);\n  },false);\n\n  // Al cambiar servicios o descuento, el total puede variar y una aprobación\n  // anterior deja de ser válida.\n  document.addEventListener(\'click\',event=>{\n    if(\n      event.target?.closest?.(\n        \'.attention-form-modal .service-card,\'\n        +\'.attention-form-modal [data-v4502-couple-discount],\'\n        +\'.attention-form-modal input[type="checkbox"]\'\n      )\n    ){\n      const old=amount();\n      setTimeout(()=>{\n        const now=amount();\n        if(\n          state.approved\n          &&Math.abs(now-Number(state.approvedAmount||0))>0.009\n        ){\n          state.approved=false;\n          state.approvedAmount=null;\n        }\n        patchPayment();\n      },70);\n    }\n  },true);\n\n  const stableAttentionFor=window.attentionFor;\n  if(typeof stableAttentionFor===\'function\'){\n    window.attentionFor=async function(){\n      resetBendo();\n      const result=await stableAttentionFor.apply(this,arguments);\n      setTimeout(patchPayment,90);\n      setTimeout(patchPayment,260);\n      return result;\n    };\n  }\n\n  // Envoltura final del guardado: el v4.5.4 conserva compatibilidad interna con\n  // el guardado estable. Aquí reemplazamos únicamente el payload del pago cuando\n  // el usuario confirmó una tarjeta real en Bendo.\n  const stableSave=window.saveAttention;\n  if(typeof stableSave===\'function\'){\n    window.saveAttention=async function(){\n      if(!state.active){\n        return await stableSave.apply(this,arguments);\n      }\n\n      let cardPayload;\n      try{\n        cardPayload=actualPayload();\n      }catch(error){\n        alert(error?.message||String(error));\n        patchPayment();\n        return;\n      }\n\n      if(!chooseBaseCash()){\n        alert(\'No se pudo preparar el guardado de la forma de pago. Cierra y vuelve a abrir Nueva atención.\');\n        return;\n      }\n\n      const previousWindowApi=window.api;\n      const previousApi=api;\n      const downstream=previousWindowApi||previousApi;\n\n      const intercept=async function(url,opt={}){\n        if(String(url)===\'/api/visits/batch-payment\'){\n          let body={};\n          try{\n            body=JSON.parse(opt?.body||\'{}\');\n          }catch(_e){\n            body={};\n          }\n          Object.assign(body,cardPayload);\n          return downstream(\n            url,\n            {\n              ...opt,\n              body:JSON.stringify(body)\n            }\n          );\n        }\n        return downstream(url,opt);\n      };\n\n      try{\n        window.api=intercept;\n        api=intercept;\n        return await stableSave.apply(this,arguments);\n      }finally{\n        window.api=previousWindowApi;\n        api=previousApi;\n      }\n    };\n  }\n\n  // ---------- Corrección de forma de pago desde Facturación ----------\n  function billingIdentity(card){\n    try{\n      const cards=qa(\'#billingList .billing-card\');\n      const index=cards.indexOf(card);\n      const groups=Array.isArray(window.billingGroupsCache)\n        ?window.billingGroupsCache\n        :(typeof billingGroupsCache!==\'undefined\'&&Array.isArray(billingGroupsCache)\n          ?billingGroupsCache\n          :[]);\n      const group=index>=0?groups[index]:null;\n      const patientId=Number(\n        card?.dataset?.patientId\n        ||group?.patient?.id\n        ||0\n      );\n      const fecha=String(\n        card?.dataset?.fecha\n        ||group?.fecha\n        ||\'\'\n      ).slice(0,10);\n      if(!patientId||!fecha)return null;\n      return {patientId,fecha};\n    }catch(_e){\n      return null;\n    }\n  }\n\n  async function saveBillingCard(card,method){\n    const id=billingIdentity(card);\n    if(!id){\n      alert(\'No se pudo identificar esta ficha de facturación.\');\n      return;\n    }\n\n    const approved=confirm(\n      \'Usa esta opción únicamente si el cobro YA fue aprobado en el Bendo Smart.\\n\\n¿Confirmar pago con tarjeta?\'\n    );\n    if(!approved)return;\n\n    let extra={};\n    if(method===\'TARJETA_CREDITO\'){\n      const mode=String(\n        prompt(\n          \'Crédito: escribe C para CORRIENTE o D para DIFERIDO.\',\n          \'C\'\n        )||\'\'\n      ).trim().toUpperCase();\n      if(!mode)return;\n      if(mode===\'D\'){\n        const qty=Number(prompt(\'Número de cuotas:\',\'3\')||0);\n        if(!Number.isInteger(qty)||qty<2){\n          alert(\'Cantidad de cuotas inválida.\');\n          return;\n        }\n        extra={card_plan:\'DIFERIDO\',installments:qty};\n      }else{\n        extra={card_plan:\'CORRIENTE\',installments:1};\n      }\n    }\n\n    try{\n      await (window.api||api)(\n        \'/api/billing/payment-method\',\n        {\n          method:\'POST\',\n          body:JSON.stringify({\n            patient_id:id.patientId,\n            fecha:id.fecha,\n            payment_method:method,\n            ...extra\n          })\n        }\n      );\n      await window.loadBilling?.();\n      setTimeout(patchBilling,80);\n      setTimeout(patchBilling,260);\n    }catch(error){\n      alert(error?.message||String(error));\n    }\n  }\n\n  function patchBilling(){\n    qa(\'#billingList .billing-card\').forEach(card=>{\n      qa(\n        \'.v4504-billchoices [data-bm="TARJETA_DEBITO"],\'\n        +\'.v4504-billchoices [data-bm="TARJETA_CREDITO"]\',\n        card\n      ).forEach(button=>{\n        const method=button.dataset.bm;\n        const clone=button.cloneNode(true);\n        clone.removeAttribute(\'data-bm\');\n        clone.dataset.v4507Bm=method;\n        clone.setAttribute(\n          \'title\',\n          \'Registrar tarjeta solo después de verificar pago aprobado en Bendo\'\n        );\n        clone.addEventListener(\'click\',event=>{\n          event.preventDefault();\n          event.stopPropagation();\n          saveBillingCard(card,method);\n        });\n        button.replaceWith(clone);\n      });\n    });\n  }\n\n  const stableLoadBilling=window.loadBilling;\n  if(typeof stableLoadBilling===\'function\'){\n    window.loadBilling=async function(){\n      const result=await stableLoadBilling.apply(this,arguments);\n      setTimeout(patchBilling,60);\n      setTimeout(patchBilling,220);\n      return result;\n    };\n  }\n\n  // ---------- Configuración > Datáfono ----------\n  function renderManualConfig(){\n    const section=q(\'[data-config-section="dataphone"]\');\n    if(!section)return;\n\n    section.className=\'config-section v4507-config\';\n    section.innerHTML=\n      \'<div class="v4507-config-hero">\'\n      +\'<div><h3>💳 Bendo Smart</h3>\'\n      +\'<p>Flujo configurado según la operación actualmente soportada por Bendo. \'\n      +\'El cobro se inicia manualmente en el terminal; Recepción controla el monto, \'\n      +\'la validación del resultado y el registro administrativo.</p></div>\'\n      +\'<span class="v4507-status-pill">MODO MANUAL CONFIRMADO</span>\'\n      +\'</div>\'\n\n      +\'<div class="v4507-config-grid">\'\n      +\'<section class="v4507-config-card full"><h4>Cómo se cobrará</h4>\'\n      +\'<p>El programa reduce al mínimo el trabajo manual sin inventar una API que Bendo no ofrece actualmente.</p>\'\n      +\'<div class="v4507-flow">\'\n      +\'<div><span>1 · RECEPCIÓN</span><b>Calcula el total exacto de la atención.</b></div>\'\n      +\'<div><span>2 · BENDO SMART</span><b>Recepción muestra en grande el valor que debes digitar.</b></div>\'\n      +\'<div><span>3 · PACIENTE</span><b>El paciente paga directamente en el terminal.</b></div>\'\n      +\'<div><span>4 · CONFIRMACIÓN</span><b>Solo se guarda Tarjeta después de confirmar “Aprobado”.</b></div>\'\n      +\'</div></section>\'\n\n      +\'<section class="v4507-config-card"><h4>Estado actual</h4>\'\n      +\'<div class="v4507-config-list">\'\n      +\'<div class="v4507-config-row"><span>Proveedor</span><b>Bendo</b></div>\'\n      +\'<div class="v4507-config-row"><span>Equipo</span><b>Bendo Smart</b></div>\'\n      +\'<div class="v4507-config-row"><span>Integración API/ECR</span><b>No disponible actualmente</b></div>\'\n      +\'<div class="v4507-config-row"><span>Inicio del cobro</span><b>Manual en el terminal</b></div>\'\n      +\'<div class="v4507-config-row"><span>Confirmación en Recepción</span><b>Obligatoria</b></div>\'\n      +\'</div></section>\'\n\n      +\'<section class="v4507-config-card"><h4>Qué registra Recepción</h4>\'\n      +\'<div class="v4507-config-list">\'\n      +\'<div class="v4507-config-row"><span>Débito / Crédito</span><b>Sí</b></div>\'\n      +\'<div class="v4507-config-row"><span>Corriente / Diferido</span><b>Sí</b></div>\'\n      +\'<div class="v4507-config-row"><span>Cuotas</span><b>Si aplica</b></div>\'\n      +\'<div class="v4507-config-row"><span>Voucher / autorización</span><b>Opcional</b></div>\'\n      +\'<div class="v4507-config-row"><span>Número de tarjeta / CVV</span><b>Nunca</b></div>\'\n      +\'</div></section>\'\n\n      +\'<section class="v4507-config-card full"><h4>Integración futura</h4>\'\n      +\'<p>La arquitectura técnica que preparamos se conserva internamente, pero no se muestra como si estuviera disponible. \'\n      +\'Si PUBLIPROMUEVE confirma ECR, SDK, Intent, API privada o programa de partners, podremos sustituir únicamente este paso manual.</p>\'\n      +\'<div class="v4507-future">\'\n      +\'<b>Consulta técnica en curso:</b> se solicitó confirmación directa a PUBLIPROMUEVE/Desarrollo. \'\n      +\'Hasta recibir documentación oficial, Recepción no intentará enviar órdenes de cobro al dispositivo.\'\n      +\'</div></section>\'\n      +\'</div>\';\n  }\n\n  function patchConfigTab(){\n    const tabs=q(\'#config .config-tabs\');\n    if(!tabs)return;\n\n    let button=q(\'[data-config-tab="dataphone"]\',tabs);\n    if(!button)return;\n\n    if(button.dataset.v4507Manual===\'1\')return;\n\n    const clone=button.cloneNode(true);\n    clone.dataset.v4507Manual=\'1\';\n    clone.textContent=\'Datáfono\';\n    clone.onclick=()=>{\n      window.showConfigTab?.(\'dataphone\',clone);\n      renderManualConfig();\n    };\n    button.replaceWith(clone);\n  }\n\n  function boot(){\n    qa(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n    patchConfigTab();\n    patchPayment();\n    patchBilling();\n  }\n\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\n      \'DOMContentLoaded\',\n      boot,\n      {once:true}\n    );\n  }else{\n    boot();\n  }\n\n  setTimeout(boot,220);\n\n  window.__v4507BendoState={\n    mode:\'MANUAL_CONFIRMED\',\n    provider:\'Bendo\',\n    model:\'Bendo Smart\',\n    apiAvailable:false,\n    requiresApprovedConfirmation:true,\n    cardSensitiveDataStored:false\n  };\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4507_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4507_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4507/bendo/status')
def v4507_bendo_status(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'provider': 'Bendo', 'model': 'Bendo Smart', 'operating_mode': 'MANUAL_CONFIRMED', 'external_api_available': False, 'external_ecr_available': False, 'manual_amount_entry': True, 'approval_confirmation_required': True, 'debit_credit_recording': True, 'credit_plan_recording': True, 'voucher_optional': True, 'stores_pan': False, 'stores_cvv': False, 'technical_escalation_pending': True, 'confirmed_by_vendor_date': '2026-09-18'}

@app.get('/api/v4507/health')
def v4507_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'bendo_manual_flow': True, 'card_payment_enabled': True, 'card_requires_manual_approval_confirmation': True, 'automatic_terminal_control': False, 'consultation_card_restored': True, 'procedures_compact': True, 'payment_typography_enlarged': True, 'config_reflects_vendor_confirmation': True, 'database_changes': False, 'database_schema_changes': False, 'neon_writes_added': False, 'azur_contract_changes': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

_rf_snapshot_app_patch_4507 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4507, '__name__', 'app_patch_4507')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4507, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_ERROR' in globals(): setattr(_rf_snapshot_app_patch_4507, 'PATCH_BOOT_ERROR', globals()['PATCH_BOOT_ERROR'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4507, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4507_CSS' in globals(): setattr(_rf_snapshot_app_patch_4507, 'V4507_CSS', globals()['V4507_CSS'])
if 'V4507_JS' in globals(): setattr(_rf_snapshot_app_patch_4507, 'V4507_JS', globals()['V4507_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4507, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4507, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4507, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4507, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4507, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4507, 'core', globals()['core'])
if 'exc' in globals(): setattr(_rf_snapshot_app_patch_4507, 'exc', globals()['exc'])
if '_rf_alias_app_patch_4507__previous' in globals(): setattr(_rf_snapshot_app_patch_4507, 'previous', globals()['_rf_alias_app_patch_4507__previous'])
if 'uvicorn' in globals(): setattr(_rf_snapshot_app_patch_4507, 'uvicorn', globals()['uvicorn'])
if 'v4507_bendo_status' in globals(): setattr(_rf_snapshot_app_patch_4507, 'v4507_bendo_status', globals()['v4507_bendo_status'])
if 'v4507_health' in globals(): setattr(_rf_snapshot_app_patch_4507, 'v4507_health', globals()['v4507_health'])
_rf_layers['app_patch_4507'] = _rf_snapshot_app_patch_4507

# ---- app_patch_4508 ----
_rf_alias_app_patch_4508__previous = _rf_layers['app_patch_4507']
_rf_alias_app_patch_4508__payment_core = _rf_layers['app_patch_4504']
import historia_bridge
core = _rf_alias_app_patch_4508__previous.core
app = _rf_alias_app_patch_4508__previous.app
APP_VERSION = '4.5.8'
_mod = _rf_alias_app_patch_4508__previous
_seen = set()
for _ in range(180):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
_old_batch = None
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        _old_batch = getattr(_route, 'endpoint', None)
        app.router.routes.remove(_route)
        break
if _old_batch is None:
    raise RuntimeError('No se encontró /api/visits/batch-payment para activar el puente de Historia Clínica')

@app.post('/api/visits/batch-payment')
def v4508_create_visit_batch_payment(data: _rf_alias_app_patch_4508__payment_core.V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    result = _old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            services = list(getattr(data, 'services', None) or [])
            procedures = [str(getattr(x, 'procedimiento', '') or '').strip() for x in services]
            attention_type = 'Consulta' if any((not x for x in procedures)) else procedures[0] if procedures else 'Consulta'
            items = list((result or {}).get('items') or []) if isinstance(result, dict) else []
            visit_ids = [x.get('id') for x in items if isinstance(x, dict) and x.get('id') is not None]
            historia_bridge.queue_attention(reception_patient_id=int(patient.id), display_name=str(getattr(patient, 'nombre', '') or 'Paciente'), identification=str(getattr(patient, 'cedula', '') or ''), attention_type=attention_type, visit_ids=visit_ids)
    except Exception as exc:
        try:
            core.audit(db, user, 'historia_bridge_pending', f'Puente Historia Clínica pendiente: {type(exc).__name__}')
            db.commit()
        except Exception:
            pass
    return result

@app.get('/api/historia-bridge/status')
def v4508_historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4508 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4508, '__name__', 'app_patch_4508')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4508, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4508, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4508, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4508, '_mod', globals()['_mod'])
if '_old_batch' in globals(): setattr(_rf_snapshot_app_patch_4508, '_old_batch', globals()['_old_batch'])
if '_route' in globals(): setattr(_rf_snapshot_app_patch_4508, '_route', globals()['_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4508, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4508, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4508, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4508, 'core', globals()['core'])
if 'historia_bridge' in globals(): setattr(_rf_snapshot_app_patch_4508, 'historia_bridge', globals()['historia_bridge'])
if '_rf_alias_app_patch_4508__payment_core' in globals(): setattr(_rf_snapshot_app_patch_4508, 'payment_core', globals()['_rf_alias_app_patch_4508__payment_core'])
if '_rf_alias_app_patch_4508__previous' in globals(): setattr(_rf_snapshot_app_patch_4508, 'previous', globals()['_rf_alias_app_patch_4508__previous'])
if 'v4508_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_patch_4508, 'v4508_create_visit_batch_payment', globals()['v4508_create_visit_batch_payment'])
if 'v4508_historia_bridge_status' in globals(): setattr(_rf_snapshot_app_patch_4508, 'v4508_historia_bridge_status', globals()['v4508_historia_bridge_status'])
_rf_layers['app_patch_4508'] = _rf_snapshot_app_patch_4508

# ---- app_patch_4509 ----
_rf_alias_app_patch_4509__previous = _rf_layers['app_patch_4508']
core = _rf_alias_app_patch_4509__previous.core
app = _rf_alias_app_patch_4509__previous.app
APP_VERSION = '4.5.9'
_mod = _rf_alias_app_patch_4509__previous
_seen = set()
for _ in range(200):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4509 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4509, '__name__', 'app_patch_4509')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4509, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4509, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4509, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4509, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4509, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4509, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4509, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4509, 'core', globals()['core'])
if '_rf_alias_app_patch_4509__previous' in globals(): setattr(_rf_snapshot_app_patch_4509, 'previous', globals()['_rf_alias_app_patch_4509__previous'])
_rf_layers['app_patch_4509'] = _rf_snapshot_app_patch_4509

# ---- app_patch_4510 ----
_rf_alias_app_patch_4510__previous = _rf_layers['app_patch_4509']
core = _rf_alias_app_patch_4510__previous.core
app = _rf_alias_app_patch_4510__previous.app
APP_VERSION = '4.5.10'
_mod = _rf_alias_app_patch_4510__previous
_seen = set()
for _ in range(220):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4510 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4510, '__name__', 'app_patch_4510')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4510, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4510, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4510, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4510, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4510, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4510, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4510, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4510, 'core', globals()['core'])
if '_rf_alias_app_patch_4510__previous' in globals(): setattr(_rf_snapshot_app_patch_4510, 'previous', globals()['_rf_alias_app_patch_4510__previous'])
_rf_layers['app_patch_4510'] = _rf_snapshot_app_patch_4510

# ---- app_patch_4511 ----
_rf_alias_app_patch_4511__previous = _rf_layers['app_patch_4510']
core = _rf_alias_app_patch_4511__previous.core
app = _rf_alias_app_patch_4511__previous.app
APP_VERSION = '4.5.11'
_mod = _rf_alias_app_patch_4511__previous
_seen = set()
for _ in range(240):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4511 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4511, '__name__', 'app_patch_4511')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4511, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4511, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4511, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4511, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4511, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4511, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4511, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4511, 'core', globals()['core'])
if '_rf_alias_app_patch_4511__previous' in globals(): setattr(_rf_snapshot_app_patch_4511, 'previous', globals()['_rf_alias_app_patch_4511__previous'])
_rf_layers['app_patch_4511'] = _rf_snapshot_app_patch_4511

# ---- app_patch_4517 ----
_rf_alias_app_patch_4517__previous = _rf_layers['app_patch_4511']
import historia_bridge
core = _rf_alias_app_patch_4517__previous.core
app = _rf_alias_app_patch_4517__previous.app
APP_VERSION = '4.5.17'
_mod = _rf_alias_app_patch_4517__previous
_seen = set()
for _ in range(320):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/historia-bridge/status' and 'GET' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)
        break

@app.get('/api/historia-bridge/status')
def v4517_historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()
V4517_CSS = '\n#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}\n#historiaDoctorBadge{display:inline-flex!important;align-items:center!important;gap:7px!important;min-height:31px!important;padding:6px 11px!important;margin-left:8px!important;border:1px solid rgba(148,163,184,.42)!important;border-radius:999px!important;background:rgba(255,255,255,.08)!important;color:#d9e4f2!important;font-size:9px!important;font-weight:850!important;white-space:nowrap!important;vertical-align:middle!important}\n#historiaDoctorBadge:before{content:""!important;width:8px!important;height:8px!important;border-radius:50%!important;background:#94a3b8!important;box-shadow:0 0 0 3px rgba(148,163,184,.12)!important}\n#historiaDoctorBadge.online{border-color:rgba(68,201,124,.55)!important;color:#dff8e8!important;background:rgba(28,110,66,.22)!important}\n#historiaDoctorBadge.online:before{background:#35d174!important;box-shadow:0 0 0 3px rgba(53,209,116,.16)!important}\n#historiaDoctorBadge.cloud{border-color:rgba(238,187,75,.52)!important;color:#fff0c7!important;background:rgba(132,91,15,.2)!important}\n#historiaDoctorBadge.cloud:before{background:#efbd4c!important}\n#historiaDoctorBadge.error{border-color:rgba(222,105,105,.52)!important;color:#ffe0e0!important;background:rgba(130,45,45,.2)!important}\n#historiaDoctorBadge.error:before{background:#e66a6a!important}\n.v4517-version-chip{display:inline-flex!important;align-items:center!important;padding:5px 9px!important;border-radius:999px!important;background:#edf3fb!important;color:#315d86!important;font-size:10px!important;font-weight:900!important}\n@media(max-width:900px){#historiaDoctorBadge{display:none!important}}\n'
V4517_JS = '\n;(()=>{\n if(window.__v4517HistoriaLink)return;window.__v4517HistoriaLink=true;\n const VERSION=\'4.5.17\',q=(s,r=document)=>r.querySelector(s);\n function stripVersion(){const h=q(\'#connectionBadge\');if(h)h.querySelectorAll(\'.v460-version,[data-version]\').forEach(x=>x.remove())}\n function badge(){stripVersion();const h=q(\'#connectionBadge\');if(!h)return null;let b=q(\'#historiaDoctorBadge\');if(!b){b=document.createElement(\'span\');b.id=\'historiaDoctorBadge\';b.textContent=\'Historia: comprobando…\';h.insertAdjacentElement(\'afterend\',b)}return b}\n function age(s){s=Number(s);if(!Number.isFinite(s))return\'\';if(s<60)return\'ahora\';const m=Math.floor(s/60);return m<60?\'hace \'+m+\' min\':\'hace \'+Math.floor(m/60)+\' h\'}\n async function refresh(){const b=badge();if(!b)return;try{const d=await (typeof window.api===\'function\'?window.api(\'/api/historia-bridge/status\'):fetch(\'/api/historia-bridge/status\').then(r=>r.json()));b.className=\'\';if(!d.configured){b.classList.add(\'error\');b.textContent=\'Historia: sin vincular\';b.title=\'Falta la vinculación segura con Historia Clínica.\';return}if(Number(d.pending||0)>0){b.classList.add(\'cloud\');b.textContent=\'Historia: \'+Number(d.pending)+\' por enviar\';b.title=\'Recepción conserva estos eventos localmente y los reenviará.\';return}if(d.doctor_online){b.classList.add(\'online\');b.textContent=\'Historia: doctor conectado\';b.title=\'Historia Clínica sincronizó \'+age(d.doctor_last_seen_age_seconds)+\'.\'}else if(d.cloud_reachable){b.classList.add(\'cloud\');b.textContent=\'Historia: cola en nube lista\';b.title=\'Los atendidos quedan guardados en la nube aunque la PC del doctor esté apagada.\'}else{b.classList.add(\'error\');b.textContent=\'Historia: sin conexión\';b.title=d.presence_error||d.last_error||\'\'}}catch(e){b.className=\'error\';b.textContent=\'Historia: sin comprobar\';b.title=String(e?.message||e||\'\')}}\n function versionChip(){const s=document.querySelector(\'[data-config-section="actualizaciones"]\');if(!s)return;s.querySelectorAll(\'#currentVersionBadge\').forEach(x=>x.style.display=\'none\');let c=q(\'#v4517VersionChip\',s);if(!c){const h=s.querySelector(\'.updater-panel .config-panel-head,.config-panel-head\');if(!h)return;c=document.createElement(\'span\');c.id=\'v4517VersionChip\';c.className=\'v4517-version-chip\';h.appendChild(c)}c.textContent=\'Recepción v\'+VERSION}\n function boot(){badge();versionChip();refresh()}\n const os=window.show;if(typeof os===\'function\')window.show=function(...a){const r=os.apply(this,a);setTimeout(()=>{badge();versionChip()},40);return r};\n const ot=window.showConfigTab;if(typeof ot===\'function\')window.showConfigTab=function(...a){const r=ot.apply(this,a);setTimeout(versionChip,40);return r};\n if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});else boot();\n setTimeout(boot,350);setTimeout(boot,1400);setInterval(refresh,60000);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4517_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4517_JS

@app.get('/api/v4517/health')
def v4517_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_bridge_presence': True, 'version_moved_to_settings': True, 'footer_version_removed': True, 'cloud_queue_survives_doctor_offline': True, 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4517 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4517, '__name__', 'app_patch_4517')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4517, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4517, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4517_CSS' in globals(): setattr(_rf_snapshot_app_patch_4517, 'V4517_CSS', globals()['V4517_CSS'])
if 'V4517_JS' in globals(): setattr(_rf_snapshot_app_patch_4517, 'V4517_JS', globals()['V4517_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4517, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4517, '_mod', globals()['_mod'])
if '_route' in globals(): setattr(_rf_snapshot_app_patch_4517, '_route', globals()['_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4517, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4517, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4517, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4517, 'core', globals()['core'])
if 'historia_bridge' in globals(): setattr(_rf_snapshot_app_patch_4517, 'historia_bridge', globals()['historia_bridge'])
if '_rf_alias_app_patch_4517__previous' in globals(): setattr(_rf_snapshot_app_patch_4517, 'previous', globals()['_rf_alias_app_patch_4517__previous'])
if 'v4517_health' in globals(): setattr(_rf_snapshot_app_patch_4517, 'v4517_health', globals()['v4517_health'])
if 'v4517_historia_bridge_status' in globals(): setattr(_rf_snapshot_app_patch_4517, 'v4517_historia_bridge_status', globals()['v4517_historia_bridge_status'])
_rf_layers['app_patch_4517'] = _rf_snapshot_app_patch_4517

# ---- app_patch_4518 ----
import os
_rf_alias_app_patch_4518__previous = _rf_layers['app_patch_4517']
core = _rf_alias_app_patch_4518__previous.core
app = _rf_alias_app_patch_4518__previous.app
APP_VERSION = '4.5.18'
_mod = _rf_alias_app_patch_4518__previous
_seen = set()
for _ in range(360):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/version' and 'GET' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.get('/api/version')
def v4518_app_version():
    return {'version': APP_VERSION, 'pid': os.getpid()}
V4518_CSS = '\n#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}\n#v4518VersionChip{display:inline-flex!important;align-items:center!important;padding:5px 9px!important;border-radius:999px!important;background:#edf3fb!important;color:#315d86!important;font-size:10px!important;font-weight:900!important;white-space:nowrap!important}\n'
V4518_JS = '\n;(()=>{\n if(window.__v4518RealVersion)return; window.__v4518RealVersion=true;\n const FALLBACK=\'4.5.18\';\n let realVersion=FALLBACK, scheduled=false, fetching=false;\n\n function cleanOld(){\n   const h=document.querySelector(\'#connectionBadge\');\n   if(h) h.querySelectorAll(\'.v460-version,[data-version]\').forEach(x=>x.remove());\n }\n\n function updatesSection(){\n   return document.querySelector(\'[data-config-section="actualizaciones"]\');\n }\n\n function paint(){\n   cleanOld();\n   const s=updatesSection();\n   if(!s) return;\n   s.querySelectorAll(\'#currentVersionBadge,.v4517-version-chip,#v4517VersionChip\').forEach(x=>{\n     if(x.id===\'v4518VersionChip\') return;\n     x.style.display=\'none\';\n   });\n   let chip=s.querySelector(\'#v4518VersionChip\');\n   if(!chip){\n     const head=s.querySelector(\'.updater-panel .config-panel-head,.config-panel-head\');\n     if(!head) return;\n     chip=document.createElement(\'span\');\n     chip.id=\'v4518VersionChip\';\n     head.appendChild(chip);\n   }\n   const wanted=\'Recepción v\'+realVersion;\n   if(chip.textContent!==wanted) chip.textContent=wanted;\n }\n\n function schedulePaint(){\n   if(scheduled) return;\n   scheduled=true;\n   requestAnimationFrame(()=>{scheduled=false;paint()});\n }\n\n async function fetchReal(){\n   if(fetching) return;\n   fetching=true;\n   try{\n     const r=await fetch(\'/api/version?t=\'+Date.now(),{cache:\'no-store\'});\n     if(r.ok){\n       const d=await r.json();\n       const v=String(d&&d.version||\'\').trim();\n       if(v) realVersion=v;\n     }\n   }catch(_e){}\n   finally{fetching=false;schedulePaint()}\n }\n\n function boot(){\n   schedulePaint();\n   fetchReal();\n   const root=document.body||document.documentElement;\n   if(root){\n     const mo=new MutationObserver(()=>schedulePaint());\n     mo.observe(root,{subtree:true,childList:true});\n   }\n }\n\n if(document.readyState===\'loading\') document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n else boot();\n\n const os=window.show;\n if(typeof os===\'function\') window.show=function(...a){const r=os.apply(this,a);schedulePaint();setTimeout(schedulePaint,120);setTimeout(schedulePaint,450);return r};\n const ot=window.showConfigTab;\n if(typeof ot===\'function\') window.showConfigTab=function(...a){const r=ot.apply(this,a);schedulePaint();setTimeout(schedulePaint,120);setTimeout(schedulePaint,450);return r};\n\n setInterval(fetchReal,30000);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4518_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4518_JS

@app.get('/api/v4518/health')
def v4518_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'version_source': 'api/version', 'version_dom_observer': True, 'survives_tab_rerender': True, 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4518 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4518, '__name__', 'app_patch_4518')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4518, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4518, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4518_CSS' in globals(): setattr(_rf_snapshot_app_patch_4518, 'V4518_CSS', globals()['V4518_CSS'])
if 'V4518_JS' in globals(): setattr(_rf_snapshot_app_patch_4518, 'V4518_JS', globals()['V4518_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4518, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4518, '_mod', globals()['_mod'])
if '_route' in globals(): setattr(_rf_snapshot_app_patch_4518, '_route', globals()['_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4518, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4518, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4518, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4518, 'core', globals()['core'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4518, 'os', globals()['os'])
if '_rf_alias_app_patch_4518__previous' in globals(): setattr(_rf_snapshot_app_patch_4518, 'previous', globals()['_rf_alias_app_patch_4518__previous'])
if 'v4518_app_version' in globals(): setattr(_rf_snapshot_app_patch_4518, 'v4518_app_version', globals()['v4518_app_version'])
if 'v4518_health' in globals(): setattr(_rf_snapshot_app_patch_4518, 'v4518_health', globals()['v4518_health'])
_rf_layers['app_patch_4518'] = _rf_snapshot_app_patch_4518

# ---- app_patch_4519 ----
import os
_rf_alias_app_patch_4519__previous = _rf_layers['app_patch_4518']
core = _rf_alias_app_patch_4519__previous.core
app = _rf_alias_app_patch_4519__previous.app
APP_VERSION = '4.5.19'
_mod = _rf_alias_app_patch_4519__previous
_seen = set()
for _ in range(380):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/version' and 'GET' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.get('/api/version')
def v4519_app_version():
    return {'version': APP_VERSION, 'pid': os.getpid(), 'source': 'backend'}
V4519_CSS = '\n#sidebarRealVersion{\n  display:flex!important;\n  align-items:center!important;\n  justify-content:center!important;\n  width:calc(100% - 28px)!important;\n  min-height:28px!important;\n  box-sizing:border-box!important;\n  margin:8px 14px 10px!important;\n  padding:5px 10px!important;\n  border:1px solid rgba(148,163,184,.28)!important;\n  border-radius:11px!important;\n  background:rgba(15,23,42,.16)!important;\n  color:rgba(226,232,240,.78)!important;\n  font-size:10px!important;\n  font-weight:800!important;\n  letter-spacing:.02em!important;\n  text-align:center!important;\n  white-space:nowrap!important;\n  line-height:1.15!important;\n}\n#sidebarRealVersion[data-verified="1"]::before{\n  content:""!important;\n  width:6px!important;\n  height:6px!important;\n  margin-right:7px!important;\n  border-radius:50%!important;\n  background:#7dd3fc!important;\n  box-shadow:0 0 0 3px rgba(125,211,252,.10)!important;\n}\n#sidebarRealVersion[data-verified="0"]{opacity:.72!important}\n#connectionBadge .v460-version,#connectionBadge [data-version]{display:none!important}\n'
V4519_JS = '\n;(()=>{\n if(window.__v4519SidebarRealVersion)return;\n window.__v4519SidebarRealVersion=true;\n\n let realVersion=\'\';\n let verified=false;\n let fetching=false;\n let paintQueued=false;\n let lastFetch=0;\n\n function oldVersionCleanup(){\n   const connection=document.querySelector(\'#connectionBadge\');\n   if(connection){\n     connection.querySelectorAll(\'.v460-version,[data-version]\').forEach(x=>x.remove());\n   }\n }\n\n function ensureSidebarVersion(){\n   oldVersionCleanup();\n   const historia=document.querySelector(\'#historiaDoctorBadge\');\n   const connection=document.querySelector(\'#connectionBadge\');\n   const anchor=historia||connection;\n   if(!anchor)return null;\n\n   let el=document.querySelector(\'#sidebarRealVersion\');\n   if(!el){\n     el=document.createElement(\'div\');\n     el.id=\'sidebarRealVersion\';\n   }\n\n   if(anchor.nextElementSibling!==el){\n     anchor.insertAdjacentElement(\'afterend\',el);\n   }\n\n   const text=\'Recepción v\'+(realVersion||\'…\');\n   if(el.textContent!==text)el.textContent=text;\n   el.dataset.verified=verified?\'1\':\'0\';\n   el.title=verified\n     ? \'Versión confirmada directamente por el backend en ejecución.\'\n     : \'Comprobando versión real del backend…\';\n   return el;\n }\n\n function paint(){\n   paintQueued=false;\n   ensureSidebarVersion();\n\n   const section=document.querySelector(\'[data-config-section="actualizaciones"]\');\n   if(section&&realVersion){\n     const chip=section.querySelector(\'#v4518VersionChip\');\n     if(chip)chip.textContent=\'Recepción v\'+realVersion;\n   }\n }\n\n function queuePaint(){\n   if(paintQueued)return;\n   paintQueued=true;\n   requestAnimationFrame(paint);\n }\n\n async function fetchReal(force=false){\n   const now=Date.now();\n   if(fetching)return;\n   if(!force && now-lastFetch<5000){queuePaint();return;}\n   fetching=true;\n   try{\n     const r=await fetch(\'/api/version?t=\'+now,{cache:\'no-store\',headers:{\'Cache-Control\':\'no-cache\'}});\n     if(!r.ok)throw new Error(\'HTTP \'+r.status);\n     const d=await r.json();\n     const v=String(d&&d.version||\'\').trim();\n     if(v){\n       realVersion=v;\n       verified=true;\n       lastFetch=Date.now();\n     }\n   }catch(_e){\n     verified=false;\n   }finally{\n     fetching=false;\n     queuePaint();\n   }\n }\n\n function onUiChange(){\n   queuePaint();\n   fetchReal(false);\n }\n\n function boot(){\n   queuePaint();\n   fetchReal(true);\n\n   const root=document.body||document.documentElement;\n   if(root){\n     const mo=new MutationObserver(()=>queuePaint());\n     mo.observe(root,{subtree:true,childList:true});\n   }\n\n   document.addEventListener(\'visibilitychange\',()=>{\n     if(!document.hidden)fetchReal(true);\n   });\n   window.addEventListener(\'focus\',()=>fetchReal(true));\n }\n\n if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n else boot();\n\n const oldShow=window.show;\n if(typeof oldShow===\'function\'){\n   window.show=function(...args){\n     const out=oldShow.apply(this,args);\n     onUiChange();\n     setTimeout(onUiChange,100);\n     setTimeout(onUiChange,400);\n     return out;\n   };\n }\n\n const oldConfig=window.showConfigTab;\n if(typeof oldConfig===\'function\'){\n   window.showConfigTab=function(...args){\n     const out=oldConfig.apply(this,args);\n     onUiChange();\n     setTimeout(onUiChange,100);\n     setTimeout(onUiChange,400);\n     return out;\n   };\n }\n\n setInterval(()=>fetchReal(true),30000);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4519_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4519_JS

@app.get('/api/v4519/health')
def v4519_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'sidebar_version_visible': True, 'version_source': 'backend_api_version', 'cache_disabled': True, 'mutation_observer': True, 'focus_recheck': True, 'poll_seconds': 30, 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4519 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4519, '__name__', 'app_patch_4519')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4519, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4519, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4519_CSS' in globals(): setattr(_rf_snapshot_app_patch_4519, 'V4519_CSS', globals()['V4519_CSS'])
if 'V4519_JS' in globals(): setattr(_rf_snapshot_app_patch_4519, 'V4519_JS', globals()['V4519_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4519, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4519, '_mod', globals()['_mod'])
if '_route' in globals(): setattr(_rf_snapshot_app_patch_4519, '_route', globals()['_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4519, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4519, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4519, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4519, 'core', globals()['core'])
if 'os' in globals(): setattr(_rf_snapshot_app_patch_4519, 'os', globals()['os'])
if '_rf_alias_app_patch_4519__previous' in globals(): setattr(_rf_snapshot_app_patch_4519, 'previous', globals()['_rf_alias_app_patch_4519__previous'])
if 'v4519_app_version' in globals(): setattr(_rf_snapshot_app_patch_4519, 'v4519_app_version', globals()['v4519_app_version'])
if 'v4519_health' in globals(): setattr(_rf_snapshot_app_patch_4519, 'v4519_health', globals()['v4519_health'])
_rf_layers['app_patch_4519'] = _rf_snapshot_app_patch_4519

# ---- app_patch_4520 ----
_rf_alias_app_patch_4520__previous = _rf_layers['app_patch_4519']
import historia_bridge
import historia_lan_transport
core = _rf_alias_app_patch_4520__previous.core
app = _rf_alias_app_patch_4520__previous.app
APP_VERSION = '4.5.20'
_mod = _rf_alias_app_patch_4520__previous
_seen = set()
for _ in range(480):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
historia_lan_transport.install(historia_bridge)
V4520_CSS = '\n#historiaDoctorBadge.lan{\n  border-color:rgba(68,201,124,.58)!important;\n  color:#e3faeb!important;\n  background:rgba(27,116,68,.28)!important\n}\n#historiaDoctorBadge.lan:before{\n  background:#35d174!important;\n  box-shadow:0 0 0 3px rgba(53,209,116,.18)!important\n}\n'
V4520_JS = "\n;(()=>{\n if(window.__v4520HybridHistoria)return;\n window.__v4520HybridHistoria=true;\n\n const q=(s,r=document)=>r.querySelector(s);\n const VERSION='4.5.20';\n\n function ensureBadge(){\n   const connection=q('#connectionBadge');\n   let b=q('#historiaDoctorBadge');\n   if(!b && connection){\n     b=document.createElement('span');\n     b.id='historiaDoctorBadge';\n     connection.insertAdjacentElement('afterend',b);\n   }\n   return b;\n }\n\n async function getStatus(){\n   const r=await fetch('/api/historia-bridge/status?t='+Date.now(),{\n     cache:'no-store',\n     headers:{'Cache-Control':'no-cache'}\n   });\n   if(!r.ok)throw new Error('HTTP '+r.status);\n   return await r.json();\n }\n\n function age(seconds){\n   seconds=Number(seconds);\n   if(!Number.isFinite(seconds))return '';\n   if(seconds<60)return 'ahora';\n   const m=Math.floor(seconds/60);\n   if(m<60)return 'hace '+m+' min';\n   return 'hace '+Math.floor(m/60)+' h';\n }\n\n async function refresh(){\n   const b=ensureBadge();\n   if(!b)return;\n   try{\n     const d=await getStatus();\n     b.className='';\n\n     if(d.lan_online){\n       b.classList.add('lan');\n       b.textContent='Historia: LAN conectada';\n       const ms=Number(d.lan_latency_ms);\n       const latency=Number.isFinite(ms)&&ms>=0?' · '+ms+' ms':'';\n       b.title='PC del doctor accesible por red local'\n         +(d.lan_host?' · '+d.lan_host:'')\n         +(d.lan_version?' · v'+d.lan_version:'')\n         +latency\n         +(d.configured?' · Neon de respaldo activo':' · falta enlazar respaldo Neon');\n       return;\n     }\n\n     const pending=Number(d.pending||0);\n     if(d.configured && d.cloud_reachable){\n       b.classList.add('cloud');\n       if(d.doctor_online){\n         b.textContent='Historia: nube conectada';\n         b.title='La LAN no respondió; Historia reportó presencia en Neon '+age(d.doctor_last_seen_age_seconds)+'.';\n       }else{\n         b.textContent=pending>0?'Historia: nube · '+pending+' por enviar':'Historia: nube lista';\n         b.title='La PC del doctor no responde por LAN. Los atendidos quedan guardados en Neon.';\n       }\n       return;\n     }\n\n     b.classList.add('error');\n     if(pending>0){\n       b.textContent='Historia: '+pending+' pendientes';\n       b.title='Sin LAN ni nube. Los atendidos siguen protegidos en la cola local.';\n     }else{\n       b.textContent='Historia: sin conexión';\n       b.title='No responde por LAN y el respaldo de Neon no está disponible.';\n     }\n   }catch(err){\n     b.className='error';\n     b.textContent='Historia: sin comprobar';\n     b.title=String(err?.message||err||'');\n   }\n }\n\n async function version(){\n   try{\n     const r=await fetch('/api/version?t='+Date.now(),{cache:'no-store'});\n     if(!r.ok)return;\n     const d=await r.json();\n     const holder=document.querySelector('#recepcionRealVersion');\n     if(holder)holder.textContent='Recepción v'+String(d.version||VERSION);\n   }catch(_e){}\n }\n\n function boot(){refresh();version()}\n if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();\n window.addEventListener('focus',boot);\n document.addEventListener('visibilitychange',()=>{if(!document.hidden)boot()});\n setInterval(refresh,7000);\n})();\n"
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4520_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4520_JS

@app.get('/api/v4520/health')
def v4520_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {'ok': True, 'version': APP_VERSION, 'hybrid_historia': True, 'lan_online': bool(state.get('lan_online')), 'cloud_configured': bool(state.get('configured')), 'local_outbox_pending': int(state.get('pending') or 0), 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4520 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4520, '__name__', 'app_patch_4520')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4520, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4520, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4520_CSS' in globals(): setattr(_rf_snapshot_app_patch_4520, 'V4520_CSS', globals()['V4520_CSS'])
if 'V4520_JS' in globals(): setattr(_rf_snapshot_app_patch_4520, 'V4520_JS', globals()['V4520_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4520, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4520, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4520, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4520, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4520, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4520, 'core', globals()['core'])
if 'historia_bridge' in globals(): setattr(_rf_snapshot_app_patch_4520, 'historia_bridge', globals()['historia_bridge'])
if 'historia_lan_transport' in globals(): setattr(_rf_snapshot_app_patch_4520, 'historia_lan_transport', globals()['historia_lan_transport'])
if '_rf_alias_app_patch_4520__previous' in globals(): setattr(_rf_snapshot_app_patch_4520, 'previous', globals()['_rf_alias_app_patch_4520__previous'])
if 'v4520_health' in globals(): setattr(_rf_snapshot_app_patch_4520, 'v4520_health', globals()['v4520_health'])
_rf_layers['app_patch_4520'] = _rf_snapshot_app_patch_4520

# ---- app_patch_4521 ----
_rf_alias_app_patch_4521__previous = _rf_layers['app_patch_4520']
_rf_alias_app_patch_4521__bridge_v4508 = _rf_layers['app_patch_4508']
import historia_bridge
core = _rf_alias_app_patch_4521__previous.core
app = _rf_alias_app_patch_4521__previous.app
APP_VERSION = '4.5.21'
_mod = _rf_alias_app_patch_4521__previous
_seen = set()
for _ in range(520):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)
_TYPE_LABELS = {'N': 'Nuevo', 'S': 'Subsecuente', 'P': 'Procedimiento', 'X': 'Procedimiento'}

@app.post('/api/visits/batch-payment')
def v4521_create_visit_batch_payment(data: _rf_alias_app_patch_4521__bridge_v4508.payment_core.V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    result = _rf_alias_app_patch_4521__bridge_v4508._old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            items = list((result or {}).get('items') or []) if isinstance(result, dict) else []
            visit_ids = [x.get('id') for x in items if isinstance(x, dict) and x.get('id') is not None]
            type_code = ''
            if items and isinstance(items[0], dict):
                type_code = str(items[0].get('tipo') or '').strip().upper()
            if not type_code:
                type_code = str(getattr(data, 'tipo', '') or '').strip().upper()
            attention_type = _TYPE_LABELS.get(type_code)
            if not attention_type:
                attention_type = 'Subsecuente' if type_code == 'S' else 'Nuevo' if type_code == 'N' else 'Consulta'
            historia_bridge.queue_attention(reception_patient_id=int(patient.id), display_name=str(getattr(patient, 'nombre', '') or 'Paciente'), identification=str(getattr(patient, 'cedula', '') or ''), attention_type=attention_type, visit_ids=visit_ids)
    except Exception as exc:
        try:
            core.audit(db, user, 'historia_bridge_pending', f'Puente Historia Clínica pendiente: {type(exc).__name__}')
            db.commit()
        except Exception:
            pass
    return result

@app.get('/api/v4521/health')
def v4521_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_attention_type_from_visit': True, 'attention_type_map': {'N': 'Nuevo', 'S': 'Subsecuente', 'P': 'Procedimiento'}, 'hybrid_historia': True, 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4521 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4521, '__name__', 'app_patch_4521')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4521, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4521, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4521, '_', globals()['_'])
if '_TYPE_LABELS' in globals(): setattr(_rf_snapshot_app_patch_4521, '_TYPE_LABELS', globals()['_TYPE_LABELS'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4521, '_mod', globals()['_mod'])
if '_route' in globals(): setattr(_rf_snapshot_app_patch_4521, '_route', globals()['_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4521, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4521, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4521, 'app', globals()['app'])
if '_rf_alias_app_patch_4521__bridge_v4508' in globals(): setattr(_rf_snapshot_app_patch_4521, 'bridge_v4508', globals()['_rf_alias_app_patch_4521__bridge_v4508'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4521, 'core', globals()['core'])
if 'historia_bridge' in globals(): setattr(_rf_snapshot_app_patch_4521, 'historia_bridge', globals()['historia_bridge'])
if '_rf_alias_app_patch_4521__previous' in globals(): setattr(_rf_snapshot_app_patch_4521, 'previous', globals()['_rf_alias_app_patch_4521__previous'])
if 'v4521_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_patch_4521, 'v4521_create_visit_batch_payment', globals()['v4521_create_visit_batch_payment'])
if 'v4521_health' in globals(): setattr(_rf_snapshot_app_patch_4521, 'v4521_health', globals()['v4521_health'])
_rf_layers['app_patch_4521'] = _rf_snapshot_app_patch_4521

# ---- app_patch_4522 ----
_rf_alias_app_patch_4522__previous = _rf_layers['app_patch_4521']
import historia_bridge
core = _rf_alias_app_patch_4522__previous.core
app = _rf_alias_app_patch_4522__previous.app
APP_VERSION = '4.5.22'
_mod = _rf_alias_app_patch_4522__previous
_seen = set()
for _ in range(560):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION

def _remove_route(path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, 'path', None) == path and method in set(getattr(route, 'methods', set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, 'endpoint', None)
    return None
_old_safe_delete_visit = _remove_route('/api/safety/visits/{visit_id}', 'DELETE')
_old_direct_delete_visit = _remove_route('/api/visits/{visit_id}', 'DELETE')
_old_restore_trash = _remove_route('/api/ops/trash/{trash_id}/restore', 'POST')

def _cancel_historia_visit(visit_id, patient_id, db=None, user=None):
    try:
        historia_bridge.cancel_attention(visit_id=visit_id, reception_patient_id=patient_id)
    except Exception as exc:
        try:
            if db is not None and user is not None:
                core.audit(db, user, 'historia_cancel_pending', f'Atención {visit_id}: {type(exc).__name__}')
                db.commit()
        except Exception:
            pass

def _restore_historia_visit(visit_id, patient_id, db=None, user=None):
    try:
        historia_bridge.restore_attention(visit_id=visit_id, reception_patient_id=patient_id)
    except Exception as exc:
        try:
            if db is not None and user is not None:
                core.audit(db, user, 'historia_restore_pending', f'Atención {visit_id}: {type(exc).__name__}')
                db.commit()
        except Exception:
            pass
if _old_safe_delete_visit is not None:

    @app.delete('/api/safety/visits/{visit_id}')
    def v4522_safe_delete_visit(visit_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        result = _old_safe_delete_visit(visit_id, db, user)
        patient_id = (result or {}).get('patient_id') if isinstance(result, dict) else None
        _cancel_historia_visit(visit_id, patient_id or '', db, user)
        return result
if _old_direct_delete_visit is not None:

    @app.delete('/api/visits/{visit_id}')
    def v4522_direct_delete_visit(visit_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        result = _old_direct_delete_visit(visit_id, db, user)
        patient_id = (result or {}).get('patient_id') if isinstance(result, dict) else None
        _cancel_historia_visit(visit_id, patient_id or '', db, user)
        return result
if _old_restore_trash is not None:

    @app.post('/api/ops/trash/{trash_id}/restore')
    def v4522_restore_trash(trash_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        result = _old_restore_trash(trash_id, db, user)
        if isinstance(result, dict) and result.get('entity_type') == 'visit':
            visit_id = result.get('entity_id')
            try:
                visit = db.get(core.Visit, int(visit_id))
            except Exception:
                visit = None
            patient_id = getattr(visit, 'patient_id', '') if visit is not None else ''
            _restore_historia_visit(visit_id, patient_id, db, user)
        return result

@app.get('/api/v4522/health')
def v4522_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_delete_sync': True, 'historia_restore_sync': True, 'signed_history_protected': True, 'transport': 'lan-first-cloud-backup', 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4522 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4522, '__name__', 'app_patch_4522')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4522, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4522, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4522, '_', globals()['_'])
if '_cancel_historia_visit' in globals(): setattr(_rf_snapshot_app_patch_4522, '_cancel_historia_visit', globals()['_cancel_historia_visit'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4522, '_mod', globals()['_mod'])
if '_old_direct_delete_visit' in globals(): setattr(_rf_snapshot_app_patch_4522, '_old_direct_delete_visit', globals()['_old_direct_delete_visit'])
if '_old_restore_trash' in globals(): setattr(_rf_snapshot_app_patch_4522, '_old_restore_trash', globals()['_old_restore_trash'])
if '_old_safe_delete_visit' in globals(): setattr(_rf_snapshot_app_patch_4522, '_old_safe_delete_visit', globals()['_old_safe_delete_visit'])
if '_remove_route' in globals(): setattr(_rf_snapshot_app_patch_4522, '_remove_route', globals()['_remove_route'])
if '_restore_historia_visit' in globals(): setattr(_rf_snapshot_app_patch_4522, '_restore_historia_visit', globals()['_restore_historia_visit'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4522, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4522, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4522, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4522, 'core', globals()['core'])
if 'historia_bridge' in globals(): setattr(_rf_snapshot_app_patch_4522, 'historia_bridge', globals()['historia_bridge'])
if '_rf_alias_app_patch_4522__previous' in globals(): setattr(_rf_snapshot_app_patch_4522, 'previous', globals()['_rf_alias_app_patch_4522__previous'])
if 'v4522_direct_delete_visit' in globals(): setattr(_rf_snapshot_app_patch_4522, 'v4522_direct_delete_visit', globals()['v4522_direct_delete_visit'])
if 'v4522_health' in globals(): setattr(_rf_snapshot_app_patch_4522, 'v4522_health', globals()['v4522_health'])
if 'v4522_restore_trash' in globals(): setattr(_rf_snapshot_app_patch_4522, 'v4522_restore_trash', globals()['v4522_restore_trash'])
if 'v4522_safe_delete_visit' in globals(): setattr(_rf_snapshot_app_patch_4522, 'v4522_safe_delete_visit', globals()['v4522_safe_delete_visit'])
_rf_layers['app_patch_4522'] = _rf_snapshot_app_patch_4522

# ---- app_patch_4523 ----
_rf_alias_app_patch_4523__previous = _rf_layers['app_patch_4522']
core = _rf_alias_app_patch_4523__previous.core
app = _rf_alias_app_patch_4523__previous.app
APP_VERSION = '4.5.23'
_mod = _rf_alias_app_patch_4523__previous
_seen = set()
for _ in range(620):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
V4523_CSS = '\n.v4523-bendo-extra{\n  grid-column:1/-1;\n  display:grid;\n  grid-template-columns:minmax(0,1fr) minmax(0,1fr);\n  gap:8px\n}\n.v4523-bendo-extra label{\n  display:block;\n  margin-bottom:4px;\n  color:#73869a;\n  font-size:7.5px;\n  font-weight:900;\n  text-transform:uppercase\n}\n.v4523-bendo-extra input,\n.v4523-bendo-extra select{\n  width:100%;\n  height:34px!important;\n  border:1px solid #d1dde8!important;\n  border-radius:8px!important;\n  background:#fff!important;\n  color:#344d66!important;\n  font-size:9px!important;\n  box-sizing:border-box!important\n}\n.v4523-no-operation{\n  grid-column:1/-1;\n  display:flex;\n  align-items:center;\n  gap:7px;\n  min-height:30px;\n  padding:5px 8px;\n  border:1px dashed #d6e0e8;\n  border-radius:8px;\n  background:#fbfcfe;\n  color:#61758a;\n  font-size:8px;\n  font-weight:800\n}\n.v4523-no-operation input{\n  width:14px!important;\n  height:14px!important;\n  margin:0!important\n}\n.v4523-bendo-summary{\n  margin-top:9px;\n  padding:9px 10px;\n  border:1px solid #b8dfc6;\n  border-radius:10px;\n  background:#f1faf4;\n  color:#285f40\n}\n.v4523-bendo-summary strong{\n  display:block;\n  font-size:9px;\n  font-weight:950\n}\n.v4523-bendo-summary span{\n  display:block;\n  margin-top:3px;\n  font-size:8.5px;\n  line-height:1.35\n}\n.v4507-bendo-actions .approve:disabled{\n  opacity:.45!important;\n  cursor:not-allowed!important\n}\n.v4523-reconfirm{\n  background:#fff4df!important;\n  border-color:#e7c780!important;\n  color:#7d5a16!important\n}\n@media(max-width:780px){\n  .v4523-bendo-extra{grid-template-columns:1fr}\n}\n'
V4523_JS = '\n;(()=>{\n  if(window.__v4523BendoOperation)return;\n  window.__v4523BendoOperation=true;\n\n  const q=(s,r=document)=>r.querySelector(s);\n  const qa=(s,r=document)=>[...r.querySelectorAll(s)];\n  const money=n=>\'$\'+Number(n||0).toFixed(2);\n\n  const ui=window.__v4523BendoUiState||{\n    operation:\'\',\n    noOperation:false,\n    brand:\'\',\n    last4:\'\',\n    approvedSnapshot:\'\'\n  };\n  window.__v4523BendoUiState=ui;\n\n  function total(){\n    try{\n      return Math.round(Number(window.__v4504PaymentTest?.total?.()||0)*100)/100;\n    }catch(_e){return 0}\n  }\n\n  function flow(){\n    return q(\'.attention-form-modal #v4507BendoFlow\');\n  }\n\n  function active(){\n    return !!flow();\n  }\n\n  function cardType(){\n    const selected=q(\'#v4507BendoFlow [data-v4507-cardtype].selected\');\n    return String(selected?.dataset?.v4507Cardtype||\'\').toUpperCase();\n  }\n\n  function cardTypeLabel(){\n    const type=cardType();\n    return type===\'CREDITO\'?\'Crédito\':type===\'DEBITO\'?\'Débito\':\'Tarjeta\';\n  }\n\n  function cleanOperation(value){\n    return String(value||\'\')\n      .toUpperCase()\n      .replace(/[^A-Z0-9._-]/g,\'\')\n      .slice(0,18);\n  }\n\n  function cleanLast4(value){\n    return String(value||\'\').replace(/\\D/g,\'\').slice(0,4);\n  }\n\n  function referenceValue(){\n    const parts=[];\n    if(ui.noOperation) parts.push(\'SIN-OPERACION\');\n    else if(cleanOperation(ui.operation)) parts.push(cleanOperation(ui.operation));\n    if(ui.brand) parts.push(String(ui.brand).toUpperCase().slice(0,10));\n    if(ui.last4) parts.push(cleanLast4(ui.last4));\n    return parts.join(\'/\').slice(0,32);\n  }\n\n  function snapshot(){\n    return [\n      Number(total()).toFixed(2),\n      cardType(),\n      ui.noOperation?\'SIN-OPERACION\':cleanOperation(ui.operation),\n      String(ui.brand||\'\').toUpperCase(),\n      cleanLast4(ui.last4)\n    ].join(\'|\');\n  }\n\n  function resetUi(){\n    ui.operation=\'\';\n    ui.noOperation=false;\n    ui.brand=\'\';\n    ui.last4=\'\';\n    ui.approvedSnapshot=\'\';\n  }\n\n  function invalidateApproval(){\n    ui.approvedSnapshot=\'\';\n    const button=q(\'#v4507Approve\');\n    if(button?.classList.contains(\'done\')){\n      button.textContent=\'⚠ Volver a confirmar PAGO EXITOSO\';\n      button.classList.add(\'v4523-reconfirm\');\n    }\n    const result=q(\'#v4507BendoFlow .v4507-bendo-result\');\n    if(result){\n      result.classList.remove(\'ok\');\n      result.textContent=\'Los datos cambiaron. Confirma nuevamente el pago en Bendo.\';\n    }\n    q(\'#v4523BendoSummary\')?.remove();\n  }\n\n  function validateMeta(show=true){\n    const amount=total();\n    if(amount<=0){\n      if(show) alert(\'Selecciona primero la consulta o procedimiento.\');\n      return false;\n    }\n    if(!cardType()){\n      if(show) alert(\'Selecciona primero Débito o Crédito.\');\n      return false;\n    }\n    if(!ui.noOperation && !cleanOperation(ui.operation)){\n      if(show) alert(\'Ingresa el N.º de operación que muestra Bendo o marca “N.º no disponible”.\');\n      return false;\n    }\n    if(ui.last4 && cleanLast4(ui.last4).length!==4){\n      if(show) alert(\'Los últimos 4 dígitos deben tener exactamente 4 números o quedar vacíos.\');\n      return false;\n    }\n    return true;\n  }\n\n  function summaryText(){\n    const bits=[money(total()),cardTypeLabel()];\n    bits.push(ui.noOperation?\'Op. no disponible\':\'Op. \'+cleanOperation(ui.operation));\n    if(ui.brand) bits.push(String(ui.brand).toUpperCase());\n    if(ui.last4) bits.push(\'••••\'+cleanLast4(ui.last4));\n    return bits.join(\' · \');\n  }\n\n  function approvalQuestion(){\n    return \'CONFIRMAR COBRO BENDO\\n\\n\'\n      +\'Monto: \'+money(total())+\'\\n\'\n      +\'Tipo: \'+cardTypeLabel()+\'\\n\'\n      +(ui.noOperation?\'N.º operación: no disponible\':\'N.º operación: \'+cleanOperation(ui.operation))+\'\\n\'\n      +(ui.brand?\'Marca: \'+String(ui.brand).toUpperCase()+\'\\n\':\'\')\n      +(ui.last4?\'Tarjeta: ••••\'+cleanLast4(ui.last4)+\'\\n\':\'\')\n      +\'\\nConfirma únicamente si el Bendo muestra PAGO EXITOSO.\';\n  }\n\n  function patchConfig(){\n    const section=q(\'[data-config-section="dataphone"]\');\n    if(!section)return;\n\n    qa(\'.v4507-config-row\',section).forEach(row=>{\n      const left=row.querySelector(\'span\');\n      const right=row.querySelector(\'b\');\n      const text=String(left?.textContent||\'\').trim().toLowerCase();\n      if(text.includes(\'voucher\')||text.includes(\'autorización\')){\n        if(left) left.textContent=\'N.º de operación Bendo\';\n        if(right) right.textContent=\'Sí · preferido\';\n      }\n    });\n\n    const registerCard=qa(\'.v4507-config-card\',section).find(card=>\n      String(card.querySelector(\'h4\')?.textContent||\'\').includes(\'Qué registra Recepción\')\n    );\n    if(registerCard && !q(\'[data-v4523-meta-row]\',registerCard)){\n      const list=q(\'.v4507-config-list\',registerCard);\n      if(list){\n        const row=document.createElement(\'div\');\n        row.className=\'v4507-config-row\';\n        row.dataset.v4523MetaRow=\'1\';\n        row.innerHTML=\'<span>Marca / últimos 4</span><b>Opcional</b>\';\n        const sensitive=qa(\'.v4507-config-row\',list).find(x=>\n          String(x.textContent||\'\').includes(\'Número de tarjeta\')\n        );\n        if(sensitive) sensitive.insertAdjacentElement(\'beforebegin\',row);\n        else list.appendChild(row);\n      }\n    }\n\n    const future=q(\'.v4507-future\',section);\n    if(future && future.dataset.v4523Done!==\'1\'){\n      future.dataset.v4523Done=\'1\';\n      future.innerHTML=\'<b>Estado confirmado:</b> Bendo Smart trabaja actualmente con protocolo cerrado. \'\n        +\'Recepción mantiene el paso manual y queda preparada para una integración futura si Bendo habilita API/ECR/SDK.\';\n    }\n  }\n\n  function patchFlow(){\n    const host=flow();\n    if(!host)return;\n\n    const amount=total();\n    const op=q(\'#v4507Voucher\',host);\n    if(op){\n      const label=op.closest(\'.v4507-bendo-field\')?.querySelector(\'label\');\n      if(label) label.textContent=\'N.º de operación Bendo\';\n      op.placeholder=ui.noOperation?\'Marcado como no disponible\':\'Ej. 535650\';\n      op.inputMode=\'numeric\';\n      op.autocomplete=\'off\';\n      op.disabled=!!ui.noOperation;\n\n      if(!op.dataset.v4523Bound){\n        op.dataset.v4523Bound=\'1\';\n        if(!ui.operation && op.value) ui.operation=cleanOperation(op.value);\n        op.addEventListener(\'input\',()=>{\n          const cleaned=cleanOperation(op.value);\n          if(op.value!==cleaned) op.value=cleaned;\n          ui.operation=cleaned;\n          invalidateApproval();\n        });\n      }\n\n      if(document.activeElement!==op && !ui.noOperation && op.value!==ui.operation){\n        op.value=ui.operation;\n        op.dispatchEvent(new Event(\'input\',{bubbles:true}));\n      }\n    }\n\n    const fields=q(\'.v4507-bendo-fields\',host);\n    if(fields && !q(\'#v4523BendoExtra\',fields)){\n      const extra=document.createElement(\'div\');\n      extra.id=\'v4523BendoExtra\';\n      extra.className=\'v4523-bendo-extra\';\n      extra.innerHTML=\n        \'<div><label for="v4523Brand">Marca (opcional)</label>\'\n        +\'<select id="v4523Brand">\'\n        +\'<option value="">—</option>\'\n        +\'<option value="VISA">Visa</option>\'\n        +\'<option value="MASTERCARD">Mastercard</option>\'\n        +\'<option value="DINERS">Diners</option>\'\n        +\'<option value="AMEX">American Express</option>\'\n        +\'<option value="DISCOVER">Discover</option>\'\n        +\'<option value="OTRA">Otra</option>\'\n        +\'</select></div>\'\n        +\'<div><label for="v4523Last4">Últimos 4 (opcional)</label>\'\n        +\'<input id="v4523Last4" type="text" inputmode="numeric" maxlength="4" placeholder="4545"></div>\'\n        +\'<label class="v4523-no-operation"><input id="v4523NoOperation" type="checkbox"> \'\n        +\'N.º de operación no disponible</label>\';\n      fields.appendChild(extra);\n\n      const brand=q(\'#v4523Brand\',extra);\n      const last4=q(\'#v4523Last4\',extra);\n      const noOp=q(\'#v4523NoOperation\',extra);\n      if(brand){\n        brand.value=ui.brand||\'\';\n        brand.addEventListener(\'change\',()=>{\n          ui.brand=String(brand.value||\'\').toUpperCase();\n          invalidateApproval();\n        });\n      }\n      if(last4){\n        last4.value=ui.last4||\'\';\n        last4.addEventListener(\'input\',()=>{\n          const cleaned=cleanLast4(last4.value);\n          if(last4.value!==cleaned)last4.value=cleaned;\n          ui.last4=cleaned;\n          invalidateApproval();\n        });\n      }\n      if(noOp){\n        noOp.checked=!!ui.noOperation;\n        noOp.addEventListener(\'change\',()=>{\n          ui.noOperation=!!noOp.checked;\n          const backing=q(\'#v4507Voucher\',host);\n          if(ui.noOperation && backing){\n            backing.value=\'\';\n            backing.dispatchEvent(new Event(\'input\',{bubbles:true}));\n          }\n          invalidateApproval();\n          patchFlow();\n        });\n      }\n    }else{\n      const brand=q(\'#v4523Brand\',host);\n      const last4=q(\'#v4523Last4\',host);\n      const noOp=q(\'#v4523NoOperation\',host);\n      if(brand && brand.value!==(ui.brand||\'\')) brand.value=ui.brand||\'\';\n      if(last4 && document.activeElement!==last4 && last4.value!==(ui.last4||\'\')) last4.value=ui.last4||\'\';\n      if(noOp) noOp.checked=!!ui.noOperation;\n    }\n\n    const step3=qa(\'.v4507-bendo-step\',host).find(x=>\n      String(x.querySelector(\'span\')?.textContent||\'\').includes(\'3\')\n    );\n    if(step3){\n      const b=step3.querySelector(\'b\');\n      if(b)b.textContent=\'Cuando Bendo muestre PAGO EXITOSO, confirma aquí.\';\n    }\n\n    const approve=q(\'#v4507Approve\',host);\n    if(approve){\n      approve.disabled=amount<=0;\n      approve.title=amount<=0?\'Selecciona primero una consulta o procedimiento.\':\'Confirma solo después de ver PAGO EXITOSO en Bendo.\';\n\n      if(!approve.dataset.v4523Guard){\n        approve.dataset.v4523Guard=\'1\';\n        approve.addEventListener(\'click\',event=>{\n          if(!validateMeta(true)){\n            event.preventDefault();\n            event.stopPropagation();\n            event.stopImmediatePropagation();\n            return;\n          }\n          if(!window.confirm(approvalQuestion())){\n            event.preventDefault();\n            event.stopPropagation();\n            event.stopImmediatePropagation();\n            return;\n          }\n          ui.approvedSnapshot=snapshot();\n          requestAnimationFrame(patchFlow);\n        },true);\n      }\n\n      if(approve.classList.contains(\'done\')){\n        if(ui.approvedSnapshot===snapshot()){\n          approve.classList.remove(\'v4523-reconfirm\');\n          approve.textContent=\'✓ BENDO: PAGO APROBADO\';\n        }else{\n          approve.classList.add(\'v4523-reconfirm\');\n          approve.textContent=\'⚠ Volver a confirmar PAGO EXITOSO\';\n        }\n      }\n    }\n\n    const result=q(\'.v4507-bendo-result\',host);\n    if(result){\n      if(approve?.classList.contains(\'done\') && ui.approvedSnapshot===snapshot()){\n        result.classList.add(\'ok\');\n        result.textContent=\'✓ Pago verificado · listo para guardar\';\n      }else if(amount<=0){\n        result.classList.remove(\'ok\');\n        result.textContent=\'Selecciona una consulta o procedimiento para continuar.\';\n      }else{\n        result.classList.remove(\'ok\');\n        result.textContent=\'Cuando Bendo muestre PAGO EXITOSO, confirma aquí.\';\n      }\n    }\n\n    q(\'#v4523BendoSummary\',host)?.remove();\n    if(approve?.classList.contains(\'done\') && ui.approvedSnapshot===snapshot()){\n      const summary=document.createElement(\'div\');\n      summary.id=\'v4523BendoSummary\';\n      summary.className=\'v4523-bendo-summary\';\n      summary.innerHTML=\'<strong>✓ COBRO BENDO VERIFICADO</strong><span></span>\';\n      q(\'span\',summary).textContent=summaryText();\n      const warning=q(\'.v4507-bendo-warning\',host);\n      if(warning) warning.insertAdjacentElement(\'beforebegin\',summary);\n      else q(\'.v4507-bendo-body\',host)?.appendChild(summary);\n    }\n  }\n\n  document.addEventListener(\'click\',event=>{\n    if(event.target?.closest?.(\n      \'#v4507BendoFlow [data-v4507-cardtype],\'\n      +\'#v4507BendoFlow [data-v4507-plan],\'\n      +\'.attention-form-modal .service-card\'\n    )){\n      ui.approvedSnapshot=\'\';\n      setTimeout(patchFlow,70);\n      return;\n    }\n\n    if(event.isTrusted && event.target?.closest?.(\n      \'#v4507CancelCard,\'\n      +\'.attention-form-modal [data-mode="EFECTIVO"],\'\n      +\'.attention-form-modal [data-mode="TRANSFERENCIA"],\'\n      +\'.attention-form-modal [data-mode="MIXTO"]\'\n    )){\n      resetUi();\n    }\n  },true);\n\n  const stableAttentionFor=window.attentionFor;\n  if(typeof stableAttentionFor===\'function\' && !stableAttentionFor.__v4523){\n    const wrappedAttentionFor=async function(){\n      resetUi();\n      const result=await stableAttentionFor.apply(this,arguments);\n      setTimeout(()=>{patchFlow();patchConfig()},70);\n      setTimeout(()=>{patchFlow();patchConfig()},220);\n      return result;\n    };\n    wrappedAttentionFor.__v4523=true;\n    window.attentionFor=wrappedAttentionFor;\n  }\n\n  const stableSave=window.saveAttention;\n  if(typeof stableSave===\'function\' && !stableSave.__v4523){\n    const wrapped=async function(){\n      if(!active()){\n        return await stableSave.apply(this,arguments);\n      }\n\n      if(!validateMeta(true)){\n        patchFlow();\n        return;\n      }\n      if(ui.approvedSnapshot!==snapshot()){\n        alert(\'Confirma nuevamente el PAGO EXITOSO en Bendo antes de guardar.\');\n        patchFlow();\n        return;\n      }\n\n      const previousWindowApi=window.api;\n      let previousApi=null;\n      try{previousApi=api}catch(_e){}\n      const downstream=previousWindowApi||previousApi;\n\n      if(typeof downstream!==\'function\'){\n        alert(\'No se pudo preparar el registro del cobro. Cierra y vuelve a abrir Nueva atención.\');\n        return;\n      }\n\n      const intercept=async function(url,opt={}){\n        if(String(url)===\'/api/visits/batch-payment\'){\n          let body={};\n          try{body=JSON.parse(opt?.body||\'{}\')}catch(_e){body={}}\n          body.card_reference=referenceValue();\n          delete body.voucher;\n          return downstream(url,{...opt,body:JSON.stringify(body)});\n        }\n        return downstream(url,opt);\n      };\n\n      try{\n        window.api=intercept;\n        try{api=intercept}catch(_e){}\n        return await stableSave.apply(this,arguments);\n      }finally{\n        window.api=previousWindowApi;\n        try{api=previousApi}catch(_e){}\n      }\n    };\n    wrapped.__v4523=true;\n    window.saveAttention=wrapped;\n  }\n\n  function boot(){\n    patchFlow();\n    patchConfig();\n  }\n\n  if(document.readyState===\'loading\'){\n    document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  }else{\n    boot();\n  }\n\n  // v4.5.24: no observamos todo el DOM. El flujo se actualiza únicamente\n  // en apertura de atención y eventos relevantes, evitando repintados en bucle.\n  window.addEventListener(\'focus\',()=>requestAnimationFrame(boot));\n  setTimeout(boot,180);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4523_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4523_JS

@app.get('/api/v4523/health')
def v4523_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'bendo_manual_flow': True, 'bendo_operation_reference': True, 'bendo_brand_optional': True, 'bendo_last4_optional': True, 'bendo_operation_unavailable_explicit': True, 'bendo_payment_success_confirmation': True, 'zero_amount_approval_blocked': True, 'card_reference_mapping_fixed': True, 'stores_pan': False, 'stores_cvv': False, 'database_schema_changes': False, 'azur_contract_changes': False, 'neon_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4523 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4523, '__name__', 'app_patch_4523')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4523, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4523, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4523_CSS' in globals(): setattr(_rf_snapshot_app_patch_4523, 'V4523_CSS', globals()['V4523_CSS'])
if 'V4523_JS' in globals(): setattr(_rf_snapshot_app_patch_4523, 'V4523_JS', globals()['V4523_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4523, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4523, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4523, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4523, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4523, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4523, 'core', globals()['core'])
if '_rf_alias_app_patch_4523__previous' in globals(): setattr(_rf_snapshot_app_patch_4523, 'previous', globals()['_rf_alias_app_patch_4523__previous'])
if 'v4523_health' in globals(): setattr(_rf_snapshot_app_patch_4523, 'v4523_health', globals()['v4523_health'])
_rf_layers['app_patch_4523'] = _rf_snapshot_app_patch_4523

# ---- app_patch_4524 ----
_rf_alias_app_patch_4524__previous = _rf_layers['app_patch_4523']
_rf_alias_app_patch_4524__bridge_v4508 = _rf_layers['app_patch_4508']
import historia_bridge
core = _rf_alias_app_patch_4524__previous.core
app = _rf_alias_app_patch_4524__previous.app
APP_VERSION = '4.5.24'
_mod = _rf_alias_app_patch_4524__previous
_seen = set()
for _ in range(680):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)
_TYPE_LABELS = {'N': 'Nuevo', 'S': 'Subsecuente', 'P': 'Procedimiento', 'X': 'Procedimiento'}

@app.post('/api/visits/batch-payment')
def v4524_create_visit_batch_payment(data: _rf_alias_app_patch_4524__bridge_v4508.payment_core.V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    result = _rf_alias_app_patch_4524__bridge_v4508._old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            items = list((result or {}).get('items') or []) if isinstance(result, dict) else []
            visit_ids = [x.get('id') for x in items if isinstance(x, dict) and x.get('id') is not None]
            type_code = ''
            if items and isinstance(items[0], dict):
                type_code = str(items[0].get('tipo') or '').strip().upper()
            if not type_code:
                type_code = str(getattr(data, 'tipo', '') or '').strip().upper()
            attention_type = _TYPE_LABELS.get(type_code)
            if not attention_type:
                attention_type = 'Subsecuente' if type_code == 'S' else 'Nuevo' if type_code == 'N' else 'Consulta'
            birth = getattr(patient, 'fecha_nacimiento', None)
            historia_bridge.queue_attention(reception_patient_id=int(patient.id), display_name=str(getattr(patient, 'nombre', '') or 'Paciente'), identification=str(getattr(patient, 'cedula', '') or ''), attention_type=attention_type, visit_ids=visit_ids, birth_date=str(birth or ''), phone=str(getattr(patient, 'celular', '') or ''), email=str(getattr(patient, 'correo', '') or ''), address=str(getattr(patient, 'lugar', '') or ''))
    except Exception as exc:
        try:
            core.audit(db, user, 'historia_bridge_pending', f'Puente Historia Clínica pendiente: {type(exc).__name__}')
            db.commit()
        except Exception:
            pass
    return result

@app.get('/api/v4524/health')
def v4524_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_new_patient_demographics': True, 'fields': ['birth_date', 'phone', 'email', 'address'], 'clinical_notes_shared': False, 'database_schema_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4524 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4524, '__name__', 'app_patch_4524')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4524, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4524, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4524, '_', globals()['_'])
if '_TYPE_LABELS' in globals(): setattr(_rf_snapshot_app_patch_4524, '_TYPE_LABELS', globals()['_TYPE_LABELS'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4524, '_mod', globals()['_mod'])
if '_route' in globals(): setattr(_rf_snapshot_app_patch_4524, '_route', globals()['_route'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4524, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4524, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4524, 'app', globals()['app'])
if '_rf_alias_app_patch_4524__bridge_v4508' in globals(): setattr(_rf_snapshot_app_patch_4524, 'bridge_v4508', globals()['_rf_alias_app_patch_4524__bridge_v4508'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4524, 'core', globals()['core'])
if 'historia_bridge' in globals(): setattr(_rf_snapshot_app_patch_4524, 'historia_bridge', globals()['historia_bridge'])
if '_rf_alias_app_patch_4524__previous' in globals(): setattr(_rf_snapshot_app_patch_4524, 'previous', globals()['_rf_alias_app_patch_4524__previous'])
if 'v4524_create_visit_batch_payment' in globals(): setattr(_rf_snapshot_app_patch_4524, 'v4524_create_visit_batch_payment', globals()['v4524_create_visit_batch_payment'])
if 'v4524_health' in globals(): setattr(_rf_snapshot_app_patch_4524, 'v4524_health', globals()['v4524_health'])
_rf_layers['app_patch_4524'] = _rf_snapshot_app_patch_4524

# ---- app_patch_4525 ----
_rf_alias_app_patch_4525__previous = _rf_layers['app_patch_4524']
core = _rf_alias_app_patch_4525__previous.core
app = _rf_alias_app_patch_4525__previous.app
APP_VERSION = '4.5.25'
_mod = _rf_alias_app_patch_4525__previous
_seen = set()
for _ in range(720):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
V4525_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.25"!important;\n  font-size:9px!important;\n  font-weight:850!important\n}\n.attention-form-modal [data-mode="TARJETA"],\n.attention-form-modal [data-v4507-card="1"]{\n  border-style:solid!important;\n  cursor:pointer!important\n}\n.v4525-bendo{\n  margin-top:10px;\n  border:1px solid #cadbea;\n  border-radius:14px;\n  background:#fff;\n  overflow:hidden\n}\n.v4525-head{\n  display:flex;\n  align-items:center;\n  justify-content:space-between;\n  gap:12px;\n  padding:12px 14px;\n  background:#eef6ff;\n  border-bottom:1px solid #dce8f2\n}\n.v4525-head small{\n  display:block;\n  color:#6d8297;\n  font-size:8px;\n  font-weight:900\n}\n.v4525-head strong{\n  display:block;\n  margin-top:2px;\n  color:#244e74;\n  font-size:13px\n}\n.v4525-amount{\n  min-width:120px;\n  padding:7px 11px;\n  border-radius:10px;\n  background:#173f65;\n  color:#fff;\n  text-align:center\n}\n.v4525-amount span{\n  display:block;\n  font-size:7px;\n  font-weight:850\n}\n.v4525-amount b{\n  display:block;\n  font-size:22px;\n  line-height:1.05\n}\n.v4525-body{padding:12px 14px}\n.v4525-types{\n  display:grid;\n  grid-template-columns:repeat(2,minmax(0,1fr));\n  gap:8px\n}\n.v4525-types button{\n  min-height:36px!important;\n  border:1px solid #d3dee8!important;\n  border-radius:9px!important;\n  background:#fff!important;\n  color:#50677e!important;\n  font-size:9px!important;\n  font-weight:900!important\n}\n.v4525-types button.selected{\n  border-color:#7aa7cf!important;\n  background:#eaf4ff!important;\n  color:#235c8e!important\n}\n.v4525-meta{\n  display:grid;\n  grid-template-columns:minmax(0,1fr) 150px 110px;\n  gap:8px;\n  margin-top:9px\n}\n.v4525-meta label{\n  display:block;\n  margin-bottom:4px;\n  color:#71859a;\n  font-size:7.5px;\n  font-weight:900;\n  text-transform:uppercase\n}\n.v4525-meta input,.v4525-meta select{\n  width:100%;\n  height:34px!important;\n  border-radius:8px!important;\n  font-size:9px!important\n}\n.v4525-noop{\n  display:flex;\n  align-items:center;\n  gap:6px;\n  margin-top:8px;\n  color:#647b90;\n  font-size:8.5px\n}\n.v4525-noop input{width:auto!important}\n.v4525-actions{\n  display:flex;\n  gap:8px;\n  align-items:center;\n  flex-wrap:wrap;\n  margin-top:10px\n}\n.v4525-actions button{\n  min-height:36px!important;\n  border-radius:9px!important;\n  font-size:9px!important;\n  font-weight:900!important\n}\n#v4525Approve{\n  background:#2f7a51!important;\n  border-color:#2f7a51!important;\n  color:#fff!important\n}\n#v4525Approve.done{\n  background:#e7f7ed!important;\n  border-color:#a9d8b9!important;\n  color:#246440!important\n}\n.v4525-status{\n  flex:1;\n  min-width:180px;\n  color:#708399;\n  font-size:8.5px\n}\n.v4525-status.ok{color:#276a46;font-weight:900}\n.v4525-warning{\n  margin-top:9px;\n  padding:8px 10px;\n  border-radius:9px;\n  background:#fff8e9;\n  color:#80611f;\n  font-size:8px;\n  line-height:1.35\n}\n@media(max-width:780px){\n  .v4525-meta{grid-template-columns:1fr}\n  .v4525-types{grid-template-columns:1fr}\n}\n'
V4525_JS = '\n;(()=>{\n  if(window.__v4525BendoHotfix)return;\n  window.__v4525BendoHotfix=true;\n\n  const q=(s,r=document)=>r.querySelector(s);\n  const qa=(s,r=document)=>[...r.querySelectorAll(s)];\n  const money=n=>\'$\'+Number(n||0).toFixed(2);\n\n  const state={\n    active:false,\n    type:\'\',\n    operation:\'\',\n    noOperation:false,\n    brand:\'\',\n    last4:\'\',\n    approvedKey:\'\'\n  };\n\n  function total(){\n    try{\n      return Math.round(Number(window.__v4504PaymentTest?.total?.()||0)*100)/100;\n    }catch(_e){return 0}\n  }\n  function cleanOp(v){\n    return String(v||\'\').toUpperCase().replace(/[^A-Z0-9._-]/g,\'\').slice(0,18)\n  }\n  function cleanLast4(v){\n    return String(v||\'\').replace(/\\D/g,\'\').slice(0,4)\n  }\n  function key(){\n    return [\n      total().toFixed(2),\n      state.type,\n      state.noOperation?\'SIN-OPERACION\':cleanOp(state.operation),\n      String(state.brand||\'\').toUpperCase(),\n      cleanLast4(state.last4)\n    ].join(\'|\')\n  }\n  function reference(){\n    const bits=[];\n    bits.push(state.noOperation?\'SIN-OPERACION\':cleanOp(state.operation));\n    if(state.brand)bits.push(String(state.brand).toUpperCase().slice(0,10));\n    if(state.last4)bits.push(cleanLast4(state.last4));\n    return bits.filter(Boolean).join(\'/\').slice(0,32)\n  }\n  function host(){\n    return q(\'.attention-form-modal #v4504Payment\')\n  }\n  function markCard(){\n    const h=host(); if(!h)return;\n    const card=q(\'[data-mode="TARJETA"],[data-v4507-card="1"]\',h);\n    if(!card)return;\n    const title=q(\'b\',card),small=q(\'small\',card);\n    if(title)title.textContent=\'Tarjeta\';\n    if(small)small.textContent=\'Bendo Smart · manual\';\n    card.classList.toggle(\'selected\',state.active);\n    qa(\'.v4504-pay-option\',h).forEach(b=>{\n      if(state.active && b!==card)b.classList.remove(\'selected\');\n    });\n    const st=q(\'.v4504-pay-state\',h);\n    if(st&&state.active){\n      st.textContent=state.approvedKey===key()\n        ?\'✓ Tarjeta · Bendo aprobado\'\n        :\'Tarjeta · pendiente de cobro\';\n    }\n  }\n  function invalidate(){\n    state.approvedKey=\'\';\n  }\n  function render(){\n    const h=host(); if(!h)return;\n    markCard();\n    let panel=q(\'#v4525Bendo\',h);\n    if(!state.active){panel?.remove();return}\n    if(!panel){\n      panel=document.createElement(\'div\');\n      panel.id=\'v4525Bendo\';\n      panel.className=\'v4525-bendo\';\n      const opts=q(\'.v4504-pay-options\',h);\n      if(opts)opts.insertAdjacentElement(\'afterend\',panel);\n      else h.appendChild(panel);\n    }\n    const amt=total();\n    const approved=state.approvedKey && state.approvedKey===key();\n    panel.innerHTML=\n      \'<div class="v4525-head">\'\n      +\'<div><small>COBRO CON TARJETA</small><strong>Bendo Smart · operación manual</strong></div>\'\n      +\'<div class="v4525-amount"><span>DIGITAR EN BENDO</span><b>\'+money(amt)+\'</b></div>\'\n      +\'</div><div class="v4525-body">\'\n      +\'<div class="v4525-types">\'\n      +\'<button type="button" data-v4525-type="DEBITO" class="\'+(state.type===\'DEBITO\'?\'selected\':\'\')+\'">Débito · SRI 16</button>\'\n      +\'<button type="button" data-v4525-type="CREDITO" class="\'+(state.type===\'CREDITO\'?\'selected\':\'\')+\'">Crédito · SRI 19</button>\'\n      +\'</div>\'\n      +\'<div class="v4525-meta">\'\n      +\'<div><label>N.º de operación Bendo</label><input id="v4525Operation" maxlength="18" value="\'+String(state.operation||\'\')+\'" \'+(state.noOperation?\'disabled\':\'\')+\' placeholder="Ej. 123456"></div>\'\n      +\'<div><label>Marca</label><select id="v4525Brand"><option value="">Opcional</option><option>VISA</option><option>MASTERCARD</option><option>DINERS</option><option>AMEX</option><option>OTRA</option></select></div>\'\n      +\'<div><label>Últimos 4</label><input id="v4525Last4" maxlength="4" inputmode="numeric" value="\'+String(state.last4||\'\')+\'" placeholder="1234"></div>\'\n      +\'</div>\'\n      +\'<label class="v4525-noop"><input id="v4525NoOperation" type="checkbox" \'+(state.noOperation?\'checked\':\'\')+\'> N.º de operación no disponible</label>\'\n      +\'<div class="v4525-actions">\'\n      +\'<button type="button" id="v4525Approve" class="\'+(approved?\'done\':\'\')+\'">\'+(approved?\'✓ PAGO EXITOSO confirmado\':\'Confirmar PAGO EXITOSO\')+\'</button>\'\n      +\'<button type="button" id="v4525Cancel">Cambiar forma de pago</button>\'\n      +\'<span class="v4525-status \'+(approved?\'ok\':\'\')+\'">\'+(approved?\'✓ Listo para guardar\':\'Esperando confirmación del Bendo Smart\')+\'</span>\'\n      +\'</div>\'\n      +\'<div class="v4525-warning">Confirma únicamente después de ver <b>PAGO EXITOSO</b> en el Bendo. Recepción no controla el terminal y no guarda PAN ni CVV.</div>\'\n      +\'</div>\';\n\n    const brand=q(\'#v4525Brand\',panel);\n    if(brand)brand.value=state.brand||\'\';\n\n    qa(\'[data-v4525-type]\',panel).forEach(b=>b.addEventListener(\'click\',()=>{\n      state.type=b.dataset.v4525Type||\'\';\n      invalidate();render();\n    }));\n    q(\'#v4525Operation\',panel)?.addEventListener(\'input\',e=>{\n      state.operation=cleanOp(e.target.value);invalidate();\n    });\n    brand?.addEventListener(\'change\',e=>{\n      state.brand=e.target.value||\'\';invalidate();\n    });\n    q(\'#v4525Last4\',panel)?.addEventListener(\'input\',e=>{\n      state.last4=cleanLast4(e.target.value);invalidate();\n    });\n    q(\'#v4525NoOperation\',panel)?.addEventListener(\'change\',e=>{\n      state.noOperation=!!e.target.checked;\n      if(state.noOperation)state.operation=\'\';\n      invalidate();render();\n    });\n    q(\'#v4525Approve\',panel)?.addEventListener(\'click\',()=>{\n      if(amt<=0){alert(\'Selecciona primero una consulta o procedimiento.\');return}\n      if(!state.type){alert(\'Selecciona Débito o Crédito.\');return}\n      if(!state.noOperation&&!cleanOp(state.operation)){\n        alert(\'Ingresa el N.º de operación Bendo o marca “N.º de operación no disponible”.\');\n        return\n      }\n      if(state.last4&&cleanLast4(state.last4).length!==4){\n        alert(\'Los últimos 4 dígitos deben tener 4 números o quedar vacíos.\');\n        return\n      }\n      if(!confirm(\n        \'CONFIRMAR COBRO BENDO\\\\n\\\\nMonto: \'+money(amt)\n        +\'\\\\nTipo: \'+(state.type===\'CREDITO\'?\'Crédito\':\'Débito\')\n        +\'\\\\n\'+(state.noOperation?\'N.º operación: no disponible\':\'N.º operación: \'+cleanOp(state.operation))\n        +\'\\\\n\\\\nConfirma únicamente si Bendo muestra PAGO EXITOSO.\'\n      ))return;\n      state.approvedKey=key();render();\n    });\n    q(\'#v4525Cancel\',panel)?.addEventListener(\'click\',()=>{\n      state.active=false;state.type=\'\';state.approvedKey=\'\';\n      render();\n    });\n  }\n\n  // Enganche principal: funciona aunque el modal se haya creado después.\n  document.addEventListener(\'click\',event=>{\n    const card=event.target?.closest?.(\n      \'.attention-form-modal [data-mode="TARJETA"],\'\n      +\'.attention-form-modal [data-v4507-card="1"]\'\n    );\n    if(card){\n      event.preventDefault();\n      event.stopPropagation();\n      event.stopImmediatePropagation();\n      state.active=true;\n      invalidate();\n      render();\n      return;\n    }\n\n    const other=event.target?.closest?.(\n      \'.attention-form-modal [data-mode="EFECTIVO"],\'\n      +\'.attention-form-modal [data-mode="TRANSFERENCIA"],\'\n      +\'.attention-form-modal [data-mode="MIXTO"]\'\n    );\n    if(other&&state.active){\n      state.active=false;\n      state.approvedKey=\'\';\n      q(\'#v4525Bendo\')?.remove();\n    }\n\n    if(state.active&&event.target?.closest?.(\'.attention-form-modal .service-card\')){\n      invalidate();\n      requestAnimationFrame(render);\n    }\n  },true);\n\n  const stableSave=window.saveAttention;\n  if(typeof stableSave===\'function\'&&!stableSave.__v4525){\n    const wrapped=async function(){\n      if(!state.active)return await stableSave.apply(this,arguments);\n\n      const amt=total();\n      if(amt<=0){alert(\'Selecciona primero una consulta o procedimiento.\');return}\n      if(!state.type){alert(\'Selecciona Débito o Crédito.\');return}\n      if(!state.noOperation&&!cleanOp(state.operation)){\n        alert(\'Ingresa el N.º de operación Bendo o marca que no está disponible.\');return\n      }\n      if(!state.approvedKey||state.approvedKey!==key()){\n        alert(\'Primero confirma que Bendo mostró PAGO EXITOSO.\');return\n      }\n\n      const cash=q(\'.attention-form-modal [data-mode="EFECTIVO"]\');\n      if(!cash){alert(\'No se pudo preparar el guardado. Cierra y vuelve a abrir Nueva atención.\');return}\n\n      // Selección interna compatible con la capa base, sin abandonar Bendo.\n      const wasActive=state.active;\n      state.active=false;\n      cash.click();\n      state.active=wasActive;\n\n      const replacement={\n        payment_method:state.type===\'CREDITO\'?\'TARJETA_CREDITO\':\'TARJETA_DEBITO\',\n        card_plan:state.type===\'CREDITO\'?\'CORRIENTE\':null,\n        installments:state.type===\'CREDITO\'?1:null,\n        voucher:reference()\n      };\n\n      const previousWindowApi=window.api;\n      const previousApi=typeof api!==\'undefined\'?api:null;\n      const downstream=previousWindowApi||previousApi;\n      if(typeof downstream!==\'function\'){\n        alert(\'No se pudo preparar el guardado de tarjeta.\');return\n      }\n      const intercept=async function(url,opt={}){\n        if(String(url)===\'/api/visits/batch-payment\'){\n          let body={};\n          try{body=JSON.parse(opt?.body||\'{}\')}catch(_e){}\n          Object.assign(body,replacement);\n          return downstream(url,{...opt,body:JSON.stringify(body)});\n        }\n        return downstream(url,opt);\n      };\n      try{\n        window.api=intercept;\n        try{api=intercept}catch(_e){}\n        return await stableSave.apply(this,arguments);\n      }finally{\n        window.api=previousWindowApi;\n        try{api=previousApi}catch(_e){}\n      }\n    };\n    wrapped.__v4525=true;\n    window.saveAttention=wrapped;\n  }\n\n  // Corrige el texto viejo si el modal ya estaba abierto al cargar este script.\n  function repairVisibleCard(){\n    const h=host(); if(!h)return;\n    const card=q(\'[data-mode="TARJETA"],[data-v4507-card="1"]\',h);\n    if(!card)return;\n    const title=q(\'b\',card),small=q(\'small\',card);\n    if(title)title.textContent=\'Tarjeta\';\n    if(small)small.textContent=\'Bendo Smart · manual\';\n  }\n  repairVisibleCard();\n  window.addEventListener(\'focus\',repairVisibleCard);\n})();\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4525_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4525_JS

@app.get('/api/v4525/health')
def v4525_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'card_click_direct_mount': True, 'mutation_observer': False, 'timing_dependency': False, 'bendo_manual_assisted': True, 'operation_reference': True, 'brand_optional': True, 'last4_optional': True, 'approved_confirmation_required': True, 'database_schema_changes': False, 'historia_changes': False}
PATCH_BOOT_OK = True

_rf_snapshot_app_patch_4525 = _rf_types.SimpleNamespace()
setattr(_rf_snapshot_app_patch_4525, '__name__', 'app_patch_4525')
if 'APP_VERSION' in globals(): setattr(_rf_snapshot_app_patch_4525, 'APP_VERSION', globals()['APP_VERSION'])
if 'PATCH_BOOT_OK' in globals(): setattr(_rf_snapshot_app_patch_4525, 'PATCH_BOOT_OK', globals()['PATCH_BOOT_OK'])
if 'V4525_CSS' in globals(): setattr(_rf_snapshot_app_patch_4525, 'V4525_CSS', globals()['V4525_CSS'])
if 'V4525_JS' in globals(): setattr(_rf_snapshot_app_patch_4525, 'V4525_JS', globals()['V4525_JS'])
if '_' in globals(): setattr(_rf_snapshot_app_patch_4525, '_', globals()['_'])
if '_mod' in globals(): setattr(_rf_snapshot_app_patch_4525, '_mod', globals()['_mod'])
if '_seen' in globals(): setattr(_rf_snapshot_app_patch_4525, '_seen', globals()['_seen'])
if 'annotations' in globals(): setattr(_rf_snapshot_app_patch_4525, 'annotations', globals()['annotations'])
if 'app' in globals(): setattr(_rf_snapshot_app_patch_4525, 'app', globals()['app'])
if 'core' in globals(): setattr(_rf_snapshot_app_patch_4525, 'core', globals()['core'])
if '_rf_alias_app_patch_4525__previous' in globals(): setattr(_rf_snapshot_app_patch_4525, 'previous', globals()['_rf_alias_app_patch_4525__previous'])
if 'v4525_health' in globals(): setattr(_rf_snapshot_app_patch_4525, 'v4525_health', globals()['v4525_health'])
_rf_layers['app_patch_4525'] = _rf_snapshot_app_patch_4525

