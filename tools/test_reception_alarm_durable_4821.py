"""Durable WhatsApp alarm signals: offline-only. Never accesses Neon/Meta."""
import ast
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
tree = ast.parse(source)


def extract(name: str, scope: dict):
    nodes = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name]
    assert len(nodes) == 1, name
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "source-only", "exec"), scope)
    return scope[name]


def test_durable_generation_and_reopen():
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "offline_cache.db")
        scope = {"sqlite3": sqlite3, "OFFLINE_DB_PATH": db_path}
        state = extract("_wa_alarm_signal_state", scope)
        enqueue = extract("_wa_alarm_signal_enqueue", scope)
        mark = extract("_wa_alarm_signal_mark", scope)
        assert not state()["pending"]
        enqueue()
        first = state()
        assert first["pending"] and first["generation"] == 1
        enqueue()
        second = state()
        assert second["pending"] and second["generation"] == 2
        assert mark(1, acknowledged=True) is False  # stale ACK cannot lose a new booking
        assert state()["pending"]
        assert mark(2, acknowledged=False, error="HTTPError HTTP 403")
        assert state()["last_error"] == "HTTPError HTTP 403"
        # Simulates a process restart, with fresh Python functions and same disk.
        another = {"sqlite3": sqlite3, "OFFLINE_DB_PATH": db_path}
        recovered = extract("_wa_alarm_signal_state", another)()
        assert recovered["pending"] and recovered["generation"] == 2
        assert mark(2, acknowledged=True)
        assert not state()["pending"]
        assert state()["acknowledged_at"]
        enqueue()
        assert state()["generation"] == 3 and state()["pending"]


def test_lifecycle_and_no_new_cron():
    assert "def _wa_alarm_hint_resume()" in source
    assert "_wa_alarm_hint_resume()" in source
    assert "    _wa_alarm_signal_enqueue()" in source
    assert "        _wa_alarm_hint_start()" in source
    assert 'payload.get("ok") is not True' in source
    assert "if last[\"pending\"]" in source
    assert '"generation" != failed_generation' not in source  # runtime uses direct dict access
    assert "_wa_alarm_signal_mark(generation, acknowledged=True)" in source
    assert "WHATSAPP_ALARM_NOTIFY_PENDING" in source
    assert "source_id=int" not in source[source.index("def _wa_alarm_hint_post_once"):source.index("def _wa_alarm_hint_start")]
    assert "runScheduler(" not in source[source.index("def _wa_alarm_hint_post_once"):source.index("def _wa_alarm_hint_start")]


if __name__ == "__main__":
    test_durable_generation_and_reopen()
    test_lifecycle_and_no_new_cron()
    print("WA_DURABLE_ALARM_HINTS_RESTART_RACE_ACK_NO_SEND_OK")
