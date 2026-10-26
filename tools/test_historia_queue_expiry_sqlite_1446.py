from __future__ import annotations

"""Regression: expiry must respect the existing local SQLite CHECK constraint.

Extract the actual production function without importing the full clinical
application, so the test never opens or writes to patient databases.
"""

import ast
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "historia-clinica" / "app" / "app.py"
parsed = ast.parse(SOURCE.read_text(encoding="utf-8-sig"), filename=str(SOURCE))
functions = [n for n in parsed.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "cleanup_stale_waiting_queue"]
assert len(functions) == 1, "Production cleanup function is missing or duplicated"
test_function = ast.Module(body=functions, type_ignores=[])

with tempfile.TemporaryDirectory(prefix="historia-queue-1446-") as folder:
    path = Path(folder) / "synthetic_only.db"
    stamp = datetime.now().isoformat(timespec="seconds")
    old = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    today = datetime.now().isoformat(timespec="seconds")
    audits = []

    def db():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def audit(conn, action, entity_type, entity_id=None, details=None):
        audits.append((action, entity_type, entity_id, details))

    with db() as conn:
        conn.executescript("""
            CREATE TABLE waiting_queue (
                id TEXT PRIMARY KEY,
                display_name TEXT,
                queued_at TEXT,
                created_at TEXT,
                updated_at TEXT,
                status TEXT NOT NULL
                    CHECK (status IN ('waiting','in_consultation','completed','cancelled'))
            );
        """)
        conn.executemany(
            "INSERT INTO waiting_queue (id,display_name,queued_at,created_at,updated_at,status) VALUES(?,?,?,?,?,?)",
            [
                ("old_waiting", "Paciente de prueba", old, old, old, "waiting"),
                ("today_waiting", "Paciente de hoy", today, today, today, "waiting"),
                ("old_in_consultation", "Consulta vigente", old, old, old, "in_consultation"),
                ("old_completed", "Consulta finalizada", old, old, old, "completed"),
                ("old_cancelled", "Turno cancelado", old, old, old, "cancelled"),
            ],
        )

    namespace = {"db": db, "datetime": datetime, "now_iso": lambda: stamp, "audit": audit}
    exec(compile(test_function, str(SOURCE), "exec"), namespace)
    cleanup = namespace["cleanup_stale_waiting_queue"]
    assert cleanup() == ["old_waiting"], "Only yesterday's waiting turn should expire"

    with db() as conn:
        statuses = dict(conn.execute("SELECT id,status FROM waiting_queue").fetchall())
    assert statuses == {
        "old_waiting": "cancelled",
        "today_waiting": "waiting",
        "old_in_consultation": "in_consultation",
        "old_completed": "completed",
        "old_cancelled": "cancelled",
    }, statuses
    assert len(audits) == 1 and audits[0][0] == "cleanup" and audits[0][3]["count"] == 1
    assert audits[0][3]["expired_queue_ids"] == ["old_waiting"]
    assert cleanup() == [], "Cleanup must be idempotent"
    assert len(audits) == 1, "Second cleanup must not write duplicate audits"

print("OK: SQLite CHECK-safe stale waiting queue cleanup; current turns and consultations preserved")
