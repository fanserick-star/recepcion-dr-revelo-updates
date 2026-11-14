"""Synthetic 4.8.147 fiscal regression. No AZUR, Neon, Windows or real patients."""
from __future__ import annotations
import ast
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
path = root / "recepcion/app/reception_night_close.py"
source = path.read_text(encoding="utf-8")
ui = (root/"recepcion/app/static/night_closing_4888.js").read_text(encoding="utf-8")
version = json.loads((root/"recepcion/app/recepcion-version.json").read_text(encoding="utf-8"))
manifest = json.loads((root/"recepcion/app/update_manifest.json").read_text(encoding="utf-8"))
assert version["version"] == manifest["version"] == "4.8.147"
tree = ast.parse(source)
names = {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
assert {"_financial_summary","_tick","_execute","night_close_financial_report"} <= set(names)
assert "WORKING_WEEKDAYS = frozenset((2, 3, 4, 5))" in source
assert "_now().date()" in source
assert "today.weekday() not in WORKING_WEEKDAYS" in source
assert "today_local.weekday() not in WORKING_WEEKDAYS" in source
assert "return {\"ok\": True, \"available\": False}" in source
assert "SET TRANSACTION READ ONLY" in source
assert "db.execute(sql_text(\"SET TRANSACTION READ ONLY\"))" in source
assert "core.azur_emit_invoice(" not in source.split('def night_close_financial_report(',1)[1].split("\ndef _tick():",1)[0]
assert "core.AzurEmission.created_at >= utc_start" in source
assert 'core.Audit.username == "robot_cierre_nocturno"' in source
assert "reportado" not in ui.lower()  # no invented state on front-end
assert "Cierre automático de las 19:00" in ui
assert "Emitidas manualmente" in ui
assert "TOTAL AUTORIZADO POR SRI:" in ui
assert "rpNightFinancialReport" in ui
assert "miércoles a sábado" in ui.lower()
assert "if(!section.classList.contains('hidden'))refreshFinancial(false);" in ui
assert "document.getElementById('facturacion')" in ui
assert "r.financial.automatic" in ui and "r.financial.manual" in ui

namespace={}
exec(compile(ast.Module(body=[names["_financial_summary"]],type_ignores=[]),"synthetic","exec"),namespace)
summarize=namespace["_financial_summary"]
R=[
  {"group_key":"1:2026-11-13:11","patient_id":1,"fecha":"2026-11-13",
   "estado":"AUTORIZADA","clave_acceso":True,"visit_ids":[11]},
  {"group_key":"2:2026-11-13:22","patient_id":2,"fecha":"2026-11-13",
   "estado":"AUTORIZADA","clave_acceso":True,"visit_ids":[22,23]},
  {"group_key":"3:2026-11-13:33","patient_id":3,"fecha":"2026-11-13",
   "estado":"EN_PROCESO","clave_acceso":True,"visit_ids":[33]},
  {"group_key":"4:2026-11-13:44","patient_id":4,"fecha":"2026-11-13",
   "estado":"AUTORIZADA","clave_acceso":True,"visit_ids":None},
]
known={11:(1,"2026-11-13","100.25"),
       22:(2,"2026-11-13","25.00"),23:(2,"2026-11-13","24.50"),
       33:(3,"2026-11-13","10.00")}
totals=summarize(R,{"2:2026-11-13:22","3:2026-11-13:33"},known)
assert totals["manual"]["count"]==2 and totals["manual"]["authorized"]==2
assert totals["manual"]["authorized_value_cents"]==10025
assert totals["manual"]["unknown_amount"]==1
assert totals["automatic"]["count"]==2 and totals["automatic"]["authorized"]==1
assert totals["automatic"]["authorized_value_cents"]==4950
assert totals["automatic"]["in_process"]==1
assert totals["automatic"]["in_process_value_cents"]==1000
assert totals["total"]["authorized_value_cents"]==14975
assert totals["total"]["authorized"]==3 and totals["total"]["unknown_amount"]==1
# Duplicates must not inflate totals, including the same visit in two invoices.
try:
    summarize(R+R[:1],set(),known)
    raise AssertionError("Duplicate invoice key accepted")
except ValueError:
    pass
conflict=[dict(R[0]),dict(R[1])]
conflict[1]["visit_ids"]=[11]
partial=summarize(conflict,set(),known)
assert partial["total"]["authorized_value_cents"]==10025
assert partial["total"]["unknown_amount"]==1
# Weekday guard must not run a job on Sun/Mon/Tue, regardless of last marker.
fake_core=SimpleNamespace(
    _state_lock=threading.Lock(),
    _state={"client_idle":True,"idle_since":time.time()-2000},
    queue_count=lambda:0,cloud_engine=None,NEON_ECO_MODE=True
)
state={"enabled":True,"hour":19,"last_date":"","last_result":{}}
saved=[]
now=[datetime(2026,11,15,19,15,tzinfo=timezone(timedelta(hours=-5)))]  # Sunday
def load(): return dict(state)
def save(obj):state.update(obj);saved.append(dict(obj))
def execute(day):raise AssertionError("Off-day must not reach fiscal execution")
scope={"WORKING_WEEKDAYS":frozenset({2,3,4,5}),"core":fake_core,
       "_now":lambda:now[0],"LOCK":threading.Lock(),
       "_load":load,"_save":save,"_execute":execute,"time":time}
exec(compile(ast.Module(body=[names["_tick"]],type_ignores=[]),"tick-test","exec"),scope)
for d in (15,16,17):   # Sun/Mon/Tue Nov 2026
    now[0]=datetime(2026,11,d,19,15,tzinfo=timezone(timedelta(hours=-5)))
    scope["_tick"]()
assert not saved and not state["last_date"]
now[0]=datetime(2026,11,18,19,15,tzinfo=timezone(timedelta(hours=-5))) # Wednesday
called=[]
scope["_execute"]=lambda d:(called.append(d),{"date":str(d),"status":"complete","sent":0})[1]
scope["_tick"]()
assert called==[date(2026,11,18)]
assert state["last_date"]=="2026-11-18"
scope["_tick"]()
assert len(called)==1
# Separate _execute guard protects off-days even if called outside scheduler.
n=names["_execute"]
env={"WORKING_WEEKDAYS":frozenset({2,3,4,5}),"core":SimpleNamespace(queue_count=lambda:0)}
exec(compile(ast.Module(body=[n],type_ignores=[]),"execute-guard","exec"),env)
out=env["_execute"](date(2026,11,16)) # Monday
assert out["status"]=="closed" and out["sent"]==0
print("RECEPTION_NIGHT_FINANCIAL_48147_WEEKDAYS_SRI_READONLY_SYNTHETIC_OK")
