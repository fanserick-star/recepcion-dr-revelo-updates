from __future__ import annotations

import json
import sqlite3

import historia_bridge

APP_VERSION = "4.6.15"

_ORIGINAL_QUEUE = historia_bridge.queue_attention
_ORIGINAL_SEND_PAYLOAD = historia_bridge._send_payload


def _clean(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _queue_attention_reliable(*args, **kwargs):
    """A fresh Recepción handoff must really resend even if this event existed before.

    A repeated patient/visit produces the same deterministic event_id. Older code only
    replaced payload_json, leaving sent_at populated; therefore a previously sent and
    cancelled event could never be delivered again. Resetting the delivery markers here
    makes an explicit new handoff authoritative without deleting any historical row.
    """
    event_id = _ORIGINAL_QUEUE(*args, **kwargs)
    if not event_id:
        return event_id

    stamp = historia_bridge._now()
    try:
        historia_bridge._ensure_outbox()
        with sqlite3.connect(historia_bridge.OUTBOX_DB, timeout=5) as conn:
            conn.execute(
                """
                UPDATE events
                SET created_at=?,attempts=0,last_attempt_at=NULL,last_error='',sent_at=NULL
                WHERE event_id=?
                """,
                (stamp, str(event_id)),
            )
            conn.commit()
        historia_bridge.flush_pending(max_items=100, background=True)
    except Exception:
        # The original queue call already protected the event locally; failure here must
        # not make the Reception save fail. bridge_status will expose a pending retry.
        pass
    return event_id


def _send_payload_reliable(conn, payload: dict) -> None:
    action = _clean(payload.get("action") or "handoff", 40).lower()

    if action == "cancel":
        # A delayed cancel from an earlier test/delete must not cancel a newer explicit
        # requeue of the same deterministic event_id.
        target = _clean(payload.get("target_event_id") or payload.get("event_id"), 180)
        control_created = _clean(payload.get("created_at"), 40)
        if target and control_created:
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT queued_at FROM waiting_queue WHERE reception_event_id=%s LIMIT 1",
                    (target,),
                )
                row = cur.fetchone()
                queued_at = _clean(row[0], 40) if row else ""
                if queued_at and control_created < queued_at:
                    return
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

    _ORIGINAL_SEND_PAYLOAD(conn, payload)

    if action not in {"cancel", "restore"}:
        # The base UPSERT intentionally preserved many fields, but it also preserved a
        # previous status='cancelled'. A fresh handoff must reactivate the queue row.
        event_id = _clean(payload.get("event_id"), 180)
        queued_at = _clean(payload.get("queued_at"), 40) or historia_bridge._now()
        if event_id:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    UPDATE waiting_queue
                    SET status='waiting',queued_at=%s,updated_at=%s,deleted_at=NULL,
                        cloud_updated_at=now()
                    WHERE reception_event_id=%s
                      AND status<>'completed'
                    """,
                    (queued_at, historia_bridge._now(), event_id),
                )
                conn.commit()
            finally:
                try:
                    cur.close()
                except Exception:
                    pass


historia_bridge.queue_attention = _queue_attention_reliable
historia_bridge._send_payload = _send_payload_reliable

PATCH_BOOT_OK = True
