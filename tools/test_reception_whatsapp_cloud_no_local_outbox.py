"""Regression: en WhatsApp Cloud no crear una segunda cola de envios SQLite.
Prueba aislada; no conecta con Neon, Cloudflare ni Meta ni crea pacientes.
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
tree = ast.parse(source)
functions = [
    node for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "schedule_whatsapp_for_contact"
]
assert len(functions) == 1
function = functions[0]
assert isinstance(function.body[1], ast.If)
assert ast.unparse(function.body[1].test) == "WHATSAPP_CLOUD_MODE"
assert "return {'queued': 0, 'cloud_mode': True, 'local_outbox_created': False}" in ast.unparse(function.body[1])

# La funcion queda aislada sin LocalSessionLocal, sin llamadas a Meta,
# sin scheduler local ni envio de mensajes de prueba.
alarms = []
def alarm(**kwargs):
    alarms.append(kwargs)

scope = {
    "WHATSAPP_CLOUD_MODE": True,
    "_whatsapp_alarm_notify_async": alarm,
    "date": date,
}
exec(compile(ast.Module(body=[function], type_ignores=[]), "<isolated booking>", "exec"), scope)
res = scope["schedule_whatsapp_for_contact"](
    source_type="appointment", source_id=123, name="PACIENTE DE PRUEBA",
    phone="0999999999", fecha=date(2026, 10, 29), hora="10:20"
)
assert res == {"queued": 0, "cloud_mode": True, "local_outbox_created": False}
assert alarms == [{"source_type": "appointment", "source_id": 123}]
alarms.clear()

# La autoagenda puede pasar por 'staged' y sigue usando la misma alarma.
res = scope["schedule_whatsapp_for_contact"](
    source_type="staged", source_id=456, name="PRUEBA",
    phone="0999999999", fecha=date(2026, 10, 29), hora="11:00"
)
assert res["local_outbox_created"] is False
assert alarms == [{"source_type": "staged", "source_id": 456}]

# La sincronizacion offline, su reintento y las rutas del historial no se quitan.
assert "def process_offline_queue(" in source
assert "if alarm_relevant_change:" in source
assert "if pending is not None: return" in source
assert "def _whatsapp_cancel_pending(" in source
assert "def _local_outbox_history(" in (ROOT / "recepcion/app/reception_messaging_runtime.py").read_text(encoding="utf-8")
print("RECEPTION_WA_CLOUD_ONLY_NO_LOCAL_OUTBOX_OFFLINE_PRESERVED_OK")
