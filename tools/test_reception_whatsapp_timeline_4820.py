"""Recepción 4.8.20: comprobación de horas y estados de WhatsApp sin envíos reales."""
from __future__ import annotations

import ast
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
tree = ast.parse(source)


def function(name: str):
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(functions) == 1, name
    return functions[0]


def test_timestamp_utc_to_ecuador():
    node = function("_wa_created_at_ec")
    scope = {"datetime": datetime, "Optional": Optional}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<test time>", "exec"), scope)
    to_ec = scope["_wa_created_at_ec"]
    assert to_ec(datetime(2026, 10, 9, 18, 5, 51)) == datetime(2026, 10, 9, 13, 5, 51)
    # The database stores naive UTC. The visible scheduled time is 13:05, not 18:05.
    assert to_ec(datetime(2026, 10, 15, 13, 0, 0)) == datetime(2026, 10, 15, 8, 0, 0)


def test_true_booking_policy_and_no_fake_delivery():
    helpers = ast.get_source_segment(source, function("_wa_cita_agendada_allowed"))
    definitions = ast.get_source_segment(source, function("_wa_timeline_defs"))
    timeline = ast.get_source_segment(source, function("_wa_timeline_for_source"))
    assert "created = _wa_created_at_ec(created_at)" in helpers
    assert '"due_at": _wa_created_at_ec(created_at).isoformat()' in definitions
    assert '"status": "NO_CLOUD_EVENT"' in timeline
    assert '"status_label": "Sin constancia de envío"' in timeline
    assert '"status": "UNAVAILABLE"' in timeline
    assert '"status": "SCHEDULED"' in timeline
    assert "if due > now:" in timeline
    # Status requests must never cause a patient message or an alarm execution.
    assert "_whatsapp_alarm_notify_async" not in timeline
    assert "sendMeta(" not in timeline
    assert "schedule_whatsapp_for_contact" not in timeline


if __name__ == "__main__":
    test_timestamp_utc_to_ecuador()
    test_true_booking_policy_and_no_fake_delivery()
    print("RECEPTION_WA_TIMELINE_UTC_ECUADOR_NO_PHANTOM_SEND_OK")
