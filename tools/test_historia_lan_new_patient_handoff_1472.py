"""Offline regression: a newly verified patient must exist locally BEFORE LAN queue insert.

Simulates a stricter existing SQLite waiting_queue with a foreign key; no live
Neon, patient records, WhatsApp or clinical documents are touched.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "historia-clinica/app/lan_bridge.py"
spec = importlib.util.spec_from_file_location("historia_lan_queue_1472", BRIDGE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory(prefix="history-lan-1472-") as temp:
    root = Path(temp)
    database = root / "history-test.sqlite"
    with sqlite3.connect(database) as conn:
        conn.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE patients(
          id TEXT PRIMARY KEY,legacy_patient_id TEXT,name TEXT,name_search TEXT,
          birth_date TEXT,address TEXT,phone TEXT,national_id TEXT,
          national_id_search TEXT,email TEXT,source TEXT,source_record_hash TEXT,
          created_at TEXT,updated_at TEXT,merged_into_patient_id TEXT
        );
        CREATE TABLE patient_links(
          reception_patient_id TEXT PRIMARY KEY,clinical_patient_id TEXT,verified INTEGER
        );
        CREATE TABLE waiting_queue(
          id TEXT PRIMARY KEY,reception_event_id TEXT UNIQUE,
          reception_patient_id TEXT,clinical_patient_id TEXT NOT NULL REFERENCES patients(id),
          display_name TEXT,identification TEXT,attention_type TEXT,patient_status TEXT,
          reception_turn INTEGER,queued_at TEXT,status TEXT,source TEXT,
          created_at TEXT,updated_at TEXT,started_at TEXT
        );
        """)
    service = module.LanService(root, database, "1.4.72")
    payload = {
        "event_id": "test-turn-same-event",
        "reception_patient_id": "reception-01",
        "clinical_patient_id": "chart-verified-01",
        "patient_status": "NUEVO",
        "display_name": "PACIENTE DE PRUEBA",
        "identification": "FAKE-ID-0001",
        "attention_type": "CONSULTA",
        "reception_turn": 7,
        "queued_at": "2026-11-07T08:00:00",
    }

    result = service.accept_handoff(payload, "127.0.0.1")
    assert result["ok"] and result["demographics_received"] and not result["duplicate"]
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT id FROM patients").fetchall() == [("chart-verified-01",)]
        assert conn.execute("SELECT clinical_patient_id FROM waiting_queue").fetchall() == [("chart-verified-01",)]
        assert conn.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0] == 0

    result2 = service.accept_handoff(payload, "127.0.0.1")
    assert result2["ok"] and result2["duplicate"]
    assert result2["queue_id"] == result["queue_id"]
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM waiting_queue").fetchone()[0] == 1

    # A conflicting identity must be rejected, never matched or linked by Historia.
    conflict = dict(payload, event_id="different-event", clinical_patient_id="different-chart")
    try:
        service.accept_handoff(conflict, "127.0.0.1")
    except ValueError as exc:
        assert "conflicto" in str(exc).lower()
    else:
        raise AssertionError("Conflicting clinical identity must not enter queue")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM waiting_queue").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0] == 0

print("HISTORIA_LAN_NEW_PATIENT_BEFORE_QUEUE_1472_OK")
