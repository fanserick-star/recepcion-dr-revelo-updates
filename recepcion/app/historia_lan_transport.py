from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import historia_bridge as _cloud

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "historia_lan_cache.json"
LAN_OUTBOX_DB = ROOT / "data" / "historia_lan_outbox.db"
LAN_HTTP_PORT = 8765
LAN_DISCOVERY_PORT = 8766
DISCOVERY_MAGIC = b"HISTORIA_REVELO_DISCOVER_V1"
PRODUCT = "historia-clinica-dr-revelo"

_ORIGINAL_QUEUE = _cloud.queue_attention
_ORIGINAL_CANCEL = getattr(_cloud, "cancel_attention", None)
_ORIGINAL_RESTORE = getattr(_cloud, "restore_attention", None)
_ORIGINAL_STATUS = _cloud.bridge_status
_LOCK = threading.Lock()
_INSTALLED = False
_MONITOR_STARTED = False
_STATE = {
    "lan_online": False,
    "lan_host": "",
    "lan_version": "",
    "lan_last_seen": "",
    "lan_last_error": "",
    "lan_last_handoff_at": "",
    "lan_latency_ms": None,
    "token": "",
    "token_host": "",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _load_cache() -> dict:
    if not CACHE_PATH.is_file():
        return {}
    try:
        value = json.loads(CACHE_PATH.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_cache(host: str, version: str = "") -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".json.new")
        tmp.write_text(
            json.dumps(
                {"host": host, "version": version, "updated_at": _now()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, CACHE_PATH)
    except Exception:
        pass


def _http_json(host: str, path: str, *, method: str = "GET", payload=None, token: str = "", timeout: float = 0.8) -> dict:
    url = f"http://{host}:{LAN_HTTP_PORT}{path}"
    data = None
    headers = {"Accept": "application/json", "Cache-Control": "no-store"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Historia-LAN-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(65536)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Respuesta LAN inválida")
    return value


def _challenge(host: str, timeout: float = 0.55) -> dict | None:
    started = time.perf_counter()
    try:
        data = _http_json(host, "/challenge", timeout=timeout)
        if data.get("product") != PRODUCT or not data.get("token"):
            return None
        latency = int((time.perf_counter() - started) * 1000)
        return {
            "host": host,
            "token": str(data.get("token")),
            "version": str(data.get("version") or ""),
            "latency_ms": latency,
        }
    except Exception:
        return None


def _udp_discover(timeout: float = 0.35) -> dict | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.bind(("", 0))
        sock.sendto(DISCOVERY_MAGIC, ("255.255.255.255", LAN_DISCOVERY_PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict) or data.get("product") != PRODUCT or not data.get("token"):
                continue
            return {
                "host": str(addr[0]),
                "token": str(data.get("token")),
                "version": str(data.get("version") or ""),
                "latency_ms": None,
            }
    except Exception:
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _arp_candidates() -> list[str]:
    if os.name != "nt":
        return []
    try:
        out = subprocess.check_output(
            ["arp", "-a"],
            text=True,
            errors="ignore",
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return []
    result = []
    seen = set()
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?!\d)", out):
        ip = match.group(1)
        if ip.startswith("224.") or ip.startswith("239.") or ip.endswith(".255") or ip in seen:
            continue
        seen.add(ip)
        result.append(ip)
    return result[:40]


def _candidate_hosts() -> list[str]:
    values = []
    cache = _load_cache()
    if cache.get("host"):
        values.append(str(cache["host"]))

    env_host = str(os.getenv("HISTORIA_LAN_HOST") or "").strip()
    if env_host:
        values.append(env_host)

    # No consultamos Neon durante el sondeo LAN. Esto mantiene el monitor
    # local liviano y evita tráfico de nube cada pocos segundos.
    values.extend(_arp_candidates())

    out = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def discover() -> dict | None:
    for host in _candidate_hosts()[:12]:
        found = _challenge(host)
        if found:
            return found

    found = _udp_discover()
    if found:
        return found

    for host in _arp_candidates()[12:]:
        found = _challenge(host, timeout=0.25)
        if found:
            return found
    return None


def _set_state(**values) -> None:
    with _LOCK:
        _STATE.update(values)


def _snapshot() -> dict:
    with _LOCK:
        return dict(_STATE)


def probe_once() -> dict:
    found = discover()
    if not found:
        _set_state(
            lan_online=False,
            lan_last_error="Historia no respondió en la red local",
            token="",
            token_host="",
        )
        return _snapshot()

    host = str(found["host"])
    version = str(found.get("version") or "")
    token = str(found.get("token") or "")
    _save_cache(host, version)
    _set_state(
        lan_online=True,
        lan_host=host,
        lan_version=version,
        lan_last_seen=_now(),
        lan_last_error="",
        lan_latency_ms=found.get("latency_ms"),
        token=token,
        token_host=host,
    )
    return _snapshot()


def send_lan(payload: dict) -> bool:
    state = _snapshot()
    host = str(state.get("lan_host") or "")
    token = str(state.get("token") or "")
    if not host or not token or not state.get("lan_online"):
        state = probe_once()
        host = str(state.get("lan_host") or "")
        token = str(state.get("token") or "")
    if not host or not token:
        return False

    try:
        result = _http_json(
            host,
            "/handoff",
            method="POST",
            payload=payload,
            token=token,
            timeout=1.25,
        )
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or "Historia rechazó el turno"))
        _set_state(
            lan_online=True,
            lan_last_seen=_now(),
            lan_last_handoff_at=_now(),
            lan_last_error="",
        )
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            _set_state(token="", token_host="")
            fresh = probe_once()
            host = str(fresh.get("lan_host") or "")
            token = str(fresh.get("token") or "")
            if host and token:
                try:
                    result = _http_json(
                        host,
                        "/handoff",
                        method="POST",
                        payload=payload,
                        token=token,
                        timeout=1.25,
                    )
                    if result.get("ok"):
                        _set_state(
                            lan_online=True,
                            lan_last_seen=_now(),
                            lan_last_handoff_at=_now(),
                            lan_last_error="",
                        )
                        return True
                except Exception:
                    pass
        _set_state(lan_online=False, lan_last_error=f"HTTP {getattr(exc, 'code', '?')}")
        return False
    except Exception as exc:
        _set_state(lan_online=False, lan_last_error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return False














def _ensure_lan_outbox() -> None:
    """Create/migrate the local LAN outbox without touching clinical databases."""
    LAN_OUTBOX_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              sent_at TEXT,
              cancelled INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              control_action TEXT,
              control_visit_id TEXT,
              control_pending INTEGER NOT NULL DEFAULT 0,
              control_last_error TEXT,
              control_sent_at TEXT
            )
            """
        )
        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        migrations = (
            ("control_action", "TEXT"),
            ("control_visit_id", "TEXT"),
            ("control_pending", "INTEGER NOT NULL DEFAULT 0"),
            ("control_last_error", "TEXT"),
            ("control_sent_at", "TEXT"),
        )
        for name, ddl in migrations:
            if name not in cols:
                conn.execute(f"ALTER TABLE events ADD COLUMN {name} {ddl}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_historia_lan_control_pending "
            "ON events(control_pending,created_at)"
        )
        conn.commit()


def _lan_outbox_put(payload: dict) -> None:
    _ensure_lan_outbox()
    event_id = _clean(payload.get("event_id"), 180)
    if not event_id:
        raise ValueError("Falta event_id para la cola LAN")
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        conn.execute(
            """
            INSERT INTO events(event_id,payload_json,created_at,sent_at,cancelled,last_error)
            VALUES(?,?,?,NULL,0,NULL)
            ON CONFLICT(event_id) DO UPDATE SET
              payload_json=excluded.payload_json,
              sent_at=CASE WHEN events.cancelled=0 THEN NULL ELSE events.sent_at END,
              last_error=CASE WHEN events.cancelled=0 THEN NULL ELSE events.last_error END
            """,
            (event_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), _now()),
        )
        conn.commit()


def _lan_outbox_mark(event_id: str, *, sent: bool = False, error: str = "") -> None:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        if sent:
            conn.execute(
                "UPDATE events SET sent_at=?,last_error=NULL WHERE event_id=?",
                (_now(), str(event_id)),
            )
        else:
            conn.execute(
                "UPDATE events SET last_error=? WHERE event_id=?",
                (_clean(error, 240), str(event_id)),
            )
        conn.commit()


def _queue_control_intent(event_id: str, action: str, visit_id: object = "") -> None:
    """Persist the last exact cancel/restore intent until Historia confirms it."""
    _ensure_lan_outbox()
    action = str(action or "").strip().lower()
    if action not in {"cancel", "restore"}:
        raise ValueError("Acción LAN inválida")
    event_id = _clean(event_id, 180)
    if not event_id:
        raise ValueError("Falta event_id para control LAN")
    stamp = _now()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        row = conn.execute("SELECT event_id FROM events WHERE event_id=? LIMIT 1", (event_id,)).fetchone()
        if row:
            conn.execute(
                """UPDATE events
                   SET control_action=?,control_visit_id=?,control_pending=1,
                       control_last_error=NULL,control_sent_at=NULL
                   WHERE event_id=?""",
                (action, _clean(visit_id, 120), event_id),
            )
        else:
            conn.execute(
                """INSERT INTO events(
                     event_id,payload_json,created_at,sent_at,cancelled,last_error,
                     control_action,control_visit_id,control_pending,control_last_error,control_sent_at
                   ) VALUES(?,?,?,?,?,?,?,?,1,NULL,NULL)""",
                (
                    event_id, "{}", stamp, stamp,
                    1 if action == "cancel" else 0,
                    "control_only", action, _clean(visit_id, 120),
                ),
            )
        conn.commit()


def _mark_control_result(event_id: str, *, sent: bool, error: str = "") -> None:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        if sent:
            conn.execute(
                """UPDATE events SET control_pending=0,control_last_error=NULL,control_sent_at=?
                   WHERE event_id=?""",
                (_now(), str(event_id)),
            )
        else:
            conn.execute(
                """UPDATE events SET control_pending=1,control_last_error=?
                   WHERE event_id=?""",
                (_clean(error, 240), str(event_id)),
            )
        conn.commit()


def _lan_control_pending_count() -> int:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        return int(conn.execute(
            "SELECT COUNT(*) FROM events WHERE control_pending=1"
        ).fetchone()[0] or 0)


def _expire_stale_lan_outbox() -> int:
    """Do not deliver yesterday's waiting-room handoffs on a later day."""
    _ensure_lan_outbox()
    today = datetime.now().date().isoformat()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        cur = conn.execute(
            """
            UPDATE events
               SET cancelled=1,
                   last_error='expired_previous_day'
             WHERE sent_at IS NULL
               AND cancelled=0
               AND date(created_at) < date(?)
            """,
            (today,),
        )
        conn.commit()
        return max(0, int(cur.rowcount or 0))


def _lan_outbox_counts() -> tuple[int, int]:
    _expire_stale_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        pending = int(conn.execute(
            "SELECT COUNT(*) FROM events WHERE sent_at IS NULL AND cancelled=0"
        ).fetchone()[0] or 0)
        sent = int(conn.execute(
            "SELECT COUNT(*) FROM events WHERE sent_at IS NOT NULL"
        ).fetchone()[0] or 0)
    return pending, sent


def _cloud_link_id(reception_patient_id: object) -> str:
    """Reads only the verified patient link from Historia Neon."""
    try:
        import reception_history_identity_consolidated as identity
        import core_runtime as core
        cloud_reception_id = str(reception_patient_id)
        try:
            with core.LocalSessionLocal() as ldb:
                mapped = core.get_id_map(ldb, "patient", int(reception_patient_id))
                if mapped is not None:
                    cloud_reception_id = str(mapped)
        except Exception:
            pass
        conn = identity._connect_public()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT l.clinical_patient_id
                FROM public.patient_links l
                JOIN public.patients p ON p.id=l.clinical_patient_id
                WHERE l.reception_patient_id=%s
                  AND l.verified=1
                  AND l.deleted_at IS NULL AND p.deleted_at IS NULL
                LIMIT 1
                """,
                (cloud_reception_id,),
            )
            row = cur.fetchone()
            return _clean(row[0], 120) if row and row[0] else ""
        finally:
            conn.close()
    except Exception:
        return ""


def _flush_lan_outbox(max_items: int = 30) -> None:
    _expire_stale_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        rows = conn.execute(
            """
            SELECT event_id,payload_json
            FROM events
            WHERE sent_at IS NULL AND cancelled=0
            ORDER BY created_at
            LIMIT ?
            """,
            (max(1, int(max_items)),),
        ).fetchall()
    for event_id, payload_json in rows:
        try:
            payload = json.loads(payload_json)
            if send_lan(payload):
                _lan_outbox_mark(str(event_id), sent=True)
            else:
                _lan_outbox_mark(str(event_id), error=_snapshot().get("lan_last_error") or "Historia no disponible por LAN")
                break
        except Exception as exc:
            _lan_outbox_mark(str(event_id), error=f"{type(exc).__name__}: {str(exc)[:180]}")
            break


def _lan_event_targets(visit_id: object = "", reception_patient_id: object = "") -> list[str]:
    _ensure_lan_outbox()
    wanted_visit = str(visit_id or "").strip()
    wanted_patient = str(reception_patient_id or "").strip()
    found = []
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        rows = conn.execute("SELECT event_id,payload_json FROM events ORDER BY created_at DESC").fetchall()
    for event_id, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except Exception:
            continue
        visits = {str(x) for x in (payload.get("visit_ids") or []) if x is not None}
        same_visit = bool(wanted_visit and wanted_visit in visits)
        same_patient = bool(wanted_patient and str(payload.get("reception_patient_id") or "") == wanted_patient)
        if wanted_visit and wanted_patient:
            matches = same_visit and same_patient
        elif wanted_visit:
            matches = same_visit
        else:
            matches = same_patient
        if matches:
            found.append(str(event_id))
    return list(dict.fromkeys(found))


def _lan_set_cancelled(event_id: str, cancelled: bool) -> tuple[bool, dict | None]:
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        row = conn.execute(
            "SELECT sent_at,payload_json FROM events WHERE event_id=? LIMIT 1",
            (str(event_id),),
        ).fetchone()
        if not row:
            return False, None
        conn.execute(
            "UPDATE events SET cancelled=? WHERE event_id=?",
            (1 if cancelled else 0, str(event_id)),
        )
        conn.commit()
    try:
        payload = json.loads(row[1])
    except Exception:
        payload = None
    return bool(row[0]), payload

def _send_control_lan(action: str, target_event_id: str, visit_id: object = "") -> bool:
    state = _snapshot()
    host = str(state.get("lan_host") or "")
    token = str(state.get("token") or "")
    if not host or not token or not state.get("lan_online"):
        state = probe_once()
        host = str(state.get("lan_host") or "")
        token = str(state.get("token") or "")
    if not host or not token:
        return False

    path = "/cancel" if action == "cancel" else "/restore"
    data = {
        "action": action,
        "event_id": str(target_event_id),
        "target_event_id": str(target_event_id),
        "visit_id": str(visit_id or ""),
    }

    for attempt in range(2):
        try:
            result = _http_json(
                host,
                path,
                method="POST",
                payload=data,
                token=token,
                timeout=1.25,
            )
            if result.get("ok"):
                _set_state(
                    lan_online=True,
                    lan_last_seen=_now(),
                    lan_last_error="",
                )
                return True
            raise RuntimeError(str(result.get("error") or "Historia rechazó la acción"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and attempt == 0:
                _set_state(token="", token_host="")
                fresh = probe_once()
                host = str(fresh.get("lan_host") or "")
                token = str(fresh.get("token") or "")
                if host and token:
                    continue
            _set_state(lan_online=False, lan_last_error=f"HTTP {getattr(exc, 'code', '?')}")
            return False
        except Exception as exc:
            _set_state(lan_online=False, lan_last_error=f"{type(exc).__name__}: {str(exc)[:160]}")
            return False
    return False


def _flush_control_outbox(max_items: int = 30) -> None:
    """Retry exact cancel/restore commands independently from handoff delivery."""
    _ensure_lan_outbox()
    with sqlite3.connect(LAN_OUTBOX_DB, timeout=5) as conn:
        rows = conn.execute(
            """SELECT event_id,control_action,control_visit_id
               FROM events WHERE control_pending=1
               ORDER BY created_at LIMIT ?""",
            (max(1, int(max_items)),),
        ).fetchall()
    for event_id, action, visit_id in rows:
        action = str(action or "").strip().lower()
        if action not in {"cancel", "restore"}:
            _mark_control_result(str(event_id), sent=True)
            continue
        if _send_control_lan(action, str(event_id), visit_id or ""):
            _mark_control_result(str(event_id), sent=True)
            continue
        _mark_control_result(
            str(event_id), sent=False,
            error=_snapshot().get("lan_last_error") or "Historia no disponible por LAN",
        )
        break


def _hybrid_control(action: str, *, visit_id: object, reception_patient_id: object = "") -> list[str]:
    targets = _lan_event_targets(visit_id=visit_id, reception_patient_id=reception_patient_id)
    # Si se perdió el outbox local pero conocemos paciente+visita, el event_id es
    # determinista y seguro. Esto permite cancelar exactamente la fila de Historia
    # sin buscar por un visit_id reutilizable.
    if not targets and str(visit_id or "").strip() and str(reception_patient_id or "").strip():
        targets = [_cloud._event_id(reception_patient_id, [visit_id])]
    for target in targets:
        was_sent, payload = _lan_set_cancelled(target, action == "cancel")
        if was_sent or payload is None:
            _queue_control_intent(target, action, visit_id)
            threading.Thread(
                target=_flush_control_outbox,
                daemon=True,
                name=f"historia-lan-{action}-retry",
            ).start()
        elif action == "restore" and payload:
            threading.Thread(
                target=_flush_lan_outbox,
                daemon=True,
                name="historia-lan-restore-pending",
            ).start()
    return targets


def hybrid_cancel_attention(*, visit_id: object, reception_patient_id: object = "") -> list[str]:
    return _hybrid_control(
        "cancel",
        visit_id=visit_id,
        reception_patient_id=reception_patient_id,
    )


def hybrid_restore_attention(*, visit_id: object, reception_patient_id: object = "") -> list[str]:
    return _hybrid_control(
        "restore",
        visit_id=visit_id,
        reception_patient_id=reception_patient_id,
    )


def hybrid_bridge_status() -> dict:
    lan = _snapshot()
    try:
        handoff_pending, sent = _lan_outbox_counts()
        control_pending = _lan_control_pending_count()
    except Exception:
        handoff_pending, sent, control_pending = 0, 0, 0
    return {
        "configured": True,
        "pending": handoff_pending + control_pending,
        "handoff_pending": handoff_pending,
        "control_pending": control_pending,
        "sent": sent,
        "cloud_reachable": False,
        "doctor_online": bool(lan.get("lan_online")),
        "last_error": lan.get("lan_last_error") or "",
        "lan_online": bool(lan.get("lan_online")),
        "lan_host": lan.get("lan_host") or "",
        "lan_version": lan.get("lan_version") or "",
        "lan_last_seen": lan.get("lan_last_seen") or "",
        "lan_last_handoff_at": lan.get("lan_last_handoff_at") or "",
        "lan_latency_ms": lan.get("lan_latency_ms"),
        "transport": "lan" if lan.get("lan_online") else "local",
        "waiting_queue_transport": "lan_only",
    }


def _monitor_loop():
    while True:
        online = False
        try:
            state = probe_once()
            online = bool(state.get("lan_online"))
            if online:
                _flush_control_outbox()
                _flush_lan_outbox()
        except Exception:
            pass
        time.sleep(6 if not online else 20)


def install(historia_bridge_module=None) -> None:
    global _INSTALLED, _MONITOR_STARTED
    if _INSTALLED:
        return
    _INSTALLED = True
    target = historia_bridge_module or _cloud
    target.queue_attention = hybrid_queue_attention
    if _ORIGINAL_CANCEL is not None:
        target.cancel_attention = hybrid_cancel_attention
    if _ORIGINAL_RESTORE is not None:
        target.restore_attention = hybrid_restore_attention
    target.bridge_status = hybrid_bridge_status
    if not _MONITOR_STARTED:
        _MONITOR_STARTED = True
        threading.Thread(
            target=_monitor_loop,
            daemon=True,
            name="historia-lan-monitor",
        ).start()


# v4.5.24 — propaga datos administrativos del paciente por LAN.
def _payload(event_id: str, reception_patient_id: object, display_name: object,
             identification: object, attention_type: object, visit_ids,
             birth_date: object = "", phone: object = "",
             email: object = "", address: object = "",
             patient_status: object = "", reception_turn: object = None) -> dict:
    return {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "patient_status": _clean(patient_status, 40),
        "reception_turn": int(reception_turn) if reception_turn not in (None, "") else None,
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "birth_date": _clean(birth_date, 20),
        "phone": _clean(phone, 80),
        "email": _clean(email, 180),
        "address": _clean(address, 360),
        "queued_at": _now(),
    }

def hybrid_queue_attention(*, reception_patient_id: object, display_name: object,
                           identification: object = "", attention_type: object = "Consulta",
                           patient_status: object = "", reception_turn: object = None,
                           visit_ids: list[object] | None = None,
                           birth_date: object = "", phone: object = "",
                           email: object = "", address: object = "",
                           clinical_patient_id: object = "") -> str:
    label = _clean(attention_type, 180).upper()
    is_procedure = label == "PROCEDIMIENTO" or label.startswith("PROCEDIMIENTO ")
    event_id = _cloud._event_id(reception_patient_id, visit_ids)
    payload = {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        # Exam reviews pass a chart ID already checked against the verified
        # Historia link. Regular consultations keep their existing resolver.
        "clinical_patient_id": _clean(clinical_patient_id, 120) or _cloud_link_id(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "patient_status": _clean(patient_status, 40),
        "reception_turn": None if is_procedure else reception_turn,
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "birth_date": _clean(birth_date, 40),
        "phone": _clean(phone, 120),
        "email": _clean(email, 180),
        "address": _clean(address, 360),
        "queued_at": _now(),
    }
    _lan_outbox_put(payload)
    if send_lan(payload):
        _lan_outbox_mark(event_id, sent=True)
    else:
        _lan_outbox_mark(event_id, error=_snapshot().get("lan_last_error") or "Pendiente de entrega LAN")
    return event_id
