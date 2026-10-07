from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"
HISTORIA = ROOT / "historia-clinica" / "app"
sys.path.insert(0, str(APP))

import historia_lan_transport as lan
from reception_tv_service import TVTurnService


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_source_contracts() -> None:
    app = read(APP / "app.py")
    bridge = read(APP / "reception_history_bridge.py")
    resilience = read(APP / "reception_history_lan_resilience.py")
    tv = read(APP / "reception_tv_service.py")
    h_lan = read(HISTORIA / "lan_bridge.py")
    h_tv = read(HISTORIA / "tv_turn_bridge.py")
    h_queue = read(HISTORIA / "queue_open_attention.py")

    assert "historia_bridge.OUTBOX_DB" not in app
    assert "historia_bridge.flush_pending" not in app
    assert bridge.index("reception_history_lan_resilience") < bridge.index("reception_history_cancellation")
    assert "historia-lan-recovery-monitor" not in resilience
    assert "_flush_control_outbox()" in resilience
    assert "control_pending" in read(APP / "historia_lan_transport.py")
    assert "events.cancelled=0" in read(APP / "historia_lan_transport.py")
    assert "target=_flush_control_outbox" in read(APP / "historia_lan_transport.py")
    assert "LAN discovery has one authority" in tv
    assert "delay = 3.0" in tv

    assert "WHERE reception_event_id=? LIMIT 1" in h_lan
    assert "protected_signed_history" in h_lan
    snap = h_tv[h_tv.index("def _snapshot"):h_tv.index("def install")]
    assert "display_name" not in snap
    assert "identification" not in snap
    assert "_is_procedure" in h_tv
    assert "previous_attention_never_auto_completed" in h_queue


def test_cancelled_handoff_cannot_revive() -> None:
    old_path = lan.LAN_OUTBOX_DB
    try:
        with tempfile.TemporaryDirectory() as td:
            lan.LAN_OUTBOX_DB = Path(td) / "outbox.db"
            payload = {"event_id":"reception:test-event","reception_patient_id":"88","visit_ids":["901"],"attention_type":"Consulta"}
            lan._lan_outbox_put(payload)
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                conn.execute("UPDATE events SET cancelled=1,sent_at=? WHERE event_id=?", ("sent", payload["event_id"]))
                conn.commit()
            changed = dict(payload)
            changed["display_name"] = "NOMBRE CORREGIDO"
            lan._lan_outbox_put(changed)
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                row = conn.execute("SELECT cancelled,sent_at,payload_json FROM events WHERE event_id=?", (payload["event_id"],)).fetchone()
            assert row[0] == 1
            assert row[1] == "sent"
            assert json.loads(row[2])["display_name"] == "NOMBRE CORREGIDO"
    finally:
        lan.LAN_OUTBOX_DB = old_path


def test_control_retry_is_persistent() -> None:
    old_path = lan.LAN_OUTBOX_DB
    old_sender = lan._send_control_lan
    try:
        with tempfile.TemporaryDirectory() as td:
            lan.LAN_OUTBOX_DB = Path(td) / "outbox.db"
            payload = {"event_id":"reception:test-control","reception_patient_id":"99","visit_ids":["902"],"attention_type":"Consulta"}
            lan._lan_outbox_put(payload)
            lan._lan_outbox_mark(payload["event_id"], sent=True)
            lan._queue_control_intent(payload["event_id"], "cancel", "902")
            lan._send_control_lan = lambda *_args, **_kwargs: False
            lan._flush_control_outbox()
            assert lan._lan_control_pending_count() == 1
            lan._send_control_lan = lambda *_args, **_kwargs: True
            lan._flush_control_outbox()
            assert lan._lan_control_pending_count() == 0
    finally:
        lan._send_control_lan = old_sender
        lan.LAN_OUTBOX_DB = old_path


def test_tv_completed_vs_cancelled() -> None:
    def state(current=None, waiting=None, recent=None):
        return {"host":"127.0.0.1","current":current,"waiting":waiting or [],"recent":recent or []}
    q1={"queue_id":"q1","turn":1,"status":"waiting"}
    q2={"queue_id":"q2","turn":2,"status":"waiting"}

    service=TVTurnService()
    service.apply_history(state(waiting=[q1,q2]))
    service.apply_history(state(current={"queue_id":"q1","turn":1,"status":"in_consultation"},waiting=[q2]))
    service.live["calling_started_epoch"]-=6
    service.apply_history(state(current={"queue_id":"q1","turn":1,"status":"in_consultation"},waiting=[q2]))
    before=int(service.live["event_id"])
    service.apply_history(state(waiting=[q2],recent=[{"queue_id":"q1","status":"completed"}]))
    assert service.live["mode"]=="calling" and service.live["turn"]==2
    assert int(service.live["event_id"])==before+1

    cancelled=TVTurnService()
    cancelled.apply_history(state(waiting=[q1,q2]))
    cancelled.apply_history(state(current={"queue_id":"q1","turn":1,"status":"in_consultation"},waiting=[q2]))
    cancelled.live["calling_started_epoch"]-=6
    cancelled.apply_history(state(current={"queue_id":"q1","turn":1,"status":"in_consultation"},waiting=[q2]))
    before_cancel=int(cancelled.live["event_id"])
    cancelled.apply_history(state(waiting=[q2],recent=[{"queue_id":"q1","status":"cancelled"}]))
    assert cancelled.live["mode"]=="idle" and cancelled.live["turn"] is None
    assert int(cancelled.live["event_id"])==before_cancel


if __name__ == "__main__":
    test_source_contracts()
    test_cancelled_handoff_cannot_revive()
    test_control_retry_is_persistent()
    test_tv_completed_vs_cancelled()
    print("RECEPTION/HISTORIA/TV CONTRACT OK")
