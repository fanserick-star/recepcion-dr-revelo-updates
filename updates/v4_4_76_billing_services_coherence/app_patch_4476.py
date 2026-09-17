from __future__ import annotations

# v4.4.76 — historial fiscal coherente + Servicios y precios simplificados.
# - Parte de v4.4.75; conserva guardado rápido e impresión en segundo plano.
# - Un paciente enviado a Papelera deja de aparecer en POR EMITIR inmediatamente.
# - Las facturas ya emitidas se conservan y siguen visibles aunque luego se borre el paciente.
# - EMITIDAS separa comprobantes distintos del mismo paciente/día por número de factura.
# - Advierte antes de emitir otra factura si el paciente ya tiene una enviada ese día.
# - No permite borrar individualmente una atención que ya fue facturada.
# - Reemplaza las múltiples columnas de Servicios y precios por un único panel compacto.
# - No agrega MutationObserver ni toca el recibo térmico aprobado v4.4.69.

import json as _json
from datetime import date as _date, datetime as _datetime, timedelta as _timedelta

import app_patch_4475 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.76"

_mod = previous
_seen = set()
for _ in range(32):
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


def _active_patient_trash_snapshots() -> list[dict]:
    out = []
    try:
        with core.LocalSessionLocal() as ldb:
            try:
                core._ops_ensure_trash_table(ldb)
            except Exception:
                pass
            rows = list(ldb.scalars(
                core.select(core.TrashItem).where(
                    core.TrashItem.entity_type == "patient",
                    core.TrashItem.restored_at.is_(None),
                )
            ))
            for item in rows:
                try:
                    snap = _json.loads(item.snapshot_json or "{}")
                except Exception:
                    continue
                patient = snap.get("patient") if isinstance(snap, dict) else None
                if not isinstance(patient, dict):
                    continue
                try:
                    pid = int(patient.get("id") or item.entity_id or 0)
                except Exception:
                    pid = 0
                if not pid:
                    continue
                out.append({
                    "trash_id": int(item.id),
                    "patient_id": pid,
                    "snapshot": snap,
                    "deleted_at": item.deleted_at,
                })
    except Exception:
        return []
    return out


def _active_trashed_patient_ids() -> set[int]:
    return {int(x["patient_id"]) for x in _active_patient_trash_snapshots()}


def _json_date(value):
    if isinstance(value, (_date, _datetime)):
        return value.isoformat()
    return value


def _patient_snapshot(patient) -> dict:
    return {
        "id": int(patient.id),
        "cedula": getattr(patient, "cedula", None),
        "nombre": getattr(patient, "nombre", None),
        "fecha_nacimiento": _json_date(getattr(patient, "fecha_nacimiento", None)),
        "celular": getattr(patient, "celular", None),
        "correo": getattr(patient, "correo", None),
        "lugar": getattr(patient, "lugar", None),
        "notas": getattr(patient, "notas", None),
        "created_at": _json_date(getattr(patient, "created_at", None)),
    }


def _fiscal_line_snapshot(visit, billing) -> dict:
    return {
        "visit": {
            "id": int(visit.id),
            "patient_id": int(visit.patient_id),
            "fecha": _json_date(visit.fecha),
            "tipo": visit.tipo,
            "procedimiento": visit.procedimiento,
            "valor": float(visit.valor) if visit.valor is not None else None,
            "observacion": visit.observacion,
            "source_row": getattr(visit, "source_row", None),
            "created_at": _json_date(getattr(visit, "created_at", None)),
        },
        "billing": {
            "id": int(billing.id),
            "visit_id": int(billing.visit_id),
            "estado": billing.estado,
            "numero_factura": billing.numero_factura,
            "approved_at": _json_date(billing.approved_at),
            "emitted_at": _json_date(billing.emitted_at),
            "created_at": _json_date(getattr(billing, "created_at", None)),
        },
    }


def _emission_payload(record) -> dict:
    try:
        value = _json.loads(record.response_json or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_emission_payload(record, payload: dict) -> None:
    # Mantener holgura: response_json es texto; evitamos guardar secretos o datos clínicos extra.
    record.response_json = _json.dumps(
        payload, ensure_ascii=False, default=_json_date
    )


def _preserve_patient_fiscal_history(db, patient) -> int:
    """Adjunta a AzurEmission un snapshot mínimo antes de borrar el paciente."""
    pid = int(patient.id)
    rows = db.execute(
        core.select(core.BillingRecord, core.Visit)
        .join(core.Visit, core.BillingRecord.visit_id == core.Visit.id)
        .where(
            core.Visit.patient_id == pid,
            core.BillingRecord.estado == "EMITIDA",
        )
        .order_by(core.Visit.fecha, core.Visit.id)
    ).all()
    if not rows:
        return 0

    emissions = list(db.scalars(
        core.select(core.AzurEmission)
        .where(core.AzurEmission.patient_id == pid)
        .order_by(core.AzurEmission.fecha, core.AzurEmission.id)
    ))
    if not emissions:
        return 0

    p_snap = _patient_snapshot(patient)
    changed = 0
    for emission in emissions:
        payload = _emission_payload(emission)
        ids = set()
        for raw in payload.get("_billing_visit_ids") or []:
            try:
                ids.add(int(raw))
            except Exception:
                pass

        matched = []
        for billing, visit in rows:
            if visit.fecha != emission.fecha:
                continue
            same_invoice = bool(
                emission.numero_factura
                and billing.numero_factura
                and str(emission.numero_factura) == str(billing.numero_factura)
            )
            if ids and int(visit.id) not in ids and not same_invoice:
                continue
            if not ids and emission.numero_factura and billing.numero_factura and not same_invoice:
                continue
            matched.append(_fiscal_line_snapshot(visit, billing))

        if not matched:
            continue
        payload["_patient_snapshot"] = p_snap
        payload["_billing_snapshot"] = matched
        payload["_snapshot_version"] = "4.4.76"
        _save_emission_payload(emission, payload)
        changed += 1
    return changed


def _trash_emitted_lines(entry: dict) -> list[dict]:
    snap = entry.get("snapshot") or {}
    patient = snap.get("patient") or {}
    result = []
    for visit in snap.get("visits") or []:
        if not isinstance(visit, dict):
            continue
        billing = visit.get("billing") or {}
        if str(billing.get("estado") or "").upper() != "EMITIDA":
            continue
        result.append({
            "patient": patient,
            "visit": {k: v for k, v in visit.items() if k != "billing"},
            "billing": billing,
        })
    return result


def _backfill_active_trash_to_emissions(db) -> int:
    """Repara también pacientes borrados antes de instalar 4.4.76."""
    entries = _active_patient_trash_snapshots()
    if not entries:
        return 0
    changed_records = []
    for entry in entries:
        pid = int(entry["patient_id"])
        lines = _trash_emitted_lines(entry)
        if not lines:
            continue
        dates = sorted({
            str(x["visit"].get("fecha") or "")[:10]
            for x in lines
            if str(x["visit"].get("fecha") or "")[:10]
        })
        parsed_dates = []
        for raw in dates:
            try:
                parsed_dates.append(_date.fromisoformat(raw))
            except Exception:
                pass
        if not parsed_dates:
            continue
        emissions = list(db.scalars(
            core.select(core.AzurEmission).where(
                core.AzurEmission.patient_id == pid,
                core.AzurEmission.fecha.in_(parsed_dates),
            )
        ))
        for emission in emissions:
            payload = _emission_payload(emission)
            if payload.get("_patient_snapshot") and payload.get("_billing_snapshot"):
                continue
            matched = []
            for line in lines:
                v = line["visit"]
                b = line["billing"]
                if str(v.get("fecha") or "")[:10] != emission.fecha.isoformat():
                    continue
                same_invoice = bool(
                    emission.numero_factura
                    and b.get("numero_factura")
                    and str(emission.numero_factura) == str(b.get("numero_factura"))
                )
                if emission.numero_factura and b.get("numero_factura") and not same_invoice:
                    continue
                matched.append({"visit": v, "billing": b})
            if not matched:
                continue
            payload["_patient_snapshot"] = entry["snapshot"].get("patient") or {}
            payload["_billing_snapshot"] = matched
            payload["_snapshot_version"] = "4.4.76-backfill"
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
    if default_history and not desde and not hasta:
        if d < (_date.today() - _timedelta(days=6)):
            return False
    return True


def _archived_emitted_items(db, desde=None, hasta=None) -> list[dict]:
    """Reconstruye facturas emitidas de pacientes eliminados sin revivirlos."""
    hidden = _active_trashed_patient_ids()
    if not hidden:
        return []

    emissions = list(db.scalars(
        core.select(core.AzurEmission)
        .where(core.AzurEmission.patient_id.in_(sorted(hidden)))
        .order_by(core.AzurEmission.fecha.desc(), core.AzurEmission.id.desc())
    ))
    by_patient_date = {}
    for emission in emissions:
        by_patient_date.setdefault((int(emission.patient_id), emission.fecha.isoformat()), []).append(emission)

    items = []
    seen = set()

    # Fuente preferida: snapshots persistentes dentro de AzurEmission.
    for emission in emissions:
        if not _date_allowed(emission.fecha, desde, hasta):
            continue
        payload = _emission_payload(emission)
        patient = payload.get("_patient_snapshot")
        lines = payload.get("_billing_snapshot")
        if not isinstance(patient, dict) or not isinstance(lines, list):
            continue
        az = core.azur_emission_dict(emission)
        for line in lines:
            if not isinstance(line, dict):
                continue
            visit = line.get("visit") or {}
            billing = line.get("billing") or {}
            if str(billing.get("estado") or "").upper() != "EMITIDA":
                continue
            invoice = str(
                billing.get("numero_factura")
                or emission.numero_factura
                or ""
            )
            key = (
                int(patient.get("id") or emission.patient_id or 0),
                int(visit.get("id") or 0),
                int(billing.get("id") or 0),
                invoice,
            )
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "billing": billing,
                "visit": visit,
                "patient": patient,
                "azur": az,
                "billing_group_key": (
                    f"{int(patient.get('id') or emission.patient_id)}:"
                    f"{str(visit.get('fecha') or emission.fecha.isoformat())[:10]}:"
                    f"EMITIDA:{invoice or int(emission.id)}"
                ),
                "archived_deleted_patient": True,
            })

    # Respaldo inmediato: Papelera local (sirve para borrados previos a 4.4.76).
    for entry in _active_patient_trash_snapshots():
        pid = int(entry["patient_id"])
        for line in _trash_emitted_lines(entry):
            patient = line["patient"]
            visit = line["visit"]
            billing = line["billing"]
            raw_date = str(visit.get("fecha") or "")[:10]
            if not _date_allowed(raw_date, desde, hasta):
                continue
            invoice = str(billing.get("numero_factura") or "")
            key = (
                pid,
                int(visit.get("id") or 0),
                int(billing.get("id") or 0),
                invoice,
            )
            if key in seen:
                continue
            seen.add(key)
            az_candidates = by_patient_date.get((pid, raw_date), [])
            az = None
            for emission in az_candidates:
                if invoice and str(emission.numero_factura or "") == invoice:
                    az = emission
                    break
            if az is None and az_candidates:
                az = az_candidates[0]
            items.append({
                "billing": billing,
                "visit": visit,
                "patient": patient,
                "azur": core.azur_emission_dict(az) if az else None,
                "billing_group_key": f"{pid}:{raw_date}:EMITIDA:{invoice or int(billing.get('id') or 0)}",
                "archived_deleted_patient": True,
            })
    return items


def _billing_counts(db, archived_items: list[dict] | None = None) -> dict:
    hidden = _active_trashed_patient_ids()
    rows = db.execute(
        core.select(core.BillingRecord, core.Visit)
        .join(core.Visit, core.BillingRecord.visit_id == core.Visit.id)
        .where(core.Visit.fecha >= core.BILLING_QUEUE_START_DATE)
    ).all()

    pending = set()
    emitted = set()
    for billing, visit in rows:
        pid = int(visit.patient_id)
        if pid in hidden:
            continue
        state = str(billing.estado or "").upper()
        if state in {"PENDIENTE", "APROBADA"}:
            pending.add((pid, visit.fecha.isoformat()))
        elif state == "EMITIDA":
            inv = str(billing.numero_factura or "").strip()
            emitted.add((pid, visit.fecha.isoformat(), inv or f"visit-{int(visit.id)}"))

    for item in archived_items or []:
        p = item.get("patient") or {}
        v = item.get("visit") or {}
        b = item.get("billing") or {}
        try:
            pid = int(p.get("id") or v.get("patient_id") or 0)
        except Exception:
            pid = 0
        fecha = str(v.get("fecha") or "")[:10]
        inv = str(b.get("numero_factura") or "").strip()
        if pid and fecha:
            emitted.add((pid, fecha, inv or f"visit-{int(v.get('id') or 0)}"))

    rejected = set()
    try:
        emissions = list(db.scalars(
            core.select(core.AzurEmission).where(core.AzurEmission.estado == "RECHAZADA")
        ))
        for x in emissions:
            if int(x.patient_id) not in hidden:
                rejected.add((int(x.patient_id), x.fecha.isoformat(), int(x.id)))
    except Exception:
        pass

    return {
        "PENDIENTE": len(pending),
        "APROBADA": 0,
        "EMITIDA": len(emitted),
        "RECHAZADA": len(rejected),
    }


def _billing_action_counts_v4476(db) -> dict[str, int]:
    hidden = _active_trashed_patient_ids()
    rows = db.execute(
        core.select(core.Visit.patient_id, core.Visit.fecha, core.BillingRecord.estado)
        .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
        .where(core.Visit.fecha >= core.BILLING_QUEUE_START_DATE)
    ).all()
    keys = {
        (int(pid), fecha)
        for pid, fecha, estado in rows
        if int(pid) not in hidden
        and str(estado or "").upper() in {"PENDIENTE", "APROBADA"}
    }
    total = len(keys)
    return {"pending": total, "approved": 0, "total": total}


try:
    # Hacer que badges/contadores no incluyan pacientes que ya están en Papelera.
    core._billing_action_counts = _billing_action_counts_v4476

    # Defensa central: ningún flujo de facturación (individual o por lotes) debe
    # volver a tomar líneas de un paciente que Recepción ya envió a Papelera.
    _stable_billing_group_records = core.billing_group_records

    def _billing_group_records_v4476(db, patient_id: int, fecha):
        if int(patient_id) in _active_trashed_patient_ids():
            return []
        return _stable_billing_group_records(db, int(patient_id), fecha)

    core.billing_group_records = _billing_group_records_v4476

    _stable_billing_list = core.billing_list
    _remove_api_route("/api/billing", "GET")

    @app.get("/api/billing")
    def v4476_billing_list(
        estado: str = "TODAS",
        desde: _date | None = None,
        hasta: _date | None = None,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        try:
            _backfill_active_trash_to_emissions(db)
        except Exception:
            pass

        result = dict(_stable_billing_list(estado, desde, hasta, db, user) or {})
        requested = str(estado or "TODAS").strip().upper()
        hidden = _active_trashed_patient_ids()

        visible = []
        for item in list(result.get("items") or []):
            try:
                pid = int((item.get("patient") or {}).get("id") or 0)
            except Exception:
                pid = 0
            # Un paciente eliminado nunca debe volver a aparecer en POR EMITIR.
            if pid in hidden:
                continue
            visible.append(item)

        archived = []
        if requested == "EMITIDA":
            archived = _archived_emitted_items(db, desde, hasta)
            dedupe = set()
            merged = []
            for item in visible + archived:
                p = item.get("patient") or {}
                v = item.get("visit") or {}
                b = item.get("billing") or {}
                key = (
                    int(p.get("id") or v.get("patient_id") or 0),
                    int(v.get("id") or 0),
                    int(b.get("id") or 0),
                    str(b.get("numero_factura") or ""),
                )
                if key in dedupe:
                    continue
                dedupe.add(key)
                merged.append(item)
            visible = merged

        result["items"] = visible
        result["counts"] = _billing_counts(db, archived if requested == "EMITIDA" else None)
        result["v4476_deleted_patients_filtered"] = True
        result["v4476_archived_emitted_history"] = bool(archived)
        return result

    # Antes de borrar un paciente, preservar el mínimo fiscal dentro de AzurEmission.
    _stable_safe_delete_patient = core.ops_safe_delete_patient
    _remove_api_route("/api/safety/patients/{pid}", "DELETE")

    @app.delete("/api/safety/patients/{pid}")
    def v4476_safe_delete_patient(
        pid: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        patient = db.get(core.Patient, int(pid))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        try:
            _preserve_patient_fiscal_history(db, patient)
            # El commit lo realizará el flujo estable de borrado en la misma sesión.
            db.flush()
        except Exception as exc:
            try:
                core.logging.getLogger(__name__).warning(
                    "v4.4.76: no se pudo preparar snapshot fiscal de paciente %s: %s",
                    pid, exc,
                )
            except Exception:
                pass
        return _stable_safe_delete_patient(int(pid), db, user)

    # Una atención ya facturada no debe poder borrarse como si fuera una prueba.
    _stable_safe_delete_visit = core.ops_safe_delete_visit
    _remove_api_route("/api/safety/visits/{visit_id}", "DELETE")

    @app.delete("/api/safety/visits/{visit_id}")
    def v4476_safe_delete_visit(
        visit_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        visit = db.get(core.Visit, int(visit_id))
        if not visit:
            raise core.HTTPException(404, "Atención no encontrada")
        billing = db.scalar(
            core.select(core.BillingRecord).where(
                core.BillingRecord.visit_id == int(visit_id)
            )
        )
        if billing and str(billing.estado or "").upper() == "EMITIDA":
            raise core.HTTPException(
                409,
                "Esta atención ya tiene una factura emitida y no se puede borrar. "
                "El historial fiscal debe conservarse.",
            )
        return _stable_safe_delete_visit(int(visit_id), db, user)

    @app.get("/api/v4476/billing/prior-emissions")
    def v4476_prior_emissions(
        patient_id: int,
        fecha: _date,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        rows = list(db.scalars(
            core.select(core.AzurEmission)
            .where(
                core.AzurEmission.patient_id == int(patient_id),
                core.AzurEmission.fecha == fecha,
            )
            .order_by(core.AzurEmission.id.desc())
        ))
        sent = [
            x for x in rows
            if str(x.clave_acceso or "").strip()
            or str(x.numero_factura or "").strip()
        ]
        return {
            "count": len(sent),
            "items": [
                {
                    "id": int(x.id),
                    "estado": x.estado,
                    "numero_factura": x.numero_factura,
                    "has_clave_acceso": bool(x.clave_acceso),
                }
                for x in sent
            ],
        }

    class V4476ProcedureUpsertIn(core.BaseModel):
        nombre: str
        valor_default: float | None = None

    @app.post("/api/v4476/procedures/upsert")
    def v4476_procedure_upsert(
        data: V4476ProcedureUpsertIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        if core.is_offline_db(db):
            raise core.HTTPException(
                503, "Agregar o reactivar servicios requiere conexión a Internet"
            )
        name = " ".join(str(data.nombre or "").split()).upper()
        if not name:
            raise core.HTTPException(400, "Escribe el nombre del servicio")
        price = data.valor_default
        if price is not None:
            try:
                price = float(price)
            except Exception:
                raise core.HTTPException(400, "El precio no es válido")
            if price < 0:
                raise core.HTTPException(400, "El precio no es válido")

        proc = db.scalar(
            core.select(core.Procedure).where(core.Procedure.nombre == name)
        )
        if proc:
            if int(getattr(proc, "activo", 1) or 0) == 1:
                raise core.HTTPException(409, "Ese servicio ya existe")
            proc.activo = 1
            proc.valor_default = price
            core.audit(db, user, "reactivar_procedimiento", name)
            db.commit()
            try:
                core.mirror_procedure_local(proc)
            except Exception:
                pass
            return {
                "ok": True,
                "restored": True,
                "id": int(proc.id),
                "nombre": proc.nombre,
                "valor_default": float(proc.valor_default) if proc.valor_default is not None else None,
            }

        proc = core.Procedure(nombre=name, valor_default=price, activo=1)
        db.add(proc)
        core.audit(db, user, "crear_procedimiento", name)
        db.commit()
        try:
            core.mirror_procedure_local(proc)
        except Exception:
            pass
        return {
            "ok": True,
            "restored": False,
            "id": int(proc.id),
            "nombre": proc.nombre,
            "valor_default": float(proc.valor_default) if proc.valor_default is not None else None,
        }

    V4476_CSS = r"""
/* v4.4.76 — Servicios y precios: una sola vista, sin tres columnas duplicadas */
[data-config-section="procedimientos"] > .v4476-service-old{
  display:none!important;
}
#v4476ServicePanel{
  width:100%;box-sizing:border-box;display:block!important;
  padding:0!important;margin:0!important
}
.v4476-service-shell{
  width:100%;box-sizing:border-box;border:1px solid #d7e3ed;border-radius:16px;
  background:#fff;overflow:hidden;box-shadow:0 5px 18px rgba(35,67,94,.05)
}
.v4476-service-head{
  display:flex;align-items:flex-start;justify-content:space-between;gap:14px;
  padding:16px 18px;border-bottom:1px solid #e5edf4;background:#f8fbfe
}
.v4476-service-head h3{margin:0!important;font-size:15px!important;color:#294a66!important}
.v4476-service-head p{margin:3px 0 0!important;font-size:10px!important;color:#71869a!important}
.v4476-service-count{
  min-width:34px;height:28px;padding:0 9px;border-radius:999px;background:#eaf3fb;
  color:#315f84;display:grid;place-items:center;font-size:11px;font-weight:950
}
.v4476-service-new{
  display:grid;grid-template-columns:minmax(0,1fr) 130px auto;gap:8px;
  padding:13px 18px;border-bottom:1px solid #e9eff5;background:#fff
}
.v4476-service-new input,.v4476-service-search,.v4476-service-price{
  min-height:36px!important;border:1px solid #ccd9e5!important;border-radius:9px!important;
  background:#fff!important;color:#304b63!important;padding:7px 9px!important;
  font-size:11px!important;box-sizing:border-box!important
}
.v4476-service-new button,.v4476-service-actions button{
  min-height:34px!important;border-radius:9px!important;padding:7px 11px!important;
  font-size:10px!important;font-weight:900!important;cursor:pointer!important
}
.v4476-service-add{
  border:1px solid #72a98a!important;background:#eaf7ef!important;color:#286447!important
}
.v4476-service-tools{padding:10px 18px;border-bottom:1px solid #edf2f6;background:#fbfdff}
.v4476-service-search{width:100%!important}
.v4476-service-list{display:grid;grid-template-columns:1fr;gap:0}
.v4476-service-row{
  display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:11px 18px;border-bottom:1px solid #edf2f6;background:#fff
}
.v4476-service-row:last-child{border-bottom:0}
.v4476-service-name{min-width:0;flex:1}
.v4476-service-name b{
  display:block;font-size:11px;color:#304d66;white-space:normal;overflow-wrap:anywhere
}
.v4476-service-name small{display:block;margin-top:2px;font-size:8px;color:#8797a6}
.v4476-service-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.v4476-service-price{width:105px!important;text-align:right;font-weight:850}
.v4476-service-save{
  border:1px solid #b8cada!important;background:#f6f9fc!important;color:#3e607b!important
}
.v4476-service-delete{
  border:1px solid #dfb4b4!important;background:#fff6f6!important;color:#963d3d!important
}
.v4476-service-empty{padding:25px 18px;text-align:center;color:#778b9e;font-size:11px}
.v4476-service-note{
  padding:10px 18px;background:#fbfdff;border-top:1px solid #edf2f6;
  color:#7a8c9d;font-size:9px;line-height:1.4
}
.v4476-archived-billing-note{
  margin:9px 0;padding:8px 10px;border-radius:9px;border:1px solid #d7e2ec;
  background:#f7fafc;color:#64788d;font-size:10px;font-weight:750
}
@media(max-width:720px){
  .v4476-service-new{grid-template-columns:1fr}
  .v4476-service-row{align-items:flex-start;flex-direction:column;gap:8px}
  .v4476-service-actions{width:100%;justify-content:flex-start}
  .v4476-service-price{flex:1;width:auto!important;min-width:110px}
}
"""

    V4476_JS = r"""
;(()=>{
  if(window.__v4476BillingAndServices)return;
  window.__v4476BillingAndServices=true;
  const VERSION='4.4.76';
  let serviceRows=[];
  let serviceBusy=false;

  const text=v=>String(v??'').replace(/\s+/g,' ').trim();
  const norm=v=>text(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
  const money=v=>{
    const n=Number(v);
    return Number.isFinite(n)?'$'+n.toFixed(2):'Sin precio';
  };
  const apiCall=(url,opt={})=>{
    const fn=window.api;
    return typeof fn==='function'?fn(url,opt):Promise.reject(new Error('API no disponible'));
  };

  // -----------------------------------------------------------------------
  // Facturación: emitidas reales + pacientes borrados fuera de Por emitir.
  // -----------------------------------------------------------------------
  function emittedKey(item){
    const p=item?.patient||{},v=item?.visit||{},b=item?.billing||{},a=item?.azur||{};
    return [
      Number(p.id||v.patient_id||0),
      String(v.fecha||'').slice(0,10),
      String(b.numero_factura||a.numero_factura||b.emitted_at||b.id||'')
    ].join('|');
  }

  function groupEmitted(items){
    const map=new Map();
    for(const item of (Array.isArray(items)?items:[])){
      const key=emittedKey(item);
      let g=map.get(key);
      if(!g){
        g={
          patient:item.patient||{},
          fecha:String(item?.visit?.fecha||'').slice(0,10),
          items:[],
          archived_deleted:!!item.archived_deleted_patient
        };
        map.set(key,g);
      }
      g.items.push(item);
      if(item.archived_deleted_patient)g.archived_deleted=true;
    }
    return [...map.values()].sort((a,b)=>{
      const da=String(a.fecha||''),db=String(b.fecha||'');
      if(da!==db)return db.localeCompare(da);
      const ia=Number(a.items?.[0]?.billing?.id||0),ib=Number(b.items?.[0]?.billing?.id||0);
      return ib-ia;
    });
  }

  function updateEmittedCount(count){
    const box=document.querySelector('#billingSummary');if(!box)return;
    const btn=[...box.querySelectorAll('button')].find(b=>norm(b.textContent).includes('emitida'));
    if(!btn)return;
    const n=btn.querySelector('b');
    if(n)n.textContent=String(Number(count||0));
  }

  async function renderEmittedHistory(){
    const state=String(document.querySelector('#bEstado')?.value||'').toUpperCase();
    if(state!=='EMITIDA')return;
    const list=document.querySelector('#billingList');if(!list)return;
    try{
      const d=await apiCall('/api/billing?estado=EMITIDA');
      const groups=groupEmitted(d?.items||[]);
      try{billingGroupsCache=groups}catch(_e){}
      list.innerHTML=groups.length
        ?groups.map(g=>{
            let html='';
            try{html=typeof window.billingCardHtml==='function'?window.billingCardHtml(g):''}catch(_e){html=''}
            if(!html){
              const total=(g.items||[]).reduce((s,x)=>s+Number(x?.visit?.valor||0),0);
              const inv=String(g.items?.[0]?.billing?.numero_factura||g.items?.[0]?.azur?.numero_factura||'');
              html=`<article class="billing-card emitida"><div class="billing-card-head"><div><div class="billing-patient-name">${esc(g.patient?.nombre||'Paciente')}</div><div class="billing-meta"><span><b>Cédula:</b> ${esc(g.patient?.cedula||'Sin cédula')}</span><span><b>Fecha:</b> ${esc(g.fecha)}</span></div></div><span class="billing-status emitida">EMITIDA</span></div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${money(total)}</strong></div>${inv?`<div class="billing-invoice-number"><span>Factura</span><b>${esc(inv)}</b></div>`:''}</div></article>`;
            }
            return html;
          }).join('')
        :'<div class="billing-empty">No hay facturas emitidas en los últimos 7 días.</div>';
      [...list.querySelectorAll('.billing-card')].forEach((card,i)=>{
        const g=groups[i];
        if(!g?.archived_deleted)return;
        card.dataset.v4476Archived='1';
        const note=document.createElement('div');
        note.className='v4476-archived-billing-note';
        note.textContent='Histórico fiscal conservado · este paciente fue eliminado de Recepción.';
        const lines=card.querySelector('.billing-lines');
        if(lines)lines.insertAdjacentElement('beforebegin',note);
        else card.querySelector('.billing-card-foot')?.insertAdjacentElement('beforebegin',note);
        // Evitar acciones que intenten abrir una ficha que ya no existe.
        card.querySelector('.billing-actions')?.remove();
      });
      updateEmittedCount(groups.length);
    }catch(e){
      console.warn('v4476_emitted_history_failed',e);
    }
  }

  const stableLoadBilling=window.loadBilling;
  if(typeof stableLoadBilling==='function'){
    window.loadBilling=async function(){
      const out=await stableLoadBilling.apply(this,arguments);
      if(String(document.querySelector('#bEstado')?.value||'').toUpperCase()==='EMITIDA'){
        await renderEmittedHistory();
      }
      return out;
    };
  }

  const stableSetBillingStatus=window.setBillingStatus;
  if(typeof stableSetBillingStatus==='function'){
    window.setBillingStatus=async function(next){
      const out=await stableSetBillingStatus.apply(this,arguments);
      if(String(next||'').toUpperCase()==='EMITIDA')await renderEmittedHistory();
      return out;
    };
  }

  // Doble factura el mismo día: no bloquea un cobro legítimo adicional, pero
  // exige una advertencia extra para evitar repetir una factura por accidente.
  const stableApproveBilling=window.approveBilling;
  if(typeof stableApproveBilling==='function'){
    window.approveBilling=async function(patientId,fecha){
      try{
        const d=await apiCall(
          '/api/v4476/billing/prior-emissions?patient_id='+Number(patientId)
          +'&fecha='+encodeURIComponent(String(fecha||'').slice(0,10))
        );
        if(Number(d?.count||0)>0){
          const nums=(d.items||[]).map(x=>x.numero_factura).filter(Boolean).join(', ');
          const msg=`Este paciente ya tiene ${Number(d.count)} factura${Number(d.count)===1?'':'s'} enviada${Number(d.count)===1?'':'s'} en esta fecha${nums?': '+nums:''}.\n\nLa ficha actual es una atención adicional POR EMITIR. ¿Confirmas que realmente deseas generar otra factura?`;
          const ok=typeof window.rpConfirm==='function'
            ?await window.rpConfirm(msg,'Confirmar factura adicional')
            :window.confirm(msg);
          if(!ok)return;
        }
      }catch(_e){}
      return stableApproveBilling.apply(this,arguments);
    };
  }

  // -----------------------------------------------------------------------
  // Servicios y precios: un panel único, sin tres columnas redundantes.
  // -----------------------------------------------------------------------
  function serviceSection(){
    return document.querySelector('[data-config-section="procedimientos"]')
      ||document.querySelector('[data-config-section="services"]')
      ||null;
  }

  function markOldServiceUi(section){
    if(!section)return;
    [...section.children].forEach(el=>{
      if(el.id==='v4476ServicePanel')return;
      el.classList.add('v4476-service-old');
    });
  }

  function filteredServices(){
    const q=norm(document.querySelector('#v4476ServiceSearch')?.value||'');
    if(!q)return serviceRows;
    return serviceRows.filter(x=>norm(x.nombre).includes(q));
  }

  function renderServiceRows(){
    const list=document.querySelector('#v4476ServiceList');if(!list)return;
    const rows=filteredServices();
    list.innerHTML=rows.length?rows.map(p=>`
      <div class="v4476-service-row" data-service-id="${Number(p.id)}">
        <div class="v4476-service-name">
          <b>${esc(p.nombre||'SERVICIO')}</b>
          <small>${p.valor_default==null?'Sin precio configurado':'Precio actual '+money(p.valor_default)}</small>
        </div>
        <div class="v4476-service-actions">
          <input class="v4476-service-price" type="number" min="0" step="0.01"
            value="${p.valor_default==null?'':Number(p.valor_default).toFixed(2)}"
            aria-label="Precio de ${esc(p.nombre||'servicio')}">
          <button type="button" class="v4476-service-save" data-save-service="${Number(p.id)}">Guardar precio</button>
          <button type="button" class="v4476-service-delete" data-delete-service="${Number(p.id)}">Eliminar</button>
        </div>
      </div>`).join('')
      :'<div class="v4476-service-empty">No hay servicios que coincidan.</div>';
  }

  async function fetchServices(){
    const rows=await apiCall('/api/procedures');
    serviceRows=Array.isArray(rows)?rows:[];
    const count=document.querySelector('#v4476ServiceCount');
    if(count)count.textContent=String(serviceRows.length);
    renderServiceRows();
  }

  async function mountServicePanel(){
    if(serviceBusy)return;
    const section=serviceSection();if(!section)return;
    serviceBusy=true;
    try{
      markOldServiceUi(section);
      let panel=document.querySelector('#v4476ServicePanel');
      if(!panel){
        panel=document.createElement('div');
        panel.id='v4476ServicePanel';
        section.appendChild(panel);
      }
      panel.innerHTML=`
        <div class="v4476-service-shell">
          <div class="v4476-service-head">
            <div><h3>Servicios y precios</h3><p>Agrega, cambia el precio o elimina desde una sola lista.</p></div>
            <span id="v4476ServiceCount" class="v4476-service-count">0</span>
          </div>
          <div class="v4476-service-new">
            <input id="v4476NewServiceName" autocomplete="off" placeholder="NOMBRE DEL SERVICIO">
            <input id="v4476NewServicePrice" type="number" min="0" step="0.01" placeholder="PRECIO">
            <button id="v4476AddService" type="button" class="v4476-service-add">+ Agregar</button>
          </div>
          <div class="v4476-service-tools">
            <input id="v4476ServiceSearch" class="v4476-service-search" autocomplete="off" placeholder="BUSCAR SERVICIO">
          </div>
          <div id="v4476ServiceList" class="v4476-service-list"><div class="v4476-service-empty">Cargando servicios…</div></div>
          <div class="v4476-service-note">Si un servicio ya fue usado, “Eliminar” lo archiva: desaparece de nuevas atenciones, pero nunca modifica el historial anterior.</div>
        </div>`;

      panel.oninput=e=>{
        if(e.target?.id==='v4476ServiceSearch')renderServiceRows();
      };
      panel.onclick=async e=>{
        const add=e.target?.closest?.('#v4476AddService');
        const save=e.target?.closest?.('[data-save-service]');
        const del=e.target?.closest?.('[data-delete-service]');
        if(add){
          const name=text(panel.querySelector('#v4476NewServiceName')?.value||'');
          const priceRaw=text(panel.querySelector('#v4476NewServicePrice')?.value||'');
          if(!name){alert('Escribe el nombre del servicio.');return}
          const price=priceRaw===''?null:Number(priceRaw);
          if(price!==null&&(!Number.isFinite(price)||price<0)){alert('Escribe un precio válido.');return}
          add.disabled=true;
          try{
            const r=await apiCall('/api/v4476/procedures/upsert',{
              method:'POST',body:JSON.stringify({nombre:name,valor_default:price})
            });
            panel.querySelector('#v4476NewServiceName').value='';
            panel.querySelector('#v4476NewServicePrice').value='';
            await fetchServices();
            if(typeof window.rpNotice==='function')window.rpNotice(r?.restored?'Servicio reactivado.':'Servicio agregado.');
          }catch(err){alert(err?.message||String(err))}
          finally{add.disabled=false}
          return;
        }
        if(save){
          const row=save.closest('.v4476-service-row');
          const id=Number(save.dataset.saveService||0);
          const input=row?.querySelector('.v4476-service-price');
          const raw=text(input?.value||'');
          const value=raw===''?null:Number(raw);
          if(value!==null&&(!Number.isFinite(value)||value<0)){alert('Escribe un precio válido.');return}
          save.disabled=true;
          try{
            await apiCall('/api/procedures/'+id,{
              method:'PUT',body:JSON.stringify({valor_default:value})
            });
            await fetchServices();
            if(typeof window.rpNotice==='function')window.rpNotice('Precio actualizado.');
          }catch(err){alert(err?.message||String(err));save.disabled=false}
          return;
        }
        if(del){
          const row=del.closest('.v4476-service-row');
          const id=Number(del.dataset.deleteService||0);
          const item=serviceRows.find(x=>Number(x.id)===id);
          const name=text(item?.nombre||row?.querySelector('b')?.textContent||'este servicio');
          if(!window.confirm(`¿Eliminar "${name}"?\n\nSi ya tiene historial se archivará y las atenciones anteriores se conservarán.`))return;
          del.disabled=true;
          try{
            const r=await apiCall('/api/v4475/procedures/'+id+'/delete',{method:'POST',body:'{}'});
            await fetchServices();
            if(typeof window.rpNotice==='function')window.rpNotice(r?.message||'Servicio eliminado.');
          }catch(err){alert(err?.message||String(err));del.disabled=false}
        }
      };

      await fetchServices();
    }catch(e){
      console.warn('v4476_service_panel_failed',e);
    }finally{
      serviceBusy=false;
    }
  }

  document.addEventListener('click',e=>{
    const tab=e.target?.closest?.('[data-config-tab]');
    const key=String(tab?.dataset?.configTab||'').toLowerCase();
    if(key==='procedimientos'||key==='services')setTimeout(mountServicePanel,70);
  });

  const stableLoadProcedures=window.loadProcedures;
  if(typeof stableLoadProcedures==='function'){
    window.loadProcedures=async function(){
      const out=await stableLoadProcedures.apply(this,arguments);
      setTimeout(mountServicePanel,30);
      return out;
    };
  }

  function boot(){
    setTimeout(mountServicePanel,100);
    setTimeout(mountServicePanel,700);
    setTimeout(mountServicePanel,1800);
    if(String(document.querySelector('#bEstado')?.value||'').toUpperCase()==='EMITIDA'){
      setTimeout(renderEmittedHistory,120);
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();

  // Versión: sustitución simple, sin observers.
  try{
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      if(text(el.textContent)!=='v'+VERSION)el.textContent='v'+VERSION;
    });
  }catch(_e){}
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4476_CSS
    )
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "")
        .replace("const VERSION='4.4.75';", "const VERSION='4.4.76';")
        + "\n"
        + V4476_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.76 billing/services patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4476/health")
def v4476_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "deleted_patient_hidden_from_pending_billing": True,
        "emitted_history_survives_patient_delete": True,
        "emitted_invoices_grouped_by_invoice_number": True,
        "same_day_duplicate_invoice_warning": True,
        "emitted_visit_delete_blocked": True,
        "single_service_price_panel": True,
        "fast_save_preserved": True,
        "background_print_preserved": True,
        "uses_new_dom_observer": False,
        "receipt_layout_version": "4.4.69",
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
