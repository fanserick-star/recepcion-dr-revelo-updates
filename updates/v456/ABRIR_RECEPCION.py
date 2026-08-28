from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8000"
VERSION_URL = URL + "/api/version"
TITLE = "Recepción Dr. Armando Revelo"
LAUNCHER_VERSION = "4.3.56-standalone-safe"
EXPECTED_APP_VERSION = "4.3.54"

def log(msg: str) -> None:
    try:
        with (DATA / "launcher_errors.log").open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def message(text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x10)
    except Exception:
        pass

def running_version(timeout: float = 1.0) -> str | None:
    try:
        with urllib.request.urlopen(VERSION_URL + f"?ts={time.time_ns()}", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return str(data.get("version") or "")
    except Exception:
        return None

def python_exe(windowless: bool = True) -> Path:
    choices = []
    if windowless:
        choices.append(ROOT / ".venv" / "Scripts" / "pythonw.exe")
    choices.append(ROOT / ".venv" / "Scripts" / "python.exe")
    for p in choices:
        if p.exists():
            return p
    raise FileNotFoundError("No se encontró Python en .venv\\Scripts.")

def start_backend() -> None:
    py = python_exe(windowless=True)
    log_path = DATA / "backend_startup.log"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    env = os.environ.copy()
    env["RP_DESKTOP_LAUNCH"] = "1"
    fh = open(log_path, "a", encoding="utf-8")
    fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando app.py con {py}\n")
    fh.flush()
    subprocess.Popen(
        [str(py), str(ROOT / "app.py")],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=fh,
        stderr=fh,
        creationflags=flags,
        close_fds=True,
    )

def edge_path() -> Path | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for p in candidates:
        if str(p) and p.exists():
            return p
    return None

def open_ui() -> None:
    edge = edge_path()
    if edge:
        try:
            subprocess.Popen(
                [str(edge), f"--app={URL}", "--start-maximized", "--disable-background-mode", "--no-first-run"],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return
        except Exception as exc:
            log("No se pudo abrir Edge app: " + repr(exc))
    webbrowser.open(URL, new=2)

def main() -> None:
    current = running_version()
    if current == EXPECTED_APP_VERSION:
        open_ui()
        return

    start_backend()
    deadline = time.time() + 18
    while time.time() < deadline:
        if running_version(timeout=0.8) == EXPECTED_APP_VERSION:
            open_ui()
            return
        time.sleep(0.25)

    log("Primer intento no respondió; reintentando app.py.")
    start_backend()
    deadline = time.time() + 18
    while time.time() < deadline:
        if running_version(timeout=0.8) == EXPECTED_APP_VERSION:
            open_ui()
            return
        time.sleep(0.25)

    raise RuntimeError("El backend no respondió. Revisa data\\backend_startup.log.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("Fallo launcher standalone: " + repr(exc) + " | " + traceback.format_exc(limit=6).replace("\n", " | "))
        message(
            "No se pudo iniciar Recepción.\n\n"
            "El detalle quedó guardado en:\n"
            "data\\backend_startup.log\n"
            "data\\launcher_errors.log"
        )
