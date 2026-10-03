from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

import cloud_sync

PATCH_VERSION = "1.3.95"
_FALLBACK_LOCK = threading.Lock()
_LAST_WRITE_ERROR = ""
_STATUS_WRITE_FAILURES = 0


def _now_iso() -> str:
    try:
        return str(cloud_sync._now_iso())
    except Exception:
        from datetime import datetime

        return datetime.now().isoformat(timespec="seconds")


def _read_existing(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_temp(path: Path, payload: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            pass


def _atomic_replace(source: Path, target: Path) -> None:
    os.replace(source, target)


def _replace_with_retry(source: Path, target: Path) -> bool:
    global _LAST_WRITE_ERROR
    delays = (0.04, 0.08, 0.16, 0.28, 0.45, 0.70)
    for attempt in range(len(delays) + 1):
        try:
            _atomic_replace(source, target)
            _LAST_WRITE_ERROR = ""
            return True
        except PermissionError as exc:
            _LAST_WRITE_ERROR = f"PermissionError: {exc}"
            if attempt >= len(delays):
                break
            time.sleep(delays[attempt])
        except OSError as exc:
            _LAST_WRITE_ERROR = f"{type(exc).__name__}: {exc}"
            if attempt >= len(delays):
                break
            time.sleep(delays[attempt])
        except Exception as exc:
            _LAST_WRITE_ERROR = f"{type(exc).__name__}: {exc}"
            break
    return False


def _direct_write_fallback(path: Path, payload: str) -> bool:
    """Best-effort fallback for the auxiliary status file only.

    sync_status.json contains UI/synchronization status, never the clinical
    database itself. If Windows temporarily blocks atomic replacement, this
    fallback prevents that auxiliary file from stopping the real sync worker.
    """
    global _LAST_WRITE_ERROR
    for delay in (0.0, 0.08, 0.20, 0.45):
        if delay:
            time.sleep(delay)
        try:
            with path.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except Exception:
                    pass
            _LAST_WRITE_ERROR = ""
            return True
        except Exception as exc:
            _LAST_WRITE_ERROR = f"{type(exc).__name__}: {exc}"
    return False


def resilient_write_status(data_dir: Path, **values) -> dict:
    """Write sync_status without allowing a Windows file lock to kill sync.

    - Uses a unique temporary filename per write/process/thread.
    - Retries atomic replacement when antivirus/Windows briefly holds the file.
    - Falls back to a direct status-only write if replacement stays blocked.
    - Never raises merely because the auxiliary status file could not be saved.
    """
    global _STATUS_WRITE_FAILURES

    data_dir = Path(data_dir)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    path = data_dir / "sync_status.json"
    lock = getattr(cloud_sync, "_STATUS_LOCK", _FALLBACK_LOCK)

    with lock:
        old = _read_existing(path)
        old.update(values)
        old["updated_at"] = _now_iso()
        payload = json.dumps(old, ensure_ascii=False, indent=2)
        temp = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )
        wrote = False
        try:
            _write_temp(temp, payload)
            wrote = _replace_with_retry(temp, path)
            if not wrote:
                wrote = _direct_write_fallback(path, payload)
        except Exception as exc:
            globals()["_LAST_WRITE_ERROR"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except Exception:
                pass

        if not wrote:
            _STATUS_WRITE_FAILURES += 1
        return old


def health() -> dict:
    return {
        "ok": True,
        "version": PATCH_VERSION,
        "installed": bool(getattr(cloud_sync, "_V1395_STATUS_RESILIENCE_ACTIVE", False)),
        "unique_temp_files": True,
        "atomic_replace_retry": True,
        "status_write_failure_nonfatal": True,
        "failures": int(_STATUS_WRITE_FAILURES),
        "last_error": str(_LAST_WRITE_ERROR or ""),
    }


def install() -> None:
    if getattr(cloud_sync, "_V1395_STATUS_RESILIENCE_ACTIVE", False):
        return
    cloud_sync._write_status = resilient_write_status
    cloud_sync._V1395_STATUS_RESILIENCE_ACTIVE = True


PATCH_BOOT_OK = True
