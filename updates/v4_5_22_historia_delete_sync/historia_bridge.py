from __future__ import annotations

import json
import os
import re
import sqlite3
import ssl
import threading
import time
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTBOX_DB = ROOT / "data" / "historia_bridge.db"
ENV_KEY = "HISTORIA_DATABASE_URL"
_LOCK = threading.Lock()
_FLUSHING = False
_LAST_ERROR = ""
_LAST_SENT_AT = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _read_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return {}
    return out


def _database_url() -> str:
    return _clean(os.getenv(ENV_KEY) or _read_env_file().get(ENV_KEY), 4000)


def _ensure_outbox() -> None:
    OUTBOX_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              last_attempt_at TEXT,
              last_error TEXT,
              sent_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_pending ON events(sent_at, created_at)")
        conn.commit()


def _event_id(reception_patient_id: object, visit_ids: list[object] | None) -> str:
    ids = ",".join(str(x) for x in (visit_ids or []) if x is not None)
    raw = f"reception:{reception_patient_id}:{ids or _now()}"
    return "reception:" + str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def _queue_id(event_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "historia-queue:" + event_id))


def _parse_pg_url(url: str) -> dict:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower().split("+", 1)[0] not in {"postgres", "postgresql"}:
        raise RuntimeError("HISTORIA_DATABASE_URL no es PostgreSQL")
    return {
        "user": urllib.parse.unquote(parts.username or ""),
        "password": urllib.parse.unquote(parts.password or ""),
        "host": parts.hostname or "",
        "port": int(parts.port or 5432),
        "database": urllib.parse.unquote((parts.path or "/neondb").lstrip("/")) or "neondb",
    }


def _connect():
    url = _database_url()
    if not url:
        raise RuntimeError("Puente no configurado: falta HISTORIA_DATABASE_URL")
    cfg = _parse_pg_url(url)
    if not cfg["user"] or not cfg["password"] or not cfg["host"]:
        raise RuntimeError("HISTORIA_DATABASE_URL incompleta")
    from pg8000 import dbapi
    return dbapi.connect(
        user=cfg["user"], password=cfg["password"], host=cfg["host"],
        port=cfg["port"], database=cfg["database"],
        ssl_context=ssl.create_default_context(), timeout=12,
    )


def _normalize_id(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _clean(value).upper())


def _resolve_patient(cur, reception_patient_id: str, identification: str) -> str | None:
    cur.execute(
        "SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id=%s AND deleted_at IS NULL LIMIT 1",
        (reception_patient_id,),
    )
    row = cur.fetchone()
    if row and row[0]:
        return str(row[0])

    ident = _normalize_id(identification)
    if not ident:
        return None
    cur.execute(
        "SELECT id FROM patients WHERE national_id_search=%s AND deleted_at IS NULL LIMIT 2",
        (ident,),
    )
    rows = cur.fetchall() or []
    if len(rows) != 1:
        return None
    clinical_id = str(rows[0][0])
    now = _now()
    cur.execute(
        """
        INSERT INTO patient_links(reception_patient_id,clinical_patient_id,matched_by,verified,verified_at,created_at,updated_at)
        VALUES(%s,%s,'identification',1,%s,%s,%s)
        ON CONFLICT(reception_patient_id) DO UPDATE SET
          clinical_patient_id=EXCLUDED.clinical_patient_id,
          matched_by='identification', verified=1, verified_at=EXCLUDED.verified_at,
          updated_at=EXCLUDED.updated_at, deleted_at=NULL
        """,
        (reception_patient_id, clinical_id, now, now, now),
    )
    return clinical_id


def _send_payload(conn, payload: dict) -> None:
    cur = conn.cursor()
    try:
        action = _clean(payload.get("action") or "handoff", 40).lower()
        now = _now()

        if action in {"cancel", "restore"}:
            target_event_id = _clean(
                payload.get("target_event_id") or payload.get("event_id"),
                180,
            )
            if not target_event_id:
                raise ValueError("Falta target_event_id")

            if action == "cancel":
                # Nunca toca una consulta completada. Recepción sólo puede
                # cancelar un turno que aún estaba esperando o en consulta.
                cur.execute(
                    """
                    UPDATE waiting_queue
                    SET status='cancelled',updated_at=%s
                    WHERE reception_event_id=%s
                      AND status IN ('waiting','in_consultation')
                    """,
                    (now, target_event_id),
                )
            else:
                # Deshacer desde Papelera: sólo revive un turno que nosotros
                # mismos habíamos cancelado. Un turno completado no cambia.
                cur.execute(
                    """
                    UPDATE waiting_queue
                    SET status='waiting',updated_at=%s,deleted_at=NULL
                    WHERE reception_event_id=%s
                      AND status='cancelled'
                    """,
                    (now, target_event_id),
                )
            conn.commit()
            return

        reception_patient_id = _clean(payload.get("reception_patient_id"), 120)
        identification = _clean(payload.get("identification"), 120)
        clinical_id = _resolve_patient(cur, reception_patient_id, identification)
        event_id = _clean(payload.get("event_id"), 160)
        queue_id = _queue_id(event_id)
        queued_at = _clean(payload.get("queued_at"), 40) or _now()
        display_name = _clean(payload.get("display_name"), 260) or "Paciente"
        attention_type = _clean(payload.get("attention_type"), 180) or "Consulta"
        cur.execute(
            """
            INSERT INTO waiting_queue(
              id,reception_event_id,reception_patient_id,clinical_patient_id,
              display_name,identification,attention_type,queued_at,status,source,created_at,updated_at
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'waiting','reception',%s,%s)
            ON CONFLICT(reception_event_id) DO UPDATE SET
              reception_patient_id=EXCLUDED.reception_patient_id,
              clinical_patient_id=COALESCE(waiting_queue.clinical_patient_id,EXCLUDED.clinical_patient_id),
              display_name=EXCLUDED.display_name,
              identification=EXCLUDED.identification,
              attention_type=EXCLUDED.attention_type,
              updated_at=EXCLUDED.updated_at,
              deleted_at=NULL
            """,
            (queue_id, event_id, reception_patient_id, clinical_id, display_name,
             identification or None, attention_type, queued_at, now, now),
        )
        conn.commit()
    finally:
        try: cur.close()
        except Exception: pass

def _flush_worker(max_items: int = 30) -> None:
    global _FLUSHING, _LAST_ERROR, _LAST_SENT_AT
    with _LOCK:
        if _FLUSHING:
            return
        _FLUSHING = True
    try:
        _ensure_outbox()
        conn = _connect()
        try:
            with sqlite3.connect(OUTBOX_DB, timeout=5) as local:
                local.row_factory = sqlite3.Row
                rows = local.execute(
                    "SELECT event_id,payload_json FROM events WHERE sent_at IS NULL ORDER BY created_at LIMIT ?",
                    (max(1, int(max_items)),),
                ).fetchall()
                for row in rows:
                    event_id = str(row["event_id"])
                    try:
                        payload = json.loads(row["payload_json"])
                        _send_payload(conn, payload)
                        stamp = _now()
                        local.execute(
                            "UPDATE events SET sent_at=?,last_attempt_at=?,last_error='' WHERE event_id=?",
                            (stamp, stamp, event_id),
                        )
                        local.commit()
                        _LAST_SENT_AT = stamp
                        _LAST_ERROR = ""
                    except Exception as exc:
                        stamp = _now()
                        safe = f"{type(exc).__name__}: {str(exc)}"[:600]
                        local.execute(
                            "UPDATE events SET attempts=attempts+1,last_attempt_at=?,last_error=? WHERE event_id=?",
                            (stamp, safe, event_id),
                        )
                        local.commit()
                        _LAST_ERROR = safe
                        break
        finally:
            try: conn.close()
            except Exception: pass
    except Exception as exc:
        _LAST_ERROR = f"{type(exc).__name__}: {str(exc)}"[:600]
    finally:
        with _LOCK:
            _FLUSHING = False


def flush_pending(max_items: int = 30, background: bool = True) -> None:
    if background:
        threading.Thread(target=_flush_worker, args=(max_items,), daemon=True, name="historia-bridge").start()
    else:
        _flush_worker(max_items)


def queue_attention(*, reception_patient_id: object, display_name: object,
                    identification: object = "", attention_type: object = "Consulta",
                    visit_ids: list[object] | None = None) -> str:
    _ensure_outbox()
    event_id = _event_id(reception_patient_id, visit_ids)
    payload = {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "queued_at": _now(),
    }
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        conn.execute(
            """
            INSERT INTO events(event_id,payload_json,created_at)
            VALUES(?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (event_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), _now()),
        )
        conn.commit()
    flush_pending(background=True)
    return event_id


def _attention_event_ids_for_visit(
    visit_id: object,
    reception_patient_id: object = "",
) -> list[str]:
    _ensure_outbox()
    wanted = str(visit_id)
    patient = str(reception_patient_id or "").strip()
    matches: list[str] = []
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_id,payload_json FROM events ORDER BY created_at DESC"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                continue
            if str(payload.get("action") or "handoff").lower() != "handoff":
                continue
            ids = [str(x) for x in (payload.get("visit_ids") or [])]
            if wanted not in ids:
                continue
            if patient and str(payload.get("reception_patient_id") or "") != patient:
                continue
            event_id = _clean(payload.get("event_id") or row["event_id"], 180)
            if event_id and event_id not in matches:
                matches.append(event_id)
    if not matches and patient:
        # Compatibilidad con atenciones de un solo Visit anteriores al puente
        # de cancelación.
        matches.append(_event_id(patient, [visit_id]))
    return matches


def _queue_control_action(
    action: str,
    *,
    visit_id: object,
    reception_patient_id: object = "",
) -> list[str]:
    targets = _attention_event_ids_for_visit(visit_id, reception_patient_id)
    if not targets:
        return []
    stamp = _now()
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        for target in targets:
            control_id = (
                f"{action}:"
                + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{action}:{target}:{visit_id}"))
            )
            payload = {
                "action": action,
                "target_event_id": target,
                "visit_id": str(visit_id),
                "reception_patient_id": str(reception_patient_id or ""),
                "created_at": stamp,
            }
            conn.execute(
                """
                INSERT INTO events(
                  event_id,payload_json,created_at,attempts,last_attempt_at,last_error,sent_at
                ) VALUES(?,?,?,0,NULL,'',NULL)
                ON CONFLICT(event_id) DO UPDATE SET
                  payload_json=excluded.payload_json,
                  created_at=excluded.created_at,
                  attempts=0,
                  last_attempt_at=NULL,
                  last_error='',
                  sent_at=NULL
                """,
                (
                    control_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    stamp,
                ),
            )
        conn.commit()
    flush_pending(background=True)
    return targets


def cancel_attention(
    *,
    visit_id: object,
    reception_patient_id: object = "",
) -> list[str]:
    return _queue_control_action(
        "cancel",
        visit_id=visit_id,
        reception_patient_id=reception_patient_id,
    )


def restore_attention(
    *,
    visit_id: object,
    reception_patient_id: object = "",
) -> list[str]:
    return _queue_control_action(
        "restore",
        visit_id=visit_id,
        reception_patient_id=reception_patient_id,
    )


def _parse_seen(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _doctor_presence() -> dict:
    if not _database_url():
        return {
            "cloud_reachable": False,
            "doctor_online": False,
            "doctor_last_seen": "",
            "doctor_device": "",
            "doctor_app_version": "",
            "cloud_waiting": 0,
        }
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT display_name,last_seen_at,app_version FROM devices "
            "WHERE last_seen_at IS NOT NULL ORDER BY last_seen_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM waiting_queue "
            "WHERE deleted_at IS NULL AND status IN ('waiting','in_consultation')"
        )
        waiting = int((cur.fetchone() or [0])[0] or 0)
        device = str(row[0] or "") if row else ""
        last_seen = str(row[1] or "") if row else ""
        app_version = str(row[2] or "") if row else ""
        seen = _parse_seen(last_seen)
        online = False
        age_seconds = None
        if seen is not None:
            try:
                now = datetime.now(seen.tzinfo) if seen.tzinfo else datetime.now()
                age_seconds = max(0, int((now - seen).total_seconds()))
                online = age_seconds <= 300
            except Exception:
                pass
        return {
            "cloud_reachable": True,
            "doctor_online": bool(online),
            "doctor_last_seen": last_seen,
            "doctor_last_seen_age_seconds": age_seconds,
            "doctor_device": device,
            "doctor_app_version": app_version,
            "cloud_waiting": waiting,
        }
    finally:
        try: cur.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass


def bridge_status() -> dict:
    _ensure_outbox()
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        pending = int(conn.execute("SELECT count(*) FROM events WHERE sent_at IS NULL").fetchone()[0])
        sent = int(conn.execute("SELECT count(*) FROM events WHERE sent_at IS NOT NULL").fetchone()[0])
    configured = bool(_database_url())
    if pending and configured:
        flush_pending(background=True)

    presence = {
        "cloud_reachable": False,
        "doctor_online": False,
        "doctor_last_seen": "",
        "doctor_last_seen_age_seconds": None,
        "doctor_device": "",
        "doctor_app_version": "",
        "cloud_waiting": 0,
    }
    if configured:
        try:
            presence.update(_doctor_presence())
        except Exception as exc:
            presence["presence_error"] = f"{type(exc).__name__}: {str(exc)}"[:300]

    return {
        "configured": configured,
        "pending": pending,
        "sent": sent,
        "flushing": bool(_FLUSHING),
        "last_error": _LAST_ERROR,
        "last_sent_at": _LAST_SENT_AT,
        **presence,
    }
