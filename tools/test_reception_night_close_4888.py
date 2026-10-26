"""Regresiones sintéticas 4.8.88: NO envía facturas ni toca Neon."""
from __future__ import annotations

import ast
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
new = (ROOT / "recepcion/app/reception_night_close.py").read_text(encoding="utf-8")
core = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
app = (ROOT / "recepcion/app/app.py").read_text(encoding="utf-8")
discard = (ROOT / "recepcion/app/reception_billing_discard.py").read_text(encoding="utf-8")
frontend = (ROOT / "recepcion/app/static/night_closing_4888.js").read_text(encoding="utf-8")
html = (ROOT / "recepcion/app/static/index.html").read_text(encoding="utf-8")
manifest = json.loads((ROOT / "recepcion/app/update_manifest.json").read_text(encoding="utf-8"))
version = json.loads((ROOT / "recepcion/app/recepcion-version.json").read_text(encoding="utf-8"))

ast.parse(new)
ast.parse(core)
ast.parse(app)
assert tuple(map(int,version["version"].split("."))) >= (4,8,88)
assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == version["version"]
assert "reception_night_close.py" in manifest["copy"]
assert "reception_night_close.py" in manifest["required_dependencies"]
assert "static/night_closing_4888.js" in manifest["copy"]
assert "static/night_closing_4888.js" in manifest["required_dependencies"]
assert 'import reception_night_close as _night_close' in app
assert '_night_close.install()' in app
assert 'night_closing_4888.js?v=4.8.95' in html
assert 'app.js?v=4.8.88' in html

# 4.8.89: ninguna ruta nocturna puede cerrar Recepción ni Historia.
assert 'NIGHT_REST_AUTO_CLOSE_PROGRAMS = False' in new
assert '"auto_close_programs": NIGHT_REST_AUTO_CLOSE_PROGRAMS' in new
assert '"programs_remain_open": True' in new
assert 'd.programs_remain_open===true && d.auto_close_programs===false' in frontend
assert 'Recepción e Historia Clínica permanecen abiertas' in frontend
assert manifest['notes']['night_rest_auto_close_reception'] is False
assert manifest['notes']['night_rest_auto_close_historia'] is False
assert manifest['notes']['night_rest_auto_shutdown_windows'] is False
assert manifest['notes']['night_rest_programs_remain_open'] is True
assert manifest['notes']['night_rest_preserve_lan'] is True
assert 'const IDLE_AFTER_MS=5*60*1000;' in (ROOT / 'recepcion/app/static/app.js').read_text(encoding='utf-8')
# Inspecciona solo las funciones del trabajador nocturno; otras funciones
# del launcher pueden cerrar normalmente cuando el usuario pulsa «Cerrar».
night_tree = ast.parse(new)
for fn_name in ('_tick', '_watch', '_execute'):
    fn = next(n for n in night_tree.body if isinstance(n,ast.FunctionDef) and n.name==fn_name)
    for n in ast.walk(fn):
        if not isinstance(n,ast.Call):
            continue
        q = ast.unparse(n.func).lower()
        assert q not in {'exit','quit','os._exit','os.kill','os.killpg','sys.exit','subprocess.run',
                         'subprocess.popen','os.system','core.shutdown','app.shutdown'}, (fn_name,q)
        assert not q.endswith(('.kill','.terminate','.shutdown','.close_programs')),(fn_name,q)

# Opt-in; solamente facturas de hoy; cuando está inactivo; nunca cron de Neon.
assert '"enabled": False' in new
assert 'core.Visit.fecha == today' in new
assert 'MAX_GROUPS = 25' in new
assert 'app_is_idle = bool(core._state.get("client_idle"))' in new
assert 'if not app_is_idle or idle_secs < 15 * 60:' in new
assert 'if core.queue_count() > 0:' in new
assert 'CONFIRMATION = "FACTURAR AUTOMATICAMENTE"' in new
assert 'str(user.role or "").lower() != "admin"' in new
assert 'time.sleep(75)' in new
assert 'CloudSessionLocal()' in new
assert 'query_comprobante' not in new
assert 'AZUR_LIVE_EMISSION' in new
assert '_azur_mass_unlocked(db)' in new
assert 'v.cancelled_at is not None' in new
assert '"AUTO_RESERVADA"' in new and '"AUTO_INCIERTA"' in new
assert 'core.mirror_azur_emission_to_local(record)' in new
assert 'core._azur_pack_response({"auto": True}, rows)' in new
assert 'status": "uncertain"' in new
assert 'core.AzurEmission.fecha == date_value' in new
assert 'or not idle_still or core.queue_count() > 0' in new

fn = new.split('def _run_one(db, pid, fecha):', 1)[1].split('\ndef _execute(today):', 1)[0]
assert fn.index('record = core.AzurEmission(') < fn.index('db.commit()') < fn.index('core.azur_emit_invoice(')
assert fn.index('db.commit()') < fn.index('core.azur_emit_invoice(')
assert 'b.estado = "EMITIDA"' not in fn
assert 'core.azur_emit_invoice(' not in new.split('def _local_summary():', 1)[1].split('def _run_one(', 1)[0]
assert 'if _azur_issuance_locked(existing):' in core
assert core.count('if _azur_issuance_locked(existing):') >= 4
assert 'if _azur_issuance_locked(reserved):' in core
assert "'AUTO_RESERVADA','AUTO_INCIERTA'" in discard
assert 'if(!window.confirm(' in frontend
assert 'FACTURAR AUTOMATICAMENTE' in frontend
assert "fetch(url" in frontend
assert 'Emitir ahora' not in frontend
assert 'setInterval(' in frontend  # lee solamente estado local

# Ejecutar _tick de forma AISLADA: el test no importa core_runtime, no abre Neon.
node = next(n for n in ast.parse(new).body if isinstance(n, ast.FunctionDef) and n.name == "_tick")
state = {"enabled": False, "hour": 19, "last_date": "", "last_result": {}}
records = []
simulated_now = datetime(2026, 10, 24, 19, 1, tzinfo=timezone(timedelta(hours=-5)))
fake_core = SimpleNamespace(
    _state_lock=threading.Lock(),
    _state={"client_idle": True, "idle_since": time.time() - 1200},
    queue_count=lambda: 0,
    cloud_engine=None,
)
def load():
    return dict(state)
def save(item):
    state.update(item)
    records.append(("saved", str(item.get("last_date") or "")))
def execute(today):
    records.append(("sent", str(today)))
    assert state.get("last_date") == today.isoformat()  # write-ahead marker
    return {"date": today.isoformat(), "status": "complete", "sent": 0}

scope = {"LOCK": threading.Lock(), "_load": load, "_save": save, "_now": lambda: simulated_now,
         "_execute": execute, "core": fake_core, "time": time}
exec(compile(ast.Module(body=[node], type_ignores=[]), "<night-test>", "exec"), scope)
tick = scope["_tick"]
tick()
assert not records, records  # disabled by default
state["enabled"] = True
fake_core._state["client_idle"] = False
tick()
assert not records, records  # active user => no emission
fake_core._state["client_idle"] = True
tick()
assert [x[0] for x in records] == ["saved", "sent", "saved"], records
tick()
assert [x[0] for x in records] == ["saved", "sent", "saved"], "No reattempt after restart/reentry"

print("RECEPTION_NIGHT_CLOSE_4888_NO_LIVE_ISSUE_OPT_IN_IDEMPOTENT_OK")
