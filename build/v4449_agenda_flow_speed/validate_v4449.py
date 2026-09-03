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
OUT = ROOT / "updates" / "v4_4_49_agenda_flow_speed"
LEGACY = ROOT / "updates" / "v4_4_43_daily_emitted_whatsapp_schedule"
VERSION = "4.4.49"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> None:
    subprocess.run([sys.executable, str(HERE / "build_v4449.py")], cwd=ROOT, check=True)


def launcher_bytes(folder: pathlib.Path) -> bytes:
    return b"".join((folder / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


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
        'APP_VERSION = "4.4.49"',
        '_v4449_cloud_sync_background',
        '_v4445_sync_cloud_agenda_for_dates = _v4449_cloud_sync_background',
        'row["planned"] = "Al guardar la cita"',
        'Actualizar datos y atender',
        'Guardar cambios y atender',
        "CONFIRMAFY_LEGACY",
        "PATIENT_APPOINTMENT",
        'window.__v4449AgendaFlowSpeed',
        'window.__v4446PhoneGuardTest',
    ):
        require(marker in app, f"Falta contrato v4.4.49: {marker}")

    # Contratos acumulativos que no pueden desaparecer.
    for marker in (
        '/api/agenda/appointments/guarded',
        'window.__v4445StagedIdentityFix',
        '/api/identity/phone-owner',
        'window.__v4446PhoneDuplicateGuard',
        'stopIfDuplicate',
    ):
        require(marker in app, f"Se perdió arreglo acumulativo: {marker}")

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    expected = ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"]
    require(manifest.get("version") == VERSION, "Manifest incorrecto")
    require(manifest.get("required_dependencies") == ["app_base_4428.py"], "Falta dependencia obligatoria")
    require(manifest.get("copy") == expected, "Manifest copy incompleto")
    require([x.get("path") for x in candidate.get("files", [])] == expected, "Candidate incompleto")
    require(
        sha((OUT / "app_base_4428.py").read_bytes()) == sha((ROOT / "updates" / "v4_4_48_dependency_recovery" / "app_base_4428.py").read_bytes()),
        "La base estable cambió",
    )

    # Sintaxis del JS nuevo: extraer solo la capa v4.4.49 y pasar node --check.
    start = app.index('V4449_AGENDA_FLOW_JS = r"""') + len('V4449_AGENDA_FLOW_JS = r"""')
    end = app.index('\n"""\n\n    V4449_AGENDA_FLOW_CSS', start)
    js = app[start:end]
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "v4449.js"
        path.write_text(js, encoding="utf-8", newline="")
        proc = subprocess.run(["node", "--check", str(path)], text=True, capture_output=True)
        require(proc.returncode == 0, f"JS v4.4.49 inválido: {proc.stderr}")

    print("V4449_CONTRACT_OK")


class Handler(BaseHTTPRequestHandler):
    files: dict[str, tuple[bytes, str]] = {}

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        item = self.files.get(path)
        if item is None:
            self.send_response(404); self.end_headers(); return
        body, ctype = item
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *_):
        pass


def start_server():
    class H(Handler):
        pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def localize_candidate(candidate: dict, folder: pathlib.Path, base: str) -> dict[str, tuple[bytes, str]]:
    remote = copy.deepcopy(candidate)
    files: dict[str, tuple[bytes, str]] = {}
    for idx, item in enumerate(remote.get("files") or []):
        target = str(item.get("path") or "")
        if target == "ABRIR_RECEPCION.py":
            parts=[]
            for part_no in range(1,5):
                route=f"/item{idx}_part{part_no}"
                files[route]=((folder/f"ABRIR_RECEPCION.part{part_no}").read_bytes(),"text/plain")
                parts.append(base+route)
            item.pop("url",None); item["parts"]=parts
        else:
            route=f"/item{idx}"
            files[route]=((folder/target).read_bytes(),"application/octet-stream")
            item.pop("parts",None); item["url"]=base+route
    files["/manifest"] = ((json.dumps(remote, ensure_ascii=False)+"\n").encode("utf-8"), "application/json")
    return files


def seed_legacy_install(root: pathlib.Path) -> dict[pathlib.Path, bytes]:
    root.mkdir(parents=True, exist_ok=True); (root/"data").mkdir(exist_ok=True)
    for name in ("app.py","app_base_4428.py","update_manifest.json"):
        shutil.copyfile(LEGACY/name, root/name)
    (root/"ABRIR_RECEPCION.py").write_bytes(launcher_bytes(LEGACY))
    sentinels={
        root/".env":b"PRIVATE_SENTINEL=KEEP_ME\n",
        root/"BASE DE DATOS 2026.xlsx":b"EXCEL_SENTINEL_BYTES",
        root/"data"/"offline_cache.db":b"SQLITE_OFFLINE_SENTINEL",
        root/"data"/"recepcion.db":b"SQLITE_RECEPCION_SENTINEL",
    }
    for path,data in sentinels.items(): path.write_bytes(data)
    return sentinels


def legacy_module(temp: pathlib.Path):
    path=temp/"legacy_443_launcher.py"; path.write_bytes(launcher_bytes(LEGACY))
    return load_module(path,"legacy_443_updater_v4449")


def accepted_by_real_443() -> None:
    candidate=json.loads((OUT/"candidate_latest.json").read_text(encoding="utf-8"))
    server,base=start_server()
    try:
        server.RequestHandlerClass.files=localize_candidate(candidate,OUT,base)
        with tempfile.TemporaryDirectory() as td:
            temp=pathlib.Path(td); install=temp/"install"; sentinels=seed_legacy_install(install); legacy=legacy_module(temp)
            result=legacy.check_and_apply_update(install,base+"/manifest",attempts=1,timeout=8,allow_test_sources=True)
            require(result.get("ok") and result.get("updated"), f"Updater 4.4.43 no instaló 4.4.49: {result}")
            require(legacy._local_package_version(install)==VERSION,"Manifest final incorrecto")
            require(legacy._installed_app_version(install)==VERSION,"app.py final incorrecta")
            require(legacy._installation_consistent(install),"Instalación incoherente")
            for path,data in sentinels.items(): require(path.read_bytes()==data,f"Se alteró archivo protegido: {path.name}")
    finally:
        server.shutdown();server.server_close()
    print("V4449_ACCEPTED_BY_LEGACY_443")


def launcher_selftests() -> None:
    with tempfile.TemporaryDirectory() as td:
        path=pathlib.Path(td)/"ABRIR_RECEPCION.py";path.write_bytes(launcher_bytes(OUT))
        proc=subprocess.run([sys.executable,str(path),"--self-test-core"],cwd=td,text=True,capture_output=True,timeout=100)
        require(proc.returncode==0,f"Self-test launcher falló: {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        require("SELFTEST OK:" in proc.stdout,"Launcher no reportó SELFTEST OK")
    print("V4449_LAUNCHER_SELFTESTS_OK")


def main() -> None:
    build();contracts();accepted_by_real_443();launcher_selftests();print("VALIDATE_V4449_OK")


if __name__ == "__main__":
    main()
