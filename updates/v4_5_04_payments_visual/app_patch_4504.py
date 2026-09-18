from __future__ import annotations

# v4.5.4 — cobros preparados para datáfono + pulido visual.
# Efectivo, transferencia, débito, crédito y pago mixto.
# No guarda PAN/CVV. Voucher/autorización es opcional.

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
ROUTES_REPLACED = {}

CONSULT_BASE = 40.0
COUPLE_DISCOUNT = 10.0
CONSULT_COUPLE_TOTAL = 30.0

PAYMENT_SENTINELS = {
    "EFECTIVO": -442901,
    "TRANSFERENCIA": -442920,
    "TARJETA_DEBITO": -442916,
    "TARJETA_CREDITO": -442919,
    "MIXTO": -442999,
}
SENTINEL_TO_METHOD = {value: key for key, value in PAYMENT_SENTINELS.items()}
SRI_PAYMENT_CODES = {
    "EFECTIVO": "01",
    "TRANSFERENCIA": "20",
    "TARJETA_DEBITO": "16",
    "TARJETA_CREDITO": "19",
}
PAYMENT_LABELS = {
    "EFECTIVO": "Efectivo",
    "TRANSFERENCIA": "Transferencia bancaria",
    "TARJETA_DEBITO": "Tarjeta de débito",
    "TARJETA_CREDITO": "Tarjeta de crédito",
    "MIXTO": "Pago mixto",
}
PAYMENT_ABBR = {
    "E": "EFECTIVO",
    "T": "TRANSFERENCIA",
    "TD": "TARJETA_DEBITO",
    "TC": "TARJETA_CREDITO",
}
METHOD_ABBR = {value: key for key, value in PAYMENT_ABBR.items()}
PAYMENT_MARKER_RE = re.compile(r"\s*\[RP-PAGO:v1\|([^\]]*)\]\s*", re.I)


def _remove_api_route(path: str, method: str) -> int:
    wanted = str(method or "").upper()
    kept = []
    removed = 0
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


def _normalize_method(value: object, *, allow_mixed: bool = True) -> str:
    raw = " ".join(str(value or "").strip().upper().replace("-", "_").split())
    aliases = {
        "TRANSFERENCIA BANCARIA": "TRANSFERENCIA",
        "BANCO": "TRANSFERENCIA",
        "CASH": "EFECTIVO",
        "DEBITO": "TARJETA_DEBITO",
        "DÉBITO": "TARJETA_DEBITO",
        "TARJETA DÉBITO": "TARJETA_DEBITO",
        "TARJETA DEBITO": "TARJETA_DEBITO",
        "TARJETA DE DÉBITO": "TARJETA_DEBITO",
        "TARJETA DE DEBITO": "TARJETA_DEBITO",
        "CREDITO": "TARJETA_CREDITO",
        "CRÉDITO": "TARJETA_CREDITO",
        "TARJETA CRÉDITO": "TARJETA_CREDITO",
        "TARJETA CREDITO": "TARJETA_CREDITO",
        "TARJETA DE CRÉDITO": "TARJETA_CREDITO",
        "TARJETA DE CREDITO": "TARJETA_CREDITO",
        "PAGO MIXTO": "MIXTO",
    }
    raw = aliases.get(raw, raw)
    allowed = set(PAYMENT_SENTINELS)
    if not allow_mixed:
        allowed.discard("MIXTO")
    if raw not in allowed:
        raise core.HTTPException(
            400,
            "Selecciona Efectivo, Transferencia, Tarjeta débito, Tarjeta crédito o Pago mixto.",
        )
    return raw


def _clean_reference(value: object) -> str:
    raw = " ".join(str(value or "").strip().split())
    if not raw:
        return ""
    if len(raw) > 32:
        raise core.HTTPException(400, "La referencia/voucher es demasiado larga.")
    digits = re.sub(r"\D", "", raw)
    if raw.isdigit() and 13 <= len(digits) <= 19:
        raise core.HTTPException(
            400,
            "No ingreses el número completo de la tarjeta. Usa solo voucher o autorización.",
        )
    if re.search(r"\b\d{13,19}\b", raw):
        raise core.HTTPException(
            400,
            "No ingreses números completos de tarjeta. Usa solo voucher o autorización.",
        )
    return re.sub(r"[^A-Za-z0-9._/#-]+", " ", raw).strip()[:32]


def _clean_plan(value: object) -> str:
    raw = " ".join(str(value or "").strip().upper().split())
    if raw in {"", "CORRIENTE", "CONTADO"}:
        return "CORRIENTE"
    if raw in {"DIFERIDO", "DIFERIDA"}:
        return "DIFERIDO"
    raise core.HTTPException(400, "El plan de tarjeta debe ser Corriente o Diferido.")


def _strip_payment_marker(value: object) -> str:
    return PAYMENT_MARKER_RE.sub(" ", str(value or "")).strip(" |")


def _parse_payment_marker(value: object) -> dict:
    text = str(value or "")
    match = PAYMENT_MARKER_RE.search(text)
    if not match:
        return {}
    fields = {}
    for token in match.group(1).split("|"):
        if "=" not in token:
            continue
        key, raw = token.split("=", 1)
        fields[key.strip().upper()] = raw.strip()
    parts = []
    for short, method in PAYMENT_ABBR.items():
        raw = fields.get(short)
        if raw is None:
            continue
        try:
            amount = round(float(raw), 2)
        except Exception:
            continue
        if amount > 0:
            parts.append({"method": method, "amount": amount})
    result = {
        "method": fields.get("M", ""),
        "parts": parts,
        "reference": fields.get("REF", ""),
        "plan": fields.get("PLAN", ""),
        "installments": 0,
    }
    try:
        result["installments"] = int(fields.get("CUOTAS", "0") or 0)
    except Exception:
        result["installments"] = 0
    return result


def _build_payment_marker(method: str, parts: list[dict], reference: str = "", plan: str = "", installments: int = 0) -> str:
    tokens = ["M=" + str(method)]
    for item in parts:
        short = METHOD_ABBR.get(str(item.get("method") or ""))
        if not short:
            continue
        amount = round(float(item.get("amount") or 0), 2)
        if amount > 0:
            tokens.append(f"{short}={amount:.2f}")
    if reference:
        tokens.append("REF=" + reference)
    if plan:
        tokens.append("PLAN=" + plan)
    if installments:
        tokens.append("CUOTAS=" + str(int(installments)))
    return "[RP-PAGO:v1|" + "|".join(tokens) + "]"


def _append_payment_marker(observation: object, marker: str) -> str:
    base = _strip_payment_marker(observation)
    return (base + " | " + marker).strip(" |") if base else marker


def _append_discount_marker(observation: object) -> str:
    marker = "DESCUENTO PAREJA · BASE $40.00 · DESCUENTO $10.00 · TOTAL $30.00"
    text = str(observation or "")
    if "DESCUENTO PAREJA" in text.upper():
        return text
    return (text.strip() + " | " + marker).strip(" |") if text.strip() else marker


def _method_from_visit(visit) -> str | None:
    try:
        return SENTINEL_TO_METHOD.get(int(getattr(visit, "source_row", 0) or 0))
    except Exception:
        return None


class V4504PaymentPartIn(core.BaseModel):
    method: str
    amount: float


class V4504VisitBatchPaymentIn(core.VisitBatchIn):
    payment_method: str
    couple_discount: bool = False
    payment_parts: list[V4504PaymentPartIn] = []
    card_reference: str = ""
    card_plan: str = "CORRIENTE"
    card_installments: int = 0


class V4504BillingPaymentIn(core.BaseModel):
    patient_id: int
    fecha: _date
    payment_method: str
    payment_parts: list[V4504PaymentPartIn] = []
    card_reference: str = ""
    card_plan: str = "CORRIENTE"
    card_installments: int = 0


class V4504DataphoneIn(core.BaseModel):
    fecha: _date | None = None
    terminal_total: float


def _payment_spec(method_raw: object, total: float, raw_parts, card_reference: object = "", card_plan: object = "", card_installments: object = 0) -> dict:
    method = _normalize_method(method_raw)
    total = round(float(total or 0), 2)
    if total <= 0:
        raise core.HTTPException(400, "El total a cobrar debe ser mayor a cero.")

    reference = _clean_reference(card_reference)
    plan = _clean_plan(card_plan)
    try:
        installments = int(card_installments or 0)
    except Exception:
        installments = 0
    if installments < 0 or installments > 36:
        raise core.HTTPException(400, "Las cuotas deben estar entre 1 y 36.")
    if plan == "DIFERIDO" and installments < 2:
        raise core.HTTPException(400, "Para pago diferido indica al menos 2 cuotas.")
    if plan == "CORRIENTE":
        installments = 0

    if method != "MIXTO":
        parts = [{"method": method, "amount": total}]
    else:
        merged = {}
        for item in raw_parts or []:
            part_method = _normalize_method(getattr(item, "method", ""), allow_mixed=False)
            try:
                amount = round(float(getattr(item, "amount", 0) or 0), 2)
            except Exception:
                raise core.HTTPException(400, "Uno de los valores del pago mixto no es válido.")
            if amount <= 0:
                continue
            merged[part_method] = round(merged.get(part_method, 0.0) + amount, 2)
        parts = [{"method": key, "amount": value} for key, value in merged.items() if value > 0]
        if len(parts) < 2:
            raise core.HTTPException(400, "El pago mixto necesita al menos dos formas de pago.")
        if sum(1 for x in parts if x["method"].startswith("TARJETA_")) > 1:
            raise core.HTTPException(400, "En un pago mixto usa una sola tarjeta por transacción. Combínala con efectivo o transferencia.")
        parts_total = round(sum(x["amount"] for x in parts), 2)
        if abs(parts_total - total) > 0.01:
            diff = round(total - parts_total, 2)
            raise core.HTTPException(400, f"El pago mixto debe sumar ${total:.2f}. Diferencia: ${diff:.2f}.")

    has_credit = any(x["method"] == "TARJETA_CREDITO" for x in parts)
    has_card = any(x["method"].startswith("TARJETA_") for x in parts)
    if not has_card:
        reference = ""
        plan = ""
        installments = 0
    elif not has_credit:
        plan = "CORRIENTE"
        installments = 0

    marker_needed = method == "MIXTO" or has_card
    marker = _build_payment_marker(
        method,
        parts if method == "MIXTO" else [],
        reference=reference,
        plan=plan if has_card else "",
        installments=installments,
    ) if marker_needed else ""

    return {
        "method": method,
        "parts": parts,
        "reference": reference,
        "plan": plan,
        "installments": installments,
        "marker": marker,
        "sentinel": PAYMENT_SENTINELS[method],
    }


def _group_payment_parts(visits) -> list[dict]:
    visits = list(visits or [])
    if not visits:
        return []
    for visit in visits:
        parsed = _parse_payment_marker(getattr(visit, "observacion", None))
        if parsed.get("method") == "MIXTO" and parsed.get("parts"):
            return list(parsed["parts"])
    totals = {}
    for visit in visits:
        method = _method_from_visit(visit)
        if method == "MIXTO":
            parsed = _parse_payment_marker(getattr(visit, "observacion", None))
            if parsed.get("parts"):
                return list(parsed["parts"])
            continue
        if method not in SRI_PAYMENT_CODES:
            continue
        try:
            amount = round(float(getattr(visit, "valor", 0) or 0), 2)
        except Exception:
            amount = 0.0
        totals[method] = round(totals.get(method, 0.0) + amount, 2)
    return [{"method": method, "amount": amount} for method, amount in totals.items() if amount > 0]


try:
    payment_mod = sys.modules.get("app_prev_4458")
    if payment_mod is not None:
        try:
            payment_mod.PAYMENT_SENTINELS.update(PAYMENT_SENTINELS)
            payment_mod.SRI_PAYMENT_CODES.update(SRI_PAYMENT_CODES)
        except Exception:
            pass

    proof_mod = sys.modules.get("app_patch_4485")
    if proof_mod is not None:
        try:
            proof_mod._PAYMENT_SENTINELS.update({
                PAYMENT_SENTINELS["TARJETA_DEBITO"]: "TARJETA DÉBITO",
                PAYMENT_SENTINELS["TARJETA_CREDITO"]: "TARJETA CRÉDITO",
                PAYMENT_SENTINELS["MIXTO"]: "PAGO MIXTO",
            })
        except Exception:
            pass

    ROUTES_REPLACED["visits_batch_payment"] = _remove_api_route("/api/visits/batch-payment", "POST")

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
        if len(data.services) > 20:
            raise core.HTTPException(400, "Hay demasiadas acciones seleccionadas")

        override = (data.tipo or "").strip().upper()
        if override and override not in {"N", "S"}:
            raise core.HTTPException(400, "Estado de paciente inválido")

        prior = db.scalar(
            core.select(core.func.count(core.Visit.id)).where(core.Visit.patient_id == int(patient.id))
        ) or 0
        historical_prior = bool(not prior and core.historical_summary_for_patient(patient))
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
                value = CONSULT_COUPLE_TOTAL if bool(data.couple_discount) else CONSULT_BASE
            else:
                value = item.valor
            if value is None:
                raise core.HTTPException(400, f"Ingresa el valor de {key}")
            try:
                value = round(float(value), 2)
            except Exception:
                raise core.HTTPException(400, f"El valor de {key} no es válido")
            if value < 0:
                raise core.HTTPException(400, f"El valor de {key} no es válido")
            normalized.append((procedimiento, value))

        if not normalized:
            raise core.HTTPException(400, "Selecciona al menos una atención")

        total = round(sum(value for _, value in normalized), 2)
        spec = _payment_spec(
            data.payment_method,
            total,
            data.payment_parts,
            data.card_reference,
            data.card_plan,
            data.card_installments,
        )
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
            old_visit.source_row = spec["sentinel"]
            old_visit.observacion = (
                _append_payment_marker(old_visit.observacion, spec["marker"])
                if spec["marker"] else _strip_payment_marker(old_visit.observacion)
            )

        created = []
        specs = []
        for index, (procedimiento, value) in enumerate(normalized):
            tipo = first_type if index == 0 else "S"
            observation = data.observacion
            if procedimiento is None and discount_applied:
                observation = _append_discount_marker(observation)
            observation = (
                _append_payment_marker(observation, spec["marker"])
                if spec["marker"] else _strip_payment_marker(observation)
            )
            visit = core.Visit(
                patient_id=int(data.patient_id),
                fecha=data.fecha,
                tipo=tipo,
                procedimiento=procedimiento,
                valor=value,
                observacion=observation,
                source_row=spec["sentinel"],
            )
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedimiento, value, observation))
        db.flush()

        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado="PENDIENTE")
            db.add(billing)
            billings.append(billing)

        for visit, tipo, procedimiento, value, observation in specs:
            service_name = procedimiento or "CONSULTA"
            if offline:
                payload = {
                    "patient_id": int(data.patient_id),
                    "fecha": data.fecha.isoformat(),
                    "tipo": tipo,
                    "procedimiento": procedimiento,
                    "valor": value,
                    "observacion": observation,
                    "source_row": spec["sentinel"],
                }
                core.add_queue(db, "visit.create", "visit", payload, user.username, int(visit.id))
                core.audit(db, user, "crear_atencion_multiple_offline", f"Atención local {visit.id}, paciente {patient.id}, {service_name}")
            else:
                core.audit(db, user, "crear_atencion_multiple", f"Atención {visit.id}, paciente {patient.id}, estado {tipo}, servicio {service_name}")
            if procedimiento is None and discount_applied:
                core.audit(db, user, "aplicar_descuento_pareja", f"Atención {visit.id}, paciente {patient.id}: base $40.00, descuento $10.00, total $30.00")

        payment_detail = " + ".join(
            f"{PAYMENT_LABELS.get(x['method'], x['method'])} ${x['amount']:.2f}" for x in spec["parts"]
        )
        core.audit(db, user, "registrar_forma_pago_atencion", f"Paciente {int(data.patient_id)}, {data.fecha}: {payment_detail}")
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
                "agenda": int(summary_db.scalar(core.select(core.func.count(core.Appointment.id)).where(core.Appointment.estado == "PENDIENTE")) or 0),
            }

        return {
            "ok": True,
            "count": len(created),
            "items": [core.v_dict(v) for v in created],
            "offline": offline,
            "pending": pending_summary_local,
            "payment_method": spec["method"],
            "payment_label": PAYMENT_LABELS[spec["method"]],
            "payment_parts": spec["parts"],
            "sri_payment_codes": [
                {"method": x["method"], "code": SRI_PAYMENT_CODES.get(x["method"]), "amount": x["amount"]}
                for x in spec["parts"]
            ],
            "couple_discount": discount_applied,
            "single_commit": True,
        }

    ROUTES_REPLACED["billing_payment_methods"] = _remove_api_route("/api/billing/payment-methods", "GET")
    ROUTES_REPLACED["billing_payment_method"] = _remove_api_route("/api/billing/payment-method", "POST")

    @app.get("/api/billing/payment-methods")
    def v4504_billing_payment_methods(db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(core.BillingRecord.estado != "EMITIDA")
            .order_by(core.Visit.fecha.desc(), core.Visit.patient_id, core.Visit.id)
        ).all()
        grouped = {}
        for visit, billing in rows:
            key = (int(visit.patient_id), visit.fecha.isoformat())
            grouped.setdefault(key, []).append(visit)
        items = []
        for (patient_id, fecha), visits in grouped.items():
            methods = {_method_from_visit(v) for v in visits}
            methods.discard(None)
            marker = {}
            for visit in visits:
                marker = _parse_payment_marker(visit.observacion)
                if marker:
                    break
            method = marker.get("method") or (next(iter(methods)) if len(methods) == 1 else ("MIXTO" if len(methods) > 1 else ""))
            parts = _group_payment_parts(visits)
            items.append({
                "patient_id": patient_id,
                "fecha": fecha,
                "payment_method": method or None,
                "payment_label": PAYMENT_LABELS.get(method, ""),
                "mixed": method == "MIXTO" or len(parts) > 1,
                "payment_parts": parts,
                "card_reference": marker.get("reference", ""),
                "card_plan": marker.get("plan", ""),
                "card_installments": marker.get("installments", 0),
            })
        return {"items": items}

    @app.post("/api/billing/payment-method")
    def v4504_set_billing_payment_method(data: V4504BillingPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        if core.is_offline_db(db):
            raise core.HTTPException(503, "Conéctate a Internet para cambiar la forma de pago antes de facturar.")
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(core.Visit.patient_id == int(data.patient_id), core.Visit.fecha == data.fecha)
            .order_by(core.Visit.id)
        ).all()
        if not rows:
            raise core.HTTPException(404, "No se encontró esa ficha de facturación.")
        if any(str(b.estado or "").upper() == "EMITIDA" for _, b in rows):
            raise core.HTTPException(409, "La factura ya fue emitida. Su forma de pago no se modifica.")
        total = round(sum(float(v.valor or 0) for v, _ in rows), 2)
        spec = _payment_spec(data.payment_method, total, data.payment_parts, data.card_reference, data.card_plan, data.card_installments)
        visits = []
        for visit, _billing in rows:
            visit.source_row = spec["sentinel"]
            visit.observacion = _append_payment_marker(visit.observacion, spec["marker"]) if spec["marker"] else _strip_payment_marker(visit.observacion)
            visits.append(visit)
        core.audit(
            db, user, "registrar_forma_pago_facturacion",
            f"Paciente {data.patient_id}, {data.fecha}: " + " + ".join(f"{PAYMENT_LABELS.get(x['method'], x['method'])} ${x['amount']:.2f}" for x in spec["parts"]),
        )
        db.commit()
        for visit in visits:
            try:
                core.mirror_visit_to_local(visit)
            except Exception:
                pass
        return {
            "ok": True,
            "patient_id": int(data.patient_id),
            "fecha": data.fecha.isoformat(),
            "payment_method": spec["method"],
            "payment_label": PAYMENT_LABELS[spec["method"]],
            "payment_parts": spec["parts"],
        }

    base_azur_builder = (getattr(payment_mod, "_stable_azur_payload_for_group", None) if payment_mod is not None else None) or core._azur_payload_for_group

    def _azur_payload_for_group_v4504(data, patient, rows):
        payload = base_azur_builder(data, patient, rows)
        visits = [visit for _billing, visit in rows]
        parts = _group_payment_parts(visits)
        if not parts:
            raise core.HTTPException(409, "La forma de pago no está registrada. Vuelve a la atención o selecciónala en Facturación.")
        invoice_total = round(sum(float(v.valor or 0) for v in visits), 2)
        parts_total = round(sum(float(x["amount"]) for x in parts), 2)
        if abs(invoice_total - parts_total) > 0.01:
            raise core.HTTPException(409, f"El desglose de pago suma ${parts_total:.2f} y la factura ${invoice_total:.2f}. Corrige la forma de pago.")
        by_code = {}
        for item in parts:
            method = item["method"]
            code = SRI_PAYMENT_CODES.get(method)
            if not code:
                raise core.HTTPException(409, f"Forma de pago sin código SRI: {method}")
            by_code[code] = round(by_code.get(code, 0.0) + float(item["amount"]), 2)
        payload["pagos"] = [
            {"tipo": code, "total": amount, "tiempo": "dias", "plazo": 0}
            for code, amount in sorted(by_code.items())
        ]
        return payload

    core._azur_payload_for_group = _azur_payload_for_group_v4504

    def _local_today_summary(fecha: _date) -> dict:
        with core.LocalSessionLocal() as db:
            visits = list(db.scalars(core.select(core.Visit).where(core.Visit.fecha == fecha).order_by(core.Visit.patient_id, core.Visit.id)))
            groups = {}
            for visit in visits:
                groups.setdefault(int(visit.patient_id), []).append(visit)
            totals = {key: 0.0 for key in SRI_PAYMENT_CODES}
            patients_missing_id = 0
            pending_billing = 0
            discount_count = 0
            discount_total = 0.0
            for patient_id, group_visits in groups.items():
                for item in _group_payment_parts(group_visits):
                    method = item["method"]
                    if method in totals:
                        totals[method] = round(totals[method] + float(item["amount"]), 2)
                patient = db.get(core.Patient, patient_id)
                if patient is not None and not str(getattr(patient, "cedula", "") or "").strip():
                    patients_missing_id += 1
                states = []
                for visit in group_visits:
                    billing = db.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id == int(visit.id)))
                    if billing:
                        states.append(str(billing.estado or "").upper())
                    if "DESCUENTO PAREJA" in str(visit.observacion or "").upper():
                        discount_count += 1
                        discount_total = round(discount_total + COUPLE_DISCOUNT, 2)
                if states and any(state != "EMITIDA" for state in states):
                    pending_billing += 1
            pending_appointments = int(db.scalar(core.select(core.func.count(core.Appointment.id)).where(core.Appointment.fecha == fecha, core.Appointment.estado == "PENDIENTE")) or 0)
            total = round(sum(totals.values()), 2)
            card_total = round(totals["TARJETA_DEBITO"] + totals["TARJETA_CREDITO"], 2)
            key = "v4504_dataphone_" + fecha.isoformat()
            saved = db.get(core.CacheMeta, key)
            terminal_total = None
            if saved and str(saved.value or "").strip():
                try:
                    terminal_total = round(float(saved.value), 2)
                except Exception:
                    terminal_total = None
            difference = round(float(terminal_total) - card_total, 2) if terminal_total is not None else None
            return {
                "date": fecha.isoformat(),
                "patients": len(groups),
                "total": total,
                "methods": {
                    method: {"label": PAYMENT_LABELS[method], "amount": round(amount, 2), "sri_code": SRI_PAYMENT_CODES[method]}
                    for method, amount in totals.items()
                },
                "card_total": card_total,
                "discounts": {"count": discount_count, "amount": discount_total},
                "pending": {
                    "billing": pending_billing,
                    "appointments": pending_appointments,
                    "missing_identification": patients_missing_id,
                    "total": pending_billing + pending_appointments + patients_missing_id,
                },
                "dataphone": {
                    "registered_total": terminal_total,
                    "system_total": card_total,
                    "difference": difference,
                    "matches": difference is not None and abs(difference) <= 0.01,
                },
            }

    @app.get("/api/v4504/payments/today")
    def v4504_payments_today(user=core.Depends(core.current_user)):
        return _local_today_summary(_date.today())

    @app.post("/api/v4504/dataphone/reconcile")
    def v4504_dataphone_reconcile(data: V4504DataphoneIn, request: core.Request, user=core.Depends(core.current_user)):
        if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
            raise core.HTTPException(403, "La conciliación del datáfono solo se registra desde Recepción.")
        fecha = data.fecha or _date.today()
        try:
            value = round(float(data.terminal_total), 2)
        except Exception:
            raise core.HTTPException(400, "Ingresa un total válido del datáfono.")
        if value < 0 or value > 100000:
            raise core.HTTPException(400, "El total del datáfono no es válido.")
        key = "v4504_dataphone_" + fecha.isoformat()
        with core.LocalSessionLocal() as db:
            row = db.get(core.CacheMeta, key)
            if row:
                row.value = f"{value:.2f}"
            else:
                db.add(core.CacheMeta(key=key, value=f"{value:.2f}"))
            db.commit()
        return {"ok": True, **_local_today_summary(fecha)}

    V4504_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}.v460-version::after,#currentVersionBadge::after{content:"v4.5.4"!important;font-size:9px!important;line-height:1!important;font-weight:850!important}
.v4451-attention-payment{display:none!important}.v4504-checkout{margin:13px 0 11px;border:1px solid #d6e2ee;border-radius:14px;background:#fbfdff;overflow:hidden;box-shadow:0 3px 13px rgba(33,66,101,.05)}
.v4504-checkout-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;background:linear-gradient(90deg,#f0f6fd,#fbfdff);border-bottom:1px solid #dce6ef}.v4504-checkout-head b{font-size:12px;color:#27445f}.v4504-checkout-head small{display:block;font-size:8px;color:#71859a}.v4504-total{text-align:right}.v4504-total span{display:block;font-size:7px;font-weight:900;letter-spacing:.08em;color:#7e8fa1}.v4504-total strong{display:block;font-size:22px;line-height:1;color:#245c8d;margin-top:2px}.v4504-discount-line{color:#2c7751!important;font-weight:850!important}
.v4504-pay-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;padding:11px 12px 8px}.v4504-pay-btn{min-height:48px!important;border:1px solid #d2dde8!important;border-radius:10px!important;background:#fff!important;color:#425c74!important;display:flex!important;flex-direction:column;align-items:center!important;justify-content:center!important;gap:3px!important;padding:7px 5px!important;box-shadow:none!important;font-size:8px!important;font-weight:850!important}.v4504-pay-btn span{font-size:15px}.v4504-pay-btn.selected{border-color:#609bcf!important;background:#eef6ff!important;color:#225d91!important;box-shadow:0 0 0 2px rgba(67,126,184,.09)!important}.v4504-pay-btn.selected.card{border-color:#6c83c9!important;background:#f0f2ff!important;color:#3c5196!important}.v4504-pay-btn.selected.mixed{border-color:#6aa889!important;background:#eff9f3!important;color:#28684a!important}.v4504-pay-required{border-color:#dda944!important;box-shadow:0 0 0 3px rgba(221,169,68,.10)!important}
.v4504-card-meta,.v4504-mixed{margin:2px 12px 11px;padding:10px;border:1px solid #e0e7ef;border-radius:10px;background:#fff}.v4504-card-meta.hidden,.v4504-mixed.hidden{display:none!important}.v4504-meta-grid{display:grid;grid-template-columns:1.4fr .8fr .55fr;gap:8px}.v4504-meta-grid label,.v4504-mix-row label{font-size:7.5px;font-weight:850;color:#6b7d91;text-transform:uppercase;letter-spacing:.04em}.v4504-meta-grid input,.v4504-meta-grid select,.v4504-mix-row input{width:100%;height:34px;margin-top:4px;border:1px solid #ccd8e4;border-radius:8px;padding:6px 8px;box-sizing:border-box;background:#fff;font-size:9px;color:#324b65}.v4504-card-note{display:block;margin-top:7px;font-size:7.5px;color:#8190a0}.v4504-mix-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.v4504-mix-row{border:1px solid #e0e6ee;border-radius:9px;padding:8px;background:#fafcfe}.v4504-mix-row b{display:block;font-size:8.5px;color:#3d5870;margin-bottom:3px}.v4504-mix-check{display:flex;justify-content:space-between;align-items:center;margin-top:8px;font-size:8px;color:#6a7d90}.v4504-mix-check strong.ok{color:#28744d}.v4504-mix-check strong.bad{color:#a25936}
#inicio .v4504-today-strip{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:8px 0 10px;padding:8px 11px;border:1px solid #d9e4ef;border-radius:11px;background:#f8fbfe}.v4504-today-kicker{font-size:7px;font-weight:950;letter-spacing:.09em;color:#6f849a}.v4504-today-metric{font-size:9px;color:#536a82}.v4504-today-metric b{color:#274f79;font-size:11px}.v4504-today-strip button{margin-left:auto;min-height:29px!important;border-radius:8px!important;padding:5px 9px!important;font-size:8px!important;font-weight:850!important}
.v4504-overlay{position:fixed;inset:0;z-index:12050;background:rgba(16,28,47,.38);display:grid;place-items:center;padding:18px}.v4504-overlay.hidden{display:none!important}.v4504-payments-modal{width:min(720px,94vw);max-height:88vh;overflow:auto;border-radius:16px;background:#fff;box-shadow:0 18px 55px rgba(14,35,59,.24)}.v4504-modal-head{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:15px 17px;border-bottom:1px solid #e1e7ef}.v4504-modal-head h3{margin:0;font-size:18px;color:#253d58}.v4504-modal-head p{margin:3px 0 0;font-size:9px;color:#77899c}.v4504-modal-head button{border:0!important;background:#eef2f6!important;border-radius:9px!important;width:32px;height:32px;padding:0!important}.v4504-modal-body{padding:14px 16px 17px}.v4504-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.v4504-summary-card{border:1px solid #e0e6ee;border-radius:11px;padding:10px;background:#fafbfd}.v4504-summary-card span{display:block;font-size:7.5px;font-weight:850;color:#75869a;text-transform:uppercase}.v4504-summary-card b{display:block;margin-top:4px;font-size:17px;color:#294e75}.v4504-method-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:10px}.v4504-method-item{display:flex;justify-content:space-between;gap:10px;padding:9px 10px;border:1px solid #e3e8ef;border-radius:9px}.v4504-method-item span{font-size:9px;color:#536b82}.v4504-method-item b{font-size:10px;color:#2c4d6c}.v4504-dataphone{margin-top:12px;padding:12px;border:1px solid #d8e4ef;border-radius:12px;background:#f5f9fd}.v4504-dataphone-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.v4504-dataphone h4{margin:0;font-size:12px;color:#2c4c69}.v4504-dataphone small{font-size:8px;color:#788b9e}.v4504-data-row{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:end;margin-top:9px}.v4504-data-row input{height:35px;border:1px solid #cbd8e5;border-radius:8px;padding:6px 9px;font-size:10px}.v4504-data-row button{height:35px!important;border-radius:8px!important;font-size:8.5px!important}.v4504-reconcile{min-width:110px;padding:8px 9px;border-radius:8px;background:#eef2f7;font-size:8.5px;font-weight:850;color:#65778b;text-align:center}.v4504-reconcile.ok{background:#e8f7ed;color:#247047}.v4504-reconcile.bad{background:#fff0e9;color:#9a542f}.v4504-pending{margin-top:12px;padding:10px 12px;border-radius:10px;background:#fff9ee;border:1px solid #eddcb8}.v4504-pending.ok{background:#eef9f2;border-color:#cfe8d8}.v4504-pending b{font-size:9px;color:#5a6470}.v4504-pending small{display:block;margin-top:3px;font-size:8px;color:#798695}
#facturacion .billing-card{border-radius:14px!important;box-shadow:0 3px 13px rgba(30,61,94,.045)!important}.v4504-billing-extra{display:inline-flex;gap:5px;flex-wrap:wrap}.v4504-billing-choice{min-height:32px!important;padding:5px 9px!important;border-radius:9px!important;border:1px solid #cfdbe7!important;background:#fff!important;font-size:8.5px!important;font-weight:850!important}.v4504-billing-choice.selected{border-color:#7189c8!important;background:#f0f2ff!important;color:#405495!important}
@media(max-width:850px){.v4504-pay-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.v4504-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.v4504-mix-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.v4504-pay-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.v4504-meta-grid{grid-template-columns:1fr}.v4504-mix-grid,.v4504-method-list{grid-template-columns:1fr}.v4504-data-row{grid-template-columns:1fr}}
"""

    V4504_JS = r"""
;(()=>{
  if(window.__v4504Payments)return;window.__v4504Payments=true;
  const VERSION='4.5.4';
  const METHODS=[['EFECTIVO','💵','Efectivo'],['TRANSFERENCIA','🏦','Transferencia'],['TARJETA_DEBITO','💳','Débito'],['TARJETA_CREDITO','💳','Crédito'],['MIXTO','＋','Mixto']];
  let payMethod='';let latestToday=null;
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const n=v=>Number(String(v??'').replace(/[^0-9.,-]/g,'').replace(',','.'))||0;
  const money=v=>'$'+Number(v||0).toFixed(2);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  function modal(){return q('.attention-form-modal')||qa('#modal .modalbox,.modal .modalbox,.modalbox').find(b=>qa('h1,h2,h3',b).some(h=>norm(h.textContent)==='nueva atencion'))||null}
  function selectedServices(box=modal()){if(!box)return [];const seen=new Set(),out=[];qa('button.service-card[data-service]',box).forEach(card=>{const input=q('input[type="checkbox"],input[type="radio"]',card),selected=card.classList.contains('selected')||card.classList.contains('is-selected')||card.getAttribute('aria-pressed')==='true'||!!input?.checked;if(!selected)return;const key=norm(card.dataset.service||card.textContent||'');if(!key||seen.has(key))return;seen.add(key);let price=n(q('.service-price',card)?.textContent||'');if(!price)price=n(q('input[type="number"]',card)?.value||0);out.push({key,price,card})});return out}
  const attentionTotal=()=>selectedServices().reduce((s,x)=>s+Number(x.price||0),0);
  function coupleDiscountActive(){try{return !!window.__v4502CoupleDiscountTest?.enabled?.()}catch(_e){return false}}
  function paymentParts(){if(payMethod!=='MIXTO')return [];const box=q('#v4504Checkout');return qa('[data-mix-method]',box).map(inp=>({method:inp.dataset.mixMethod,amount:Number(inp.value||0)})).filter(x=>x.amount>0)}
  function cardMeta(){const box=q('#v4504Checkout');return {card_reference:String(q('#v4504CardRef',box)?.value||'').trim(),card_plan:String(q('#v4504CardPlan',box)?.value||'CORRIENTE').toUpperCase(),card_installments:Number(q('#v4504CardInstallments',box)?.value||0)}}
  function hasCard(){return payMethod==='TARJETA_DEBITO'||payMethod==='TARJETA_CREDITO'||paymentParts().some(x=>x.method==='TARJETA_DEBITO'||x.method==='TARJETA_CREDITO')}
  function hasCredit(){return payMethod==='TARJETA_CREDITO'||paymentParts().some(x=>x.method==='TARJETA_CREDITO')}
  function bridgeLegacy(method){if(typeof window.v4451ChooseAttentionPayment!=='function')return;if(method==='EFECTIVO')window.v4451ChooseAttentionPayment('EFECTIVO');else window.v4451ChooseAttentionPayment('TRANSFERENCIA')}
  function checkoutMarkup(){let buttons='';METHODS.forEach(item=>{const cls=(item[0]===payMethod?' selected':'')+(item[0].startsWith('TARJETA_')?' card':'')+(item[0]==='MIXTO'?' mixed':'');buttons+='<button type="button" class="v4504-pay-btn'+cls+'" data-v4504-pay="'+item[0]+'"><span>'+item[1]+'</span><b>'+item[2]+'</b></button>'});return '<div class="v4504-checkout-head"><div><b>Resumen de cobro</b><small>Revisa servicios, total y forma de pago antes de guardar.</small><small id="v4504DiscountLine" class="v4504-discount-line"></small></div><div class="v4504-total"><span>TOTAL A COBRAR</span><strong id="v4504Total">$0.00</strong></div></div><div class="v4504-pay-grid">'+buttons+'</div><div id="v4504CardMeta" class="v4504-card-meta hidden"><div class="v4504-meta-grid"><label>Voucher / autorización<input id="v4504CardRef" maxlength="32" autocomplete="off" placeholder="Opcional"></label><label>Plan<select id="v4504CardPlan"><option value="CORRIENTE">Corriente</option><option value="DIFERIDO">Diferido</option></select></label><label>Cuotas<input id="v4504CardInstallments" type="number" min="2" max="36" placeholder="—"></label></div><small class="v4504-card-note">No ingreses número completo de tarjeta ni CVV. Solo voucher/autorización del datáfono.</small></div><div id="v4504Mixed" class="v4504-mixed hidden"><div class="v4504-mix-grid"><div class="v4504-mix-row"><b>💵 Efectivo</b><label>Valor<input type="number" step="0.01" min="0" data-mix-method="EFECTIVO" placeholder="0.00"></label></div><div class="v4504-mix-row"><b>🏦 Transferencia</b><label>Valor<input type="number" step="0.01" min="0" data-mix-method="TRANSFERENCIA" placeholder="0.00"></label></div><div class="v4504-mix-row"><b>💳 Débito</b><label>Valor<input type="number" step="0.01" min="0" data-mix-method="TARJETA_DEBITO" placeholder="0.00"></label></div><div class="v4504-mix-row"><b>💳 Crédito</b><label>Valor<input type="number" step="0.01" min="0" data-mix-method="TARJETA_CREDITO" placeholder="0.00"></label></div></div><div class="v4504-mix-check"><span>La suma debe coincidir con el total.</span><strong id="v4504MixCheck">Ingresa valores</strong></div></div>'}
  function mountCheckout(){const box=modal();if(!box)return;let checkout=q('#v4504Checkout',box);if(!checkout){checkout=document.createElement('div');checkout.id='v4504Checkout';checkout.className='v4504-checkout';checkout.innerHTML=checkoutMarkup();const actions=q('.v492-sticky-actions',box)||q('.modal-actions',box);if(actions)actions.insertAdjacentElement('beforebegin',checkout);else box.appendChild(checkout);qa('[data-v4504-pay]',checkout).forEach(btn=>btn.addEventListener('click',()=>{payMethod=String(btn.dataset.v4504Pay||'');bridgeLegacy(payMethod);renderCheckout()}));qa('input,select',checkout).forEach(el=>el.addEventListener('input',renderCheckout));qa('input,select',checkout).forEach(el=>el.addEventListener('change',renderCheckout))}renderCheckout()}
  function renderCheckout(){const checkout=q('#v4504Checkout');if(!checkout)return;const total=attentionTotal(),totalEl=q('#v4504Total',checkout);if(totalEl)totalEl.textContent=money(total);const discount=q('#v4504DiscountLine',checkout);if(discount)discount.textContent=coupleDiscountActive()?'Descuento pareja aplicado · -$10.00':'';qa('[data-v4504-pay]',checkout).forEach(btn=>btn.classList.toggle('selected',String(btn.dataset.v4504Pay||'')===payMethod));q('#v4504Mixed',checkout)?.classList.toggle('hidden',payMethod!=='MIXTO');q('#v4504CardMeta',checkout)?.classList.toggle('hidden',!hasCard());const plan=q('#v4504CardPlan',checkout),inst=q('#v4504CardInstallments',checkout);if(plan){plan.disabled=!hasCredit();if(!hasCredit())plan.value='CORRIENTE'}if(inst){const deferred=hasCredit()&&String(plan?.value||'')==='DIFERIDO';inst.disabled=!deferred;if(!deferred)inst.value=''}if(payMethod==='MIXTO'){const parts=paymentParts(),sum=parts.reduce((s,x)=>s+x.amount,0),diff=Math.round((total-sum)*100)/100,check=q('#v4504MixCheck',checkout);if(check){if(parts.length>=2&&Math.abs(diff)<=.01){check.textContent='✓ Cuadra';check.className='ok'}else{check.textContent=(diff>=0?'Falta ':'Excede ')+money(Math.abs(diff));check.className='bad'}}}}
  function validateBeforeSave(){const checkout=q('#v4504Checkout');checkout?.classList.remove('v4504-pay-required');if(!payMethod){checkout?.classList.add('v4504-pay-required');checkout?.scrollIntoView?.({behavior:'smooth',block:'center'});alert('Selecciona la forma de pago antes de guardar la atención.');return false}if(payMethod==='MIXTO'){const parts=paymentParts(),total=attentionTotal(),sum=parts.reduce((s,x)=>s+x.amount,0);if(parts.length<2||Math.abs(total-sum)>.01){checkout?.classList.add('v4504-pay-required');alert('El pago mixto necesita al menos dos formas y debe sumar exactamente '+money(total)+'.');return false}if(parts.filter(x=>x.method.startsWith('TARJETA_')).length>1){alert('Para pago mixto usa una sola tarjeta y combínala con efectivo o transferencia.');return false}}return true}
  const stableAttentionFor=window.attentionFor;if(typeof stableAttentionFor==='function'){window.attentionFor=async function(id,draft=null){payMethod='';const out=await stableAttentionFor.apply(this,arguments);setTimeout(mountCheckout,0);setTimeout(mountCheckout,120);setTimeout(mountCheckout,300);return out}}
  const stableSaveAttention=window.saveAttention;if(typeof stableSaveAttention==='function'){window.saveAttention=async function(id){if(!validateBeforeSave())return;bridgeLegacy(payMethod);const parts=paymentParts(),meta=cardMeta(),stableApi=window.api||api;const intercept=async function(url,opt={}){if(String(url)==='/api/visits/batch-payment'){let body={};try{body=JSON.parse(opt?.body||'{}')}catch(_e){body={}}body.payment_method=payMethod;body.payment_parts=parts;body.card_reference=meta.card_reference;body.card_plan=meta.card_plan;body.card_installments=meta.card_installments;return stableApi(url,{...opt,body:JSON.stringify(body)})}return stableApi(url,opt)};const previousApi=api;try{api=intercept;const result=await stableSaveAttention.apply(this,arguments);setTimeout(refreshToday,250);return result}finally{api=previousApi}}}
  document.addEventListener('click',e=>{if(e.target?.closest?.('.attention-form-modal button.service-card[data-service]')){setTimeout(mountCheckout,20);setTimeout(renderCheckout,160);setTimeout(renderCheckout,340)}},true);document.addEventListener('change',e=>{if(e.target?.closest?.('.attention-form-modal'))setTimeout(renderCheckout,40)},true);
  async function call(url,opt={}){if(typeof window.api==='function')return window.api(url,opt);const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.message||'No se pudo completar la operación');return d}
  function todayStripHtml(d){const p=d.pending||{},dis=d.discounts||{};return '<span class="v4504-today-kicker">PAGOS DE HOY</span><span class="v4504-today-metric"><b>'+Number(d.patients||0)+'</b> pacientes</span><span class="v4504-today-metric"><b>'+money(d.total||0)+'</b> cobrado</span><span class="v4504-today-metric"><b>'+Number(p.billing||0)+'</b> por facturar</span><span class="v4504-today-metric"><b>'+Number(dis.count||0)+'</b> descuento(s)</span><button type="button" class="secondary" id="v4504OpenPayments">Ver pagos</button>'}
  function mountTodayStrip(){const inicio=q('#inicio');if(!inicio)return;let strip=q('#v4504TodayStrip',inicio);if(!strip){strip=document.createElement('div');strip.id='v4504TodayStrip';strip.className='v4504-today-strip';const table=q('#todayTable',inicio);if(table)table.insertAdjacentElement('beforebegin',strip);else inicio.appendChild(strip)}if(latestToday)strip.innerHTML=todayStripHtml(latestToday);q('#v4504OpenPayments',strip)?.addEventListener('click',openPaymentsModal)}
  async function refreshToday(){try{latestToday=await call('/api/v4504/payments/today');mountTodayStrip();if(!q('#v4504PaymentsOverlay')?.classList.contains('hidden'))renderPaymentsModal()}catch(_e){}}
  function ensurePaymentsModal(){let overlay=q('#v4504PaymentsOverlay');if(overlay)return overlay;overlay=document.createElement('div');overlay.id='v4504PaymentsOverlay';overlay.className='v4504-overlay hidden';overlay.innerHTML='<div class="v4504-payments-modal"><div class="v4504-modal-head"><div><h3>Pagos de hoy</h3><p>Resumen operativo y conciliación del datáfono. No realiza cierres de caja.</p></div><button type="button" id="v4504ClosePayments">✕</button></div><div id="v4504PaymentsBody" class="v4504-modal-body"></div></div>';document.body.appendChild(overlay);q('#v4504ClosePayments',overlay)?.addEventListener('click',()=>overlay.classList.add('hidden'));overlay.addEventListener('click',e=>{if(e.target===overlay)overlay.classList.add('hidden')});return overlay}
  function renderPaymentsModal(){if(!latestToday)return;const overlay=ensurePaymentsModal(),body=q('#v4504PaymentsBody',overlay),d=latestToday,p=d.pending||{},dp=d.dataphone||{},dis=d.discounts||{},methods=d.methods||{};let methodHtml='';['EFECTIVO','TRANSFERENCIA','TARJETA_DEBITO','TARJETA_CREDITO'].forEach(key=>{const x=methods[key]||{};methodHtml+='<div class="v4504-method-item"><span>'+esc(x.label||key)+'</span><b>'+money(x.amount||0)+'</b></div>'});let rec='Sin comparar',recClass='';if(dp.registered_total!=null){if(dp.matches){rec='✓ Cuadra';recClass=' ok'}else{rec='Diferencia '+money(dp.difference||0);recClass=' bad'}}const pendingTotal=Number(p.total||0);body.innerHTML='<div class="v4504-summary-grid"><div class="v4504-summary-card"><span>Total cobrado</span><b>'+money(d.total||0)+'</b></div><div class="v4504-summary-card"><span>Pacientes</span><b>'+Number(d.patients||0)+'</b></div><div class="v4504-summary-card"><span>Tarjetas</span><b>'+money(d.card_total||0)+'</b></div><div class="v4504-summary-card"><span>Descuentos</span><b>'+money(dis.amount||0)+'</b></div></div><div class="v4504-method-list">'+methodHtml+'</div><div class="v4504-dataphone"><div class="v4504-dataphone-head"><div><h4>Conciliación del datáfono</h4><small>Ingresa el total que muestra el datáfono; el sistema lo compara con las tarjetas registradas.</small></div><b>'+money(d.card_total||0)+'</b></div><div class="v4504-data-row"><input id="v4504TerminalTotal" type="number" step="0.01" min="0" placeholder="Total del datáfono" value="'+(dp.registered_total==null?'':Number(dp.registered_total).toFixed(2))+'"><button type="button" class="primary" id="v4504SaveTerminal">Comparar</button><div class="v4504-reconcile'+recClass+'">'+esc(rec)+'</div></div></div><div class="v4504-pending '+(pendingTotal?'':'ok')+'"><b>'+(pendingTotal?'Pendientes de hoy · '+pendingTotal:'✓ Sin pendientes de hoy')+'</b><small>'+Number(p.billing||0)+' por facturar · '+Number(p.appointments||0)+' cita(s) pendientes · '+Number(p.missing_identification||0)+' sin identificación</small></div>';q('#v4504SaveTerminal',body)?.addEventListener('click',saveTerminalTotal)}
  async function saveTerminalTotal(){const inp=q('#v4504TerminalTotal'),value=Number(inp?.value||0);if(!Number.isFinite(value)||value<0){alert('Ingresa un total válido del datáfono.');return}try{latestToday=await call('/api/v4504/dataphone/reconcile',{method:'POST',body:JSON.stringify({terminal_total:value})});renderPaymentsModal();mountTodayStrip()}catch(e){alert(e?.message||String(e))}}
  async function openPaymentsModal(){ensurePaymentsModal().classList.remove('hidden');await refreshToday();renderPaymentsModal()}
  const oldRenderHome=window.renderHomeDayPayload;if(typeof oldRenderHome==='function'&&!oldRenderHome.__v4504){const wrapped=function(){const out=oldRenderHome.apply(this,arguments);setTimeout(()=>{mountTodayStrip();refreshToday()},40);return out};wrapped.__v4504=true;window.renderHomeDayPayload=wrapped}
  let billingMap=new Map();const bkey=(pid,fecha)=>Number(pid)+'|'+String(fecha||'').slice(0,10);
  async function refreshBillingMap(){try{const d=await call('/api/billing/payment-methods');billingMap=new Map((d?.items||[]).map(x=>[bkey(x.patient_id,x.fecha),x]));decorateBillingPayments()}catch(_e){}}
  function billingIdentity(wrap){const pid=Number(wrap?.dataset?.patientId||0),fecha=String(wrap?.dataset?.fecha||'').slice(0,10);return pid&&fecha?{pid,fecha}:null}
  function decorateBillingPayments(){qa('#billingList .v4431-pay-wrap').forEach(wrap=>{const id=billingIdentity(wrap);if(!id)return;const state=billingMap.get(bkey(id.pid,id.fecha))||{};let extra=q('.v4504-billing-extra',wrap);if(!extra){extra=document.createElement('span');extra.className='v4504-billing-extra';extra.innerHTML='<button type="button" class="v4504-billing-choice" data-method="TARJETA_DEBITO">💳 Débito</button><button type="button" class="v4504-billing-choice" data-method="TARJETA_CREDITO">💳 Crédito</button>';wrap.appendChild(extra);qa('[data-method]',extra).forEach(btn=>btn.addEventListener('click',async()=>{const method=String(btn.dataset.method||'');try{await call('/api/billing/payment-method',{method:'POST',body:JSON.stringify({patient_id:id.pid,fecha:id.fecha,payment_method:method})});await refreshBillingMap()}catch(e){alert(e?.message||String(e))}}))}qa('[data-method]',extra).forEach(btn=>btn.classList.toggle('selected',String(btn.dataset.method||'')===String(state.payment_method||'')));const label=q('.v4431-pay-label',wrap);if(label&&state.payment_method==='MIXTO')label.textContent='Forma de pago · MIXTO'})}
  const oldLoadBilling=window.loadBilling;if(typeof oldLoadBilling==='function'&&!oldLoadBilling.__v4504){const wrapped=async function(){const out=await oldLoadBilling.apply(this,arguments);setTimeout(refreshBillingMap,80);return out};wrapped.__v4504=true;window.loadBilling=wrapped}
  function boot(){document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION)});mountCheckout();mountTodayStrip();refreshToday();refreshBillingMap()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  window.__v4504PaymentTest={refreshToday,mountCheckout,getMethod:()=>payMethod,getParts:()=>paymentParts(),total:()=>attentionTotal()};
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
        "payments": {
            "cash": True,
            "transfer": True,
            "debit_card": True,
            "credit_card": True,
            "mixed": True,
            "sri_codes": SRI_PAYMENT_CODES,
            "no_pan_or_cvv": True,
        },
        "dataphone_ready": True,
        "dataphone_reconciliation": True,
        "cash_closing": False,
        "today_summary": True,
        "today_pending": True,
        "visual_checkout": True,
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