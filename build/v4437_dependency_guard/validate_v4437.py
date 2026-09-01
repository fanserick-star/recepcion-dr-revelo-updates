from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_37_dependency_guard"
OLD_LAUNCHER_DIR = ROOT / "updates" / "v4_4_32_launcher_port_patch"
APP_4436 = ROOT / "updates" / "v4_4_36_default_cash" / "app.py"
MANIFEST_4436 = ROOT / "updates" / "v4_4_36_default_cash" / "update_manifest.json"
BASE = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "app.py"
STATIC_APP = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "static" / "app.js"
STATIC_INDEX = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "static" / "index.html"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def old_launcher_bytes() -> bytes:
    return b"".join((OLD_LAUNCHER_DIR / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def new_launcher_bytes() -> bytes:
    return b"".join(
        [(OLD_LAUNCHER_DIR / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 4)]
        + [(OUT / "ABRIR_RECEPCION.part4").read_bytes()]
    )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Handler(BaseHTTPRequestHandler):
    files: dict[str, tuple[bytes, str]] = {}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        item = self.files.get(path)
        if not item:
            self.send_response(404); self.end_headers(); return
        data, ctype = item
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def server(files: dict[str, tuple[bytes, str]]):
    Handler.files = files
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_payloads() -> tuple[dict, dict[str, bytes]]:
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    payloads = {
        "ABRIR_RECEPCION.py": new_launcher_bytes(),
        "app_base_4428.py": BASE.read_bytes(),
        "app.py": APP_4436.read_bytes(),
        "static/app.js": STATIC_APP.read_bytes(),
        "static/index.html": STATIC_INDEX.read_bytes(),
        "update_manifest.json": (OUT / "update_manifest.json").read_bytes(),
    }
    for item in candidate["files"]:
        require(item["path"] in payloads, f"Payload no preparado: {item['path']}")
        require(sha(payloads[item["path"]]) == item["sha256"], f"SHA candidato incorrecto: {item['path']}")
    return candidate, payloads


def local_manifest(candidate: dict, payloads: dict[str, bytes], base: str) -> dict:
    remote = {k: v for k, v in candidate.items() if k != "files"}
    remote["files"] = []
    for idx, item in enumerate(candidate["files"]):
        rel = item["path"]
        remote["files"].append({
            "path": rel,
            "url": f"{base}/payload/{idx}",
            "sha256": sha(payloads[rel]),
            "encoding": "utf-8",
        })
    return remote


def make_broken_4436(root: pathlib.Path) -> None:
    root.mkdir(parents=True)
    (root / "app.py").write_bytes(APP_4436.read_bytes())
    (root / "ABRIR_RECEPCION.py").write_bytes(old_launcher_bytes())
    (root / "update_manifest.json").write_bytes(MANIFEST_4436.read_bytes())
    (root / "static").mkdir()
    (root / "static" / "app.js").write_text("OLD_STATIC_APP", encoding="utf-8")
    (root / "static" / "index.html").write_text("OLD_STATIC_INDEX", encoding="utf-8")
    (root / ".env").write_text("KEEP_ENV=YES\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "keep.txt").write_text("KEEP_DATA", encoding="utf-8")
    (root / ".venv").mkdir()
    (root / ".venv" / "keep.txt").write_text("KEEP_VENV", encoding="utf-8")
    require(not (root / "app_base_4428.py").exists(), "Fixture no está rota como producción")


def test_old_launcher_repairs_direct_jump(candidate: dict, payloads: dict[str, bytes]) -> pathlib.Path:
    td = tempfile.mkdtemp(prefix="rp-v4437-broken-")
    root = pathlib.Path(td) / "install"
    make_broken_4436(root)
    files = {"/manifest": (b"{}", "application/json")}
    httpd, base = server(files)
    try:
        remote = local_manifest(candidate, payloads, base)
        Handler.files = {"/manifest": (json.dumps(remote).encode(), "application/json")}
        for idx, item in enumerate(remote["files"]):
            Handler.files[f"/payload/{idx}"] = (payloads[item["path"]], "application/octet-stream")
        old = load_module(root / "ABRIR_RECEPCION.py", "rp_old_launcher_4432")
        result = old.check_and_apply_update(root, base + "/manifest", attempts=1, timeout=3, allow_test_sources=True)
        require(result.get("ok") and result.get("updated"), f"Launcher 4.4.32 no reparó salto directo: {result}")
        require((root / "app_base_4428.py").is_file(), "No restauró app_base_4428.py")
        require(sha((root / "app_base_4428.py").read_bytes()) == sha(BASE.read_bytes()), "Base restaurada incorrecta")
        require((root / ".env").read_text(encoding="utf-8") == "KEEP_ENV=YES\n", ".env fue alterado")
        require((root / "data" / "keep.txt").read_text() == "KEEP_DATA", "data fue alterado")
        require((root / ".venv" / "keep.txt").read_text() == "KEEP_VENV", ".venv fue alterado")
        installed = json.loads((root / "update_manifest.json").read_text(encoding="utf-8"))
        require(installed["version"] == "4.4.37" and installed["app_version"] == "4.4.36", "Manifest instalado incorrecto")
        compile((root / "app.py").read_text(encoding="utf-8-sig"), "app.py", "exec")
        compile((root / "app_base_4428.py").read_text(encoding="utf-8-sig"), "app_base_4428.py", "exec")
        print("DIRECT_JUMP_4436_BROKEN_TO_4437_OK")
    finally:
        httpd.shutdown(); httpd.server_close()
    return root


def test_same_version_self_repair(root: pathlib.Path, candidate: dict, payloads: dict[str, bytes]) -> None:
    launcher = load_module(root / "ABRIR_RECEPCION.py", "rp_new_launcher_4437_repair")
    require(launcher._installation_consistent(root), "Instalación 4.4.37 debería ser coherente")
    (root / "app_base_4428.py").unlink()
    require(not launcher._installation_consistent(root), "No detectó dependencia faltante en misma versión")

    httpd, base = server({})
    try:
        remote = local_manifest(candidate, payloads, base)
        Handler.files = {"/manifest": (json.dumps(remote).encode(), "application/json")}
        for idx, item in enumerate(remote["files"]):
            Handler.files[f"/payload/{idx}"] = (payloads[item["path"]], "application/octet-stream")
        result = launcher.check_and_apply_update(root, base + "/manifest", attempts=1, timeout=3, allow_test_sources=True)
        require(result.get("ok") and result.get("updated"), f"No autoreparó misma versión: {result}")
        require((root / "app_base_4428.py").is_file(), "Autoreparación no repuso base")
        require(launcher._installation_consistent(root), "Sigue incoherente después de autoreparar")
        print("SAME_VERSION_MISSING_DEPENDENCY_REPAIR_OK")

        # Corrupción sintáctica también debe detectarse y repararse.
        (root / "app_base_4428.py").write_text("def broken(:\n", encoding="utf-8")
        require(not launcher._installation_consistent(root), "No detectó dependencia corrupta")
        result2 = launcher.check_and_apply_update(root, base + "/manifest", attempts=1, timeout=3, allow_test_sources=True)
        require(result2.get("ok") and result2.get("updated"), f"No reparó dependencia corrupta: {result2}")
        require(launcher._installation_consistent(root), "Sigue incoherente tras reparar corrupción")
        print("SAME_VERSION_CORRUPT_DEPENDENCY_REPAIR_OK")
    finally:
        httpd.shutdown(); httpd.server_close()


def test_future_incomplete_manifest_is_rejected(root: pathlib.Path) -> None:
    launcher = load_module(root / "ABRIR_RECEPCION.py", "rp_new_launcher_4437_reject")
    old_app = (root / "app.py").read_bytes()
    old_manifest = (root / "update_manifest.json").read_bytes()
    future_app = b'APP_VERSION = "4.4.38"\nimport app_missing_future\n'
    future_inner = json.dumps({
        "product": "recepcion-pacientes",
        "version": "4.4.38",
        "app_version": "4.4.38",
        "runtime_version": "4.4.38",
        "copy": ["app.py", "update_manifest.json"],
    }, indent=2).encode()
    httpd, base = server({})
    try:
        remote = {
            "product": "recepcion-pacientes", "version": "4.4.38",
            "app_version": "4.4.38", "runtime_version": "4.4.38",
            "files": [
                {"path": "app.py", "url": base + "/future_app", "sha256": sha(future_app), "encoding": "utf-8"},
                {"path": "update_manifest.json", "url": base + "/future_manifest", "sha256": sha(future_inner), "encoding": "utf-8"},
            ],
        }
        Handler.files = {
            "/manifest": (json.dumps(remote).encode(), "application/json"),
            "/future_app": (future_app, "text/plain"),
            "/future_manifest": (future_inner, "application/json"),
        }
        result = launcher.check_and_apply_update(root, base + "/manifest", attempts=1, timeout=3, allow_test_sources=True)
        require(result.get("ok") and result.get("deferred"), f"No rechazó de forma segura manifest incompleto: {result}")
        require((root / "app.py").read_bytes() == old_app, "Manifest incompleto reemplazó app.py")
        require((root / "update_manifest.json").read_bytes() == old_manifest, "Manifest incompleto reemplazó manifest local")
        require(launcher._installation_consistent(root), "Instalación funcional quedó dañada tras rechazo")
        print("FUTURE_MISSING_LOCAL_MODULE_REJECTED_BEFORE_SWAP_OK")
    finally:
        httpd.shutdown(); httpd.server_close()


def test_dynamic_port_preserved(root: pathlib.Path) -> None:
    launcher = load_module(root / "ABRIR_RECEPCION.py", "rp_new_launcher_4437_port")
    require(launcher.LAUNCHER_VERSION == "4.4.32-dynamic-port-patch-1", "Se sustituyó el launcher dinámico")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied = False
    try:
        try:
            sock.bind(("127.0.0.1", 8000)); sock.listen(1); occupied = True
        except OSError:
            pass
        launcher._set_app_port(8000)
        chosen = launcher._choose_app_port(force_new=True)
        require(chosen != 8000, "Eligió 8000 pese a forzar puerto nuevo")
        require(1024 <= chosen <= 65535, "Puerto elegido inválido")
        print("DYNAMIC_PORT_GUARD_PRESERVED_OK", chosen, "occupied8000", occupied)
    finally:
        sock.close()


def test_launcher_selftests(root: pathlib.Path) -> None:
    result = subprocess.run([sys.executable, str(root / "ABRIR_RECEPCION.py"), "--self-test-core"],
                            cwd=str(root), text=True, capture_output=True, timeout=90)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="")
    require(result.returncode == 0, f"Self-test launcher falló: {result.returncode}")
    require("SELFTEST OK" in result.stdout, "Launcher no confirmó self-tests")
    print("LAUNCHER_SELFTESTS_OK")


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "build" / "v4437_dependency_guard" / "build_v4437.py")], check=True)
    candidate, payloads = candidate_payloads()
    paths = [x["path"] for x in candidate["files"]]
    expected = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    require(paths == expected, f"El canal de reparación no es acumulativo: {paths}")
    require(candidate["app_version"] == "4.4.36", "La reparación cambió funcionalidad de app")
    require(sha(payloads["app.py"]) == "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e", "app.py no es exactamente 4.4.36")
    require(sha(payloads["app_base_4428.py"]) == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba", "base no es exactamente la estable esperada")
    print("CUMULATIVE_MANIFEST_CONTRACT_OK")

    root = test_old_launcher_repairs_direct_jump(candidate, payloads)
    test_same_version_self_repair(root, candidate, payloads)
    test_future_incomplete_manifest_is_rejected(root)
    test_dynamic_port_preserved(root)
    test_launcher_selftests(root)
    print("VALIDATE_V4437_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
