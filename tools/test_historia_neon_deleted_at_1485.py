"""Regression: deleted_at included EXACTLY ONCE in Neon UPSERT (SQLSTATE 42701)."""
from __future__ import annotations
import sys
from pathlib import Path
APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0,str(APP))
from cloud_sync import _make_sync_upsert_sql

def check(sql, table, expected):
    before_values=sql.split("VALUES(",1)[0]
    columns=before_values.split("INSERT INTO "+table+"(",1)[1].split(")",1)[0].split(",")
    assert columns==expected, (columns,expected)
    assert len(columns)==len(set(columns)),columns
    assert columns.count("deleted_at")<=1,sql
    assert columns.count("cloud_updated_at")==1,sql
    values=sql.split("VALUES(",1)[1].split(")",1)[0].split(",")
    assert len(values)==len(columns),(columns,values)
    assert values.count("now()")==0 or values[-1].startswith("now("),values

for tab,pk in [("patients","id"),("encounters","id"),("prescriptions","id"),("certificates","id"),("waiting_queue","id")]:
    cols=[pk,"patient_id","deleted_at"]
    sql=_make_sync_upsert_sql(tab,pk,cols,set(cols)|{"cloud_updated_at"})
    check(sql,tab,cols+["cloud_updated_at"])
    assert "deleted_at=EXCLUDED.deleted_at" in sql
    assert "OR EXCLUDED.deleted_at IS NOT NULL" in sql
    assert "deleted_at=NULL" not in sql
    assert "NULLIF("+tab+".deleted_at::text, '') IS NULL" in sql

sql=_make_sync_upsert_sql("clinic_settings","setting_key",["setting_key","value"],{"setting_key","value","cloud_updated_at"})
check(sql,"clinic_settings",["setting_key","value","cloud_updated_at"])
assert "EXCLUDED.deleted_at" not in sql
sql=_make_sync_upsert_sql("patients","id",["id","deleted_at"],{"id","deleted_at","cloud_updated_at"})
check(sql,"patients",["id","deleted_at","cloud_updated_at"])
for bad_cols,remote in [
    (["id","deleted_at","deleted_at"],{"id","deleted_at","cloud_updated_at"}),
    (["id","cloud_updated_at"],{"id","cloud_updated_at"}),
    (["id"],{"id","deleted_at","cloud_updated_at"}),
]:
    try:
        _make_sync_upsert_sql("patients","id",bad_cols,remote)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid column list accepted: "+str(bad_cols))
print("NEON_UPSERT_DELETED_AT_42701_REGRESSION_OK")
