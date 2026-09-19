from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

LAUNCHER_VERSION = "1.1.1"
PRODUCT = "historia-clinica-dr-revelo"
TITLE = "Historia Clínica - Dr. Armando Revelo"
APP_PORT = 8787
URL = f"http://127.0.0.1:{APP_PORT}"
VERSION_URL = URL + "/api/version"
ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-historia.json"
OFFICIAL_RAW_PREFIX = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/"
PROTECTED_TOP = {"data", ".venv"}
PROTECTED_FILES = {".env"}
MUTEX_NAME = "DrArmandoRevelo_HistoriaClinica_Launcher_v1"


def _data_dir() -> Path:
    p = ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log(message: str) -> None:
    try:
        p = _data_dir() / "launcher.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        if p.stat().st_size > 700_000:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-1000:]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def _message(text: str, error: bool = False) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(text), TITLE, 0x10 if error else 0x40)
            return
        except Exception:
            pass
    print(text, file=sys.stderr if error else sys.stdout)


class _Splash:
    """Pantalla liviana de arranque. Si Tk no está disponible, no bloquea el programa."""
    def __init__(self):
        self.root = None
        self.canvas = None
        self.title = None
        self.detail = None
        self.elapsed = None
        self.stage = 1
        self.started = time.monotonic()
        self.phase = self.started
        self.spin = 0
        try:
            import tkinter as tk
            self.tk = tk
            root = tk.Tk()
            root.title(TITLE)
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg="#f4efe5")
            width, height = 520, 250
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{width}x{height}+{max(0,(sw-width)//2)}+{max(0,(sh-height)//2)}")

            outer = tk.Frame(root, bg="#f4efe5", highlightthickness=1, highlightbackground="#b8aa94")
            outer.pack(fill="both", expand=True)

            head = tk.Frame(outer, bg="#123f73", height=74)
            head.pack(fill="x")
            head.pack_propagate(False)

            logo_path = ROOT / "static" / "doctor_logo.png"
            if logo_path.is_file():
                try:
                    img = tk.PhotoImage(file=str(logo_path))
                    # El logo original es suficientemente pequeño; reducimos si viniera grande.
                    if img.width() > 64 or img.height() > 64:
                        factor = max(1, int(max(img.width()/56, img.height()/56)))
                        img = img.subsample(factor, factor)
                    self._logo_img = img
                    tk.Label(head, image=img, bg="#123f73").pack(side="left", padx=(20,10), pady=9)
                except Exception:
                    pass
            brand = tk.Frame(head, bg="#123f73")
            brand.pack(side="left", fill="y", pady=11)
            tk.Label(brand, text="Historia Clínica", font=("Segoe UI", 15, "bold"), fg="white", bg="#123f73").pack(anchor="w")
            tk.Label(brand, text="Dr. Armando Revelo", font=("Segoe UI", 9), fg="#dce8f5", bg="#123f73").pack(anchor="w")

            body = tk.Frame(outer, bg="#f4efe5", padx=26, pady=18)
            body.pack(fill="both", expand=True)
            self.title = tk.Label(body, text="Preparando Historia Clínica…", font=("Segoe UI", 13, "bold"), fg="#173b66", bg="#f4efe5")
            self.title.pack(anchor="w")
            self.detail = tk.Label(body, text="Comprobando componentes del sistema", font=("Segoe UI", 9), fg="#655d52", bg="#f4efe5")
            self.detail.pack(anchor="w", pady=(4, 14))

            self.canvas = tk.Canvas(body, height=8, bd=0, highlightthickness=0, bg="#ded6c9")
            self.canvas.pack(fill="x")
            self.elapsed = tk.Label(body, text="Etapa 1 de 4", font=("Segoe UI", 8), fg="#847b70", bg="#f4efe5")
            self.elapsed.pack(anchor="e", pady=(8,0))
            self.root = root
            self.pump()
        except Exception as exc:
            self.root = None
            _log("Splash no disponible: " + repr(exc))

    def set_stage(self, stage: int, title: str, detail: str = "") -> None:
        self.stage = max(1, min(4, int(stage)))
        self.phase = time.monotonic()
        try:
            if self.title: self.title.config(text=title)
            if self.detail: self.detail.config(text=detail)
            self.pump()
        except Exception:
            pass

    def pump(self) -> None:
        if not self.root:
            return
        try:
            now = time.monotonic()
            secs = max(0, int(now - self.started))
            if self.elapsed:
                self.elapsed.config(text=f"{secs} s · etapa {self.stage} de 4" if secs >= 2 else f"Etapa {self.stage} de 4")
            if self.canvas:
                self.canvas.update_idletasks()
                w = max(1, int(self.canvas.winfo_width() or 450))
                self.canvas.delete("progress")
                base = int(w * ((self.stage - 1) / 4.0))
                target = int(w * (self.stage / 4.0))
                self.spin = (self.spin + 1) % 20
                pulse = int((target - base) * (self.spin / 19.0))
                if self.stage >= 4:
                    pulse = target - base
                self.canvas.create_rectangle(0, 0, min(w, base + pulse), 8, fill="#2b6aa7", outline="", tags="progress")
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self.root:
                self.root.destroy()
        except Exception:
            pass
        self.root = None


def _vtuple(value: str) -> tuple[int, ...]:
    out = []
    for part in str(value or "0").split("."):
        m = re.match(r"^(\d+)", part)
        out.append(int(m.group(1)) if m else 0)
    return tuple((out + [0, 0, 0, 0])[:4])


def _cache_bust(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    q.append(("hc_ts", str(time.time_ns())))
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), p.fragment))


def _fetch_bytes(url: str, timeout: float = 10.0, attempts: int = 3) -> bytes:
    last = None
    for i in range(max(1, attempts)):
        try:
            req = urllib.request.Request(
                _cache_bust(url),
                headers={"User-Agent": f"HistoriaClinicaDrRevelo/{LAUNCHER_VERSION}", "Cache-Control": "no-cache", "Pragma": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if getattr(r, "status", 200) != 200:
                    raise RuntimeError(f"HTTP {getattr(r, 'status', '?')}")
                return r.read()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(0.45 * (i + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def _fetch_manifest() -> dict:
    data = json.loads(_fetch_bytes(DEFAULT_MANIFEST_URL, timeout=8, attempts=2).decode("utf-8-sig"))
    if not isinstance(data, dict) or data.get("product") != PRODUCT:
        raise RuntimeError("Canal de actualización inválido")
    if not data.get("version") or not isinstance(data.get("files"), list):
        raise RuntimeError("Canal de actualización incompleto")
    return data


def _local_version() -> str:
    try:
        text = (ROOT / "app.py").read_text(encoding="utf-8-sig", errors="ignore")
        m = re.search(r'(?m)^\s*APP_VERSION\s*=\s*["\']([^"\']+)', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        return str(json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8-sig")).get("version") or "0.0.0")
    except Exception:
        return "0.0.0"


def _safe_target(relative: str) -> Path:
    rel = str(relative or "").replace("\\", "/").lstrip("/")
    parts = [x for x in rel.split("/") if x]
    if not parts or any(x in {".", ".."} for x in parts):
        raise RuntimeError("Ruta de actualización inválida")
    if parts[0].lower() in {x.lower() for x in PROTECTED_TOP}:
        raise RuntimeError(f"Ruta protegida: {rel}")
    if len(parts) == 1 and parts[0].lower() in {x.lower() for x in PROTECTED_FILES}:
        raise RuntimeError(f"Archivo protegido: {rel}")
    dest = (ROOT / Path(*parts)).resolve()
    rr = ROOT.resolve()
    if dest != rr and rr not in dest.parents:
        raise RuntimeError("Ruta fuera de la instalación")
    return dest


def _download_item(item: dict) -> bytes:
    urls = item.get("parts") or ([item.get("url")] if item.get("url") else [])
    urls = [str(u or "").strip() for u in urls if str(u or "").strip()]
    if not urls:
        raise RuntimeError(f"{item.get('path')}: sin URL")
    for url in urls:
        if not url.startswith(OFFICIAL_RAW_PREFIX):
            raise RuntimeError("Fuente de actualización no autorizada")
    payload = b"".join(_fetch_bytes(url) for url in urls)
    expected = str(item.get("sha256") or "").lower().strip()
    got = hashlib.sha256(payload).hexdigest()
    if not expected or got != expected:
        raise RuntimeError(f"SHA inválido para {item.get('path')}")
    return payload


def _backup_before_update(paths: list[str], version: str) -> tuple[Path, set[str]]:
    backups = _data_dir() / "update_backups"
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"antes_v{version.replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns()}.zip"
    existed = set()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in paths:
            p = _safe_target(rel)
            if p.is_file():
                z.write(p, rel)
                existed.add(rel)
    old = sorted(backups.glob("antes_v*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in old[3:]:
        try: p.unlink()
        except Exception: pass
    return target, existed


def _restore_backup(backup: Path, touched: list[str], existed: set[str]) -> None:
    for rel in touched:
        if rel not in existed:
            try:
                p = _safe_target(rel)
                if p.is_file(): p.unlink()
            except Exception:
                pass
    if backup.is_file():
        with zipfile.ZipFile(backup, "r") as z:
            for name in z.namelist():
                dest = _safe_target(name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".rollback_tmp")
                tmp.write_bytes(z.read(name))
                os.replace(tmp, dest)


def _apply_update(remote: dict, splash: _Splash | None = None) -> bool:
    version = str(remote["version"])
    stage = Path(tempfile.mkdtemp(prefix="hc_update_", dir=str(_data_dir())))
    staged = []
    try:
        files = list(remote.get("files") or [])
        total = max(1, len(files))
        for idx, item in enumerate(files, 1):
            if splash:
                splash.set_stage(2, "Actualizando Historia Clínica…", f"Descargando archivos {idx} de {total}")
            rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            dest = _safe_target(rel)
            expected = str(item.get("sha256") or "").lower().strip()
            if dest.is_file() and expected:
                try:
                    if hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
                        continue
                except Exception:
                    pass
            payload = _download_item(item)
            if rel.lower().endswith(".py"):
                compile(payload.decode("utf-8-sig"), rel, "exec")
            sp = stage / rel
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_bytes(payload)
            staged.append((rel, sp, expected))
        if not staged:
            return False
        touched = [x[0] for x in staged]
        backup, existed = _backup_before_update(touched, version)
        try:
            for rel, sp, expected in staged:
                dest = _safe_target(rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".new")
                shutil.copyfile(sp, tmp)
                os.replace(tmp, dest)
                if hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
                    raise RuntimeError(f"Verificación local falló: {rel}")
            _log(f"Actualización aplicada {version}")
            return True
        except Exception:
            _restore_backup(backup, touched, existed)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _venv_python(windowless: bool = False) -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / ("pythonw.exe" if windowless else "python.exe")
    return ROOT / ".venv" / "bin" / "python"


def _create_venv() -> None:
    py = _venv_python(False)
    if py.is_file():
        return
    subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], cwd=str(ROOT), check=True)


def _requirements_hash() -> str:
    p = ROOT / "requirements.txt"
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def _ensure_dependencies(force: bool = False, splash: _Splash | None = None) -> None:
    if splash:
        splash.set_stage(1, "Preparando Historia Clínica…", "Comprobando componentes necesarios")
    _create_venv()
    py = _venv_python(False)
    marker = _data_dir() / "requirements_state.json"
    wanted = _requirements_hash()
    old = {}
    if marker.is_file():
        try: old = json.loads(marker.read_text(encoding="utf-8"))
        except Exception: old = {}
    if not force and old.get("sha256") == wanted:
        return
    if splash:
        splash.set_stage(1, "Preparando Historia Clínica…", "Instalando componentes; esto puede tardar la primera vez")
    subprocess.run(
        [str(py), "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "-r", str(ROOT / "requirements.txt")],
        cwd=str(ROOT), check=True,
    )
    marker.write_text(json.dumps({"sha256": wanted, "installed_at": time.time()}, indent=2), encoding="utf-8")


def _api_version(timeout: float = 0.7) -> str:
    try:
        with urllib.request.urlopen(VERSION_URL + f"?t={time.time_ns()}", timeout=timeout) as r:
            return str(json.loads(r.read().decode("utf-8")).get("version") or "")
    except Exception:
        return ""


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _start_server(splash: _Splash | None = None) -> subprocess.Popen:
    if splash:
        splash.set_stage(3, "Iniciando Historia Clínica…", "Abriendo la base local y preparando la sincronización")
    py = _venv_python(False)
    log = (_data_dir() / "backend_startup.log").open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [str(py), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(APP_PORT), "--no-access-log", "--log-level", "warning"],
        cwd=str(ROOT), stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=_hidden_flags(),
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("El servidor de Historia Clínica no pudo iniciar. Revise data\\backend_startup.log")
        if _api_version():
            return proc
        if splash:
            splash.pump()
        time.sleep(0.20)
    try: proc.terminate()
    except Exception: pass
    raise RuntimeError("Historia Clínica tardó demasiado en iniciar")


def _open_webview() -> bool:
    try:
        import webview
    except Exception as exc:
        _log("pywebview no disponible: " + repr(exc))
        return False
    kwargs = {
        "gui": "edgechromium", "debug": False, "private_mode": False,
        "storage_path": str(_data_dir() / "webview_profile"),
    }
    icon = ROOT / "static" / "doctor_icon.ico"
    if icon.is_file(): kwargs["icon"] = str(icon)
    try:
        try:
            window = webview.create_window(TITLE, URL, width=1440, height=900, min_size=(1050, 700), resizable=True, text_select=True, maximized=True)
            maximize_after = False
        except TypeError:
            window = webview.create_window(TITLE, URL, width=1440, height=900, min_size=(1050, 700), resizable=True, text_select=True)
            maximize_after = True
        if maximize_after:
            def on_start():
                try: window.maximize()
                except Exception: pass
            webview.start(on_start, **kwargs)
        else:
            webview.start(**kwargs)
        return True
    except Exception as exc:
        _log("WebView2 falló: " + repr(exc) + " | " + traceback.format_exc(limit=3).replace("\n", " | "))
        return False


def _edge_exe() -> Path | None:
    if os.name != "nt": return None
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for p in candidates:
        if p.is_file(): return p
    return None


def _open_fallback() -> subprocess.Popen | None:
    edge = _edge_exe()
    if edge:
        try:
            return subprocess.Popen([str(edge), f"--app={URL}", "--start-maximized", "--disable-background-mode", "--no-first-run"], cwd=str(ROOT), creationflags=_hidden_flags())
        except Exception as exc:
            _log("Fallback Edge falló: " + repr(exc))
    webbrowser.open(URL, new=2)
    return None


def _acquire_mutex():
    if os.name != "nt": return None
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:
        _message("Historia Clínica ya está abierta.")
        raise SystemExit(0)
    return handle


def _release_mutex(handle):
    if os.name == "nt" and handle:
        try:
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex(handle)
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception: pass


def _check_and_update(splash: _Splash | None = None) -> bool:
    if splash:
        splash.set_stage(2, "Buscando actualizaciones…", "Comprobando que tengas la versión más reciente")
    try:
        remote = _fetch_manifest()
    except Exception as exc:
        _log("No se pudo revisar actualización: " + repr(exc))
        return False
    local = _local_version()
    if _vtuple(str(remote.get("version"))) <= _vtuple(local):
        return False
    _log(f"Actualización disponible {local} -> {remote.get('version')}")
    changed = _apply_update(remote, splash=splash)
    if changed:
        _ensure_dependencies(force=True, splash=splash)
    return changed


def prepare() -> int:
    splash = _Splash()
    try:
        _ensure_dependencies(force=False, splash=splash)
        splash.set_stage(4, "Todo listo", "Historia Clínica quedó preparada")
        time.sleep(0.4)
        splash.close()
        _message("Historia Clínica quedó preparada. Ya puede abrirla desde el acceso directo del escritorio.")
        return 0
    except Exception as exc:
        splash.close()
        _log("Preparación falló: " + repr(exc))
        _message("No se pudo preparar Historia Clínica.\n\n" + str(exc), error=True)
        return 2


def self_test() -> int:
    assert _vtuple("1.10.0") > _vtuple("1.9.9")
    for rel in ("data/x", ".env"):
        try:
            _safe_target(rel)
            raise AssertionError(rel + " debía estar protegido")
        except RuntimeError:
            pass
    assert _safe_target("app.py").name == "app.py"
    compile((ROOT / "app.py").read_text(encoding="utf-8"), "app.py", "exec")
    compile((ROOT / "cloud_sync.py").read_text(encoding="utf-8"), "cloud_sync.py", "exec")
    print("SELF_TEST_OK")
    return 0


def main() -> None:
    handle = _acquire_mutex()
    server = None
    splash = _Splash()
    try:
        _ensure_dependencies(splash=splash)
        _check_and_update(splash=splash)
        _ensure_dependencies(splash=splash)
        server = _start_server(splash=splash)
        splash.set_stage(4, "Todo listo", "Abriendo Historia Clínica")
        time.sleep(0.28)
        splash.close()
        if not _open_webview():
            edge_proc = _open_fallback()
            if edge_proc is not None:
                try: edge_proc.wait()
                except Exception: pass
            else:
                while server.poll() is None:
                    time.sleep(2)
    except Exception as exc:
        splash.close()
        _log("Fallo fatal: " + repr(exc) + " | " + traceback.format_exc(limit=5).replace("\n", " | "))
        _message("No se pudo abrir Historia Clínica.\n\n" + str(exc) + "\n\nEl detalle quedó en data\\launcher.log", error=True)
    finally:
        splash.close()
        if server is not None and server.poll() is None:
            try: server.terminate(); server.wait(timeout=4)
            except Exception:
                try: server.kill()
                except Exception: pass
        _release_mutex(handle)


if __name__ == "__main__":
    if "--prepare" in sys.argv:
        raise SystemExit(prepare())
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    main()