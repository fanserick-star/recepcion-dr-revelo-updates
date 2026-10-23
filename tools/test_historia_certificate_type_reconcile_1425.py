"""Regression: only pre-existing document TYPE metadata can be reconciled.

Synthetic SQLite and synthetic PostgreSQL cursor. Never connects to a real
patient database, Neon, LAN, WhatsApp, signing key, or R2.
"""
from __future__ import annotations

import ast
import sqlite3
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"historia-clinica/app/cloud_sync.py").read_text(encoding="utf-8")
tree=ast.parse(source)
service=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=="CloudSyncService")
method=next(x for x in service.body if isinstance(x,ast.FunctionDef)
            and x.name=="_restore_document_types_from_local_once")
single=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
context={"sqlite3":sqlite3,"CLOUD_SCHEMA":"public"}
exec(compile(single,"clinical_type_reconcile_offline","exec"),context)
backfill=context["_restore_document_types_from_local_once"]

class FakeNeon:
    def __init__(self):
        self.rows={
            ("report-1","clinical-1"):"medical",
            ("report-2","clinical-1"):"report_ultrasound",
            ("rest-1","clinical-2"):"medical",
            ("report-3","other-patient"):"medical",
        }
        self.changes=[]
        self.commits=0
    def cursor(self):
        return self
    def execute(self,sql,parameters):
        assert "UPDATE public.certificates" in sql
        assert "SET certificate_type=%s,cloud_updated_at=now()" in sql
        assert "WHERE id=%s AND patient_id=%s" in sql
        assert "certificate_type='medical'" in sql
        assert "deleted_at IS NULL" in sql
        assert not any(word in sql.lower() for word in (
            "delete from","update public.patients","patient_links",
            "body_text","pdf_sha256","electronic_signatures"))
        typ,doc_id,patient_id=parameters
        assert typ in ("rest_isolation","report_cystoscopy","report_ultrasound")
        key=(doc_id,patient_id)
        self.rowcount=int(self.rows.get(key)=="medical")
        if self.rowcount:
            self.rows[key]=typ
            self.changes.append(key)
    def commit(self):
        self.commits+=1

class FakeService:
    def __init__(self,db):
        self.db_path=db
    def _remote_columns(self,pg,schema,table):
        assert schema=="public" and table=="certificates"
        return {"id","patient_id","certificate_type","deleted_at","cloud_updated_at"}
    def _get_state(self,db,name,default):
        row=db.execute("SELECT value FROM sync_state WHERE key=?",(name,)).fetchone()
        return row[0] if row else default
    def _set_state(self,db,name,value):
        db.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)",(name,value))

with tempfile.TemporaryDirectory(prefix="clinical_reconcile_safe_") as directory:
    database=Path(directory)/"clinic.sqlite"
    with sqlite3.connect(database) as con:
        con.executescript("""
        CREATE TABLE sync_state(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE certificates(id TEXT,patient_id TEXT,certificate_type TEXT,deleted_at TEXT);
        """)
        con.executemany("INSERT INTO certificates VALUES (?,?,?,?)",[
            ("report-1","clinical-1","report_cystoscopy",None),
            ("report-2","clinical-1","report_ultrasound",None),
            ("rest-1","clinical-2","rest_isolation",None),
            ("report-3","clinical-3","report_ultrasound",None),
            ("deleted-1","clinical-1","report_cystoscopy","2026-10-20"),
            ("ordinary-1","clinical-1","medical",None),
        ])
    neon=FakeNeon()
    subject=FakeService(database)
    assert backfill(subject,neon)==2
    assert neon.rows[("report-1","clinical-1")]=="report_cystoscopy"
    assert neon.rows[("rest-1","clinical-2")]=="rest_isolation"
    assert neon.rows[("report-2","clinical-1")]=="report_ultrasound"
    assert neon.rows[("report-3","other-patient")]=="medical"
    assert len(neon.changes)==2
    assert neon.commits==1
    assert backfill(subject,neon)==0
    assert len(neon.changes)==2
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]==6
        assert con.execute("SELECT value FROM sync_state WHERE key='document_types_restored_neon_1425'").fetchone()[0]=="1"
        assert con.execute("SELECT certificate_type FROM certificates WHERE id='report-1'").fetchone()[0]=="report_cystoscopy"

    # If local records are empty on a newly installed PC, do NOT mark repaired.
    empty=Path(directory)/"empty.sqlite"
    with sqlite3.connect(empty) as con:
        con.executescript("""
        CREATE TABLE sync_state(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE certificates(id TEXT,patient_id TEXT,certificate_type TEXT,deleted_at TEXT);
        """)
    assert backfill(FakeService(empty),neon)==0
    with sqlite3.connect(empty) as con:
        assert con.execute("SELECT COUNT(*) FROM sync_state").fetchone()[0]==0

assert "type_recovery_due = not type_recovery_done and now_mono - last_try >= 1800" in source
assert "restored_types = self._restore_document_types_from_local_once(pg)" in source
assert "or restored_types > 0" in source
assert "BIDIRECTIONAL_TABLES" in source
print("HISTORIA_DOCUMENT_TYPE_1425_SAFE_RECONCILIATION_OK")
