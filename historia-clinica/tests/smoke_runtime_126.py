from __future__ import annotations

import importlib
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOT = pathlib.Path(tempfile.gettempdir()) / "hc_runtime_smoke"
if ROOT.exists():
    shutil.rmtree(ROOT)
(ROOT / "data").mkdir(parents=True)
(ROOT / "static").mkdir(parents=True)

parts = [
    REPO / "historia-clinica/updates/v1_2_6_queue_cleanup/app.py.part01",
    REPO / "historia-clinica/updates/v1_2_6_queue_cleanup/app.py.part02",
    REPO / "historia-clinica/updates/v1_2_6_queue_cleanup/app.py.part03",
    REPO / "historia-clinica/updates/v1_2_6_queue_cleanup/app.py.part04",
]
(ROOT / "app.py").write_bytes(b"".join(p.read_bytes() for p in parts))

sync_parts = [
    REPO / "historia-clinica/updates/v1_1_3_live_sync/cloud_sync.py.part01",
    REPO / "historia-clinica/updates/v1_1_3_live_sync/cloud_sync.py.part02",
]
(ROOT / "cloud_sync.py").write_bytes(b"".join(p.read_bytes() for p in sync_parts))
shutil.copy2(REPO / "historia-clinica/updates/v1_2_6_queue_cleanup/cloud_presence_patch.py", ROOT / "cloud_presence_patch.py")
shutil.copy2(REPO / "historia-clinica/updates/v1_2_0_lan_hybrid/lan_bridge.py", ROOT / "lan_bridge.py")

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
conn.execute(
    """INSERT INTO waiting_queue(
         id,reception_event_id,reception_patient_id,clinical_patient_id,
         display_name,identification,attention_type,queued_at,status,
         source,created_at,updated_at,deleted_at
       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("queue-old","event-old","rp-1","clinical-1","PACIENTE PRUEBA",None,"Subsecuente",
     "2026-09-19T10:00:00","waiting","reception","2026-09-19T10:00:00","2026-09-19T10:00:00",None),
)
conn.execute(
    """INSERT INTO waiting_queue(
         id,reception_event_id,reception_patient_id,clinical_patient_id,
         display_name,identification,attention_type,queued_at,status,
         source,created_at,updated_at,deleted_at
       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    ("queue-new","event-new","rp-1","clinical-1","PACIENTE PRUEBA",None,"Subsecuente",
     "2026-09-19T11:00:00","waiting","reception","2026-09-19T11:00:00","2026-09-19T11:00:00",None),
)
conn.commit()
conn.close()

os.environ["HISTORIA_SYNC_ENABLED"] = "0"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

app = importlib.import_module("app")
assert app.APP_VERSION == "1.2.6", app.APP_VERSION
assert hasattr(app, "app")
paths = {getattr(r, "path", "") for r in app.app.router.routes}
assert "/cola/{queue_id}/descartar" in paths

check = sqlite3.connect(ROOT / "data" / "historia_clinica.db")
active = check.execute(
    "SELECT COUNT(*) FROM waiting_queue WHERE status IN ('waiting','in_consultation')"
).fetchone()[0]
cancelled = check.execute(
    "SELECT COUNT(*) FROM waiting_queue WHERE status='cancelled'"
).fetchone()[0]
check.close()
assert active == 1, active
assert cancelled == 1, cancelled
print("APP_IMPORT_OK", app.APP_VERSION, "QUEUE_DEDUPE_OK")
