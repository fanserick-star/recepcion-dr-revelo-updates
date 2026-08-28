from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_STATE = "remote_agenda_state.json"
_LOG = "cloudflared.log"
_LOCK = threading.Lock()


def normalize_public_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    p = urlsplit(raw)
    if p.scheme.lower() != "https" or not p.netloc:
        raise ValueError("El enlace público debe ser HTTPS")
    return urlunsplit(("https", p.netloc, p.path.rstrip("/"), "", "")).rstrip("/")


def _paths(data_dir: str | os.PathLike):
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d, d / _STATE, d / _LOG


def _binary() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "tools" / "cloudflared.exe",
        here / "cloudflared.exe",
        Path(os.environ.get("CLOUDFLARED_EXE", "")) if os.environ.get("CLOUDFLARED_EXE") else None,
    ]
    for p in candidates:
        if p and p.is_file():
            return p
    raise FileNotFoundError("No se encontró cloudflared.exe")


def _load(state: Path) -> dict:
    try:
        value = json.loads(state.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save(state: Path, data: dict) -> None:
    tmp = state.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, state)


def _pid_running(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, timeout=4, creationflags=flags)
            return str(int(pid)) in (r.stdout or "")
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def stop_managed_tunnel(data_dir: str | os.PathLike) -> dict:
    d, state_path, _ = _paths(data_dir)
    del d
    with _LOCK:
        info = _load(state_path)
        pid = int(info.get("pid") or 0)
        if pid and _pid_running(pid):
            try:
                if os.name == "nt":
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=6, creationflags=flags)
                else:
                    os.kill(pid, 15)
            except Exception:
                pass
        try:
            state_path.unlink(missing_ok=True)
        except Exception:
            pass
    return {"running": False, "mode": "off"}


def _spawn(data_dir: str | os.PathLike, command: list[str], mode: str, public_base_url: str = "") -> dict:
    d, state_path, log_path = _paths(data_dir)
    stop_managed_tunnel(d)
    exe = _binary()
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    fh = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen([str(exe), *command], cwd=str(exe.parent), stdin=subprocess.DEVNULL,
                            stdout=fh, stderr=subprocess.STDOUT, creationflags=flags, close_fds=True)
    info = {
        "pid": proc.pid,
        "mode": mode,
        "public_base_url": public_base_url,
        "started_at": time.time(),
        "last_error": "",
    }
    _save(state_path, info)
    return info


def _quick_url(log_path: Path) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    hits = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text, flags=re.I)
    return hits[-1].rstrip("/") if hits else ""


def start_quick_tunnel(data_dir: str | os.PathLike, origin: str = "http://127.0.0.1:8000",
                       wait_seconds: float = 18.0) -> dict:
    origin = str(origin or "").strip()
    if not origin.startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("El origen del túnel rápido debe ser local")
    info = _spawn(data_dir, ["tunnel", "--no-autoupdate", "--url", origin], "quick")
    _, state_path, log_path = _paths(data_dir)
    deadline = time.time() + max(1.0, float(wait_seconds))
    while time.time() < deadline:
        url = _quick_url(log_path)
        if url:
            info["public_base_url"] = url
            _save(state_path, info)
            return tunnel_status(data_dir)
        if not _pid_running(int(info.get("pid") or 0)):
            break
        time.sleep(0.4)
    return tunnel_status(data_dir)


def start_named_tunnel(data_dir: str | os.PathLike, token: str, public_base_url: str) -> dict:
    token = str(token or "").strip()
    if not token:
        raise ValueError("Falta el token del túnel estable")
    base = normalize_public_base_url(public_base_url)
    _spawn(data_dir, ["tunnel", "--no-autoupdate", "run", "--token", token], "named", base)
    time.sleep(0.8)
    status = tunnel_status(data_dir)
    if not status.get("running"):
        raise RuntimeError(status.get("last_error") or "cloudflared se cerró al iniciar")
    return status


def start_named_tunnel_background(data_dir: str | os.PathLike, token: str, public_base_url: str) -> None:
    def _run():
        try:
            start_named_tunnel(data_dir, token, public_base_url)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True, name="rp-cloudflared").start()


def tunnel_status(data_dir: str | os.PathLike) -> dict:
    _, state_path, log_path = _paths(data_dir)
    info = _load(state_path)
    pid = int(info.get("pid") or 0)
    running = _pid_running(pid)
    mode = str(info.get("mode") or "off") if running else "off"
    base = str(info.get("public_base_url") or "") if running else ""
    if running and mode == "quick" and not base:
        base = _quick_url(log_path)
        if base:
            info["public_base_url"] = base
            try:
                _save(state_path, info)
            except Exception:
                pass
    last_error = str(info.get("last_error") or "")
    if not running and info:
        try:
            tail = log_path.read_text(encoding="utf-8", errors="ignore")[-1800:].strip()
            if tail:
                last_error = tail.splitlines()[-1][:500]
        except Exception:
            pass
    try:
        ready = _binary().is_file()
    except Exception:
        ready = False
    return {
        "running": running,
        "pid": pid if running else 0,
        "mode": mode,
        "public_base_url": base,
        "cloudflared_ready": ready,
        "downloading": False,
        "last_error": last_error,
    }
