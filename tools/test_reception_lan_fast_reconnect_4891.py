"""v4.8.91 — LAN fiable: el indicador no espera a Neon ni a la cola de turnos."""
from __future__ import annotations

import ast
import inspect
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recepcion/app"))
import historia_lan_transport as lan
import reception_history_lan_resilience as resilience


def check_fast_cached_connection_without_arp():
    orig_challenge = lan._challenge
    orig_cache = lan._load_cache
    orig_snap = lan._snapshot
    orig_env = lan.os.getenv
    orig_quick = resilience._quick_hosts
    called = []
    try:
        lan._load_cache = lambda: {"host": "192.168.1.24"}
        lan._snapshot = lambda: {"lan_host": ""}
        lan.os.getenv = lambda k, *a: "" if k == "HISTORIA_LAN_HOST" else orig_env(k, *a)
        def check(host, timeout=0.55):
            called.append((host, timeout))
            return {"host": host, "token": "test", "version": "1.0"} if host == "192.168.1.24" else None
        lan._challenge = check
        resilience._quick_hosts = lambda: (_ for _ in ()).throw(AssertionError("ARP no debe bloquear IP conocida"))
        out = resilience.resilient_discover()
        assert out["host"] == "192.168.1.24" and out["method"] == "cached-direct"
        assert called == [("192.168.1.24", 0.40)]
    finally:
        lan._challenge = orig_challenge
        lan._load_cache = orig_cache
        lan._snapshot = orig_snap
        lan.os.getenv = orig_env
        resilience._quick_hosts = orig_quick


def check_monitor_never_waits_for_neon():
    original_probe = resilience.resilient_probe_once
    original_sleep = resilience.time.sleep
    original_flush = lan._flush_lan_outbox
    original_control = lan._flush_control_outbox
    original_wake = lan._DELIVERY_WAKE
    calls = []
    class Stop(Exception): pass
    class Wake:
        def set(self):
            calls.append("wake")
    try:
        resilience.resilient_probe_once = lambda force_subnet_scan=False: {"lan_online": True}
        resilience.time.sleep = lambda secs: (_ for _ in ()).throw(Stop(secs))
        lan._flush_lan_outbox = lambda *a,**k: (_ for _ in ()).throw(AssertionError("El monitor no envía turnos"))
        lan._flush_control_outbox = lambda *a,**k: (_ for _ in ()).throw(AssertionError("El monitor no envía controles"))
        lan._DELIVERY_WAKE = Wake()
        try:
            resilience.resilient_monitor_loop()
        except Stop as e:
            assert e.args == (8,)
        else:
            raise AssertionError("El monitor debe seguir comprobando por intervalos")
        assert calls == ["wake"]
    finally:
        resilience.resilient_probe_once = original_probe
        resilience.time.sleep = original_sleep
        lan._flush_lan_outbox = original_flush
        lan._flush_control_outbox = original_control
        lan._DELIVERY_WAKE = original_wake


def check_delivery_worker_and_badge():
    original_snap = lan._snapshot
    original_handoff = lan._flush_lan_outbox
    original_control = lan._flush_control_outbox
    original_wake = lan._DELIVERY_WAKE
    calls = []
    class Stop(Exception): pass
    class FakeWake:
        def wait(self, timeout):
            assert timeout == 45
        def clear(self):
            pass
    try:
        lan._snapshot = lambda: {"lan_online": True}
        lan._flush_control_outbox = lambda: calls.append("control")
        def handoff():
            calls.append("handoff")
            raise Stop()
        lan._flush_lan_outbox = handoff
        lan._DELIVERY_WAKE = FakeWake()
        try:
            resilience.resilient_delivery_loop()
        except Stop:
            pass
        assert calls == ["control","handoff"]
    finally:
        lan._snapshot = original_snap
        lan._flush_control_outbox = original_control
        lan._flush_lan_outbox = original_handoff
        lan._DELIVERY_WAKE = original_wake

    source = (ROOT / "recepcion/app/reception_history_transport.py").read_text(encoding="utf-8")
    assert "setInterval(refresh,5000);" in source
    assert "let fetching=false;" in source
    assert "finally{fetching=false}" in source
    assert "/api/historia-bridge/status" in source
    assert "window.__historyLanStatus" in source
    app = (ROOT / "recepcion/app/app.py").read_text(encoding="utf-8")
    assert "RUNTIME_CONSOLIDATED = True" in app
    version = (ROOT / "recepcion/app/recepcion-version.json").read_text(encoding="utf-8")
    assert '"4.8.91"' in version


if __name__ == "__main__":
    check_fast_cached_connection_without_arp()
    check_monitor_never_waits_for_neon()
    check_delivery_worker_and_badge()
    print("RECEPTION_LAN_FAST_RECONNECT_4891_OK")
