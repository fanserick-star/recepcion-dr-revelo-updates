from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_47_updater_recovery"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> None:
    subprocess.run([sys.executable, str(HERE / "build_v4447.py")], cwd=ROOT, check=True)


def launcher_bytes() -> bytes:
    return b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def contracts() -> None:
    app = (OUT / "app.py").read_text(encoding="utf-8-sig")
    launcher = launcher_bytes().decode("utf-8-sig")
    compile(app, "app.py", "exec")
    compile(launcher, "ABRIR_RECEPCION.py", "exec")

    for marker in (
        'APP_VERSION = "4.4.47"',
        '/api/agenda/appointments/guarded',
        'window.__v4445StagedIdentityFix',
        'window.__v4446PhoneGuard',
        'CELULAR YA REGISTRADO',
    ):
        require(marker in app, f"Falta contrato acumulativo: {marker}")

    require('LAUNCHER_VERSION = "4.4.47-update-before-focus-1"' in launcher, "Launcher no tiene versión nueva")
    main = launcher[launcher.index("def main() -> None:"):launcher.index("\ndef _selftest_mutex_holder", launcher.index("def main() -> None:"))]
    update_pos = main.index("result = check_and_apply_update(ROOT)")
    focus_pos = main.index("if current == expected and _focus_existing_window()")
    require(update_pos < focus_pos, "La reutilización de ventana sigue antes de actualizar")
    require("if _running_version(timeout=0.45) is not None and _focus_existing_window()" not in main, "Sigue presente el atajo que atrapaba 4.4.43")

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == "4.4.47", "Manifest incorrecto")
    require(manifest.get("launcher_version") == "4.4.47-update-before-focus-1", "Manifest no declara launcher nuevo")
    require(manifest.get("copy") == ["app.py", "ABRIR_RECEPCION.py", "update_manifest.json"], "Alcance del update incorrecto")
    require(candidate.get("version") == "4.4.47", "Candidato incorrecto")
    paths = [x.get("path") for x in candidate.get("files", [])]
    require(paths == ["app.py", "ABRIR_RECEPCION.py", "update_manifest.json"], f"Archivos publicados inesperados: {paths}")
    require(not ({".env", "data", "BASE DE DATOS 2026.xlsx"} & set(paths)), "Se intenta tocar datos protegidos")

    by_path = {x["path"]: x for x in candidate["files"]}
    require(by_path["app.py"]["sha256"] == sha((OUT / "app.py").read_bytes()), "SHA app incorrecto")
    require(by_path["ABRIR_RECEPCION.py"]["sha256"] == sha(launcher_bytes()), "SHA launcher incorrecto")
    require(by_path["update_manifest.json"]["sha256"] == sha((OUT / "update_manifest.json").read_bytes()), "SHA manifest incorrecto")
    print("V4447_CONTRACT_OK")


def load_launcher_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("launcher_v4447_test", path)
    require(spec is not None and spec.loader is not None, "No se pudo crear spec del launcher")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DummySplash:
    def __init__(self, events): self.events = events
    def set(self, text, detail=""): self.events.append("splash:" + str(text))
    def pump(self): pass
    def close(self): pass


def lifecycle_regression() -> None:
    with tempfile.TemporaryDirectory() as td:
        launcher_path = pathlib.Path(td) / "ABRIR_RECEPCION.py"
        launcher_path.write_bytes(launcher_bytes())
        mod = load_launcher_module(launcher_path)

        # Caso exacto del bug: backend ya vivo + ventana local existente. Antes
        # v4.4.43 hacía focus y RETURN antes de consultar latest-v3.json.
        events = []
        mod._set_windows_identity = lambda: None
        mod._choose_app_port = lambda force_new=False: 8000
        mod._acquire_mutex = lambda name=mod.MUTEX_NAME: (object(), False)
        mod._release_mutex = lambda handle: events.append("release")
        mod._rp_diag_flush_outbox = lambda max_items=3: None
        mod._rp_ensure_python_runtime = lambda root: []
        mod._expected_app_version = lambda root: "4.4.47"
        mod._running_version = lambda timeout=1.0: "4.4.47"
        mod._focus_existing_window = lambda: events.append("focus") or True
        mod._open_webview = lambda: events.append("open") or True
        mod.check_and_apply_update = lambda root: events.append("update") or {"ok": True, "updated": False, "paths": []}
        mod.Splash = lambda: DummySplash(events)
        mod.time.sleep = lambda seconds: None
        mod.main()
        require("update" in events and "focus" in events, f"No se recorrió update/focus: {events}")
        require(events.index("update") < events.index("focus"), f"Se enfocó antes de actualizar: {events}")
        require("open" not in events, "Debió reutilizar la ventana ya actualizada")

        # Si el backend que quedó vivo es 4.4.43, NO se reutiliza: tras comprobar
        # el canal debe cerrarse y arrancarse con la versión esperada.
        events.clear()
        mod._running_version = lambda timeout=1.0: "4.4.43"
        mod._focus_existing_window = lambda: events.append("focus") or True
        mod._stop_server = lambda: events.append("stop")
        mod._start_server = lambda: events.append("start")
        mod._wait_server = lambda expected, seconds, splash=None: events.append("wait:" + expected) or True
        mod._open_webview = lambda: events.append("open") or True
        mod.main()
        require("update" in events, f"No comprobó canal con backend viejo: {events}")
        require("focus" not in events, f"Reutilizó ventana 4.4.43: {events}")
        require("stop" in events and "start" in events and "open" in events, f"No reinició backend viejo: {events}")

        # Cuando el update instala el propio launcher, el proceso viejo debe
        # relanzar inmediatamente el archivo nuevo antes de seguir.
        events.clear()
        mod.check_and_apply_update = lambda root: events.append("update") or {
            "ok": True, "updated": True, "version": "4.4.47", "paths": ["ABRIR_RECEPCION.py", "app.py", "update_manifest.json"]
        }
        mod._relaunch_updated_launcher = lambda: events.append("relaunch")
        mod.main()
        require(events.index("update") < events.index("relaunch"), f"No relanzó después del update: {events}")
        require("open" not in events, "El launcher viejo siguió ejecutándose después de reemplazarse")
    print("V4447_LIFECYCLE_REGRESSION_OK")


def inherited_selftests() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "ABRIR_RECEPCION.py"
        path.write_bytes(launcher_bytes())
        proc = subprocess.run([sys.executable, str(path), "--self-test-core"], cwd=td, text=True, capture_output=True, timeout=90)
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr)
        require(proc.returncode == 0, f"Self-tests heredados fallaron: {proc.returncode}")
        require("ALL PASS" in proc.stdout, "Self-tests no reportaron ALL PASS")
    print("V4447_INHERITED_UPDATER_SELFTESTS_OK")


def main() -> None:
    build()
    contracts()
    lifecycle_regression()
    inherited_selftests()
    print("VALIDATE_V4447_OK")


if __name__ == "__main__":
    main()
