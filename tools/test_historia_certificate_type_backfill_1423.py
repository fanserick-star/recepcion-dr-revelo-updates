"""Offline regression: only document type metadata may be repaired in Neon."""
import ast
import sqlite3
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / "historia-clinica/app/cloud_sync.py").read_text(encoding="utf-8")
tree = ast.parse(source)
klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CloudSyncService")
fn = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == "_backfill_clinical_document_types_once")
single = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
scope = {"sqlite3": sqlite3, "CLOUD_SCHEMA": "public"}
exec(compile(single, "safe_historia_backfill", "exec"), scope)

class FakePg:
    def __init__(self):
        self.statements = []
        self.commits = 0
    def cursor(self):
        return self
    def execute(self, sql, args):
        self.statements.append((sql, args))
        assert "UPDATE public.certificates" in sql
        assert "SET certificate_type=%s, cloud_updated_at=now()" in sql
        assert "WHERE id=%s AND patient_id=%s" in sql
        assert "certificate_type='medical' AND deleted_at IS NULL" in sql
        assert "body_text" not in sql and "patient_links" not in sql
        self.rowcount = 1
    def commit(self):
        self.commits += 1

class Dummy:
    def __init__(self, db_path):
        self.db_path = db_path
    def _remote_columns(self, pg, schema, table):
        assert schema == "public" and table == "certificates"
        return {"id", "patient_id", "certificate_type", "cloud_updated_at", "deleted_at"}
    def _get_state(self, local, name, default):
        row = local.execute("SELECT value FROM sync_state WHERE key=?", (name,)).fetchone()
        return row[0] if row else default
    def _set_state(self, local, name, value):
        local.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)", (name,value))

with tempfile.TemporaryDirectory(prefix="clinical_type_safe_1423_") as folder:
    db = Path(folder) / "clinical.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sync_state(key TEXT PRIMARY KEY,value TEXT)")
        conn.execute("CREATE TABLE certificates(id TEXT,patient_id TEXT,certificate_type TEXT,deleted_at TEXT)")
        conn.executemany("INSERT INTO certificates VALUES(?,?,?,?)", [
            ("report-id", "patient-1", "report_cystoscopy", None),
            ("normal-id", "patient-1", "medical", None),
            ("deleted-id", "patient-1", "report_ultrasound", "2026-10-21"),
        ])
    pg = FakePg()
    dummy = Dummy(db)
    fn_bound = scope["_backfill_clinical_document_types_once"]
    assert fn_bound(dummy, pg) == 1
    assert len(pg.statements) == 1
    assert pg.statements[0][1] == ("report_cystoscopy", "report-id", "patient-1")
    assert pg.commits == 1
    assert fn_bound(dummy, pg) == 0, "Backfill must not poll Neon repeatedly"
    assert len(pg.statements) == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM certificates").fetchone()[0] == 3
        assert conn.execute("SELECT certificate_type FROM certificates WHERE id='report-id'").fetchone()[0] == "report_cystoscopy"
        assert conn.execute("SELECT value FROM sync_state WHERE key='certificate_type_neon_backfill_1423'").fetchone()[0] == "1"

assert "restored_document_types = self._backfill_clinical_document_types_once(pg)" in source
assert "or restored_document_types > 0" in source
print("HISTORIA_DOCUMENT_TYPE_BACKFILL_1423_SAFE_IDEMPOTENT_OK")
