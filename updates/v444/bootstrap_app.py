from __future__ import annotations

# Puente automático v4.3.44: corrige Agenda + estado AZUR/SRI local-first.
APP_VERSION = "4.3.44"

import base64, hashlib, json, os, sys, zipfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = "4.3.44"
TARGET_FILES = ("app.py", "static/app.js")
PATCH_DATA_B64 = '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'

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _data_dir() -> Path:
    return Path((os.getenv("RP_DATA_DIR") or "").strip() or (ROOT / "data"))

def _plans() -> dict:
    return json.loads(zlib.decompress(base64.b64decode(PATCH_DATA_B64)).decode("utf-8"))

def _patched_bytes(raw: bytes, spec: dict) -> bytes:
    if _sha(raw) != spec["source_sha256"]:
        raise RuntimeError("El archivo base no coincide con una versión compatible")
    lines = raw.decode("utf-8").splitlines(keepends=True)
    for i1, i2, replacement in reversed(spec["ops"]):
        lines[int(i1):int(i2)] = [replacement]
    out = "".join(lines).encode("utf-8")
    if _sha(out) != spec["final_sha256"]:
        raise RuntimeError("La huella final no coincide")
    return out

def _find_previous_app(plans: dict):
    backup_dir = _data_dir() / "update_backups"
    candidates = sorted(backup_dir.glob("auto_antes_actualizacion_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if backup_dir.exists() else []
    for zp in candidates[:12]:
        try:
            with zipfile.ZipFile(zp) as zf:
                if "app.py" not in zf.namelist():
                    continue
                raw = zf.read("app.py")
            h = _sha(raw)
            for version, plan in plans.items():
                if h == plan["app.py"]["source_sha256"]:
                    return version, raw
        except Exception:
            continue
    raise RuntimeError("No se encontró el app.py anterior compatible (4.3.42/4.3.43)")

def _main():
    plans = _plans()
    version, old_app = _find_previous_app(plans)
    plan = plans[version]
    static_path = ROOT / "static/app.js"
    old_static = static_path.read_bytes()
    if _sha(old_static) != plan["static/app.js"]["source_sha256"]:
        # Si el frontend ya quedó en 4.3.44, se acepta tal cual.
        final_hash = next(iter(plans.values()))["static/app.js"]["final_sha256"]
        if _sha(old_static) != final_hash:
            raise RuntimeError("El frontend instalado no coincide con 4.3.42 ni 4.3.43")
        new_static = old_static
    else:
        new_static = _patched_bytes(old_static, plan["static/app.js"])
    new_app = _patched_bytes(old_app, plan["app.py"])
    tmp_static = static_path.with_name("app.js.v444_tmp")
    tmp_app = ROOT / "app.py.v444_tmp"
    tmp_static.write_bytes(new_static)
    tmp_app.write_bytes(new_app)
    try:
        tmp_static.replace(static_path)
        tmp_app.replace(ROOT / "app.py")
    except Exception:
        try: static_path.write_bytes(old_static)
        except Exception: pass
        try: (ROOT / "app.py").write_bytes(old_app)
        except Exception: pass
        raise
    if os.getenv("RP_V444_BOOTSTRAP_TEST") == "1":
        return
    os.execv(sys.executable, [sys.executable, str(ROOT / "app.py")])

if __name__ == "__main__":
    _main()
