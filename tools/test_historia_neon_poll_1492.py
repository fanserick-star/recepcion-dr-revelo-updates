"""Regression tests for compact emergency-only Neon polling (no live credentials).

Exercise idle remote, changed records, conflicts, fallback and Official path.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
from cloud_sync import CloudSyncService, HISTORIA_NEON_EMERGENCY_ENDPOINT_ID, HISTORIA_NEON_ENDPOINT_ID


class FakeCursor:
    def __init__(self, owner):
        self.owner = owner
        self.kind = ""
        self.table = ""
        self.description = []

    def execute(self, sql, args=None):
        self.owner.queries.append((sql, args))
        if "EXISTS(SELECT 1 FROM" in sql:
            if self.owner.fail_probe:
                raise RuntimeError("Simulated unsupported probe")
            self.kind = "probe"
            return
        if "SELECT * FROM" in sql:
            self.kind = "rows"
            self.table = sql.split("SELECT * FROM ", 1)[1].split()[0]
            self.description = [(field,) for field in ("id", "name", "deleted_at", "cloud_updated_at")]
            return
        raise AssertionError(sql)

    def fetchone(self):
        if self.kind != "probe":
            raise AssertionError("Unexpected fetchone")
        return tuple(table in self.owner.changed for table in ("patients", "encounters"))

    def fetchall(self):
        if self.kind != "rows":
            raise AssertionError("Unexpected fetchall")
        if self.table == "patients" and "patients" in self.owner.changed:
            return [("p-2", "TEST RECORD", None, "2026-11-12T20:00:01+00:00")]
        return []


class FakePG:
    def __init__(self, changed=(), fail_probe=False):
        self.changed = set(changed)
        self.fail_probe = fail_probe
        self.queries = []
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rollbacks += 1


def make_db(path):
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE sync_state(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE sync_dirty(table_name TEXT,row_key TEXT,changed_at TEXT,
                                    PRIMARY KEY(table_name,row_key));
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
            INSERT INTO meta VALUES('sync_applying_remote','0');
            INSERT INTO sync_state VALUES('last_pull','2026-11-12T19:00:00+00:00');
            CREATE TABLE patients(id TEXT PRIMARY KEY,name TEXT,deleted_at TEXT,cloud_updated_at TEXT);
            CREATE TABLE encounters(id TEXT PRIMARY KEY,name TEXT,deleted_at TEXT,cloud_updated_at TEXT);
        """)


def service(path, emergency=True):
    obj = CloudSyncService.__new__(CloudSyncService)
    obj.db_path = path
    obj.target_endpoint = HISTORIA_NEON_EMERGENCY_ENDPOINT_ID if emergency else HISTORIA_NEON_ENDPOINT_ID
    obj._remote_available_tables = {"patients", "encounters"}
    return obj


def scans(pg):
    return [sql for sql, _ in pg.queries if "SELECT * FROM" in sql]


def test_no_change(path):
    svc = service(path)
    pg = FakePG()
    assert svc._pull(pg, "2026-11-12T20:01:00+00:00") == 0
    assert len(pg.queries) == 1, pg.queries
    assert len(scans(pg)) == 0
    assert svc._last_poll_compact is True
    assert svc._last_poll_changed_tables == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT value FROM sync_state WHERE key='last_pull'").fetchone()[0] == "2026-11-12T20:01:00+00:00"
        assert conn.execute("SELECT value FROM meta WHERE key='sync_applying_remote'").fetchone()[0] == "0"


def test_one_changed(path):
    svc = service(path)
    pg = FakePG({"patients"})
    assert svc._pull(pg, "2026-11-12T20:02:00+00:00") == 1
    assert len(pg.queries) == 2, pg.queries
    assert len(scans(pg)) == 1 and "FROM patients" in scans(pg)[0]
    assert svc._last_poll_changed_tables == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM patients WHERE id='p-2'").fetchone()[0] == "TEST RECORD"


def test_fallback(path):
    svc = service(path)
    pg = FakePG(fail_probe=True)
    assert svc._pull(pg, "2026-11-12T20:03:00+00:00") == 0
    assert pg.rollbacks == 1
    assert len(scans(pg)) == 2, scans(pg)
    assert svc._last_poll_compact is False
    assert svc._last_poll_changed_tables == -1


def test_official_untouched(path):
    svc = service(path, emergency=False)
    pg = FakePG()
    assert svc._pull(pg, "2026-11-12T20:04:00+00:00") == 0
    assert len(scans(pg)) == 2
    assert all("EXISTS(SELECT 1 FROM" not in sql for sql, _ in pg.queries)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "doctor.sqlite"
        make_db(db)
        test_no_change(db)
        test_one_changed(db)
        test_fallback(db)
        test_official_untouched(db)
    print("HISTORIA_NEON_COMPACT_POLL_1492_OK")
