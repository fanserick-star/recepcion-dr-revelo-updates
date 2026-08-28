from __future__ import annotations

APP_VERSION = "4.3.52"

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V451_HELPER_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v451/bootstrap_app.py"
V451_HELPER_BLOB = "da7d569c96dca6b53bac8025d60df6de96c6b690"
APP_MARKER = "# v4.3.51 — PROGRAM_UPDATE_API"
JS_MARKER = "/* v4.3.51 — professional agenda/settings enhancer */"
CSS_MARKER = "/* v4.3.51 — compact professional UI */"


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


def _log(message: str) -> None:
    try:
        d = _data_dir()
        d.mkdir(parents=True, exist_ok=True)
        with (d / "v452_recovery.log").open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def _backup_dirs() -> list[Path]:
    candidates = [
        _data_dir() / "update_backups",
        ROOT / "data" / "update_backups",
        ROOT.parent / "data" / "update_backups",
    ]
    out, seen = [], set()
    for p in candidates:
        try:
            key = str(p.resolve()).lower()
        except Exception:
            key = str(p).lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _is_v450(data: bytes) -> bool:
    try:
        text = data.decode("utf-8-sig", errors="ignore")
    except Exception:
        return False
    return bool(re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.50["\']', text, re.MULTILINE))


def _find_v450() -> tuple[bytes, str]:
    archives: list[Path] = []
    for directory in _backup_dirs():
        try:
            archives.extend(directory.glob("*.zip"))
        except Exception:
            pass

    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except Exception:
            return 0.0

    seen = set()
    for archive in sorted(archives, key=mtime, reverse=True)[:160]:
        try:
            key = str(archive.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            with zipfile.ZipFile(archive) as zf:
                for name in zf.namelist():
                    if not name.replace("\\", "/").endswith("app.py"):
                        continue
                    data = zf.read(name)
                    if _is_v450(data):
                        return data, f"{archive.name}:{name}"
        except Exception:
            pass
    raise RuntimeError("No encontré un respaldo app.py v4.3.50 para reconstruir la actualización.")


def _git_blob_sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _fetch_helper() -> bytes:
    req = urllib.request.Request(
        V451_HELPER_URL + f"?rp_ts={time.time_ns()}",
        headers={
            "User-Agent": "Recepcion-Dr-Revelo-v452",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read(2_000_000)
    if _git_blob_sha(data) != V451_HELPER_BLOB:
        raise RuntimeError("No se pudo verificar el aplicador base v4.3.51.")
    return data


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".v452_tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _build_in_temp(base_v450: bytes) -> tuple[bytes, bytes, bytes]:
    live_js = ROOT / "static" / "app.js"
    live_css = ROOT / "static" / "style.css"
    if not live_js.exists() or not live_css.exists():
        raise RuntimeError("Faltan recursos de interfaz static/app.js o static/style.css.")

    with tempfile.TemporaryDirectory(prefix="rp_v452_build_") as td:
        temp = Path(td)
        (temp / "static").mkdir(parents=True)
        (temp / "app.py").write_bytes(base_v450)
        shutil.copy2(live_js, temp / "static" / "app.js")
        shutil.copy2(live_css, temp / "static" / "style.css")
        helper = temp / "_v451_apply.py"
        helper.write_bytes(_fetch_helper())

        env = dict(os.environ)
        env["RP_V451_NO_EXEC"] = "1"
        proc = subprocess.run(
            [sys.executable, str(helper)],
            cwd=str(temp),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "falló el constructor v4.3.51").strip()
            raise RuntimeError(detail[-2500:])

        app_text = (temp / "app.py").read_text(encoding="utf-8-sig", errors="strict")
        if not re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.51["\']', app_text, re.MULTILINE):
            raise RuntimeError("El constructor temporal no produjo app.py v4.3.51.")
        if APP_MARKER not in app_text:
            raise RuntimeError("El constructor temporal no incorporó el actualizador interno.")

        app_text, n = re.subn(
            r'^\s*APP_VERSION\s*=\s*["\']4\.3\.51["\']',
            'APP_VERSION = "4.3.52"',
            app_text,
            count=1,
            flags=re.MULTILINE,
        )
        if n != 1:
            raise RuntimeError("No se pudo marcar la versión final como 4.3.52.")
        compile(app_text, "app.py", "exec")
        if not re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.52["\']', app_text, re.MULTILINE):
            raise RuntimeError("La versión final 4.3.52 no quedó confirmada.")

        js_text = (temp / "static" / "app.js").read_text(encoding="utf-8", errors="strict")
        css_text = (temp / "static" / "style.css").read_text(encoding="utf-8", errors="strict")
        if JS_MARKER not in js_text:
            raise RuntimeError("No se incorporó la interfaz v4.3.51 en app.js.")
        if CSS_MARKER not in css_text:
            raise RuntimeError("No se incorporaron los estilos v4.3.51 en style.css.")

        return app_text.encode("utf-8"), js_text.encode("utf-8"), css_text.encode("utf-8")


def _backup_live(paths: list[Path]) -> Path:
    d = _data_dir() / "update_backups"
    d.mkdir(parents=True, exist_ok=True)
    z = d / ("v452_antes_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as q:
        for p in paths:
            if p.exists():
                q.write(p, p.relative_to(ROOT).as_posix())
    return z


def _restore(z: Path) -> None:
    try:
        with zipfile.ZipFile(z) as q:
            for name in q.namelist():
                _atomic_write(ROOT / name, q.read(name))
    except Exception as exc:
        _log("Rollback falló: " + repr(exc))


def main() -> int:
    _log("Inicio hotfix v4.3.52")
    base, source = _find_v450()
    _log("Base v4.3.50 encontrada en " + source)

    final_app, final_js, final_css = _build_in_temp(base)
    _log("Construcción temporal v4.3.52 verificada")

    app = ROOT / "app.py"
    js = ROOT / "static" / "app.js"
    css = ROOT / "static" / "style.css"
    backup = _backup_live([app, js, css])

    try:
        _atomic_write(js, final_js)
        _atomic_write(css, final_css)
        _atomic_write(app, final_app)

        installed = app.read_text(encoding="utf-8-sig", errors="strict")
        compile(installed, "app.py", "exec")
        if not re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.52["\']', installed, re.MULTILINE):
            raise RuntimeError("La instalación final no reporta v4.3.52.")
        if JS_MARKER not in js.read_text(encoding="utf-8", errors="ignore"):
            raise RuntimeError("La instalación final perdió app.js v4.3.51.")
        if CSS_MARKER not in css.read_text(encoding="utf-8", errors="ignore"):
            raise RuntimeError("La instalación final perdió style.css v4.3.51.")
    except Exception:
        _restore(backup)
        raise

    try:
        marker = _data_dir() / "v452_consolidated.json"
        marker.write_text(
            json.dumps({"version": "4.3.52", "source": source, "at": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    _log("v4.3.52 consolidada correctamente")
    if os.getenv("RP_V452_NO_EXEC") == "1":
        print("v4.3.52 consolidada y verificada")
        return 0

    os.execv(sys.executable, [sys.executable, str(app), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _log("ERROR: " + repr(exc))
        print("No se pudo completar v4.3.52:", exc, file=sys.stderr)
        raise
