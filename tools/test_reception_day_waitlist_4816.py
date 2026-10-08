"""4.8.16 — Las nuevas solicitudes no tocan citas, historias ni facturas."""
from __future__ import annotations
import ast
import sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
src = (ROOT/"recepcion/app/reception_system_status.py").read_text(encoding="utf-8")
front = (ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
parsed = ast.parse(src)
schema = next(x.value.value for x in parsed.body if isinstance(x, ast.Assign) and
              any(isinstance(t,ast.Name) and t.id=="_WAITLIST_4816_DDL" for t in x.targets))
connection = sqlite3.connect(":memory:")
connection.execute(schema)
connection.execute("INSERT INTO reception_waitlist_4816(patient_id,desired_date,desired_time,note) VALUES(?,?,?,?)",
                   (12,"2026-11-15","09:40","Prueba local"))
one = connection.execute("SELECT patient_id,desired_date,desired_time,note,status FROM reception_waitlist_4816").fetchone()
assert one == (12,"2026-11-15","09:40","Prueba local","OPEN")
connection.execute("UPDATE reception_waitlist_4816 SET status='CLOSED' WHERE id=1 AND status='OPEN'")
assert connection.execute("SELECT status FROM reception_waitlist_4816 WHERE id=1").fetchone()[0]=="CLOSED"
assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()==[("reception_waitlist_4816",)]
connection.close()
assert "@app.get('/api/ops/today')" in src
assert "@app.get('/api/ops/waitlist')" in src
assert "@app.post('/api/ops/waitlist')" in src
assert "@app.post('/api/ops/waitlist/{waitlist_id}/close')" in src
assert "'source': 'local_sqlite'" in src
assert "'no_messages_sent': True" in src
assert "in_queue is not None" in src
assert "if found is not None:" in src
assert "no_cloud_queries': True" in src
segment = src.split("def reception_4816_today(",1)[1].split("class ReceptionWaitlist4816In",1)[0]
assert "CloudSessionLocal" not in segment and "_connect_public()" not in segment
assert "core.LocalSessionLocal()" in segment
assert "core.is_exam_review_no_charge(v)" in segment
assert "def _waitlist_4816_date_time(" in src
assert "function mountAgendaWaitlistShortcut()" in front
assert "function loadHomeDaySummary(" in front
assert "async function openWaitlistBoard()" in front
assert "async function addWaitlistEntry()" in front
assert "async function markWaitlistServed(" in front
jswait=front.split("// 4.8.16: diario y lista",1)[1].split("async function goHomeToday()",1)[0]
assert "setInterval(" not in jswait and "sendWhatsapp" not in jswait
print("RECEPTION_LOCAL_DAY_WAITLIST_4816_SQLITE_ONLY_NO_WHATSAPP_OK")
