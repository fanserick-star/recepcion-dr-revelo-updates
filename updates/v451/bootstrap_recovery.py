from __future__ import annotations

APP_VERSION = "4.3.51"

import hashlib
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HELPER_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v451/bootstrap_app.py"
HELPER_GIT_BLOB = "da7d569c96dca6b53bac8025d60df6de96c6b690"


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".v451_recovery_tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def env_data_dir() -> Path | None:
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
        return None
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    return p if p.is_absolute() else ROOT / p


def backup_dirs() -> list[Path]:
    candidates = [ROOT / "data" / "update_backups"]
    configured = env_data_dir()
    if configured:
        candidates.insert(0, configured / "update_backups")
    candidates.append(ROOT.parent / "data" / "update_backups")
    out: list[Path] = []
    seen = set()
    for p in candidates:
        try:
            key = str(p.resolve()).lower()
        except Exception:
            key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def is_v450(data: bytes) -> bool:
    head = data[:4000].decode("utf-8-sig", errors="ignore")
    return (
        'APP_VERSION = "4.3.50"' in head
        or "APP_VERSION='4.3.50'" in head
        or 'APP_VERSION="4.3.50"' in head
    )


def find_v450_backup() -> bytes | None:
    zips: list[Path] = []
    for directory in backup_dirs():
        try:
            zips.extend(directory.glob("auto_antes_actualizacion_*.zip"))
            zips.extend(directory.glob("programa_antes_actualizacion_*.zip"))
            zips.extend(directory.glob("v451_antes_*.zip"))
        except Exception:
            pass

    def mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0

    for archive in sorted(zips, key=mtime, reverse=True)[:80]:
        try:
            with zipfile.ZipFile(archive) as zf:
                names = [n for n in zf.namelist() if n.replace("\\", "/").endswith("app.py")]
                for name in names:
                    data = zf.read(name)
                    if is_v450(data):
                        return data
        except Exception:
            pass
    return None


def fetch_helper() -> bytes:
    req = urllib.request.Request(
        HELPER_URL,
        headers={
            "User-Agent": "Recepcion-Dr-Revelo-v451-recovery",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read(300000)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    if blob != HELPER_GIT_BLOB:
        raise RuntimeError("No se pudo verificar el aplicador v4.3.51.")
    return data


def main() -> int:
    app_path = ROOT / "app.py"

    # El autoactualizador acaba de respaldar la instalación anterior. Recuperamos
    # exclusivamente app.py v4.3.50 para que el aplicador 4.3.51 tenga una base
    # determinista. Nunca restauramos .env, data, bases ni el manifiesto nuevo.
    previous = find_v450_backup()
    if previous is not None:
        atomic_write(app_path, previous)

    helper = ROOT / "_v451_apply.py"
    atomic_write(helper, fetch_helper())
    env = dict(os.environ)
    env["RP_V451_NO_EXEC"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, str(helper)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=150,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "falló el aplicador v4.3.51").strip()
            raise RuntimeError(detail[-1800:])
    finally:
        try:
            helper.unlink()
        except Exception:
            pass

    try:
        head = app_path.read_text(encoding="utf-8-sig", errors="ignore")[:500]
    except Exception:
        head = ""
    if 'APP_VERSION = "4.3.51"' not in head and 'APP_VERSION="4.3.51"' not in head:
        raise RuntimeError("La actualización v4.3.51 no quedó consolidada en app.py.")

    if os.getenv("RP_V451_RECOVERY_NO_EXEC") == "1":
        print("v4.3.51 consolidada y verificada")
        return 0

    os.execv(sys.executable, [sys.executable, str(app_path), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("No se pudo consolidar v4.3.51:", exc, file=sys.stderr)
        raise
