from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
module_path = ROOT / 'historia-clinica/app/lan_bridge.py'
spec = importlib.util.spec_from_file_location('lan_bridge_identity_test', module_path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    db_path = root / 'historia.db'
    with sqlite3.connect(db_path) as conn:
        conn.executescript('''
        CREATE TABLE patients(
          id TEXT PRIMARY KEY,name TEXT,name_search TEXT,national_id TEXT,
          national_id_search TEXT,birth_date TEXT,phone TEXT,email TEXT,address TEXT,
          merged_into_patient_id TEXT,deleted_at TEXT
        );
        CREATE TABLE encounters(
          id TEXT PRIMARY KEY,patient_id TEXT,encounter_date TEXT,note_status TEXT,deleted_at TEXT
        );
        CREATE TABLE patient_links(
          reception_patient_id TEXT PRIMARY KEY,clinical_patient_id TEXT,matched_by TEXT,
          verified INTEGER,verified_at TEXT,created_at TEXT,updated_at TEXT
        );
        CREATE TABLE waiting_queue(
          id TEXT PRIMARY KEY,reception_patient_id TEXT,clinical_patient_id TEXT,status TEXT,updated_at TEXT
        );
        CREATE TABLE audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,occurred_at TEXT,actor TEXT,action TEXT,
          entity_type TEXT,entity_id TEXT,details_json TEXT
        );
        ''')
        conn.execute(
            'INSERT INTO patients VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            ('p1','ESPINEL FRANCO ERICK JHAIR','ESPINEL FRANCO ERICK JHAIR',
             '1207087550','1207087550','1996-01-01','0999999999','e@test.local',
             'QUEVEDO','',None),
        )
        conn.execute(
            'INSERT INTO encounters VALUES(?,?,?,?,?)',
            ('e1','p1','2019-05-10','legacy',None),
        )
        conn.commit()

    service = mod.LanService(root, db_path, '1.3.83')
    payload = {
        'reception_patient_id': '501',
        'name': 'ESPINEL FRANCO ERICK JHAIR',
        'identification': '1207087550',
        'birth_date': '1996-01-01',
        'phone': '0999999999',
    }
    prepared = service.identity_status(payload, '127.0.0.1', auto_link=True)
    assert prepared['ok'] is True
    assert prepared['linked'] is True
    assert prepared['auto_linked'] is True
    assert prepared['clinical_patient']['id'] == 'p1'
    assert prepared['history_date_count'] == 1
    assert prepared['last_history_date'] == '2019-05-10'

    search = service.identity_search({**payload, 'q': 'ESPINEL FRANCO ERICK', 'limit': 10}, '127.0.0.1')
    assert search['ok'] is True
    assert search['results']
    assert search['results'][0]['id'] == 'p1'

    linked = service.identity_link(
        {**payload, 'reception_patient_id': '502', 'clinical_patient_id': 'p1'},
        '127.0.0.1',
    )
    assert linked['linked'] is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            'SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id=?',
            ('502',),
        ).fetchone()
        assert row and row[0] == 'p1'

print('LAN_IDENTITY_TEST_OK')
