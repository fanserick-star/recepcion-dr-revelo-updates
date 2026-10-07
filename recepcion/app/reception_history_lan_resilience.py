from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import threading
import time

import historia_lan_transport as _lan

PATCH_VERSION = "4.6.36"
_SCAN_LOCK = threading.Lock()
_SCAN_COOLDOWN_SECONDS = 12.0
_LAST_SCAN_MONOTONIC = 0.0


_ORIGINAL_SEND_LAN = _lan.send_lan
_ORIGINAL_CONTROL_LAN = _lan._send_control_lan
_ORIGINAL_BRIDGE_STATUS = _lan.hybrid_bridge_status


def _is_private_ipv4(value: object) -> bool:
    try:
        ip = ipaddress.ip_address(str(value or "").strip())
        return bool(
            ip.version == 4
            and ip.is_private
            and not ip.is_loopback
            and not ip.is_link_local
            and not ip.is_multicast
        )
    except Exception:
        return False


def _local_ipv4s() -> list[str]:
    values: list[str] = []

    try:
        _name, _aliases, addresses = socket.gethostbyname_ex(socket.gethostname())
        values.extend(str(item) for item in addresses)
    except Exception:
        pass

    # UDP connect no envía datos; solo permite a Windows indicar qué interfaz
    # usaría para salir. Es útil cuando el nombre del equipo no resuelve a la
    # IPv4 real después de reiniciar router/PC.
    for destination in (("8.8.8.8", 53), ("1.1.1.1", 53), ("192.168.1.1", 9)):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(destination)
            values.append(str(sock.getsockname()[0]))
        except Exception:
            pass
        finally:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass

    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if _is_private_ipv4(value) and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _quick_hosts() -> list[str]:
    values: list[str] = []
    try:
        values.extend(_lan._candidate_hosts())
    except Exception:
        pass

    out: list[str] = []
    seen: set[str] = set()
    local = set(_local_ipv4s())
    for value in values:
        host = str(value or "").strip()
        if not host or host in seen or host in local:
            continue
        seen.add(host)
        out.append(host)
    return out[:48]


def _challenge_many(hosts: list[str], timeout: float, method: str) -> dict | None:
    hosts = [str(host) for host in hosts if str(host or "").strip()]
    if not hosts:
        return None

    workers = min(32, max(1, len(hosts)))
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="historia-discover")
    futures = [pool.submit(_lan._challenge, host, timeout) for host in hosts]
    try:
        for future in concurrent.futures.as_completed(futures):
            try:
                found = future.result()
            except Exception:
                found = None
            if found:
                found = dict(found)
                found["method"] = method
                for pending in futures:
                    if pending is not future:
                        pending.cancel()
                return found
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return None


def _subnet_hosts() -> list[str]:
    local_ips = _local_ipv4s()
    networks: list[ipaddress.IPv4Network] = []
    seen_networks: set[str] = set()

    # El consultorio usa /24. Si DHCP cambia el último octeto, este fallback
    # encuentra Historia sin depender de la tabla ARP ni de una IP guardada.
    for local_ip in local_ips:
        try:
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
        except Exception:
            continue
        key = str(network)
        if key in seen_networks:
            continue
        seen_networks.add(key)
        networks.append(network)
        if len(networks) >= 2:
            break

    local_set = set(local_ips)
    out: list[str] = []
    for network in networks:
        for host in network.hosts():
            value = str(host)
            if value not in local_set:
                out.append(value)
    return out


def _active_subnet_scan(*, force: bool = False) -> dict | None:
    global _LAST_SCAN_MONOTONIC

    if not _SCAN_LOCK.acquire(blocking=False):
        return None
    try:
        now = time.monotonic()
        if not force and now - _LAST_SCAN_MONOTONIC < _SCAN_COOLDOWN_SECONDS:
            return None
        _LAST_SCAN_MONOTONIC = now
        try:
            _lan._set_state(lan_last_scan_at=_lan._now())
        except Exception:
            pass
        return _challenge_many(_subnet_hosts(), 0.20, "subnet-scan")
    finally:
        _SCAN_LOCK.release()


def resilient_discover(force_subnet_scan: bool = False) -> dict | None:
    # 1) IP conocida, variable de entorno y vecinos ARP; en paralelo para que
    # una IP vieja no bloquee varios segundos el redescubrimiento.
    found = _challenge_many(_quick_hosts(), 0.24, "known-or-arp")
    if found:
        return found

    # 2) Descubrimiento UDP original de Historia.
    try:
        found = _lan._udp_discover(timeout=0.30)
    except Exception:
        found = None
    if found:
        found = dict(found)
        found["method"] = "udp-broadcast"
        return found

    # 3) Fallback activo: escanea solo la(s) subred(es) privadas locales /24.
    # Esto cubre el caso observado tras un corte de luz: DHCP asigna nuevas IP.
    return _active_subnet_scan(force=force_subnet_scan)


def resilient_probe_once(force_subnet_scan: bool = False) -> dict:
    found = resilient_discover(force_subnet_scan=force_subnet_scan)
    if not found:
        _lan._set_state(
            lan_online=False,
            lan_host="",
            lan_last_error="Historia no respondió en la red local; reintento automático activo",
            token="",
            token_host="",
            lan_discovery_method="none",
        )
        return _lan._snapshot()

    host = str(found["host"])
    version = str(found.get("version") or "")
    token = str(found.get("token") or "")
    method = str(found.get("method") or "auto")
    _lan._save_cache(host, version)
    _lan._set_state(
        lan_online=True,
        lan_host=host,
        lan_version=version,
        lan_last_seen=_lan._now(),
        lan_last_error="",
        lan_latency_ms=found.get("latency_ms"),
        token=token,
        token_host=host,
        lan_discovery_method=method,
    )
    return _lan._snapshot()


def resilient_send_lan(payload: dict) -> bool:
    # Primer intento normal. Si la IP cambió mientras figuraba online, el
    # transporte anterior fallaría una vez y esperaría al monitor. Aquí se
    # fuerza redescubrimiento inmediato y se reintenta el mismo handoff.
    if _ORIGINAL_SEND_LAN(payload):
        return True

    _lan._set_state(lan_online=False, token="", token_host="")
    state = resilient_probe_once(force_subnet_scan=True)
    if not state.get("lan_online"):
        return False
    return bool(_ORIGINAL_SEND_LAN(payload))


def resilient_control_lan(action: str, target_event_id: str, visit_id: object = "") -> bool:
    if _ORIGINAL_CONTROL_LAN(action, target_event_id, visit_id):
        return True

    _lan._set_state(lan_online=False, token="", token_host="")
    state = resilient_probe_once(force_subnet_scan=True)
    if not state.get("lan_online"):
        return False
    return bool(_ORIGINAL_CONTROL_LAN(action, target_event_id, visit_id))


def resilient_bridge_status() -> dict:
    state = dict(_ORIGINAL_BRIDGE_STATUS())
    snapshot = _lan._snapshot()
    state.update(
        {
            "lan_auto_recovery": True,
            "lan_active_subnet_scan": True,
            "lan_discovery_method": snapshot.get("lan_discovery_method") or "",
            "lan_last_scan_at": snapshot.get("lan_last_scan_at") or "",
            "lan_recovery_version": PATCH_VERSION,
            "lan_outbox_auto_resend": True,
        }
    )
    return state


def resilient_monitor_loop() -> None:
    while True:
        online = False
        try:
            state = resilient_probe_once(force_subnet_scan=False)
            online = bool(state.get("lan_online"))
            if online:
                _lan._flush_control_outbox()
                _lan._flush_lan_outbox()
        except Exception:
            pass
        # Caído: vuelve a buscar rápido. Conectado: conserva el sondeo liviano.
        time.sleep(6 if not online else 20)


def _install() -> None:
    if getattr(_lan, "_V4636_RESILIENCE_ACTIVE", False):
        return

    _lan.discover = resilient_discover
    _lan.probe_once = resilient_probe_once
    _lan.send_lan = resilient_send_lan
    _lan._send_control_lan = resilient_control_lan
    _lan.hybrid_bridge_status = resilient_bridge_status
    _lan._monitor_loop = resilient_monitor_loop
    _lan._V4636_RESILIENCE_ACTIVE = True

    # Si el transporte aún no estaba instalado, esto arranca directamente el
    # monitor reforzado. Si ya estaba instalado, sus wrappers consultan los
    # globals parcheados y siguen funcionando con el nuevo redescubrimiento.
    _lan.install()
    try:
        _lan._cloud.bridge_status = resilient_bridge_status
    except Exception:
        pass

_install()
PATCH_BOOT_OK = True
