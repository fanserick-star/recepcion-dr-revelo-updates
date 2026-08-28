from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path((os.getenv("RP_DATA_DIR") or "").strip() or (ROOT / "data"))
STATE_PATH = DATA_DIR / "auto_update_state.json"
DOWNLOAD_DIR = DATA_DIR / "auto_updates"
BACKUP_DIR = DATA_DIR / "update_backups"
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json"
MANIFEST_URL = (os.getenv("RP_UPDATE_MANIFEST_URL") or DEFAULT_MANIFEST_URL).strip()
USER_AGENT = "Recepcion-Dr-Revelo-AutoUpdater/3.1"
PROTECTED_TOP = {".env", "data", ".venv", "BASE DE DATOS 2026.xlsx"}


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_state(**updates):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = _read_json(STATE_PATH, {}) or {}
    state.update(updates)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _manifest_data() -> dict:
    return _read_json(ROOT / "update_manifest.json", {}) or {}


def local_version() -> str:
    data = _manifest_data()
    return str(data.get("version") or "0").strip()


def installed_app_version() -> str:
    try:
        text = (ROOT / "app.py").read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^\s*APP_VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        return match.group(1).strip() if match else ""
    except Exception:
        return ""


def installation_consistent() -> bool:
    data = _manifest_data()
    expected = str(data.get("app_version") or "").strip()
    if not expected:
        return True
    actual = installed_app_version()
    return bool(actual and actual == expected)


def _version_tuple(value: str):
    raw = str(value or "").strip().upper()
    main = raw.split("-", 1)[0]
    nums = [int(x) for x in re.findall(r"\d+", main)]
    nums = (nums + [0, 0, 0, 0])[:4]
    rc = re.search(r"(?:RC|BETA|ALPHA)[._-]?(\d+)?", raw)
    stable_rank = 1 if not rc else 0
    rc_num = int(rc.group(1) or 0) if rc else 0
    return (*nums, stable_rank, rc_num)


def is_newer(remote: str, local: str) -> bool:
    return _version_tuple(remote) > _version_tuple(local)


def _cache_bust(url: str) -> str:
    parts = urllib.parse.urlsplit(str(url))
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query.append(("rp_ts", str(time.time_ns())))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _urlopen(url: str, timeout: float = 8.0, *, fresh: bool = False):
    final = _cache_bust(url) if fresh else str(url)
    req = urllib.request.Request(final, headers={
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_manifest(attempts: int = 3) -> dict:
    last = None
    for attempt in range(max(1, attempts)):
        try:
            with _urlopen(MANIFEST_URL, timeout=7.0 + attempt * 2, fresh=True) as response:
                if getattr(response, "status", 200) != 200:
                    raise RuntimeError(f"Servidor de actualizaciones respondió {getattr(response, 'status', '?')}")
                raw = response.read(256 * 1024)
            data = json.loads(raw.decode("utf-8-sig"))
            if data.get("product") != "recepcion-pacientes":
                raise RuntimeError("Manifiesto de actualización no corresponde a Recepción")
            if not str(data.get("version") or "").strip():
                raise RuntimeError("Manifiesto de actualización sin versión")
            return data
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(f"No se pudo leer el canal de actualizaciones: {last}")


def _download(url: str, dest: Path) -> str:
    h = hashlib.sha256()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with _urlopen(url, timeout=15.0, fresh=True) as response, tmp.open("wb") as fh:
        total = 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 60 * 1024 * 1024:
                raise RuntimeError("El paquete de actualización supera el límite permitido")
            fh.write(chunk)
            h.update(chunk)
    tmp.replace(dest)
    return h.hexdigest()


def _remote_bytes(url: str, *, limit: int = 12 * 1024 * 1024, attempts: int = 3) -> bytes:
    last = None
    for attempt in range(max(1, attempts)):
        try:
            with _urlopen(url, timeout=16.0 + attempt * 2, fresh=True) as response:
                chunks = []
                total = 0
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise RuntimeError("Un componente de actualización supera el límite permitido")
                    chunks.append(chunk)
            return b"".join(chunks)
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(f"No se pudo descargar un componente de actualización: {last}")


def _entry_payload(entry: dict) -> bytes:
    urls = entry.get("parts") or []
    if urls:
        if not isinstance(urls, list) or not all(isinstance(x, str) and x.strip() for x in urls):
            raise RuntimeError("Partes de actualización inválidas")
        raw = b"".join(_remote_bytes(x.strip()) for x in urls)
    else:
        url = str(entry.get("url") or "").strip()
        if not url:
            raise RuntimeError("Componente remoto sin URL")
        raw = _remote_bytes(url)
    encoding = str(entry.get("encoding") or "raw").strip().lower()
    if encoding in {"raw", "binary", "utf-8", "utf8"}:
        return raw
    if encoding == "base64":
        try:
            return base64.b64decode(b"".join(raw.split()), validate=True)
        except Exception as exc:
            raise RuntimeError("Componente base64 inválido") from exc
    raise RuntimeError(f"Codificación de actualización no soportada: {encoding}")


def _safe_member(root: Path, member: str) -> Path:
    dest = (root / member).resolve()
    base = root.resolve()
    if dest != base and base not in dest.parents:
        raise RuntimeError("Ruta de actualización inválida")
    return dest


def _backup_changed(copy_items) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"auto_antes_actualizacion_{stamp}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in copy_items:
            src = ROOT / item
            if not src.exists():
                continue
            if src.is_dir():
                for child in src.rglob("*"):
                    if child.is_file():
                        zf.write(child, child.relative_to(ROOT).as_posix())
            else:
                zf.write(src, src.relative_to(ROOT).as_posix())
    backups = sorted(BACKUP_DIR.glob("auto_antes_actualizacion_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[5:]:
        try: old.unlink()
        except Exception: pass
    return dest


def _restore_files_backup(backup: Path, copy_items, existed_before) -> None:
    try:
        with zipfile.ZipFile(backup) as zf:
            for member in zf.namelist():
                dest = _safe_member(ROOT, member)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".rollback_tmp")
                tmp.write_bytes(zf.read(member))
                tmp.replace(dest)
    except Exception:
        pass
    for item in copy_items:
        if item in existed_before:
            continue
        try:
            p = ROOT / item
            if p.is_file():
                p.unlink()
        except Exception:
            pass


def _validate_staged(stage: Path, copy_items, expected_version: str) -> None:
    for item in copy_items:
        p = stage / item
        if p.suffix.lower() == ".py":
            text = p.read_text(encoding="utf-8-sig", errors="strict")
            compile(text, item, "exec")
    mp = stage / "update_manifest.json"
    if mp.exists():
        data = json.loads(mp.read_text(encoding="utf-8-sig"))
        if str(data.get("version") or "").strip() != expected_version:
            raise RuntimeError("El manifiesto local preparado no coincide con la versión remota")


def apply_files_manifest(remote: dict, expected_version: str) -> dict:
    entries = remote.get("files") or []
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("El manifiesto remoto no contiene archivos")

    with tempfile.TemporaryDirectory(prefix="rp_file_update_") as td:
        stage = Path(td) / "stage"
        stage.mkdir(parents=True)
        copy_items = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise RuntimeError("Entrada de actualización inválida")
            rel = Path(str(entry.get("path") or ""))
            if not rel.parts or rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError("Ruta inválida en actualización")
            top = rel.parts[0]
            if top in PROTECTED_TOP:
                raise RuntimeError(f"La actualización intenta tocar un archivo protegido: {top}")
            expected_sha = str(entry.get("sha256") or "").strip().lower()
            if len(expected_sha) != 64 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
                raise RuntimeError(f"SHA-256 inválido para {rel.as_posix()}")
            payload = _entry_payload(entry)
            actual_sha = hashlib.sha256(payload).hexdigest()
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f"SHA-256 no coincide para {rel.as_posix()} "
                    f"(esperado {expected_sha[:12]}…, recibido {actual_sha[:12]}…)"
                )
            dest = _safe_member(stage, rel.as_posix())
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            copy_items.append(rel.as_posix())

        _validate_staged(stage, copy_items, expected_version)
        existed_before = {item for item in copy_items if (ROOT / item).exists()}
        backup = _backup_changed(copy_items)
        try:
            for item in copy_items:
                src = stage / item
                dst = ROOT / item
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(dst.name + ".update_tmp")
                shutil.copy2(src, tmp)
                tmp.replace(dst)

            new_local = local_version()
            if new_local != expected_version:
                raise RuntimeError(
                    f"La actualización terminó, pero update_manifest.json reporta {new_local or 'sin versión'} "
                    f"en vez de {expected_version}"
                )
            if not installation_consistent():
                raise RuntimeError(
                    f"La actualización terminó, pero app.py reporta {installed_app_version() or 'sin versión'} "
                    f"y no coincide con el manifiesto local"
                )
        except Exception:
            _restore_files_backup(backup, copy_items, existed_before)
            raise
        return {"version": expected_version, "backup": backup.name, "app_version": installed_app_version()}


def apply_package(zip_path: Path, expected_version: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="rp_auto_update_") as td:
        extract = Path(td) / "extract"
        extract.mkdir(parents=True)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    _safe_member(extract, member)
                zf.extractall(extract)
        except zipfile.BadZipFile as exc:
            raise RuntimeError("El ZIP descargado está dañado") from exc

        manifests = list(extract.rglob("update_manifest.json"))
        if len(manifests) != 1:
            raise RuntimeError("El paquete no contiene un manifiesto único")
        manifest_path = manifests[0]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("product") != "recepcion-pacientes":
            raise RuntimeError("El paquete no corresponde a Recepción")
        package_version = str(manifest.get("version") or "").strip()
        if package_version != expected_version:
            raise RuntimeError("La versión del ZIP no coincide con el manifiesto remoto")

        package_root = manifest_path.parent
        copy_items = manifest.get("copy") or []
        if not copy_items:
            raise RuntimeError("El paquete no indica qué archivos actualizar")
        for item in copy_items:
            rel = Path(str(item))
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError("Ruta inválida en paquete")
            top = rel.parts[0] if rel.parts else ""
            if top in PROTECTED_TOP:
                raise RuntimeError(f"El paquete intenta tocar un archivo protegido: {top}")
            if not (package_root / rel).exists():
                raise RuntimeError(f"Falta componente de actualización: {item}")

        existed_before = {str(item) for item in copy_items if (ROOT / str(item)).exists()}
        backup = _backup_changed(copy_items)
        try:
            for item in copy_items:
                rel = Path(str(item))
                src = package_root / rel
                dst = ROOT / rel
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    for child in src.rglob("*"):
                        sub = child.relative_to(src)
                        target = dst / sub
                        if child.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(child, target)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dst.with_name(dst.name + ".update_tmp")
                    shutil.copy2(src, tmp)
                    tmp.replace(dst)

            expected_app = str(manifest.get("app_version") or "").strip()
            if expected_app and installed_app_version() != expected_app:
                raise RuntimeError("El backend instalado no coincide con el paquete")
        except Exception:
            _restore_files_backup(backup, [str(x) for x in copy_items], existed_before)
            raise
        return {"version": package_version, "backup": backup.name, "app_version": installed_app_version()}


def check_and_apply() -> dict:
    local = local_version()
    remote = None
    try:
        remote = fetch_manifest(attempts=3)
        remote_version = str(remote.get("version") or "").strip()
        coherent = installation_consistent()
        _write_state(last_check_ok=True, last_error="", local_version=local,
                     local_app_version=installed_app_version(), remote_version=remote_version,
                     installation_consistent=coherent)
        if not remote_version:
            return {"ok": True, "updated": False, "version": local}
        if not is_newer(remote_version, local) and coherent:
            return {"ok": True, "updated": False, "version": local}
        if _version_tuple(remote_version) < _version_tuple(local):
            return {"ok": True, "updated": False, "version": local}

        try:
            if remote.get("files"):
                result = apply_files_manifest(remote, remote_version)
            else:
                url = str(remote.get("url") or "").strip()
                expected_sha = str(remote.get("sha256") or "").strip().lower()
                if not url or len(expected_sha) != 64:
                    raise RuntimeError("Manifiesto remoto incompleto")
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", remote_version)
                zip_path = DOWNLOAD_DIR / f"recepcion_{safe_name}.zip"
                actual_sha = _download(url, zip_path)
                if actual_sha.lower() != expected_sha:
                    try: zip_path.unlink()
                    except Exception: pass
                    raise RuntimeError("El SHA-256 del paquete no coincide")
                result = apply_package(zip_path, remote_version)
        except Exception as first_exc:
            refreshed = fetch_manifest(attempts=3)
            refreshed_version = str(refreshed.get("version") or "").strip()
            if refreshed_version != remote_version:
                remote = refreshed
                remote_version = refreshed_version
            if remote.get("files"):
                result = apply_files_manifest(remote, remote_version)
            else:
                raise first_exc

        _write_state(last_check_ok=True, last_error="", local_version=remote_version,
                     local_app_version=installed_app_version(), remote_version=remote_version,
                     installation_consistent=installation_consistent(),
                     last_installed_version=remote_version, last_backup=result.get("backup", ""))
        return {"ok": True, "updated": True, "version": remote_version, "backup": result.get("backup")}
    except Exception as exc:
        remote_version = str((remote or {}).get("version") or "").strip()
        coherent = installation_consistent()
        should_block = not coherent
        _write_state(last_check_ok=False, last_error=str(exc)[:1000], local_version=local,
                     local_app_version=installed_app_version(), remote_version=remote_version or None,
                     mandatory_block=should_block, installation_consistent=coherent,
                     deferred=not should_block)
        return {
            "ok": False, "updated": False, "version": local, "error": str(exc),
            "blocked": should_block, "deferred": not should_block,
        }
