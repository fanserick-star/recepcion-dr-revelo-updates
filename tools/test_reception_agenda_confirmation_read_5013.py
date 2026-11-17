"""Agenda confirmation HTTP 500 fail-closed regression, synthetic only.

The WhatsApp history is optional on the appointment detail view.
No live patients, Neon requests, SRI writes, WhatsApp sends or DB mutations.
"""
from __future__ import annotations

import ast
import copy
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/reception_messaging_runtime_guard.py").read_text(encoding="utf-8")
tree = ast.parse(source)
install = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "install_guard")
handler = next(n for n in ast.walk(install) if isinstance(n, ast.FunctionDef) and n.name == "appointment_message_history")
route = copy.deepcopy(handler)
route.decorator_list = []
route.args.defaults = [ast.Constant(value=None), ast.Constant(value=None)]
ast.fix_missing_locations(route)

class FakeSelect:
    def join(self, *_):
        return self
    def where(self, *_):
        return self

class FakeDB:
    def __init__(self, appointment, patient):
        self.appointment = appointment
        self.patient = patient
        self.executions = 0
    def execute(self, *_):
        self.executions += 1
        return SimpleNamespace(first=lambda: (self.appointment, self.patient))

appointment = SimpleNamespace(
    id=55, fecha=date(2026, 11, 18), hora="17:00",
    created_at=datetime.utcnow()-timedelta(minutes=8), estado="PENDIENTE",
)
patient = SimpleNamespace(nombre="PACIENTE SINTETICO")
state = {}
core = SimpleNamespace(
    select=lambda *_: FakeSelect(),
    Appointment=SimpleNamespace(id=55),
    Patient=object(),
    HTTPException=ValueError,
    WHATSAPP_TEMPLATE_CITA_AGENDADA="cita_agendada",
    WHATSAPP_CLOUD_MODE=True,
    FORCE_OFFLINE=False,
    is_offline_db=lambda db: False,
    _state=state,
)
ns = {"core": core, "datetime": datetime, "date": date}
exec(compile(ast.Module(body=[route],type_ignores=[]), "<synthetic route>", "exec"), ns)
view = ns["appointment_message_history"]

# A failed optional confirmation must not change the appointment, claim
# confirmation, enable resends or return HTTP 500.
original = vars(appointment).copy()
ns["_history_payload"] = lambda **_: (_ for _ in ()).throw(ValueError("synthetic history read"))
db = FakeDB(appointment, patient)
result = view(55, db=db, user=object())
assert result["confirmation_unverified"] is True, result
assert result["can_manual_resend"] is False
assert result["cloud_available"] is False and result["events"] == []
assert result["patient_name"] == ""
assert result["cloud_error"] and "confirmación" in result["cloud_error"]
assert state["last_agenda_confirmation_read_error"] == "ValueError"
assert vars(appointment) == original
assert db.executions == 1

# A successful Cloud status should be represented unchanged; a scheduled
# local message must never be mistaken for an approved Meta send.
ns["_history_payload"] = lambda **_: {"events":[], "cloud_error": "", "available":True}
legacy = SimpleNamespace(**(original | {"created_at": "malformed-stamp"}))
result2 = view(55, db=FakeDB(legacy, patient), user=object())
assert result2["can_manual_resend"] is False, result2

# A live Cloud event is an actual record, not a local draft.
ns["_history_payload"] = lambda **_: {
    "events": [{"direction":"outbound","template":"cita_agendada","source":"cloud"}],
    "cloud_error": "", "cloud_available": True
}
result3 = view(55, db=FakeDB(appointment, patient), user=object())
assert result3["can_manual_resend"] is False
assert len(result3["events"]) == 1

text = ast.get_source_segment(source,handler)
for forbidden in ("db.commit(", "method='POST'", "send_whatsapp(", "_wa_gateway_request("):
    assert forbidden not in text, forbidden
print("RECEPTION_AGENDA_CONFIRMATION_HTTP500_FAIL_CLOSED_5013_OK")
