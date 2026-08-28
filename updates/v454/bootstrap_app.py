from __future__ import annotations

APP_VERSION = "4.3.54"

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HELPER_PATH = ROOT / "_v451_apply.py"
HELPER_SHA256 = "bc938668ae0a153e90bcd8c7f325de5f290c7b0bc422c58704ffe25f9ff236ca"
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
        with (d / "v454_recovery.log").open("a", encoding="utf-8") as fh:
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
    for archive in sorted(archives, key=mtime, reverse=True)[:200]:
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
    raise RuntimeError("No encontré una copia v4.3.50 válida en los respaldos de actualización.")


def _load_direct_helper() -> str:
    if not HELPER_PATH.is_file():
        raise RuntimeError("Falta el componente local _v451_apply.py de la actualización.")
    raw = HELPER_PATH.read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != HELPER_SHA256:
        raise RuntimeError("El componente local _v451_apply.py no pasó la verificación SHA-256.")
    text = raw.decode("utf-8-sig", errors="strict")

    # Causa raíz del bucle 4.3.50→51: el helper original intentaba reconstruir
    # nuevamente v4.3.50 y exigía hallar v4.3.46–49. Aquí ya entregamos una
    # v4.3.50 validada, por lo que ese segundo puente debe omitirse por completo.
    old = "def main():\n    ensure_v450()\n    ap=ROOT/\"app.py\"; jp=ROOT/\"static\"/\"app.js\"; cp=ROOT/\"static\"/\"style.css\""
    new = "def main():\n    ap=ROOT/\"app.py\"; jp=ROOT/\"static\"/\"app.js\"; cp=ROOT/\"static\"/\"style.css\""
    if text.count(old) != 1:
        raise RuntimeError("No pude neutralizar de forma segura el puente redundante v4.3.50.")
    text = text.replace(old, new, 1)
    compile(text, "_v451_apply_direct.py", "exec")
    return text


def _build_final(base_v450: bytes) -> tuple[bytes, bytes, bytes]:
    live_js = ROOT / "static" / "app.js"
    live_css = ROOT / "static" / "style.css"
    if not live_js.exists() or not live_css.exists():
        raise RuntimeError("Faltan static/app.js o static/style.css en la instalación.")

    helper_text = _load_direct_helper()
    with tempfile.TemporaryDirectory(prefix="rp_v454_build_") as td:
        temp = Path(td)
        (temp / "static").mkdir(parents=True)
        (temp / "app.py").write_bytes(base_v450)
        shutil.copy2(live_js, temp / "static" / "app.js")
        shutil.copy2(live_css, temp / "static" / "style.css")
        helper = temp / "_v451_apply_direct.py"
        helper.write_text(helper_text, encoding="utf-8", newline="\n")

        env = dict(os.environ)
        env["RP_V451_NO_EXEC"] = "1"
        proc = subprocess.run(
            [sys.executable, str(helper)],
            cwd=str(temp),
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "falló el aplicador directo v4.3.51").strip()
            raise RuntimeError(detail[-3000:])

        app_text = (temp / "app.py").read_text(encoding="utf-8-sig", errors="strict")
        if not re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.51["\']', app_text, re.MULTILINE):
            raise RuntimeError("El aplicador directo no produjo app.py v4.3.51.")
        if APP_MARKER not in app_text:
            raise RuntimeError("El app.py construido no contiene el actualizador interno.")

        app_text, n = re.subn(
            r'^\s*APP_VERSION\s*=\s*["\']4\.3\.51["\']',
            'APP_VERSION = "4.3.54"',
            app_text,
            count=1,
            flags=re.MULTILINE,
        )
        if n != 1:
            raise RuntimeError("No se pudo marcar app.py como v4.3.54.")
        compile(app_text, "app.py", "exec")

        js_text = (temp / "static" / "app.js").read_text(encoding="utf-8", errors="strict")
        css_text = (temp / "static" / "style.css").read_text(encoding="utf-8", errors="strict")
        if JS_MARKER not in js_text:
            raise RuntimeError("No se incorporó la interfaz v4.3.51 en app.js.")
        if CSS_MARKER not in css_text:
            raise RuntimeError("No se incorporaron los estilos v4.3.51 en style.css.")
        js_text = js_text.replace("const VERSION='4.3.51';", "const VERSION='4.3.54';", 1)

        return app_text.encode("utf-8"), js_text.encode("utf-8"), css_text.encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".v454_tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _backup_live(paths: list[Path]) -> Path:
    d = _data_dir() / "update_backups"
    d.mkdir(parents=True, exist_ok=True)
    z = d / ("v454_antes_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip")
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
    _log("Inicio v4.3.54: consolidación directa desde v4.3.50")
    base, source = _find_v450()
    _log("Base v4.3.50 encontrada en " + source)

    final_app, final_js, final_css = _build_final(base)
    _log("Construcción temporal directa v4.3.54 verificada")

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
        if not re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.54["\']', installed, re.MULTILINE):
            raise RuntimeError("La instalación final no reporta v4.3.54.")
        if APP_MARKER not in installed:
            raise RuntimeError("La instalación final perdió el actualizador interno.")
        if JS_MARKER not in js.read_text(encoding="utf-8", errors="ignore"):
            raise RuntimeError("La instalación final perdió la interfaz v4.3.51.")
        if CSS_MARKER not in css.read_text(encoding="utf-8", errors="ignore"):
            raise RuntimeError("La instalación final perdió los estilos v4.3.51.")
    except Exception:
        _restore(backup)
        raise

    try:
        marker = _data_dir() / "v454_consolidated.json"
        marker.write_text(
            json.dumps({"version": "4.3.54", "source": source, "at": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    _log("v4.3.54 consolidada correctamente")
    if os.getenv("RP_V454_NO_EXEC") == "1":
        print("v4.3.54 consolidada y verificada")
        return 0

    os.execv(sys.executable, [sys.executable, str(app), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _log("ERROR: " + repr(exc))
        print("No se pudo completar v4.3.54:", exc, file=sys.stderr)
        raise
