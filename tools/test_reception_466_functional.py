from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "updates" / "v4_6_6_fast_attention_save"
DATA_DIR = Path(tempfile.mkdtemp(prefix="rp466-functional-"))

os.environ["RP_DATA_DIR"] = str(DATA_DIR)
os.environ["RP_FORCE_OFFLINE"] = "1"
os.environ["DATABASE_URL"] = ""
os.environ["HISTORIA_DATABASE_URL"] = ""
os.environ["REMOTE_AGENDA_AUTOSTART"] = "0"
os.environ["WHATSAPP_ENABLED"] = "0"

os.chdir(APP_DIR)
sys.path.insert(0, str(APP_DIR))
import app  # noqa: E402

assert app.APP_VERSION == "4.6.6"
app.core.Base.metadata.create_all(app.core.local_engine)


def required_patient_kwargs():
    out = {}
    for col in app.core.Patient.__table__.columns:
        if col.primary_key or col.nullable or col.default is not None or col.server_default is not None:
            continue
        name = col.name
        typename = type(col.type).__name__.lower()
        if name == "nombre":
            value = "PACIENTE PRUEBA CUATRO SEIS SEIS"
        elif "date" in typename and "time" not in typename:
            value = date(1990, 1, 1)
        elif "datetime" in typename:
            value = datetime.utcnow()
        elif "int" in typename:
            value = 0
        elif "numeric" in typename or "float" in typename:
            value = 0
        else:
            value = "TEST466"
        out[name] = value
    return out


with app.core.LocalSessionLocal() as db:
    patient = app.core.Patient(**required_patient_kwargs())
    # Keep common optional administrative fields harmless when they exist.
    if hasattr(patient, "cedula"):
        patient.cedula = "TEST466"
    db.add(patient)
    db.commit()
    db.refresh(patient)
    patient_id = int(patient.id)

User = SimpleNamespace(username="test-466")
Service = app.core.VisitBatchServiceIn
Batch = app.bridge_v4508.payment_core.V4504VisitBatchPaymentIn


def local_db():
    gen = app._v466_local_attention_db()
    db = next(gen)
    return gen, db


# 1) PROCEDURE: must save locally, create BillingRecord + offline queue, and
# print route must explicitly refuse it.
proc_payload = Batch(
    patient_id=patient_id,
    fecha=date.today(),
    tipo=None,
    services=[Service(procedimiento="INSTILACION", valor=80.0)],
    observacion="PRUEBA 4.6.6",
    payment_method="EFECTIVO",
)
gen, db = local_db()
t0 = time.perf_counter()
proc_result = app.v466_fast_local_attention_save(proc_payload, db=db, user=User)
proc_ms = (time.perf_counter() - t0) * 1000
try:
    next(gen)
except StopIteration:
    pass
assert proc_ms < 2000, proc_ms
assert proc_result.get("local_first") is True
proc_item = proc_result["items"][0]
proc_id = int(proc_item["id"])

with app.core.LocalSessionLocal() as db:
    visit = db.get(app.core.Visit, proc_id)
    assert visit is not None
    assert str(visit.procedimiento or "").strip().upper() == "INSTILACION"
    billing = db.scalar(app.core.select(app.core.BillingRecord).where(app.core.BillingRecord.visit_id == proc_id))
    assert billing is not None
    queued = db.scalar(app.core.select(app.core.OfflineQueue).where(
        app.core.OfflineQueue.operation == "visit.create",
        app.core.OfflineQueue.local_entity_id == proc_id,
    ))
    assert queued is not None

# Print protection: no spool call for procedures.
gen, db = local_db()
try:
    pr = app.v466_print_visit_local_first(
        proc_id,
        data=app._V4544PrintVisitIn(),
        db=db,
        user=User,
    )
finally:
    try:
        next(gen)
    except StopIteration:
        pass
assert pr.get("printed") is False, pr
assert pr.get("reason") == "procedure_only", pr

# 2) CONSULTATION: same fast local persistence contract; it remains eligible
# for the existing UI auto-print path after save.
consult_payload = Batch(
    patient_id=patient_id,
    fecha=date.today(),
    tipo=None,
    services=[Service(procedimiento=None, valor=40.0)],
    observacion="PRUEBA CONSULTA 4.6.6",
    payment_method="EFECTIVO",
)
gen, db = local_db()
t0 = time.perf_counter()
consult_result = app.v466_fast_local_attention_save(consult_payload, db=db, user=User)
consult_ms = (time.perf_counter() - t0) * 1000
try:
    next(gen)
except StopIteration:
    pass
assert consult_ms < 2000, consult_ms
assert consult_result.get("local_first") is True
consult_id = int(consult_result["items"][0]["id"])

with app.core.LocalSessionLocal() as db:
    visit = db.get(app.core.Visit, consult_id)
    assert visit is not None and not str(visit.procedimiento or "").strip()
    billing = db.scalar(app.core.select(app.core.BillingRecord).where(app.core.BillingRecord.visit_id == consult_id))
    assert billing is not None
    queued = db.scalar(app.core.select(app.core.OfflineQueue).where(
        app.core.OfflineQueue.operation == "visit.create",
        app.core.OfflineQueue.local_entity_id == consult_id,
    ))
    assert queued is not None

assert "consult=items.find(v=>!text(v?.procedimiento))" in app.core.V460_OVERLAY_JS
assert "Guardando atención…" in app.core.V460_OVERLAY_JS
assert app._V466_OLD_BUSY not in app.core.V460_OVERLAY_JS

print(f"FUNCTIONAL OK procedure_save_ms={proc_ms:.1f} consultation_save_ms={consult_ms:.1f}")
print("procedure print guard", pr)
print("offline queue", app.core.queue_count())
