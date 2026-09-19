from __future__ import annotations

# v4.5.8 candidate — puente mínimo Recepción -> Historia Clínica.
# No modifica pacientes, facturación ni agenda. Después de que una atención se
# guarda correctamente, encola solo identidad mínima del paciente para que el
# doctor la vea en "Pacientes en espera". Un fallo del puente nunca impide
# guardar la atención de Recepción.

import app_patch_4507 as previous
import app_patch_4504 as payment_core
import historia_bridge

core = previous.core
app = previous.app
APP_VERSION = "4.5.8"

_mod = previous
_seen = set()
for _ in range(160):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

_old_batch = None
for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/visits/batch-payment" and "POST" in set(getattr(_route, "methods", set()) or set()):
        _old_batch = getattr(_route, "endpoint", None)
        app.router.routes.remove(_route)
        break

if _old_batch is None:
    raise RuntimeError("No se encontró /api/visits/batch-payment para activar el puente de Historia Clínica")


@app.post("/api/visits/batch-payment")
def v4508_create_visit_batch_payment(
    data: payment_core.V4504VisitBatchPaymentIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result = _old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            services = list(getattr(data, "services", None) or [])
            procedures = [str(getattr(x, "procedimiento", "") or "").strip() for x in services]
            attention_type = "Consulta" if any(not x for x in procedures) else (procedures[0] if procedures else "Consulta")
            items = list((result or {}).get("items") or []) if isinstance(result, dict) else []
            visit_ids = [x.get("id") for x in items if isinstance(x, dict) and x.get("id") is not None]
            historia_bridge.queue_attention(
                reception_patient_id=int(patient.id),
                display_name=str(getattr(patient, "nombre", "") or "Paciente"),
                identification=str(getattr(patient, "cedula", "") or ""),
                attention_type=attention_type,
                visit_ids=visit_ids,
            )
    except Exception as exc:
        try:
            core.audit(db, user, "historia_bridge_pending", f"Puente Historia Clínica pendiente: {type(exc).__name__}")
            db.commit()
        except Exception:
            pass
    return result


@app.get("/api/historia-bridge/status")
def v4508_historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()

PATCH_BOOT_OK = True