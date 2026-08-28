from __future__ import annotations

import json
import os
import re
from pathlib import Path

import _AUTOACTUALIZAR_31 as _base

UPDATER_VERSION = "3.2"
ROOT = Path(__file__).resolve().parent


def _data_dir() -> Path:
    raw = (os.getenv("RP_DATA_DIR") or "").strip()
    if not raw and (ROOT / ".env").exists():
        try:
            for line in (ROOT / ".env").read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                if line.strip().startswith("RP_DATA_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if not raw:
        return ROOT / "data"
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    return p if p.is_absolute() else ROOT / p


def _bootstrap_pending() -> tuple[bool, str]:
    """Detecta un app.py de transición que aún no se consolidó.

    Los bootstraps escriben un marcador vNNN_consolidated.json únicamente al
    finalizar. Si el proceso murió antes de levantar el servidor, el número de
    versión de app.py puede coincidir con el manifest aunque la instalación no
    esté terminada. En ese caso debemos permitir reinstalar la MISMA versión.
    """
    try:
        text = (ROOT / "app.py").read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return False, ""
    names = re.findall(r'["\'](v\d+_consolidated\.json)["\']', text, flags=re.IGNORECASE)
    if not names:
        return False, ""
    data = _data_dir()
    for name in dict.fromkeys(names):
        if not (data / name).exists():
            return True, name
    return False, ""


def check_and_apply() -> dict:
    pending, marker = _bootstrap_pending()
    if pending:
        try:
            local = _base.local_version()
            remote = _base.fetch_manifest(attempts=3)
            remote_version = str(remote.get("version") or "").strip()
            coherent = _base.installation_consistent()
            _base._write_state(
                last_check_ok=True,
                last_error="",
                local_version=local,
                local_app_version=_base.installed_app_version(),
                remote_version=remote_version,
                installation_consistent=coherent,
                bootstrap_pending=True,
                bootstrap_marker=marker,
            )
            # Regla de recuperación: si el manifest ya dice la misma versión pero
            # el bootstrap no dejó su marcador de éxito, se reaplica esa versión.
            if remote_version and remote_version == local and remote.get("files"):
                result = _base.apply_files_manifest(remote, remote_version)
                _base._write_state(
                    last_check_ok=True,
                    last_error="",
                    local_version=remote_version,
                    local_app_version=_base.installed_app_version(),
                    remote_version=remote_version,
                    installation_consistent=_base.installation_consistent(),
                    bootstrap_pending=True,
                    bootstrap_retry=True,
                    last_installed_version=remote_version,
                    last_backup=result.get("backup", ""),
                )
                return {
                    "ok": True,
                    "updated": True,
                    "version": remote_version,
                    "backup": result.get("backup"),
                    "recovery_retry": True,
                }
        except Exception:
            # La implementación base conserva el comportamiento seguro de abrir
            # la copia local cuando sea coherente y registrar el error.
            pass
    return _base.check_and_apply()


# Compatibilidad para herramientas que consulten atributos del updater anterior.
def __getattr__(name):
    return getattr(_base, name)
