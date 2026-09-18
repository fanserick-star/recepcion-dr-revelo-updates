from __future__ import annotations

# v4.5.4 — cobros preparados para datáfono + mejora visual.
# No añade cierre de caja, no crea tablas y no guarda PAN/CVV.

import base64
import json
import re
import sys
from datetime import date as _date

import app_patch_4502 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.4"

_mod = previous
_seen = set()
for _ in range(120):
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
ROUTES_REPLACED = 0

PAYMENT_SENTINELS = {
    "EFECTIVO": -442901,
    "TRANSFERENCIA": -442920,
    "TARJETA_DEBITO": -442916,
    "TARJETA_CREDITO": -442919,
    "MIXTO": -442999,
}
SRI_CODES = {
    "EFECTIVO": "01",
    "TRANSFERENCIA": "20",
    "TARJETA_DEBITO": "16",
    "TARJETA_CREDITO": "19",
}
PAYMENT_LABELS = {
    "EFECTIVO": "EFECTIVO",
    "TRANSFERENCIA": "TRANSFERENCIA BANCARIA",
    "TARJETA_DEBITO": "TARJETA DE DÉBITO",
    "TARJETA_CREDITO": "TARJETA DE CRÉDITO",
    "MIXTO": "PAGO MIXTO",
}
CARD_METHODS = {"TARJETA_DEBITO", "TARJETA_CREDITO"}
PAY_RE = re.compile(r"\s*(?:\|\s*)?\[\[RP_PAY_V1:([A-Za-z0-9_-]+)\]\]")


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _normalize_method(value: object, allow_mixed: bool = True) -> str:
    raw = " ".join(str(value or "").strip().upper().split())
    raw = {
        "TRANSFERENCIA BANCARIA": "TRANSFERENCIA",
        "BANCO": "TRANSFERENCIA",
        "CASH": "EFECTIVO",
        "DEBITO": "TARJETA_DEBITO",
        "DÉBITO": "TARJETA_DEBITO",
        "TARJETA DE DEBITO": "TARJETA_DEBITO",
        "TARJETA DE DÉBITO": "TARJETA_DEBITO",
        "CREDITO": "TARJETA_CREDITO",
        "CRÉDITO": "TARJETA_CREDITO",
        "TARJETA DE CREDITO": "TARJETA_CREDITO",
        "TARJETA DE CRÉDITO": "TARJETA_CREDITO",
        "PAGO MIXTO": "MIXTO",
    }.get(raw, raw)
    valid = set(PAYMENT_SENTINELS)
    if not allow_mixed:
        valid.discard("MIXTO")
    if raw == "TARJETA":
        raise core.HTTPException(400, "Selecciona si la tarjeta es Débito o Crédito.")
    if raw not in valid:
        raise core.HTTPException(
            400,
            "Selecciona Efectivo, Transferencia, Tarjeta o Pago mixto.",
        )
    return raw


def _clean_voucher(value: object) -> str:
    raw = " ".join(str(value or "").strip().split())
    if len(raw) > 40:
        raise core.HTTPException(400, "El voucher/autorización es demasiado largo.")
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 13:
        raise core.HTTPException(
            400,
            "No guardes el número de la tarjeta. Ingresa solo voucher/autorización.",
        )
    return raw


def _card_details(method: str, plan=None, installments=None, voucher=None) -> dict:
    if method not in CARD_METHODS:
        return {}
    out = {"voucher": _clean_voucher(voucher)}
    if method == "TARJETA_DEBITO":
        out["plan"] = None
        out["installments"] = None
        return out

    raw_plan = " ".join(str(plan or "CORRIENTE").strip().upper().split())
    raw_plan = {"DIFERIDA": "DIFERIDO", "CUOTAS": "DIFERIDO"}.get(raw_plan, raw_plan)
    if raw_plan not in {"CORRIENTE", "DIFERIDO"}:
        raise core.HTTPException(400, "Selecciona Corriente o Diferido.")
    out["plan"] = raw_plan
    if raw_plan == "DIFERIDO":
        try:
            qty = int(installments or 0)
        except Exception:
            qty = 0
        if qty < 2 or qty > 99:
            raise core.HTTPException(400, "Ingresa una cantidad válida de cuotas.")
        out["installments"] = qty
    else:
        out["installments"] = 1
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


def _make_payment_info(
    method: object,
    total: float,
    payment_parts=None,
    card_plan=None,
    installments=None,
    voucher=None,
) -> dict:
    total = _money(total)
    if total <= 0:
        raise core.HTTPException(400, "El total a cobrar debe ser mayor a cero.")

    method = _normalize_method(method)
    if method != "MIXTO":
        part = {"method": method, "amount": total, "sri_code": SRI_CODES[method]}
        part.update(_card_details(method, card_plan, installments, voucher))
        return {"version": 1, "method": method, "total": total, "parts": [part]}

    raw_parts = list(payment_parts or [])
    if len(raw_parts) < 2 or len(raw_parts) > 4:
        raise core.HTTPException(400, "Pago mixto requiere entre 2 y 4 partes.")

    parts = []
    methods = set()
    running = 0.0
    for raw in raw_parts:
        part_method = _normalize_method(getattr(raw, "method", None), False)
        amount = _money(getattr(raw, "amount", 0))
        if amount <= 0:
            raise core.HTTPException(400, "Cada parte del pago mixto debe ser mayor a cero.")
        methods.add(part_method)
        running = _money(running + amount)
        part = {
            "method": part_method,
            "amount": amount,
            "sri_code": SRI_CODES[part_method],
        }
        part.update(_card_details(
            part_method,
            getattr(raw, "card_plan", None),
            getattr(raw, "installments", None),
            getattr(raw, "voucher", None),
        ))
        parts.append(part)

    if len(methods) < 2:
        raise core.HTTPException(400, "Pago mixto debe combinar dos formas distintas.")
    if abs(running - total) > 0.009:
        raise core.HTTPException(
            400,
            "El pago mixto suma $" + f"{running:.2f}" +
            ", pero el total es $" + f"{total:.2f}" + ".",
        )
    return {"version": 1, "method": "MIXTO", "total": total, "parts": parts}


def _encode_marker(info: dict) -> str:
    raw = json.dumps(info, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return "[[RP_PAY_V1:" + token + "]]"


def _strip_marker(value: object) -> str:
    text = PAY_RE.sub("", str(value or ""))
    text = re.sub(r"\s*\|\s*\|\s*", " | ", text)
    return text.strip(" |")


def _with_marker(value: object, info: dict | None):
    clean = _strip_marker(value)
    if not info:
        return clean or None
    marker = _encode_marker(info)
    return (clean + " | " + marker) if clean else marker


def _decode_marker(value: object):
    match = PAY_RE.search(str(value or ""))
    if not match:
        return None
    try:
        token = match.group(1)
        token += "=" * ((4 - len(token) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _payment_info_from_visits(visits):
    rows = sorted(list(visits or []), key=lambda v: abs(int(getattr(v, "id", 0) or 0)))
    total = _money(sum(_money(getattr(v, "valor", 0)) for v in rows))

    for visit in rows:
        info = _decode_marker(getattr(visit, "observacion", None))
        if info:
            info = dict(info)
            info["total"] = total
            if info.get("method") != "MIXTO" and info.get("parts"):
                info["parts"][0]["amount"] = total
            return info

    reverse = {value: method for method, value in PAYMENT_SENTINELS.items()}
    totals = {}
    for visit in rows:
        try:
            method = reverse.get(int(getattr(visit, "source_row", 0) or 0))
        except Exception:
            method = None
        if method and method != "MIXTO":
            totals[method] = _money(totals.get(method, 0) + _money(visit.valor))

    if len(totals) == 1:
        method = next(iter(totals))
        return {
            "version": 0,
            "method": method,
            "total": total,
            "parts": [{"method": method, "amount": total, "sri_code": SRI_CODES[method]}],
        }
    if len(totals) > 1:
        return {
            "version": 0,
            "method": "MIXTO",
            "total": total,
            "parts": [
                {"method": method, "amount": amount, "sri_code": SRI_CODES[method]}
                for method, amount in totals.items()
            ],
        }
    return None


def _payment_label_from_visits(visits):
    info = _payment_info_from_visits(visits)
    return PAYMENT_LABELS.get(str((info or {}).get("method") or ""), "NO REGISTRADA")


def _apply_payment(visits, info: dict):
    rows = sorted(list(visits or []), key=lambda v: abs(int(getattr(v, "id", 0) or 0)))
    sentinel = PAYMENT_SENTINELS[str(info.get("method") or "")]
    for index, visit in enumerate(rows):
        visit.source_row = sentinel
        visit.observacion = _with_marker(
            getattr(visit, "observacion", None),
            info if index == 0 else None,
        )


def _remove_route(path: str, method: str) -> int:
    wanted = str(method).upper()
    kept = []
    removed = 0
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in (getattr(route, "methods", None) or set())}
        if getattr(route, "path", None) == path and wanted in methods:
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
        queued = list(db.scalars(
            core.select(core.OfflineQueue).where(
                core.OfflineQueue.operation == "visit.create",
                core.OfflineQueue.local_entity_id == int(visit.id),
            )
        ))
        for item in queued:
            try:
                payload = core.json.loads(item.payload or "{}")
            except Exception:
                payload = {}
            payload["source_row"] = visit.source_row
            payload["observacion"] = visit.observacion
            item.payload = core.json.dumps(payload, ensure_ascii=False)
    except Exception:
        pass


try:
    legacy = sys.modules.get("app_prev_4458")
    if legacy is not None:
        try:
            legacy.PAYMENT_SENTINELS.update(PAYMENT_SENTINELS)
            legacy.SRI_PAYMENT_CODES.update(SRI_CODES)
        except Exception:
            pass

    ROUTES_REPLACED += _remove_route("/api/visits/batch-payment", "POST")
    ROUTES_REPLACED += _remove_route("/api/billing/payment-method", "POST")
    ROUTES_REPLACED += _remove_route("/api/billing/payment-methods", "GET")

    @app.post("/api/visits/batch-payment")
    def v4504_create_visit_batch_payment(
        data: V4504VisitBatchPaymentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        if not data.services:
            raise core.HTTPException(400, "Selecciona al menos una atención")

        override = (data.tipo or "").strip().upper()
        if override and override not in {"N", "S"}:
            raise core.HTTPException(400, "Estado de paciente inválido")

        prior = db.scalar(
            core.select(core.func.count(core.Visit.id)).where(
                core.Visit.patient_id == int(patient.id)
            )
        ) or 0
        historical_prior = bool(not prior and core.historical_summary_for_patient(patient))
        first_type = override or ("S" if prior or historical_prior else "N")

        normalized = []
        seen = set()
        has_consultation = False
        for item in data.services:
            procedure = (item.procedimiento or "").strip().upper() or None
            key = procedure or "CONSULTA"
            if key in seen:
                continue
            seen.add(key)
            if procedure is None:
                has_consultation = True
                value = (
                    previous.CONSULT_COUPLE_TOTAL
                    if bool(data.couple_discount)
                    else previous.CONSULT_BASE
                )
            else:
                value = _money(item.valor)
            if value is None:
                raise core.HTTPException(400, "Ingresa el valor de " + key)
            value = _money(value)
            if value < 0:
                raise core.HTTPException(400, "Valor inválido para " + key)
            normalized.append((procedure, value))

        existing = list(db.scalars(
            core.select(core.Visit)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.patient_id == int(data.patient_id),
                core.Visit.fecha == data.fecha,
                core.BillingRecord.estado != "EMITIDA",
            )
            .order_by(core.Visit.id)
        ))

        requested_method = _normalize_method(data.payment_method)
        if requested_method == "MIXTO" and existing:
            raise core.HTTPException(
                409,
                "Este paciente ya tiene cobros abiertos del mismo día. "
                "Guarda con una forma simple y ajusta Pago mixto desde Facturación.",
            )

        new_total = _money(sum(value for _procedure, value in normalized))
        info = _make_payment_info(
            requested_method,
            new_total,
            data.payment_parts,
            data.card_plan,
            data.installments,
            data.voucher,
        )

        discount_applied = bool(data.couple_discount and has_consultation)
        offline = core.is_offline_db(db)
        created = []
        specs = []
        for index, (procedure, value) in enumerate(normalized):
            tipo = first_type if index == 0 else "S"
            observation = data.observacion
            if procedure is None and discount_applied:
                observation = previous._discount_observation(data.observacion)
            visit = core.Visit(
                patient_id=int(data.patient_id),
                fecha=data.fecha,
                tipo=tipo,
                procedimiento=procedure,
                valor=value,
                observacion=observation,
                source_row=PAYMENT_SENTINELS[info["method"]],
            )
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedure, value))

        db.flush()
        all_open = [*existing, *created]
        group_total = _money(sum(_money(v.valor) for v in all_open))
        if info["method"] != "MIXTO":
            info = _make_payment_info(
                info["method"],
                group_total,
                None,
                data.card_plan,
                data.installments,
                data.voucher,
            )
        _apply_payment(all_open, info)

        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado="PENDIENTE")
            db.add(billing)
            billings.append(billing)

        for visit, tipo, procedure, value in specs:
            service_name = procedure or "CONSULTA"
            if offline:
                payload = {
                    "patient_id": int(data.patient_id),
                    "fecha": data.fecha.isoformat(),
                    "tipo": tipo,
                    "procedimiento": procedure,
                    "valor": value,
                    "observacion": visit.observacion,
                    "source_row": visit.source_row,
                }
                core.add_queue(
                    db, "visit.create", "visit", payload,
                    user.username, int(visit.id),
                )
                core.audit(
                    db, user, "crear_atencion_multiple_offline",
                    "Atención local " + str(visit.id) + ", paciente " +
                    str(patient.id) + ", " + service_name,
                )
            else:
                core.audit(
                    db, user, "crear_atencion_multiple",
                    "Atención " + str(visit.id) + ", paciente " +
                    str(patient.id) + ", servicio " + service_name,
                )
            if procedure is None and discount_applied:
                core.audit(
                    db, user, "aplicar_descuento_pareja",
                    "Consulta base $40.00, descuento $10.00, total $30.00",
                )

        if offline:
            for visit in all_open:
                _update_offline_payload(db, visit)

        detail = PAYMENT_LABELS[info["method"]]
        if info["method"] == "MIXTO":
            detail += " · " + " + ".join(
                PAYMENT_LABELS[p["method"]] + " $" + f"{_money(p['amount']):.2f}"
                for p in info["parts"]
            )
        core.audit(db, user, "registrar_forma_pago_atencion", detail)
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

        return {
            "ok": True,
            "count": len(created),
            "items": [core.v_dict(v) for v in created],
            "offline": offline,
            "payment_method": info["method"],
            "payment_label": PAYMENT_LABELS[info["method"]],
            "payment_parts": info["parts"],
            "couple_discount": discount_applied,
            "consultation_total": (
                previous.CONSULT_COUPLE_TOTAL
                if discount_applied and has_consultation
                else (previous.CONSULT_BASE if has_consultation else None)
            ),
        }

    @app.get("/api/billing/payment-methods")
    def v4504_billing_payment_methods(
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(core.BillingRecord.estado != "EMITIDA")
            .order_by(core.Visit.fecha.desc(), core.Visit.patient_id, core.Visit.id)
        ).all()
        grouped = {}
        for visit, _billing in rows:
            grouped.setdefault(
                (int(visit.patient_id), visit.fecha.isoformat()), []
            ).append(visit)

        items = []
        for (patient_id, fecha), visits in grouped.items():
            info = _payment_info_from_visits(visits)
            method = str((info or {}).get("method") or "")
            items.append({
                "patient_id": patient_id,
                "fecha": fecha,
                "payment_method": method or None,
                "payment_label": PAYMENT_LABELS.get(method),
                "payment_parts": list((info or {}).get("parts") or []),
                "mixed": method == "MIXTO",
                "total": _money(sum(_money(v.valor) for v in visits)),
            })
        return {"items": items}

    @app.post("/api/billing/payment-method")
    def v4504_set_billing_payment_method(
        data: V4504BillingPaymentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        if core.is_offline_db(db):
            raise core.HTTPException(
                503,
                "Conéctate a Internet para cambiar la forma de pago desde Facturación.",
            )

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
        if "EMITIDA" in {str(b.estado or "").upper() for _v, b in rows}:
            raise core.HTTPException(409, "La factura ya fue emitida.")

        visits = [visit for visit, _billing in rows]
        total = _money(sum(_money(v.valor) for v in visits))
        info = _make_payment_info(
            data.payment_method,
            total,
            data.payment_parts,
            data.card_plan,
            data.installments,
            data.voucher,
        )
        _apply_payment(visits, info)
        core.audit(
            db, user, "registrar_forma_pago_facturacion",
            PAYMENT_LABELS[info["method"]],
        )
        db.commit()
        for visit in visits:
            try:
                core.mirror_visit_to_local(visit)
            except Exception:
                pass

        return {
            "ok": True,
            "payment_method": info["method"],
            "payment_label": PAYMENT_LABELS[info["method"]],
            "payment_parts": info["parts"],
        }

    base_payload = (
        getattr(legacy, "_stable_azur_payload_for_group", None)
        if legacy is not None else None
    ) or core._azur_payload_for_group

    def v4504_azur_payload_for_group(data, patient, rows):
        payload = base_payload(data, patient, rows)
        visits = [visit for _billing, visit in rows]
        total = _money(sum(_money(v.valor) for v in visits))
        info = _payment_info_from_visits(visits)
        if not info:
            raise core.HTTPException(
                409,
                "La forma de pago no está registrada.",
            )

        if info.get("method") == "MIXTO":
            parts = list(info.get("parts") or [])
            running = _money(sum(_money(p.get("amount")) for p in parts))
            if not parts or abs(running - total) > 0.009:
                raise core.HTTPException(
                    409,
                    "El Pago mixto no coincide con el total. Corrígelo antes de emitir.",
                )
            totals = {}
            for part in parts:
                code = str(part.get("sri_code") or SRI_CODES.get(part.get("method")) or "")
                amount = _money(part.get("amount"))
                if code and amount > 0:
                    totals[code] = _money(totals.get(code, 0) + amount)
        else:
            method = str(info.get("method") or "")
            code = SRI_CODES.get(method)
            if not code:
                raise core.HTTPException(409, "Forma de pago inválida.")
            totals = {code: total}

        payload["pagos"] = [
            {"tipo": code, "total": amount, "tiempo": "dias", "plazo": 0}
            for code, amount in sorted(totals.items())
        ]
        return payload

    core._azur_payload_for_group = v4504_azur_payload_for_group

    proof_mod = sys.modules.get("app_patch_4485")
    if proof_mod is not None:
        proof_mod._PAYMENT_SENTINELS = {
            value: PAYMENT_LABELS[method]
            for method, value in PAYMENT_SENTINELS.items()
        }
        proof_mod._payment_method_for_visits = _payment_label_from_visits

    @app.get("/api/v4504/day-summary")
    def v4504_day_summary(
        fecha: str,
        user=core.Depends(core.current_user),
    ):
        try:
            target = _date.fromisoformat(str(fecha or "")[:10])
        except Exception:
            raise core.HTTPException(400, "Fecha inválida")

        with core.LocalSessionLocal() as db:
            visits = list(db.scalars(
                core.select(core.Visit)
                .where(core.Visit.fecha == target)
                .order_by(core.Visit.patient_id, core.Visit.id)
            ))
            grouped = {}
            for visit in visits:
                grouped.setdefault(int(visit.patient_id), []).append(visit)

            amounts = {"efectivo": 0.0, "transferencia": 0.0, "tarjeta": 0.0}
            mixed_groups = 0
            discount_count = 0
            for group in grouped.values():
                info = _payment_info_from_visits(group)
                if info:
                    if info.get("method") == "MIXTO":
                        mixed_groups += 1
                    for part in info.get("parts") or []:
                        method = str(part.get("method") or "")
                        amount = _money(part.get("amount"))
                        if method == "EFECTIVO":
                            amounts["efectivo"] = _money(amounts["efectivo"] + amount)
                        elif method == "TRANSFERENCIA":
                            amounts["transferencia"] = _money(amounts["transferencia"] + amount)
                        elif method in CARD_METHODS:
                            amounts["tarjeta"] = _money(amounts["tarjeta"] + amount)
                discount_count += sum(
                    1 for v in group
                    if "DESCUENTO PAREJA" in str(v.observacion or "").upper()
                )

            pending_rows = db.execute(
                core.select(core.Visit, core.BillingRecord)
                .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
                .where(
                    core.Visit.fecha == target,
                    core.BillingRecord.estado != "EMITIDA",
                )
            ).all()
            pending_ids = {int(v.patient_id) for v, _b in pending_rows}
            missing_id = 0
            for pid in pending_ids:
                patient = db.get(core.Patient, pid)
                if patient and not str(patient.cedula or "").strip():
                    missing_id += 1

        return {
            "ok": True,
            "fecha": target.isoformat(),
            "payments": amounts,
            "mixed_groups": mixed_groups,
            "discounts": {
                "count": discount_count,
                "amount": _money(discount_count * previous.COUPLE_DISCOUNT),
            },
            "pending": {
                "billing_groups": len(pending_ids),
                "missing_identification": missing_id,
            },
            "local_only": True,
        }

    V4504_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{content:"v4.5.4"!important;font-size:9px!important;line-height:1!important;font-weight:850!important}
#v4451AttentionPayment{display:none!important}
.modalbox.attention-form-modal{border-radius:17px!important;box-shadow:0 22px 58px rgba(29,51,79,.18)!important}
.attention-form-modal .service-card{border-radius:12px!important}
.v4504-pay{margin:12px 0 10px;padding:13px;border:1px solid #d8e3ee;border-radius:14px;background:#f8fbff}
.v4504-pay.required{border-color:#d9a23d;background:#fffaf0;box-shadow:0 0 0 3px rgba(217,162,61,.09)}
.v4504-pay-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}
.v4504-pay-head b{font-size:11px;color:#203c5b}.v4504-pay-head small{display:block;margin-top:2px;font-size:8px;color:#71859a}
.v4504-pay-state{padding:4px 8px;border-radius:999px;background:#edf2f7;color:#66788d;font-size:8px;font-weight:900;white-space:nowrap}.v4504-pay-state.ready{background:#e5f5eb;color:#286b46}
.v4504-pay-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}
.v4504-pay-option{min-height:52px!important;border:1px solid #d0dce8!important;border-radius:11px!important;background:#fff!important;color:#3f5871!important;padding:8px 9px!important;box-shadow:none!important;display:grid!important;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:7px;text-align:left!important}
.v4504-pay-option>span{grid-row:1/3;font-size:17px;align-self:center}.v4504-pay-option>b{font-size:9px}.v4504-pay-option>small{font-size:7.5px;color:#8190a1}.v4504-pay-option.selected{border-color:#6ea88a!important;background:#edf8f2!important;color:#245e41!important}
.v4504-details{margin-top:9px;padding:10px;border:1px solid #e1e8f0;border-radius:11px;background:#fff}.v4504-details.hidden{display:none!important}
.v4504-segment{display:flex;gap:6px;flex-wrap:wrap}.v4504-segment button{min-height:30px!important;padding:5px 9px!important;border-radius:8px!important;border:1px solid #d4dee8!important;background:#fff!important;color:#52677e!important;font-size:8px!important;font-weight:850!important;box-shadow:none!important}.v4504-segment button.selected{background:#eaf4ff!important;border-color:#89add2!important;color:#285d92!important}
.v4504-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:9px}.v4504-fields label{display:block;margin-bottom:4px;font-size:7.5px;font-weight:850;color:#75879a}.v4504-fields input{width:100%;height:34px!important;border-radius:8px!important;font-size:9px!important}
.v4504-mixed{display:grid;grid-template-columns:1.2fr .8fr 1.2fr .8fr;gap:7px}.v4504-mixed label{display:block;margin-bottom:4px;font-size:7.5px;font-weight:850;color:#75879a}.v4504-mixed select,.v4504-mixed input{width:100%;height:34px!important;border-radius:8px!important;font-size:9px!important}
.v4504-summary{margin:10px 0 12px;border:1px solid #d8e3ed;border-radius:14px;background:#fff;overflow:hidden}.v4504-summary-head{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;background:#f4f8fc;border-bottom:1px solid #e1e8ef}.v4504-summary-head b{font-size:9px;color:#657b92}.v4504-summary-head strong{font-size:18px;color:#1f4f7e}.v4504-summary-body{display:grid;grid-template-columns:1fr auto;gap:5px 12px;padding:10px 12px;font-size:9px;color:#536a82}.v4504-summary-body b{text-align:right;color:#2e536f}.v4504-discount{color:#347150!important}
.v4504-day-strip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:7px 0 10px;padding:7px 9px;border:1px solid #e0e7ef;border-radius:10px;background:#fbfcfe}.v4504-day-strip>span:first-child{font-size:7.5px;font-weight:950;color:#718399;letter-spacing:.08em}.v4504-day-pill{display:inline-flex;gap:4px;padding:4px 7px;border:1px solid #dce5ee;border-radius:999px;background:#fff;color:#536a82;font-size:8px;font-weight:800}.v4504-day-pill b{color:#274e76}.v4504-day-pill.warn{border-color:#ecd4a1;background:#fff8e8;color:#8b641d}
#facturacion .v4431-pay-wrap{display:none!important}#facturacion .billing-card{border-radius:14px!important}.v4504-billpay{margin:8px 0 10px;padding:9px;border:1px solid #d9e3ed;border-radius:11px;background:#f9fbfd}.v4504-billpay-head{display:flex;justify-content:space-between;margin-bottom:7px}.v4504-billpay-head span{font-size:8px;font-weight:950;color:#64798f}.v4504-billpay-head b{font-size:9px;color:#315978}.v4504-billchoices{display:flex;gap:5px;flex-wrap:wrap}.v4504-billchoices button{min-height:29px!important;padding:5px 8px!important;border-radius:8px!important;border:1px solid #d2dde8!important;background:#fff!important;color:#536a82!important;font-size:8px!important;font-weight:850!important;box-shadow:none!important}.v4504-billchoices button.selected{background:#eaf7ef!important;border-color:#79b291!important;color:#286344!important}
@media(max-width:760px){.v4504-pay-options{grid-template-columns:repeat(2,minmax(0,1fr))}.v4504-fields,.v4504-mixed{grid-template-columns:1fr 1fr}}
"""

    V4504_JS = r"""
;(()=>{
 if(window.__v4504Payments)return;window.__v4504Payments=true;
 const VERSION='4.5.4';
 let mode='',cardType='DEBITO',cardPlan='CORRIENTE',installments=3,voucher='';
 let mixA='EFECTIVO',mixB='TARJETA_DEBITO',mixAmount='';
 let billingMap=new Map(),billingBusy=false;
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const money=n=>'$'+Number(n||0).toFixed(2),key=(p,f)=>Number(p)+'|'+String(f||'').slice(0,10);
 const label=m=>({EFECTIVO:'Efectivo',TRANSFERENCIA:'Transferencia',TARJETA_DEBITO:'Débito',TARJETA_CREDITO:'Crédito',MIXTO:'Pago mixto'}[m]||m||'');
 function box(){return document.querySelector('.attention-form-modal')||[...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function cards(){const b=box();return b?[...new Set([...b.querySelectorAll('button.service-card.selected'),...b.querySelectorAll('button.service-card.is-selected')])]:[]}
 function cardVal(c){let t=String(q('.service-price',c)?.textContent||'').replace(',','.').replace(/[^\d.]/g,''),n=Number(t||0);if(!n)n=Number(q('input[type="number"]',c)?.value||0);return Number.isFinite(n)?Math.round(n*100)/100:0}
 function total(){return Math.round(cards().reduce((s,c)=>s+cardVal(c),0)*100)/100}
 function discounted(){try{return !!window.__v4502CoupleDiscountTest?.enabled?.()}catch(_e){return false}}
 function serverMethod(){if(mode==='EFECTIVO'||mode==='TRANSFERENCIA')return mode;if(mode==='TARJETA')return cardType==='CREDITO'?'TARJETA_CREDITO':'TARJETA_DEBITO';if(mode==='MIXTO')return 'MIXTO';return ''}
 function paymentText(){const m=serverMethod();if(m==='TARJETA_CREDITO')return cardPlan==='DIFERIDO'?'Crédito diferido · '+Number(installments||0)+' cuotas':'Tarjeta crédito · corriente';if(m==='MIXTO'){const a=Number(mixAmount||0),b=Math.max(0,total()-a);return 'Mixto · '+label(mixA)+' '+money(a)+' + '+label(mixB)+' '+money(b)}return label(m)||'Sin seleccionar'}
 function payload(){
   const t=total(),m=serverMethod();if(!m)throw Error('Selecciona la forma de pago.');if(t<=0)throw Error('Selecciona al menos una atención con valor.');
   const p={payment_method:m};
   if(m==='TARJETA_DEBITO'||m==='TARJETA_CREDITO'){p.card_plan=m==='TARJETA_CREDITO'?cardPlan:null;p.installments=m==='TARJETA_CREDITO'&&cardPlan==='DIFERIDO'?Number(installments||0):1;p.voucher=String(voucher||'').trim()}
   if(m==='MIXTO'){const a=Math.round(Number(mixAmount||0)*100)/100,b=Math.round((t-a)*100)/100;if(a<=0||b<=0)throw Error('En Pago mixto ambos valores deben ser mayores a $0.');if(mixA===mixB)throw Error('Selecciona dos formas distintas.');const mk=(x,v)=>({method:x,amount:v,card_plan:x==='TARJETA_CREDITO'?cardPlan:null,installments:x==='TARJETA_CREDITO'&&cardPlan==='DIFERIDO'?Number(installments||0):(x==='TARJETA_CREDITO'?1:null),voucher:x.indexOf('TARJETA')===0?String(voucher||'').trim():''});p.payment_parts=[mk(mixA,a),mk(mixB,b)]}
   return p;
 }
 function btn(m,ico,name,small){return '<button type="button" class="v4504-pay-option '+(mode===m?'selected':'')+'" data-mode="'+m+'"><span>'+ico+'</span><b>'+name+'</b><small>'+small+'</small></button>'}
 function render(){
   const b=box();if(!b)return;
   let host=q('#v4504Payment',b);if(!host){host=document.createElement('section');host.id='v4504Payment';host.className='v4504-pay';const old=q('#v4451AttentionPayment',b);if(old)old.insertAdjacentElement('afterend',host);else(q('.v492-sticky-actions',b)||q('.actions',b))?.insertAdjacentElement('beforebegin',host)}
   host.classList.toggle('required',!mode);
   host.innerHTML='<div class="v4504-pay-head"><div><b>Forma de pago</b><small>Obligatorio · preparado para datáfono y factura/SRI.</small></div><span class="v4504-pay-state '+(mode?'ready':'')+'">'+(mode?'✓ '+paymentText():'Sin seleccionar')+'</span></div><div class="v4504-pay-options">'+btn('EFECTIVO','💵','Efectivo','SRI 01')+btn('TRANSFERENCIA','🏦','Transferencia','SRI 20')+btn('TARJETA','💳','Tarjeta','Débito / Crédito')+btn('MIXTO','◫','Pago mixto','Combina 2 formas')+'</div><div id="v4504Card" class="v4504-details '+((mode==='TARJETA'||(mode==='MIXTO'&&(mixA.indexOf('TARJETA')===0||mixB.indexOf('TARJETA')===0)))?'':'hidden')+'"></div><div id="v4504Mixed" class="v4504-details '+(mode==='MIXTO'?'':'hidden')+'"></div>';
   qa('[data-mode]',host).forEach(x=>x.addEventListener('click',()=>{mode=x.dataset.mode||'';render()}));
   renderCard();renderMixed();renderSummary();
 }
 function renderCard(){const h=q('#v4504Card');if(!h||h.classList.contains('hidden'))return;const credit=(mode==='TARJETA'?cardType==='CREDITO':(mixA==='TARJETA_CREDITO'||mixB==='TARJETA_CREDITO'));h.innerHTML=(mode==='TARJETA'?'<div class="v4504-segment"><button type="button" data-ct="DEBITO" class="'+(cardType==='DEBITO'?'selected':'')+'">Débito · SRI 16</button><button type="button" data-ct="CREDITO" class="'+(cardType==='CREDITO'?'selected':'')+'">Crédito · SRI 19</button></div>':'')+(credit?'<div class="v4504-segment" style="margin-top:7px"><button type="button" data-cp="CORRIENTE" class="'+(cardPlan==='CORRIENTE'?'selected':'')+'">Corriente</button><button type="button" data-cp="DIFERIDO" class="'+(cardPlan==='DIFERIDO'?'selected':'')+'">Diferido</button></div>':'')+'<div class="v4504-fields">'+(credit&&cardPlan==='DIFERIDO'?'<div><label>Cuotas</label><input id="v4504Cuotas" type="number" min="2" max="99" value="'+Number(installments||3)+'"></div>':'')+'<div><label>Voucher / autorización</label><input id="v4504Voucher" maxlength="40" placeholder="Opcional" value="'+String(voucher||'').replace(/"/g,'&quot;')+'"></div><div><label>Seguridad</label><input disabled value="No se guarda tarjeta ni CVV"></div></div>';qa('[data-ct]',h).forEach(x=>x.addEventListener('click',()=>{cardType=x.dataset.ct;render()}));qa('[data-cp]',h).forEach(x=>x.addEventListener('click',()=>{cardPlan=x.dataset.cp;render()}));q('#v4504Cuotas',h)?.addEventListener('input',e=>{installments=Number(e.target.value||0);renderSummary()});q('#v4504Voucher',h)?.addEventListener('input',e=>{voucher=e.target.value})}
 function opts(selected){return ['EFECTIVO','TRANSFERENCIA','TARJETA_DEBITO','TARJETA_CREDITO'].map(x=>'<option value="'+x+'" '+(x===selected?'selected':'')+'>'+label(x)+'</option>').join('')}
 function renderMixed(){const h=q('#v4504Mixed');if(!h||mode!=='MIXTO')return;const rest=Math.max(0,Math.round((total()-Number(mixAmount||0))*100)/100);h.innerHTML='<div class="v4504-mixed"><div><label>Forma 1</label><select id="v4504MixA">'+opts(mixA)+'</select></div><div><label>Valor 1</label><input id="v4504MixAmount" type="number" min="0.01" step="0.01" value="'+mixAmount+'"></div><div><label>Forma 2</label><select id="v4504MixB">'+opts(mixB)+'</select></div><div><label>Valor 2</label><input disabled value="'+rest.toFixed(2)+'"></div></div><small style="display:block;margin-top:7px;color:#71859a;font-size:8px">El segundo valor se calcula automáticamente para que el total cuadre.</small>';q('#v4504MixA',h)?.addEventListener('change',e=>{mixA=e.target.value;render()});q('#v4504MixB',h)?.addEventListener('change',e=>{mixB=e.target.value;render()});q('#v4504MixAmount',h)?.addEventListener('input',e=>{mixAmount=e.target.value;renderCard();renderSummary()})}
 function renderSummary(){const b=box();if(!b)return;let s=q('#v4504Summary',b);if(!s){s=document.createElement('section');s.id='v4504Summary';s.className='v4504-summary';(q('.v492-sticky-actions',b)||q('.actions',b))?.insertAdjacentElement('beforebegin',s)}const cs=cards(),t=total();let rows=cs.length?cs.map(c=>'<span>'+String(c.dataset.service||q('strong,b',c)?.textContent||'Atención')+'</span><b>'+money(cardVal(c))+'</b>').join(''):'<span>Selecciona una atención</span><b>—</b>';if(discounted())rows+='<span class="v4504-discount">Descuento pareja</span><b class="v4504-discount">−$10.00</b>';rows+='<span>Forma de pago</span><b>'+paymentText()+'</b>';s.innerHTML='<div class="v4504-summary-head"><b>RESUMEN ANTES DE GUARDAR</b><strong>'+money(t)+'</strong></div><div class="v4504-summary-body">'+rows+'</div>'}
 function delayed(){setTimeout(render,0);setTimeout(render,100);setTimeout(render,260)}
 const oldAttention=window.attentionFor;if(typeof oldAttention==='function')window.attentionFor=async function(){mode='';cardType='DEBITO';cardPlan='CORRIENTE';installments=3;voucher='';mixA='EFECTIVO';mixB='TARJETA_DEBITO';mixAmount='';const out=await oldAttention.apply(this,arguments);delayed();return out};
 const oldSave=window.saveAttention;if(typeof oldSave==='function')window.saveAttention=async function(){let p;try{p=payload()}catch(e){q('#v4504Payment')?.classList.add('required');alert(e?.message||String(e));return}try{window.v4451ChooseAttentionPayment?.(p.payment_method==='TRANSFERENCIA'?'TRANSFERENCIA':'EFECTIVO')}catch(_e){}const stable=window.api||api,intercept=async function(url,opt={}){if(String(url)==='/api/visits/batch-payment'){let body={};try{body=JSON.parse(opt?.body||'{}')}catch(_e){}Object.assign(body,p);return stable(url,{...opt,body:JSON.stringify(body)})}return stable(url,opt)};const previousApi=api;try{api=intercept;return await oldSave.apply(this,arguments)}finally{api=previousApi}};
 document.addEventListener('click',e=>{if(e.target?.closest?.('.attention-form-modal .service-card')){setTimeout(render,30);setTimeout(render,170)}},true);
 document.addEventListener('change',e=>{if(e.target?.closest?.('.attention-form-modal'))setTimeout(render,30)},true);

 function cached(){try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}catch(_e){return []}}
 function identity(card){let pid=Number(card.dataset.patientId||0),fecha=String(card.dataset.fecha||'').slice(0,10);const list=qa('#billingList .billing-card'),idx=list.indexOf(card),g=idx>=0?cached()[idx]:null;if(!pid)pid=Number(g?.patient?.id||0);if(!fecha)fecha=String(g?.fecha||'').slice(0,10);if(!pid||!fecha)return null;card.dataset.patientId=String(pid);card.dataset.fecha=fecha;return{pid,fecha,total:Number(g?.total||0)}}
 async function loadBillingPayments(){if(billingBusy)return;billingBusy=true;try{const d=await api('/api/billing/payment-methods');billingMap=new Map((d?.items||[]).map(x=>[key(x.patient_id,x.fecha),x]));decorateBilling()}catch(_e){}finally{billingBusy=false}}
 async function saveBill(card,method,extra={}){const id=identity(card);if(!id)return;try{await api('/api/billing/payment-method',{method:'POST',body:JSON.stringify({patient_id:id.pid,fecha:id.fecha,payment_method:method,...extra})});await loadBillingPayments()}catch(e){alert(e?.message||String(e))}}
 function decorateBill(card){const id=identity(card);if(!id)return;const d=billingMap.get(key(id.pid,id.fecha))||{},selected=String(d.payment_method||'');let w=q('.v4504-billpay',card);if(!w){w=document.createElement('div');w.className='v4504-billpay';const a=q('.billing-actions',card);a?a.insertAdjacentElement('beforebegin',w):card.appendChild(w)}const b=(m,t)=>'<button type="button" data-bm="'+m+'" class="'+(selected===m?'selected':'')+'">'+t+'</button>';w.innerHTML='<div class="v4504-billpay-head"><span>Forma de pago</span><b>'+String(d.payment_label||'Sin seleccionar')+'</b></div><div class="v4504-billchoices">'+b('EFECTIVO','💵 Efectivo')+b('TRANSFERENCIA','🏦 Transferencia')+b('TARJETA_DEBITO','💳 Débito')+b('TARJETA_CREDITO','💳 Crédito')+b('MIXTO','◫ Mixto')+'</div>';qa('[data-bm]',w).forEach(x=>x.addEventListener('click',()=>{const m=x.dataset.bm;if(m==='MIXTO'){const total=Number(d.total||id.total||0),raw=prompt('Valor de la primera parte del pago mixto (total '+money(total)+')','');if(raw===null)return;const a=Math.round(Number(raw||0)*100)/100,bv=Math.round((total-a)*100)/100;if(a<=0||bv<=0){alert('El valor debe ser mayor a $0 y menor al total.');return}const first=prompt('Primera forma: EFECTIVO, TRANSFERENCIA, TARJETA_DEBITO o TARJETA_CREDITO','EFECTIVO');if(!first)return;const second=prompt('Segunda forma: EFECTIVO, TRANSFERENCIA, TARJETA_DEBITO o TARJETA_CREDITO','TARJETA_DEBITO');if(!second)return;const mk=(mm,v)=>({method:String(mm).toUpperCase(),amount:v,card_plan:String(mm).toUpperCase()==='TARJETA_CREDITO'?'CORRIENTE':null,installments:String(mm).toUpperCase()==='TARJETA_CREDITO'?1:null});saveBill(card,'MIXTO',{payment_parts:[mk(first,a),mk(second,bv)]})}else saveBill(card,m,m==='TARJETA_CREDITO'?{card_plan:'CORRIENTE',installments:1}:{})}))}
 function decorateBilling(){qa('#billingList .billing-card').forEach(decorateBill)}
 const oldLoadBilling=window.loadBilling;if(typeof oldLoadBilling==='function')window.loadBilling=async function(){const out=await oldLoadBilling.apply(this,arguments);await loadBillingPayments();return out};

 async function dayStrip(iso){try{const d=await api('/api/v4504/day-summary?fecha='+encodeURIComponent(String(iso||'').slice(0,10))),title=q('#selectedDayTitle');if(!title)return;let s=q('#v4504DayStrip');if(!s){s=document.createElement('div');s.id='v4504DayStrip';s.className='v4504-day-strip';title.insertAdjacentElement('afterend',s)}const p=d.payments||{},pd=d.pending||{},dc=d.discounts||{};let html='<span>COBROS</span><span class="v4504-day-pill">💵 <b>'+money(p.efectivo)+'</b></span><span class="v4504-day-pill">🏦 <b>'+money(p.transferencia)+'</b></span><span class="v4504-day-pill">💳 <b>'+money(p.tarjeta)+'</b></span>';if(Number(d.mixed_groups||0))html+='<span class="v4504-day-pill">◫ '+d.mixed_groups+' mixto(s)</span>';if(Number(dc.count||0))html+='<span class="v4504-day-pill">− '+dc.count+' descuento(s) · <b>'+money(dc.amount)+'</b></span>';if(Number(pd.billing_groups||0))html+='<span class="v4504-day-pill warn">Por facturar: <b>'+pd.billing_groups+'</b></span>';if(Number(pd.missing_identification||0))html+='<span class="v4504-day-pill warn">Sin identificación: <b>'+pd.missing_identification+'</b></span>';s.innerHTML=html}catch(_e){}}
 const oldRender=window.renderHomeDayPayload;if(typeof oldRender==='function')window.renderHomeDayPayload=function(iso,d){const out=oldRender.apply(this,arguments);setTimeout(()=>dayStrip(iso),20);return out};

 function boot(){qa('.v460-version,#currentVersionBadge').forEach(el=>{el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION)});delayed();if(q('#billingList'))loadBillingPayments()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
 window.__v4504PaymentTest={total,payload,render,refreshBilling:loadBillingPayments};
})();
"""

    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4504_CSS
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4504_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4504/health")
def v4504_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "routes_replaced": ROUTES_REPLACED,
        "sri_codes": {"cash": "01", "transfer": "20", "debit": "16", "credit": "19"},
        "mixed_payment": True,
        "card_sensitive_data_stored": False,
        "voucher_optional": True,
        "credit_current_or_deferred": True,
        "azur_payment_breakdown": True,
        "day_payment_strip": True,
        "cash_closing": False,
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
