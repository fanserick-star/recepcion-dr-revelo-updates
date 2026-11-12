"""Regression checks for 1.4.86 emergency bandwidth and queue protections."""
from pathlib import Path
import sys,sqlite3,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"historia-clinica"/"app"))
from cloud_sync import _make_sync_upsert_sql
source=(Path(__file__).resolve().parents[1]/"historia-clinica"/"app"/"cloud_sync.py").read_text(encoding="utf8")
for required in [
    "effective_pull_due = pull_due or restored_types > 0",
    "self._remote_columns_cache",
    "remote_profile_checked",
    "ORDER BY CASE WHEN ?=1 THEN changed_at END DESC",
    "DELETE FROM sync_dirty WHERE table_name=? AND row_key=? AND changed_at=?",
    "strftime('%Y-%m-%dT%H:%M:%fZ','now')",
]:
    assert required in source,required
assert "pull_due or pushed > 0" not in source
assert "_queue_missing_local_rows(pg)" in source
for table,pk,columns in [
    ("encounters","id",["id","patient_id","clinical_note","deleted_at"]),
    ("patients","id",["id","name","deleted_at"]),
    ("prescriptions","id",["id","items_json","deleted_at"]),
    ("certificates","id",["id","body_text","deleted_at"]),
]:
    sql=_make_sync_upsert_sql(table,pk,columns,set(columns)|{"cloud_updated_at"})
    assert "IS DISTINCT FROM" in sql
    assert ("WHERE (NULLIF("+table+".deleted_at::text, '') IS NULL") in sql
    assert "AND (" in sql
    insert_head=sql.split("VALUES(",1)[0]
    assert insert_head.count("deleted_at")==1,insert_head
    assert "deleted_at=NULL" not in sql
with tempfile.TemporaryDirectory() as d:
    db=sqlite3.connect(str(Path(d)/"test.sqlite"))
    db.execute("CREATE TABLE sync_dirty(table_name TEXT,row_key TEXT,changed_at TEXT,PRIMARY KEY(table_name,row_key))")
    db.execute("INSERT INTO sync_dirty VALUES('encounters','one','2026-11-12T13:40:01.100Z')")
    items=db.execute("SELECT table_name,row_key,changed_at FROM sync_dirty").fetchall()
    db.execute("UPDATE sync_dirty SET changed_at='2026-11-12T13:40:01.600Z'")
    db.executemany("DELETE FROM sync_dirty WHERE table_name=? AND row_key=? AND changed_at=?",items)
    assert db.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0]==1, "new edit cannot be lost after remote commit"
    db.executemany("DELETE FROM sync_dirty WHERE table_name=? AND row_key=? AND changed_at=?",
                   db.execute("SELECT table_name,row_key,changed_at FROM sync_dirty").fetchall())
    assert db.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0]==0
print("SMART_NEON_SYNC_1486_OK")
