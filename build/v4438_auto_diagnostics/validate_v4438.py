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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_38_auto_diagnostics"
SOURCE_REF = "38399d6767db0c79e81ec357db1176e39ff3d7e5"
SOURCE_PREFIX = "updates/v4_4_37_dependency_guard"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


def old_launcher() -> bytes:
    return b"".join(git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5))


def new_launcher() -> bytes:
    return b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"No se puede cargar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCursor:
    def __init__(self, owner):
        self.owner = owner

    def execute(self, sql, params=None):
        self.owner.calls.append((str(sql), params))
        if "INSERT INTO rp_diagnostics_incidents" in str(sql):
            self.owner.inserts.append(params)

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.calls = []
        self.inserts = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class H(BaseHTTPRequestHandler):
    files = {}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        item = self.files.get(path)
        if not item:
            self.send_response(404)
            self.end_headers()
            return
        body, content_type = item
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def server(files=None):
    H.files = files or {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def payloads():
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    payload = {
        "ABRIR_RECEPCION.py": new_launcher(),
        "app_base_4428.py": (OUT / "app_base_4428.py").read_bytes(),
        "app.py": (OUT / "app.py").read_bytes(),
        "static/app.js": (OUT / "static" / "app.js").read_bytes(),
        "static/index.html": (OUT / "static" / "index.html").read_bytes(),
        "update_manifest.json": (OUT / "update_manifest.json").read_bytes(),
    }
    for item in candidate["files"]:
        require(sha(payload[item["path"]]) == item["sha256"], f"SHA local incorrecto {item['path']}")
    return candidate, payload


def served(candidate: dict, payload: dict):
    srv, base = server()
    remote = {k: v for k, v in candidate.items() if k != "files"}
    remote["files"] = []
    files = {}
    for idx, item in enumerate(candidate["files"]):
        url = f"{base}/p/{idx}"
        remote["files"].append({"path": item["path"], "url": url, "sha256": sha(payload[item["path"]]), "encoding": "utf-8"})
        files[f"/p/{idx}"] = (payload[item["path"]], "application/octet-stream")
    files["/manifest"] = (json.dumps(remote).encode("utf-8"), "application/json")
    H.files = files
    return srv, base


def prepare_current_install(root: pathlib.Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ABRIR_RECEPCION.py").write_bytes(old_launcher())
    for rel in ("app_base_4428.py", "app.py"):
        (root / rel).write_bytes(git_bytes(rel))
    (root / "static").mkdir()
    (root / "static" / "app.js").write_bytes(git_bytes("static/app.js"))
    (root / "static" / "index.html").write_bytes(git_bytes("static/index.html"))
    (root / "update_manifest.json").write_bytes(git_bytes("update_manifest.json"))
    (root / "data").mkdir()
    (root / ".venv").mkdir()
    (root / "data" / "keep.txt").write_text("KEEP_DATA", encoding="utf-8")
    (root / ".venv" / "keep.txt").write_text("KEEP_VENV", encoding="utf-8")
    (root / ".env").write_text(
        "DATABASE_URL=postgresql://diag_user:ENV_SUPER_SECRET@ep-private.example/neondb?sslmode=require\nKEEP_ENV=YES\n",
        encoding="utf-8",
    )


def update_from_4437(candidate, payload):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "install"
        prepare_current_install(root)
        env_before = (root / ".env").read_bytes()
        srv, base = served(candidate, payload)
        try:
            old = load(root / "ABRIR_RECEPCION.py", "launcher4437_update_test")
            result = old.check_and_apply_update(root, base + "/manifest", attempts=1, timeout=3, allow_test_sources=True)
            require(result.get("ok") and result.get("updated"), f"4.4.37 no instaló 4.4.38: {result}")
            require((root / "ABRIR_RECEPCION.py").read_bytes() == payload["ABRIR_RECEPCION.py"], "Launcher nuevo no quedó exacto")
            require((root / ".env").read_bytes() == env_before, ".env fue modificado")
            require((root / "data" / "keep.txt").read_text() == "KEEP_DATA", "data existente fue modificado")
            require((root / ".venv" / "keep.txt").read_text() == "KEEP_VENV", ".venv fue modificado")
            print("UPDATE_4437_TO_4438_PROTECTED_OK")
        finally:
            srv.shutdown()
            srv.server_close()


def diagnostics_privacy_and_queue(candidate, payload):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "install"
        root.mkdir()
        (root / "ABRIR_RECEPCION.py").write_bytes(payload["ABRIR_RECEPCION.py"])
        (root / "app.py").write_bytes(payload["app.py"])
        (root / "app_base_4428.py").write_bytes(payload["app_base_4428.py"])
        (root / "update_manifest.json").write_bytes(payload["update_manifest.json"])
        (root / "data").mkdir()
        secret_env = "postgresql://diag_user:ENV_SUPER_SECRET@ep-private.example/neondb?sslmode=require"
        env_bytes = ("DATABASE_URL=" + secret_env + "\nKEEP_ENV=YES\n").encode()
        (root / ".env").write_bytes(env_bytes)
        sensitive = (
            "DATABASE_URL=postgresql://u:LOG_DB_PASSWORD@host.example/neondb token=TOKEN_XYZ_987654 "
            "Authorization: Bearer BEARER_SUPER_TOKEN correo: paciente.real@example.com "
            "cedula: 1207087550 telefono: 0989286631 C:\\Users\\Consultorio\\Downloads\\Recepcion\\app.py "
            "IP 8.8.8.8\n"
        )
        (root / "data" / "launcher_errors.log").write_text(sensitive + "RuntimeError backend muerto\n", encoding="utf-8")
        (root / "data" / "backend_startup.log").write_text(sensitive + "Traceback line 16 ModuleNotFoundError\n", encoding="utf-8")
        (root / "data" / "auto_update_state.json").write_text(json.dumps({"last_error": sensitive}), encoding="utf-8")

        m = load(root / "ABRIR_RECEPCION.py", "launcher4438_diag_test")
        fake = FakeConn()
        m._rp_diag_db_connect = lambda: fake
        result = m._rp_diag_report("launcher_fatal", RuntimeError("Bearer EXC_TOKEN correo admin@example.com cedula 1712345678"))
        require(result.get("status") == "sent", f"Diagnóstico fake no enviado: {result}")
        require(result.get("incident_id", "").startswith("INC-"), "ID de incidente inválido")
        require(len(fake.inserts) == 1, f"Insert esperado 1, recibido {len(fake.inserts)}")
        serialized = json.dumps(fake.inserts, ensure_ascii=False, default=str)
        forbidden = [
            "ENV_SUPER_SECRET", "LOG_DB_PASSWORD", "TOKEN_XYZ_987654", "BEARER_SUPER_TOKEN", "EXC_TOKEN",
            "paciente.real@example.com", "admin@example.com", "1207087550", "0989286631", "1712345678",
            "C:\\Users\\Consultorio", "8.8.8.8", secret_env,
        ]
        leaked = [x for x in forbidden if x in serialized]
        require(not leaked, f"PRIVACIDAD: se filtraron datos: {leaked}")
        require("[CORREO_REDACTADO]" in serialized, "No confirmó redacción de correo")
        require("[NUMERO_REDACTADO]" in serialized, "No confirmó redacción numérica")
        require("[DATABASE_URL_REDACTADA]" in serialized or "[REDACTADO]" in serialized, "No confirmó redacción de secreto")
        require((root / ".env").read_bytes() == env_bytes, "Diagnóstico alteró .env")
        outbox = root / "data" / "diagnostic_outbox"
        require(not list(outbox.glob("*.json")), "Incidente enviado quedó en cola")
        print("DIAGNOSTIC_PRIVACY_SENT_OK", result["incident_id"])

        # Dedupe: mismo fallo/logs dentro de 30 minutos no debe inundar Neon.
        result2 = m._rp_diag_report("launcher_fatal", RuntimeError("Bearer EXC_TOKEN correo admin@example.com cedula 1712345678"))
        require(result2.get("incident_id") == result.get("incident_id"), "Dedupe cambió incidente")
        require(len(fake.inserts) == 1, "Dedupe volvió a insertar el mismo fallo")
        print("DIAGNOSTIC_DEDUPE_OK")

        # Otro error sin red: queda sanitizado en cola y se reintenta al próximo arranque.
        def offline():
            raise OSError("network offline password=OFFLINE_SECRET token=OFFLINE_TOKEN")
        m._rp_diag_db_connect = offline
        queued = m._rp_diag_report("update_blocked", RuntimeError("otro fallo correo cola@example.com 0999999999"))
        require(queued.get("status") == "queued", f"No quedó en cola: {queued}")
        queued_files = list(outbox.glob("INC-*.json"))
        require(len(queued_files) == 1, f"Cola esperada 1, recibida {len(queued_files)}")
        queue_text = queued_files[0].read_text(encoding="utf-8")
        require("cola@example.com" not in queue_text and "0999999999" not in queue_text, "Cola contiene PII")
        require("OFFLINE_SECRET" not in queue_text and "OFFLINE_TOKEN" not in queue_text, "Cola contiene secreto de transporte")
        fake_retry = FakeConn()
        m._rp_diag_db_connect = lambda: fake_retry
        sent = m._rp_diag_flush_outbox(max_items=3)
        require(sent == 1 and len(fake_retry.inserts) == 1, "Reintento no envió la cola")
        require(not list(outbox.glob("*.json")), "Cola no se vació")
        last_id = (root / "data" / "last_diagnostic_incident.txt").read_text().strip()
        require(last_id == queued["incident_id"], "ID local no apunta al último incidente")
        print("DIAGNOSTIC_OFFLINE_RETRY_OK", last_id)

        # Opt-out documentado: no crea otro incidente.
        os.environ["RP_DIAGNOSTICS_ENABLED"] = "0"
        before = len(fake_retry.inserts)
        disabled = m._rp_diag_report("launcher_fatal", RuntimeError("disabled"))
        require(disabled.get("status") == "disabled" and len(fake_retry.inserts) == before, "Opt-out no funcionó")
        os.environ.pop("RP_DIAGNOSTICS_ENABLED", None)
        print("DIAGNOSTIC_OPTOUT_OK")

        # Puerto dinámico y guardia de dependencia siguen presentes.
        require(m.LAUNCHER_VERSION == "4.4.38-dynamic-port-dependency-diagnostics-1", "Versión launcher nueva incorrecta")
        require(m._installation_consistent(root), "Instalación completa no se reconoce coherente")
        (root / "app_base_4428.py").write_text("def broken(:\n", encoding="utf-8")
        require(not m._installation_consistent(root), "Guardia v4.4.37 dejó de detectar base corrupta")
        (root / "app_base_4428.py").write_bytes(payload["app_base_4428.py"])
        sk = socket.socket()
        occupied = False
        try:
            try:
                sk.bind(("127.0.0.1", 8000)); sk.listen(1); occupied = True
            except OSError:
                pass
            m._set_app_port(8000)
            chosen = m._choose_app_port(force_new=True)
            require(chosen != 8000 and 1024 <= chosen <= 65535, f"Puerto dinámico roto: {chosen}")
        finally:
            sk.close()
        print("DYNAMIC_PORT_AND_DEPENDENCY_GUARD_PRESERVED_OK", occupied)

        # Self-tests históricos del launcher siguen pasando.
        proc = subprocess.run([sys.executable, str(root / "ABRIR_RECEPCION.py"), "--self-test-core"], cwd=str(root), capture_output=True, text=True, timeout=140)
        print(proc.stdout, end="")
        if proc.returncode:
            print(proc.stderr, end="")
        require(proc.returncode == 0 and "SELFTEST OK" in proc.stdout, f"Selftest launcher falló: {proc.returncode}")
        print("LAUNCHER_SELFTEST_OK")


def main():
    subprocess.run([sys.executable, str(ROOT / "build" / "v4438_auto_diagnostics" / "build_v4438.py")], check=True)
    candidate, payload = payloads()
    required = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    require(candidate.get("version") == "4.4.38", "Versión candidato incorrecta")
    require(candidate.get("app_version") == "4.4.36", "App runtime cambió sin necesidad")
    require([x["path"] for x in candidate["files"]] == required, "Release dejó de ser acumulativo")
    require(sha(payload["app.py"]) == "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e", "app.py funcional fue alterado")
    require(sha(payload["app_base_4428.py"]) == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba", "base estable fue alterada")
    text = payload["ABRIR_RECEPCION.py"].decode("utf-8-sig")
    compile(text, "ABRIR_RECEPCION.py", "exec")
    markers = ["_rp_diag_report", "_rp_diag_flush_outbox", "rp_diagnostics_incidents", "_rp_v4437_required_files", "_choose_app_port", 'env["RP_PORT"] = str(APP_PORT)']
    require(all(x in text for x in markers), "Faltan contratos de diagnóstico/puerto/dependencia")
    forbidden = ["AUTOACTUALIZAR", "_AUTOACTUALIZAR_31", "_ABRIR_RECEPCION_451"]
    require(not any(("import " + x) in text for x in forbidden), "Regresó dependencia de launcher viejo")
    print("V4438_STATIC_CONTRACT_OK")
    update_from_4437(candidate, payload)
    diagnostics_privacy_and_queue(candidate, payload)
    print("VALIDATE_V4438_OK")


if __name__ == "__main__":
    main()
