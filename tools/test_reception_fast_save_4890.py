"""v4.8.90: guardado de atención no bloqueante, con entrega LAN verificada.
No requiere credenciales, Windows ni datos clínicos reales.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recepcion" / "app"))
import historia_lan_transport as lan


def check_durable_enqueue_and_verified_delivery() -> None:
    original = {
        "db": lan.LAN_OUTBOX_DB,
        "lookup": lan._cloud_link_id,
        "sender": lan.send_lan,
        "snapshot": lan._snapshot,
        "wake": lan._DELIVERY_WAKE,
        "retry": dict(lan._PENDING_LINK_RETRY_AT),
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            lan.LAN_OUTBOX_DB = Path(tmp) / "lan_outbox.db"
            lan._PENDING_LINK_RETRY_AT.clear()
            calls = []
            sent = []

            def wake():
                # Al despertar al worker el evento YA está confirmado en SQLite.
                with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 1
                calls.append("wake")

            class Wake:
                def set(self):
                    wake()

            lan._DELIVERY_WAKE = Wake()
            def forbidden(_pid):
                raise AssertionError("No debe consultar Neon durante el HTTP de guardado")
            lan._cloud_link_id = forbidden
            lan.send_lan = lambda payload: (_ for _ in ()).throw(
                AssertionError("No debe invocar LAN durante el HTTP de guardado")
            )
            event = lan.hybrid_queue_attention(
                reception_patient_id=1001,
                display_name="PACIENTE DE PRUEBA",
                attention_type="Consulta",
                patient_status="Nuevo",
                visit_ids=[2001],
                clinical_patient_id="id-no-verificado",
            )
            assert calls == ["wake"]
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                raw, sent_at = conn.execute(
                    "SELECT payload_json,sent_at FROM events WHERE event_id=?", (event,)
                ).fetchone()
            assert sent_at is None
            assert json.loads(raw)["clinical_patient_id"] == ""

            # Simular worker posterior a la respuesta, con enlace verificado.
            lan._cloud_link_id = lambda pid: calls.append(("lookup", str(pid))) or "clinical-ok-1001"
            lan.send_lan = lambda payload: sent.append(dict(payload)) or True
            lan._snapshot = lambda: {"lan_online": False}
            lan._flush_lan_outbox()
            assert sent and sent[0]["clinical_patient_id"] == "clinical-ok-1001"
            assert calls.count(("lookup", "1001")) == 1
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                assert conn.execute(
                    "SELECT sent_at FROM events WHERE event_id=?", (event,)
                ).fetchone()[0]

            # Vínculo ausente: queda en cola y se limita el reintento cloud.
            lan._cloud_link_id = lambda pid: calls.append(("missing", str(pid))) or ""
            missing = lan.hybrid_queue_attention(
                reception_patient_id=1002,
                display_name="PACIENTE SIN VINCULAR",
                attention_type="Consulta",
                visit_ids=[2002],
            )
            lan._flush_lan_outbox()
            lan._flush_lan_outbox()
            assert calls.count(("missing", "1002")) == 1
            assert len(sent) == 1
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                assert conn.execute(
                    "SELECT sent_at FROM events WHERE event_id=?", (missing,)
                ).fetchone()[0] is None

            # Revinculación legítima desbloquea inmediatamente sin doble turno.
            lan._cloud_link_id = lambda _pid: "clinical-ok-1002"
            assert lan.resume_pending_for_patient(1002) == 1
            lan._flush_lan_outbox()
            assert len(sent) == 2
            assert sent[1]["clinical_patient_id"] == "clinical-ok-1002"
            lan._flush_lan_outbox()
            assert len(sent) == 2

            # Cancelación antes del envío jamás resucita la espera.
            cancelled = lan.hybrid_queue_attention(
                reception_patient_id=1003,
                display_name="CANCELADO",
                visit_ids=[2003],
            )
            with sqlite3.connect(lan.LAN_OUTBOX_DB) as conn:
                conn.execute("UPDATE events SET cancelled=1 WHERE event_id=?", (cancelled,))
                conn.commit()
            lan._flush_lan_outbox()
            assert len(sent) == 2
    finally:
        lan.LAN_OUTBOX_DB = original["db"]
        lan._cloud_link_id = original["lookup"]
        lan.send_lan = original["sender"]
        lan._snapshot = original["snapshot"]
        lan._DELIVERY_WAKE = original["wake"]
        lan._PENDING_LINK_RETRY_AT.clear()
        lan._PENDING_LINK_RETRY_AT.update(original["retry"])


def check_frontend_preflight_and_print_guard() -> None:
    js = (ROOT / "recepcion/app/static/app.js").read_text(encoding="utf-8")
    lan_source = (ROOT / "recepcion/app/historia_lan_transport.py").read_text(encoding="utf-8")
    queue_code = lan_source.split("def hybrid_queue_attention(", 1)[1]
    assert "_lan_outbox_put(payload)" in queue_code
    assert queue_code.index("_lan_outbox_put(payload)") < queue_code.index("_DELIVERY_WAKE.set()")
    assert "_cloud_link_id(reception_patient_id)" not in queue_code
    assert "send_lan(payload)" not in queue_code
    assert "freshClinical" in js and "clinicalCheckedAt" in js
    assert "Date.now()-Number(attentionContext.clinicalCheckedAt)<300000" in js
    assert "if(!verified)" in js and "Primero vincula la ficha" in js
    print_source = (ROOT / "recepcion/app/reception_printing_queue.py").read_text(encoding="utf-8")
    assert "_PRINT_QUEUE.put_nowait(" in print_source
    assert "_stable_print_receipt_windows(payload, printer_name, show_blood_pressure)" in print_source


if __name__ == "__main__":
    check_durable_enqueue_and_verified_delivery()
    check_frontend_preflight_and_print_guard()
    print("RECEPTION_FAST_SAVE_VERIFIED_LAN_4890_OK")
