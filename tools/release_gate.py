from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESC_PATH = ROOT / "release_candidate.json"
WORK = ROOT / ".release_gate"
STAGE = WORK / "stage"
INSTALL = WORK / "install"
CANDIDATE_LATEST = WORK / "candidate_latest.json"
SMOKE_OK = WORK / "smoke.ok"
REPO = os.getenv("GITHUB_REPOSITORY", "fanserick-star/recepcion-dr-revelo-updates")
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main/"


def load_desc() -> dict:
    data = json.loads(DESC_PATH.read_text(encoding="utf-8-sig"))
    if data.get("product") != "recepcion-pacientes":
        raise SystemExit("release_candidate.json: producto inválido")
    version = str(data.get("version") or "").strip()
    folder = str(data.get("folder") or "").strip().strip("/")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("release_candidate.json: versión inválida")
    if not folder or ".." in folder:
        raise SystemExit("release_candidate.json: folder inválido")
    return data


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main_guard_present(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if not isinstance(t, ast.Compare) or len(t.ops) != 1 or not isinstance(t.ops[0], ast.Eq):
            continue
        vals = [t.left, *t.comparators]
        has_name = any(isinstance(x, ast.Name) and x.id == "__name__" for x in vals)
        has_main = any(isinstance(x, ast.Constant) and x.value == "__main__" for x in vals)
        if has_name and has_main:
            return True
    return False


def compile_py(path: str, raw: bytes) -> None:
    source = raw.decode("utf-8-sig")
    compile(source, path, "exec")


def source_bytes(desc: dict, item: dict) -> bytes:
    folder = ROOT / desc["folder"]
    if item.get("generated"):
        p = folder / item["path"]
        return p.read_bytes()
    if item.get("source"):
        return (folder / item["source"]).read_bytes()
    parts = item.get("parts") or []
    if parts:
        return b"".join((folder / p).read_bytes() for p in parts)
    raise SystemExit(f"No hay fuente para {item.get('path')}")


def raw_spec(desc: dict, item: dict) -> dict:
    folder = desc["folder"].strip("/")
    out = {"path": item["path"], "encoding": "utf-8"}
    if item.get("parts"):
        out["parts"] = [RAW_BASE + folder + "/" + p for p in item["parts"]]
    else:
        src = item.get("source") or item["path"]
        out["url"] = RAW_BASE + folder + "/" + src
    return out


def build_update_manifest(desc: dict) -> dict:
    return {
        "product": desc["product"],
        "version": desc["version"],
        "app_version": desc.get("app_version") or desc["version"],
        "runtime_version": desc.get("runtime_version") or desc["version"],
        "launcher_version": desc.get("launcher_version") or "",
        "updater_version": "release-gate-v1",
        "required_dependencies": list(desc.get("required_dependencies") or []),
        "required_python_packages": list(desc.get("required_python_packages") or []),
        "copy": list(desc.get("copy") or []),
    }


def extract_embedded_js(paths: list[Path]) -> str:
    chunks = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if any(name == "JS" or name.endswith("_JS") for name in names):
                chunks.append(value.value)
    return "\n;\n".join(chunks)


def prepare() -> None:
    desc = load_desc()
    folder = ROOT / desc["folder"]
    if not folder.is_dir():
        raise SystemExit(f"No existe {folder}")

    # El manifest interno SIEMPRE lo genera el gate. Nunca se escribe el SHA a mano.
    inner = build_update_manifest(desc)
    manifest_path = folder / "update_manifest.json"
    manifest_path.write_text(json.dumps(inner, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if WORK.exists():
        shutil.rmtree(WORK)
    STAGE.mkdir(parents=True)

    declared_paths = {str(x.get("path") or "") for x in desc.get("files") or []}
    for dep in inner["required_dependencies"]:
        if dep not in declared_paths:
            raise SystemExit(f"Dependencia requerida no incluida en el paquete: {dep}")

    app_item = next((x for x in desc["files"] if x.get("path") == "app.py"), None)
    if not app_item:
        raise SystemExit("El candidato no contiene app.py")
    app_raw = source_bytes(desc, app_item)
    app_source = app_raw.decode("utf-8-sig")
    expected = re.escape(str(desc.get("app_version") or desc["version"]))
    if not re.search(rf'(?m)^\s*APP_VERSION\s*=\s*["\']{expected}["\']', app_source):
        raise SystemExit("app.py no declara la versión candidata")
    if not main_guard_present(app_source):
        raise SystemExit("app.py no tiene bloque if __name__ == '__main__'; no arrancaría al abrir Recepción")

    latest_files = []
    py_paths = []
    for item in desc.get("files") or []:
        rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
        if not rel or ".." in Path(rel).parts:
            raise SystemExit(f"Ruta inválida: {rel}")
        raw = source_bytes(desc, item)
        if rel.lower().endswith(".py"):
            compile_py(rel, raw)
        dest = STAGE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        spec = raw_spec(desc, item)
        spec["sha256"] = sha(raw)
        latest_files.append(spec)
        if rel.lower().endswith(".py"):
            py_paths.append(dest)

    # Comprobación interna de hashes: exactamente los bytes que descargaría el launcher.
    for spec in latest_files:
        raw = (STAGE / spec["path"]).read_bytes()
        if sha(raw) != spec["sha256"]:
            raise SystemExit(f"SHA interno inconsistente: {spec['path']}")

    latest = {
        "product": desc["product"],
        "version": desc["version"],
        "app_version": desc.get("app_version") or desc["version"],
        "runtime_version": desc.get("runtime_version") or desc["version"],
        "mandatory": bool(desc.get("mandatory", True)),
        "channel": "files-v3-gated",
        "message": str(desc.get("message") or "").strip(),
        "files": latest_files,
    }
    CANDIDATE_LATEST.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    js = extract_embedded_js(py_paths)
    (WORK / "embedded.js").write_text(js, encoding="utf-8")

    # Simula una instalación real partiendo de los recursos limpios del producto.
    base_zip = ROOT / "installer_clean" / "base" / "clean_base_resources.zip"
    if not base_zip.is_file():
        raise SystemExit("Falta installer_clean/base/clean_base_resources.zip para el smoke test")
    INSTALL.mkdir(parents=True)
    with zipfile.ZipFile(base_zip) as z:
        z.extractall(INSTALL)
    for spec in latest_files:
        dst = INSTALL / spec["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STAGE / spec["path"], dst)

    print("GATE_PREPARE_OK", desc["version"])
    for spec in latest_files:
        print(spec["path"], spec["sha256"])


def smoke() -> None:
    desc = load_desc()
    version = str(desc["version"])
    if not (INSTALL / "app.py").is_file():
        raise SystemExit("Ejecuta prepare antes de smoke")
    data_dir = WORK / "smoke_data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    env = os.environ.copy()
    env["RP_FORCE_OFFLINE"] = "1"
    env["RP_DATA_DIR"] = str(data_dir)
    env["DATABASE_URL"] = ""
    env["RP_PORT"] = "18159"

    code = (
        "import app; "
        f"assert app.APP_VERSION == {version!r}; "
        "assert getattr(app, 'PATCH_BOOT_OK', True), getattr(app, 'PATCH_BOOT_ERROR', ''); "
        "paths={getattr(r,'path',None) for r in app.app.routes}; "
        "assert '/api/billing/non-billable' in paths; "
        "print('IMPORT_SMOKE_OK')"
    )
    subprocess.run([sys.executable, "-c", code], cwd=INSTALL, env=env, check=True, timeout=45)

    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=INSTALL, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.time() + 35
        last = None
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen("http://127.0.0.1:18159/api/version", timeout=1) as r:
                    payload = json.loads(r.read().decode("utf-8"))
                    if str(payload.get("version")) == version:
                        with urllib.request.urlopen("http://127.0.0.1:18159/", timeout=2) as home:
                            if int(getattr(home, "status", 200)) != 200:
                                raise RuntimeError("La pantalla principal no respondió 200")
                        SMOKE_OK.write_text(version + "\n", encoding="utf-8")
                        print("RUNTIME_SMOKE_OK", version)
                        return
            except Exception as exc:
                last = exc
            time.sleep(0.25)
        output = ""
        try:
            output = proc.stdout.read() if proc.stdout else ""
        except Exception:
            pass
        raise SystemExit(f"El backend candidato no arrancó: {last}\n{output[-4000:]}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


def promote() -> None:
    desc = load_desc()
    version = str(desc["version"])
    if not SMOKE_OK.is_file() or SMOKE_OK.read_text(encoding="utf-8").strip() != version:
        raise SystemExit("No existe smoke test válido; promoción bloqueada")
    latest = CANDIDATE_LATEST.read_bytes()
    (ROOT / "latest-v3.json").write_bytes(latest)
    (ROOT / "latest.json").write_bytes(latest)
    print("PROMOTION_READY", version)


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if cmd == "prepare":
        prepare()
    elif cmd == "smoke":
        smoke()
    elif cmd == "promote":
        promote()
    else:
        raise SystemExit("Uso: release_gate.py prepare|smoke|promote")


if __name__ == "__main__":
    main()
