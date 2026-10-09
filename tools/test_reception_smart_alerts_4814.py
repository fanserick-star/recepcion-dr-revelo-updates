"""Pruebas 4.8.14: alertas bajo demanda, sin enviar WhatsApp ni escribir Neon."""
from __future__ import annotations
import ast
import threading
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
runtime = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
status = (ROOT / "recepcion/app/reception_system_status.py").read_text(encoding="utf-8")
js = (ROOT / "recepcion/app/static/app.js").read_text(encoding="utf-8")
ast.parse(runtime)
ast.parse(status)
assert "@app.get('/api/ops/alerts')" in status
assert "SELECT 1 FROM whatsapp_cloud.events e" in status
assert "a.created_at AT TIME ZONE 'UTC' <= now() - interval '3 minutes'" in status
assert "a.created_at AT TIME ZONE 'UTC' >= now() - interval '12 hours'" in status
assert "AND e.appointment_date = a.fecha" in status
assert "no_message_sent': True" in status
assert "automatic_neon_polling': False" in status
assert "mountSmartAlertsShortcut();" in js
assert "btn.addEventListener('click',openSmartAlerts)" in js
assert "api('/api/ops/alerts')" in js
assert "No envía ni reenvía WhatsApp." in js
assert "setInterval(" not in js.split("async function openSmartAlerts()", 1)[1].split("function ", 1)[0]
assert "_wa_alarm_hint_diag" in runtime
assert 'status="ok", last_ok_at=' in runtime
assert '_wa_alarm_hint_diag.update(status="fallido", last_error=label)' in runtime
assert "_wa_alarm_signal_mark(generation, acknowledged=True)" in runtime

fn = next(n for n in ast.parse(status).body if isinstance(n, ast.FunctionDef)
          and n.name == "reception_4814_alerts")
fn = ast.FunctionDef(name=fn.name,args=fn.args,body=fn.body,decorator_list=[],
                     returns=fn.returns,type_comment=None)
queries = []
class FakeResult:
    def __init__(self, values): self.values = values
    def mappings(self): return self
    def all(self): return self.values
class FakeSession:
    def __enter__(self): return self
    def __exit__(self,*_): return None
    def execute(self, sql):
        queries.append(sql)
        assert sql.lstrip().upper().startswith("SELECT")
        assert all(word not in sql.upper() for word in ("INSERT INTO", "DELETE FROM", "UPDATE PUBLIC"))
        if "FROM public.appointments a" in sql:
            return FakeResult([{"id": 17, "patient_id": 21, "nombre": "PACIENTE PRUEBA",
                                "fecha": "2026-11-13", "hora": "08:00"}])
        return FakeResult([{"patient_name": "PACIENTE PRUEBA", "template_name": "recordatorio_hoy",
                            "fecha": "2026-11-13", "hora": "08:00", "status": "ERROR", "error_code": "M"}])

core = SimpleNamespace(
    Depends=lambda _:None, current_user=None,
    queue_count=lambda:2, cloud_configured=lambda:True,
    CloudSessionLocal=FakeSession, FORCE_OFFLINE=False, text=lambda x:x,
    _wa_alarm_hint_lock=threading.Lock(),
    _wa_alarm_hint_diag={"status": "fallido", "last_error": "HTTPError HTTP 403"},
)
ns = {"core": core, "_backup_status": lambda: {"ok": True}}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),
             "alert_readonly_unit", "exec"), ns)
d = ns["reception_4814_alerts"]()
assert d["ok"] and d["cloud_checked"] and d["no_message_sent"]
assert d["missing_count"] == 1 and d["delivery_error_count"] == 1
assert d["pending_sync"] == 2 and d["backup_ok"]
assert d["alarm_hint"]["status"] == "fallido"
assert len(queries) == 2

core.cloud_configured = lambda: False
queries.clear()
d = ns["reception_4814_alerts"]()
assert not d["cloud_checked"] and d["cloud_error"] and d["pending_sync"] == 2
assert not queries, "Offline alerts must not connect to Neon"
print("RECEPTION_SMART_ALERTS_4814_NO_SEND_NO_POLL_NO_WRITE_OK")
