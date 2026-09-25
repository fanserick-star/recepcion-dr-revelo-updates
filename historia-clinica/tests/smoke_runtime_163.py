from __future__ import annotations

import ast
import asyncio
import hashlib
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse

REPO = Path(__file__).resolve().parents[2]
PARTS = [
    REPO / "historia-clinica/updates/v1_3_63_save_autosave_repair/app.py.part01",
    REPO / "historia-clinica/updates/v1_3_56_system_tools_options/app.py.part02",
    REPO / "historia-clinica/updates/v1_3_62_reliable_print_buttons/app.py.part03",
    REPO / "historia-clinica/updates/v1_3_63_save_autosave_repair/app.py.part04",
    REPO / "historia-clinica/updates/v1_3_21_single_new_patient/app.py.part05",
    REPO / "historia-clinica/updates/v1_3_63_save_autosave_repair/app.py.part06",
]
source = "".join(p.read_text(encoding="utf-8") for p in PARTS)
compile(source, "historia_v163_app.py", "exec")

# Static regression checks.
assert 'ensure_column(conn, "waiting_queue", "started_at", "started_at TEXT")' in source
assert 'ensure_column(conn, "waiting_queue", "completed_at", "completed_at TEXT")' in source
assert "if(manual && window.showAppToast)" in source
assert "Protegido localmente · reintentando" in source

tree = ast.parse(source)
wanted = {"save_encounter", "sign_encounter"}
nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
assert {n.name for n in nodes} == wanted

root = Path(tempfile.mkdtemp(prefix="hc_v163_smoke_"))
db_path = root / "historia.db"
conn = sqlite3.connect(db_path)
conn.executescript("""
CREATE TABLE patients(
  id TEXT PRIMARY KEY, name TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE encounters(
  id TEXT PRIMARY KEY, patient_id TEXT, encounter_date TEXT, encounter_time TEXT,
  clinical_note TEXT, diagnosis TEXT, treatment TEXT, source TEXT,
  source_record_hash TEXT, is_legacy_locked INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT, deleted_at TEXT,
  note_status TEXT NOT NULL DEFAULT 'draft',
  signed_at TEXT, signed_by TEXT, copied_from_encounter_id TEXT,
  queue_id TEXT, created_by TEXT
);
CREATE TABLE waiting_queue(
  id TEXT PRIMARY KEY, clinical_patient_id TEXT, status TEXT, updated_at TEXT
);
CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT, actor TEXT, action TEXT, entity_type TEXT, entity_id TEXT, details_json TEXT
);
CREATE TABLE encounter_revisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  encounter_id TEXT, revision_no INTEGER, saved_at TEXT, actor TEXT,
  clinical_note TEXT, diagnosis TEXT, treatment TEXT, reason TEXT
);
""")
conn.execute("INSERT INTO patients(id,name) VALUES('p1','PACIENTE PRUEBA')")
conn.execute("INSERT INTO waiting_queue(id,clinical_patient_id,status,updated_at) VALUES('q1','p1','waiting','')")
conn.commit()
conn.close()

def db():
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c

def ensure_column(conn, table, col, ddl):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def new_id():
    return str(uuid.uuid4())

def audit(conn, action, entity_type, entity_id=None, details=None, actor="DR. ARMANDO REVELO"):
    conn.execute(
        "INSERT INTO audit_log(occurred_at,actor,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)",
        (now_iso(), actor, action, entity_type, entity_id, "{}"),
    )

ns = {
    "db": db,
    "ensure_column": ensure_column,
    "HTTPException": HTTPException,
    "JSONResponse": JSONResponse,
    "hashlib": hashlib,
    "datetime": datetime,
    "new_id": new_id,
    "now_iso": now_iso,
    "audit": audit,
    "DOCTOR_NAME": "DR. ARMANDO REVELO",
}
module = ast.Module(body=nodes, type_ignores=[])
exec(compile(module, "v163_selected.py", "exec"), ns)

class FakeRequest:
    async def json(self):
        return {
            "patient_id": "p1",
            "queue_id": "q1",
            "encounter_date": "2026-09-25",
            "encounter_time": "11:30",
            "clinical_note": "control de prueba",
            "manual_snapshot": True,
        }

resp = asyncio.run(ns["save_encounter"](FakeRequest()))
payload = resp.body.decode("utf-8")
assert "encounter_id" in payload

check = sqlite3.connect(db_path)
check.row_factory = sqlite3.Row
cols = {r[1] for r in check.execute("PRAGMA table_info(waiting_queue)")}
assert "started_at" in cols, cols
assert "completed_at" in cols, cols
row = check.execute("SELECT * FROM waiting_queue WHERE id='q1'").fetchone()
assert row["status"] == "in_consultation", dict(row)
assert row["started_at"], dict(row)
enc = check.execute("SELECT * FROM encounters WHERE patient_id='p1'").fetchone()
assert enc and enc["note_status"] == "draft", dict(enc) if enc else None
enc_id = enc["id"]
check.close()

signed = ns["sign_encounter"](enc_id)
assert signed.status_code == 200

check = sqlite3.connect(db_path)
check.row_factory = sqlite3.Row
enc = check.execute("SELECT * FROM encounters WHERE id=?", (enc_id,)).fetchone()
q = check.execute("SELECT * FROM waiting_queue WHERE id='q1'").fetchone()
assert enc["note_status"] == "signed", dict(enc)
assert q["status"] == "completed", dict(q)
assert q["completed_at"], dict(q)
check.close()

print("HISTORIA_V163_SAVE_OK AUTOSAVE_SILENT_OK FINALIZE_OK")
