from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent
data = ROOT / "data"
if data.exists():
    shutil.rmtree(data)

spec = importlib.util.spec_from_file_location("historia_bridge_test", ROOT / "historia_bridge.py")
bridge = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(bridge)

# Do not start a network flush during the unit smoke test.
bridge.flush_pending = lambda *args, **kwargs: None

event_id = bridge.queue_attention(
    reception_patient_id=42,
    display_name="PACIENTE PRUEBA",
    identification="",
    attention_type="Subsecuente",
    visit_ids=[777],
)
cancel_targets = bridge.cancel_attention(visit_id=777, reception_patient_id=42)
restore_targets = bridge.restore_attention(visit_id=777, reception_patient_id=42)

assert cancel_targets == [event_id], (cancel_targets, event_id)
assert restore_targets == [event_id], (restore_targets, event_id)

with sqlite3.connect(bridge.OUTBOX_DB) as conn:
    rows = conn.execute("SELECT payload_json FROM events ORDER BY created_at,event_id").fetchall()
payloads = [json.loads(r[0]) for r in rows]
assert any(p.get("action") == "cancel" and p.get("target_event_id") == event_id for p in payloads)
assert any(p.get("action") == "restore" and p.get("target_event_id") == event_id for p in payloads)

print("RECEPTION_BRIDGE_CANCEL_RESTORE_OK", event_id)
