from __future__ import annotations

def normalize_public_base_url(value):
    return str(value or "").strip().rstrip("/")

def _legacy_disabled(*args, **kwargs):
    raise RuntimeError("Cloudflare Tunnel legado retirado de Recepción; Agenda 24/7 usa GitHub Pages + Neon.")

def start_quick_tunnel(*args, **kwargs):
    return _legacy_disabled(*args, **kwargs)

def start_named_tunnel(*args, **kwargs):
    return _legacy_disabled(*args, **kwargs)

def start_named_tunnel_background(*args, **kwargs):
    return None

def stop_managed_tunnel(*args, **kwargs):
    return {"running": False, "mode": "off"}

def tunnel_status(*args, **kwargs):
    return {
        "running": False,
        "mode": "off",
        "public_base_url": "",
        "cloudflared_ready": False,
        "downloading": False,
        "last_error": "",
    }
