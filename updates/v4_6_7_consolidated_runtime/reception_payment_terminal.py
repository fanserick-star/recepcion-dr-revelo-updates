from __future__ import annotations
import reception_consultation_discount as _dep_consultation_discount
import base64
import json
import re
import sys
from datetime import date as _date
core = _dep_consultation_discount.core
app = _dep_consultation_discount.app
APP_VERSION = '4.5.4'
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
    legacy = sys.modules.get('reception_payments_and_agenda')
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
                value = _dep_consultation_discount.CONSULT_COUPLE_TOTAL if bool(data.couple_discount) else _dep_consultation_discount.CONSULT_BASE
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
                observation = _dep_consultation_discount._discount_observation(data.observacion)
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
        return {'ok': True, 'count': len(created), 'items': [core.v_dict(v) for v in created], 'offline': offline, 'payment_method': info['method'], 'payment_label': PAYMENT_LABELS[info['method']], 'payment_parts': info['parts'], 'couple_discount': discount_applied, 'consultation_total': _dep_consultation_discount.CONSULT_COUPLE_TOTAL if discount_applied and has_consultation else _dep_consultation_discount.CONSULT_BASE if has_consultation else None}

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
    proof_mod = sys.modules.get('reception_payment_proof')
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
        return {'ok': True, 'fecha': target.isoformat(), 'payments': amounts, 'mixed_groups': mixed_groups, 'discounts': {'count': discount_count, 'amount': _money(discount_count * _dep_consultation_discount.COUPLE_DISCOUNT)}, 'pending': {'billing_groups': len(pending_ids), 'missing_identification': missing_id}, 'local_only': True}
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
