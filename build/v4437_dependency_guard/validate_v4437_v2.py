from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_37_dependency_guard"
OLD_LAUNCHER_DIR = ROOT / "updates" / "v4_4_32_launcher_port_patch"
APP_4436 = ROOT / "updates" / "v4_4_36_default_cash" / "app.py"
MANIFEST_4436 = ROOT / "updates" / "v4_4_36_default_cash" / "update_manifest.json"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def old_launcher_bytes() -> bytes:
    return b"".join((OLD_LAUNCHER_DIR / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def new_launcher_bytes() -> bytes:
    return b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


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
        self.end_headers(); self.wfile.write(data)
    def log_message(self, *_): pass


def server(files=None):
    Handler.files = files or {}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def candidate_payloads():
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    payloads = {
        "ABRIR_RECEPCION.py": new_launcher_bytes(),
        "app_base_4428.py": (OUT / "app_base_4428.py").read_bytes(),
        "app.py": (OUT / "app.py").read_bytes(),
        "static/app.js": (OUT / "static" / "app.js").read_bytes(),
        "static/index.html": (OUT / "static" / "index.html").read_bytes(),
        "update_manifest.json": (OUT / "update_manifest.json").read_bytes(),
    }
    for item in candidate["files"]:
        require(item["path"] in payloads, f"Falta payload local {item['path']}")
        require(sha(payloads[item["path"]]) == item["sha256"], f"SHA incorrecto {item['path']}")
    return candidate, payloads


def local_manifest(candidate, payloads, base):
    remote = {k: v for k, v in candidate.items() if k != "files"}; remote["files"] = []
    for idx, item in enumerate(candidate["files"]):
        rel = item["path"]
        remote["files"].append({"path": rel, "url": f"{base}/p/{idx}", "sha256": sha(payloads[rel]), "encoding": "utf-8"})
    return remote


def serve_remote(candidate, payloads):
    httpd, base = server()
    remote = local_manifest(candidate, payloads, base)
    files = {"/manifest": (json.dumps(remote).encode(), "application/json")}
    for idx, item in enumerate(remote["files"]): files[f"/p/{idx}"] = (payloads[item["path"]], "application/octet-stream")
    Handler.files = files
    return httpd, base


def make_broken_4436(root: pathlib.Path):
    root.mkdir(parents=True)
    (root / "app.py").write_bytes(APP_4436.read_bytes())
    (root / "ABRIR_RECEPCION.py").write_bytes(old_launcher_bytes())
    (root / "update_manifest.json").write_bytes(MANIFEST_4436.read_bytes())
    (root / "static").mkdir()
    (root / "static" / "app.js").write_text("OLD_STATIC_APP", encoding="utf-8")
    (root / "static" / "index.html").write_text("OLD_STATIC_INDEX", encoding="utf-8")
    (root / ".env").write_text("KEEP_ENV=YES\n", encoding="utf-8")
    (root / "data").mkdir(); (root / "data" / "keep.txt").write_text("KEEP_DATA", encoding="utf-8")
    (root / ".venv").mkdir(); (root / ".venv" / "keep.txt").write_text("KEEP_VENV", encoding="utf-8")
    require(not (root / "app_base_4428.py").exists(), "Fixture debe iniciar sin app_base_4428.py")


def test_direct_jump(candidate, payloads):
    td = tempfile.mkdtemp(prefix="rp-v4437-"); root = pathlib.Path(td) / "install"; make_broken_4436(root)
    httpd, base = serve_remote(candidate, payloads)
    try:
        old = load_module(root / "ABRIR_RECEPCION.py", "rp_old4432")
        result = old.check_and_apply_update(root, base + "/manifest", attempts=1, timeout=3, allow_test_sources=True)
        require(result.get("ok") and result.get("updated"), f"No reparó salto directo: {result}")
        require((root / "app_base_4428.py").is_file(), "No repuso app_base_4428.py")
        require(sha((root / "app_base_4428.py").read_bytes()) == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba", "Base repuesta no es la verificada")
        require((root / ".env").read_text(encoding="utf-8") == "KEEP_ENV=YES\n", ".env alterado")
        require((root / "data" / "keep.txt").read_text() == "KEEP_DATA", "data alterado")
        require((root / ".venv" / "keep.txt").read_text() == "KEEP_VENV", ".venv alterado")
        m=json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
        require(m["version"]=="4.4.37" and m["app_version"]=="4.4.36", "Manifest final incorrecto")
        compile((root/"app.py").read_text(encoding="utf-8-sig"),"app.py","exec")
        compile((root/"app_base_4428.py").read_text(encoding="utf-8-sig"),"app_base_4428.py","exec")
        print("BROKEN_CONSULTORIO_DIRECT_JUMP_REPAIRED_OK")
    finally: httpd.shutdown(); httpd.server_close()
    return root


def test_same_version_repair(root, candidate, payloads):
    launcher=load_module(root/"ABRIR_RECEPCION.py","rp_guard4437")
    require(launcher._installation_consistent(root),"Instalación recién reparada no es coherente")
    for mode in ("missing","corrupt"):
        if mode=="missing": (root/"app_base_4428.py").unlink()
        else: (root/"app_base_4428.py").write_text("def broken(:\n",encoding="utf-8")
        require(not launcher._installation_consistent(root),f"No detectó base {mode}")
        httpd,base=serve_remote(candidate,payloads)
        try:
            result=launcher.check_and_apply_update(root,base+"/manifest",attempts=1,timeout=3,allow_test_sources=True)
            require(result.get("ok") and result.get("updated"),f"No autoreparó {mode}: {result}")
            require(launcher._installation_consistent(root),f"Sigue incoherente tras reparar {mode}")
            require(sha((root/"app_base_4428.py").read_bytes())=="e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba","SHA base tras autoreparar incorrecto")
            print("SAME_VERSION_REPAIR_OK",mode)
        finally: httpd.shutdown(); httpd.server_close()


def test_future_omission_rejected(root):
    launcher=load_module(root/"ABRIR_RECEPCION.py","rp_reject4437")
    old_app=(root/"app.py").read_bytes(); old_manifest=(root/"update_manifest.json").read_bytes()
    app=b'APP_VERSION = "4.4.38"\nimport app_missing_future\n'
    inner=(json.dumps({"product":"recepcion-pacientes","version":"4.4.38","app_version":"4.4.38","runtime_version":"4.4.38","copy":["app.py","update_manifest.json"]},indent=2)+"\n").encode()
    httpd,base=server()
    try:
        remote={"product":"recepcion-pacientes","version":"4.4.38","app_version":"4.4.38","runtime_version":"4.4.38","files":[
            {"path":"app.py","url":base+"/app","sha256":sha(app),"encoding":"utf-8"},
            {"path":"update_manifest.json","url":base+"/inner","sha256":sha(inner),"encoding":"utf-8"}]}
        Handler.files={"/manifest":(json.dumps(remote).encode(),"application/json"),"/app":(app,"text/plain"),"/inner":(inner,"application/json")}
        result=launcher.check_and_apply_update(root,base+"/manifest",attempts=1,timeout=3,allow_test_sources=True)
        require(result.get("ok") and result.get("deferred"),f"Update incompleto no fue rechazado de forma segura: {result}")
        require((root/"app.py").read_bytes()==old_app,"Update incompleto tocó app.py")
        require((root/"update_manifest.json").read_bytes()==old_manifest,"Update incompleto tocó manifest")
        require(launcher._installation_consistent(root),"Rechazo dejó instalación incoherente")
        print("FUTURE_INCOMPLETE_DEPENDENCY_UPDATE_BLOCKED_BEFORE_SWAP_OK")
    finally: httpd.shutdown(); httpd.server_close()


def test_ports(root):
    launcher=load_module(root/"ABRIR_RECEPCION.py","rp_port4437")
    require(launcher.LAUNCHER_VERSION=="4.4.32-dynamic-port-patch-1","Launcher dinámico fue sustituido")
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); occupied=False
    try:
        try: s.bind(("127.0.0.1",8000)); s.listen(1); occupied=True
        except OSError: pass
        launcher._set_app_port(8000); chosen=launcher._choose_app_port(force_new=True)
        require(chosen!=8000 and 1024<=chosen<=65535,f"Selección dinámica falló: {chosen}")
        print("DYNAMIC_PORT_STILL_OK",chosen,"occupied8000",occupied)
    finally: s.close()


def test_selftests(root):
    r=subprocess.run([sys.executable,str(root/"ABRIR_RECEPCION.py"),"--self-test-core"],cwd=str(root),text=True,capture_output=True,timeout=120)
    print(r.stdout,end="")
    if r.returncode: print(r.stderr,end="")
    require(r.returncode==0 and "SELFTEST OK" in r.stdout,f"Self-tests launcher fallaron: {r.returncode}")
    print("LAUNCHER_CORE_SELFTESTS_OK")


def main():
    subprocess.run([sys.executable,str(ROOT/"build"/"v4437_dependency_guard"/"build_v4437_v2.py")],check=True)
    candidate,payloads=candidate_payloads()
    expected=["ABRIR_RECEPCION.py","app_base_4428.py","app.py","static/app.js","static/index.html","update_manifest.json"]
    require([x["path"] for x in candidate["files"]]==expected,"Manifest no acumulativo")
    require(candidate["app_version"]=="4.4.36","Repair cambió app_version")
    require(sha(payloads["app.py"])=="2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e","App no es 4.4.36 exacta")
    require(sha(payloads["app_base_4428.py"])=="e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba","Base no es estable exacta")
    print("SELF_CONTAINED_CUMULATIVE_RELEASE_OK")
    root=test_direct_jump(candidate,payloads)
    test_same_version_repair(root,candidate,payloads)
    test_future_omission_rejected(root)
    test_ports(root)
    test_selftests(root)
    print("VALIDATE_V4437_V2_OK")


if __name__=="__main__": main()
