from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_33_ui_fix"
LEGACY_APP = ROOT / "updates" / "v4_4_31_startup_guard" / "app.py"
BASE_APP = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "app.py"
BASE_STATIC = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "static"
CLEAN_ZIP = ROOT / "installer_clean" / "base" / "clean_base_resources.zip"


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def static_contract() -> None:
    src = LEGACY_APP.read_text(encoding="utf-8")
    app = (OUT / "app.py").read_text(encoding="utf-8")
    inner = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    latest = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    compile(app, "app.py", "exec")
    for marker in (
        'APP_VERSION = "4.4.33"',
        "import app_base_4428 as core",
        "PAYMENT_SENTINELS",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "/api/billing/payment-method",
        "Antes de emitir, marca Efectivo o Transferencia en la ficha.",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
        "window.__v4431BillingPayment",
        "_overlay_version_marker",
    ):
        require(marker in app, f"Falta marcador requerido: {marker}")
    require("function fixVersionLabels()" not in app, "Quedó fixVersionLabels regresivo")
    require(
        "const observer=new MutationObserver(()=>{\n    hookBilling();decorate();fixVersionLabels();" not in app,
        "Quedó observer global regresivo",
    )
    for marker in (
        "PAYMENT_SENTINELS",
        "set_billing_payment_method",
        "_azur_payload_for_group_v4431",
        "PAYMENT_CSS",
        "PAYMENT_JS",
    ):
        require(marker in src and marker in app, f"Se perdió funcionalidad: {marker}")
    require(inner.get("version") == "4.4.33", "Manifest interno incorrecto")
    require(inner.get("copy") == ["app.py", "update_manifest.json"], "Alcance interno no mínimo")
    paths = [x.get("path") for x in latest.get("files", [])]
    require(paths == ["app.py", "update_manifest.json"], f"Canal candidato toca de más: {paths}")
    forbidden = {"ABRIR_RECEPCION.py", ".env", "static/app.js", "static/index.html", "static/style.css", "app_base_4428.py"}
    require(not (forbidden & set(paths)), f"Candidato toca archivo prohibido: {forbidden & set(paths)}")
    require(not any(str(p).startswith("data/") or str(p).startswith(".venv/") for p in paths), "Candidato toca datos/runtime")
    print("STATIC_SCOPE_OK", paths)


def reconstruct_launcher(tmp: pathlib.Path) -> pathlib.Path:
    src = ROOT / "updates" / "v4_4_32_launcher_port_patch"
    parts = sorted(src.glob("ABRIR_RECEPCION.part*"), key=lambda p: int(p.name.split("part")[-1]))
    require(len(parts) >= 2, "Faltan partes del launcher 4.4.32")
    raw = b"".join(p.read_bytes() for p in parts)
    text = raw.decode("utf-8-sig")
    compile(text, "ABRIR_RECEPCION.py", "exec")
    for marker in ("_choose_app_port", "local_port.txt", "RP_PORT", "_running_version", "_can_bind_port"):
        require(marker in text, f"Launcher dinámico perdió {marker}")
    p = tmp / "ABRIR_RECEPCION_4432.py"
    p.write_bytes(raw)
    result = subprocess.run([os.sys.executable, str(p), "--self-test-core"], text=True, capture_output=True, timeout=45)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="")
        raise AssertionError(f"Self-tests launcher fallaron: {result.returncode}")
    require("SELFTEST OK" in result.stdout, "Self-tests launcher no terminaron correctamente")
    return p


def find_one(root: pathlib.Path, name: str) -> pathlib.Path:
    found = list(root.rglob(name))
    require(bool(found), f"No se encontró {name} en base limpia")
    return found[0]


def prepare_install(root: pathlib.Path, app_source: pathlib.Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        extracted = pathlib.Path(td) / "base"
        with zipfile.ZipFile(CLEAN_ZIP, "r") as z:
            z.extractall(extracted)
        for name in ("azur_client.py", "whatsapp_client.py", "remote_agenda.py"):
            shutil.copy2(find_one(extracted, name), root / name)
        static_src = find_one(extracted, "static") if False else None
        static_dirs = [p for p in extracted.rglob("static") if p.is_dir()]
        require(bool(static_dirs), "No se encontró static en base limpia")
        shutil.copytree(static_dirs[0], root / "static", dirs_exist_ok=True)
        mobile_dirs = [p for p in extracted.rglob("mobile") if p.is_dir()]
        if mobile_dirs:
            shutil.copytree(mobile_dirs[0], root / "mobile", dirs_exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    shutil.copy2(BASE_APP, root / "app_base_4428.py")
    shutil.copy2(BASE_STATIC / "app.js", root / "static" / "app.js")
    shutil.copy2(BASE_STATIC / "index.html", root / "static" / "index.html")
    shutil.copy2(app_source, root / "app.py")
    if app_source == OUT / "app.py":
        shutil.copy2(OUT / "update_manifest.json", root / "update_manifest.json")


def get_bytes(port: int, path: str, timeout: float = 6.0) -> tuple[int, bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return int(r.status), r.read()


def choose_free_port(start: int = 18766) -> int:
    for port in range(start, start + 30):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return port
        except OSError:
            pass
        finally:
            s.close()
    raise RuntimeError("No hay puerto de smoke libre")


def browser_smoke(runtime_python: pathlib.Path, root: pathlib.Path) -> None:
    port = choose_free_port()
    env = os.environ.copy()
    env.update(
        RP_FORCE_OFFLINE="1",
        RP_DATA_DIR=str(root / "data"),
        RP_PORT=str(port),
        DISABLE_SQLALCHEMY_CEXT_RUNTIME="1",
    )
    diag = pathlib.Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "v4433-browser"
    diag.mkdir(parents=True, exist_ok=True)
    log = (diag / "backend.log").open("w", encoding="utf-8")

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocked_8000 = False
    try:
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        blocker.bind(("127.0.0.1", 8000))
        blocker.listen(1)
        blocked_8000 = True
        print("PORT_8000_BLOCKED_BY_TEST")
    except OSError:
        print("PORT_8000_ALREADY_OCCUPIED")

    proc = subprocess.Popen([str(runtime_python), str(root / "app.py")], cwd=str(root), env=env, stdout=log, stderr=log)
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"Backend salió antes de tiempo: {proc.returncode}")
            try:
                status, raw = get_bytes(port, "/api/version", 1)
                if status == 200 and json.loads(raw).get("version") == "4.4.33":
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise AssertionError("Backend candidato no respondió /api/version")

        assets = [
            "/",
            "/static/style.css?v=4.3.34",
            "/static/app.js?v=4.4.28",
            "/v458/settings.css?v=4.3.58",
            "/v458/settings.js?v=4.3.58",
            "/v459/settings.css?v=4.3.59",
            "/v459/settings.js?v=4.3.59",
            "/v460/overlay.css?v=4.3.72",
            "/v460/overlay.js?v=4.3.72",
        ]
        for path in assets:
            t = time.perf_counter()
            status, body = get_bytes(port, path, 8)
            elapsed = time.perf_counter() - t
            print("ASSET", path, status, len(body), round(elapsed, 3))
            require(status == 200 and len(body) > 0, f"Recurso inválido: {path}")

        _, overlay_raw = get_bytes(port, "/v460/overlay.js?v=4.3.72", 8)
        overlay = overlay_raw.decode("utf-8")
        require("const VERSION='4.4.33';" in overlay, "Overlay no expone versión 4.4.33")
        require("const VERSION='4.4.28';" not in overlay, "Overlay conserva versión vieja")
        require("window.__v4431BillingPayment" in overlay, "Overlay perdió selector de pago")
        require("fixVersionLabels" not in overlay, "Overlay conserva observer regresivo")

        console: list[dict] = []
        page_errors: list[str] = []
        failed: list[dict] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1360, "height": 840})
            page.on("console", lambda m: console.append({"type": m.type, "text": m.text}))
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("requestfailed", lambda r: failed.append({"url": r.url, "failure": str(r.failure)}))
            response = page.goto(f"http://127.0.0.1:{port}/?release=v4433", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(1400)
            title = page.title()
            body_text = page.locator("body").inner_text(timeout=5000)
            payment_flag = page.evaluate("() => window.__v4431BillingPayment === true")
            ready = page.evaluate("() => document.readyState")
            badge = page.evaluate("() => document.querySelector('#connectionBadge .v460-version')?.textContent || document.querySelector('#currentVersionBadge')?.textContent || ''")
            report = {
                "status": response.status if response else None,
                "title": title,
                "ready": ready,
                "body_len": len(body_text),
                "body_start": body_text[:800],
                "payment_flag": payment_flag,
                "badge": badge,
                "page_errors": page_errors,
                "failed": failed,
                "console_errors": [x for x in console if x.get("type") == "error"],
            }
            # ensure_ascii evita que la consola CP1252 de Windows convierta un diagnóstico sano en fallo.
            print("BROWSER_REPORT", json.dumps(report, ensure_ascii=True))
            page.screenshot(path=str(diag / "screen.png"), full_page=True)
            browser.close()

        require(response is not None and response.status == 200, "Navegador no recibió HTTP 200")
        require(title == "Recepción de Pacientes", f"Título inesperado: {title!r}")
        require(ready in ("interactive", "complete"), f"DOM no listo: {ready}")
        require(len(body_text) > 200, f"Pantalla sin contenido suficiente: {len(body_text)}")
        require(payment_flag is True, "Módulo de forma de pago no inició")
        require(not page_errors, f"Errores JS: {page_errors}")
        require(not failed, f"Recursos fallidos: {failed}")
        require(badge == "v4.4.33", f"Badge no actualizado: {badge!r}")
        require(proc.poll() is None, "Backend murió durante la prueba de navegador")
        print("REAL_BROWSER_UI_OK", "port", port, "body_len", len(body_text), "badge", badge)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        if blocked_8000:
            blocker.close()
        else:
            blocker.close()
        log.close()


def updater_smoke(launcher_path: pathlib.Path) -> None:
    spec = importlib.util.spec_from_file_location("rp_launcher_4432", launcher_path)
    require(spec is not None and spec.loader is not None, "No se pudo importar launcher")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    app_new = (OUT / "app.py").read_bytes()
    manifest_new = (OUT / "update_manifest.json").read_bytes()
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))

    class Handler(http.server.BaseHTTPRequestHandler):
        files: dict[str, bytes] = {}

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            body = self.files.get(path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    remote = dict(candidate)
    remote["files"] = [
        {"path": "app.py", "url": base + "/app.py", "sha256": hashlib.sha256(app_new).hexdigest(), "encoding": "utf-8"},
        {"path": "update_manifest.json", "url": base + "/update_manifest.json", "sha256": hashlib.sha256(manifest_new).hexdigest(), "encoding": "utf-8"},
    ]
    Handler.files = {
        "/latest.json": json.dumps(remote).encode("utf-8"),
        "/app.py": app_new,
        "/update_manifest.json": manifest_new,
    }
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

    def seed(root: pathlib.Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "data").mkdir(exist_ok=True)
        (root / "static").mkdir(exist_ok=True)
        shutil.copy2(LEGACY_APP, root / "app.py")
        shutil.copy2(ROOT / "updates" / "v4_4_32_launcher_port_patch" / "update_manifest.json", root / "update_manifest.json")
        (root / ".env").write_text("SECRET_KEEP=1\n", encoding="utf-8")
        (root / "data" / "keep.txt").write_text("DATA_KEEP", encoding="utf-8")
        (root / "static" / "keep.txt").write_text("STATIC_KEEP", encoding="utf-8")

    try:
        with tempfile.TemporaryDirectory() as td:
            install = pathlib.Path(td) / "install"
            seed(install)
            env_before = (install / ".env").read_bytes()
            data_before = (install / "data" / "keep.txt").read_bytes()
            static_before = (install / "static" / "keep.txt").read_bytes()
            result = mod.check_and_apply_update(install, base + "/latest.json", attempts=1, timeout=3, allow_test_sources=True)
            require(result.get("ok") and result.get("updated"), f"Updater no aplicó candidato: {result}")
            require(mod._local_package_version(install) == "4.4.33", "Package local no quedó 4.4.33")
            require(mod._installed_app_version(install) == "4.4.33", "app.py local no quedó 4.4.33")
            require((install / ".env").read_bytes() == env_before, ".env fue modificado")
            require((install / "data" / "keep.txt").read_bytes() == data_before, "data fue modificado")
            require((install / "static" / "keep.txt").read_bytes() == static_before, "static fue modificado")
            second = mod.check_and_apply_update(install, base + "/latest.json", attempts=1, timeout=3, allow_test_sources=True)
            require(second.get("ok") and not second.get("updated"), f"Segundo inicio volvió a descargar: {second}")
            print("UPDATE_4432_TO_4433_OK")

        with tempfile.TemporaryDirectory() as td:
            rollback = pathlib.Path(td) / "rollback"
            seed(rollback)
            old_app = (rollback / "app.py").read_bytes()
            old_manifest = (rollback / "update_manifest.json").read_bytes()
            try:
                mod._apply_remote(remote, rollback, attempts=1, timeout=3, test_fail_after=1, allow_test_sources=True)
                raise AssertionError("La prueba de rollback no provocó fallo")
            except RuntimeError as exc:
                require("Fallo simulado" in str(exc), f"Fallo inesperado en rollback: {exc}")
            require((rollback / "app.py").read_bytes() == old_app, "Rollback no restauró app.py")
            require((rollback / "update_manifest.json").read_bytes() == old_manifest, "Rollback no restauró manifest")
            print("ROLLBACK_4433_OK")
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    static_contract()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        launcher = reconstruct_launcher(tmp)
        install = tmp / "full-install"
        prepare_install(install, OUT / "app.py")
        browser_smoke(pathlib.Path(os.sys.executable), install)
        updater_smoke(launcher)
    print("V4433_ALL_VALIDATIONS_OK")


if __name__ == "__main__":
    main()
