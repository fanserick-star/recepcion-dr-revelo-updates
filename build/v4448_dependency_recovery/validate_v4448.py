from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_48_dependency_recovery"
PREV = ROOT / "updates" / "v4_4_47_updater_recovery"
LEGACY = ROOT / "updates" / "v4_4_43_daily_emitted_whatsapp_schedule"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_text_bytes(path: pathlib.Path) -> bytes:
    return path.read_text(encoding="utf-8-sig").encode("utf-8")


def build() -> None:
    subprocess.run([sys.executable, str(HERE / "build_v4448.py")], cwd=ROOT, check=True)


def launcher_bytes(folder: pathlib.Path) -> bytes:
    return b"".join((folder / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def legacy_launcher_bytes() -> bytes:
    return launcher_bytes(LEGACY)


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"No se pudo cargar {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def contracts() -> None:
    app = (OUT / "app.py").read_text(encoding="utf-8-sig")
    app_base = (OUT / "app_base_4428.py").read_text(encoding="utf-8-sig")
    launcher = launcher_bytes(OUT).decode("utf-8-sig")
    compile(app, "app.py", "exec")
    compile(app_base, "app_base_4428.py", "exec")
    compile(launcher, "ABRIR_RECEPCION.py", "exec")

    for marker in (
        'APP_VERSION = "4.4.48"',
        '/api/agenda/appointments/guarded',
        'window.__v4445StagedIdentityFix',
        '/api/identity/phone-owner',
        'window.__v4446PhoneDuplicateGuard',
        'stopIfDuplicate',
        'Este celular ya está registrado',
    ):
        require(marker in app, f"Falta contrato acumulativo: {marker}")

    require(
        'LAUNCHER_VERSION = "4.4.48-update-before-focus-dependency-safe-1"' in launcher,
        "Launcher no tiene versión de recuperación",
    )
    main = launcher[
        launcher.index("def main() -> None:"):
        launcher.index("\ndef _selftest_mutex_holder", launcher.index("def main() -> None:"))
    ]
    require(
        main.index("result = check_and_apply_update(ROOT)")
        < main.index("if current == expected and _focus_existing_window()"),
        "El launcher volvió a enfocar antes de actualizar",
    )

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == "4.4.48", "Manifest incorrecto")
    require(manifest.get("required_dependencies") == ["app_base_4428.py"], "Dependencia obligatoria no declarada")
    expected_paths = ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"]
    require(manifest.get("copy") == expected_paths, f"copy incorrecto: {manifest.get('copy')}")
    require([x.get("path") for x in candidate.get("files", [])] == expected_paths, "El candidato no incluye la dependencia")
    by_path = {x["path"]: x for x in candidate["files"]}
    require(by_path["app.py"]["sha256"] == sha((OUT / "app.py").read_bytes()), "SHA app local incorrecto")
    require(by_path["app_base_4428.py"]["sha256"] == sha((OUT / "app_base_4428.py").read_bytes()), "SHA app_base local incorrecto")
    require(by_path["ABRIR_RECEPCION.py"]["sha256"] == sha(launcher_bytes(OUT)), "SHA launcher local incorrecto")
    require(by_path["update_manifest.json"]["sha256"] == sha((OUT / "update_manifest.json").read_bytes()), "SHA manifest local incorrecto")
    require(
        sha((OUT / "app_base_4428.py").read_bytes()) == sha(stable_text_bytes(LEGACY / "app_base_4428.py")),
        "app_base_4428.py no es la base estable normalizada",
    )
    print("V4448_CONTRACT_OK")


class Handler(BaseHTTPRequestHandler):
    files: dict[str, tuple[bytes, str]] = {}

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        item = self.files.get(path)
        if item is None:
            self.send_response(404)
            self.end_headers()
            return
        body, ctype = item
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def start_server():
    class H(Handler):
        pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def localize_candidate(candidate: dict, folder: pathlib.Path, base: str) -> tuple[dict, dict[str, tuple[bytes, str]]]:
    # Esta prueba es semántica: al servir archivos desde un checkout Windows,
    # recalculamos SHA sobre esos bytes locales para no confundir CRLF con el
    # problema que queremos probar. Los SHA publicados se validan luego contra Raw.
    remote = copy.deepcopy(candidate)
    files: dict[str, tuple[bytes, str]] = {}
    for idx, item in enumerate(remote.get("files") or []):
        target = str(item.get("path") or "")
        if target == "ABRIR_RECEPCION.py":
            local_parts = []
            joined = b""
            for part_no in range(1, 5):
                route = f"/item{idx}_part{part_no}"
                data = (folder / f"ABRIR_RECEPCION.part{part_no}").read_bytes()
                files[route] = (data, "text/plain")
                joined += data
                local_parts.append(base + route)
            item.pop("url", None)
            item["parts"] = local_parts
            item["sha256"] = sha(joined)
        else:
            route = f"/item{idx}"
            data = (folder / target).read_bytes()
            files[route] = (data, "application/octet-stream")
            item.pop("parts", None)
            item["url"] = base + route
            item["sha256"] = sha(data)
    files["/manifest"] = ((json.dumps(remote, ensure_ascii=False) + "\n").encode("utf-8"), "application/json")
    return remote, files


def seed_legacy_install(root: pathlib.Path) -> dict[pathlib.Path, bytes]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    for name in ("app.py", "app_base_4428.py", "update_manifest.json"):
        shutil.copyfile(LEGACY / name, root / name)
    (root / "ABRIR_RECEPCION.py").write_bytes(legacy_launcher_bytes())

    sentinels = {
        root / ".env": b"PRIVATE_SENTINEL=KEEP_ME\n",
        root / "BASE DE DATOS 2026.xlsx": b"EXCEL_SENTINEL_BYTES",
        root / "data" / "offline_cache.db": b"SQLITE_OFFLINE_SENTINEL",
        root / "data" / "recepcion.db": b"SQLITE_RECEPCION_SENTINEL",
    }
    for path, data in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return sentinels


def load_legacy_module(temp: pathlib.Path):
    path = temp / "legacy_443_launcher.py"
    path.write_bytes(legacy_launcher_bytes())
    return load_module(path, "legacy_443_updater_test")


def prove_v4447_is_rejected_by_real_443() -> None:
    candidate = json.loads((PREV / "candidate_latest.json").read_text(encoding="utf-8"))
    server, base = start_server()
    try:
        _, files = localize_candidate(candidate, PREV, base)
        server.RequestHandlerClass.files = files
        with tempfile.TemporaryDirectory() as td:
            temp = pathlib.Path(td)
            install = temp / "install"
            seed_legacy_install(install)
            legacy = load_legacy_module(temp)
            result = legacy.check_and_apply_update(
                install, base + "/manifest", attempts=1, timeout=4, allow_test_sources=True
            )
            require(not result.get("updated"), f"4.4.47 inesperadamente actualizó: {result}")
            require(result.get("deferred"), f"4.4.47 no fue rechazada de forma segura: {result}")
            error = str(result.get("error") or "")
            require("app_base_4428.py" in error, f"No se reprodujo la causa real: {error}")
    finally:
        server.shutdown()
        server.server_close()
    print("V4447_REJECTION_BY_LEGACY_443_PROVEN")


def prove_v4448_is_accepted_by_real_443() -> None:
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    server, base = start_server()
    try:
        _, files = localize_candidate(candidate, OUT, base)
        server.RequestHandlerClass.files = files
        with tempfile.TemporaryDirectory() as td:
            temp = pathlib.Path(td)
            install = temp / "install"
            sentinels = seed_legacy_install(install)
            legacy = load_legacy_module(temp)
            result = legacy.check_and_apply_update(
                install, base + "/manifest", attempts=1, timeout=8, allow_test_sources=True
            )
            require(result.get("ok") and result.get("updated"), f"El actualizador 4.4.43 no instaló 4.4.48: {result}")
            require(result.get("version") == "4.4.48", f"Versión final incorrecta: {result}")
            require(legacy._local_package_version(install) == "4.4.48", "Manifest local no llegó a 4.4.48")
            require(legacy._installed_app_version(install) == "4.4.48", "app.py local no llegó a 4.4.48")
            require(legacy._installation_consistent(install), "Instalación 4.4.48 no quedó coherente para el updater 4.4.43")
            launcher = (install / "ABRIR_RECEPCION.py").read_text(encoding="utf-8-sig")
            require('LAUNCHER_VERSION = "4.4.48-update-before-focus-dependency-safe-1"' in launcher, "Launcher no se reemplazó")
            require(
                sha((install / "app_base_4428.py").read_bytes()) == sha((OUT / "app_base_4428.py").read_bytes()),
                "La dependencia estable cambió",
            )
            for path, data in sentinels.items():
                require(path.read_bytes() == data, f"Archivo protegido fue alterado: {path.name}")
    finally:
        server.shutdown()
        server.server_close()
    print("V4448_ACCEPTED_BY_LEGACY_443")


def new_launcher_selftests() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "ABRIR_RECEPCION.py"
        path.write_bytes(launcher_bytes(OUT))
        proc = subprocess.run(
            [sys.executable, str(path), "--self-test-core"],
            cwd=td,
            text=True,
            capture_output=True,
            timeout=100,
        )
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr)
        require(proc.returncode == 0, f"Self-tests del launcher fallaron: {proc.returncode}")
        require("SELFTEST OK:" in proc.stdout, "Self-tests no reportaron resumen correcto")
    print("V4448_LAUNCHER_SELFTESTS_OK")


def main() -> None:
    build()
    contracts()
    prove_v4447_is_rejected_by_real_443()
    prove_v4448_is_accepted_by_real_443()
    new_launcher_selftests()
    print("VALIDATE_V4448_OK")


if __name__ == "__main__":
    main()
