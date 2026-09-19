from __future__ import annotations

import asyncio
import importlib
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = pathlib.Path(tempfile.gettempdir()) / "hc_runtime_smoke_131"
if ROOT.exists():
    shutil.rmtree(ROOT)
(ROOT / "data").mkdir(parents=True)
(ROOT / "static").mkdir(parents=True)

parts = [
    REPO / "historia-clinica/updates/v1_3_1_new_patient_turn/app.py.part01",
    REPO / "historia-clinica/updates/v1_3_1_new_patient_turn/app.py.part02",
    REPO / "historia-clinica/updates/v1_3_1_new_patient_turn/app.py.part03",
    REPO / "historia-clinica/updates/v1_3_1_new_patient_turn/app.py.part04",
]
(ROOT / "app.py").write_bytes(b"".join(p.read_bytes() for p in parts))

sync_parts = [
    REPO / "historia-clinica/updates/v1_1_3_live_sync/cloud_sync.py.part01",
    REPO / "historia-clinica/updates/v1_1_3_live_sync/cloud_sync.py.part02",
]
(ROOT / "cloud_sync.py").write_bytes(b"".join(p.read_bytes() for p in sync_parts))
shutil.copy2(
    REPO / "historia-clinica/updates/v1_3_1_new_patient_turn/cloud_presence_patch.py",
    ROOT / "cloud_presence_patch.py",
)
shutil.copy2(
    REPO / "historia-clinica/updates/v1_3_1_new_patient_turn/lan_bridge.py",
    ROOT / "lan_bridge.py",
)

conn = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
conn.executescript("""
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE patients(
 id TEXT PRIMARY KEY, legacy_patient_id INTEGER, name TEXT, name_search TEXT,
 birth_date TEXT, sex TEXT, civil_status TEXT, address TEXT, phone TEXT,
 next_appointment_legacy TEXT, national_id TEXT, national_id_search TEXT,
 legacy_notes TEXT, legacy_photo BLOB, legacy_alert TEXT, email TEXT, insurer TEXT,
 legacy_no_depurable INTEGER DEFAULT 0, source TEXT, source_record_hash TEXT,
 created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE TABLE encounters(
 id TEXT PRIMARY KEY, patient_id TEXT, legacy_history_id INTEGER, legacy_patient_id INTEGER,
 encounter_date TEXT, encounter_time TEXT, clinical_note TEXT, diagnosis TEXT, treatment TEXT,
 source TEXT, source_record_hash TEXT, is_legacy_locked INTEGER DEFAULT 0,
 created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE TABLE patient_links(
 reception_patient_id TEXT PRIMARY KEY, clinical_patient_id TEXT, matched_by TEXT,
 verified INTEGER, verified_at TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE waiting_queue(
 id TEXT PRIMARY KEY, reception_event_id TEXT UNIQUE, reception_patient_id TEXT,
 clinical_patient_id TEXT, display_name TEXT, identification TEXT, attention_type TEXT,
 queued_at TEXT, status TEXT, source TEXT, created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE TABLE audit_log(
 id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT, actor TEXT, action TEXT,
 entity_type TEXT, entity_id TEXT, details_json TEXT
);
CREATE TABLE encounter_addenda(
 id TEXT PRIMARY KEY, encounter_id TEXT, text TEXT, created_at TEXT, actor TEXT
);
CREATE TABLE macros(
 id TEXT PRIMARY KEY, label TEXT UNIQUE, text TEXT, created_at TEXT, updated_at TEXT
);
""")
# Duplicate queue regression.
for qid,event,when in [
    ("queue-old","event-old","2026-09-19T10:00:00"),
    ("queue-new","event-new","2026-09-19T11:00:00"),
]:
    conn.execute(
        """INSERT INTO waiting_queue(
             id,reception_event_id,reception_patient_id,clinical_patient_id,
             display_name,identification,attention_type,queued_at,status,
             source,created_at,updated_at,deleted_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (qid,event,"rp-1","clinical-1","PACIENTE PRUEBA",None,"Subsecuente",
         when,"waiting","reception",when,when,None),
    )
conn.commit()
conn.close()

os.environ["HISTORIA_SYNC_ENABLED"] = "0"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

app = importlib.import_module("app")
assert app.APP_VERSION == "1.3.1", app.APP_VERSION
assert hasattr(app, "app")
paths = {getattr(r, "path", "") for r in app.app.router.routes}
assert "/cola/{queue_id}/descartar" in paths
assert "/api/encounters/save" in paths

check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
active = check.execute(
    "SELECT COUNT(*) FROM waiting_queue WHERE status IN ('waiting','in_consultation')"
).fetchone()[0]
cancelled = check.execute(
    "SELECT COUNT(*) FROM waiting_queue WHERE status='cancelled'"
).fetchone()[0]
assert active == 1, active
assert cancelled == 1, cancelled

# Server-side uppercase is authoritative, not just CSS/JS.
check.execute(
    """INSERT INTO patients(
       id,name,name_search,source,created_at,updated_at
       ) VALUES(?,?,?,?,?,?)""",
    ("patient-uppercase","PACIENTE MAYUS","PACIENTE MAYUS","test","2026-09-19T12:00:00","2026-09-19T12:00:00"),
)
check.commit()
check.close()

class FakeRequest:
    async def json(self):
        return {
            "patient_id": "patient-uppercase",
            "encounter_date": "2026-09-19",
            "encounter_time": "12:30",
            "clinical_note": "Consulta por dolor leve. control en 8 días.",
            "manual_snapshot": False,
        }

asyncio.run(app.save_encounter(FakeRequest()))
check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
saved = check.execute(
    "SELECT id,clinical_note FROM encounters WHERE patient_id='patient-uppercase' AND note_status='draft'"
).fetchone()
assert saved and saved[1] == "CONSULTA POR DOLOR LEVE. CONTROL EN 8 DÍAS.", saved

# LAN cancel removes only an unfinished draft.
check.execute(
    """INSERT INTO waiting_queue(
       id,reception_event_id,reception_patient_id,clinical_patient_id,display_name,
       attention_type,queued_at,status,source,created_at,updated_at
       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
    ("queue-cancel","event-cancel","rp-cancel","patient-uppercase","PACIENTE MAYUS",
     "Subsecuente","2026-09-19T13:00:00","in_consultation","reception",
     "2026-09-19T13:00:00","2026-09-19T13:00:00"),
)
check.execute(
    "UPDATE encounters SET queue_id='queue-cancel' WHERE id=?",
    (saved[0],),
)
check.commit()
check.close()

service = app.lan_bridge.LanService(ROOT, ROOT / "data" / "historia_clinica.db", "1.3.1", None)
result = service.accept_cancel({"event_id":"event-cancel"}, "127.0.0.1")
assert result["cancelled"] is True
assert result["removed_drafts"] == 1

check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
assert check.execute("SELECT status FROM waiting_queue WHERE id='queue-cancel'").fetchone()[0] == "cancelled"
assert check.execute("SELECT COUNT(*) FROM encounters WHERE id=?", (saved[0],)).fetchone()[0] == 0

# Signed clinical history is protected from a Reception deletion.
check.execute(
    """INSERT INTO waiting_queue(
       id,reception_event_id,reception_patient_id,clinical_patient_id,display_name,
       attention_type,queued_at,status,source,created_at,updated_at
       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
    ("queue-signed","event-signed","rp-signed","patient-uppercase","PACIENTE MAYUS",
     "Subsecuente","2026-09-19T14:00:00","completed","reception",
     "2026-09-19T14:00:00","2026-09-19T14:00:00"),
)
check.execute(
    """INSERT INTO encounters(
       id,patient_id,encounter_date,encounter_time,clinical_note,source,
       source_record_hash,is_legacy_locked,created_at,updated_at,note_status,queue_id
       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("signed-1","patient-uppercase","2026-09-19","14:00","HISTORIA FIRMADA","historia_clinica",
     "hash",0,"2026-09-19T14:00:00","2026-09-19T14:00:00","signed","queue-signed"),
)
check.commit()
check.close()

protected = service.accept_cancel({"event_id":"event-signed"}, "127.0.0.1")
assert protected["protected_signed_history"] is True
check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
assert check.execute("SELECT COUNT(*) FROM encounters WHERE id='signed-1'").fetchone()[0] == 1
assert check.execute("SELECT status FROM waiting_queue WHERE id='queue-signed'").fetchone()[0] == "completed"
check.close()



# NUEVO from Reception: auto-create minimal ficha, link it, show turn and badge.
check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
check.execute(
    """INSERT INTO waiting_queue(
       id,reception_event_id,reception_patient_id,clinical_patient_id,
       display_name,identification,attention_type,queued_at,status,
       source,created_at,updated_at,deleted_at
       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (
        "queue-new-patient","event-new-patient","rp-new-777",None,
        "GUTIERREZ TROYA REINALDO PORFIRIO","1717171717","Nuevo",
        "2026-09-19T15:00:00","waiting","reception",
        "2026-09-19T15:00:00","2026-09-19T15:00:00",None,
    ),
)
check.commit()
check.close()

response = app.attend_from_queue("queue-new-patient")
assert response.status_code == 303
assert "/nueva?queue_id=queue-new-patient" in response.headers["location"]

check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
check.row_factory = sqlite3.Row
created = check.execute(
    """SELECT * FROM patients
       WHERE name='GUTIERREZ TROYA REINALDO PORFIRIO'
         AND national_id_search='1717171717'"""
).fetchall()
assert len(created) == 1, created
new_pid = created[0]["id"]
qrow = check.execute(
    "SELECT clinical_patient_id FROM waiting_queue WHERE id='queue-new-patient'"
).fetchone()
assert qrow and qrow["clinical_patient_id"] == new_pid
link = check.execute(
    "SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id='rp-new-777'"
).fetchone()
assert link and link["clinical_patient_id"] == new_pid
check.close()

home_html = app.home().body.decode("utf-8")
assert "TURNO" in home_html and "#2" in home_html, home_html[:1000]
assert "★ PACIENTE NUEVO" in home_html

consult_html = app.new_consultation(new_pid, queue_id="queue-new-patient").body.decode("utf-8")
assert "PACIENTE NUEVO" in consult_html
assert "TURNO #2" in consult_html

# Re-opening the same queue must not create a second ficha.
response2 = app.attend_from_queue("queue-new-patient")
assert response2.status_code == 303
check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
again = check.execute(
    "SELECT COUNT(*) FROM patients WHERE national_id_search='1717171717'"
).fetchone()[0]
check.close()
assert again == 1, again

print("APP_IMPORT_OK", app.APP_VERSION, "UPPERCASE_OK", "LAN_CANCEL_SAFE_OK", "NEW_PATIENT_AUTO_CREATE_OK", "TURN_BADGE_OK")
