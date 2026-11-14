"""4.8.145 safe boot diagnostics: no Neon, private credentials or clinical data."""
import ast
import json
import os
import tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
src=(root/"recepcion/app/reception_history_neon_selector.py").read_text(encoding="utf-8")
js=(root/"recepcion/app/static/configuration.js").read_text(encoding="utf-8")
manifest=json.loads((root/"recepcion/app/update_manifest.json").read_text(encoding="utf-8"))
tree=ast.parse(src)
names={"_status","_record_startup","apply_pending_at_startup"}
body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert len(body)==3
class Bridge:
    def __init__(self,d):
        self.ACTIVE_NEON_SELECTION=d/"data"/"historia_neon_selection.json"
        self._PROCESS_HISTORY_TARGET="official"
    def _history_target(self):return self._PROCESS_HISTORY_TARGET
    def _validated_target(self,t):
        if t not in ("official","emergency"):raise ValueError("invalid")
        return t
    def _database_url_for_target(self,t):return "synthetic-private-credential"
class Blocked(Exception):pass
with tempfile.TemporaryDirectory() as tmp:
    d=Path(tmp);data=d/"data";data.mkdir()
    bridge=Bridge(d)
    pending=data/"historia_neon_pending.json"
    pending.write_text(json.dumps({"schema":1,"target":"emergency"}))
    ns={"_STARTUP_RESULT":{"state":"not_scheduled"},"PENDING_PATH":pending,"bridge":bridge,
        "_json_read":lambda path:json.loads(path.read_text()),
        "_preflight":lambda target:{"ok":False,"missing":1,"different":0,
                                   "destination_only":0,"invalid":0,"pending":0,"pending_lan":0},
        "_safe_check_error":lambda exc:{"code":"pending_queue_unavailable",
                                       "message":"No se pudo comprobar la cola LAN."},
        "os":os,"json":json}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),"selector_boot", "exec"),ns)
    status=ns["_status"]()
    assert status["active"]=="official"
    assert status["startup_diagnostic"]["state"]=="server_still_running"
    assert "launcher" in status["startup_diagnostic"]["message"]
    blocked=ns["apply_pending_at_startup"]()
    assert blocked["state"]=="blocked" and blocked["reason"]=="parity_or_pending"
    assert ns["_status"]()["startup_diagnostic"]["missing"]==1
    assert pending.exists()
    assert not bridge.ACTIVE_NEON_SELECTION.exists()
    ns["_preflight"]=lambda target:(_ for _ in ()).throw(Blocked("sensitive-uri"))
    blocked=ns["apply_pending_at_startup"]()
    assert blocked["reason"]=="pending_queue_unavailable"
    assert "sensitive-uri" not in json.dumps(ns["_status"]())
    ns["_preflight"]=lambda target:{"ok":True,"missing":0}
    assert ns["apply_pending_at_startup"]()["state"]=="activated"
    assert bridge._history_target()=="emergency"
    assert not pending.exists()
    assert bridge.ACTIVE_NEON_SELECTION.exists()
assert "startup_diagnostic" in js
assert 'DIAGNÓSTICO:' in js
assert manifest["version"]=="4.8.145"
print("RECEPTION_48145_PENDING_NEON_STARTUP_SAFE_DIAGNOSTICS_OK")
