"""Regresiones del ACK LAN Recepción → Historia: solo datos simulados."""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recepcion/app"))
import historia_lan_transport as lan


def test_ack_timeout_and_duplicate_safe_contract():
    saved = (lan._snapshot, lan._set_state, lan._http_json)
    state = {"lan_online": True, "lan_host": "192.168.1.14", "token": "simulated"}
    calls = []

    try:
        lan._snapshot = lambda: dict(state)
        lan._set_state = lambda **kwargs: state.update(kwargs)

        def fake_http(host, path, **kwargs):
            calls.append((host, path, kwargs["timeout"], kwargs.get("payload", {}).get("event_id")))
            return {"ok": True, "event_id": "test-event", "duplicate": False}

        lan._http_json = fake_http
        assert lan.send_lan({"event_id": "test-event", "clinical_patient_id": "verified-chart"})
        assert calls == [("192.168.1.14", "/handoff", 4.0, "test-event")]
        assert lan.LAN_HANDOFF_TIMEOUT_SECONDS == 4.0
        assert not lan.send_lan({"event_id": "unverified", "clinical_patient_id": ""})
        assert len(calls) == 1, "Nunca enviar turnos sin ficha verificada"
    finally:
        lan._snapshot, lan._set_state, lan._http_json = saved


def test_http_400_stays_online_and_preserves_safe_reason():
    saved = (lan._snapshot, lan._set_state, lan._http_json)
    state = {"lan_online": True, "lan_host": "192.168.1.14", "token": "simulated"}
    try:
        lan._snapshot = lambda: dict(state)
        lan._set_state = lambda **kwargs: state.update(kwargs)

        def rejected(*args, **kwargs):
            body = json.dumps({"ok": False, "error": "Identificación clínica en conflicto: resolver en Recepción."}).encode("utf-8")
            raise urllib.error.HTTPError("http://localhost/handoff", 400, "Bad request", {}, io.BytesIO(body))

        lan._http_json = rejected
        assert not lan.send_lan({"event_id": "test-event", "clinical_patient_id": "verified-chart"})
        assert state["lan_online"] is True, "Rechazo clínico no equivale a caída de LAN"
        assert "HTTP 400" in state["lan_last_error"]
        code, hint = lan._public_delivery_issue(state["lan_last_error"])
        assert code == "clinical_conflict"
        assert "Recepción" in hint
    finally:
        lan._snapshot, lan._set_state, lan._http_json = saved


def test_local_outbox_status_never_exposes_patient_details():
    previous_db, previous_schema = lan.LAN_OUTBOX_DB, lan._OUTBOX_SCHEMA_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            lan.LAN_OUTBOX_DB = Path(tmp) / "outbox.db"
            lan._OUTBOX_SCHEMA_PATH = None
            event_id = lan.hybrid_queue_attention(
                reception_patient_id="90001", display_name="PACIENTE SINTETICO",
                visit_ids=["70001"], clinical_patient_id="",
            )
            d = lan.pending_delivery_diagnostics()
            assert d["delivery_phase"] == "verifying_chart"
            assert d["delivery_attempts"] == 0
            lan._defer_lan_event(event_id, 15, "TimeoutError: timed out: NOMBRE DE PRUEBA")
            d = lan.pending_delivery_diagnostics()
            assert d["delivery_error_code"] == "ack_timeout"
            assert "NOMBRE DE PRUEBA" not in json.dumps(d, ensure_ascii=False)
            assert d["delivery_attempts"] == 1
            assert d["delivery_retry_seconds"] is not None
            lan._defer_lan_event(event_id, 30, "Neon temporalmente no disponible: timed out")
            assert lan.pending_delivery_diagnostics()["delivery_phase"] == "retrying_neon"
            lan._lan_outbox_mark(event_id, sent=True)
            d = lan.pending_delivery_diagnostics()
            assert d["delivery_phase"] == "delivered" and not d["delivery_error_hint"]
    finally:
        lan.LAN_OUTBOX_DB, lan._OUTBOX_SCHEMA_PATH = previous_db, previous_schema


def test_ui_contract_and_retry_policy():
    transport = (ROOT / "recepcion/app/historia_lan_transport.py").read_text(encoding="utf-8")
    ui = (ROOT / "recepcion/app/reception_history_transport.py").read_text(encoding="utf-8")
    assert "timeout=LAN_HANDOFF_TIMEOUT_SECONDS" in transport
    assert "if verified_id != _clean(payload.get" in transport
    assert "_defer_lan_event(str(event_id), 15, error)" in transport
    assert "delivery_error_hint" in ui and "delivery_retry_seconds" in ui
    assert "setInterval(refresh,5000);" in ui


if __name__ == "__main__":
    test_ack_timeout_and_duplicate_safe_contract()
    test_http_400_stays_online_and_preserves_safe_reason()
    test_local_outbox_status_never_exposes_patient_details()
    test_ui_contract_and_retry_policy()
    print("RECEPTION_LAN_DELIVERY_DIAGNOSTICS_48115_OK")
