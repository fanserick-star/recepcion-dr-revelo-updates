"""Offline regression checks for bandwidth-safe 1.4.88 sync.

No Neon credentials or production clinical records.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from cloud_sync import (
    _make_remote_equal_probe, _batch_immutable_insert,
    _revision_insert_statement, HISTORIA_NEON_EMERGENCY_ENDPOINT_ID
)

def test_compare():
    row={"id":"case-a","patient_id":"p-1","clinical_note":"private note",
         "deleted_at":None,"revision_no":3,"cloud_updated_at":"ignored"}
    cols=set(row)
    result=_make_remote_equal_probe("encounters","id",row,cols)
    assert result is not None
    sql,values=result
    assert sql.startswith("SELECT 1 FROM encounters t WHERE CAST(t.id AS TEXT)=%s ")
    assert "SELECT *" not in sql
    assert "cloud_updated_at" not in sql
    assert "IS NOT DISTINCT FROM" in sql
    assert "NULLIF(t.deleted_at::text, '')" in sql
    assert "LIMIT 1" in sql
    assert values[0]=="case-a"
    # Check actual null-safe equality with a SQLite stand-in.
    conn=sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE encounters(id TEXT PRIMARY KEY, patient_id TEXT, clinical_note TEXT,deleted_at TEXT,revision_no INTEGER)")
    conn.execute("INSERT INTO encounters VALUES(?,?,?,?,?)",("case-a","p-1","private note",None,3))
    test_sql=sql.replace("::text","").replace("%s","?")
    assert conn.execute(test_sql,values).fetchone()==(1,)
    conn.execute("UPDATE encounters SET clinical_note='different' WHERE id='case-a'")
    assert conn.execute(test_sql,values).fetchone() is None
    conn.execute("UPDATE encounters SET clinical_note='private note',deleted_at='2026-11-10T08:00:00' WHERE id='case-a'")
    assert conn.execute(test_sql,values).fetchone() is None
    assert _make_remote_equal_probe("encounters","id",row,{"id"}) is None

def test_bulk_immutable():
    sql="INSERT INTO audit_log(id,actor,action) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING"
    out,params=_batch_immutable_insert(sql,[["1","a","create"],["2","a","edit"]])
    assert out.count("(%s,%s,%s)")==2
    assert len(params)==6
    con=sqlite3.connect(":memory:")
    con.execute("CREATE TABLE audit_log(id TEXT PRIMARY KEY,actor TEXT,action TEXT)")
    con.execute(out.replace("%s","?"),params)
    con.execute(out.replace("%s","?"),params) # Retry is idempotent.
    assert con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]==2
    one,vals=_batch_immutable_insert(sql,[["3","b","create"]])
    assert one==sql and len(vals)==3
    for malformed in [[],[["1","a"]],[["1","a","x"]]*26]:
        try:
            _batch_immutable_insert(sql,malformed)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed immutable batch was accepted")

def test_revision_bulk():
    item={"id":733,"encounter_id":"enc1","revision_no":1,"saved_at":"2026-11-12",
          "actor":"test","clinical_note":"test-only","diagnosis":"test",
          "treatment":"", "reason":"test"}
    sql,values=_revision_insert_statement(
        item,"test-device",HISTORIA_NEON_EMERGENCY_ENDPOINT_ID)
    out,flattened=_batch_immutable_insert(sql,[values,values])
    assert out.count("%s")==len(values)*2
    assert out.count("ON CONFLICT DO NOTHING")==1
    assert flattened.count("733")==2

def test_preserves_safety():
    source=(Path(__file__).resolve().parents[1]/"historia-clinica"/"app"/"cloud_sync.py").read_text(encoding="utf8")
    assert "DELETE FROM sync_dirty WHERE table_name=? AND row_key=? AND changed_at=?" in source
    assert "remote_changed_before_local_push" in source
    assert "remote_tombstone_preserved" in source
    assert "pg.commit()" in source
    assert "pending_backlog" in source

if __name__=="__main__":
    test_compare()
    test_bulk_immutable()
    test_revision_bulk()
    test_preserves_safety()
    print("NEON_BANDWIDTH_1488_REGRESSION_OK")
