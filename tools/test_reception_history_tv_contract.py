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
    assert "target=_flush_control_outbox" not in read(APP / "historia_lan_transport.py")
    assert "_DELIVERY_WAKE.set()" in read(APP / "historia_lan_transport.py")
    assert "def resilient_delivery_loop()" in resilience
    assert "_lan._flush_control_outbox()" in resilience
    assert "_lan._flush_lan_outbox()" in resilience
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
    """No event on open/finish/cancel; only explicit call from doctor produces audio."""
    import time
    import ast
    from reception_tv_common import _epoch, _now_iso

    # CI verifies the actual clinic TV subclass without importing full Reception
    # runtime (SQLAlchemy/Neon are not dependencies of this isolated LAN test).
    cls_tree = ast.parse(read(APP / "reception_tv_turns.py"))
    cls = next(n for n in cls_tree.body if isinstance(n, ast.ClassDef)
               and n.name == "ClinicTVTurnService")
    ns = {"TVTurnService": TVTurnService, "_epoch": _epoch, "_now_iso": _now_iso}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 "<clinic-tv-state>", "exec"), ns)
    ClinicTVTurnService = ns["ClinicTVTurnService"]

    def state(current=None, waiting=None, recent=None, doctor_call=None):
        return {
            "host": "127.0.0.1", "current": current, "waiting": waiting or [],
            "recent": recent or [], "doctor_call": doctor_call,
        }

    q1 = {"queue_id": "q1", "turn": 1, "status": "waiting"}
    q2 = {"queue_id": "q2", "turn": 2, "status": "waiting"}
    current1 = {"queue_id": "q1", "turn": 1, "status": "in_consultation"}
    current2 = {"queue_id": "q2", "turn": 2, "status": "in_consultation"}

    for service in (TVTurnService(), ClinicTVTurnService()):
        service.apply_history(state(waiting=[q1, q2]))
        event_before = int(service.live["event_id"])
        assert service.live["next_waiting_turn"] == 1

        # Opening a chart without calling must remain silent.
        service.apply_history(state(current=current1, waiting=[q2]))
        assert service.live["mode"] == "attending" and service.live["turn"] == 1
        assert int(service.live["event_id"]) == event_before

        # Saving the chart and polling it again must be silent.
        service.apply_history(state(current=current1, waiting=[q2]))
        assert int(service.live["event_id"]) == event_before

        # Completing the consultation leaves q2 waiting without calling it.
        service.apply_history(state(waiting=[q2], recent=[{"queue_id": "q1", "status": "completed"}]))
        assert service.live["mode"] == "idle" and service.live["turn"] is None
        assert service.live["next_waiting_turn"] == 2
        assert int(service.live["event_id"]) == event_before
        service.apply_history(state(waiting=[q2], recent=[{"queue_id": "q1", "status": "completed"}]))
        assert int(service.live["event_id"]) == event_before

        # Switching/opening a different patient record does not call anyone.
        service.apply_history(state(current=current2))
        assert service.live["mode"] == "attending" and service.live["turn"] == 2
        assert int(service.live["event_id"]) == event_before

    cancelled = ClinicTVTurnService()
    cancelled.apply_history(state(waiting=[q1, q2]))
    cancelled.apply_history(state(current=current1, waiting=[q2]))
    before_cancel = int(cancelled.live["event_id"])
    cancelled.apply_history(state(waiting=[q2], recent=[{"queue_id": "q1", "status": "cancelled"}]))
    assert cancelled.live["mode"] == "idle"
    assert int(cancelled.live["event_id"]) == before_cancel

    # A separate deliberate doctor call is still allowed and deduplicated.
    manual = ClinicTVTurnService()
    manual.apply_history(state(waiting=[q2]))
    before = int(manual.live["event_id"])
    event = {"event_id": "manual-call-2", "queue_id": "q2", "turn": 2,
             "at_epoch": time.time(), "exam_review": False}
    manual.apply_history(state(waiting=[q2], doctor_call=event))
    assert manual.live["mode"] == "calling" and manual.live["turn"] == 2
    assert int(manual.live["event_id"]) == before + 1
    manual.apply_history(state(waiting=[q2], doctor_call=event))
    assert int(manual.live["event_id"]) == before + 1
    # A second deliberate click is a new manual call event, not a poll duplicate.
    event2 = dict(event, event_id="manual-call-3", at_epoch=time.time())
    manual.apply_history(state(waiting=[q2], doctor_call=event2))
    assert int(manual.live["event_id"]) == before + 2

    # Old Reception's live controls are disabled so doctor is sole caller.
    for action in (manual.recall_live, manual.test_sound_live):
        try:
            action()
            raise AssertionError("Reception cannot create a real calling event")
        except ValueError:
            pass
    assert int(manual.live["event_id"]) == before + 2

    # Simulated completion does not announce the next turn either.
    test = TVTurnService()
    test.set_test({"mode": "attending", "turn": 6, "waiting_count": 2})
    test.finish_test()
    assert test.test["mode"] == "idle" and test.test["turn"] == 7

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
            # En producción _DELIVERY_WAKE activa el único worker LAN.
            # En esta prueba aislada no arranca el monitor: ejecutar su tick.
            assert lan._lan_control_pending_count() == 1
            lan._flush_control_outbox()
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


def test_exam_review_linked_chart_and_tv_label() -> None:
    """Isolated real doctor queue + privacy-safe TV state + Reception TV service."""
    sys.path.insert(0, str(HISTORIA))
    import lan_bridge as doctor_lan
    import tv_turn_bridge as doctor_tv
    # CI validates the real TV-turn implementation without starting FastAPI.
    import types
    stub = types.ModuleType("core_runtime")
    stub.V460_OVERLAY_CSS = ""
    stub.V460_OVERLAY_JS = ""
    stub.Depends = lambda _value: None
    stub.current_user = lambda: None
    class DummyRoutes:
        def on_event(self, *_args, **_kwargs):
            return lambda func: func
        def get(self, *_args, **_kwargs):
            return lambda func: func
    stub.app = DummyRoutes()
    previous = sys.modules.get("core_runtime")
    sys.modules["core_runtime"] = stub
    try:
        from reception_tv_turns import ClinicTVTurnService
    finally:
        if previous is not None:
            sys.modules["core_runtime"] = previous
        else:
            sys.modules.pop("core_runtime", None)

    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        doctor_db = folder / "historia_exam_review.db"
        with sqlite3.connect(doctor_db) as conn:
            conn.executescript(
                """
                CREATE TABLE waiting_queue(
                  id TEXT PRIMARY KEY,reception_event_id TEXT UNIQUE,
                  reception_patient_id TEXT, clinical_patient_id TEXT,
                  display_name TEXT,identification TEXT,attention_type TEXT,
                  patient_status TEXT,reception_turn INTEGER,
                  queued_at TEXT,status TEXT,source TEXT,created_at TEXT,
                  updated_at TEXT,started_at TEXT,completed_at TEXT
                );
                """
            )
        doctor = doctor_lan.LanService(folder, doctor_db, "1.4.7")
        from historia_bridge import _event_id
        event_id = _event_id(77, [401])
        result = doctor.accept_handoff({
            "event_id": event_id,
            "reception_patient_id": "77",
            "clinical_patient_id": "ficha-confirmada-77",
            "display_name": "APELLIDO PRUEBA",
            "identification": "0988888888",
            "attention_type": "Revisión de exámenes",
            "patient_status": "Subsecuente",
            "reception_turn": 5,
            "visit_ids": ["401"],
        }, "127.0.0.1")
        assert result["ok"]
        with sqlite3.connect(doctor_db) as conn:
            row = conn.execute(
                "SELECT clinical_patient_id,attention_type,reception_turn,status "
                "FROM waiting_queue WHERE reception_event_id=?", (event_id,),
            ).fetchone()
            assert row == ("ficha-confirmada-77", "Revisión de exámenes", 5, "waiting")
        snapshot = doctor_tv._snapshot(doctor_db)
        assert snapshot["waiting_count"] == 1
        assert snapshot["waiting"][0]["turn"] == 5
        assert snapshot["waiting"][0]["exam_review"] is True
        assert "APELLIDO PRUEBA" not in json.dumps(snapshot)
        assert "0988888888" not in json.dumps(snapshot)

        tv = ClinicTVTurnService()
        tv.apply_history({"host": "testdoctor", **snapshot})
        assert tv.live["next_waiting_turn"] == 5
        assert tv.live["next_waiting_exam_review"] is True

        with sqlite3.connect(doctor_db) as conn:
            conn.execute(
                "UPDATE waiting_queue SET status='in_consultation' WHERE reception_event_id=?",
                (event_id,),
            )
            conn.commit()
        now_current = doctor_tv._snapshot(doctor_db)
        tv.apply_history({"host": "testdoctor", **now_current})
        assert tv.live["mode"] == "attending"  # direct open never calls the TV
        assert tv.live["exam_review"] is True
        assert tv.live["turn"] == 5

def test_optional_surname_audio_uses_exact_historia_queue_id() -> None:
    """Only exact today's delivered queue may speak surnames; never infer by turn."""
    import uuid
    from datetime import datetime, timedelta
    from reception_tv_speech import surnames_for_queue, _first_two_surnames
    old_path = lan.LAN_OUTBOX_DB
    try:
        with tempfile.TemporaryDirectory() as td:
            lan.LAN_OUTBOX_DB = Path(td) / "outbox.db"
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                conn.execute(
                    "CREATE TABLE events(event_id TEXT PRIMARY KEY, payload_json TEXT, "
                    "created_at TEXT, sent_at TEXT, cancelled INTEGER DEFAULT 0)"
                )
                now = datetime.now().isoformat(timespec="seconds")
                yesterday = (datetime.now()-timedelta(days=1)).isoformat(timespec="seconds")
                samples = [
                    ("event-valid", "PÉREZ GARCÍA JUAN CARLOS", now, "sent", 0),
                    ("event-cancelled", "GÓMEZ VEGA ALBERTO", now, "sent", 1),
                    ("event-old", "OTRO APELLIDO MARIA", yesterday, "sent", 0),
                    ("event-unsent", "LÓPEZ SUÁREZ MIGUEL", now, None, 0),
                    ("event-placeholder", "PACIENTE DE PRUEBA", now, "sent", 0),
                ]
                for event_id, name, created, sent, cancelled in samples:
                    payload = json.dumps({"event_id":event_id,"display_name":name})
                    conn.execute(
                        "INSERT INTO events(event_id,payload_json,created_at,sent_at,cancelled) "
                        "VALUES(?,?,?,?,?)",
                        (event_id, payload, created, sent, cancelled),
                    )
                conn.commit()
            def queue(event_id: str) -> str:
                return str(uuid.uuid5(uuid.NAMESPACE_URL, "historia-queue:"+event_id))
            assert surnames_for_queue(queue("event-valid")) == "PÉREZ GARCÍA"
            assert surnames_for_queue(queue("event-cancelled")) == ""
            assert surnames_for_queue(queue("event-old")) == ""
            assert surnames_for_queue(queue("event-unsent")) == ""
            assert surnames_for_queue(queue("event-placeholder")) == ""
            assert surnames_for_queue(queue("event-unknown")) == ""
            assert surnames_for_queue("invalid-queue") == ""
            assert _first_two_surnames("GARCÍA PÉREZ MARÍA") == "GARCÍA PÉREZ"
            assert _first_two_surnames("PACIENTE") == ""
    finally:
        lan.LAN_OUTBOX_DB = old_path


def test_fictitious_surnames_preview_is_safe() -> None:
    """Fictitious tests work without patients and never expose surname text on TV."""
    import ast
    import threading
    import time
    import reception_tv_speech as speech

    assert set(speech.VOICE_TEST_SAMPLES) == {
        "perez_garcia", "zambrano_velez", "lopez_mendoza", "rodriguez_andrade"
    }
    assert all(len(value.split()) == 2 for value in speech.VOICE_TEST_SAMPLES.values())

    # Isolate the REAL two TV methods without importing Reception's full ORM.
    tree = ast.parse(read(APP / "reception_tv_turns.py"))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                    and node.name == "ClinicTVTurnService")
    methods = [node for node in original.body
               if isinstance(node, ast.FunctionDef) and
               node.name in {"trigger_voice_test", "display_snapshot"}]
    assert len(methods) == 2

    class Base:
        def display_snapshot(self, *, touch_tv=False):
            return {"event_id": 7, "mode": "idle", "display_mode": "live"}
        def _voice_config(self):
            return {"announce_surnames": False}

    fake = ast.ClassDef(
        name="TestTV", bases=[ast.Name(id="Base", ctx=ast.Load())],
        keywords=[], body=methods, decorator_list=[]
    )
    ns = {"Base": Base, "_epoch": time.time,
          "VOICE_TEST_SAMPLES": speech.VOICE_TEST_SAMPLES}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fake], type_ignores=[])),
                 "<tv-fictitious-preview>", "exec"), ns)
    svc = ns["TestTV"]()
    svc.lock = threading.RLock()
    svc.voice_test_id = 0
    svc.voice_test_turn = 6
    svc.voice_test_sample_key = ""
    svc.voice_test_started_epoch = 0.0
    before = svc.display_snapshot()
    assert not before["voice_test_has_surnames"]

    # Preview works even when real-patient surname announcements are disabled.
    result = svc.trigger_voice_test({"turn": 6, "sample": "perez_garcia"})
    assert result["has_sample"] is True and result["turn"] == 6
    snapshot = svc.display_snapshot()
    assert snapshot["voice_test_has_surnames"] is True
    assert snapshot["mode"] == "idle" and snapshot["event_id"] == 7
    assert "Pérez" not in json.dumps(snapshot, ensure_ascii=False)
    assert "perez_garcia" not in json.dumps(snapshot)
    try:
        svc.trigger_voice_test({"turn": 6, "sample": "nombre-de-paciente-real"})
        raise AssertionError("Unknown or real surnames must never be accepted")
    except ValueError:
        pass
    assert svc.voice_test_id == result["voice_test_id"]

    # The exact SAME WAV synthesis path receives two synthetic surnames.
    original_synthesize = speech._synthesize
    try:
        speech._synthesize = lambda turn, voice, rate, pitch, surname="": (
            (str(turn) + ":" + surname).encode("utf-8")
        )
        generated = speech.turn_voice_wav(6, surnames=speech.VOICE_TEST_SAMPLES["perez_garcia"])
        assert generated == "6:Pérez García".encode("utf-8")
    finally:
        speech._synthesize = original_synthesize

    # Number-only tests clear any previous sample without touching the queue.
    result = svc.trigger_voice_test({"turn": 6})
    assert result["has_sample"] is False
    assert svc.display_snapshot()["voice_test_has_surnames"] is False
    assert svc.display_snapshot()["event_id"] == 7


def test_verified_tv_bell_never_replays_or_autostarts() -> None:
    """Server-side bell is silent for old pages, reloads and stale events."""
    from reception_tv_common import _epoch
    import reception_tv_http

    service = TVTurnService()
    service.live.update({
        "event_id": 11, "doctor_call_event_id": "doctor-explicit-11",
        "doctor_call_event_seq": 11, "history_online": True, "mode": "calling", "turn": 6, "sound": True,
    })
    service._doctor_hold_until = _epoch() + 7
    boot = service.tv_boot_id
    kw = {"mode": "live", "event": 11, "doctor_token": "doctor-explicit-11",
          "boot": boot, "remote_ip": "192.168.1.15"}

    assert not service.authorize_bell(**{**kw, "boot": "old-fully-page"})
    assert not service.authorize_bell(**{**kw, "doctor_token": "older-doctor-token"})
    assert not service.authorize_bell(**{**kw, "event": 10})
    assert service.authorize_bell(**kw)  # first real manual event is audible
    assert not service.authorize_bell(**kw)  # reload: never audible again
    assert service.bell_diagnostics()["events"][0]["reason"] == "duplicado_bloqueado"

    service.live["event_id"] = 12
    assert not service.authorize_bell(**{**kw, "event": 12})  # old doctor token
    service.live["doctor_call_event_id"] = "doctor-explicit-12"
    assert not service.authorize_bell(**{**kw, "event": 12, "doctor_token": "doctor-explicit-12"})
    service.live["doctor_call_event_seq"] = 12
    assert service.authorize_bell(**{**kw, "event": 12, "doctor_token": "doctor-explicit-12"})
    service._doctor_hold_until = _epoch() - 1
    service.live["event_id"] = 13
    service.live["doctor_call_event_id"] = "doctor-explicit-13"
    service.live["doctor_call_event_seq"] = 13
    assert not service.authorize_bell(**{**kw, "event": 13, "doctor_token": "doctor-explicit-13"})
    service.record_old_bell_request()
    assert service.bell_diagnostics()["events"][0]["reason"] == "pagina_antigua"

    # Simulated test mode retains manual chime capability, but not forever.
    service.config["display_mode"] = "test"
    service.set_test({"mode": "calling", "turn": 7, "sound": True})
    test_id = int(service.test["event_id"])
    test_kw = {"mode": "test", "event": test_id, "doctor_token": "",
               "boot": boot, "remote_ip": "192.168.1.15"}
    assert service.authorize_bell(**test_kw)
    assert not service.authorize_bell(**test_kw)
    service.set_test({"mode": "calling", "turn": 7, "sound": True})
    service.test_bell_until = _epoch() - 1
    assert not service.authorize_bell(**{**test_kw, "event": service.test["event_id"]})

    source = read(APP / "reception_tv_http.py")
    display = read(APP / "tv_display.html")
    assert 'service.record_old_bell_request()' in source
    assert 'return self._send(200, _SILENCE, "audio/wav", "no-store")' in source
    assert 'service.authorize_bell(' in source
    assert 'if path == "/api/bell-diagnostics":' in source
    assert 'self._require_control()' in source
    assert 'id="ding" preload="none"' in display
    assert 'src="/ding.wav"' not in display
    assert "/api/verified-ding.wav?" in display
    assert "a.onended=function()" in display


def test_tv_surname_opt_in_survives_app_restart() -> None:
    """Opt-in and chosen Windows SAPI voice must survive reading config.json."""
    import reception_tv_media as media

    saved_path, saved_dir = media.CONFIG_PATH, media.DATA_DIR
    try:
        with tempfile.TemporaryDirectory() as td:
            media.DATA_DIR = Path(td)
            media.CONFIG_PATH = Path(td) / "config.json"
            obj = media.TVMediaMixin()
            obj.config = obj._load_config()
            assert obj.config["voice_announce_surnames"] is False
            assert obj.config["windows_voice_name"] == ""
            # User explicitly turns this on in TV > Voz de llamado.
            obj.config["voice_announce_surnames"] = True
            obj.config["windows_voice_name"] = "Voz de Windows de prueba"
            obj._save_config()
            restored = media.TVMediaMixin()._load_config()
            assert restored["voice_announce_surnames"] is True
            assert restored["windows_voice_name"] == "Voz de Windows de prueba"
            assert restored["voice_rate"] == obj.config["voice_rate"]

            restored["voice_announce_surnames"] = False
            obj.config = restored
            obj._save_config()
            assert media.TVMediaMixin()._load_config()["voice_announce_surnames"] is False

            # Backward-compatible older config must default to OFF.
            media.CONFIG_PATH.write_text(json.dumps({"videos_enabled": True}), encoding="utf-8")
            assert media.TVMediaMixin()._load_config()["voice_announce_surnames"] is False
    finally:
        media.CONFIG_PATH, media.DATA_DIR = saved_path, saved_dir


if __name__ == "__main__":
    test_tv_surname_opt_in_survives_app_restart()
    test_verified_tv_bell_never_replays_or_autostarts()
    test_fictitious_surnames_preview_is_safe()
    test_optional_surname_audio_uses_exact_historia_queue_id()
    test_source_contracts()
    test_cancelled_handoff_cannot_revive()
    test_control_retry_is_persistent()
    test_tv_completed_vs_cancelled()
    test_connected_historia_cancel_removes_waiting_and_tv_without_clinical_loss()
    test_exam_review_linked_chart_and_tv_label()
    print("RECEPTION/HISTORIA/TV CONTRACT OK")
