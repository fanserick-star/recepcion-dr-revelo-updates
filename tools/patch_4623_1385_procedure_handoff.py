from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_top_function(path: str, name: str, replacement: str) -> None:
    text = read(path)
    tree = ast.parse(text)
    node = next(
        (n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name),
        None,
    )
    if node is None:
        raise AssertionError(f"{path}: function {name} not found")
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n"]
    write(path, "".join(lines))


RECEPTION_ATTENTION = '''from __future__ import annotations
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
'''

write("recepcion/app/reception_history_attention_type.py", RECEPTION_ATTENTION)

replace_top_function(
    "recepcion/app/historia_lan_transport.py",
    "hybrid_queue_attention",
    '''def hybrid_queue_attention(*, reception_patient_id: object, display_name: object,
                           identification: object = "", attention_type: object = "Consulta",
                           patient_status: object = "", reception_turn: object = None,
                           visit_ids: list[object] | None = None,
                           birth_date: object = "", phone: object = "",
                           email: object = "", address: object = "") -> str:
    label = _clean(attention_type, 180).upper()
    is_procedure = label == "PROCEDIMIENTO" or label.startswith("PROCEDIMIENTO ")
    event_id = _cloud._event_id(reception_patient_id, visit_ids)
    payload = {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "clinical_patient_id": _cloud_link_id(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "patient_status": _clean(patient_status, 40),
        "reception_turn": None if is_procedure else reception_turn,
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "birth_date": _clean(birth_date, 40),
        "phone": _clean(phone, 120),
        "email": _clean(email, 180),
        "address": _clean(address, 360),
        "queued_at": _now(),
    }
    _lan_outbox_put(payload)
    if send_lan(payload):
        _lan_outbox_mark(event_id, sent=True)
    else:
        _lan_outbox_mark(event_id, error=_snapshot().get("lan_last_error") or "Pendiente de entrega LAN")
    return event_id
''',
)

replace_top_function(
    "historia-clinica/app/app.py",
    "cleanup_active_queue_duplicates",
    '''def cleanup_active_queue_duplicates():
    """Deduplica consultas, pero permite procedimientos distintos del mismo paciente."""
    stamp = now_iso()
    removed = []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id,reception_event_id,reception_patient_id,clinical_patient_id,status,
                   attention_type,queued_at,updated_at,display_name
            FROM waiting_queue
            WHERE status IN ('waiting','in_consultation')
            ORDER BY
              CASE WHEN status='in_consultation' THEN 0 ELSE 1 END,
              COALESCE(updated_at,queued_at,'') DESC,
              COALESCE(queued_at,'') DESC
            """
        ).fetchall()
        seen_reception = set()
        seen_clinical = set()
        for row in rows:
            raw = str(row["attention_type"] or "").strip().upper()
            is_procedure = (
                raw in {"P", "X", "PROCEDIMIENTO"}
                or raw.startswith("PROCEDIMIENTO ")
                or (
                    raw
                    and raw not in {"CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}
                    and not raw.startswith("CONSULTA")
                )
            )
            if is_procedure:
                continue
            reception_id = str(row["reception_patient_id"] or "").strip()
            clinical_id = str(row["clinical_patient_id"] or "").strip()
            duplicate = (
                (reception_id and reception_id in seen_reception)
                or (clinical_id and clinical_id in seen_clinical)
            )
            if duplicate:
                conn.execute(
                    """UPDATE waiting_queue
                       SET status='cancelled',updated_at=?
                       WHERE id=? AND status IN ('waiting','in_consultation')""",
                    (stamp, row["id"]),
                )
                removed.append(str(row["id"]))
                continue
            if reception_id:
                seen_reception.add(reception_id)
            if clinical_id:
                seen_clinical.add(clinical_id)
        if removed:
            audit(
                conn,
                "cleanup",
                "waiting_queue",
                "duplicate-active-consultation",
                {"cancelled_queue_ids": removed, "count": len(removed)},
            )
            conn.commit()
    return removed
''',
)

rv = json.loads(read("recepcion/app/recepcion-version.json"))
assert rv["version"] == "4.6.22", rv
rv["version"] = "4.6.23"
write("recepcion/app/recepcion-version.json", json.dumps(rv, ensure_ascii=False, indent=2) + "\n")

rm = json.loads(read("recepcion/app/update_manifest.json"))
for key in ("version", "app_version", "runtime_version"):
    rm[key] = "4.6.23"
rn = rm.setdefault("notes", {})
rn.update({
    "purpose": "Envía procedimientos a Historia Clínica por LAN sin consumir turno y recupera procedimientos recientes que 4.6.22 omitió.",
    "previous_version": "4.6.22",
    "procedure_logic_changes": True,
    "procedure_historia_handoff": True,
    "procedure_lan_handoff": True,
    "procedure_turn_consumption": False,
    "procedure_specific_name_handoff": True,
    "recent_procedure_handoff_recovery_hours": 3,
    "waiting_queue_transport": "lan_only",
    "waiting_queue_cloud_write": False,
    "billing_logic_changes": False,
    "procedure_pricing_logic_changes": False,
    "database_schema_changes": False,
})
write("recepcion/app/update_manifest.json", json.dumps(rm, ensure_ascii=False, indent=2) + "\n")

hv = json.loads(read("historia-clinica/app/historia-version.json"))
assert hv["version"] == "1.3.84", hv
hv["version"] = "1.3.85"
write("historia-clinica/app/historia-version.json", json.dumps(hv, ensure_ascii=False, separators=(",", ":")) + "\n")

hm = json.loads(read("historia-clinica/app/update_manifest.json"))
for key in ("version", "app_version", "runtime_version"):
    hm[key] = "1.3.85"
hn = hm.setdefault("notes", {})
hn.update({
    "purpose": "Permite procedimientos en Pacientes en espera sin turno y conserva múltiples procedimientos distintos del mismo paciente.",
    "previous_version": "1.3.84",
    "functional_changes": True,
    "ui_only_release": False,
    "waiting_room_queue_logic_unchanged": False,
    "waiting_queue_unchanged": False,
    "procedure_visual_identity": True,
    "procedure_specific_name_supported": True,
    "procedure_multiple_active_same_patient": True,
    "procedure_turn_consumption": False,
    "procedure_lan_handoff": True,
    "waiting_queue_accepts_procedures": True,
    "database_schema_changes": False,
    "clinical_data_changes": False,
    "patient_data_destructive_changes": False,
})
write("historia-clinica/app/update_manifest.json", json.dumps(hm, ensure_ascii=False, indent=2) + "\n")

print("PATCH_OK Reception 4.6.23 / Historia 1.3.85")
