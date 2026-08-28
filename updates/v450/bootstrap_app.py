from __future__ import annotations
APP_VERSION = "4.3.50"
import hashlib, os, subprocess, sys, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / "data" / "update_backups"

APP_446 = "f63a9466fef0c24f977a48d08e347504b7d582cc36aca465b07d004c43c02fd6"
APP_447 = "d856e2e6b8dc2bea28d2b06b4b593b7cf5dd091eeafb1c67a9ba28ef62cd8ad3"
APP_448 = "5ec6b484e2bdf6a15a798a276a3bafa7415d64a6f0c98d7eefc5ca20983247b6"
APP_449 = "f52c47436d005bba0c5546fff8ef4ebbdf0782c779c9a652a32abca2b4f50cf8"
KNOWN = {APP_446, APP_447, APP_448, APP_449}

V449_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v449/bootstrap_app.py"
V449_GIT_BLOB = "1539438dfb7f35c244307bcb3475491b306c1839"

def hb(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _env_data_dir():
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

def backup_dirs():
    dirs = [BACKUP]
    d = _env_data_dir()
    if d:
        dirs.append(d / "update_backups")
    dirs.append(ROOT.parent / "data" / "update_backups")
    out, seen = [], set()
    for p in dirs:
        try:
            k = str(p.resolve()).lower()
        except Exception:
            k = str(p).lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out

def find_previous_app():
    app = ROOT / "app.py"
    try:
        b = app.read_bytes()
        if hb(b) in KNOWN:
            return b
    except Exception:
        pass

    zips = []
    for d in backup_dirs():
        try:
            zips.extend(d.glob("*.zip"))
        except Exception:
            pass

    def mtime(p):
        try:
            return p.stat().st_mtime
        except Exception:
            return 0

    for z in sorted(zips, key=mtime, reverse=True)[:40]:
        try:
            with zipfile.ZipFile(z) as q:
                cand = next((n for n in q.namelist()
                             if n.replace("\\", "/").endswith("app.py")), None)
                if not cand:
                    continue
                b = q.read(cand)
                if hb(b) in KNOWN:
                    return b
        except Exception:
            pass
    raise RuntimeError("No hallé una copia compatible de app.py (v4.3.46–v4.3.49).")

def atomic_write(path: Path, data: bytes):
    tmp = path.with_name(path.name + ".v450_tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)

def fetch_v449_helper():
    req = urllib.request.Request(V449_URL, headers={"User-Agent": "Recepcion-Dr-Revelo-v450"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(100000)
    git_blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    if git_blob != V449_GIT_BLOB:
        raise RuntimeError("No se pudo verificar el puente v4.3.49.")
    return data

def main():
    app_path = ROOT / "app.py"
    base = find_previous_app()
    base_hash = hb(base)

    if base_hash != APP_449:
        atomic_write(app_path, base)
        helper = ROOT / "_v449_bridge.py"
        atomic_write(helper, fetch_v449_helper())
        env = dict(os.environ)
        env["RP_V449_NO_EXEC"] = "1"
        try:
            p = subprocess.run(
                [sys.executable, str(helper)],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            if p.returncode != 0:
                msg = (p.stderr or p.stdout or "falló el puente v4.3.49").strip()
                raise RuntimeError(msg[-1200:])
        finally:
            try:
                helper.unlink()
            except Exception:
                pass

    b = app_path.read_bytes()
    if hb(b) != APP_449:
        raise RuntimeError("La reconstrucción no llegó correctamente a v4.3.49.")

    marker = b'APP_VERSION = "4.3.49"'
    if marker not in b:
        raise RuntimeError("No encontré la versión esperada dentro de app.py.")
    final = b.replace(marker, b'APP_VERSION = "4.3.50"', 1)
    atomic_write(app_path, final)

    if b'APP_VERSION = "4.3.50"' not in app_path.read_bytes()[:300]:
        raise RuntimeError("No se pudo activar v4.3.50.")

    if os.getenv("RP_V450_NO_EXEC") == "1":
        print("v4.3.50 reconstruida y verificada")
        return 0

    os.execv(sys.executable, [sys.executable, str(app_path), *sys.argv[1:]])

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("No se pudo completar v4.3.50:", e, file=sys.stderr)
        raise
