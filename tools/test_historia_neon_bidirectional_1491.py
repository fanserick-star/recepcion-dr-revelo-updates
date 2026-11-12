"""Two-way clinical Neon cutover safety checks without live DB or private data."""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app"
sys.path.insert(0, str(APP))
import neon_official_return as engine

panel = (APP / "neon_return_settings.py").read_text(encoding="utf-8")
cloud = (APP / "cloud_sync.py").read_text(encoding="utf-8")
ast.parse(panel)
ast.parse((APP / "neon_official_return.py").read_text(encoding="utf-8"))
assert 'target = "official" if current_target == "emergency" else "emergency"' in panel
assert 'target=target' in panel
assert 'check_automatic_return(report, private)' in panel
assert 'neon_return_before_copy.sqlite' in panel
assert 'if health["pending"] != 0 or health["conflicts"] != 0:' in panel
assert 'if request.get("source_target") not in (None, expected_source):' in panel
assert 'if not request:' in panel  # Nothing changes after a normal update/install
assert 'return {"state": "not_scheduled"}' in panel
assert 'HISTORIA_EMERGENCY_DATABASE_URL' in panel or '_load_direction_credentials' in panel
assert "cloud_endpoint_id" in cloud
assert "emergency_cutover_seeded_1478" in cloud
assert '"emergency_cutover_seeded_1478"' in (APP / "neon_official_return.py").read_text()
assert 'input type=\'password\'' not in panel

official = "postgresql://user:pass@ep-sweet-mud-arlsk7qa.c-4.us-west-2.aws.neon.tech/neondb"
emergency = "postgresql://user:pass@ep-noisy-paper-arf28291.c-4.us-west-2.aws.neon.tech/neondb"

class FakePG:
    def cursor(self):
        return self
    def execute(self, sql):
        assert sql == "SELECT now()::text", sql
    def fetchone(self):
        return ("2026-11-12T16:50:00+00",)
    def commit(self):
        pass

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "data").mkdir()
    (root / ".env").write_text(
        "HISTORIA_DATABASE_URL=" + emergency + "\n" +
        "HISTORIA_NEON_TARGET=emergency\n" +
        "HISTORIA_OFFICIAL_DATABASE_URL=" + official + "\n",
        encoding="utf8",
    )
    db = sqlite3.connect(root / "data" / "historia_clinica.db")
    db.execute("CREATE TABLE sync_state(key TEXT PRIMARY KEY,value TEXT)")
    db.commit()

    def select_target(target):
        source, destination, _ = engine._load_direction_credentials(root, target)
        result = engine.switch(root, db, source, destination, "verified", FakePG(), target=target)
        assert result["connection"] == target
        values = dict(db.execute("SELECT key,value FROM sync_state"))
        assert values["cloud_endpoint_id"] == (
            engine.DESTINATION if target == "official" else engine.SOURCE
        )
        assert values["cloud_bootstrap_complete"] == "1"
        assert values["last_pull"] == "2026-11-12T16:50:00+00"
        assert values["neon_last_switch_at"]
        env = (root / ".env").read_text(encoding="utf8")
        assert "HISTORIA_NEON_TARGET=" + target in env
        assert "HISTORIA_DATABASE_URL=" + destination in env
        assert "HISTORIA_OFFICIAL_DATABASE_URL=" + official in env
        assert "HISTORIA_EMERGENCY_DATABASE_URL=" + emergency in env
        return values

    initial = select_target("official")
    try:
        engine._load_direction_credentials(root, "official")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Cannot return to active Official")
    reversed_values = select_target("emergency")
    assert reversed_values["emergency_return_verified_sha"] == "verified"
    assert reversed_values["emergency_cutover_seeded_1478"]
    assert (root / "data" / "neon_before_emergency_private.env").exists()
    third = select_target("official")
    assert third["official_return_verified_sha"] == "verified"

    env_file = root / ".env"
    original = env_file.read_text()
    env_file.write_text(original.replace(emergency, official))
    try:
        engine._load_direction_credentials(root, "emergency")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Wrong emergency endpoint must not be accepted")
    env_file.write_text(original)
    db.close()

print("HISTORIA_NEON_BIDIRECTIONAL_1491_OK")
