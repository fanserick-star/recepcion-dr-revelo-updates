from __future__ import annotations
import reception_history_transport as _dep_history_transport
import reception_history_bridge as bridge_v4508
import historia_bridge
core = _dep_history_transport.core
app = _dep_history_transport.app
APP_VERSION = '4.5.21'
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)
_TYPE_LABELS = {'N': 'Nuevo', 'S': 'Subsecuente', 'P': 'Procedimiento', 'X': 'Procedimiento'}

@app.post('/api/visits/batch-payment')
def v4521_create_visit_batch_payment(data: bridge_v4508.payment_core.V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    result = bridge_v4508._old_batch(data, db, user)
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
