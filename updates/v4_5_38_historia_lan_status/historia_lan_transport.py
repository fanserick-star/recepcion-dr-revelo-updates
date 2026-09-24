from __future__ import annotations

import json
import os
import re
import socket
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


def _payload(event_id: str, reception_patient_id: object, display_name: object, identification: object, attention_type: object, visit_ids) -> dict:
    return {
        "event_id": event_id,
        "reception_patient_id": str(reception_patient_id),
        "display_name": _clean(display_name, 260) or "Paciente",
        "identification": _clean(identification, 120),
        "attention_type": _clean(attention_type, 180) or "Consulta",
        "visit_ids": [str(x) for x in (visit_ids or []) if x is not None],
        "queued_at": _now(),
    }


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


def _hybrid_control(action: str, *, visit_id: object, reception_patient_id: object = "") -> list[str]:
    original = _ORIGINAL_CANCEL if action == "cancel" else _ORIGINAL_RESTORE
    if original is None:
        return []
    targets = list(original(
        visit_id=visit_id,
        reception_patient_id=reception_patient_id,
    ) or [])
    for target in targets:
        threading.Thread(
            target=_send_control_lan,
            args=(action, str(target), visit_id),
            daemon=True,
            name=f"historia-lan-{action}",
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


def hybrid_queue_attention(*, reception_patient_id: object, display_name: object,
                           identification: object = "", attention_type: object = "Consulta",
                           visit_ids: list[object] | None = None) -> str:
    event_id = _ORIGINAL_QUEUE(
        reception_patient_id=reception_patient_id,
        display_name=display_name,
        identification=identification,
        attention_type=attention_type,
        visit_ids=visit_ids,
    )

    data = _payload(event_id, reception_patient_id, display_name, identification, attention_type, visit_ids)

    threading.Thread(
        target=send_lan,
        args=(data,),
        daemon=True,
        name="historia-lan-handoff",
    ).start()
    return event_id


def hybrid_bridge_status() -> dict:
    try:
        cloud = _ORIGINAL_STATUS()
    except Exception as exc:
        cloud = {
            "configured": False,
            "pending": 0,
            "sent": 0,
            "cloud_reachable": False,
            "doctor_online": False,
            "last_error": f"{type(exc).__name__}: {str(exc)[:180]}",
        }
    lan = _snapshot()
    return {
        **cloud,
        "lan_online": bool(lan.get("lan_online")),
        "lan_host": lan.get("lan_host") or "",
        "lan_version": lan.get("lan_version") or "",
        "lan_last_seen": lan.get("lan_last_seen") or "",
        "lan_last_handoff_at": lan.get("lan_last_handoff_at") or "",
        "lan_last_error": lan.get("lan_last_error") or "",
        "lan_latency_ms": lan.get("lan_latency_ms"),
        "transport": "lan" if lan.get("lan_online") else ("cloud" if cloud.get("cloud_reachable") else "local"),
    }


def _monitor_loop():
    while True:
        try:
            probe_once()
        except Exception:
            pass
        time.sleep(7)


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
             patient_status: object = "") -> dict:
    return {
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

def hybrid_queue_attention(*, reception_patient_id: object, display_name: object,
                           identification: object = "", attention_type: object = "Consulta",
                           patient_status: object = "",
                           visit_ids: list[object] | None = None,
                           birth_date: object = "", phone: object = "",
                           email: object = "", address: object = "") -> str:
    event_id = _ORIGINAL_QUEUE(
        reception_patient_id=reception_patient_id,
        display_name=display_name,
        identification=identification,
        attention_type=attention_type,
        patient_status=patient_status,
        visit_ids=visit_ids,
        birth_date=birth_date,
        phone=phone,
        email=email,
        address=address,
    )
    data = _payload(
        event_id, reception_patient_id, display_name, identification,
        attention_type, visit_ids, birth_date, phone, email, address, patient_status,
    )
    threading.Thread(
        target=send_lan,
        args=(data,),
        daemon=True,
        name="historia-lan-handoff",
    ).start()
    return event_id
