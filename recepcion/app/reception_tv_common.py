from __future__ import annotations

import io
import ipaddress
import json
import math
import re
import socket
import struct
import time
import urllib.parse
import wave
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
try:
    APP_VERSION = str(json.loads((ROOT / "recepcion-version.json").read_text(encoding="utf-8-sig"))["version"]).strip()
except Exception:
    APP_VERSION = "0.0.0"
PORT = 8899
DATA_DIR = ROOT / "data" / "tv_turnos"
VIDEOS_DIR = DATA_DIR / "videos"
CONFIG_PATH = DATA_DIR / "config.json"
STATIC_DIR = ROOT / "static"
LOGO_FULL = STATIC_DIR / "doctor_full_logo.png"
LOGO_ICON = STATIC_DIR / "doctor_isotype.png"
DISPLAY_PATH = ROOT / "tv_display.html"
CONTROL_PATH = ROOT / "tv_control.html"
FIREWALL_RULE = "Dr Revelo Pantalla TV Turnos"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _epoch() -> float:
    return time.time()


def _clean_name(value: object) -> str:
    name = Path(str(value or "")).name.strip()
    name = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ ._()\-]", "_", name)
    return name[:180]


def _is_video_name(name: str) -> bool:
    return Path(name).suffix.lower() in {".mp4", ".webm", ".m4v"}


def _lan_ip() -> str:
    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
        for value in candidates:
            if value and not value.startswith("127.") and not value.startswith("169.254."):
                return value
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            value = sock.getsockname()[0]
            if value:
                return value
        finally:
            sock.close()
    except Exception:
        pass
    return "127.0.0.1"


def _allowed_lan(ip: str) -> bool:
    try:
        value = ipaddress.ip_address(ip)
        return bool(value.is_loopback or value.is_private)
    except Exception:
        return False


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except Exception:
        return False


def _ding_wav() -> bytes:
    sample_rate = 22050
    duration = 0.48
    frames = int(sample_rate * duration)
    buff = io.BytesIO()
    with wave.open(buff, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        data = bytearray()
        for i in range(frames):
            t = i / sample_rate
            envelope = min(1.0, t / 0.025) * max(0.0, 1.0 - t / duration) ** 1.8
            f1 = 880.0 if t < 0.22 else 1174.66
            value = 0.34 * envelope * math.sin(2 * math.pi * f1 * t)
            value += 0.10 * envelope * math.sin(2 * math.pi * (f1 * 1.5) * t)
            data.extend(struct.pack("<h", max(-32767, min(32767, int(value * 32767)))))
        wf.writeframes(bytes(data))
    return buff.getvalue()


_DING = _ding_wav()
