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
_LAST_STATUS_RETRY_MONOTONIC = 0.0
_STATUS_RETRY_SECONDS = 60.0


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
    env = _read_env_file()
    return _clean(
        os.getenv(ENV_KEY)
        or env.get(ENV_KEY)
        or os.getenv("DATABASE_URL")
        or env.get("DATABASE_URL"),
        4000,
    )


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


def _ensure_remote_bridge_schema(conn) -> None:
    """Deja listo solo lo mínimo que necesita el puente.

    Es aditivo: crea/agrega tablas, columnas e índices faltantes. No elimina,
    renombra ni reescribe datos clínicos.
    """
    cur = conn.cursor()
    try:
        cur.execute('CREATE SCHEMA IF NOT EXISTS "historia"')
        cur.execute('SET search_path TO "historia", public')

        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients(
              id text PRIMARY KEY
            )
        """)
        for col, typ in (
            ("legacy_patient_id","text"),("name","text"),("name_search","text"),
            ("birth_date","text"),("address","text"),("phone","text"),
            ("national_id","text"),("national_id_search","text"),("email","text"),
            ("source","text"),("source_record_hash","text"),
            ("created_at","text"),("updated_at","text"),
            ("deleted_at","timestamptz"),
            ("cloud_updated_at","timestamptz NOT NULL DEFAULT now()")
        ):
            cur.execute(f'ALTER TABLE patients ADD COLUMN IF NOT EXISTS "{col}" {typ}')

        cur.execute("""
            CREATE TABLE IF NOT EXISTS patient_links(
              reception_patient_id text PRIMARY KEY
            )
        """)
        for col, typ in (
            ("clinical_patient_id","text"),("matched_by","text"),("verified","bigint"),
            ("verified_at","text"),("created_at","text"),("updated_at","text"),
            ("deleted_at","timestamptz"),
            ("cloud_updated_at","timestamptz NOT NULL DEFAULT now()")
        ):
            cur.execute(f'ALTER TABLE patient_links ADD COLUMN IF NOT EXISTS "{col}" {typ}')

        cur.execute("""
            CREATE TABLE IF NOT EXISTS waiting_queue(
              id text PRIMARY KEY
            )
        """)
        for col, typ in (
            ("reception_event_id","text"),("reception_patient_id","text"),
            ("clinical_patient_id","text"),("display_name","text"),
            ("identification","text"),("attention_type","text"),
            ("patient_status","text"),("reception_turn","bigint"),
            ("queued_at","text"),("status","text"),("source","text"),
            ("created_at","text"),("updated_at","text"),
            ("deleted_at","timestamptz"),
            ("cloud_updated_at","timestamptz NOT NULL DEFAULT now()")
        ):
            cur.execute(f'ALTER TABLE waiting_queue ADD COLUMN IF NOT EXISTS "{col}" {typ}')

        # El puente hace UPSERT por reception_event_id. La nube creada desde
        # SQLite conservaba el PK, pero no esta restricción UNIQUE.
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS historia_bridge_waiting_event_uidx "
            "ON waiting_queue(reception_event_id) WHERE reception_event_id IS NOT NULL"
        )
        conn.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _connect():
    url = _database_url()
    if not url:
        raise RuntimeError("Puente no configurado: falta HISTORIA_DATABASE_URL o DATABASE_URL")
    cfg = _parse_pg_url(url)
    if not cfg["user"] or not cfg["password"] or not cfg["host"]:
        raise RuntimeError("La conexión PostgreSQL de Historia está incompleta")
    from pg8000 import dbapi
    conn = dbapi.connect(
        user=cfg["user"], password=cfg["password"], host=cfg["host"],
        port=cfg["port"], database=cfg["database"],
        ssl_context=ssl.create_default_context(), timeout=12,
    )
    _ensure_remote_bridge_schema(conn)
    return conn


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

    # Recepción puede abrir antes de que Historia haya sembrado patients.
    # Eso no debe bloquear el turno: se envía sin vínculo y el doctor lo
    # vincula/crea desde Historia cuando corresponda.
    cur.execute("SELECT to_regclass('historia.patients')")
    if not (cur.fetchone() or [None])[0]:
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
          updated_at=EXCLUDED.updated_at, deleted_at=NULL,
          cloud_updated_at=now()
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
                    SET status='cancelled',updated_at=%s,cloud_updated_at=now()
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
                    SET status='waiting',updated_at=%s,deleted_at=NULL,cloud_updated_at=now()
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
        patient_status = _clean(payload.get("patient_status"), 40)
        try:
            reception_turn = int(payload.get("reception_turn")) if payload.get("reception_turn") not in (None, "") else None
        except Exception:
            reception_turn = None
        cur.execute(
            """
            INSERT INTO waiting_queue(
              id,reception_event_id,reception_patient_id,clinical_patient_id,
              display_name,identification,attention_type,patient_status,reception_turn,queued_at,status,source,created_at,updated_at
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'waiting','reception',%s,%s)
            ON CONFLICT(reception_event_id) DO UPDATE SET
              reception_patient_id=EXCLUDED.reception_patient_id,
              clinical_patient_id=COALESCE(waiting_queue.clinical_patient_id,EXCLUDED.clinical_patient_id),
              display_name=EXCLUDED.display_name,
              identification=EXCLUDED.identification,
              attention_type=EXCLUDED.attention_type,
              patient_status=EXCLUDED.patient_status,
              reception_turn=EXCLUDED.reception_turn,
              updated_at=EXCLUDED.updated_at,
              deleted_at=NULL,
              cloud_updated_at=now()
            """,
            (queue_id, event_id, reception_patient_id, clinical_id, display_name,
             identification or None, attention_type, patient_status or None, reception_turn, queued_at, now, now),
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
                    patient_status: object = "", reception_turn: object = None,
                    visit_ids: list[object] | None = None,
                    birth_date: object = "", phone: object = "",
                    email: object = "", address: object = "") -> str:
    _ensure_outbox()
    event_id = _event_id(reception_patient_id, visit_ids)
    payload = {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "patient_status": _clean(patient_status, 40),
        "reception_turn": int(reception_turn) if reception_turn not in (None, "") else None,
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "birth_date": _clean(birth_date, 40),
        "phone": _clean(phone, 120),
        "email": _clean(email, 180),
        "address": _clean(address, 400),
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
    global _LAST_STATUS_RETRY_MONOTONIC
    _ensure_outbox()
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        pending = int(conn.execute("SELECT count(*) FROM events WHERE sent_at IS NULL").fetchone()[0])
        sent = int(conn.execute("SELECT count(*) FROM events WHERE sent_at IS NOT NULL").fetchone()[0])
    configured = bool(_database_url())
    now_mono = time.monotonic()
    if (
        pending and configured and not _FLUSHING
        and now_mono - _LAST_STATUS_RETRY_MONOTONIC >= _STATUS_RETRY_SECONDS
    ):
        _LAST_STATUS_RETRY_MONOTONIC = now_mono
        flush_pending(max_items=100, background=True)

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


# v4.5.24 — datos administrativos mínimos para paciente NUEVO.
_v4524_send_payload_original = _send_payload

def _v4524_is_new_attention(value: object) -> bool:
    return _clean(value, 40).upper() in {"N", "NUEVO"}


def _v4537_is_new_payload(payload: dict) -> bool:
    status = _clean(payload.get("patient_status"), 40)
    if status:
        return _v4524_is_new_attention(status)
    # Compatibilidad con eventos guardados antes de separar estado/tipo.
    return _v4524_is_new_attention(payload.get("attention_type"))

def _v4524_patient_id(reception_patient_id: object) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "historia-reception-patient:" + str(reception_patient_id or "").strip(),
    ))

def _v4524_ensure_cloud_new_patient(conn, payload: dict) -> str:
    if not _v4537_is_new_payload(payload):
        return ""

    reception_patient_id = _clean(payload.get("reception_patient_id"), 120)
    name = re.sub(r"\s+", " ", _clean(payload.get("display_name"), 260)).strip().upper()
    if not reception_patient_id or not name:
        return ""

    identification = _clean(payload.get("identification"), 120)
    ident_search = _normalize_id(identification)
    birth_date = _clean(payload.get("birth_date"), 20)
    phone = _clean(payload.get("phone"), 80)
    email = _clean(payload.get("email"), 180).lower()
    address = _clean(payload.get("address"), 360)
    stamp = _now()

    cur = conn.cursor()
    try:
        cur.execute(
            """SELECT clinical_patient_id,matched_by
               FROM patient_links
               WHERE reception_patient_id=%s AND deleted_at IS NULL
               LIMIT 1""",
            (reception_patient_id,),
        )
        link = cur.fetchone()
        patient_id = str(link[0] or "").strip() if link else ""

        if not patient_id and ident_search:
            cur.execute(
                """SELECT id FROM patients
                   WHERE national_id_search=%s AND deleted_at IS NULL
                   LIMIT 2""",
                (ident_search,),
            )
            exact = cur.fetchall() or []
            if len(exact) == 1:
                patient_id = str(exact[0][0])

        if not patient_id:
            patient_id = _v4524_patient_id(reception_patient_id)

        source_hash = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "historia-reception-demographics:" + reception_patient_id,
        ).hex
        name_search = re.sub(r"\s+", " ", name.upper())

        cur.execute(
            """
            INSERT INTO patients(
              id,legacy_patient_id,name,name_search,birth_date,address,phone,
              national_id,national_id_search,email,source,source_record_hash,
              created_at,updated_at
            ) VALUES(%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,'reception_new',%s,%s,%s)
            ON CONFLICT(id) DO UPDATE SET
              name=CASE WHEN COALESCE(TRIM(patients.name),'')='' THEN EXCLUDED.name ELSE patients.name END,
              name_search=CASE WHEN COALESCE(TRIM(patients.name_search),'')='' THEN EXCLUDED.name_search ELSE patients.name_search END,
              birth_date=COALESCE(patients.birth_date,EXCLUDED.birth_date),
              address=CASE WHEN COALESCE(TRIM(patients.address),'')='' THEN EXCLUDED.address ELSE patients.address END,
              phone=CASE WHEN COALESCE(TRIM(patients.phone),'')='' THEN EXCLUDED.phone ELSE patients.phone END,
              national_id=CASE WHEN COALESCE(TRIM(patients.national_id),'')='' THEN EXCLUDED.national_id ELSE patients.national_id END,
              national_id_search=CASE WHEN COALESCE(TRIM(patients.national_id_search),'')='' THEN EXCLUDED.national_id_search ELSE patients.national_id_search END,
              email=CASE WHEN COALESCE(TRIM(patients.email),'')='' THEN EXCLUDED.email ELSE patients.email END,
              updated_at=EXCLUDED.updated_at,
              deleted_at=NULL,
              cloud_updated_at=now()
            """,
            (
                patient_id, name, name_search, birth_date or None, address or None,
                phone or None, identification or None,
                ident_search if identification else "", email or None,
                source_hash, stamp, stamp,
            ),
        )

        cur.execute(
            """
            INSERT INTO patient_links(
              reception_patient_id,clinical_patient_id,matched_by,verified,
              verified_at,created_at,updated_at,deleted_at
            ) VALUES(%s,%s,'cloud_new_demographics',1,%s,%s,%s,NULL)
            ON CONFLICT(reception_patient_id) DO UPDATE SET
              clinical_patient_id=EXCLUDED.clinical_patient_id,
              matched_by=CASE
                WHEN patient_links.matched_by='doctor_confirmed_new'
                THEN patient_links.matched_by
                ELSE EXCLUDED.matched_by
              END,
              verified=1,
              verified_at=EXCLUDED.verified_at,
              updated_at=EXCLUDED.updated_at,
              deleted_at=NULL,
              cloud_updated_at=now()
            """,
            (reception_patient_id, patient_id, stamp, stamp, stamp),
        )
        return patient_id
    finally:
        try:
            cur.close()
        except Exception:
            pass

def _send_payload(conn, payload: dict) -> None:
    if str(payload.get("action") or "handoff").strip().lower() == "handoff":
        _v4524_ensure_cloud_new_patient(conn, payload)
    return _v4524_send_payload_original(conn, payload)

def queue_attention(*, reception_patient_id: object, display_name: object,
                    identification: object = "", attention_type: object = "Consulta",
                    patient_status: object = "",
                    visit_ids: list[object] | None = None,
                    birth_date: object = "", phone: object = "",
                    email: object = "", address: object = "") -> str:
    _ensure_outbox()
    event_id = _event_id(reception_patient_id, visit_ids)
    payload = {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "patient_status": _clean(patient_status, 40),
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "birth_date": _clean(birth_date, 20),
        "phone": _clean(phone, 80),
        "email": _clean(email, 180),
        "address": _clean(address, 360),
        "queued_at": _now(),
    }
    with sqlite3.connect(OUTBOX_DB, timeout=5) as conn:
        conn.execute(
            """
            INSERT INTO events(event_id,payload_json,created_at)
            VALUES(?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET
              payload_json=excluded.payload_json,
              sent_at=NULL,
              attempts=0,
              last_attempt_at=NULL,
              last_error=''
            """,
            (
                event_id,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                _now(),
            ),
        )
        conn.commit()
    flush_pending(background=True)
    return event_id
