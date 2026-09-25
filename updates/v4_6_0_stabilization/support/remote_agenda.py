from __future__ import annotations

"""Compatibilidad mínima del antiguo Cloudflare Tunnel.

Recepción 4.6.0 usa Agenda Cloud (GitHub Pages + Neon). Este módulo existe
únicamente para que el runtime histórico pueda importarse sin arrancar ni
instalar cloudflared.
"""

from urllib.parse import urlparse


class RemoteAgendaRetired(RuntimeError):
    pass


def normalize_public_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("La URL pública debe ser HTTPS")
    return raw


def _retired(*_args, **_kwargs):
    raise RemoteAgendaRetired(
        "Cloudflare Tunnel fue retirado. La Agenda vigente usa GitHub Pages + Neon."
    )


def start_quick_tunnel(*args, **kwargs):
    return _retired(*args, **kwargs)


def start_named_tunnel(*args, **kwargs):
    return _retired(*args, **kwargs)


def start_named_tunnel_background(*args, **kwargs):
    return _retired(*args, **kwargs)


def stop_managed_tunnel(_data_dir=None):
    # No hay proceso que administrar en 4.6.0.
    return {"ok": True, "running": False, "mode": "retired"}


def tunnel_status(_data_dir=None):
    return {
        "running": False,
        "mode": "retired",
        "public_base_url": "",
        "active_base_url": "",
        "cloudflared_ready": False,
        "downloading": False,
        "last_error": "",
    }
