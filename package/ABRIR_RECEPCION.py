from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8000"
VERSION_URL = URL + "/api/version"
def package_version() -> str:
    try:
        manifest = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8"))
        version = str(manifest.get("version") or "").strip()
        if version:
            return version
    except Exception:
        pass
    return "4.3.16.1"


def expected_server_version() -> str:
    try:
        manifest = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8"))
        value = str(manifest.get("app_version") or manifest.get("version") or "").strip()
        if value:
            return value
    except Exception:
        pass
    return package_version()


TITLE = "Recepción Dr. Armando Revelo"


def _data_dir() -> Path:
    configured = (os.getenv("RP_DATA_DIR") or "").strip()
    return Path(configured) if configured else ROOT / "data"


def launcher_settings_path() -> Path:
    return _data_dir() / "launcher_settings.json"


def selected_window_mode() -> str:
    try:
        data = json.loads(launcher_settings_path().read_text(encoding="utf-8"))
        mode = str(data.get("window_mode") or "AUTO").strip().upper()
        if mode in {"AUTO", "WEBVIEW2", "EDGE"}:
            return mode
    except Exception:
        pass
    return "AUTO"


def running_version(timeout: float = 1.5) -> str | None:
    """Consulta una ruta local instantánea; nunca usa el chequeo de Neon."""
    try:
        with urllib.request.urlopen(VERSION_URL + f"?ts={time.time_ns()}", timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
            return str(data.get("version") or "")
    except Exception:
        return None


def listening_pid() -> int | None:
    if os.name != "nt":
        return None
    script = (
        "$c=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue "
        "| Select-Object -First 1; if($c){Write-Output $c.OwningProcess}"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=4, check=False,
        )
        value = (r.stdout or "").strip().splitlines()
        if value:
            return int(value[-1].strip())
    except Exception:
        pass
    return None


def stop_server_on_port() -> None:
    if os.name != "nt":
        return
    for _ in range(2):
        pid = listening_pid()
        if not pid:
            break
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            )
        except Exception:
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, check=False,
                )
            except Exception:
                pass
        for _ in range(15):
            if listening_pid() is None:
                return
            time.sleep(0.15)


def program_python(prefer_windowless: bool = True) -> Path:
    candidates = []
    if prefer_windowless:
        candidates.append(ROOT / ".venv" / "Scripts" / "pythonw.exe")
    candidates.append(ROOT / ".venv" / "Scripts" / "python.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No se encontró Python del programa. Ejecuta INSTALAR.bat una vez.")


def start_server() -> None:
    python_exe = program_python(prefer_windowless=True)
    env = os.environ.copy()
    env["RP_DESKTOP_LAUNCH"] = "1"
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    entry = ROOT / "APP_ENTRY.py"
    if not entry.exists():
        entry = ROOT / "app.py"
    subprocess.Popen(
        [str(python_exe), str(entry)],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def wait_for_expected_version(seconds: float = 24.0) -> bool:
    deadline = time.time() + seconds
    expected = expected_server_version()
    while time.time() < deadline:
        if running_version(timeout=1.0) == expected:
            return True
        time.sleep(0.35)
    return False


def run_automatic_update() -> dict:
    try:
        import AUTOACTUALIZAR
        return AUTOACTUALIZAR.check_and_apply() or {}
    except Exception as exc:
        return {"ok": False, "updated": False, "error": str(exc)}


def _prepare_module():
    try:
        import PREPARAR_ESCRITORIO as prep
        return prep
    except Exception:
        return None


def open_edge_app() -> bool:
    prep = _prepare_module()
    edge = prep.edge_executable() if prep else None
    if not edge:
        return False
    try:
        subprocess.Popen(
            [
                str(edge),
                f"--app={URL}",
                "--start-maximized",
                "--disable-background-mode",
                "--no-first-run",
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def cached_desktop_ready(max_age_days: int = 30) -> bool:
    """Evita recorrer Program Files en cada inicio si WebView2 ya fue verificado."""
    try:
        path = _data_dir() / "desktop_runtime_status.json"
        if not path.exists() or (time.time() - path.stat().st_mtime) > max_age_days * 86400:
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("webview2") and data.get("pywebview"))
    except Exception:
        return False


def open_webview2() -> bool:
    """Abre una ventana nativa ligera usando el runtime Edge WebView2.

    Si falta algún componente intentamos prepararlo silenciosamente. Cualquier
    problema cae a Edge modo aplicación sin afectar al servidor ni a los datos.
    """
    if os.name != "nt":
        return False
    prep = _prepare_module()
    if not prep:
        return False
    try:
        ready = cached_desktop_ready()
        if not ready:
            ready = bool(prep.webview2_runtime_path() and prep.pywebview_ready())
        if not ready:
            result = prep.prepare(install_runtime=True, install_python=True)
            ready = bool(result.get("webview2") and result.get("pywebview"))
        if not ready:
            return False

        import webview

        try:
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        except Exception:
            pass
        icon = ROOT / "static" / "doctor_icon.ico"
        webview.create_window(
            TITLE,
            URL,
            width=1180,
            height=760,
            min_size=(760, 560),
            resizable=True,
            text_select=True,
        )
        kwargs = {
            "gui": "edgechromium",
            "debug": False,
            "private_mode": False,
            "storage_path": str(_data_dir() / "webview_profile"),
        }
        if icon.exists():
            kwargs["icon"] = str(icon)
        webview.start(**kwargs)
        return True
    except Exception:
        return False


def open_ui() -> None:
    mode = selected_window_mode()
    if mode == "EDGE":
        if open_edge_app():
            return
        webbrowser.open(URL, new=2)
        return

    # AUTO y WEBVIEW2 intentan primero la ventana nativa. WEBVIEW2 también cae
    # a Edge si algo falta para que el usuario nunca quede bloqueado.
    if open_webview2():
        return
    if open_edge_app():
        return
    webbrowser.open(URL, new=2)


def main() -> None:
    # Siempre comprobar actualizaciones al abrir, incluso si el servidor local
    # quedó vivo de una sesión anterior. Así ninguna PC se queda atrás.
    update = run_automatic_update()
    if update.get("updated"):
        if listening_pid() is not None:
            stop_server_on_port()
        start_server()
        wait_for_expected_version(seconds=24.0)
        open_ui()
        return

    version = running_version()
    expected = expected_server_version()
    if version is None:
        start_server()
        if not wait_for_expected_version(seconds=18.0):
            if listening_pid() is not None:
                stop_server_on_port()
            start_server()
            wait_for_expected_version(seconds=18.0)
    elif version != expected:
        stop_server_on_port()
        start_server()
        wait_for_expected_version(seconds=18.0)
    open_ui()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Último respaldo: abrir la URL. Nunca tocamos ni borramos datos aquí.
        webbrowser.open(URL, new=2)
