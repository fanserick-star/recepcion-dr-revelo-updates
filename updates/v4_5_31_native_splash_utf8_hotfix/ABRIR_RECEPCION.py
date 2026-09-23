from __future__ import annotations

import ast
import base64
import ctypes
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import socket

LAUNCHER_VERSION = "4.5.31-native-splash-utf8-hotfix-1"
PRODUCT = "recepcion-pacientes"
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v4.json"
APP_PORT = 8000
URL = f"http://127.0.0.1:{APP_PORT}"
VERSION_URL = URL + "/api/version"
TITLE = "Recepción Dr. Armando Revelo"
APP_USER_MODEL_ID = "DrArmandoRevelo.Recepcion"
MUTEX_NAME = "DrArmandoRevelo_Recepcion_Launcher_v2"
OFFICIAL_RAW_PREFIX = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/"
ROOT = Path(__file__).resolve().parent
MIN_SPLASH_SECONDS = 5.0

PROTECTED_TOP = {"data", ".venv"}
PROTECTED_FILES = {".env", "BASE DE DATOS 2026.xlsx"}


def _data_dir(root: Path = ROOT) -> Path:
    raw = (os.getenv("RP_DATA_DIR") or "").strip()
    if not raw and (root / ".env").exists():
        try:
            for line in (root / ".env").read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                if line.strip().startswith("RP_DATA_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if not raw:
        return root / "data"
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    return p if p.is_absolute() else root / p


def _log(message: str, root: Path = ROOT) -> None:
    try:
        d = _data_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "launcher_errors.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        if p.stat().st_size > 768 * 1024:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-900:]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def _write_state(root: Path = ROOT, **values) -> None:
    try:
        d = _data_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "auto_update_state.json"
        old = {}
        if p.exists():
            try:
                old = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                old = {}
        old.update(values)
        old["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def _vtuple(value: str) -> tuple[int, ...]:
    out = []
    for part in str(value or "0").split("."):
        m = re.match(r"^(\d+)", part)
        out.append(int(m.group(1)) if m else 0)
    return tuple((out + [0, 0, 0, 0])[:4])


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON inválido: {path.name}")
    return data


def _local_manifest(root: Path = ROOT) -> dict:
    p = root / "update_manifest.json"
    return _load_json(p) if p.exists() else {}


def _local_package_version(root: Path = ROOT) -> str:
    return str(_local_manifest(root).get("version") or "0.0.0").strip()


def _installed_app_version(root: Path = ROOT) -> str:
    try:
        text = (root / "app.py").read_text(encoding="utf-8-sig", errors="ignore")
        m = re.search(r'(?m)^\s*APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def _expected_app_version(root: Path = ROOT) -> str:
    m = _local_manifest(root)
    return str(m.get("app_version") or m.get("runtime_version") or m.get("version") or "").strip()


def _installation_consistent(root: Path = ROOT) -> bool:
    """Valida versión Y dependencias obligatorias del paquete instalado."""
    try:
        m = _local_manifest(root)
        expected = str(m.get("app_version") or m.get("runtime_version") or "").strip()
        if expected and _installed_app_version(root) != expected:
            return False
        if not (root / "app.py").is_file():
            return False

        required = m.get("required_dependencies") or []
        if isinstance(required, list):
            for rel in required:
                rel = str(rel or "").replace("\\", "/").strip().lstrip("/")
                if not rel:
                    continue
                if not _safe_target(root, rel).is_file():
                    return False
        return True
    except Exception:
        return False


def _cache_bust(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    q.append(("rp_ts", str(time.time_ns())))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment))


def _fetch_bytes(url: str, *, attempts: int = 3, timeout: float = 8.0) -> bytes:
    last = None
    for i in range(max(1, attempts)):
        try:
            req = urllib.request.Request(
                _cache_bust(url),
                headers={
                    "User-Agent": f"Recepcion-Dr-Revelo-Standalone/{LAUNCHER_VERSION}",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if getattr(r, "status", 200) != 200:
                    raise RuntimeError(f"HTTP {getattr(r, 'status', '?')}")
                return r.read()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(0.35 * (i + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def _fetch_manifest(url: str = DEFAULT_MANIFEST_URL, *, attempts: int = 3, timeout: float = 8.0) -> dict:
    data = json.loads(_fetch_bytes(url, attempts=attempts, timeout=timeout).decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError("Manifest remoto inválido")
    if data.get("product") != PRODUCT:
        raise RuntimeError("Producto remoto inválido")
    version = str(data.get("version") or "").strip()
    files = data.get("files")
    if not version or not isinstance(files, list) or not files:
        raise RuntimeError("Manifest remoto incompleto")
    return data


def _safe_target(root: Path, relative: str) -> Path:
    rel = str(relative or "").replace("\\", "/").lstrip("/")
    parts = [p for p in rel.split("/") if p]
    if not parts or any(p in {".", ".."} for p in parts):
        raise RuntimeError(f"Ruta de actualización inválida: {relative!r}")
    if parts[0].lower() in {x.lower() for x in PROTECTED_TOP}:
        raise RuntimeError(f"Ruta protegida: {relative}")
    if len(parts) == 1 and parts[0].lower() in {x.lower() for x in PROTECTED_FILES}:
        raise RuntimeError(f"Archivo protegido: {relative}")
    dest = (root / Path(*parts)).resolve()
    rr = root.resolve()
    if dest != rr and rr not in dest.parents:
        raise RuntimeError(f"Ruta fuera de la instalación: {relative}")
    return dest


def _payload_urls(item: dict) -> list[str]:
    urls = item.get("parts") or ([item.get("url")] if item.get("url") else [])
    urls = [str(u).strip() for u in urls if str(u or "").strip()]
    if not urls:
        raise RuntimeError(f"{item.get('path')}: no tiene URL")
    return urls


def _download_item(
    item: dict,
    *,
    attempts: int = 3,
    timeout: float = 10.0,
    allow_test_sources: bool = False,
) -> bytes:
    urls = _payload_urls(item)
    if not allow_test_sources:
        for u in urls:
            if not u.startswith(OFFICIAL_RAW_PREFIX):
                raise RuntimeError(f"Fuente de actualización no autorizada: {u}")
    payload = b"".join(_fetch_bytes(u, attempts=attempts, timeout=timeout) for u in urls)
    expected = str(item.get("sha256") or "").lower().strip()
    got = hashlib.sha256(payload).hexdigest()
    if not expected or got != expected:
        raise RuntimeError(f"SHA inválido para {item.get('path')}: {got} != {expected or '[vacío]'}")
    return payload


def _validate_payload(target_rel: str, payload: bytes, remote: dict) -> None:
    lower = target_rel.lower()
    if lower.endswith(".py"):
        try:
            source_text = payload.decode("utf-8-sig")
            compile(source_text, target_rel, "exec")
        except Exception as exc:
            raise RuntimeError(f"{target_rel} no compila: {exc}") from exc

        if lower == "abrir_recepcion.py":
            tree = ast.parse(source_text)
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            banned = {"AUTOACTUALIZAR", "_AUTOACTUALIZAR_31", "_ABRIR_RECEPCION_451"}
            bad = banned & imported
            if bad:
                raise RuntimeError(
                    "El launcher publicado depende de módulos auxiliares prohibidos: " + ", ".join(sorted(bad))
                )

    if lower == "app.py":
        text = payload.decode("utf-8-sig", errors="ignore")
        expected_app = str(remote.get("app_version") or remote.get("runtime_version") or remote.get("version") or "").strip()
        if expected_app and not re.search(
            rf'(?m)^\s*APP_VERSION\s*=\s*["\']{re.escape(expected_app)}["\']', text
        ):
            raise RuntimeError(f"app.py no declara APP_VERSION {expected_app}")

    if lower == "update_manifest.json":
        inner = json.loads(payload.decode("utf-8-sig"))
        if str(inner.get("version") or "").strip() != str(remote.get("version") or "").strip():
            raise RuntimeError("update_manifest.json no coincide con la versión remota")
        av = str(inner.get("app_version") or "").strip()
        rv = str(inner.get("runtime_version") or "").strip()
        if av and rv and av != rv:
            raise RuntimeError("app_version y runtime_version difieren")
        if av and _vtuple(av) > _vtuple(str(remote.get("version") or "")):
            raise RuntimeError("app_version no puede superar package version")


def _stage_update(
    remote: dict,
    root: Path = ROOT,
    *,
    attempts: int = 3,
    timeout: float = 10.0,
    allow_test_sources: bool = False,
) -> tuple[Path, list[dict]]:
    """Descarga únicamente archivos cuyo SHA difiere de la instalación local."""
    data = _data_dir(root)
    stage = data / "update_staging" / f"v{remote['version'].replace('.', '_')}_{time.time_ns()}"
    stage.mkdir(parents=True, exist_ok=False)
    staged = []
    seen = set()
    try:
        for item in remote.get("files") or []:
            rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            if rel in seen:
                raise RuntimeError(f"Ruta duplicada: {rel}")
            seen.add(rel)
            dest = _safe_target(root, rel)
            expected_sha = str(item.get("sha256") or "").lower().strip()
            if dest.is_file() and expected_sha:
                try:
                    if hashlib.sha256(dest.read_bytes()).hexdigest() == expected_sha:
                        continue
                except Exception:
                    pass

            payload = _download_item(
                item, attempts=attempts, timeout=timeout, allow_test_sources=allow_test_sources
            )
            _validate_payload(rel, payload, remote)
            sp = stage / rel
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_bytes(payload)
            staged.append({"rel": rel, "stage": sp, "sha256": expected_sha})
        return stage, staged
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _make_backup(root: Path, staged: list[dict], version: str) -> tuple[Path, set[str]]:
    d = _data_dir(root) / "update_backups"
    d.mkdir(parents=True, exist_ok=True)

    # v4.5.3: mantenemos hasta 3 respaldos automáticos. Así siempre existe
    # una referencia reciente de "última versión buena" sin llenar el disco.
    old_backups = sorted(
        d.glob("auto_antes_v*.zip"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for old in old_backups[2:]:
        try:
            old.unlink()
        except Exception:
            pass

    backup = d / f"auto_antes_v{version.replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns()}.zip"
    existed = set()
    with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as z:
        for entry in staged:
            rel = entry["rel"]
            dest = _safe_target(root, rel)
            if dest.is_file():
                z.write(dest, rel)
                existed.add(rel)
    return backup, existed


def _rollback(root: Path, backup: Path, staged: list[dict], existed: set[str]) -> None:
    for entry in staged:
        rel = entry["rel"]
        dest = _safe_target(root, rel)
        if rel not in existed:
            try:
                if dest.exists():
                    dest.unlink()
            except Exception:
                pass
    if backup.exists():
        with zipfile.ZipFile(backup, "r") as z:
            for name in z.namelist():
                dest = _safe_target(root, name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_name(dest.name + ".rollback_tmp")
                temp.write_bytes(z.read(name))
                os.replace(temp, dest)


def _restore_update_backup(root: Path, backup_path: str, updated_paths: list[str]) -> bool:
    """Restaura la versión previa si el backend nuevo no consigue iniciar.

    El ZIP creado por _make_backup contiene todos los archivos actualizados que
    ya existían. Los archivos nuevos de la versión fallida se eliminan para
    volver al conjunto exacto anterior.
    """
    backup = Path(str(backup_path or ""))
    if not backup.is_file():
        return False
    with zipfile.ZipFile(backup, "r") as z:
        names = {str(n).replace("\\", "/").lstrip("/") for n in z.namelist()}
        for rel in updated_paths or []:
            rel = str(rel or "").replace("\\", "/").lstrip("/")
            if not rel or rel in names:
                continue
            try:
                dest = _safe_target(root, rel)
                if dest.is_file():
                    dest.unlink()
                elif dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
            except Exception:
                pass
        for name in names:
            dest = _safe_target(root, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(dest.name + ".startup_rollback_tmp")
            temp.write_bytes(z.read(name))
            os.replace(temp, dest)
    _log("Rollback automático aplicado después de fallo de arranque.", root)
    _write_state(
        root,
        last_check_ok=False,
        last_error="La versión nueva no inició; se recuperó automáticamente la versión anterior.",
        startup_rollback=True,
        installation_consistent=_installation_consistent(root),
        local_version=_local_package_version(root),
        local_app_version=_installed_app_version(root),
    )
    return True


def _validate_installed(remote: dict, root: Path, staged: list[dict]) -> None:
    for entry in staged:
        dest = _safe_target(root, entry["rel"])
        if not dest.is_file():
            raise RuntimeError(f"Falta archivo tras actualizar: {entry['rel']}")
        got = hashlib.sha256(dest.read_bytes()).hexdigest()
        if got != entry["sha256"]:
            raise RuntimeError(f"SHA local incorrecto tras actualizar: {entry['rel']}")
        if entry["rel"].lower().endswith(".py"):
            compile(dest.read_text(encoding="utf-8-sig"), entry["rel"], "exec")

    local = _local_manifest(root)
    if str(local.get("version") or "").strip() != str(remote.get("version") or "").strip():
        raise RuntimeError("El manifest local no quedó en la versión remota")
    expected_app = str(local.get("app_version") or local.get("runtime_version") or "").strip()
    if expected_app and _installed_app_version(root) != expected_app:
        raise RuntimeError(
            f"app.py quedó en {_installed_app_version(root) or '[sin versión]'}; se esperaba {expected_app}"
        )



def _candidate_fingerprint(remote: dict) -> str:
    rows = []
    for item in remote.get("files") or []:
        rows.append([
            str(item.get("path") or ""),
            str(item.get("sha256") or ""),
        ])
    raw = json.dumps(
        {"version": str(remote.get("version") or ""), "files": rows},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _update_state_snapshot(root: Path = ROOT) -> dict:
    try:
        p = _data_dir(root) / "auto_update_state.json"
        return _load_json(p) if p.is_file() else {}
    except Exception:
        return {}


def _candidate_failure_count(remote: dict, root: Path = ROOT) -> int:
    state = _update_state_snapshot(root)
    if str(state.get("failed_candidate_version") or "") != str(remote.get("version") or ""):
        return 0
    if str(state.get("failed_candidate_fingerprint") or "") != _candidate_fingerprint(remote):
        return 0
    try:
        return int(state.get("failed_candidate_count") or 0)
    except Exception:
        return 0


def _mark_candidate_failure(remote: dict, exc: BaseException, root: Path = ROOT) -> int:
    count = _candidate_failure_count(remote, root) + 1
    _write_state(
        root,
        failed_candidate_version=str(remote.get("version") or ""),
        failed_candidate_fingerprint=_candidate_fingerprint(remote),
        failed_candidate_count=count,
        candidate_quarantined=count >= 2,
        candidate_last_error=str(exc)[:800],
    )
    return count


def _clear_candidate_failure(root: Path = ROOT) -> None:
    _write_state(
        root,
        failed_candidate_version="",
        failed_candidate_fingerprint="",
        failed_candidate_count=0,
        candidate_quarantined=False,
        candidate_last_error="",
    )


def _trial_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _trial_version(url: str, timeout: float = 0.6) -> str | None:
    try:
        with urllib.request.urlopen(url + f"?ts={time.time_ns()}", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return str(data.get("version") or "")
    except Exception:
        return None


def _trial_runtime(remote: dict, root: Path, stage: Path, staged: list[dict], splash=None) -> dict:
    """Levanta la versión candidata en un puerto aislado antes de tocar la estable."""
    runtime_changed = any(
        e["rel"].lower().endswith(".py")
        and e["rel"].lower() != "abrir_recepcion.py"
        for e in staged
    )
    if not runtime_changed:
        return {"tested": False, "reason": "launcher_or_manifest_only"}

    trial = stage / "__trial_root"
    trial.mkdir(parents=True, exist_ok=False)
    staged_map = {str(e["rel"]).replace("\\", "/"): Path(e["stage"]) for e in staged}

    try:
        # v4.5.3.1: la prueba aislada parte de los módulos auxiliares ya
        # instalados (azur_client, whatsapp_client, remote_agenda, etc.).
        # La versión candidata declarada se copia DESPUÉS y los reemplaza.
        for local_py in root.glob("*.py"):
            try:
                if local_py.name.lower() == "abrir_recepcion.py":
                    continue
                dest = trial / local_py.name
                shutil.copyfile(local_py, dest)
            except Exception:
                pass

        for item in remote.get("files") or []:
            rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
            if not rel or rel.lower() == "abrir_recepcion.py":
                continue
            src = staged_map.get(rel)
            if src is None:
                src = _safe_target(root, rel)
            if not src.is_file():
                continue
            dest = trial / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)

        static_src = root / "static"
        if static_src.is_dir():
            shutil.copytree(static_src, trial / "static", dirs_exist_ok=True)

        app_path = trial / "app.py"
        if not app_path.is_file():
            return {"tested": False, "reason": "app_unchanged_not_in_candidate"}

        expected = str(
            remote.get("app_version")
            or remote.get("runtime_version")
            or remote.get("version")
            or ""
        ).strip()
        port = _trial_free_port()
        trial_data = trial / "_trial_data"
        trial_data.mkdir(parents=True, exist_ok=True)
        log_path = trial / "_trial_startup.log"

        py = _python_exe(windowless=False)
        env = os.environ.copy()
        env.update({
            "RP_PREFLIGHT": "1",
            "RP_DESKTOP_LAUNCH": "1",
            "RP_PORT": str(port),
            "RP_DATA_DIR": str(trial_data),
            "DATABASE_URL": "",
            "NEON_DATABASE_URL": "",
            "WHATSAPP_ENABLED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DISABLE_SQLALCHEMY_CEXT_RUNTIME": "1",
        })

        if splash:
            splash.set(
                "Probando actualización antes de instalar…",
                "Arranque aislado · tus datos reales no se tocan",
            )

        with log_path.open("w", encoding="utf-8") as fh:
            proc = subprocess.Popen(
                [str(py), str(app_path)],
                cwd=str(trial),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=fh,
                creationflags=_hidden_flags(),
                close_fds=True,
            )

        version_url = f"http://127.0.0.1:{port}/api/version"
        deadline = time.time() + 18.0
        success = False
        failure = ""
        try:
            while time.time() < deadline:
                rc = proc.poll()
                if rc is not None:
                    failure = f"La copia de prueba terminó con código {rc}."
                    break
                if _trial_version(version_url) == expected:
                    success = True
                    break
                if splash:
                    splash.pump()
                time.sleep(0.18)
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        if not success:
            try:
                tail = "\n".join(log_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()[-20:])
            except Exception:
                tail = ""
            if not failure:
                failure = "La copia de prueba no respondió dentro del tiempo seguro."
            if tail:
                failure += "\n" + tail
            raise RuntimeError("PRECHECK_STARTUP: " + failure)

        return {"tested": True, "version": expected, "port": port}
    finally:
        try:
            shutil.rmtree(trial, ignore_errors=True)
        except Exception:
            pass


def _apply_remote(
    remote: dict,
    root: Path = ROOT,
    *,
    attempts: int = 3,
    timeout: float = 10.0,
    test_fail_after: int | None = None,
    allow_test_sources: bool = False,
    splash=None,
) -> dict:
    stage, staged = _stage_update(
        remote, root, attempts=attempts, timeout=timeout, allow_test_sources=allow_test_sources
    )
    try:
        trial = _trial_runtime(remote, root, stage, staged, splash=splash)
        backup, existed = _make_backup(root, staged, str(remote["version"]))
        ordered = sorted(staged, key=lambda e: e["rel"].lower() == "update_manifest.json")
        applied = 0
        try:
            for entry in ordered:
                rel = entry["rel"]
                dest = _safe_target(root, rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                temp = dest.with_name(dest.name + f".new_{os.getpid()}_{time.time_ns()}")
                shutil.copyfile(entry["stage"], temp)
                os.replace(temp, dest)
                applied += 1
                if test_fail_after is not None and applied >= test_fail_after:
                    raise RuntimeError("Fallo simulado para probar rollback")
            _validate_installed(remote, root, staged)
            return {
                "backup": str(backup),
                "paths": [e["rel"] for e in staged],
                "trial": trial,
                "downloaded_files": len(staged),
                "declared_files": len(remote.get("files") or []),
            }
        except Exception:
            _rollback(root, backup, staged, existed)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def check_and_apply_update(
    root: Path = ROOT,
    manifest_url: str = DEFAULT_MANIFEST_URL,
    *,
    attempts: int = 3,
    timeout: float = 8.0,
    allow_test_sources: bool = False,
    splash=None,
) -> dict:
    local_version = _local_package_version(root)
    coherent = _installation_consistent(root)
    try:
        remote = _fetch_manifest(
            manifest_url,
            attempts=max(3, attempts),
            timeout=max(8.0, timeout),
        )
    except Exception as exc:
        _write_state(
            root,
            last_check_ok=False,
            last_error=str(exc),
            local_version=local_version,
            local_app_version=_installed_app_version(root),
            installation_consistent=coherent,
        )
        if coherent:
            return {"ok": True, "updated": False, "deferred": True, "error": str(exc)}
        return {"ok": False, "updated": False, "blocked": True, "error": str(exc)}

    remote_version = str(remote.get("version") or "").strip()
    mandatory = bool(remote.get("mandatory")) and _vtuple(remote_version) > _vtuple(local_version)
    should_apply = _vtuple(remote_version) > _vtuple(local_version) or (
        remote_version == local_version and not coherent
    )

    if not should_apply:
        _write_state(
            root,
            last_check_ok=True,
            last_error="",
            local_version=local_version,
            local_app_version=_installed_app_version(root),
            remote_version=remote_version,
            installation_consistent=coherent,
            mandatory_update=False,
        )
        return {"ok": True, "updated": False, "version": local_version}

    failures = _candidate_failure_count(remote, root)
    if coherent and failures >= 2:
        msg = (
            f"La versión {remote_version} quedó en cuarentena porque falló "
            "dos pruebas de arranque. Se abrirá la última versión estable."
        )
        _write_state(
            root,
            last_check_ok=False,
            last_error=msg,
            remote_version=remote_version,
            mandatory_update=False,
            candidate_quarantined=True,
        )
        return {
            "ok": True,
            "updated": False,
            "deferred": True,
            "quarantined": True,
            "version": local_version,
            "remote_version": remote_version,
            "error": msg,
        }

    try:
        result = _apply_remote(
            remote,
            root,
            attempts=max(attempts, 5 if mandatory else attempts),
            timeout=max(timeout, 14.0 if mandatory else timeout),
            allow_test_sources=allow_test_sources,
            splash=splash,
        )
        _clear_candidate_failure(root)
        _write_state(
            root,
            last_check_ok=True,
            last_error="",
            local_version=remote_version,
            local_app_version=_installed_app_version(root),
            remote_version=remote_version,
            installation_consistent=_installation_consistent(root),
            last_installed_version=remote_version,
            last_backup=result.get("backup", ""),
            last_updated_paths=list(result.get("paths", []) or []),
            last_downloaded_files=int(result.get("downloaded_files") or 0),
            last_declared_files=int(result.get("declared_files") or 0),
            last_preflight_tested=bool((result.get("trial") or {}).get("tested")),
            mandatory_update=False,
        )
        return {
            "ok": True,
            "updated": True,
            "version": remote_version,
            "paths": result.get("paths", []),
            "backup": result.get("backup"),
            "trial": result.get("trial", {}),
            "downloaded_files": result.get("downloaded_files", 0),
            "declared_files": result.get("declared_files", 0),
        }
    except Exception as exc:
        _log("Actualización candidata rechazada/revertida: " + repr(exc), root)
        current_coherent = _installation_consistent(root)
        fail_count = _mark_candidate_failure(remote, exc, root)
        quarantined = fail_count >= 2

        _write_state(
            root,
            last_check_ok=False,
            last_error=str(exc),
            local_version=_local_package_version(root),
            local_app_version=_installed_app_version(root),
            remote_version=remote_version,
            installation_consistent=current_coherent,
            mandatory_update=False if current_coherent else mandatory,
            candidate_quarantined=quarantined,
        )

        # Si la instalación actual sigue coherente, una candidata mala jamás
        # impide trabajar. La dejamos para reintento/cuarentena y abrimos LKG.
        if current_coherent:
            return {
                "ok": True,
                "updated": False,
                "deferred": True,
                "candidate_failed": True,
                "quarantined": quarantined,
                "failure_count": fail_count,
                "remote_version": remote_version,
                "error": str(exc),
            }

        return {
            "ok": False,
            "updated": False,
            "blocked": True,
            "mandatory": mandatory,
            "remote_version": remote_version,
            "error": "La instalación local necesita reparación y la actualización no pudo validarse: " + str(exc),
        }


def _running_version(timeout: float = 1.0) -> str | None:
    try:
        with urllib.request.urlopen(VERSION_URL + f"?ts={time.time_ns()}", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return str(data.get("version") or "")
    except Exception:
        return None


def _hidden_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _set_app_port(port: int) -> int:
    global APP_PORT, URL, VERSION_URL
    APP_PORT = int(port)
    URL = f"http://127.0.0.1:{APP_PORT}"
    VERSION_URL = URL + "/api/version"
    return APP_PORT


def _port_file() -> Path:
    return _data_dir(ROOT) / "local_port.txt"


def _read_saved_port() -> int | None:
    try:
        value = int(_port_file().read_text(encoding="utf-8").strip())
        return value if 1024 <= value <= 65535 else None
    except Exception:
        return None


def _save_port(port: int) -> None:
    try:
        path = _port_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(int(port)), encoding="utf-8")
    except Exception as exc:
        _log("No se pudo guardar el puerto local: " + repr(exc))


def _can_bind_port(port: int) -> bool:
    # Primero comprobamos si ya hay un listener accesible en loopback. En Windows
    # un bind a 0.0.0.0 puede no detectar correctamente un listener ligado solo
    # a 127.0.0.1, así que usamos ambas comprobaciones.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.20)
        if probe.connect_ex(("127.0.0.1", int(port))) == 0:
            return False
    except Exception:
        pass
    finally:
        try: probe.close()
        except Exception: pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.bind(("0.0.0.0", int(port)))
        return True
    except OSError:
        return False
    finally:
        try: sock.close()
        except Exception: pass


def _choose_app_port(force_new: bool = False) -> int:
    """Elige un puerto de Recepción sin cerrar ni interferir con programas ajenos."""
    saved = _read_saved_port()
    if saved and not force_new:
        _set_app_port(saved)
        # Si responde /api/version es nuestra copia ya levantada; se conserva.
        if _running_version(timeout=0.30) is not None:
            return saved
        if _can_bind_port(saved):
            return saved

    candidates = []
    if not force_new:
        candidates.append(8000)
    candidates.extend(range(8765, 8800))
    candidates.extend(range(18000, 18021))
    current = int(APP_PORT or 0)
    for port in candidates:
        if force_new and int(port) == current:
            continue
        if _can_bind_port(port):
            _set_app_port(port)
            _save_port(port)
            _log(f"Puerto local seleccionado: {port}")
            return port
    raise RuntimeError("No se encontró un puerto local libre para Recepción")


def _port_pids(port: int | None = None) -> list[int]:
    if os.name != "nt":
        return []
    wanted = str(int(port or APP_PORT))
    pids = set()
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
            timeout=6, check=False, creationflags=_hidden_flags(),
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0].upper() != "TCP":
                continue
            local = parts[1].strip()
            if local.rsplit(":", 1)[-1] != wanted:
                continue
            try: pid = int(parts[-1])
            except Exception: continue
            if pid > 0 and pid != os.getpid(): pids.add(pid)
    except Exception as exc:
        _log(f"No se pudo leer netstat para puerto {wanted}: {exc!r}")
    return sorted(pids)


def _listening_pid() -> int | None:
    pids = _port_pids()
    return pids[0] if pids else None


def _wait_app_port_free(seconds: float = 7.0) -> bool:
    deadline = time.time() + max(0.5, float(seconds))
    while time.time() < deadline:
        if not _port_pids(): return True
        time.sleep(0.15)
    return not _port_pids()


def _stop_server() -> None:
    if os.name != "nt": return
    pids = _port_pids()
    if not pids: return
    # Nunca matamos un proceso desconocido. Solo cerramos el dueño del puerto si
    # ese puerto está respondiendo como Recepción.
    if _running_version(timeout=0.45) is None:
        _log(f"Puerto {APP_PORT} ocupado por proceso ajeno; se conservará y se elegirá otro puerto")
        return
    for _round in range(4):
        pids = _port_pids()
        if not pids: return
        for pid in pids:
            try:
                proc = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=8, check=False, creationflags=_hidden_flags(),
                )
                if proc.returncode not in (0,128):
                    _log(f"taskkill PID {pid} devolvió {proc.returncode}")
            except Exception as exc:
                _log(f"No se pudo cerrar PID {pid} del puerto {APP_PORT}: {exc!r}")
        if _wait_app_port_free(2.5): return
    remaining=_port_pids()
    if remaining:
        raise RuntimeError(f"No se pudo liberar el puerto local {APP_PORT}. Procesos: " + ", ".join(map(str,remaining)))

def _ensure_embedded_python_root(root: Path = ROOT) -> bool:
    """Garantiza que el Python portátil pueda importar módulos desde la raíz."""
    scripts = root / ".venv" / "Scripts"
    pth = scripts / "python311._pth"
    if not pth.is_file():
        return False
    try:
        lines = [line.rstrip() for line in pth.read_text(encoding="utf-8-sig", errors="ignore").splitlines() if line.strip()]
        if "..\\.." not in [line.strip() for line in lines]:
            try:
                backup = pth.with_name(pth.name + ".antes_runtime_guard")
                if not backup.exists():
                    shutil.copyfile(pth, backup)
            except Exception:
                pass
            try:
                idx = next(i for i, line in enumerate(lines) if line.strip() == "import site")
            except StopIteration:
                idx = len(lines)
            lines.insert(idx, "..\\..")
            tmp = pth.with_suffix(pth.suffix + ".new")
            tmp.write_text("\n".join(lines) + "\n", encoding="ascii")
            os.replace(tmp, pth)
            _log("python311._pth reparado automáticamente: añadida la raíz de Recepción", root)
        root_s = str(root.resolve())
        if root_s not in sys.path:
            sys.path.insert(0, root_s)
        return True
    except Exception as exc:
        _log("No se pudo reparar python311._pth: " + repr(exc), root)
        return False


def _python_exe(windowless: bool = True) -> Path:
    candidates = []
    if windowless:
        candidates.append(ROOT / ".venv" / "Scripts" / "pythonw.exe")
    candidates.append(ROOT / ".venv" / "Scripts" / "python.exe")
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("No se encontró Python dentro de .venv\\Scripts.")


def _backend_log_tail(max_lines: int = 18) -> str:
    try:
        path = _data_dir(ROOT) / "backend_startup.log"
        if not path.is_file():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


_LAST_STARTUP_FAILURE = ""


def _start_server():
    """Inicia el backend y devuelve el proceso para detectar crashes inmediatos."""
    global _LAST_STARTUP_FAILURE
    _LAST_STARTUP_FAILURE = ""
    if os.name == "nt" and _port_pids():
        if _running_version(timeout=0.45) is not None:
            _stop_server()
        else:
            _choose_app_port(force_new=True)
    if os.name == "nt" and _port_pids():
        raise RuntimeError(f"El puerto local {APP_PORT} sigue ocupado")

    py = _python_exe(windowless=True)
    env = os.environ.copy()
    env["RP_DESKTOP_LAUNCH"] = "1"
    env["DISABLE_SQLALCHEMY_CEXT_RUNTIME"] = "1"
    env["RP_PORT"] = str(APP_PORT)

    d = _data_dir(ROOT)
    d.mkdir(parents=True, exist_ok=True)
    log_path = d / "backend_startup.log"
    fh = open(log_path, "a", encoding="utf-8")
    fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando app.py en puerto {APP_PORT}\n")
    fh.flush()

    flags = _hidden_flags()
    if os.name == "nt":
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    proc = subprocess.Popen(
        [str(py), str(ROOT / "app.py")], cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
        creationflags=flags, close_fds=True,
    )
    try:
        fh.close()
    except Exception:
        pass
    return proc


def _wait_server(expected: str, seconds: float, splash=None, process=None) -> bool:
    """Espera el servidor, pero termina al instante si app.py ya se cayó."""
    global _LAST_STARTUP_FAILURE
    deadline = time.time() + max(0.5, float(seconds))
    while time.time() < deadline:
        if process is not None:
            try:
                rc = process.poll()
            except Exception:
                rc = None
            if rc is not None:
                tail = _backend_log_tail()
                _LAST_STARTUP_FAILURE = f"app.py terminó con código {rc}."
                if tail:
                    _LAST_STARTUP_FAILURE += "\n" + tail
                return False
        if _running_version(timeout=0.55) == expected:
            return True
        if splash:
            splash.pump()
        time.sleep(0.16)

    _LAST_STARTUP_FAILURE = (
        f"El servidor local no respondió en {float(seconds):.0f} s."
        + (("\n" + _backend_log_tail()) if _backend_log_tail() else "")
    )
    return False



def _set_windows_identity() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def _ensure_windows_shortcuts() -> None:
    """Autorrepara los accesos de Recepción sin tocar datos ni configuración."""
    if os.name != "nt":
        return
    try:
        state_path = _data_dir(ROOT) / "auto_update_state.json"
        state = _load_json(state_path) if state_path.is_file() else {}
        last = float(state.get("shortcut_branding_checked_epoch") or 0)
        if (
            state.get("shortcut_branding_version") == LAUNCHER_VERSION
            and time.time() - last < 86400
        ):
            return
    except Exception:
        pass

    pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    launcher_file = ROOT / "ABRIR_RECEPCION.py"
    icon = ROOT / "recepcion.ico"
    if not icon.is_file():
        icon = ROOT / "static" / "doctor_icon.ico"
    if not pyw.is_file() or not launcher_file.is_file():
        _log("No se autorreparó acceso directo: faltan pythonw.exe o ABRIR_RECEPCION.py", ROOT)
        return

    try:
        name = "Recepción Dr. Armando Revelo.lnk"
        ps = f"""
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$name = '{name.replace("'", "''")}'
$target = '{str(pyw).replace("'", "''")}'
$args = '"{str(launcher_file).replace("'", "''")}"'
$work = '{str(ROOT).replace("'", "''")}'
$icon = '{str(icon).replace("'", "''")},0'
$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($dir in $dirs) {{
  if ([string]::IsNullOrWhiteSpace($dir)) {{ continue }}
  if (-not (Test-Path -LiteralPath $dir)) {{ continue }}
  Get-ChildItem -LiteralPath $dir -Filter '*.lnk' -ErrorAction SilentlyContinue |
    Where-Object {{
      $_.Name -ne $name -and (
        $_.Name -like 'Recepcion*Revelo*.lnk' -or
        $_.Name -like 'Recepción*Revelo*.lnk'
      )
    }} | Remove-Item -Force -ErrorAction SilentlyContinue
  $path = Join-Path $dir $name
  $s = $ws.CreateShortcut($path)
  $s.TargetPath = $target
  $s.Arguments = $args
  $s.WorkingDirectory = $work
  $s.IconLocation = $icon
  $s.Description = 'Recepción Dr. Armando Revelo'
  $s.WindowStyle = 1
  $s.Save()
}}
"""
        encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False, creationflags=_hidden_flags(),
        )
        if proc.returncode != 0:
            _log(f"Autorreparación de accesos terminó con código {proc.returncode}", ROOT)
            return
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass
        _write_state(
            ROOT,
            shortcut_branding_version=LAUNCHER_VERSION,
            shortcut_branding_checked_epoch=time.time(),
            shortcut_target="pythonw.exe + ABRIR_RECEPCION.py",
        )
    except Exception as exc:
        _log("No se pudo autorreparar acceso directo: " + repr(exc), ROOT)


def _enum_visible_windows():
    if os.name != "nt":
        return []
    found = []
    user32 = ctypes.windll.user32
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @PROC
    def cb(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.strip()
            if title:
                found.append((hwnd, title))
        except Exception:
            pass
        return True

    user32.EnumWindows(cb, 0)
    return found


def _focus_existing_window() -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    for hwnd, title in _enum_visible_windows():
        low = title.lower()
        if "recepción dr. armando revelo" in low or "recepcion dr. armando revelo" in low:
            try:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return True
            except Exception:
                pass
    return False


def _request_close_existing_window() -> bool:
    """Pide cerrar la ventana actual para poder instalar una actualización obligatoria."""
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    closed = False
    for hwnd, title in _enum_visible_windows():
        low = title.lower()
        if "recepción dr. armando revelo" in low or "recepcion dr. armando revelo" in low:
            try:
                # WM_CLOSE: cierre normal de la ventana, no mata el proceso a la fuerza.
                user32.PostMessageW(hwnd, 0x0010, 0, 0)
                closed = True
            except Exception:
                pass
    return closed


def _acquire_mutex(name: str = MUTEX_NAME):
    if os.name != "nt":
        return None, False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    already = kernel32.GetLastError() == 183
    return handle, already


def _release_mutex(handle) -> None:
    if os.name == "nt" and handle:
        try:
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            pass


class Splash:
    """Splash profesional de cuatro etapas, liviano y apto para PC antigua."""
    STAGES = ("ACTUALIZACIÓN", "COMPONENTES", "SERVIDOR", "LISTO")

    def __init__(self):
        self.root = None
        self.native_proc = None
        self.native_state = None
        self.native_last_write = 0.0
        self.label = None
        self.detail = None
        self.elapsed = None
        self.canvas = None
        self.stage_labels = []
        self.stage = 1
        self.started = time.monotonic()
        self.phase = self.started
        self.spin = 0
        self.warned = False
        try:
            import tkinter as tk

            root = tk.Tk()
            try:
                _ico = ROOT / "recepcion.ico"
                if not _ico.is_file():
                    _ico = ROOT / "static" / "doctor_icon.ico"
                if _ico.is_file():
                    root.iconbitmap(str(_ico))
            except Exception:
                pass
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            w, h = 550, 286
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
            root.configure(bg="#101c33")

            outer = tk.Frame(root, bg="#101c33", padx=26, pady=21)
            outer.pack(fill="both", expand=True)

            top = tk.Frame(outer, bg="#101c33")
            top.pack(fill="x")

            c = tk.Canvas(top, width=62, height=62, bg="#101c33", highlightthickness=0)
            c.pack(side="left", padx=(0, 14))
            try:
                logo = tk.PhotoImage(file=str(ROOT / "static" / "doctor_isotype.png")).subsample(5, 5)
                c.create_image(31, 31, image=logo)
                c._doctor_logo = logo
            except Exception:
                c.create_oval(5, 5, 57, 57, outline="#79a9ff", width=2)
                c.create_text(31, 31, text="+", font=("Segoe UI", 24, "bold"), fill="#ffffff")

            titles = tk.Frame(top, bg="#101c33")
            titles.pack(side="left", fill="x", expand=True)
            tk.Label(
                titles, text="RECEPCIÓN", font=("Segoe UI", 9, "bold"),
                fg="#78a9ff", bg="#101c33"
            ).pack(anchor="w")
            tk.Label(
                titles, text="Dr. Armando Revelo", font=("Segoe UI", 18, "bold"),
                fg="white", bg="#101c33"
            ).pack(anchor="w", pady=(1, 0))
            tk.Label(
                titles, text="Inicio seguro", font=("Segoe UI", 8),
                fg="#90a5c3", bg="#101c33"
            ).pack(anchor="w", pady=(2, 0))

            badge = tk.Frame(top, bg="#1a2b48", padx=9, pady=5)
            badge.pack(side="right", anchor="n")
            tk.Label(
                badge, text="PROTEGIDO", font=("Segoe UI", 7, "bold"),
                fg="#85dfaa", bg="#1a2b48"
            ).pack()
            tk.Label(
                badge, text="Launcher 4.5.3", font=("Segoe UI", 7),
                fg="#9fb0c7", bg="#1a2b48"
            ).pack(pady=(1, 0))

            steps = tk.Frame(outer, bg="#101c33")
            steps.pack(fill="x", pady=(18, 0))
            for idx, name in enumerate(self.STAGES, start=1):
                cell = tk.Frame(steps, bg="#101c33")
                cell.pack(side="left", fill="x", expand=True)
                num = tk.Label(
                    cell, text=str(idx), width=2,
                    font=("Segoe UI", 8, "bold"),
                    fg="#7e91ac", bg="#1b2a42", padx=2, pady=2
                )
                num.pack(side="left")
                txt = tk.Label(
                    cell, text=name, font=("Segoe UI", 7, "bold"),
                    fg="#6f819b", bg="#101c33"
                )
                txt.pack(side="left", padx=(5, 0))
                self.stage_labels.append((num, txt))

            body = tk.Frame(outer, bg="#101c33")
            body.pack(fill="x", pady=(17, 0))
            self.label = tk.Label(
                body, text="Preparando Recepción…",
                font=("Segoe UI", 11, "bold"), fg="white", bg="#101c33"
            )
            self.label.pack(anchor="w")
            self.detail = tk.Label(
                body, text="Comprobando inicio seguro",
                font=("Segoe UI", 9), fg="#b3c2d7", bg="#101c33"
            )
            self.detail.pack(anchor="w", pady=(4, 0))
            self.elapsed = tk.Label(
                body, text="", font=("Segoe UI", 8),
                fg="#7085a4", bg="#101c33"
            )
            self.elapsed.pack(anchor="w", pady=(5, 0))

            self.canvas = tk.Canvas(
                outer, width=490, height=6, bg="#22334f", highlightthickness=0
            )
            self.canvas.pack(fill="x", pady=(12, 0))

            footer = tk.Frame(outer, bg="#101c33")
            footer.pack(fill="x", pady=(8, 0))
            tk.Label(
                footer,
                text="Las actualizaciones se verifican antes de reemplazar la versión estable",
                font=("Segoe UI", 7), fg="#647996", bg="#101c33"
            ).pack(anchor="w")

            root.update_idletasks()
            root.update()
            self.root = root
            self._paint_stages()
        except Exception as exc:
            self.root = None
            _log("Tkinter no disponible para splash; usando respaldo nativo: " + repr(exc))
            self._start_native_fallback()

    def _native_write(self, *, closed: bool = False, force: bool = False):
        if not self.native_state:
            return
        now = time.monotonic()
        if not force and now - float(self.native_last_write or 0.0) < 0.08:
            return
        self.native_last_write = now
        try:
            payload = {
                "closed": bool(closed),
                "stage": int(self.stage),
                "text": str(self.label.cget("text") if self.label else getattr(self, "_native_text", "Preparando Recepción…")),
                "detail": str(self.detail.cget("text") if self.detail else getattr(self, "_native_detail", "Comprobando inicio seguro")),
                "elapsed": max(0.0, time.monotonic() - self.started),
            }
            tmp = self.native_state.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.native_state)
        except Exception:
            pass

    def _start_native_fallback(self):
        if os.name != "nt":
            return
        try:
            self._native_text = "Preparando Recepción…"
            self._native_detail = "Comprobando inicio seguro"
            self.native_state = Path(tempfile.gettempdir()) / (
                f"dr_revelo_splash_{os.getpid()}_{time.time_ns()}.json"
            )
            self._native_write(force=True)
            ps = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$state = $env:RP_SPLASH_STATE

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Recepción Dr. Armando Revelo'
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.ControlBox = $false
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.TopMost = $true
$form.ClientSize = New-Object System.Drawing.Size(550,286)
$form.BackColor = [System.Drawing.Color]::FromArgb(16,28,51)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'RECEPCIÓN'
$title.ForeColor = [System.Drawing.Color]::FromArgb(120,169,255)
$title.Font = New-Object System.Drawing.Font('Segoe UI',9,[System.Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(28,24)
$form.Controls.Add($title)

$doctor = New-Object System.Windows.Forms.Label
$doctor.Text = 'Dr. Armando Revelo'
$doctor.ForeColor = [System.Drawing.Color]::White
$doctor.Font = New-Object System.Drawing.Font('Segoe UI',18,[System.Drawing.FontStyle]::Bold)
$doctor.AutoSize = $true
$doctor.Location = New-Object System.Drawing.Point(26,43)
$form.Controls.Add($doctor)

$protected = New-Object System.Windows.Forms.Label
$protected.Text = 'PROTEGIDO'
$protected.ForeColor = [System.Drawing.Color]::FromArgb(133,223,170)
$protected.Font = New-Object System.Drawing.Font('Segoe UI',8,[System.Drawing.FontStyle]::Bold)
$protected.AutoSize = $true
$protected.Location = New-Object System.Drawing.Point(445,30)
$form.Controls.Add($protected)

$steps = New-Object System.Windows.Forms.Label
$steps.Text = '1  ACTUALIZACIÓN     2  COMPONENTES     3  SERVIDOR     4  LISTO'
$steps.ForeColor = [System.Drawing.Color]::FromArgb(185,213,255)
$steps.Font = New-Object System.Drawing.Font('Segoe UI',8,[System.Drawing.FontStyle]::Bold)
$steps.AutoSize = $true
$steps.Location = New-Object System.Drawing.Point(28,105)
$form.Controls.Add($steps)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'Preparando Recepción…'
$status.ForeColor = [System.Drawing.Color]::White
$status.Font = New-Object System.Drawing.Font('Segoe UI',11,[System.Drawing.FontStyle]::Bold)
$status.AutoSize = $true
$status.Location = New-Object System.Drawing.Point(28,151)
$form.Controls.Add($status)

$detail = New-Object System.Windows.Forms.Label
$detail.Text = 'Comprobando inicio seguro'
$detail.ForeColor = [System.Drawing.Color]::FromArgb(179,194,215)
$detail.Font = New-Object System.Drawing.Font('Segoe UI',9)
$detail.AutoSize = $true
$detail.Location = New-Object System.Drawing.Point(28,181)
$form.Controls.Add($detail)

$elapsed = New-Object System.Windows.Forms.Label
$elapsed.Text = ''
$elapsed.ForeColor = [System.Drawing.Color]::FromArgb(112,133,164)
$elapsed.Font = New-Object System.Drawing.Font('Segoe UI',8)
$elapsed.AutoSize = $true
$elapsed.Location = New-Object System.Drawing.Point(28,207)
$form.Controls.Add($elapsed)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Minimum = 0
$progress.Maximum = 100
$progress.Value = 5
$progress.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
$progress.Location = New-Object System.Drawing.Point(28,235)
$progress.Size = New-Object System.Drawing.Size(494,9)
$form.Controls.Add($progress)

$footer = New-Object System.Windows.Forms.Label
$footer.Text = 'Inicio seguro · actualizaciones verificadas antes de abrir'
$footer.ForeColor = [System.Drawing.Color]::FromArgb(100,121,150)
$footer.Font = New-Object System.Drawing.Font('Segoe UI',7)
$footer.AutoSize = $true
$footer.Location = New-Object System.Drawing.Point(28,255)
$form.Controls.Add($footer)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 100
$timer.Add_Tick({
    try {
        if (-not (Test-Path -LiteralPath $state)) { return }
        $j = Get-Content -LiteralPath $state -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json
        if ($j.closed) {
            $timer.Stop()
            $form.Close()
            return
        }
        $stage = [Math]::Max(1,[Math]::Min(4,[int]$j.stage))
        $status.Text = [string]$j.text
        $detail.Text = [string]$j.detail
        $elapsed.Text = ('{0:0} s · etapa {1}/4' -f [double]$j.elapsed,$stage)
        $progress.Value = [Math]::Max(5,[Math]::Min(100,$stage * 25))
    } catch {}
})
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
'''
            env = os.environ.copy()
            env["RP_SPLASH_STATE"] = str(self.native_state)
            encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
            self.native_proc = subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                cwd=str(ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_hidden_flags(),
            )
        except Exception as exc:
            self.native_proc = None
            _log("No se pudo abrir splash nativo de Windows: " + repr(exc))

    def _paint_stages(self):
        try:
            for idx, (num, txt) in enumerate(self.stage_labels, start=1):
                if idx < self.stage:
                    num.config(text="✓", fg="#a6edbf", bg="#21523a")
                    txt.config(fg="#7ebf98")
                elif idx == self.stage:
                    num.config(text=str(idx), fg="white", bg="#356fc2")
                    txt.config(fg="#b9d5ff")
                else:
                    num.config(text=str(idx), fg="#7e91ac", bg="#1b2a42")
                    txt.config(fg="#61738e")
        except Exception:
            pass

    def set_stage(self, step: int, text: str, detail: str = ""):
        self.stage = max(1, min(4, int(step)))
        self._paint_stages()
        self.set(text, detail)

    def set(self, text: str, detail: str = ""):
        self.phase = time.monotonic()
        self.warned = False
        self._native_text = str(text)
        self._native_detail = str(detail)
        try:
            if self.label:
                self.label.config(text=text)
            if self.detail:
                self.detail.config(text=detail)
        except Exception:
            pass
        self._native_write(force=True)
        self.pump()

    def pump(self):
        try:
            now = time.monotonic()
            if self.elapsed and now - self.started >= 2:
                self.elapsed.config(text=f"{now - self.started:.0f} s · etapa {self.stage}/4")
            if self.detail and now - self.phase >= 8 and not self.warned:
                self.warned = True
                self.detail.config(text="Está tardando más de lo habitual; seguimos comprobando de forma segura…")
            if self.canvas:
                self.spin = (self.spin + 1) % 24
                self.canvas.delete("progress")
                full = max(1, int(self.canvas.winfo_width() or 490))
                base = int(full * ((self.stage - 1) / 4.0))
                target = int(full * (self.stage / 4.0))
                pulse = int((target - base) * (self.spin / 23.0))
                self.canvas.create_rectangle(
                    0, 0, min(full, base + pulse), 6,
                    fill="#5d98ef", outline="", tags="progress"
                )
                if self.stage == 4:
                    self.canvas.delete("progress")
                    self.canvas.create_rectangle(
                        0, 0, full, 6, fill="#55b878", outline="", tags="progress"
                    )
            if self.root:
                self.root.update_idletasks()
                self.root.update()
            self._native_write()
        except Exception:
            pass

    def wait_minimum(self, seconds: float = MIN_SPLASH_SECONDS):
        deadline = self.started + max(0.0, float(seconds))
        while time.monotonic() < deadline:
            self.pump()
            time.sleep(0.05)

    def close(self):
        try:
            if self.root:
                self.root.destroy()
        except Exception:
            pass
        self.root = None
        try:
            self._native_write(closed=True, force=True)
            if self.native_proc is not None:
                try:
                    self.native_proc.wait(timeout=0.8)
                except Exception:
                    self.native_proc.terminate()
        except Exception:
            pass
        self.native_proc = None
        try:
            if self.native_state and self.native_state.exists():
                self.native_state.unlink()
        except Exception:
            pass
        self.native_state = None


def _open_webview() -> bool:
    try:
        import webview
    except Exception as exc:
        _log("pywebview no disponible: " + repr(exc))
        return False

    kwargs = {
        "gui": "edgechromium",
        "debug": False,
        "private_mode": False,
        "storage_path": str(_data_dir(ROOT) / "webview_profile"),
    }
    icon = ROOT / "static" / "doctor_icon.ico"
    if icon.exists():
        kwargs["icon"] = str(icon)

    try:
        try:
            window = webview.create_window(
                TITLE, URL, width=1360, height=840, min_size=(900, 620),
                resizable=True, text_select=True, maximized=True,
            )
            maximize_after = False
        except TypeError:
            window = webview.create_window(
                TITLE, URL, width=1360, height=840, min_size=(900, 620),
                resizable=True, text_select=True,
            )
            maximize_after = True

        if maximize_after:
            def on_start():
                try:
                    time.sleep(0.15)
                    window.maximize()
                except Exception:
                    pass
            webview.start(on_start, **kwargs)
        else:
            webview.start(**kwargs)
        return True
    except Exception as exc:
        _log("WebView2 falló: " + repr(exc) + " | " + traceback.format_exc(limit=4).replace("\n", " | "))
        return False


def _edge_exe() -> Path | None:
    if os.name != "nt":
        return None
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for p in candidates:
        if str(p) and p.exists():
            return p
    return None


def _open_fallback() -> None:
    edge = _edge_exe()
    if edge:
        try:
            subprocess.Popen(
                [str(edge), f"--app={URL}", "--start-maximized", "--disable-background-mode", "--no-first-run"],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_hidden_flags(),
            )
            return
        except Exception as exc:
            _log("Fallback Edge falló: " + repr(exc))
    webbrowser.open(URL, new=2)


def _message(text: str) -> None:
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x10)
            return
        except Exception:
            pass
    print(text, file=sys.stderr)



def _classify_launcher_error(exc: BaseException) -> str:
    text = (type(exc).__name__ + " " + str(exc)).lower()
    if "precheck_startup" in text:
        return "UPDATE-PRECHECK"
    if "modulenotfounderror" in text or "importerror" in text or "no module named" in text:
        return "STARTUP-IMPORT"
    if "python" in text and (".venv" in text or "dependencia" in text):
        return "STARTUP-PYTHON"
    if "puerto" in text or "port" in text:
        return "STARTUP-PORT"
    if "actualiza" in text or "sha" in text or "manifest" in text:
        return "UPDATE-FAILED"
    if "webview" in text:
        return "STARTUP-WEBVIEW"
    return "STARTUP-ERROR"


def _show_failure(title: str, code: str, detail: str, incident: str = "") -> None:
    """Diálogo legible con botón para copiar diagnóstico; fallback a MessageBox."""
    safe_detail = str(detail or "").strip()
    try:
        safe_detail = _rp_diag_sanitize(safe_detail)
    except Exception:
        pass
    payload = f"{code}\n{safe_detail}"
    if incident:
        payload += f"\nIncidente: {incident}"

    try:
        import tkinter as tk
        root = tk.Tk()
        root.title(TITLE)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.configure(bg="#111d33")
        w, h = 560, 330
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        outer = tk.Frame(root, bg="#111d33", padx=24, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(
            outer, text=title, font=("Segoe UI", 15, "bold"),
            fg="white", bg="#111d33"
        ).pack(anchor="w")
        tk.Label(
            outer, text=code, font=("Consolas", 10, "bold"),
            fg="#ffca76", bg="#2d2a28", padx=9, pady=5
        ).pack(anchor="w", pady=(10, 10))

        box = tk.Text(
            outer, height=9, wrap="word", font=("Segoe UI", 9),
            bg="#182842", fg="#d8e2f0", relief="flat", padx=10, pady=9
        )
        box.pack(fill="both", expand=True)
        box.insert("1.0", safe_detail or "No hay más detalle disponible.")
        box.config(state="disabled")

        actions = tk.Frame(outer, bg="#111d33")
        actions.pack(fill="x", pady=(12, 0))
        status = tk.Label(
            actions, text="", font=("Segoe UI", 8),
            fg="#86d5a2", bg="#111d33"
        )
        status.pack(side="left")

        def copy_diag():
            try:
                root.clipboard_clear()
                root.clipboard_append(payload)
                root.update()
                status.config(text="Diagnóstico copiado")
            except Exception:
                status.config(text="No se pudo copiar")

        tk.Button(
            actions, text="Copiar diagnóstico", command=copy_diag,
            font=("Segoe UI", 9, "bold"), bg="#2d67b1", fg="white",
            activebackground="#3978ca", activeforeground="white",
            relief="flat", padx=12, pady=7
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            actions, text="Cerrar", command=root.destroy,
            font=("Segoe UI", 9), bg="#24354e", fg="#d9e3ef",
            activebackground="#304763", activeforeground="white",
            relief="flat", padx=12, pady=7
        ).pack(side="right")
        root.mainloop()
        return
    except Exception:
        _message(f"{title}\n\nCódigo: {code}\n\n{safe_detail}")


def _relaunch_updated_launcher() -> None:
    """Abre el launcher recién escrito en disco y deja terminar el proceso viejo."""
    py = _python_exe(windowless=True)
    env = os.environ.copy()
    env["RP_PORT"] = str(APP_PORT)
    flags = _hidden_flags()
    if os.name == "nt":
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [str(py), str(ROOT / "ABRIR_RECEPCION.py")],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )



# ---------------------------------------------------------------------------
# v4.4.42 — guardia permanente de paquetes Python del runtime
# ---------------------------------------------------------------------------
def _rp_required_python_packages(root: Path = ROOT) -> list[dict]:
    try:
        manifest = _local_manifest(root)
    except Exception:
        manifest = {}
    values = manifest.get("required_python_packages") or []
    if not isinstance(values, list):
        return []
    out = []
    seen = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        module = str(item.get("import") or "").strip()
        spec = str(item.get("pip") or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", module):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:==[A-Za-z0-9_.+!-]+)?", spec):
            continue
        if module in seen:
            continue
        seen.add(module)
        out.append({"import": module, "pip": spec})
    return out


def _rp_python_import_ok(python_exe: Path, module: str) -> bool:
    try:
        proc = subprocess.run(
            [str(python_exe), "-c", "import importlib; importlib.import_module(" + repr(module) + ")"],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False, creationflags=_hidden_flags(),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _rp_ensure_python_runtime(root: Path = ROOT, python_exe: Path | None = None) -> list[str]:
    required = _rp_required_python_packages(root)
    if not required:
        return []
    py = Path(python_exe) if python_exe is not None else Path(_python_exe(windowless=False))
    if not py.is_file():
        raise RuntimeError("No se encontró el Python de .venv para reparar dependencias.")
    repaired = []
    for item in required:
        module = item["import"]
        spec = item["pip"]
        if _rp_python_import_ok(py, module):
            continue
        _log("Dependencia Python ausente; reparación automática: " + module, root)
        try:
            proc = subprocess.run(
                [str(py), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", spec],
                cwd=str(root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=180, check=False, creationflags=_hidden_flags(),
            )
        except Exception as exc:
            raise RuntimeError("No se pudo reparar la dependencia Python " + module + ": " + type(exc).__name__) from exc
        if proc.returncode != 0 or not _rp_python_import_ok(py, module):
            raise RuntimeError("No se pudo reparar la dependencia Python obligatoria: " + module)
        repaired.append(module)
        _log("Dependencia Python reparada correctamente: " + module, root)
    return repaired

def main() -> None:
    _set_windows_identity()
    _ensure_embedded_python_root(ROOT)
    splash = Splash()
    splash.set_stage(1, "Verificando actualización…", "Comprobando inicio seguro")
    _ensure_windows_shortcuts()
    _choose_app_port()

    handle, already = _acquire_mutex()
    if already:
        force_mandatory = False
        try:
            local_v = _local_package_version(ROOT)
            remote_preview = _fetch_manifest(DEFAULT_MANIFEST_URL, attempts=3, timeout=8.0)
            remote_v = str(remote_preview.get("version") or "").strip()
            force_mandatory = bool(remote_preview.get("mandatory")) and _vtuple(remote_v) > _vtuple(local_v)
        except Exception:
            force_mandatory = False

        if not force_mandatory:
            splash.set_stage(4, "Todo listo", "Recepción ya estaba abierta")
            splash.wait_minimum(MIN_SPLASH_SECONDS)
            splash.close()
            _focus_existing_window()
            _release_mutex(handle)
            return

        _request_close_existing_window()
        _release_mutex(handle)
        handle = None

        deadline = time.time() + 15.0
        while time.time() < deadline:
            candidate, busy = _acquire_mutex()
            if not busy:
                handle = candidate
                break
            _release_mutex(candidate)
            time.sleep(0.20)

        if handle is None:
            splash.set_stage(4, "Actualización pendiente", "Cierra Recepción y vuelve a abrirla")
            splash.wait_minimum(MIN_SPLASH_SECONDS)
            splash.close()
            _message("Hay una actualización obligatoria pendiente. Cierra Recepción completamente y vuelve a abrirla.")
            return

    try:
        _rp_diag_flush_outbox(max_items=3)
    except Exception as diag_exc:
        _log(
            "No se pudo reenviar diagnóstico pendiente: "
            + _rp_diag_sanitize(type(diag_exc).__name__ + ": " + str(diag_exc)),
            ROOT,
        )

    try:
        splash.set_stage(1, "Verificando actualización…", "Comprobando canal, firma y versión candidata")
        result = check_and_apply_update(ROOT, splash=splash)

        if result.get("blocked"):
            splash.close()
            blocked_text = result.get("error") or "La instalación local necesita reparación."
            diag = _rp_diag_report("update_blocked", RuntimeError(blocked_text))
            _show_failure(
                "No se pudo preparar Recepción",
                "UPDATE-BLOCKED",
                blocked_text,
                str(diag.get("incident_id") or ""),
            )
            return

        if result.get("quarantined"):
            splash.set(
                "Actualización en cuarentena",
                "La versión candidata falló previamente; abriendo la última versión estable",
            )
            time.sleep(0.35)
        elif result.get("candidate_failed"):
            splash.set(
                "Actualización descartada de forma segura",
                "La copia de prueba falló; tu versión estable no fue reemplazada",
            )
            time.sleep(0.35)

        updated_paths = {
            str(p).replace("\\", "/").lower()
            for p in result.get("paths", [])
        }
        if result.get("updated") and "abrir_recepcion.py" in updated_paths:
            splash.set_stage(
                1,
                "Aplicando lanzador nuevo…",
                f"Versión {result.get('version') or ''} · reinicio seguro",
            )
            splash.wait_minimum(MIN_SPLASH_SECONDS)
            splash.close()
            _release_mutex(handle)
            handle = None
            _relaunch_updated_launcher()
            return

        if result.get("updated"):
            downloaded = int(result.get("downloaded_files") or 0)
            declared = int(result.get("declared_files") or 0)
            detail = f"{downloaded} archivo(s) cambiado(s)"
            if declared:
                detail += f" de {declared}"
            splash.set("Actualización verificada", detail)
            if "app.py" in updated_paths:
                _stop_server()

        splash.set_stage(2, "Verificando componentes…", "Python y dependencias del entorno")
        repaired_python = _rp_ensure_python_runtime(ROOT)
        if repaired_python:
            splash.set("Componentes reparados", "Preparando el inicio local")

        expected = _expected_app_version(ROOT)
        current = _running_version(timeout=0.55)

        if current == expected and _focus_existing_window():
            _write_state(
                ROOT,
                startup_verified_version=expected,
                last_known_good_app_version=expected,
                last_known_good_package_version=_local_package_version(ROOT),
                last_known_good_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                startup_rollback=False,
                installation_consistent=_installation_consistent(ROOT),
            )
            splash.set_stage(4, "Todo listo", "Recepción ya estaba iniciada")
            splash.wait_minimum(MIN_SPLASH_SECONDS)
            return

        if current != expected:
            splash.set_stage(3, "Iniciando servidor local…", "Comprobando que app.py permanezca activo")
            if current is not None:
                _stop_server()

            proc = _start_server()
            if not _wait_server(expected, 15.0, splash, process=proc):
                # Si el proceso murió, no perdemos otros 16 s repitiendo un error
                # determinista de importación/arranque.
                died = False
                try:
                    died = proc is not None and proc.poll() is not None
                except Exception:
                    pass

                if not died:
                    _stop_server()
                    splash.set("Reintentando servidor…", "Segundo intento automático")
                    proc = _start_server()
                    ok = _wait_server(expected, 10.0, splash, process=proc)
                else:
                    ok = False

                if not ok:
                    backup_path = str(result.get("backup") or "") if isinstance(result, dict) else ""
                    updated_list = list(result.get("paths") or []) if isinstance(result, dict) else []

                    if not backup_path:
                        try:
                            st = _load_json(_data_dir(ROOT) / "auto_update_state.json")
                            if str(st.get("last_installed_version") or "") == str(_local_package_version(ROOT) or ""):
                                backup_path = str(st.get("last_backup") or "")
                                if not updated_list:
                                    updated_list = list(st.get("last_updated_paths") or [])
                        except Exception:
                            backup_path = ""

                    if backup_path and bool(result.get("updated")):
                        splash.set(
                            "Recuperando última versión buena…",
                            "El servidor nuevo no inició; restaurando automáticamente",
                        )
                        _stop_server()
                        if not _restore_update_backup(ROOT, backup_path, updated_list):
                            raise RuntimeError(
                                "El backend no respondió y no se pudo recuperar el respaldo previo."
                            )
                        expected = _expected_app_version(ROOT)
                        proc = _start_server()
                        splash.set("Versión estable restaurada", "Comprobando arranque recuperado")
                        if not _wait_server(expected, 15.0, splash, process=proc):
                            raise RuntimeError(
                                "La versión anterior fue restaurada, pero tampoco respondió.\n"
                                + (_LAST_STARTUP_FAILURE or "")
                            )
                    else:
                        raise RuntimeError(
                            "El servidor local no pudo iniciar.\n"
                            + (_LAST_STARTUP_FAILURE or "Sin detalle adicional.")
                        )

        _write_state(
            ROOT,
            startup_verified_version=expected,
            last_known_good_app_version=expected,
            last_known_good_package_version=_local_package_version(ROOT),
            last_known_good_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            startup_rollback=False,
            installation_consistent=_installation_consistent(ROOT),
        )

        splash.set_stage(4, "Todo listo", "Abriendo Recepción")
        splash.wait_minimum(MIN_SPLASH_SECONDS)
        splash.close()

        if not _open_webview():
            _open_fallback()

    except Exception as exc:
        _log(
            "Fallo general del launcher: "
            + repr(exc) + " | " + traceback.format_exc(limit=6).replace("\n", " | ")
        )
        diag = _rp_diag_report("launcher_fatal", exc)
        incident = str(diag.get("incident_id") or "")
        code = _classify_launcher_error(exc)
        detail = str(exc)
        if _LAST_STARTUP_FAILURE and _LAST_STARTUP_FAILURE not in detail:
            detail += "\n\n" + _LAST_STARTUP_FAILURE
        splash.close()
        _show_failure(
            "No se pudo iniciar Recepción",
            code,
            detail + "\n\nEl detalle técnico también quedó en data\\launcher_errors.log.",
            incident,
        )
    finally:
        splash.close()
        _release_mutex(handle)


def _selftest_mutex_holder(name: str, ready_file: str) -> int:
    handle, already = _acquire_mutex(name)
    if already:
        _release_mutex(handle)
        return 31
    try:
        Path(ready_file).write_text("ready", encoding="utf-8")
        time.sleep(4.0)
        return 0
    finally:
        _release_mutex(handle)


def _selftest_mutex_probe(name: str) -> int:
    handle, already = _acquire_mutex(name)
    try:
        return 0 if already else 32
    finally:
        _release_mutex(handle)

# -------------------- SELF TESTS --------------------

class _TestHandler(BaseHTTPRequestHandler):
    files = {}

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in self.files:
            body, ctype = self.files[path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


def _test_server(files: dict):
    class H(_TestHandler):
        pass
    H.files = files
    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _write_test_install(root: Path, package="4.3.56", app="4.3.54"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "app.py").write_text(f'APP_VERSION = "{app}"\nprint("app")\n', encoding="utf-8")
    (root / "ABRIR_RECEPCION.py").write_text('LAUNCHER_VERSION="old"\n', encoding="utf-8")
    (root / "update_manifest.json").write_text(json.dumps({
        "product": PRODUCT,
        "version": package,
        "app_version": app,
        "runtime_version": app,
        "copy": ["update_manifest.json", "ABRIR_RECEPCION.py"],
    }), encoding="utf-8")


def _remote_test_files(base: str, *, bad_sha=False, protected=False):
    launcher = b'LAUNCHER_VERSION="new"\n'
    inner = json.dumps({
        "product": PRODUCT,
        "version": "4.3.57",
        "app_version": "4.3.54",
        "runtime_version": "4.3.54",
        "copy": ["update_manifest.json", "ABRIR_RECEPCION.py"],
    }, ensure_ascii=False, indent=2).encode()
    path = "data/evil.txt" if protected else "ABRIR_RECEPCION.py"
    payload = b"evil" if protected else launcher
    sha = hashlib.sha256(payload).hexdigest()
    if bad_sha:
        sha = "0" * 64
    manifest = {
        "product": PRODUCT,
        "version": "4.3.57",
        "files": [
            {"path": path, "url": base + "/payload", "sha256": sha, "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": base + "/inner", "sha256": hashlib.sha256(inner).hexdigest(), "encoding": "utf-8"},
        ],
    }
    return manifest, payload, inner


def run_self_tests() -> int:
    passed = []

    def ok(name):
        passed.append(name)
        print("PASS", name)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "install"
        _write_test_install(root)
        server, base = _test_server({})
        try:
            manifest, payload, inner = _remote_test_files(base)
            _TestHandler.files = {}
            # handler class copied files at creation; update actual RequestHandlerClass
            server.RequestHandlerClass.files = {
                "/manifest": (json.dumps(manifest).encode(), "application/json"),
                "/payload": (payload, "text/plain"),
                "/inner": (inner, "application/json"),
            }

            r = check_and_apply_update(root, base + "/manifest", attempts=1, timeout=2, allow_test_sources=True)
            assert r["ok"] and r["updated"] and _local_package_version(root) == "4.3.57"
            assert (root / "ABRIR_RECEPCION.py").read_bytes() == payload
            assert _installation_consistent(root)
            ok("clean_update")

            r2 = check_and_apply_update(root, base + "/manifest", attempts=1, timeout=2, allow_test_sources=True)
            assert r2["ok"] and not r2["updated"]
            ok("second_open_no_redownload")
        finally:
            server.shutdown()
            server.server_close()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "install"
        _write_test_install(root)
        old = (root / "ABRIR_RECEPCION.py").read_bytes()
        server, base = _test_server({})
        try:
            manifest, payload, inner = _remote_test_files(base, bad_sha=True)
            server.RequestHandlerClass.files = {
                "/manifest": (json.dumps(manifest).encode(), "application/json"),
                "/payload": (payload, "text/plain"),
                "/inner": (inner, "application/json"),
            }
            r = check_and_apply_update(root, base + "/manifest", attempts=1, timeout=2, allow_test_sources=True)
            assert r["ok"] and r.get("deferred") and (root / "ABRIR_RECEPCION.py").read_bytes() == old
            ok("sha_mismatch_keeps_local")
        finally:
            server.shutdown(); server.server_close()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "install"
        _write_test_install(root)
        old = (root / "ABRIR_RECEPCION.py").read_bytes()
        server, base = _test_server({})
        try:
            invalid = b"def broken(:\n"
            inner = json.dumps({
                "product": PRODUCT,
                "version": "4.3.57",
                "app_version": "4.3.54",
                "runtime_version": "4.3.54",
                "copy": ["update_manifest.json", "ABRIR_RECEPCION.py"],
            }, ensure_ascii=False, indent=2).encode()
            manifest = {
                "product": PRODUCT,
                "version": "4.3.57",
                "files": [
                    {"path": "ABRIR_RECEPCION.py", "url": base + "/payload",
                     "sha256": hashlib.sha256(invalid).hexdigest(), "encoding": "utf-8"},
                    {"path": "update_manifest.json", "url": base + "/inner",
                     "sha256": hashlib.sha256(inner).hexdigest(), "encoding": "utf-8"},
                ],
            }
            server.RequestHandlerClass.files = {
                "/manifest": (json.dumps(manifest).encode(), "application/json"),
                "/payload": (invalid, "text/plain"),
                "/inner": (inner, "application/json"),
            }
            r = check_and_apply_update(
                root, base + "/manifest", attempts=1, timeout=2, allow_test_sources=True
            )
            assert r["ok"] and r.get("deferred") and (root / "ABRIR_RECEPCION.py").read_bytes() == old
            ok("invalid_python_keeps_local")
        finally:
            server.shutdown(); server.server_close()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "install"
        _write_test_install(root)
        server, base = _test_server({})
        try:
            manifest, payload, inner = _remote_test_files(base, protected=True)
            server.RequestHandlerClass.files = {
                "/manifest": (json.dumps(manifest).encode(), "application/json"),
                "/payload": (payload, "text/plain"),
                "/inner": (inner, "application/json"),
            }
            r = check_and_apply_update(root, base + "/manifest", attempts=1, timeout=2, allow_test_sources=True)
            assert r["ok"] and r.get("deferred") and not (root / "data" / "evil.txt").exists()
            ok("protected_paths")
        finally:
            server.shutdown(); server.server_close()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "install"
        _write_test_install(root)
        old_launcher = (root / "ABRIR_RECEPCION.py").read_bytes()
        old_manifest = (root / "update_manifest.json").read_bytes()
        server, base = _test_server({})
        try:
            manifest, payload, inner = _remote_test_files(base)
            server.RequestHandlerClass.files = {
                "/manifest": (json.dumps(manifest).encode(), "application/json"),
                "/payload": (payload, "text/plain"),
                "/inner": (inner, "application/json"),
            }
            remote = _fetch_manifest(base + "/manifest", attempts=1, timeout=2)
            try:
                _apply_remote(remote, root, attempts=1, timeout=2, test_fail_after=1, allow_test_sources=True)
                raise AssertionError("rollback test did not fail")
            except RuntimeError as exc:
                assert "Fallo simulado" in str(exc)
            assert (root / "ABRIR_RECEPCION.py").read_bytes() == old_launcher
            assert (root / "update_manifest.json").read_bytes() == old_manifest
            ok("rollback")
        finally:
            server.shutdown(); server.server_close()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "install"
        _write_test_install(root)
        r = check_and_apply_update(root, "http://127.0.0.1:9/nope", attempts=1, timeout=0.2)
        assert r["ok"] and r.get("deferred") and _installation_consistent(root)
        ok("offline_local_start_allowed")

    # Static architecture checks.
    import ast
    source = Path(__file__).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not ({"AUTOACTUALIZAR", "_AUTOACTUALIZAR_31", "_ABRIR_RECEPCION_451"} & imported)
    ok("no_auxiliary_imports")
    assert "PRECHECK_STARTUP" in source and "_trial_runtime" in source
    assert "candidate_quarantined" in source and "last_known_good_app_version" in source
    assert "downloaded_files" in source and "Copiar diagnóstico" in source
    ok("v453_safe_launcher_features")

    if os.name == "nt":
        name = MUTEX_NAME + "_SELFTEST_" + str(os.getpid()) + "_" + str(time.time_ns())
        with tempfile.TemporaryDirectory() as mtd:
            ready = str(Path(mtd) / "ready.txt")
            holder = subprocess.Popen(
                [sys.executable, str(Path(__file__)), "--self-test-mutex-holder", name, ready],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            deadline = time.time() + 5
            while time.time() < deadline and not Path(ready).exists():
                if holder.poll() is not None:
                    break
                time.sleep(0.05)
            assert Path(ready).exists(), "holder no adquirió mutex"
            probe = subprocess.run(
                [sys.executable, str(Path(__file__)), "--self-test-mutex-probe", name],
                capture_output=True, text=True, timeout=5,
            )
            assert probe.returncode == 0, f"segundo proceso no detectó mutex: {probe.returncode}"
            holder.wait(timeout=8)
            assert holder.returncode == 0
            ok("windows_two_process_single_instance")
    else:
        print("SKIP windows_two_process_single_instance (not Windows)")

    print(f"SELFTEST OK: {len(passed)} pruebas")
    return 0



# ---------------------------------------------------------------------------
# v4.4.37 — guardia permanente de dependencias del runtime
# ---------------------------------------------------------------------------
# Parche mínimo sobre el launcher dinámico 4.4.32. No cambia selección de
# puertos, RP_PORT, mutex, WebView/Edge ni el flujo de arranque.
_RP_V4437_OLD_INSTALLATION_CONSISTENT = _installation_consistent
_RP_V4437_OLD_STAGE_UPDATE = _stage_update


def _rp_v4437_required_files(root: Path = ROOT) -> list[str]:
    try: manifest = _local_manifest(root)
    except Exception: manifest = {}
    values = manifest.get("required_dependencies") or []
    if not isinstance(values, list): return []
    out=[]
    for value in values:
        rel=str(value or "").replace("\\","/").lstrip("/")
        if rel and rel not in out: out.append(rel)
    return out


def _rp_v4437_app_local_imports(app_path: Path) -> set[str]:
    try:
        tree=ast.parse(app_path.read_text(encoding="utf-8-sig"),filename=str(app_path))
    except Exception:
        return set()
    result=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for alias in node.names:
                name=str(alias.name or "").split(".",1)[0]
                if name.startswith("app_"): result.add(name+".py")
        elif isinstance(node,ast.ImportFrom) and node.module:
            name=str(node.module).split(".",1)[0]
            if name.startswith("app_"): result.add(name+".py")
    return result


def _rp_v4437_dependency_file_ok(path: Path) -> bool:
    if not path.is_file(): return False
    if path.suffix.lower()==".py":
        try: compile(path.read_text(encoding="utf-8-sig"),str(path),"exec")
        except Exception: return False
    return True


def _installation_consistent(root: Path = ROOT) -> bool:
    if not _RP_V4437_OLD_INSTALLATION_CONSISTENT(root): return False
    required=set(_rp_v4437_required_files(root))
    required.update(_rp_v4437_app_local_imports(root/"app.py"))
    for rel in required:
        try: target=_safe_target(root,rel)
        except Exception: return False
        if not _rp_v4437_dependency_file_ok(target):
            _log(f"Dependencia obligatoria ausente o dañada: {rel}",root)
            return False
    return True


def _stage_update(remote: dict, root: Path = ROOT, *, attempts: int = 3,
                  timeout: float = 10.0, allow_test_sources: bool = False):
    stage, staged = _RP_V4437_OLD_STAGE_UPDATE(
        remote, root, attempts=attempts, timeout=timeout,
        allow_test_sources=allow_test_sources
    )
    try:
        changed_paths = {
            str(x.get("rel") or "").replace("\\", "/")
            for x in staged
        }
        declared_paths = {
            str(item.get("path") or "").replace("\\", "/").lstrip("/")
            for item in (remote.get("files") or [])
            if str(item.get("path") or "").strip()
        }

        staged_app = stage / "app.py"
        app_for_check = staged_app if staged_app.is_file() else (root / "app.py")
        if app_for_check.is_file():
            imports = _rp_v4437_app_local_imports(app_for_check)
            missing = []
            for rel in imports:
                if rel in declared_paths:
                    continue
                try:
                    if _rp_v4437_dependency_file_ok(_safe_target(root, rel)):
                        continue
                except Exception:
                    pass
                missing.append(rel)
            if missing:
                raise RuntimeError(
                    "Actualización incompleta: app.py requiere archivo(s) no disponibles: "
                    + ", ".join(sorted(missing))
                )

        inner = stage / "update_manifest.json"
        if inner.is_file():
            data = json.loads(inner.read_text(encoding="utf-8-sig"))
            req = data.get("required_dependencies") or []
            if not isinstance(req, list):
                raise RuntimeError("required_dependencies debe ser una lista")
            absent = []
            for value in req:
                rel = str(value or "").replace("\\", "/").lstrip("/")
                if not rel:
                    continue
                if rel in declared_paths:
                    continue
                try:
                    if _rp_v4437_dependency_file_ok(_safe_target(root, rel)):
                        continue
                except Exception:
                    pass
                absent.append(rel)
            if absent:
                raise RuntimeError(
                    "Manifest de actualización incompleto; faltan dependencias obligatorias: "
                    + ", ".join(sorted(set(absent)))
                )
        return stage, staged
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise



# ---------------------------------------------------------------------------
# v4.4.38 — diagnóstico automático privado de fallos fatales
# ---------------------------------------------------------------------------
# Solo se ejecuta cuando Recepción NO puede arrancar (o para reenviar una cola
# pendiente). No sube .env, SQLite, Excel, pacientes, citas ni facturas.
# Antes de salir de la PC los textos pasan por sanitización de secretos/PII.
_RP_DIAGNOSTICS_VERSION = "4.4.41-private-neon-capability-1"
_RP_DIAGNOSTIC_TABLE = "rp_diagnostics_incidents"
_RP_DIAGNOSTIC_DEDUPE_SECONDS = 1800


def _rp_diag_enabled() -> bool:
    raw = str(os.getenv("RP_DIAGNOSTICS_ENABLED", "1") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def _rp_diag_sanitize(value: object) -> str:
    text = str(value or "")
    try:
        text = text.replace(str(ROOT), "[APP_ROOT]")
    except Exception:
        pass
    # Credenciales/URLs de base de datos completas.
    text = re.sub(r"(?i)postgres(?:ql)?://[^\\s\\'\\\"<>\\]]+", "[DATABASE_URL_REDACTADA]", text)
    # Cabeceras y claves comunes.
    text = re.sub(
        r"(?i)\\b(database_url|neon_database_url|password|passwd|secret|token|api[_-]?key|authorization)\\b\\s*[:=]\\s*([^\\s,;|]+)",
        lambda m: f"{m.group(1)}=[REDACTADO]",
        text,
    )
    text = re.sub(r"(?i)\\bBearer\\s+[A-Za-z0-9._~+\\/=-]+", "Bearer [REDACTADO]", text)
    # Correos.
    text = re.sub(r"(?i)\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b", "[CORREO_REDACTADO]", text)
    # Usuario de Windows en rutas.
    text = re.sub(r"(?i)C:\\\\Users\\\\[^\\\\\\r\\n\\t ]+", r"C:\\Users\\[USUARIO]", text)
    # Campos que podrían contener datos de pacientes.
    text = re.sub(
        r"(?i)\\b(c[eé]dula|ruc|correo|e-?mail|celular|tel[eé]fono|patient_id|patient|cliente)\\b\\s*[:=]\\s*[^,\\r\\n|]+",
        lambda m: m.group(1) + "=[REDACTADO]",
        text,
    )
    # Cédulas, teléfonos, RUC, IDs largos. Puertos/líneas cortas no se alteran.
    text = re.sub(r"(?<!\\d)\\d{7,20}(?!\\d)", "[NUMERO_REDACTADO]", text)

    def _ip_repl(match):
        ip = match.group(0)
        return ip if ip.startswith("127.") else "[IP_REDACTADA]"

    text = re.sub(r"(?<!\\d)(?:\\d{1,3}\\.){3}\\d{1,3}(?!\\d)", _ip_repl, text)
    return text


def _rp_diag_read_tail(path: Path, *, max_bytes: int = 131072, max_lines: int = 350, max_chars: int = 48000) -> str:
    try:
        if not path.is_file():
            return ""
        size = path.stat().st_size
        with path.open("rb") as fh:
            start = max(0, size - max_bytes)
            fh.seek(start)
            raw = fh.read(max_bytes)
        text = raw.decode("utf-8", errors="replace")
        if start > 0 and "\n" in text:
            text = text.split("\n", 1)[1]
        text = "\n".join(text.splitlines()[-max_lines:])
        return _rp_diag_sanitize(text)[-max_chars:]
    except Exception as exc:
        return "[No se pudo leer log: " + _rp_diag_sanitize(type(exc).__name__) + "]"


def _rp_diag_connection_url() -> str:
    for key in ("DATABASE_URL", "NEON_DATABASE_URL"):
        value = str(os.getenv(key, "") or "").strip()
        if value:
            return value
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() in {"DATABASE_URL", "NEON_DATABASE_URL"}:
                return value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _rp_diag_db_connect():
    """Abre Neon con el primer driver disponible; no depende de un único driver."""
    url = _rp_diag_connection_url()
    if not url:
        raise RuntimeError("Conexión privada de diagnóstico no configurada")
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in {"postgres", "postgresql", "postgresql+pg8000", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError("Esquema de base privada no compatible")
    base_scheme = scheme.split("+", 1)[0]
    clean_parts = parts._replace(scheme=base_scheme)
    user = urllib.parse.unquote(parts.username or "")
    password = urllib.parse.unquote(parts.password or "")
    host = parts.hostname or ""
    database = urllib.parse.unquote((parts.path or "/").lstrip("/")) or "neondb"
    if not user or not password or not host:
        raise RuntimeError("Conexión privada incompleta")

    failures = []
    try:
        from pg8000 import dbapi as _pg8000
        import ssl as _ssl
        return _pg8000.connect(
            user=user, password=password, host=host, port=int(parts.port or 5432),
            database=database, ssl_context=_ssl.create_default_context(), timeout=12,
        )
    except Exception as exc:
        failures.append("pg8000:" + type(exc).__name__)

    dsn = urllib.parse.urlunsplit(clean_parts)
    try:
        import psycopg as _psycopg
        return _psycopg.connect(dsn, connect_timeout=12)
    except Exception as exc:
        failures.append("psycopg:" + type(exc).__name__)

    try:
        import psycopg2 as _psycopg2
        # psycopg2 puede no entender channel_binding en versiones antiguas.
        q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if str(k).lower() != "channel_binding"]
        dsn2 = urllib.parse.urlunsplit((base_scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment))
        return _psycopg2.connect(dsn2, connect_timeout=12)
    except Exception as exc:
        failures.append("psycopg2:" + type(exc).__name__)

    raise RuntimeError("No se pudo abrir transporte Neon [" + ", ".join(failures) + "]")


def _rp_diag_paths() -> tuple[Path, Path, Path]:
    data = _data_dir(ROOT)
    return data / "diagnostic_outbox", data / "diagnostic_last.json", data / "last_diagnostic_incident.txt"


def _rp_diag_machine_hash() -> str:
    seed = (str(os.getenv("COMPUTERNAME", "")) + "|" + str(ROOT)).encode("utf-8", errors="ignore")
    return hashlib.sha256(seed).hexdigest()[:20]


def _rp_diag_update_state() -> str:
    path = _data_dir(ROOT) / "auto_update_state.json"
    return _rp_diag_read_tail(path, max_bytes=32768, max_lines=120, max_chars=16000)


def _rp_diag_build_payload(stage: str, exc: BaseException) -> dict:
    launcher_log = _rp_diag_read_tail(_data_dir(ROOT) / "launcher_errors.log")
    backend_log = _rp_diag_read_tail(_data_dir(ROOT) / "backend_startup.log")
    err = _rp_diag_sanitize(str(exc) or repr(exc))[:6000]
    error_class = _rp_diag_sanitize(type(exc).__name__)[:120]
    clean_stage = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(stage or "launcher_fatal"))[:80]
    signature_source = (clean_stage + "|" + error_class + "|" + err + "|" + backend_log[-5000:]).encode("utf-8", errors="ignore")
    signature = hashlib.sha256(signature_source).hexdigest()
    now_epoch = int(time.time())
    suffix = hashlib.sha256(os.urandom(32)).hexdigest()[:32].upper()
    incident_id = "INC-" + time.strftime("%Y%m%d-%H%M%S", time.localtime(now_epoch)) + "-" + suffix
    metadata = {
        "diagnostics_version": _RP_DIAGNOSTICS_VERSION,
        "port": int(APP_PORT or 0),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": os.name,
        "source_epoch": now_epoch,
    }
    return {
        "incident_id": incident_id,
        "created_epoch": now_epoch,
        "package_version": _local_package_version(ROOT),
        "app_version": _installed_app_version(ROOT),
        "launcher_version": str(LAUNCHER_VERSION),
        "stage": clean_stage,
        "error_class": error_class,
        "error_message": err,
        "signature": signature,
        "launcher_log": launcher_log,
        "backend_log": backend_log,
        "update_state": _rp_diag_update_state(),
        "machine_hash": _rp_diag_machine_hash(),
        "metadata": metadata,
    }


def _rp_diag_upload_payload_direct(payload: dict) -> None:
    conn = _rp_diag_db_connect()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS rp_diagnostics_incidents (
                incident_id VARCHAR(64) PRIMARY KEY,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                source_created_epoch BIGINT,
                package_version VARCHAR(32),
                app_version VARCHAR(32),
                launcher_version VARCHAR(120),
                stage VARCHAR(80),
                error_class VARCHAR(120),
                error_message TEXT,
                signature VARCHAR(64),
                launcher_log TEXT,
                backend_log TEXT,
                update_state TEXT,
                machine_hash VARCHAR(64),
                metadata_json TEXT
            )"""
        )
        cur.execute(
            """INSERT INTO rp_diagnostics_incidents (
                incident_id, source_created_epoch, package_version, app_version,
                launcher_version, stage, error_class, error_message, signature,
                launcher_log, backend_log, update_state, machine_hash, metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (incident_id) DO UPDATE SET
                received_at=NOW(), error_message=EXCLUDED.error_message,
                launcher_log=EXCLUDED.launcher_log, backend_log=EXCLUDED.backend_log,
                update_state=EXCLUDED.update_state, metadata_json=EXCLUDED.metadata_json""",
            (
                str(payload.get("incident_id") or ""), int(payload.get("created_epoch") or 0),
                str(payload.get("package_version") or "")[:32], str(payload.get("app_version") or "")[:32],
                str(payload.get("launcher_version") or "")[:120], str(payload.get("stage") or "")[:80],
                str(payload.get("error_class") or "")[:120], str(payload.get("error_message") or "")[:6000],
                str(payload.get("signature") or "")[:64], str(payload.get("launcher_log") or "")[:48000],
                str(payload.get("backend_log") or "")[:48000], str(payload.get("update_state") or "")[:16000],
                str(payload.get("machine_hash") or "")[:64],
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, separators=(",", ":"))[:8000],
            ),
        )
        conn.commit()
    finally:
        try:
            if cur is not None: cur.close()
        except Exception:
            pass
        try: conn.close()
        except Exception: pass


def _rp_diag_upload_via_venv(payload: dict) -> None:
    """Segundo camino: ejecuta el mismo uploader con el Python real de .venv."""
    outbox, _, _ = _rp_diag_paths()
    outbox.mkdir(parents=True, exist_ok=True)
    incident = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(payload.get("incident_id") or "INC"))[:80]
    temp = outbox / (".transport_" + incident + "_" + str(os.getpid()) + ".json")
    _rp_diag_save_json(temp, payload)
    try:
        py = _python_exe(windowless=False)
        flags = _hidden_flags()
        proc = subprocess.run(
            [str(py), str(ROOT / "ABRIR_RECEPCION.py"), "--diag-upload-file", str(temp)],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=28, check=False, creationflags=flags,
        )
        if proc.returncode != 0:
            marker = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["sin-detalle"]
            safe = re.sub(r"[^A-Za-z0-9_.:-]+", "_", marker[0])[:120]
            raise RuntimeError("Uploader .venv falló: " + safe)
    finally:
        try: temp.unlink(missing_ok=True)
        except Exception: pass


def _rp_diag_upload_payload(payload: dict) -> None:
    first = None
    try:
        _rp_diag_upload_payload_direct(payload)
        return
    except Exception as exc:
        first = exc
    try:
        _rp_diag_upload_via_venv(payload)
        return
    except Exception as second:
        raise RuntimeError(
            "Transporte diagnóstico agotó rutas [directo=" + type(first).__name__ +
            ", venv=" + type(second).__name__ + "]"
        ) from second


def _rp_diag_load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _rp_diag_save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _rp_diag_mark_last(payload: dict, status: str) -> dict:
    _, last_path, id_path = _rp_diag_paths()
    result = {
        "incident_id": str(payload.get("incident_id") or ""),
        "signature": str(payload.get("signature") or ""),
        "created_epoch": int(payload.get("created_epoch") or time.time()),
        "status": str(status),
    }
    try:
        _rp_diag_save_json(last_path, result)
        id_path.parent.mkdir(parents=True, exist_ok=True)
        id_path.write_text(result["incident_id"] + "\n", encoding="utf-8")
    except Exception:
        pass
    return result


def _rp_diag_flush_outbox(max_items: int = 3) -> int:
    if not _rp_diag_enabled():
        return 0
    outbox, last_path, _ = _rp_diag_paths()
    if not outbox.is_dir():
        return 0
    sent = 0
    for path in sorted(outbox.glob("INC-*.json"))[:max(0, int(max_items))]:
        try:
            payload = _rp_diag_load_json(path)
            if not payload.get("incident_id"):
                path.unlink(missing_ok=True)
                continue
            _rp_diag_upload_payload(payload)
            path.unlink(missing_ok=True)
            sent += 1
            last = _rp_diag_load_json(last_path)
            if last.get("incident_id") == payload.get("incident_id"):
                _rp_diag_mark_last(payload, "sent")
        except Exception as exc:
            _log("Diagnóstico pendiente no enviado: " + _rp_diag_sanitize(type(exc).__name__ + ": " + str(exc)), ROOT)
            break
    return sent


def _rp_diag_report(stage: str, exc: BaseException) -> dict:
    if not _rp_diag_enabled():
        return {"incident_id": "", "status": "disabled"}
    payload = _rp_diag_build_payload(stage, exc)
    outbox, last_path, _ = _rp_diag_paths()
    last = _rp_diag_load_json(last_path)
    if (
        last.get("signature") == payload.get("signature")
        and int(payload["created_epoch"]) - int(last.get("created_epoch") or 0) <= _RP_DIAGNOSTIC_DEDUPE_SECONDS
        and last.get("incident_id")
    ):
        # Evita inundar Neon si el usuario intenta abrir varias veces el mismo fallo.
        _rp_diag_flush_outbox(max_items=3)
        refreshed = _rp_diag_load_json(last_path)
        return refreshed or last

    outbox.mkdir(parents=True, exist_ok=True)
    queued = outbox / (payload["incident_id"] + ".json")
    _rp_diag_save_json(queued, payload)
    status = "queued"
    try:
        _rp_diag_upload_payload(payload)
        queued.unlink(missing_ok=True)
        status = "sent"
    except Exception as upload_exc:
        # Nunca registrar credenciales ni URL: solo tipo/mensaje ya sanitizado.
        _log("Diagnóstico en cola: " + _rp_diag_sanitize(type(upload_exc).__name__ + ": " + str(upload_exc)), ROOT)
    return _rp_diag_mark_last(payload, status)


def _rp_diag_message(base: str, result: dict) -> str:
    incident = str((result or {}).get("incident_id") or "").strip()
    status = str((result or {}).get("status") or "")
    if not incident:
        return base
    if status == "sent":
        return base + "\n\nDiagnóstico enviado automáticamente: " + incident
    return base + "\n\nDiagnóstico preparado: " + incident + "\nQuedó guardado localmente y se reintentará automáticamente en el próximo arranque."



# v4.4.38 privacy filter revision 2 — probado con secretos y PII sintéticos.
def _rp_diag_sanitize(value: object) -> str:
    text = str(value or "")
    try:
        text = text.replace(str(ROOT), "[APP_ROOT]")
    except Exception:
        pass

    # 1) Credenciales completas de Postgres/Neon antes de cualquier otro filtro.
    text = re.sub(r"(?i)postgres(?:ql)?://[^\s'\"<>\]]+", "[DATABASE_URL_REDACTADA]", text)

    # 2) Bearer completo antes de redacción genérica de Authorization.
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTADO]", text)

    # 3) Claves/secretos comunes key=value o key:value.
    text = re.sub(
        r"(?i)\b(database_url|neon_database_url|password|passwd|secret|token|api[_-]?key|authorization)\b\s*[:=]\s*([^\s,;|]+)",
        lambda m: f"{m.group(1)}=[REDACTADO]",
        text,
    )

    # 4) Correo electrónico.
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[CORREO_REDACTADO]", text)

    # 5) Usuario de Windows en rutas; conserva el resto del path útil para traceback.
    text = re.sub(r"(?i)C:\\Users\\[^\\\r\n\t ]+", r"C:\\Users\\[USUARIO]", text)

    # 6) Campos que pueden contener PII explícita.
    text = re.sub(
        r"(?i)\b(c[eé]dula|ruc|correo|e-?mail|celular|tel[eé]fono|patient_id|patient|cliente)\b\s*[:=]\s*[^,\r\n|]+",
        lambda m: m.group(1) + "=[REDACTADO]",
        text,
    )

    # 7) Cédulas, teléfonos, RUC e identificadores numéricos largos.
    text = re.sub(r"(?<!\d)\d{7,20}(?!\d)", "[NUMERO_REDACTADO]", text)

    # 8) IP no-loopback.
    def _ip_repl(match):
        ip = match.group(0)
        return ip if ip.startswith("127.") else "[IP_REDACTADA]"
    text = re.sub(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", _ip_repl, text)
    return text


if __name__ == "__main__":
    if "--diag-upload-file" in sys.argv:
        i = sys.argv.index("--diag-upload-file")
        try:
            payload = _rp_diag_load_json(Path(sys.argv[i + 1]))
            if not payload.get("incident_id"):
                raise RuntimeError("payload_sin_incident_id")
            _rp_diag_upload_payload_direct(payload)
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            # Nunca imprimir el mensaje del driver: podría contener host/usuario.
            sys.stderr.write("DIAG_UPLOAD_ERROR:" + type(exc).__name__ + "\n")
            raise SystemExit(73)
    if "--self-test-mutex-holder" in sys.argv:
        i = sys.argv.index("--self-test-mutex-holder")
        raise SystemExit(_selftest_mutex_holder(sys.argv[i + 1], sys.argv[i + 2]))
    if "--self-test-mutex-probe" in sys.argv:
        i = sys.argv.index("--self-test-mutex-probe")
        raise SystemExit(_selftest_mutex_probe(sys.argv[i + 1]))
    if "--self-test-core" in sys.argv:
        raise SystemExit(run_self_tests())
    main()
