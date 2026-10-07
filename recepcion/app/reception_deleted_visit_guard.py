from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import reception_payment_terminal_panel as _dep
import historia_bridge
import historia_lan_transport

core = _dep.core
app = _dep.app

# Guard permanente para atenciones que el usuario ya eliminó/canceló.
# Fuentes locales de verdad:
#   1) Papelera de Recepción (cuando existe snapshot recuperable).
#   2) Handoff LAN de Historia marcado cancelled=1 por un borrado explícito.
# Nunca usamos los handoffs expirados automáticamente como una eliminación clínica.

_CACHE_LOCK = threading.Lock()
_CACHE = {"ts": 0.0, "ids": set(), "sources": 0}
_CACHE_SECONDS = 0.8


def _norm_name(value: object) -> str:
    try:
        return core.normalize_lookup_name(str(value or ""))
    except Exception:
        return " ".join(str(value or "").upper().split())


def _norm_proc(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _parse_date(value: object):
    try:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return date.fromisoformat(str(value or "")[:10])
    except Exception:
        return None


def _parse_dt(value: object):
    try:
        if isinstance(value, datetime):
            return value
        raw = str(value or "").strip()
        return datetime.fromisoformat(raw) if raw else None
    except Exception:
        return None


def _visit_spec_from_trash(item) -> dict | None:
    try:
        payload = json.loads(str(item.snapshot_json or "{}"))
        snap = payload.get("visit") or {}
        if not isinstance(snap, dict):
            return None
        label = str(item.label or "")
        name = label.split(" · ", 1)[0].strip() if " · " in label else ""
        return {
            "source": "trash",
            "visit_ids": {int(snap.get("id") or item.entity_id)},
            "patient_id": int(snap.get("patient_id") or item.patient_id or 0),
            "patient_name": name,
            "fecha": _parse_date(snap.get("fecha")),
            "procedimiento": _norm_proc(snap.get("procedimiento")),
            "valor": float(snap.get("valor") or 0),
            "created_at": _parse_dt(snap.get("created_at")),
        }
    except Exception:
        return None


def _trash_specs(ldb) -> list[dict]:
    try:
        core._ops_ensure_trash_table(ldb)
        cutoff = datetime.utcnow() - timedelta(days=max(7, int(getattr(core, "TRASH_RETENTION_DAYS", 7) or 7)))
        rows = list(
            ldb.scalars(
                core.select(core.TrashItem)
                .where(
                    core.TrashItem.entity_type == "visit",
                    core.TrashItem.restored_at.is_(None),
                    core.TrashItem.deleted_at >= cutoff,
                )
                .order_by(core.TrashItem.deleted_at.desc())
            )
        )
    except Exception:
        return []
    out = []
    for item in rows:
        spec = _visit_spec_from_trash(item)
        if spec:
            out.append(spec)
    return out


def _cancelled_handoff_specs() -> list[dict]:
    path = Path(historia_lan_transport.LAN_OUTBOX_DB)
    if not path.is_file():
        return []
    cutoff = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT payload_json,created_at,last_error
                FROM events
                WHERE created_at>=?
                  AND cancelled=1
                ORDER BY created_at DESC
                LIMIT 200
                """,
                (cutoff,),
            ).fetchall()
    except Exception:
        return []
    out = []
    for payload_json, created_at, last_error in rows:
        # Expirar un handoff viejo no significa borrar la atención de Recepción.
        if str(last_error or "").strip().lower() == "expired_previous_day":
            continue
        try:
            payload = json.loads(payload_json)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("action") or "handoff").strip().lower() != "handoff":
            continue
        ids = set()
        for value in payload.get("visit_ids") or []:
            try:
                ids.add(int(value))
            except Exception:
                pass
        if not ids:
            continue
        attention = str(payload.get("attention_type") or "").strip()
        proc = ""
        if "·" in attention:
            proc = attention.split("·", 1)[1].strip()
        out.append(
            {
                "source": "historia-cancel",
                "visit_ids": ids,
                "patient_id": int(str(payload.get("reception_patient_id") or "0") or 0),
                "patient_name": str(payload.get("display_name") or "").strip(),
                "fecha": _parse_date(created_at),
                "procedimiento": _norm_proc(proc),
                "valor": None,
                "created_at": _parse_dt(created_at),
            }
        )
    return out


def _same_value(left, right) -> bool:
    if right is None:
        return True
    try:
        return abs(float(left or 0) - float(right)) < 0.005
    except Exception:
        return False


def _candidate_matches(visit, patient, spec: dict) -> bool:
    try:
        vid = int(visit.id)
    except Exception:
        return False
    direct = vid in set(spec.get("visit_ids") or set())
    fecha = spec.get("fecha")
    if fecha and getattr(visit, "fecha", None) != fecha:
        return False
    expected_proc = _norm_proc(spec.get("procedimiento"))
    current_proc = _norm_proc(getattr(visit, "procedimiento", None))
    if expected_proc != current_proc:
        # Para un handoff "Consulta" ambos deben ser vacíos.
        return False
    if not _same_value(getattr(visit, "valor", None), spec.get("valor")):
        return False

    wanted_pid = int(spec.get("patient_id") or 0)
    wanted_name = _norm_name(spec.get("patient_name"))
    if wanted_name:
        if patient is None or _norm_name(getattr(patient, "nombre", "")) != wanted_name:
            return False
    elif wanted_pid and int(getattr(visit, "patient_id", 0) or 0) != wanted_pid:
        return False
    elif not direct:
        return False

    wanted_created = spec.get("created_at")
    current_created = _parse_dt(getattr(visit, "created_at", None))
    if wanted_created and current_created:
        # El handoff se crea inmediatamente después de la atención. Un margen de
        # 20 min permite diferencias de reloj, pero evita ocultar una nueva consulta
        # legítima del mismo paciente varias horas después.
        if abs((current_created - wanted_created).total_seconds()) > 20 * 60:
            return False
    return True


def _matched_visit_ids(ldb, specs: list[dict]) -> set[int]:
    found: set[int] = set()
    for spec in specs:
        candidates = {}
        for vid in spec.get("visit_ids") or set():
            try:
                visit = ldb.get(core.Visit, int(vid))
            except Exception:
                visit = None
            if visit is not None:
                patient = ldb.get(core.Patient, int(visit.patient_id))
                if _candidate_matches(visit, patient, spec):
                    candidates[int(visit.id)] = visit

        # Si Neon volvió a descargar la atención con otro ID, la recuperamos por
        # fecha + paciente + servicio + hora aproximada. Solo aceptamos coincidencia única.
        fecha = spec.get("fecha")
        if fecha and not candidates:
            try:
                rows = list(
                    ldb.execute(
                        core.select(core.Visit, core.Patient)
                        .join(core.Patient, core.Visit.patient_id == core.Patient.id)
                        .where(core.Visit.fecha == fecha)
                    ).all()
                )
            except Exception:
                rows = []
            for visit, patient in rows:
                if _candidate_matches(visit, patient, spec):
                    candidates[int(visit.id)] = visit

        if len(candidates) == 1:
            found.add(next(iter(candidates)))
    return found


def active_deleted_visit_ids(ldb=None, force: bool = False) -> set[int]:
    now = time.monotonic()
    if ldb is None and not force:
        with _CACHE_LOCK:
            if now - float(_CACHE.get("ts") or 0) < _CACHE_SECONDS:
                return set(_CACHE.get("ids") or set())

    own = ldb is None
    if own:
        ldb = core.LocalSessionLocal()
    try:
        specs = _trash_specs(ldb) + _cancelled_handoff_specs()
        ids = _matched_visit_ids(ldb, specs)
    finally:
        if own:
            try:
                ldb.close()
            except Exception:
                pass
    if own:
        with _CACHE_LOCK:
            _CACHE["ts"] = now
            _CACHE["ids"] = set(ids)
            _CACHE["sources"] = len(specs)
    return set(ids)


def _clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE["ts"] = 0.0
        _CACHE["ids"] = set()


core.active_deleted_visit_ids = active_deleted_visit_ids


# ---------------------------------------------------------------------------
# Sincronización robusta: un delete nunca se declara exitoso contra el ID equivocado.
# ---------------------------------------------------------------------------
_STABLE_SYNC_ONE = core.sync_one_operation


def _cloud_patient_for_delete(payload: dict, ldb, cdb):
    ids = []
    for raw in (
        core.get_id_map(ldb, "patient", int(payload.get("patient_id") or 0)) if payload.get("patient_id") else None,
        payload.get("cloud_patient_id"),
        payload.get("patient_id"),
    ):
        try:
            value = int(raw)
        except Exception:
            continue
        if value and value not in ids:
            ids.append(value)
    for pid in ids:
        p = cdb.get(core.Patient, pid)
        if p is not None:
            return p

    ced = str(payload.get("patient_cedula") or "").strip()
    if ced:
        rows = list(cdb.scalars(core.select(core.Patient).where(core.Patient.cedula == ced).limit(3)))
        if len(rows) == 1:
            return rows[0]

    name = str(payload.get("patient_name") or "").strip()
    if name:
        wanted = _norm_name(name)
        rows = list(cdb.scalars(core.select(core.Patient).limit(5000)))
        matched = [p for p in rows if _norm_name(getattr(p, "nombre", "")) == wanted]
        if len(matched) == 1:
            return matched[0]
    return None


def _visit_delete_match(payload: dict, ldb, cdb):
    local_id = int(payload["visit_id"])
    candidate_ids = []
    for raw in (
        core.get_id_map(ldb, "visit", local_id),
        payload.get("cloud_visit_id"),
        local_id,
    ):
        try:
            value = int(raw)
        except Exception:
            continue
        if value and value not in candidate_ids:
            candidate_ids.append(value)
    for vid in candidate_ids:
        row = cdb.get(core.Visit, vid)
        if row is not None:
            return row, vid, True

    patient = _cloud_patient_for_delete(payload, ldb, cdb)
    fecha = _parse_date(payload.get("fecha"))
    if patient is None or fecha is None:
        return None, (candidate_ids[0] if candidate_ids else local_id), False

    rows = list(
        cdb.scalars(
            core.select(core.Visit).where(
                core.Visit.patient_id == int(patient.id),
                core.Visit.fecha == fecha,
            )
        )
    )
    proc = _norm_proc(payload.get("procedimiento"))
    rows = [v for v in rows if _norm_proc(getattr(v, "procedimiento", None)) == proc]
    if payload.get("valor") is not None:
        rows = [v for v in rows if _same_value(getattr(v, "valor", None), payload.get("valor"))]

    created = _parse_dt(payload.get("created_at"))
    if len(rows) > 1 and created:
        close = []
        for v in rows:
            v_created = _parse_dt(getattr(v, "created_at", None))
            if v_created and abs((v_created - created).total_seconds()) <= 20 * 60:
                close.append(v)
        rows = close

    if len(rows) > 1:
        raise RuntimeError(
            "Borrado detenido: hay varias atenciones remotas parecidas y no es seguro elegir una automáticamente."
        )
    if len(rows) == 1:
        return rows[0], int(rows[0].id), True
    # Paciente + fecha + servicio fueron identificados y no existe la atención:
    # el borrado ya quedó aplicado en nube.
    return None, (candidate_ids[0] if candidate_ids else local_id), True


def _sync_one_operation_guard(q, ldb, cdb):
    if q.operation != "visit.delete":
        return _STABLE_SYNC_ONE(q, ldb, cdb)

    already = cdb.get(core.SyncOperation, q.token)
    if already:
        return already.result_id

    payload = json.loads(q.payload or "{}")
    row, result_id, identified = _visit_delete_match(payload, ldb, cdb)
    if not identified:
        raise RuntimeError(
            "Borrado pendiente: no se pudo identificar con seguridad la atención remota. Se conservará el intento y no se recargará desde Neon."
        )

    if row is not None:
        billing = cdb.scalar(
            core.select(core.BillingRecord).where(core.BillingRecord.visit_id == int(row.id))
        )
        fiscal_emission = cdb.scalar(
            core.select(core.AzurEmission)
            .where(
                core.AzurEmission.patient_id == int(row.patient_id),
                core.AzurEmission.fecha == row.fecha,
                core.or_(
                    core.AzurEmission.clave_acceso.is_not(None),
                    core.AzurEmission.numero_factura.is_not(None),
                ),
            )
            .order_by(core.AzurEmission.id.desc())
        )
        if (
            billing and str(getattr(billing, "estado", "") or "").strip().upper() == "EMITIDA"
        ) or fiscal_emission is not None:
            raise RuntimeError(
                "La atención tiene comprobante fiscal emitido/enviado. Se conserva el registro fiscal y se oculta del flujo clínico."
            )
        cdb.delete(row)

    core.audit(
        cdb,
        q.username,
        "sincronizar_borrado_atencion_seguro",
        f"Atención local {payload.get('visit_id')} -> nube {result_id}",
    )
    cdb.add(core.SyncOperation(token=q.token, operation=q.operation, result_id=int(result_id or 0)))
    return int(result_id or 0)


core.sync_one_operation = _sync_one_operation_guard


# ---------------------------------------------------------------------------
# Filtros: una atención explícitamente borrada no cuenta ni reaparece en UI.
# ---------------------------------------------------------------------------
_STABLE_REPORT_DATA = core.build_report_data


def _build_report_data_guard(rows):
    hidden = active_deleted_visit_ids()
    if hidden:
        rows = [pair for pair in rows if int(getattr(pair[0], "id", 0) or 0) not in hidden]
    return _STABLE_REPORT_DATA(rows)


core.build_report_data = _build_report_data_guard

_STABLE_GROUP_RECORDS = core.billing_group_records


def _billing_group_records_guard(db, patient_id: int, fecha):
    rows = _STABLE_GROUP_RECORDS(db, int(patient_id), fecha)
    hidden = active_deleted_visit_ids()
    return [
        (billing, visit)
        for billing, visit in rows
        if int(getattr(visit, "id", 0) or 0) not in hidden
        or str(getattr(billing, "estado", "") or "").strip().upper() == "EMITIDA"
    ]


core.billing_group_records = _billing_group_records_guard


def _pending_count_guard(db) -> int:
    hidden = active_deleted_visit_ids()
    rows = db.execute(
        core.select(core.Visit.patient_id, core.Visit.fecha, core.Visit.id)
        .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
        .where(
            core.Visit.fecha >= core.BILLING_QUEUE_START_DATE,
            core.BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]),
        )
    ).all()
    return len(
        {
            (int(pid), fecha)
            for pid, fecha, visit_id in rows
            if int(visit_id) not in hidden
        }
    )


core._billing_pending_count = _pending_count_guard


def _remove_route(path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in set(getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _filtered_day(data: dict) -> dict:
    out = dict(data or {})
    hidden = active_deleted_visit_ids()
    visits = [
        row for row in list(out.get("visits") or [])
        if int(row.get("id") or 0) not in hidden
    ]
    out["visits"] = visits
    patient_ids = {int((row.get("patient") or {}).get("id") or row.get("patient_id") or 0) for row in visits}
    patient_ids.discard(0)
    new_ids = {
        int((row.get("patient") or {}).get("id") or row.get("patient_id") or 0)
        for row in visits
        if str(row.get("tipo") or "").upper() == "N"
    }
    new_ids.discard(0)
    out["count"] = len(patient_ids)
    out["N"] = len(new_ids)
    out["S"] = len(patient_ids - new_ids)
    out["P"] = sum(1 for row in visits if bool(str(row.get("procedimiento") or "").strip()) or str(row.get("tipo") or "").upper() == "P")
    out["total"] = round(sum(float(row.get("valor") or 0) for row in visits), 2)
    return out


_OLD_TODAY = _remove_route("/api/today", "GET")
if _OLD_TODAY is not None:
    @app.get("/api/today")
    def today_guard(fecha: date = date.today(), db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        return _filtered_day(_OLD_TODAY(fecha, db, user))


_OLD_HOME_WEEK = _remove_route("/api/home/week", "GET")
if _OLD_HOME_WEEK is not None:
    @app.get("/api/home/week")
    def home_week_guard(anchor: date, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        result = dict(_OLD_HOME_WEEK(anchor, db, user) or {})
        days = []
        for item in list(result.get("days") or []):
            x = dict(item)
            x["data"] = _filtered_day(dict(x.get("data") or {}))
            days.append(x)
        result["days"] = days
        return result


_OLD_DASHBOARD = _remove_route("/api/dashboard", "GET")
if _OLD_DASHBOARD is not None:
    @app.get("/api/dashboard")
    def dashboard_guard(fecha: date = date.today(), db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        base = dict(_OLD_DASHBOARD(fecha, db, user) or {})
        hidden = active_deleted_visit_ids()
        rows = db.execute(core.select(core.Visit, core.Patient).join(core.Patient).where(core.Visit.fecha == fecha)).all()
        rows = [(v, p) for v, p in rows if int(v.id) not in hidden]
        patient_ids = {int(p.id) for _v, p in rows}
        new_ids = {int(p.id) for v, p in rows if str(v.tipo or "").upper() == "N"}
        base.update(
            {
                "patients": len(patient_ids),
                "new": len(new_ids),
                "subsequent": len(patient_ids - new_ids),
                "procedures": sum(1 for v, _p in rows if core.is_procedure(v)),
                "total": round(sum(float(v.valor or 0) for v, _p in rows), 2),
                "billing_pending": _pending_count_guard(db),
            }
        )
        return base


_OLD_PATIENT = _remove_route("/api/patients/{pid}", "GET")
if _OLD_PATIENT is not None:
    @app.get("/api/patients/{pid}")
    def patient_guard(pid: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        result = dict(_OLD_PATIENT(int(pid), db, user) or {})
        hidden = active_deleted_visit_ids()
        visits = [v for v in list(result.get("visits") or []) if int(v.get("id") or 0) not in hidden]
        result["visits"] = visits
        result["ultima_atencion"] = visits[0].get("fecha") if visits else None
        if not visits and not result.get("historical"):
            try:
                p = db.get(core.Patient, int(pid))
                hist = core.historical_summary_for_patient(p) if p is not None else None
                result["historical"] = hist
                result["suggested_type"] = "S" if hist else "N"
            except Exception:
                result["suggested_type"] = "N"
        elif visits:
            result["suggested_type"] = "S"
        return result


_OLD_PROFILE = _remove_route("/api/patients/{pid}/profile", "GET")
if _OLD_PROFILE is not None:
    @app.get("/api/patients/{pid}/profile")
    def patient_profile_guard(pid: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        result = dict(_OLD_PROFILE(int(pid), db, user) or {})
        hidden = active_deleted_visit_ids()
        visits = [v for v in list(result.get("visits") or []) if int(v.get("id") or 0) not in hidden]
        result["visits"] = visits
        result["ultima_atencion"] = visits[0].get("fecha") if visits else None
        billing = []
        for item in list(result.get("billing") or []):
            vid = int(item.get("visit_id") or 0)
            state = str(item.get("estado") or "").strip().upper()
            if vid in hidden and state != "EMITIDA":
                continue
            if vid in hidden and state == "EMITIDA":
                item = dict(item)
                item["cancelled_attention"] = True
            billing.append(item)
        result["billing"] = billing
        result["deleted_visit_guard"] = True
        return result


_OLD_BILLING = _remove_route("/api/billing", "GET")
if _OLD_BILLING is not None:
    @app.get("/api/billing")
    def billing_guard(
        estado: str = "TODAS",
        desde: date | None = None,
        hasta: date | None = None,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        result = dict(_OLD_BILLING(estado, desde, hasta, db, user) or {})
        requested = str(estado or "TODAS").strip().upper()
        hidden = active_deleted_visit_ids()
        items = []
        for item in list(result.get("items") or []):
            vid = int((item.get("visit") or {}).get("id") or 0)
            state = str((item.get("billing") or {}).get("estado") or "").strip().upper()
            if vid in hidden and state != "EMITIDA":
                continue
            if vid in hidden and state == "EMITIDA":
                item = dict(item)
                item["cancelled_attention"] = True
            items.append(item)
        result["items"] = items
        counts = dict(result.get("counts") or {})
        counts["PENDIENTE"] = _pending_count_guard(db)
        counts["APROBADA"] = 0
        result["counts"] = counts
        result["deleted_visit_guard"] = True
        return result


_OLD_BILLING_NEXT = _remove_route("/api/billing/next", "GET")
if _OLD_BILLING_NEXT is not None:
    @app.get("/api/billing/next")
    def billing_next_guard(db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        hidden = active_deleted_visit_ids()
        stmt = (
            core.select(core.Visit.patient_id, core.Visit.fecha, core.func.min(core.Visit.id).label("first_visit"))
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.fecha >= core.BILLING_QUEUE_START_DATE,
                core.BillingRecord.estado == "PENDIENTE",
            )
        )
        if hidden:
            stmt = stmt.where(core.Visit.id.notin_(sorted(hidden)))
        target = db.execute(
            stmt.group_by(core.Visit.patient_id, core.Visit.fecha)
            .order_by(core.Visit.fecha.asc(), core.func.min(core.Visit.id).asc())
            .limit(1)
        ).first()
        if not target:
            return {"items": []}
        patient_id, fecha, _first = target
        p = db.get(core.Patient, int(patient_id))
        rows = [
            (b, v)
            for b, v in core.billing_group_records(db, int(patient_id), fecha)
            if str(getattr(b, "estado", "") or "").upper() == "PENDIENTE"
            and int(getattr(v, "id", 0) or 0) not in hidden
        ]
        return {
            "items": [
                {"billing": core.billing_dict(b), "visit": core.v_dict(v), "patient": core.p_dict(p)}
                for b, v in rows
            ],
            "patient": core.p_dict(p) if p else None,
            "fecha": fecha,
            "billing_preference": core.billing_preference_dict(core._billing_preference_for_patient(db, int(patient_id))) if p else None,
        }


# ---------------------------------------------------------------------------
# Auto-reparación al arrancar.
# - Si no está emitida: vuelve a poner el DELETE en cola y quita el fantasma local.
# - Si está emitida: no toca la factura; la supresión anterior basta.
# ---------------------------------------------------------------------------
def reconcile_resurrected_deleted_visits() -> dict:
    hidden = active_deleted_visit_ids(force=True)
    repaired = 0
    preserved_fiscal = 0
    if not hidden:
        return {"repaired": 0, "preserved_fiscal": 0}

    with core.LocalSessionLocal() as ldb:
        for vid in sorted(hidden):
            visit = ldb.get(core.Visit, int(vid))
            if visit is None:
                continue
            billing = ldb.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id == int(vid)))
            state = str(getattr(billing, "estado", "") or "").strip().upper() if billing else ""
            fiscal_emission = ldb.scalar(
                core.select(core.AzurEmission)
                .where(
                    core.AzurEmission.patient_id == int(visit.patient_id),
                    core.AzurEmission.fecha == visit.fecha,
                    core.or_(
                        core.AzurEmission.clave_acceso.is_not(None),
                        core.AzurEmission.numero_factura.is_not(None),
                    ),
                )
                .order_by(core.AzurEmission.id.desc())
            )
            if state == "EMITIDA" or fiscal_emission is not None:
                preserved_fiscal += 1
                continue

            exists = False
            for q in ldb.scalars(core.select(core.OfflineQueue).where(core.OfflineQueue.operation == "visit.delete")):
                try:
                    payload = json.loads(q.payload or "{}")
                    if int(payload.get("visit_id") or 0) == int(vid):
                        exists = True
                        break
                except Exception:
                    continue

            patient = ldb.get(core.Patient, int(visit.patient_id))
            if not exists:
                payload = {
                    "visit_id": int(vid),
                    "cloud_visit_id": core.get_id_map(ldb, "visit", int(vid)),
                    "patient_id": int(visit.patient_id),
                    "cloud_patient_id": core.get_id_map(ldb, "patient", int(visit.patient_id)),
                    "patient_cedula": str(getattr(patient, "cedula", "") or "") if patient else "",
                    "patient_name": str(getattr(patient, "nombre", "") or "") if patient else "",
                    "fecha": visit.fecha.isoformat() if visit.fecha else "",
                    "tipo": str(visit.tipo or ""),
                    "procedimiento": visit.procedimiento,
                    "valor": float(visit.valor) if visit.valor is not None else None,
                    "created_at": visit.created_at.isoformat() if getattr(visit, "created_at", None) else "",
                }
                core.add_queue(ldb, "visit.delete", "visit", payload, "system", int(vid))

            try:
                ldb.add(
                    core.Audit(
                        username="system",
                        action="reparar_atencion_eliminada_reaparecida",
                        detail=f"Atención {vid}; se mantiene eliminada y se reintenta borrado remoto",
                    )
                )
            except Exception:
                pass
            ldb.delete(visit)
            ldb.commit()
            repaired += 1

    _clear_cache()
    # El control remoto es idempotente. No llama al siguiente turno.
    for spec in _cancelled_handoff_specs():
        for vid in spec.get("visit_ids") or set():
            try:
                historia_bridge.cancel_attention(
                    visit_id=int(vid),
                    reception_patient_id=str(spec.get("patient_id") or ""),
                )
            except Exception:
                pass

    return {"repaired": repaired, "preserved_fiscal": preserved_fiscal}


core.reconcile_resurrected_deleted_visits = reconcile_resurrected_deleted_visits


@app.on_event("startup")
def _deleted_visit_guard_startup():
    def work():
        time.sleep(1.2)
        try:
            reconcile_resurrected_deleted_visits()
        except Exception:
            pass
    threading.Thread(target=work, daemon=True, name="deleted-visit-guard").start()


@app.get("/api/deleted-visit-guard/health")
def deleted_visit_guard_health(user=core.Depends(core.current_user)):
    ids = active_deleted_visit_ids(force=True)
    with _CACHE_LOCK:
        sources = int(_CACHE.get("sources") or 0)
    return {
        "ok": True,
        "suppressed_visit_ids": sorted(ids),
        "suppressed_count": len(ids),
        "evidence_sources": sources,
        "cloud_delete_safe_matching": True,
        "emitted_invoice_preserved": True,
        "pending_deleted_visit_requeued": True,
        "cancelled_historia_never_restored": True,
    }


PATCH_BOOT_OK = True
