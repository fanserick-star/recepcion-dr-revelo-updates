from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_41_diag_reader"
WORKER = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_15_DIAGNOSTICS_STANDALONE.js"


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec and spec.loader, f"No carga {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_all():
    subprocess.run([sys.executable, str(ROOT / "build" / "v4441_diag_reader" / "build_v4441.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "build" / "v4441_diag_reader" / "build_worker_diag_reader.py")], cwd=ROOT, check=True)


def launcher_bytes() -> bytes:
    return b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def static_release_contract():
    c = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(c["version"] == "4.4.41" and c["app_version"] == "4.4.36", "Versiones incorrectas")
    expected = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    require([x["path"] for x in c["files"]] == expected, "Release dejó de ser acumulativo")
    require(sha(OUT / "app.py") == "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e", "app.py cambió")
    require(sha(OUT / "app_base_4428.py") == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba", "base cambió")
    text = launcher_bytes().decode("utf-8-sig")
    compile(text, "ABRIR_RECEPCION.py", "exec")
    require('4.4.41-dynamic-port-dependency-diagnostics-private-reader-1' in text, "Falta launcher 4.4.41")
    require('hexdigest()[:32].upper()' in text and 'os.urandom(32)' in text, "INC no tiene 128 bits")
    require('hexdigest()[:6].upper()' not in text, "Persistió sufijo corto")
    require('_rp_diag_upload_via_venv' in text and '--diag-upload-file' in text, "Se perdió transporte 4.4.40")
    require('_rp_v4437_required_files' in text and '_choose_app_port' in text, "Se perdió blindaje/puerto")
    print("V4441_STATIC_RELEASE_OK")


def incident_id_contract():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "install"
        root.mkdir()
        launcher = root / "ABRIR_RECEPCION.py"
        launcher.write_bytes(launcher_bytes())
        (root / "app.py").write_bytes((OUT / "app.py").read_bytes())
        (root / "app_base_4428.py").write_bytes((OUT / "app_base_4428.py").read_bytes())
        (root / "update_manifest.json").write_bytes((OUT / "update_manifest.json").read_bytes())
        (root / "data").mkdir()
        (root / "data" / "launcher_errors.log").write_text("synthetic launcher\n", encoding="utf-8")
        (root / "data" / "backend_startup.log").write_text("synthetic backend\n", encoding="utf-8")
        m = load(launcher, "v4441_incident")
        p = m._rp_diag_build_payload("launcher_fatal", RuntimeError("synthetic"))
        iid = str(p.get("incident_id") or "")
        require(re.fullmatch(r"INC-\d{8}-\d{6}-[A-F0-9]{32}", iid) is not None, f"INC inválido: {iid}")
        require(len(iid) == 52, f"Longitud INC inesperada: {len(iid)}")
        print("V4441_INCIDENT_128BIT_OK", iid)


def launcher_selftests():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "install"
        root.mkdir()
        launcher = root / "ABRIR_RECEPCION.py"
        launcher.write_bytes(launcher_bytes())
        proc = subprocess.run([sys.executable, str(launcher), "--self-test-core"], cwd=root, capture_output=True, text=True, timeout=160)
        print(proc.stdout, end="")
        if proc.returncode:
            print(proc.stderr, end="")
        require(proc.returncode == 0 and "SELFTEST OK" in proc.stdout, "Selftests históricos del launcher fallaron")
        print("V4441_LAUNCHER_SELFTEST_OK")


def worker_contract():
    text = WORKER.read_text(encoding="utf-8")
    require('worker_version: "2.6.15"' in text, "Worker no marca 2.6.15")
    require('diagnostics_read: "capability_v1"' in text, "Health no declara puente")
    require('u.pathname.startsWith("/diagnostics/")' in text, "Falta ruta diagnóstica")
    require('/diagnostics/latest' not in text, "No se permite endpoint latest")
    require('^INC-\\d{8}-\\d{6}-[A-F0-9]{32}$' in text, "Worker no exige INC largo")
    require('2026-09-03T00:00:00Z' in text, "Falta caducidad de compatibilidad legacy")
    require("public.rp_diagnostics_incidents" in text, "Falta fuente Neon")
    bridge = text[text.index('// v2.6.15 — puente privado de diagnóstico'):text.index('var whatsapp_worker_v2_6_responses_default = {')]
    for forbidden in ("machine_hash", "metadata_json", "signature"):
        require(forbidden not in bridge, f"Puente expone campo innecesario: {forbidden}")
    require('x-robots-tag' in bridge and 'noindex' in bridge and 'cache-control' in bridge, "Faltan cabeceras anti-cache/indexación")
    require("WHERE incident_id=$1" in bridge and "LIMIT 1" in bridge, "Lectura no está acotada a un INC exacto")
    require("30 days" in bridge, "Falta ventana de retención de lectura")

    with tempfile.TemporaryDirectory() as td:
        mjs = pathlib.Path(td) / "worker.mjs"
        shutil.copy2(WORKER, mjs)
        proc = subprocess.run(["node", "--check", str(mjs)], capture_output=True, text=True, timeout=60)
        if proc.returncode:
            print(proc.stdout, proc.stderr)
        require(proc.returncode == 0, "Worker generado no compila en Node")
    print("WORKER_DIAGNOSTIC_CAPABILITY_CONTRACT_OK")


def main():
    build_all()
    static_release_contract()
    incident_id_contract()
    launcher_selftests()
    worker_contract()
    print("VALIDATE_V4441_OK")


if __name__ == "__main__":
    main()
