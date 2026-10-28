"""Recepción 4.8.111: reintentos LAN puntuales y estado, sin datos reales ni Neon."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recepcion/app"))

import historia_lan_transport as lan


def test_due_retry_and_status():
    original_db = lan.LAN_OUTBOX_DB
    original_schema = lan._OUTBOX_SCHEMA_PATH
    try:
        with tempfile.TemporaryDirectory() as directory:
            lan.LAN_OUTBOX_DB = Path(directory) / "lan-outbox.db"
            lan._OUTBOX_SCHEMA_PATH = None
            assert lan.next_retry_wait_seconds() == 45
            assert lan.pending_delivery_diagnostics()["delivery_phase"] == "delivered"

            event_id = lan.hybrid_queue_attention(
                reception_patient_id="90001",
                display_name="PACIENTE DE PRUEBA",
                attention_type="Consulta",
                visit_ids=["310001"],
            )
            assert lan.pending_delivery_diagnostics()["delivery_phase"] == "verifying_chart"
            assert lan.next_retry_wait_seconds() == 45

            lan._defer_lan_event(event_id, 2, "Historia no confirmó recepción LAN")
            delay = lan.next_retry_wait_seconds()
            assert 0.1 <= delay <= 2.1, delay
            detail = lan.pending_delivery_diagnostics()
            assert detail["delivery_phase"] == "retrying_lan", detail
            assert 0 <= detail["delivery_retry_seconds"] <= 2

            # Un vencimiento anterior no debe volver a esperar otros 45 segundos.
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                conn.execute(
                    "UPDATE events SET next_attempt_at=? WHERE event_id=?",
                    ((datetime.now() - timedelta(seconds=4)).isoformat(timespec="seconds"), event_id),
                )
                conn.commit()
            assert 0.1 <= lan.next_retry_wait_seconds() <= 0.25

            lan._defer_lan_event(event_id, 30, "Neon temporalmente no disponible: timeout")
            assert lan.pending_delivery_diagnostics()["delivery_phase"] == "retrying_neon"
            lan._defer_lan_event(event_id, 300, "Ficha clínica pendiente de verificar o vincular")
            assert lan.pending_delivery_diagnostics()["delivery_phase"] == "waiting_link"

            lan._lan_outbox_mark(event_id, sent=True)
            assert lan.pending_delivery_diagnostics()["delivery_phase"] == "delivered"
            assert lan.next_retry_wait_seconds() == 45
    finally:
        lan.LAN_OUTBOX_DB = original_db
        lan._OUTBOX_SCHEMA_PATH = original_schema


def test_worker_and_badge_contract():
    worker = (ROOT / "recepcion/app/reception_history_lan_resilience.py").read_text(encoding="utf-8")
    ui = (ROOT / "recepcion/app/reception_history_transport.py").read_text(encoding="utf-8")
    assert "timeout = _lan.next_retry_wait_seconds(max_wait=45) if online else 45" in worker
    assert "_lan._DELIVERY_WAKE.wait(timeout=timeout)" in worker
    for stage in ("verifying_chart", "waiting_link", "retrying_neon", "retrying_lan"):
        assert stage in ui
    assert "lan_last_delivery_seconds" in ui
    # El envío sigue verificando vínculo en Neon y nunca acepta IDs sin validar.
    source = (ROOT / "recepcion/app/historia_lan_transport.py").read_text(encoding="utf-8")
    assert "verified_id = _cloud_link_id(patient_id)" in source
    assert "if not _clean(payload.get(\"clinical_patient_id\"), 120):" in source
    assert "ORDER BY CASE WHEN attempt_count=0 THEN 0 ELSE 1 END" in source


if __name__ == "__main__":
    test_due_retry_and_status()
    test_worker_and_badge_contract()
    print("RECEPTION_LAN_RETRY_DEADLINE_48111_OK")
