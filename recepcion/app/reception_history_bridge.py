from __future__ import annotations

import reception_payment_terminal_manual as _dep_payment_terminal_manual
import reception_payment_terminal as payment_core
import historia_bridge
import reception_history_cancellation as _dep_history_cancellation  # noqa: F401
import reception_history_lan_resilience as _dep_history_lan_resilience  # noqa: F401

core = _dep_payment_terminal_manual.core
app = _dep_payment_terminal_manual.app
APP_VERSION = "4.6.25"
core.APP_VERSION = APP_VERSION

_old_batch = None
for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/visits/batch-payment" and "POST" in set(getattr(_route, "methods", set()) or set()):
        _old_batch = getattr(_route, "endpoint", None)
        app.router.routes.remove(_route)
        break
if _old_batch is None:
    raise RuntimeError("No se encontró /api/visits/batch-payment para activar Historia Clínica")

_TYPE_LABELS = {"N": "Nuevo", "S": "Subsecuente", "P": "Procedimiento", "X": "Procedimiento"}


def _patient_status(type_code: object) -> str:
    code = str(type_code or "").strip().upper()
    return "Nuevo" if code == "N" else "Subsecuente" if code == "S" else ""


def _procedure_attention_type(name: object) -> str:
    label = " ".join(str(name or "").strip().split())
    return f"Procedimiento - {label}" if label else "Procedimiento"


def _handoff_item(patient, item: dict, fallback_type: object = "") -> None:
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
    historia_bridge.queue_attention(
        reception_patient_id=int(patient.id),
        display_name=str(getattr(patient, "nombre", "") or "Paciente"),
        identification=str(getattr(patient, "cedula", "") or ""),
        attention_type=attention_type,
        patient_status=_patient_status(type_code),
        reception_turn=None,
        visit_ids=[visit_id],
        birth_date=str(birth or ""),
        phone=str(getattr(patient, "celular", "") or ""),
        email=str(getattr(patient, "correo", "") or ""),
        address=str(getattr(patient, "lugar", "") or ""),
    )


@app.post("/api/visits/batch-payment")
def create_visit_batch_payment(
    data: payment_core.V4504VisitBatchPaymentIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result = _old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            items = [x for x in list((result or {}).get("items") or []) if isinstance(x, dict)] if isinstance(result, dict) else []
            for item in items:
                _handoff_item(patient, item, getattr(data, "tipo", ""))
    except Exception as exc:
        try:
            core.audit(db, user, "historia_bridge_pending", f"Puente Historia Clínica pendiente: {type(exc).__name__}")
            db.commit()
        except Exception:
            pass
    return result


@app.get("/api/historia-bridge/status")
def historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()


@app.get("/api/history-handoff/health")
def history_handoff_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "single_handoff_wrapper": True,
        "waiting_queue_transport": "lan_only",
        "lan_online": bool(state.get("lan_online")),
        "pending": int(state.get("pending") or 0),
        "delete_sync_active": bool(getattr(_dep_history_cancellation, "PATCH_DELETE_HISTORY_CANCEL_OK", False)),
        "lan_auto_recovery": bool(state.get("lan_auto_recovery")),
        "lan_active_subnet_scan": bool(state.get("lan_active_subnet_scan")),
    }

PATCH_BOOT_OK = True
