from __future__ import annotations

# One-shot automatic bridge to Recepcion v4.3.41.
# AUTOACTUALIZAR sees APP_VERSION before launching this file; on first run the
# bridge reconstructs the final sources from the verified previous installation.
APP_VERSION = "4.3.41"

import base64
import hashlib
import json
import os
import runpy
import sys
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = "4.3.41"
TARGET_FILES = ("app.py", "static/app.js", "static/index.html", "static/style.css")
PATCH_DATA_B64 = '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'

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _data_dir() -> Path:
    return Path((os.getenv("RP_DATA_DIR") or "").strip() or (ROOT / "data"))

def _state(**values) -> None:
    try:
        p = _data_dir() / "v441_bootstrap_state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        values["updated_at"] = datetime.now(timezone.utc).isoformat()
        t = p.with_suffix(".tmp")
        t.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        t.replace(p)
    except Exception:
        pass

def _plans() -> dict:
    return json.loads(zlib.decompress(base64.b64decode(PATCH_DATA_B64)).decode("utf-8"))

def _find_source(plans: dict):
    backup_dir = _data_dir() / "update_backups"
    if not backup_dir.exists():
        raise RuntimeError("No se encontró el respaldo previo de la actualización")
    candidates = sorted(backup_dir.glob("auto_antes_actualizacion_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for zp in candidates[:12]:
        try:
            with zipfile.ZipFile(zp) as zf:
                old_app = zf.read("app.py")
                old_manifest = zf.read("update_manifest.json") if "update_manifest.json" in zf.namelist() else None
            app_hash = _sha(old_app)
            for version, plan in plans.items():
                if app_hash == plan["app.py"]["source_sha256"]:
                    return version, zp, old_app, old_manifest
        except Exception:
            continue
    raise RuntimeError("El respaldo no corresponde a v4.3.39 ni v4.3.40")

def _patched_bytes(raw: bytes, spec: dict) -> bytes:
    if _sha(raw) != spec["source_sha256"]:
        raise RuntimeError("El archivo base no coincide con su huella esperada")
    lines = raw.decode("utf-8").splitlines(keepends=True)
    for i1, i2, replacement in reversed(spec["ops"]):
        lines[int(i1):int(i2)] = [replacement]
    out = "".join(lines).encode("utf-8")
    if _sha(out) != spec["final_sha256"]:
        raise RuntimeError("La huella final no coincide")
    return out

def _restore(old_app: bytes | None, old_manifest: bytes | None, originals: dict[str, bytes]) -> None:
    for rel, raw in originals.items():
        try:
            (ROOT / rel).write_bytes(raw)
        except Exception:
            pass
    if old_app is not None:
        try:
            (ROOT / "app.py").write_bytes(old_app)
        except Exception:
            pass
    if old_manifest is not None:
        try:
            (ROOT / "update_manifest.json").write_bytes(old_manifest)
        except Exception:
            pass

def _apply_bridge() -> tuple[bytes | None, bytes | None]:
    plans = _plans()
    version, backup_path, old_app, old_manifest = _find_source(plans)
    plan = plans[version]
    originals: dict[str, bytes] = {}
    patched: dict[str, bytes] = {}
    try:
        originals["app.py"] = old_app
        patched["app.py"] = _patched_bytes(old_app, plan["app.py"])
        for rel in TARGET_FILES[1:]:
            raw = (ROOT / rel).read_bytes()
            originals[rel] = raw
            patched[rel] = _patched_bytes(raw, plan[rel])

        # All hashes are validated before touching the installation.
        staged: dict[str, Path] = {}
        for rel, raw in patched.items():
            dst = ROOT / rel
            tmp = dst.with_name(dst.name + ".v441_tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(raw)
            staged[rel] = tmp
        written: list[str] = []
        try:
            # Static assets first; app.py last. The currently running bridge stays in memory.
            for rel in TARGET_FILES[1:] + ("app.py",):
                staged[rel].replace(ROOT / rel)
                written.append(rel)
        except Exception:
            for rel in written:
                try:
                    (ROOT / rel).write_bytes(originals[rel])
                except Exception:
                    pass
            raise
        _state(ok=True, source=version, target=TARGET, backup=backup_path.name, files=list(TARGET_FILES))
        return old_app, old_manifest
    except Exception:
        _restore(old_app, old_manifest, originals)
        raise

def _main() -> None:
    old_app = old_manifest = None
    try:
        old_app, old_manifest = _apply_bridge()
    except Exception as exc:
        _state(ok=False, target=TARGET, error=str(exc)[:1200])
        # Restore the exact previous app/manifest so Recepcion can still open.
        try:
            plans = _plans()
            _, _, old_app, old_manifest = _find_source(plans)
            _restore(old_app, old_manifest, {})
        except Exception:
            pass
        if os.getenv("RP_V441_BOOTSTRAP_TEST") == "1":
            raise
        if old_app is not None:
            os.execv(sys.executable, [sys.executable, str(ROOT / "app.py")])
        raise

    if os.getenv("RP_V441_BOOTSTRAP_TEST") == "1":
        return
    # Start the real v4.3.41 in the same windowless Python executable.
    os.execv(sys.executable, [sys.executable, str(ROOT / "app.py")])

if __name__ == "__main__":
    _main()
