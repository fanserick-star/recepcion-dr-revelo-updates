from __future__ import annotations

import reception_payment_terminal_manual as _dep_payment_terminal_manual
import reception_payment_terminal as payment_core
import historia_bridge
import reception_history_lan_resilience as _dep_history_lan_resilience  # noqa: F401
import reception_history_cancellation as _dep_history_cancellation  # noqa: F401
import reception_history_identity_name_search as _dep_history_identity_name_search  # noqa: F401

core = _dep_payment_terminal_manual.core
app = _dep_payment_terminal_manual.app
APP_VERSION = str(core.APP_VERSION or "")
_old_batch = payment_core.v4504_create_visit_batch_payment

_TYPE_LABELS = {"N": "Nuevo", "S": "Subsecuente", "P": "Procedimiento", "X": "Procedimiento"}


def _patient_status(type_code: object) -> str:
    code = str(type_code or "").strip().upper()
    return "Nuevo" if code == "N" else "Subsecuente" if code == "S" else ""


def _procedure_attention_type(name: object) -> str:
    label = " ".join(str(name or "").strip().split())
    return f"Procedimiento - {label}" if label else "Procedimiento"


def _reception_turn_for_visit(db, visit_id: object):
    try:
        visit = db.get(core.Visit, int(visit_id))
    except Exception:
        visit = None
    if visit is None or str(getattr(visit, "procedimiento", "") or "").strip():
        return None
    try:
        rows = list(
            db.scalars(
                core.select(core.Visit)
                .where(core.Visit.fecha == visit.fecha)
                .order_by(core.Visit.id.asc())
            )
        )
    except Exception:
        return None
    ordered_patients = []
    seen = set()
    for row in rows:
        if str(getattr(row, "procedimiento", "") or "").strip():
            continue
        pid = int(getattr(row, "patient_id", 0) or 0)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        ordered_patients.append(pid)
    try:
        return ordered_patients.index(int(visit.patient_id)) + 1
    except Exception:
        return None


def _handoff_item(patient, item: dict, fallback_type: object = "", db=None) -> None:
    visit_id = item.get("id")
    if visit_id is None:
        return
    procedure = str(item.get("procedimiento") or "").strip()
    type_code = str(item.get("tipo") or fallback_type or "").strip().upper()
    if procedure:
        attention_type = _procedure_attention_type(procedure)
    else:
        attention_type = _TYPE_LABELS.get(type_code)
        if not attention_type:
            attention_type = "Subsecuente" if type_code == "S" else "Nuevo" if type_code == "N" else "Consulta"
    birth = getattr(patient, "fecha_nacimiento", None)
    reception_turn = _reception_turn_for_visit(db, visit_id) if db is not None else None
    historia_bridge.queue_attention(
        reception_patient_id=int(patient.id),
        display_name=str(getattr(patient, "nombre", "") or "Paciente"),
        identification=str(getattr(patient, "cedula", "") or ""),
        attention_type=attention_type,
        patient_status=_patient_status(type_code),
        reception_turn=reception_turn,
        visit_ids=[visit_id],
        birth_date=str(birth or ""),
        phone=str(getattr(patient, "celular", "") or ""),
        email=str(getattr(patient, "correo", "") or ""),
        address=str(getattr(patient, "lugar", "") or ""),
    )


@app.get("/api/historia-bridge/status")
def historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()


@app.get("/api/history-handoff/health")
def history_handoff_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "single_handoff_wrapper": False,
        "canonical_handoff_owner": "app.py",
        "waiting_queue_transport": "lan_only",
        "lan_online": bool(state.get("lan_online")),
        "pending": int(state.get("pending") or 0),
        "handoff_pending": int(state.get("handoff_pending") or 0),
        "control_pending": int(state.get("control_pending") or 0),
        "delete_sync_active": bool(getattr(_dep_history_cancellation, "PATCH_DELETE_HISTORY_CANCEL_OK", False)),
        "lan_auto_recovery": bool(state.get("lan_auto_recovery")),
        "lan_active_subnet_scan": bool(state.get("lan_active_subnet_scan")),
        "history_name_first_search": bool(getattr(_dep_history_identity_name_search, "PATCH_BOOT_OK", False)),
    }

PATCH_BOOT_OK = True
