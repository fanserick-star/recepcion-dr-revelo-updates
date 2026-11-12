"""Offline safety regression tests for future selective clinical Neon return.

No live Neon connection, no clinical data, no credentials.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
import neon_official_return as migration

c = migration.classify
assert c({"a": ("x", False)}, {})["missing"] == ["a"]
assert c({}, {"a": ("x", False)})["destination_only"] == ["a"]
assert c({"a": ("y", False)}, {"a": ("x", False)})["changed"] == ["a"]
assert c({"a": ("x", False)}, {"a": ("y", True)})["resurrection_conflict"] == ["a"]
assert c({"a": ("x", True)}, {"a": ("y", False)})["tombstone_mismatch"] == ["a"]
assert c({"a": ("x", False)}, {"a": ("x", False)}) == {
    "missing": [], "changed": [], "tombstone_mismatch": [],
    "resurrection_conflict": [], "destination_only": []
}

t = "encounters"
safe = {
    "missing": [], "changed": [], "tombstone_mismatch": [],
    "resurrection_conflict": [], "destination_only": [],
}
plan = {"plan_sha256": "confirmed", "tables": {
    k: {"missing":0,"changed":0,"source_deleted_diff":0,
        "reactivation_conflicts":0,"official_only":0,
        "unshared_source_columns":[]}
    for k in migration.TABLE_KEYS
}}
private = {
    k: {"delta":dict(safe), "shared":{"id","deleted_at"}}
    for k in migration.TABLE_KEYS
}
migration._check_plan(plan,private,"confirmed")
migration._verify_complete(plan)
try:
    migration._check_plan(plan,private,"invalid")
except RuntimeError:
    pass
else:
    raise AssertionError("Missing approval must be rejected")

private[t]["delta"]["resurrection_conflict"]=["a"]
try:
    migration._check_plan(plan,private,"confirmed")
except RuntimeError:
    pass
else:
    raise AssertionError("Tombstones must block copy")
private[t]["delta"]["resurrection_conflict"]=[]

plan["tables"][t]["official_only"]=1
try:
    migration._verify_complete(plan)
except RuntimeError:
    pass
else:
    raise AssertionError("Official-only clinical row needs review")
plan["tables"][t]["official_only"]=0

plan["tables"]["patient_links"]["missing"]=1
try:
    migration._verify_complete(plan)
except RuntimeError:
    pass
else:
    raise AssertionError("Reception-owned differences need review")
plan["tables"]["patient_links"]["missing"]=0

assert migration._row_hash({"id","name","deleted_at","cloud_updated_at"}) == (
    'md5(jsonb_build_object(\'id\',t."id",\'name\',t."name")::text)'
)
assert "IS NOT NULL" in migration._tombstone({"id","deleted_at"})
assert migration._tombstone({"id"}) == "FALSE"
for bad in ('evil";DELETE FROM patients', "id) FROM patients", "ID"):
    try:
        migration._ident(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe identifier allowed")

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    data = root / "data"
    data.mkdir()
    emergency = "postgresql://test_user:test_pass@ep-noisy-paper-arf28291.c-4.us-west-2.aws.neon.tech/neondb"
    original = "postgresql://old_user:old_pass@ep-sweet-mud-arlsk7qa.c-4.us-west-2.aws.neon.tech/neondb"
    (root / ".env").write_text(
        "HISTORIA_NEON_TARGET=emergency\n"
        + "HISTORIA_DATABASE_URL=" + emergency + "\n"
        + "HISTORIA_OFFICIAL_DATABASE_URL=" + original + "\n",
        encoding="utf8",
    )
    assert migration._load_credentials(root)[:2] == (emergency,original)
    db_path = data / "historia_clinica.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE sync_dirty(table_name TEXT,row_key TEXT)")
    con.execute("CREATE TABLE sync_conflicts(resolved_at TEXT)")
    con.execute("CREATE TABLE sync_state(key TEXT PRIMARY KEY,value TEXT)")
    con.execute("INSERT INTO sync_state VALUES('cloud_endpoint_id',?)",
                (migration.SOURCE,))
    con.commit()
    con.close()
    old = os.environ.get("HISTORIA_RETURN_MAINTENANCE_CONFIRMED")
    os.environ.pop("HISTORIA_RETURN_MAINTENANCE_CONFIRMED",None)
    try:
        migration._stop_if_unsafe(root)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Cannot proceed without offline confirmation")
    os.environ["HISTORIA_RETURN_MAINTENANCE_CONFIRMED"]="1"
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO sync_dirty VALUES ('encounters','abc')")
    try:
        migration._stop_if_unsafe(root)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Pending local rows must block maintenance")
    with sqlite3.connect(db_path) as con:
        con.execute("DELETE FROM sync_dirty")
    locked = migration._stop_if_unsafe(root)
    class FakeCursor:
        def execute(self,query,*args):
            assert query == "SELECT now()::text"
        def fetchone(self):
            return ("2026-12-01 17:30:00+00",)
    class FakePG:
        def cursor(self):
            return FakeCursor()
        def commit(self):
            pass
    result = migration.switch(root,locked,emergency,original,"proof_hash",FakePG())
    assert result["restart_required"]
    locked.close()
    content = (root/".env").read_text(encoding="utf8")
    assert "HISTORIA_NEON_TARGET=official" in content
    assert "HISTORIA_DATABASE_URL=" + original in content
    assert "HISTORIA_EMERGENCY_DATABASE_URL=" + emergency in content
    assert (data/"neon_before_return_private.env").is_file()
    with sqlite3.connect(db_path) as con:
        state=dict(con.execute("SELECT key,value FROM sync_state"))
    assert state["cloud_endpoint_id"] == migration.DESTINATION
    assert state["last_pull"] == "2026-12-01 17:30:00+00"
    assert state["official_return_verified_sha"] == "proof_hash"
    if old is None:
        os.environ.pop("HISTORIA_RETURN_MAINTENANCE_CONFIRMED",None)
    else:
        os.environ["HISTORIA_RETURN_MAINTENANCE_CONFIRMED"]=old

print("NEON_RETURN_DIFFERENTIAL_GUARDS_OK")
