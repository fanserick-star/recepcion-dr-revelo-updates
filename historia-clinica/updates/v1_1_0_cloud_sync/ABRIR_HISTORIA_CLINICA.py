from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

LAUNCHER_VERSION = "1.1.0"
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


def _message(text: str, title: str = TITLE) -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x40)
            return
        except Exception:
            pass
    print(text)


def _vtuple(value: str) -> tuple[int, ...]:
    parts = []
    for x in str(value or "0").split("."):
        m = re.match(r"^(\d+)", x)
        parts.append(int(m.group(1)) if m else 0)
    return tuple((parts + [0, 0, 0, 0])[:4])


def _cache_bust(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    q.append(("hc_ts", str(time.time_ns())))
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), p.fragment))


def _fetch_bytes(url: str, timeout: float = 10.0, attempts: int = 3) -> bytes:
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                _cache_bust(url),
                headers={"User-Agent": f"HistoriaClinicaDrRevelo/{LAUNCHER_VERSION}", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if getattr(r, "status", 200) != 200:
                    raise RuntimeError(f"HTTP {getattr(r, 'status', '?')}")
                return r.read()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(0.5 * (i + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def _fetch_manifest() -> dict:
    raw = _fetch_bytes(DEFAULT_MANIFEST_URL, timeout=8, attempts=2)
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or data.get("product") != PRODUCT:
        raise RuntimeError("Canal de actualización inválido")
    if not data.get("version") or not isinstance(data.get("files"), list):
        raise RuntimeError("Canal de actualización incompleto")
    return data


def _local_version() -> str:
    # app.py es la fuente de verdad: así el launcher no depende de reemplazar
    # update_manifest.json y nunca toca archivos de datos/configuración privada.
    try:
        text = (ROOT / "app.py").read_text(encoding="utf-8-sig", errors="ignore")
        m = re.search(r'(?m)^\s*APP_VERSION\s*=\s*["\']([^"\']+)', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    p = ROOT / "update_manifest.json"
    if p.is_file():
        try:
            return str(json.loads(p.read_text(encoding="utf-8-sig")).get("version") or "0.0.0")
        except Exception:
            pass
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
        raise RuntimeError(f"{item.get('path')}: no tiene URL")
    for url in urls:
        if not url.startswith(OFFICIAL_RAW_PREFIX):
            raise RuntimeError("Fuente de actualización no autorizada")
    payload = b"".join(_fetch_bytes(url) for url in urls)
    expected = str(item.get("sha256") or "").lower()
    got = hashlib.sha256(payload).hexdigest()
    if not expected or got != expected:
        raise RuntimeError(f"SHA inválido para {item.get('path')}")
    return payload


def _backup_before_update(paths: list[str], version: str) -> Path:
    backups = _data_dir() / "update_backups"
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"antes_v{version.replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in paths:
            p = _safe_target(rel)
            if p.is_file():
                z.write(p, rel)
    old = sorted(backups.glob("antes_v*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in old[4:]:
        try: p.unlink()
        except Exception: pass
    return target


def _restore_backup(backup: Path, touched: list[str], existed: set[str]) -> None:
    for rel in touched:
        if rel not in existed:
            try:
                p = _safe_target(rel)
                if p.exists(): p.unlink()
            except Exception:
                pass
    if backup.is_file():
        with zipfile.ZipFile(backup, "r") as z:
            for name in z.namelist():
                dest = _safe_target(name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".rollback")
                tmp.write_bytes(z.read(name))
                os.replace(tmp, dest)


def _apply_update(remote: dict) -> bool:
    version = str(remote["version"])
    staged_dir = Path(tempfile.mkdtemp(prefix="historia_update_", dir=str(_data_dir())))
    staged: list[tuple[str, Path, str]] = []
    try:
        for item in remote.get("files") or []:
            rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            dest = _safe_target(rel)
            expected = str(item.get("sha256") or "").lower()
            if dest.is_file() and expected:
                try:
                    if hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
                        continue
                except Exception:
                    pass
            payload = _download_item(item)
            if rel.lower().endswith(".py"):
                compile(payload.decode("utf-8-sig"), rel, "exec")
            sp = staged_dir / rel
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_bytes(payload)
            staged.append((rel, sp, expected))
        if not staged:
            return False
        touched = [x[0] for x in staged]
        existed = {rel for rel in touched if _safe_target(rel).is_file()}
        backup = _backup_before_update(touched, version)
        try:
            for rel, sp, expected in staged:
                dest = _safe_target(rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".new")
                shutil.copyfile(sp, tmp)
                os.replace(tmp, dest)
                if hashlib.sha256(dest.read_bytes()).hexdigest() != expected:
                    raise RuntimeError(f"Verificación local falló: {rel}")
            _log(f"Actualización aplicada: {version}")
            return True
        except Exception:
            _restore_backup(backup, touched, existed)
            raise
    finally:
        shutil.rmtree(staged_dir, ignore_errors=True)


def _venv_python(windowless: bool = False) -> Path:
    name = "pythonw.exe" if windowless and os.name == "nt" else ("python.exe" if os.name == "nt" else "python")
    return ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / name


def _create_venv() -> None:
    py = _venv_python(False)
    if py.is_file():
        return
    cmd = [sys.executable, "-m", "venv", str(ROOT / ".venv")]
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def _requirements_hash() -> str:
    p = ROOT / "requirements.txt"
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def _ensure_dependencies(force: bool = False) -> None:
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
    subprocess.run(
        [str(py), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(ROOT / "requirements.txt")],
        cwd=str(ROOT), check=True,
    )
    marker.write_text(json.dumps({"sha256": wanted, "installed_at": time.time()}, indent=2), encoding="utf-8")


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.15)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _api_version(timeout: float = 0.6) -> str:
    try:
        with urllib.request.urlopen(VERSION_URL + f"?t={time.time_ns()}", timeout=timeout) as r:
            return str(json.loads(r.read().decode("utf-8")).get("version") or "")
    except Exception:
        return ""


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _start_server() -> subprocess.Popen:
    py = _venv_python(False)
    log = (_data_dir() / "backend_startup.log").open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [str(py), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(APP_PORT), "--no-access-log"],
        cwd=str(ROOT), stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=_hidden_flags(),
    )
    deadline = time.time() + 25
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("El servidor de Historia Clínica no pudo iniciar")
        if _api_version():
            return proc
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("Historia Clínica tardó demasiado en iniciar")


def _edge_exe() -> str | None:
    if os.name != "nt":
        return None
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for p in candidates:
        if p.is_file(): return str(p)
    return None


def _open_ui(server: subprocess.Popen) -> None:
    try:
        import webview
        window = webview.create_window(TITLE, URL, width=1460, height=920, min_size=(1024, 700), text_select=True)
        webview.start(gui="edgechromium", debug=False, private_mode=False)
        return
    except Exception as exc:
        _log("WebView no disponible: " + repr(exc))
    edge = _edge_exe()
    if edge:
        try:
            subprocess.Popen([edge, f"--app={URL}", "--start-maximized"], creationflags=_hidden_flags())
            while server.poll() is None:
                time.sleep(2)
            return
        except Exception as exc:
            _log("Edge app falló: " + repr(exc))
    webbrowser.open(URL)
    while server.poll() is None:
        time.sleep(2)


def _acquire_mutex():
    if os.name != "nt":
        return None
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.windll.kernel32.GetLastError() == 183
    if already:
        try: ctypes.windll.user32.MessageBoxW(None, "Historia Clínica ya está abierta.", TITLE, 0x40)
        except Exception: pass
        raise SystemExit(0)
    return handle


def _check_and_update() -> bool:
    try:
        remote = _fetch_manifest()
    except Exception as exc:
        _log("No se pudo revisar actualización: " + repr(exc))
        return False
    local = _local_version()
    if _vtuple(str(remote.get("version"))) <= _vtuple(local):
        return False
    _log(f"Actualización disponible {local} -> {remote.get('version')}")
    changed = _apply_update(remote)
    if changed:
        _ensure_dependencies(force=True)
    return changed


def run_self_test() -> int:
    assert _vtuple("1.10.2") > _vtuple("1.9.9")
    try:
        _safe_target("data/x")
        raise AssertionError("data debe estar protegida")
    except RuntimeError:
        pass
    try:
        _safe_target(".env")
        raise AssertionError(".env debe estar protegido")
    except RuntimeError:
        pass
    assert _safe_target("app.py").name == "app.py"
    compile((ROOT / "app.py").read_text(encoding="utf-8"), "app.py", "exec")
    print("SELF_TEST_OK")
    return 0


def main() -> None:
    mutex = _acquire_mutex()
    server = None
    try:
        _ensure_dependencies()
        _check_and_update()
        # An update can replace requirements after the initial dependency check.
        _ensure_dependencies()
        if _port_open(APP_PORT) and _api_version():
            webbrowser.open(URL)
            return
        server = _start_server()
        _open_ui(server)
    except Exception as exc:
        _log("Fallo fatal: " + repr(exc))
        _message("No se pudo abrir Historia Clínica.\n\n" + str(exc) + "\n\nRevise data\\launcher.log si necesita más detalle.")
    finally:
        if server is not None and server.poll() is None:
            try: server.terminate(); server.wait(timeout=4)
            except Exception:
                try: server.kill()
                except Exception: pass
        if os.name == "nt" and mutex:
            try:
                import ctypes
                ctypes.windll.kernel32.ReleaseMutex(mutex)
                ctypes.windll.kernel32.CloseHandle(mutex)
            except Exception:
                pass


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(run_self_test())
    main()