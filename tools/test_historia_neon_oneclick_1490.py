"""Clinical Neon one-action return: dry-run safety guards, no live patients or secrets."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
import neon_official_return as migration

panel = (APP / "neon_return_settings.py").read_text(encoding="utf-8")
engine = (APP / "neon_official_return.py").read_text(encoding="utf-8")
ast.parse(panel)
ast.parse(engine)
assert "Sincronizar y cambiar al Neon Oficial" in panel
assert '@app.post("/api/neon/return/prepare")' in panel
assert "neon_return_before_copy.sqlite" in panel
assert "check_automatic_return(report, private)" in panel
assert "allow_updates=True, cutover_at=cutover" in panel
assert panel.index("transferred = transfer(") < panel.index(
    "report, _ = build_plan(source, official)", panel.index("transferred = transfer(")
)
assert "source.cursor().execute(\"SET TRANSACTION READ ONLY\")" in panel
assert 'if health["pending"] != 0 or health["conflicts"] != 0:' in panel
assert "if auto_sync:" in panel
assert "No se realizo" not in panel  # The reason must be visible through a safe status.

safe = {
    "missing": [], "changed": [], "tombstone_mismatch": [],
    "resurrection_conflict": [], "destination_only": [],
}
plan = {"plan_sha256": "approved", "tables": {
    t: {"missing":0,"changed":0,"official_only":0,"source_deleted_diff":0,
        "reactivation_conflicts":0,"unshared_source_columns":[]}
    for t in migration.TABLE_KEYS
}}
private = {t: {"delta":dict(safe), "shared":{"id"}}
           for t in migration.TABLE_KEYS}
migration.check_automatic_return(plan, private)
private["patients"]["delta"]["missing"]=["new"]
private["patients"]["delta"]["changed"]=["edited"]
migration.check_automatic_return(plan, private)

def must_block(table, field, value):
    private[table]["delta"][field] = value
    try:
        migration.check_automatic_return(plan, private)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"Unsafe auto return accepted: {table}/{field}")
    finally:
        private[table]["delta"][field] = []

must_block("patient_links", "missing", ["reception_owned"])
must_block("waiting_queue", "changed", ["active_turn"])
must_block("clinic_settings", "changed", ["server_setting"])
must_block("encounters", "destination_only", ["official_only"])
must_block("patients", "tombstone_mismatch", ["deleted"])
must_block("audit_log", "changed", ["immutable"])

class Cursor:
    result = (True,)
    def execute(self, statement, args):
        assert "cloud_updated_at::timestamptz" in statement
        assert len(args) == 2
    def fetchone(self):
        return self.result

class Conn:
    def __init__(self):
        self.c = Cursor()
    def cursor(self):
        return self.c

con = Conn()
migration._official_unchanged_since_cutover(con, "patients", "id", "a", "2026-11-12T10:00:00Z")
for result in [(False,), None]:
    con.c.result = result
    try:
        migration._official_unchanged_since_cutover(con, "patients", "id", "a", "2026-11-12T10:00:00Z")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Newer Official write was not blocked")
try:
    migration._official_unchanged_since_cutover(con, "patients", "id", "a", None)
except RuntimeError:
    pass
else:
    raise AssertionError("Missing cutover checkpoint allowed")

print("HISTORIA_NEON_ONECLICK_1490_SAFE")
