from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_41_diag_reader"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE_REF = "4a0a5a20b7936fe625edacfebf483c6be0eba7ef"
SOURCE_PREFIX = "updates/v4_4_40_diag_transport_resilient"
VERSION = "4.4.41"
APP_VERSION = "4.4.36"
SOURCE_LAUNCHER_SHA = "abb10be2f7b4ca0c25def6f9c1b1da795d3a68ea65d1672340498d24c8d7abfc"
EXPECTED = {
    "app_base_4428.py": "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
    "app.py": "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e",
    "static/app.js": "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
    "static/index.html": "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


def split_four(text: str) -> list[bytes]:
    lines = text.splitlines(keepends=True)
    target = max(1, len(text) // 4)
    chunks, buf, n = [], [], 0
    for line in lines:
        if len(chunks) < 3 and buf and n + len(line) > target:
            chunks.append("".join(buf).encode("utf-8")); buf=[]; n=0
        buf.append(line); n += len(line)
    chunks.append("".join(buf).encode("utf-8"))
    while len(chunks) < 4:
        chunks.append(b"")
    require(len(chunks) == 4 and b"".join(chunks).decode("utf-8") == text, "Partición launcher inválida")
    return chunks


def build() -> None:
    old_launcher = b"".join(git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5))
    require(sha(old_launcher) == SOURCE_LAUNCHER_SHA, "Launcher 4.4.40 fuente no coincide")
    text = old_launcher.decode("utf-8-sig")

    old_ver = 'LAUNCHER_VERSION = "4.4.40-dynamic-port-dependency-diagnostics-resilient-1"'
    new_ver = 'LAUNCHER_VERSION = "4.4.41-dynamic-port-dependency-diagnostics-private-reader-1"'
    require(text.count(old_ver) == 1, "Versión launcher fuente cambió")
    text = text.replace(old_ver, new_ver, 1)

    old_diag = '_RP_DIAGNOSTICS_VERSION = "4.4.40-private-neon-resilient-1"'
    new_diag = '_RP_DIAGNOSTICS_VERSION = "4.4.41-private-neon-capability-1"'
    require(text.count(old_diag) == 1, "Versión diagnóstico fuente cambió")
    text = text.replace(old_diag, new_diag, 1)

    old_suffix = 'suffix = hashlib.sha256(os.urandom(24)).hexdigest()[:6].upper()'
    new_suffix = 'suffix = hashlib.sha256(os.urandom(32)).hexdigest()[:32].upper()'
    require(text.count(old_suffix) == 1, "Generador de INC fuente cambió")
    text = text.replace(old_suffix, new_suffix, 1)

    compile(text, "ABRIR_RECEPCION.py", "exec")
    require(new_suffix in text, "No quedó ID de 128 bits")
    require("_rp_diag_upload_via_venv" in text and "--diag-upload-file" in text, "Se perdió transporte resiliente")
    require("_rp_v4437_required_files" in text and "_choose_app_port" in text, "Se perdió blindaje previo")

    parts = split_four(text)
    for i, data in enumerate(parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    fixed = {}
    for rel, expected in EXPECTED.items():
        data = git_bytes(rel)
        require(sha(data) == expected, f"Bytes funcionales cambiaron: {rel}")
        target = OUT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        fixed[rel] = data

    paths = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    inner = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "launcher_version": "4.4.41-dynamic-port-dependency-diagnostics-private-reader-1",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "copy": paths,
    }
    inner_bytes = dump(inner)
    (OUT / "update_manifest.json").write_bytes(inner_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_41_diag_reader/"
    launcher = b"".join(parts)
    files = [
        {"path":"ABRIR_RECEPCION.py","parts":[raw+f"ABRIR_RECEPCION.part{i}" for i in range(1,5)],"sha256":sha(launcher),"encoding":"utf-8"},
        {"path":"app_base_4428.py","url":raw+"app_base_4428.py","sha256":sha(fixed["app_base_4428.py"]),"encoding":"utf-8"},
        {"path":"app.py","url":raw+"app.py","sha256":sha(fixed["app.py"]),"encoding":"utf-8"},
        {"path":"static/app.js","url":raw+"static/app.js","sha256":sha(fixed["static/app.js"]),"encoding":"utf-8"},
        {"path":"static/index.html","url":raw+"static/index.html","sha256":sha(fixed["static/index.html"]),"encoding":"utf-8"},
        {"path":"update_manifest.json","url":raw+"update_manifest.json","sha256":sha(inner_bytes),"encoding":"utf-8"},
    ]
    candidate = {
        "product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
        "mandatory":True,"channel":"files-v3",
        "message":"v4.4.41: endurece la lectura privada de diagnósticos. Los nuevos INC usan 128 bits aleatorios para funcionar como código de acceso no enumerable al puente privado. Conserva íntegramente el transporte resiliente 4.4.40, puertos dinámicos, guardia de dependencias y la app funcional 4.4.36. No modifica .env, data, pacientes, citas, facturas ni bases locales.",
        "files": files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4441_OK")
    print("LAUNCHER_SHA", sha(launcher))


if __name__ == "__main__":
    build()
