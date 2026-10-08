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



def test_connected_historia_cancel_removes_waiting_and_tv_without_clinical_loss() -> None:
    """Real doctor-side handlers with simulated online LAN, isolated in temp SQLite."""
    import time

    sys.path.insert(0, str(HISTORIA))
    import lan_bridge as doctor_lan
    import tv_turn_bridge as doctor_tv

    old_outbox = lan.LAN_OUTBOX_DB
    old_http = lan._http_json
    old_state = lan._snapshot()
    try:
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            lan.LAN_OUTBOX_DB = folder / "recepcion_lan_outbox.db"
            doctor_db = folder / "historia_test.db"
            with sqlite3.connect(doctor_db) as conn:
                conn.executescript(
                    """
                    CREATE TABLE waiting_queue(
                      id TEXT PRIMARY KEY,
                      reception_event_id TEXT UNIQUE,
                      reception_patient_id TEXT,
                      clinical_patient_id TEXT,
                      display_name TEXT,
                      identification TEXT,
                      attention_type TEXT,
                      patient_status TEXT,
                      reception_turn INTEGER,
                      queued_at TEXT,
                      status TEXT,
                      source TEXT,
                      created_at TEXT,
                      updated_at TEXT,
                      started_at TEXT,
                      completed_at TEXT
                    );
                    CREATE TABLE encounters(
                      id TEXT PRIMARY KEY,
                      queue_id TEXT,
                      note_status TEXT,
                      updated_at TEXT
                    );
                    CREATE TABLE audit_log(
                      occurred_at TEXT, actor TEXT, action TEXT,
                      entity_type TEXT, entity_id TEXT, details_json TEXT
                    );
                    """
                )
            doctor = doctor_lan.LanService(folder, doctor_db, "1.4.5")

            event_id = lan._cloud._event_id("88", ["901"])
            payload = {
                "event_id": event_id,
                "reception_patient_id": "88",
                "display_name": "PACIENTE DE PRUEBA",
                "identification": "",
                "attention_type": "Consulta",
                "patient_status": "Nuevo",
                "reception_turn": 8,
                "visit_ids": ["901"],
            }
            response = doctor.accept_handoff(payload, "127.0.0.1")
            assert response["ok"]
            before = doctor_tv._snapshot(doctor_db)
            assert before["waiting_count"] == 1
            assert before["waiting"][0]["turn"] == 8

            lan._lan_outbox_put(payload)
            lan._lan_outbox_mark(event_id, sent=True)

            def online_lan_http(host, path, *, method="GET", payload=None, token="", timeout=0.8):
                assert host == "online-doctor-pc"
                assert token == "mock-lan-token"
                assert method == "POST" and path == "/cancel"
                return doctor.accept_cancel(payload, "127.0.0.1")

            lan._http_json = online_lan_http
            lan._set_state(
                lan_online=True,
                lan_host="online-doctor-pc",
                token="mock-lan-token",
                token_host="online-doctor-pc",
            )
            matched = lan.hybrid_cancel_attention(
                visit_id="901",
                reception_patient_id="88",
            )
            assert matched == [event_id]
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if lan._lan_control_pending_count() == 0:
                    break
                time.sleep(0.02)
            assert lan._lan_control_pending_count() == 0, "Online cancellation not acknowledged"

            with sqlite3.connect(doctor_db) as conn:
                status = conn.execute(
                    "SELECT status FROM waiting_queue WHERE reception_event_id=?",
                    (event_id,),
                ).fetchone()[0]
            assert status == "cancelled"
            after = doctor_tv._snapshot(doctor_db)
            assert after["waiting_count"] == 0
            assert after["current"] is None
            assert not after["waiting"]

            # A signed encounter may not be erased/cancelled by Reception.
            signed_event = lan._cloud._event_id("89", ["902"])
            signed_payload = dict(
                payload,
                event_id=signed_event,
                reception_patient_id="89",
                reception_turn=9,
                visit_ids=["902"],
            )
            signed = doctor.accept_handoff(signed_payload, "127.0.0.1")
            with sqlite3.connect(doctor_db) as conn:
                conn.execute(
                    "INSERT INTO encounters(id,queue_id,note_status) VALUES(?,?,?)",
                    ("signed-1", signed["queue_id"], "signed"),
                )
            protected = doctor.accept_cancel(
                {"event_id": signed_event},
                "127.0.0.1",
            )
            assert protected["protected_signed_history"] is True
            assert protected["cancelled"] is False
            with sqlite3.connect(doctor_db) as conn:
                assert conn.execute(
                    "SELECT note_status FROM encounters WHERE id='signed-1'"
                ).fetchone()[0] == "signed"
    finally:
        lan._http_json = old_http
        lan.LAN_OUTBOX_DB = old_outbox
        lan._set_state(**old_state)

if __name__ == "__main__":
    test_source_contracts()
    test_cancelled_handoff_cannot_revive()
    test_control_retry_is_persistent()
    test_tv_completed_vs_cancelled()
    test_connected_historia_cancel_removes_waiting_and_tv_without_clinical_loss()
    print("RECEPTION/HISTORIA/TV CONTRACT OK")
