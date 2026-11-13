"""Historia 1.4.94: key-bucket reconciliation never downloads whole remote IDs.

Synthetic SQLite and a protocol fake, plus query-shape validation on Neon.
No clinical patient data, credentials or production writes.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
from cloud_sync import (
    CloudSyncService, BIDIRECTIONAL_TABLES,
    HISTORIA_NEON_EMERGENCY_ENDPOINT_ID, HISTORIA_NEON_ENDPOINT_ID,
)

TABLES = ("patients", "encounters", "encounter_addenda", "macros",
          "prescriptions", "certificates", "clinic_settings")


class FakeCursor:
    def __init__(self, parent):
        self.parent = parent
        self.rows = []

    def execute(self, query, params=None):
        self.parent.queries.append((query, params))
        table = next((t for t in TABLES if f'"{t}"' in query), None)
        assert table, query[:200]
        remote = set(self.parent.data[table])
        pk = BIDIRECTIONAL_TABLES[table]
        if "GROUP BY bucket" in query:
            assert "STRING_AGG" in query and "MD5" in query
            groups = {}
            for key in remote:
                groups.setdefault(hashlib.md5(key.encode()).hexdigest()[:2], []).append(key)
            self.rows = []
            for bucket, keys in sorted(groups.items()):
                keys.sort()
                digest = hashlib.md5("".join(hashlib.md5(k.encode()).hexdigest() for k in keys).encode("ascii")).hexdigest()
                self.rows.append((bucket, len(keys), digest))
        elif "jsonb_array_elements_text" in query:
            assert f'remote."{pk}"=requested.key' in query
            assert params and len(params) == 1
            requested = json.loads(params[0])
            assert 0 < len(requested) <= 128
            self.rows = [(key,) for key in requested if key not in remote]
        elif "SELECT CAST" in query:
            # Old Official method; emergency must never reach here.
            self.rows = [(key,) for key in sorted(remote)]
        else:
            raise AssertionError(query)

    def fetchall(self):
        return self.rows


class FakePG:
    def __init__(self, data):
        self.data = data
        self.queries = []

    def cursor(self):
        return FakeCursor(self)


def local_database(path, contents):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sync_dirty(table_name TEXT,row_key TEXT,changed_at TEXT,PRIMARY KEY(table_name,row_key))")
        for table in TABLES:
            pk = BIDIRECTIONAL_TABLES[table]
            db.execute(f'CREATE TABLE "{table}" ("{pk}" TEXT PRIMARY KEY)')
            db.executemany(f'INSERT INTO "{table}" ("{pk}") VALUES (?)', [(k,) for k in contents[table]])


def service(path, emergency=True):
    svc = CloudSyncService.__new__(CloudSyncService)
    svc.db_path = path
    svc.target_endpoint = HISTORIA_NEON_EMERGENCY_ENDPOINT_ID if emergency else HISTORIA_NEON_ENDPOINT_ID
    svc._remote_columns = lambda pg, schema, table: {BIDIRECTIONAL_TABLES[table]}
    return svc


def test_emergency(path):
    local = {table: [] for table in TABLES}
    local["patients"] = [f"p-{i:04d}" for i in range(1000)]
    local["encounters"] = [f"enc-{i:04d}" for i in range(1000)]
    local["prescriptions"] = ["rx-1"]
    local["certificates"] = ["cert-1"]

    remote = {table: list(keys) for table, keys in local.items()}
    remote["patients"].remove("p-0730")
    remote["patients"].append("cloud-only")
    # Remote-only key must not create fake local dirty records.
    remote["encounters"].append("cloud-exclusive-encounter")
    local_database(path, local)
    svc, pg = service(path), FakePG(remote)

    assert svc._queue_missing_local_rows(pg) == 1
    assert svc._missing_repair_confirmed_missing == 1
    assert svc._missing_repair_bucket_mismatches >= 1
    assert svc._missing_repair_candidate_keys < 100, svc._missing_repair_candidate_keys
    assert len([q for q,_ in pg.queries if "GROUP BY bucket" in q]) == len(TABLES)
    assert all("SELECT CAST" not in q for q,_ in pg.queries)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT table_name,row_key FROM sync_dirty").fetchall() == [("patients", "p-0730")]
    # Second repair is idempotent; the dirty queue stays intact until push.
    assert svc._queue_missing_local_rows(pg) == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0] == 1


def test_official(path):
    svc, pg = service(path, emergency=False), FakePG({table: [] for table in TABLES})
    assert svc._queue_missing_local_rows(pg) >= 2000
    assert any("SELECT CAST" in q for q,_ in pg.queries)
    assert not any("GROUP BY bucket" in q for q,_ in pg.queries)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "fake-doctor.sqlite"
        test_emergency(path)
        test_official(path)
    source = (APP / "cloud_sync.py").read_text(encoding="utf8")
    assert "missing_repair_method=(" in source
    assert "self._push(pg)" in source
    assert "self._pull(pg, remote_now)" in source
    assert "sync_dirty" in source
    print("HISTORIA_NEON_BUCKET_REPAIR_1494_OK")
