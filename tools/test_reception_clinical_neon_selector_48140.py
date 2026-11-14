"""Offline regression for the Reception clinical Neon selector.

No Neon calls, no real credentials, no real patients, no Windows environment.
"""
from __future__ import annotations
import ast
import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/reception_history_neon_selector.py").read_text(encoding="utf-8")
bridge_source=(root/"recepcion/app/historia_bridge.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/index.html").read_text(encoding="utf-8")
js=(root/"recepcion/app/static/configuration.js").read_text(encoding="utf-8")
application=(root/"recepcion/app/app.py").read_text(encoding="utf-8")
ast.parse(source)
ast.parse(bridge_source)
assert "historiaNeonTarget" in ui
assert "window.checkHistoriaNeonSelector" in js
assert "window.applyHistoriaNeonSelector" in js
assert '"/api/config/historia-neon/select"' in source
assert '_history_neon_selector.apply_pending_at_startup()' in application
assert "import reception_history_neon_selector" in application
assert "HISTORIA_EMERGENCY_DATABASE_URL" in bridge_source
assert "_PROCESS_HISTORY_TARGET" in bridge_source
assert "identity._connect_public()" in (root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
assert "identity._connect_public()" in (root/"recepcion/app/historia_lan_transport.py").read_text(encoding="utf-8")

tree=ast.parse(source)
names={"_preflight","_json_read","_write_pending","apply_pending_at_startup","_status","_record_startup"}
isolated=ast.fix_missing_locations(ast.Module(body=[
    node for node in tree.body
    if isinstance(node,ast.FunctionDef) and node.name in names
],type_ignores=[]))
class TestBridge:
    def __init__(self, root):
        self.ROOT=root
        self.ACTIVE_NEON_SELECTION=root/"data"/"historia_neon_selection.json"
        self._PROCESS_HISTORY_TARGET="official"
    def _history_target(self):
        return self._PROCESS_HISTORY_TARGET
    def _validated_target(self,t):
        if t not in ("official","emergency"):raise RuntimeError("invalid target")
        return t
    def _database_url_for_target(self,t):
        return "synthetic-private-credential-"+t

class FakeConn:
    def __init__(self,n):self.n=n
    def rollback(self):pass
    def close(self):pass

with tempfile.TemporaryDirectory() as td:
    loc=Path(td)
    bridge=TestBridge(loc)
    ns={"bridge":bridge, "os":os, "json":json, "time":time,
        "tempfile":tempfile, "PENDING_PATH":loc/"data"/"historia_neon_pending.json",
        "_VALID_FOR_SECONDS":180, "_STARTUP_RESULT":{"state":"not_scheduled"}}
    exec(compile(isolated,"test_selector_isolated","exec"),ns)
    pairs=[("r1","c1",True),("r2","c2",True)]
    remote={"official":dict((r,(c,v)) for r,c,v in pairs),
            "emergency":{"r1":("c1",True)}}
    ns["_connected"]=lambda t:FakeConn(t)
    ns["_link_snapshot"]=lambda conn:remote[conn.n]
    ns["_pending_work"]=lambda:(0,0)
    report=ns["_preflight"]("emergency")
    assert report["ok"] is False and report["missing"]==1
    # Never auto-merge an unverified or mismatched ID.
    remote["emergency"]["r2"]=("c3",True)
    report=ns["_preflight"]("emergency")
    assert report["ok"] is False and report["different"]==1
    remote["emergency"]["r2"]=("c2",True)
    report=ns["_preflight"]("emergency")
    assert report["ok"] is True and report["missing"]==0
    ns["_pending_work"]=lambda:(1,0)
    assert ns["_preflight"]("emergency")["ok"] is False
    ns["_pending_work"]=lambda:(0,0)
    ns["_write_pending"]("emergency")
    # Current process remains on Original until app import / restart.
    assert bridge._history_target()=="official"
    assert ns["_status"]()["pending_restart"]=="emergency"
    assert ns["_status"]()["startup_diagnostic"]["state"]=="server_still_running"
    activated=ns["apply_pending_at_startup"]()
    assert activated["state"]=="activated"
    assert bridge._history_target()=="emergency"
    assert bridge.ACTIVE_NEON_SELECTION.exists()
    assert not ns["PENDING_PATH"].exists()
    assert json.loads(bridge.ACTIVE_NEON_SELECTION.read_text())["target"]=="emergency"
    # Scheduled return to Original must protect the exclusive Emergency row.
    remote["emergency"]["r3"]=("c3",True)
    report=ns["_preflight"]("official")
    assert report["ok"] is False and report["missing"]==1
    ns["_write_pending"]("official")
    blocked=ns["apply_pending_at_startup"]()
    assert blocked["state"]=="blocked"
    assert blocked["reason"]=="parity_or_pending"
    assert ns["_status"]()["startup_diagnostic"]["missing"]==1
    assert bridge._history_target()=="emergency"
    assert ns["PENDING_PATH"].exists()
    # Production process never obtains password or patient ID via the HTML.
    assert "postgresql://" not in js and "ep-sweet-mud-" not in ui
    assert "postgresql://" not in ui
print("RECEPTION_CLINICAL_NEON_SELECTOR_48140_RESTART_PARITY_FAIL_CLOSED_OK")
