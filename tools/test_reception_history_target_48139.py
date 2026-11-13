"""Offline regression for explicit emergency Historia routing on Reception.

No real connection strings, Neon calls, patient data or database writes.
"""
from __future__ import annotations
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import urllib.parse

root=Path(__file__).resolve().parents[1]
bridge=(root/"recepcion/app/historia_bridge.py").read_text(encoding="utf-8")
identity=(root/"recepcion/app/reception_history_identity_consolidated.py").read_text(encoding="utf-8")
tree=ast.parse(bridge)
named={"_clean","_connection_identity","_parse_pg_url","_history_target","_database_url"}
selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in named]
constants=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {"ENV_KEY","HISTORIA_OFFICIAL_ENDPOINT_ID","HISTORIA_EMERGENCY_ENDPOINT_ID"} for t in n.targets)]
ns={"os":os,"urllib":urllib,"ROOT":root,"_read_env_file":lambda:{}}
exec(compile(ast.fix_missing_locations(ast.Module(body=constants+selected,type_ignores=[])),"bridge_offline","exec"),ns)

def url(endpoint):
    return "postgresql://synthetic:synthetic@"+endpoint+".c-4.us-west-2.aws.neon.tech/neondb"
official=url(ns["HISTORIA_OFFICIAL_ENDPOINT_ID"])
emergency=url(ns["HISTORIA_EMERGENCY_ENDPOINT_ID"])
reception="postgresql://synthetic:synthetic@ep-reception.c-4.us-west-2.aws.neon.tech/neondb"
env={"DATABASE_URL":reception,"HISTORIA_DATABASE_URL":official,"HISTORIA_EMERGENCY_DATABASE_URL":emergency}
ns["_read_env_file"]=lambda:dict(env)
with patch.dict(os.environ,{},clear=True):
    assert ns["_history_target"]()=="official"
    assert ns["_database_url"]()==official
    env["HISTORIA_NEON_TARGET"]="emergency"
    assert ns["_history_target"]()=="emergency"
    assert ns["_database_url"]()==emergency
    # If emergency access fails, NEVER silently query Original.
    env.pop("HISTORIA_EMERGENCY_DATABASE_URL")
    try:
        ns["_database_url"]()
    except RuntimeError as exc:
        assert "No se usará el Neon Original" in str(exc)
    else: raise AssertionError("Silent fallback would leak old clinical data")
    env["HISTORIA_EMERGENCY_DATABASE_URL"]=official
    try:
        ns["_database_url"]()
    except RuntimeError as exc:
        assert "proyecto distinto" in str(exc)
    else: raise AssertionError("Original URI must be rejected under emergency target")
    env["HISTORIA_EMERGENCY_DATABASE_URL"]=reception
    try: ns["_database_url"]()
    except RuntimeError: pass
    else: raise AssertionError("Reception project must never pass as Historia")
    env["HISTORIA_EMERGENCY_DATABASE_URL"]=emergency
    env["HISTORIA_NEON_TARGET"]="unknown"
    try: ns["_database_url"]()
    except RuntimeError:pass
    else:raise AssertionError("Invalid target must block")

assert 'historia_bridge._history_target()' in identity
assert 'historia_bridge.HISTORIA_EMERGENCY_ENDPOINT_ID' in identity
assert 'identity._connect_public()' in (root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
assert 'identity._connect_public()' in (root/"recepcion/app/historia_lan_transport.py").read_text(encoding="utf-8")
assert '_connect_public()' in (root/"recepcion/app/reception_system_status.py").read_text(encoding="utf-8")
print("RECEPTION_HISTORIA_ACTIVE_TARGET_48139_FAIL_CLOSED_OK")
