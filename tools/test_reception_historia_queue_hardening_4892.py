"""v4.8.92 — regresiones del transporte Recepción → Historia; solo SQLite temporal.

Ninguna prueba escribe pacientes reales ni contacta Neon/Historia.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recepcion/app"))
import historia_lan_transport as lan
import reception_history_lan_resilience as resilience


def test_32_rows_cannot_starve_new_patient():
    saved = (lan.LAN_OUTBOX_DB, lan._cloud_link_id, lan.send_lan, lan._snapshot, lan._DELIVERY_WAKE)
    try:
        with tempfile.TemporaryDirectory() as td:
            lan.LAN_OUTBOX_DB = Path(td) / "handoffs.db"
            lookups, sent = [], []
            lan._cloud_link_id = lambda p: lookups.append(int(p)) or ("clinical-ready" if int(p) == 1031 else "")
            lan.send_lan = lambda p: sent.append(dict(p)) or True
            lan._snapshot = lambda: {"lan_online": True}
            lan._DELIVERY_WAKE = threading.Event()

            for i in range(32):
                lan.hybrid_queue_attention(
                    reception_patient_id=1000+i,
                    display_name="PRUEBA COLA",
                    attention_type="Consulta",
                    visit_ids=[2000+i],
                )
            for _ in range(4):
                lan._flush_lan_outbox()  # 8 por lote; 31 sin vínculo no bloquean último
            assert len(sent) == 1, "El paciente 32 debería salir aunque 31 anteriores no tengan ficha"
            assert sent[0]["reception_patient_id"] == "1031"
            assert sent[0]["clinical_patient_id"] == "clinical-ready"
            assert len(lookups) == 32
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as db:
                retries = db.execute(
                    "SELECT COUNT(*) FROM events WHERE next_attempt_at IS NOT NULL "
                    "AND attempt_count=1 AND sent_at IS NULL"
                ).fetchone()[0]
                assert retries == 31
                assert db.execute(
                    "SELECT COUNT(*) FROM events WHERE sent_at IS NOT NULL"
                ).fetchone()[0] == 1

            lan._flush_lan_outbox()  # ningún Neon extra hasta el plazo
            assert len(lookups) == 32
            lan._cloud_link_id = lambda pid: "clinical-restored"
            assert lan.resume_pending_for_patient(1000) == 1
            lan._flush_lan_outbox()
            assert len(sent) == 2
            assert sent[1]["reception_patient_id"] == "1000"
            assert sent[1]["clinical_patient_id"] == "clinical-restored"
            lan._flush_lan_outbox()
            assert len(sent) == 2
    finally:
        lan.LAN_OUTBOX_DB, lan._cloud_link_id, lan.send_lan, lan._snapshot, lan._DELIVERY_WAKE = saved


def test_cancel_serialized_with_inflight_delivery():
    saved = (lan.LAN_OUTBOX_DB, lan._cloud_link_id, lan.send_lan, lan._snapshot, lan._DELIVERY_WAKE)
    try:
        with tempfile.TemporaryDirectory() as td:
            lan.LAN_OUTBOX_DB = Path(td) / "handoffs.db"
            lan._cloud_link_id = lambda pid: "clinical-safe"
            lan._snapshot = lambda: {"lan_online": True}
            lan._DELIVERY_WAKE = threading.Event()
            event_id = lan.hybrid_queue_attention(
                reception_patient_id=4000,
                display_name="PACIENTE CANCELO",
                attention_type="Consulta",
                visit_ids=[5000],
            )
            started, release = threading.Event(), threading.Event()
            delivered, cancelled = [], []

            def fake_send(payload):
                started.set()
                assert release.wait(5), "Timeout simulando entrega"
                delivered.append(payload["event_id"])
                return True

            lan.send_lan = fake_send
            worker = threading.Thread(target=lan._flush_lan_outbox, daemon=True)
            worker.start()
            assert started.wait(3)
            def cancel():
                cancelled.append(lan._lan_set_cancelled(event_id, True))
            stopper = threading.Thread(target=cancel, daemon=True)
            stopper.start()
            # El candado de la entrega mantiene la cancelación ordenada.
            assert not cancelled
            release.set()
            worker.join(5)
            stopper.join(5)
            assert not worker.is_alive() and not stopper.is_alive()
            assert delivered == [event_id]
            assert cancelled and cancelled[0][0] is True
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as db:
                row = db.execute(
                    "SELECT cancelled,sent_at FROM events WHERE event_id=?", (event_id,)
                ).fetchone()
            assert row[0] == 1 and row[1], "Queda cancelado después del ACK; se puede enviar control"
            lan._flush_lan_outbox()
            assert delivered == [event_id]
    finally:
        lan.LAN_OUTBOX_DB, lan._cloud_link_id, lan.send_lan, lan._snapshot, lan._DELIVERY_WAKE = saved


def test_neon_outage_does_not_spin_or_hide_new_events():
    saved = (lan.LAN_OUTBOX_DB, lan._cloud_link_id, lan.send_lan, lan._snapshot, lan._DELIVERY_WAKE)
    try:
        with tempfile.TemporaryDirectory() as td:
            lan.LAN_OUTBOX_DB = Path(td) / "handoffs.db"
            wake = threading.Event()
            lan._DELIVERY_WAKE = wake
            lan._snapshot = lambda: {"lan_online": True}
            lan.send_lan = lambda p: (_ for _ in ()).throw(AssertionError("Never send without verified link"))
            for i in range(9):
                lan.hybrid_queue_attention(
                    reception_patient_id=6000+i,
                    display_name="SIN NEON",
                    visit_ids=[7000+i],
                )
            wake.clear()
            calls = []
            def disconnected(pid):
                calls.append(pid)
                lan._LINK_LOOKUP_STATE.error = "Timeout Neon"
                return ""
            lan._cloud_link_id = disconnected
            lan._flush_lan_outbox()
            assert len(calls) == 1, "La caída de Neon no hace 8 consultas consecutivas"
            assert not wake.is_set(), "No debe girar el worker sin pausa durante caída"
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as db:
                deadline = db.execute(
                    "SELECT next_attempt_at FROM events WHERE attempt_count=1"
                ).fetchone()[0]
                assert deadline and datetime.fromisoformat(deadline) > datetime.now()
    finally:
        lan.LAN_OUTBOX_DB, lan._cloud_link_id, lan.send_lan, lan._snapshot, lan._DELIVERY_WAKE = saved


def test_http_rejection_is_not_false_lan_disconnect():
    saved = (resilience._ORIGINAL_SEND_LAN, lan._snapshot, resilience.resilient_probe_once)
    try:
        resilience._ORIGINAL_SEND_LAN = lambda _payload: False
        lan._snapshot = lambda: {"lan_online": True}  # Doctor respondió HTTP 400
        resilience.resilient_probe_once = lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("No escanear red ante un rechazo HTTP clínico")
        )
        assert resilience.resilient_send_lan({"event_id": "test"}) is False
    finally:
        resilience._ORIGINAL_SEND_LAN, lan._snapshot, resilience.resilient_probe_once = saved


def test_sources_and_ui():
    source = (ROOT / "recepcion/app/historia_lan_transport.py").read_text(encoding="utf-8")
    ui = (ROOT / "recepcion/app/reception_history_transport.py").read_text(encoding="utf-8")
    assert "next_attempt_at" in source and "attempt_count" in source
    assert "with _HANDOFF_FLUSH_LOCK:" in source
    assert "_DELIVERY_WAKE.set()" in source
    assert "ORDER BY CASE WHEN attempt_count=0 THEN 0 ELSE 1 END" in source
    assert "Historia: LAN conectada'+(pending>0?" in ui
    assert "setInterval(refresh,5000);" in ui
    assert '"4.8.93"' in (ROOT / "recepcion/app/recepcion-version.json").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_32_rows_cannot_starve_new_patient()
    test_cancel_serialized_with_inflight_delivery()
    test_neon_outage_does_not_spin_or_hide_new_events()
    test_http_rejection_is_not_false_lan_disconnect()
    test_sources_and_ui()
    print("RECEPTION_HISTORIA_LAN_QUEUE_HARDENING_4892_OK")
