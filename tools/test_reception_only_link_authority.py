from __future__ import annotations

import ast
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "historia-clinica" / "app"
REC = ROOT / "recepcion" / "app"
sys.path.insert(0, str(HIST))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def function_source(file: Path, name: str) -> str:
    content = read(file)
    tree = ast.parse(content)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(matches) == 1, (file, name)
    node = matches[0]
    return "\n".join(content.splitlines()[node.lineno - 1:node.end_lineno])


def test_historia_cannot_link() -> None:
    app = HIST / "app.py"
    lan_file = HIST / "lan_bridge.py"
    cloud = read(HIST / "cloud_sync.py")

    old = function_source(app, "_link_queue_patient")
    assert "raise ValueError" in old and "INSERT INTO patient_links" not in old
    dead = function_source(app, "_create_new_patient_from_queue")
    assert "raise ValueError" in dead and "INSERT INTO patients" not in dead
    manual = function_source(app, "link_and_attend_queue")
    assert "status_code=403" in manual
    assert "INSERT INTO patient_links" not in manual and "UPDATE patient_links" not in manual
    active = function_source(app, "attend_from_queue_v132")
    assert "_queue_needs_reception_link(row)" in active
    assert "_create_new_patient_from_queue" not in active
    assert "_v132_attend_original" not in active
    confirm = function_source(app, "_v132_mark_queue_confirmed")
    assert "INSERT OR REPLACE INTO meta" in confirm
    assert "INSERT INTO patient_links" not in confirm and "UPDATE patient_links" not in confirm
    cleanup = function_source(app, "merge_safe_duplicate_patients")
    assert "UPDATE patient_links" not in cleanup

    lan_enrich = function_source(lan_file, "_v132_enrich_new_patient")
    assert "payload.get(\"clinical_patient_id\")" in lan_enrich
    assert "if not reception_patient_id or not is_new or not patient_id:" in lan_enrich
    assert "INSERT INTO patient_links" not in lan_enrich
    assert "UPDATE patient_links" not in lan_enrich
    assert "patient_id = str(exact[0]" not in lan_enrich
    assert "Identificación clínica en conflicto" in lan_enrich

    assert 'if table == "patient_links":' in cloud
    assert cloud.index('if table == "patient_links":') < cloud.index('if table not in ALL_SYNC_TABLES:')
    assert 'for table, pk in BIDIRECTIONAL_TABLES.items():' in cloud

    notice = read(HIST / "historia_link_helper.py")
    assert "Pendiente de vinculación en Recepción" in notice
    name_search = read(HIST / "historia_link_name_search.py")
    block = function_source(HIST / "historia_link_name_search.py", "_helper_markup_name_first")
    assert "_reception_only_link_notice" in block
    assert "Vincular esta ficha" not in block

    # Reception remains the sole source for explicit manual links and new cards.
    reception = read(REC / "reception_history_identity_consolidated.py")
    assert 'def historia_identity_link(' in reception
    create = function_source(REC / "reception_history_identity_consolidated.py", "historia_identity_create_from_reception")
    assert "ON CONFLICT(reception_patient_id) DO NOTHING" in create
    assert "_search_candidates(cur, demo, name, 20)" in create
    assert "conn.rollback()" in create
    assert "reception_created_verified" in create
    assert "Crear ficha clínica nueva" in reception
    assert "window.openExamReviewHistoryLink" in reception
    assert "La creación y vinculación desde la cola" not in create

    reception_lan = read(REC / "historia_lan_transport.py")
    assert "AND l.verified=1" in reception_lan


def test_new_patient_import_has_no_auto_link() -> None:
    import lan_bridge as lan

    with tempfile.TemporaryDirectory() as td:
        db_file = Path(td) / "doctor.db"
        with sqlite3.connect(db_file) as db:
            db.executescript("""
                CREATE TABLE patients(
                    id TEXT PRIMARY KEY,legacy_patient_id INTEGER,
                    name TEXT,name_search TEXT,birth_date TEXT,address TEXT,
                    phone TEXT,national_id TEXT,national_id_search TEXT,
                    email TEXT,source TEXT,source_record_hash TEXT,
                    created_at TEXT,updated_at TEXT,merged_into_patient_id TEXT
                );
                CREATE TABLE patient_links(
                    reception_patient_id TEXT PRIMARY KEY,
                    clinical_patient_id TEXT,matched_by TEXT,verified INTEGER
                );
            """)
        service = types.SimpleNamespace(db_path=db_file, sync_service=None)
        payload = {
            "reception_patient_id": "101",
            "patient_status": "Nuevo",
            "display_name": "TEST PACIENTE EJEMPLO",
            "identification": "0999999999",
        }
        assert lan._v132_enrich_new_patient(service, payload) == ""
        with sqlite3.connect(db_file) as db:
            assert db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0
            assert db.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0] == 0

        payload["clinical_patient_id"] = "verified-reception-id-101"
        assert lan._v132_enrich_new_patient(service, payload) == "verified-reception-id-101"
        with sqlite3.connect(db_file) as db:
            assert db.execute("SELECT name FROM patients").fetchone()[0] == "TEST PACIENTE EJEMPLO"
            assert db.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0] == 0
        # Retrying identical handoff never creates a second patient or link.
        assert lan._v132_enrich_new_patient(service, payload) == "verified-reception-id-101"
        with sqlite3.connect(db_file) as db:
            assert db.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0] == 0


if __name__ == "__main__":
    test_historia_cannot_link()
    test_new_patient_import_has_no_auto_link()
    print("RECEPTION_ONLY_CLINICAL_LINK_AUTHORITY_OK")
