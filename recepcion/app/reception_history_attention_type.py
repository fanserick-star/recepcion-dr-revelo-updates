from __future__ import annotations
import threading
import time
from datetime import datetime, timedelta
import reception_history_transport as _dep_history_transport
import reception_history_bridge as bridge_v4508
import historia_bridge
import historia_lan_transport
core = _dep_history_transport.core
app = _dep_history_transport.app
APP_VERSION = '4.5.21'
core.APP_VERSION = APP_VERSION
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)
_TYPE_LABELS = {'N': 'Nuevo', 'S': 'Subsecuente', 'P': 'Procedimiento', 'X': 'Procedimiento'}


def _patient_status(type_code: object) -> str:
    code = str(type_code or '').strip().upper()
    return 'Nuevo' if code == 'N' else 'Subsecuente' if code == 'S' else ''


def _procedure_attention_type(name: object) -> str:
    label = ' '.join(str(name or '').strip().split())
    return f'Procedimiento - {label}' if label else 'Procedimiento'


def _handoff_item(patient, item: dict, fallback_type: object = '') -> None:
    visit_id = item.get('id')
    if visit_id is None:
        return
    procedure = str(item.get('procedimiento') or '').strip()
    type_code = str(item.get('tipo') or fallback_type or '').strip().upper()
    if procedure:
        attention_type = _procedure_attention_type(procedure)
    else:
        attention_type = _TYPE_LABELS.get(type_code)
        if not attention_type:
            attention_type = 'Subsecuente' if type_code == 'S' else 'Nuevo' if type_code == 'N' else 'Consulta'
    historia_bridge.queue_attention(
        reception_patient_id=int(patient.id),
        display_name=str(getattr(patient, 'nombre', '') or 'Paciente'),
        identification=str(getattr(patient, 'cedula', '') or ''),
        attention_type=attention_type,
        patient_status=_patient_status(type_code),
        reception_turn=None,
        visit_ids=[visit_id],
        birth_date=str(getattr(patient, 'fecha_nacimiento', '') or ''),
        phone=str(getattr(patient, 'celular', '') or ''),
        email=str(getattr(patient, 'correo', '') or ''),
        address=str(getattr(patient, 'lugar', '') or ''),
    )


@app.post('/api/visits/batch-payment')
def v4521_create_visit_batch_payment(data: bridge_v4508.payment_core.V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    result = bridge_v4508._old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            items = [x for x in list((result or {}).get('items') or []) if isinstance(x, dict)] if isinstance(result, dict) else []
            for item in items:
                _handoff_item(patient, item, getattr(data, 'tipo', ''))
    except Exception as exc:
        try:
            core.audit(db, user, 'historia_bridge_pending', f'Puente Historia Clínica pendiente: {type(exc).__name__}')
            db.commit()
        except Exception:
            pass
    return result


def _recover_recent_procedures() -> None:
    """Recupera procedimientos recién creados antes de 4.6.23 sin recrearlos."""
    time.sleep(4)
    cutoff = datetime.utcnow() - timedelta(hours=3)
    try:
        with core.LocalSessionLocal() as ldb:
            rows = list(ldb.scalars(
                core.select(core.Visit)
                .where(core.Visit.created_at >= cutoff)
                .order_by(core.Visit.created_at.asc(), core.Visit.id.asc())
            ))
            work = []
            for visit in rows:
                procedure = str(getattr(visit, 'procedimiento', '') or '').strip()
                if not procedure:
                    continue
                patient = ldb.get(core.Patient, int(visit.patient_id))
                if not patient:
                    continue
                work.append({
                    'visit_id': int(visit.id),
                    'patient_id': int(patient.id),
                    'display_name': str(getattr(patient, 'nombre', '') or 'Paciente'),
                    'identification': str(getattr(patient, 'cedula', '') or ''),
                    'attention_type': _procedure_attention_type(procedure),
                    'patient_status': _patient_status(getattr(visit, 'tipo', '')),
                    'birth_date': str(getattr(patient, 'fecha_nacimiento', '') or ''),
                    'phone': str(getattr(patient, 'celular', '') or ''),
                    'email': str(getattr(patient, 'correo', '') or ''),
                    'address': str(getattr(patient, 'lugar', '') or ''),
                })
        for item in work:
            try:
                if historia_lan_transport._lan_event_targets(
                    visit_id=item['visit_id'],
                    reception_patient_id=item['patient_id'],
                ):
                    continue
                historia_bridge.queue_attention(
                    reception_patient_id=item['patient_id'],
                    display_name=item['display_name'],
                    identification=item['identification'],
                    attention_type=item['attention_type'],
                    patient_status=item['patient_status'],
                    reception_turn=None,
                    visit_ids=[item['visit_id']],
                    birth_date=item['birth_date'],
                    phone=item['phone'],
                    email=item['email'],
                    address=item['address'],
                )
            except Exception:
                pass
    except Exception:
        pass


threading.Thread(target=_recover_recent_procedures, daemon=True, name='historia-procedure-recover-4623').start()


@app.get('/api/v4521/health')
def v4521_health(user=core.Depends(core.current_user)):
    return {
        'ok': True,
        'version': APP_VERSION,
        'historia_attention_type_from_visit': True,
        'attention_type_map': {'N': 'Nuevo', 'S': 'Subsecuente', 'P': 'Procedimiento'},
        'hybrid_historia': True,
        'procedure_historia_handoff': True,
        'procedure_turn_consumption': False,
        'recent_procedure_recovery_hours': 3,
        'database_schema_changes': False,
    }
PATCH_BOOT_OK = True
