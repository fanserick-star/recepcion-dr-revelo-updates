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
URL = "http://127.0.0.1:8000"
VERSION_URL = URL + "/api/version"
TITLE = "Recepción Dr. Armando Revelo"
APP_USER_MODEL_ID = "DrArmandoRevelo.Recepcion"
MUTEX_NAME = "DrArmandoRevelo_Recepcion_Launcher"


def _data_dir() -> Path:
    configured = (os.getenv("RP_DATA_DIR") or "").strip()
    return Path(configured) if configured else ROOT / "data"


def _log_launcher(message: str) -> None:
    try:
        d = _data_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / "launcher_errors.log"
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
        if path.stat().st_size > 512 * 1024:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-600:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def _set_windows_identity() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def package_version() -> str:
    try:
        data = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8"))
        return str(data.get("version") or "4.3.34").strip()
    except Exception:
        return "4.3.34"


def expected_server_version() -> str:
    try:
        data = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8"))
        return str(data.get("app_version") or data.get("runtime_version") or data.get("version") or package_version()).strip()
    except Exception:
        return package_version()


def launcher_settings_path() -> Path:
    return _data_dir() / "launcher_settings.json"


def selected_window_mode() -> str:
    try:
        data = json.loads(launcher_settings_path().read_text(encoding="utf-8"))
        mode = str(data.get("window_mode") or "AUTO").strip().upper()
        return mode if mode in {"AUTO", "WEBVIEW2", "EDGE"} else "AUTO"
    except Exception:
        return "AUTO"


def running_version(timeout: float = 1.2) -> str | None:
    try:
        with urllib.request.urlopen(VERSION_URL + f"?ts={time.time_ns()}", timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
            return str(data.get("version") or "")
    except Exception:
        return None


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def listening_pid() -> int | None:
    if os.name != "nt":
        return None
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
            timeout=5, check=False, creationflags=_hidden_flags(),
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            if parts[3].upper() == "LISTENING" and parts[1].endswith(":8000"):
                try: return int(parts[-1])
                except Exception: pass
    except Exception:
        pass
    return None


def stop_server_on_port() -> None:
    if os.name != "nt":
        return
    for _ in range(2):
        pid = listening_pid()
        if not pid:
            return
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=6, check=False, creationflags=_hidden_flags(),
            )
        except Exception:
            return
        for _ in range(25):
            if listening_pid() is None:
                return
            time.sleep(0.12)


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
    py = program_python(prefer_windowless=True)
    env = os.environ.copy(); env["RP_DESKTOP_LAUNCH"] = "1"
    flags = 0
    if os.name == "nt":
        flags = _hidden_flags() | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [str(py), str(ROOT / "app.py")], cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, close_fds=True,
    )


def wait_for_expected_version(seconds: float = 24.0, splash=None) -> bool:
    deadline = time.time() + seconds; expected = expected_server_version()
    while time.time() < deadline:
        if running_version(timeout=0.8) == expected:
            return True
        if splash: splash.pump()
        time.sleep(0.22)
    return False


def run_automatic_update() -> dict:
    try:
        import AUTOACTUALIZAR
        result = AUTOACTUALIZAR.check_and_apply() or {}
        if not result.get("ok", True):
            _log_launcher("Actualizador: " + str(result.get("error") or "error sin detalle"))
        return result
    except Exception as exc:
        _log_launcher("No se pudo cargar AUTOACTUALIZAR: " + repr(exc))
        return {"ok": False, "updated": False, "error": str(exc), "blocked": False, "deferred": True}


def _prepare_module():
    try:
        import PREPARAR_ESCRITORIO as prep
        return prep
    except Exception:
        return None


def cached_desktop_ready(max_age_days: int = 30) -> bool:
    try:
        path = _data_dir() / "desktop_runtime_status.json"
        if not path.exists() or (time.time() - path.stat().st_mtime) > max_age_days * 86400:
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("webview2") and data.get("pywebview"))
    except Exception:
        return False


def open_edge_app() -> bool:
    prep = _prepare_module(); edge = prep.edge_executable() if prep else None
    if not edge:
        return False
    try:
        subprocess.Popen(
            [str(edge), f"--app={URL}", "--start-maximized", "--disable-background-mode", "--no-first-run"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_hidden_flags(),
        )
        return True
    except Exception:
        return False


def open_webview2() -> bool:
    if os.name != "nt":
        return False
    prep = _prepare_module()
    if not prep:
        return False
    try:
        ready = cached_desktop_ready() or bool(prep.webview2_runtime_path() and prep.pywebview_ready())
        if not ready:
            result = prep.prepare(install_runtime=True, install_python=True)
            ready = bool(result.get("webview2") and result.get("pywebview"))
        if not ready:
            return False
        import webview
        try: webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        except Exception: pass
        maximize_after_start = False
        try:
            window = webview.create_window(
                TITLE, URL, width=1360, height=840, min_size=(900,620),
                resizable=True, text_select=True, maximized=True,
            )
        except TypeError:
            window = webview.create_window(
                TITLE, URL, width=1360, height=840, min_size=(900,620),
                resizable=True, text_select=True,
            )
            maximize_after_start = True
        kwargs = {"gui":"edgechromium", "debug":False, "private_mode":False, "storage_path":str(_data_dir()/"webview_profile")}
        icon = ROOT / "static" / "doctor_icon.ico"
        if icon.exists(): kwargs["icon"] = str(icon)
        if maximize_after_start:
            def _maximize():
                try:
                    time.sleep(0.15)
                    window.maximize()
                except Exception:
                    pass
            webview.start(_maximize, **kwargs)
        else:
            webview.start(**kwargs)
        return True
    except Exception:
        return False


def _enum_visible_windows():
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32; found=[]
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    @WNDENUMPROC
    def cb(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd): return True
            n=user32.GetWindowTextLengthW(hwnd)
            if n<=0: return True
            buf=ctypes.create_unicode_buffer(n+1); user32.GetWindowTextW(hwnd,buf,n+1)
            title=buf.value.strip()
            if title: found.append((hwnd,title))
        except Exception: pass
        return True
    user32.EnumWindows(cb,0)
    return found


def focus_existing_window() -> bool:
    if os.name != "nt":
        return False
    user32=ctypes.windll.user32
    for hwnd,title in _enum_visible_windows():
        low=title.lower()
        if "recepción dr. armando revelo" in low or "recepcion dr. armando revelo" in low:
            try:
                SW_RESTORE=9; user32.ShowWindow(hwnd,SW_RESTORE); user32.SetForegroundWindow(hwnd)
                return True
            except Exception: pass
    return False


class Splash:
    def __init__(self):
        self.root=None; self.label=None; self.detail=None
        try:
            import tkinter as tk
            root=tk.Tk(); root.overrideredirect(True); root.attributes('-topmost',True)
            w,h=430,180; sw=root.winfo_screenwidth(); sh=root.winfo_screenheight(); x=(sw-w)//2; y=(sh-h)//2
            root.geometry(f"{w}x{h}+{x}+{y}"); root.configure(bg="#13213c")
            frame=tk.Frame(root,bg="#13213c",padx=26,pady=22); frame.pack(fill="both",expand=True)
            tk.Label(frame,text="RECEPCIÓN",font=("Segoe UI",11,"bold"),fg="#8fb5ff",bg="#13213c").pack(anchor="w")
            tk.Label(frame,text="Dr. Armando Revelo",font=("Segoe UI",19,"bold"),fg="white",bg="#13213c").pack(anchor="w",pady=(2,18))
            self.label=tk.Label(frame,text="Abriendo sistema…",font=("Segoe UI",11,"bold"),fg="white",bg="#13213c"); self.label.pack(anchor="w")
            self.detail=tk.Label(frame,text="Preparando Recepción",font=("Segoe UI",9),fg="#b9c8df",bg="#13213c"); self.detail.pack(anchor="w",pady=(5,0))
            root.update_idletasks(); root.update(); self.root=root
        except Exception:
            self.root=None
    def set(self,text,detail=""):
        try:
            if self.label:self.label.config(text=text)
            if self.detail:self.detail.config(text=detail)
            self.pump()
        except Exception: pass
    def pump(self):
        try:
            if self.root:self.root.update_idletasks();self.root.update()
        except Exception: pass
    def close(self):
        try:
            if self.root:self.root.destroy()
        except Exception: pass
        self.root=None


def _message(title: str, text: str) -> None:
    if os.name == "nt":
        try: ctypes.windll.user32.MessageBoxW(0, text, title, 0x10); return
        except Exception: pass


def acquire_launcher_mutex():
    if os.name != "nt": return None, False
    kernel32=ctypes.windll.kernel32; handle=kernel32.CreateMutexW(None,False,MUTEX_NAME)
    already=kernel32.GetLastError()==183
    return handle,already


def open_ui() -> None:
    mode=selected_window_mode()
    if mode=="EDGE":
        if open_edge_app(): return
        webbrowser.open(URL,new=2); return
    if open_webview2(): return
    if open_edge_app(): return
    webbrowser.open(URL,new=2)


def main() -> None:
    _set_windows_identity()
    handle,already=acquire_launcher_mutex()
    if already:
        for _ in range(50):
            if focus_existing_window(): return
            time.sleep(0.2)
        if running_version() is not None:
            focus_existing_window(); return

    if running_version() == expected_server_version() and focus_existing_window():
        return

    splash=Splash()
    try:
        splash.set("Verificando actualización…","Comprobando la versión vigente")
        update=run_automatic_update()
        if update.get("blocked"):
            splash.close(); _message(TITLE, update.get("error") or "La instalación local necesita reparación antes de iniciar."); return
        if update.get("deferred"):
            splash.set("Iniciando sistema…", "Actualización pendiente; se reintentará al próximo inicio")
            time.sleep(0.15)
        if update.get("updated"):
            splash.set("Instalando actualización…",f"Versión {update.get('version') or ''}")
            stop_server_on_port()

        version=running_version(); expected=expected_server_version()
        splash.set("Iniciando sistema…","Preparando agenda y datos locales")
        if version is None:
            start_server()
            if not wait_for_expected_version(24.0,splash):
                stop_server_on_port(); start_server(); wait_for_expected_version(18.0,splash)
        elif version != expected:
            stop_server_on_port(); start_server(); wait_for_expected_version(22.0,splash)

        splash.set("Listo","Abriendo Recepción")
        time.sleep(0.15); splash.close(); open_ui()
    finally:
        splash.close()
        if os.name=="nt" and handle:
            try: ctypes.windll.kernel32.CloseHandle(handle)
            except Exception: pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _log_launcher("Fallo general del iniciador: " + repr(exc) + " | " + traceback.format_exc(limit=5).replace("\n", " | "))
        try:
            if running_version() is None:
                start_server()
                deadline = time.time() + 12
                while time.time() < deadline and running_version(timeout=0.8) is None:
                    time.sleep(0.3)
            if running_version() is not None:
                try: open_ui()
                except Exception: webbrowser.open(URL, new=2)
            else:
                _message(TITLE, "No se pudo iniciar Recepción. El detalle quedó guardado en data/launcher_errors.log.")
        except Exception as final_exc:
            _log_launcher("También falló el arranque de respaldo: " + repr(final_exc))
