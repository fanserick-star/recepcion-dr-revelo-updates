from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_37_dependency_guard"
OUT.mkdir(parents=True, exist_ok=True)

LAUNCHER_DIR = ROOT / "updates" / "v4_4_32_launcher_port_patch"
APP_4436 = ROOT / "updates" / "v4_4_36_default_cash" / "app.py"
STABLE_REF = "6aeeea848159d9890824722518418fdaaaf3127d"
STABLE_PREFIX = "updates/v4_4_28_overlay_hotfix"
VERSION = "4.4.37"
APP_VERSION = "4.4.36"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def git_bytes(ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT)


GUARD = r'''

# ---------------------------------------------------------------------------
# v4.4.37 — guardia permanente de dependencias del runtime
# ---------------------------------------------------------------------------
# Parche mínimo sobre el launcher dinámico 4.4.32. No cambia selección de
# puertos, RP_PORT, mutex, WebView/Edge ni el flujo de arranque.
_RP_V4437_OLD_INSTALLATION_CONSISTENT = _installation_consistent
_RP_V4437_OLD_STAGE_UPDATE = _stage_update


def _rp_v4437_required_files(root: Path = ROOT) -> list[str]:
    try:
        manifest = _local_manifest(root)
    except Exception:
        manifest = {}
    values = manifest.get("required_dependencies") or []
    if not isinstance(values, list):
        return []
    out = []
    for value in values:
        rel = str(value or "").replace("\\", "/").lstrip("/")
        if rel and rel not in out:
            out.append(rel)
    return out


def _rp_v4437_app_local_imports(app_path: Path) -> set[str]:
    try:
        source = app_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(app_path))
    except Exception:
        return set()
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = str(alias.name or "").split(".", 1)[0]
                if name.startswith("app_"):
                    result.add(name + ".py")
        elif isinstance(node, ast.ImportFrom) and node.module:
            name = str(node.module).split(".", 1)[0]
            if name.startswith("app_"):
                result.add(name + ".py")
    return result


def _rp_v4437_dependency_file_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() == ".py":
        try:
            compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
        except Exception:
            return False
    return True


def _installation_consistent(root: Path = ROOT) -> bool:
    # Preserva primero TODAS las comprobaciones del launcher dinámico 4.4.32.
    if not _RP_V4437_OLD_INSTALLATION_CONSISTENT(root):
        return False
    required = set(_rp_v4437_required_files(root))
    required.update(_rp_v4437_app_local_imports(root / "app.py"))
    for rel in required:
        try:
            target = _safe_target(root, rel)
        except Exception:
            return False
        if not _rp_v4437_dependency_file_ok(target):
            _log(f"Dependencia obligatoria ausente o dañada: {rel}", root)
            return False
    return True


def _stage_update(
    remote: dict,
    root: Path = ROOT,
    *,
    attempts: int = 3,
    timeout: float = 10.0,
    allow_test_sources: bool = False,
):
    stage, staged = _RP_V4437_OLD_STAGE_UPDATE(
        remote,
        root,
        attempts=attempts,
        timeout=timeout,
        allow_test_sources=allow_test_sources,
    )
    try:
        paths = {str(x.get("rel") or "").replace("\\", "/") for x in staged}
        staged_app = stage / "app.py"
        # Regla permanente: cualquier módulo local app_* importado por app.py
        # debe venir EN EL MISMO manifiesto. Nunca más se depende de que un
        # archivo haya quedado por casualidad de una actualización anterior.
        if staged_app.is_file():
            imports = _rp_v4437_app_local_imports(staged_app)
            missing = sorted(rel for rel in imports if rel not in paths)
            if missing:
                raise RuntimeError(
                    "Actualización incompleta: app.py requiere archivo(s) no incluidos "
                    "en el manifiesto: " + ", ".join(missing)
                )
        inner = stage / "update_manifest.json"
        if inner.is_file():
            data = json.loads(inner.read_text(encoding="utf-8-sig"))
            req = data.get("required_dependencies") or []
            if not isinstance(req, list):
                raise RuntimeError("required_dependencies debe ser una lista")
            absent = []
            for value in req:
                rel = str(value or "").replace("\\", "/").lstrip("/")
                if rel and rel not in paths:
                    absent.append(rel)
            if absent:
                raise RuntimeError(
                    "Manifest de actualización incompleto; faltan dependencias obligatorias: "
                    + ", ".join(sorted(set(absent)))
                )
        return stage, staged
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

'''


def build() -> None:
    # Fijar bytes históricos exactos de la base que fue validada como 4.4.28.
    base_bytes = git_bytes(STABLE_REF, f"{STABLE_PREFIX}/app.py")
    static_app_bytes = git_bytes(STABLE_REF, f"{STABLE_PREFIX}/static/app.js")
    static_index_bytes = git_bytes(STABLE_REF, f"{STABLE_PREFIX}/static/index.html")
    require(sha(base_bytes) == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
            "El commit histórico no contiene la base 4.4.28 esperada")
    require(sha(static_app_bytes) == "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
            "El JS histórico 4.4.28 no coincide")
    require(sha(static_index_bytes) == "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
            "El index histórico 4.4.28 no coincide")

    app_bytes = APP_4436.read_bytes()
    require(sha(app_bytes) == "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e",
            "app.py 4.4.36 cambió inesperadamente")
    app_text = app_bytes.decode("utf-8")
    require('APP_VERSION = "4.4.36"' in app_text, "app.py no es 4.4.36")
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(ast.parse(app_text))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    require("app_base_4428" in imports, "La app ya no requiere la base; revisar diseño")

    # El release se apropia de TODOS sus bytes: no referencia archivos mutables
    # de carpetas de versiones previas.
    (OUT / "app_base_4428.py").write_bytes(base_bytes)
    (OUT / "app.py").write_bytes(app_bytes)
    (OUT / "static").mkdir(parents=True, exist_ok=True)
    (OUT / "static" / "app.js").write_bytes(static_app_bytes)
    (OUT / "static" / "index.html").write_bytes(static_index_bytes)

    old_parts = [(LAUNCHER_DIR / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    p4 = old_parts[3].decode("utf-8")
    anchor = '\nif __name__ == "__main__":\n'
    require(p4.count(anchor) == 1, "Cambió ancla final del launcher 4.4.32")
    patched4 = p4.replace(anchor, GUARD + anchor, 1).encode("utf-8")
    for i, data in enumerate(old_parts[:3], 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)
    (OUT / "ABRIR_RECEPCION.part4").write_bytes(patched4)
    launcher_bytes = b"".join(old_parts[:3] + [patched4])
    launcher_text = launcher_bytes.decode("utf-8-sig")
    compile(launcher_text, "ABRIR_RECEPCION.py", "exec")
    require('LAUNCHER_VERSION = "4.4.32-dynamic-port-patch-1"' in launcher_text,
            "No se conservó el launcher dinámico actual")
    require("_choose_app_port" in launcher_text and 'env["RP_PORT"] = str(APP_PORT)' in launcher_text,
            "Se perdió lógica de puertos dinámicos")
    require("_rp_v4437_required_files" in launcher_text, "No se insertó guardia")

    required_paths = [
        "ABRIR_RECEPCION.py",
        "app_base_4428.py",
        "app.py",
        "static/app.js",
        "static/index.html",
        "update_manifest.json",
    ]
    inner = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "launcher_version": "4.4.32-dynamic-port-patch-1+dependency-guard-v4437",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "copy": required_paths,
    }
    inner_bytes = dump(inner)
    (OUT / "update_manifest.json").write_bytes(inner_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_37_dependency_guard/"
    files = [
        {
            "path": "ABRIR_RECEPCION.py",
            "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)],
            "sha256": sha(launcher_bytes), "encoding": "utf-8",
        },
        {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(base_bytes), "encoding": "utf-8"},
        {"path": "app.py", "url": raw + "app.py", "sha256": sha(app_bytes), "encoding": "utf-8"},
        {"path": "static/app.js", "url": raw + "static/app.js", "sha256": sha(static_app_bytes), "encoding": "utf-8"},
        {"path": "static/index.html", "url": raw + "static/index.html", "sha256": sha(static_index_bytes), "encoding": "utf-8"},
        {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(inner_bytes), "encoding": "utf-8"},
    ]
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.37: reparación acumulativa y guardia permanente de dependencias. "
            "Recupera PCs que saltaron directamente desde versiones antiguas y quedaron sin app_base_4428.py. "
            "Cada release ahora fija sus propios bytes verificados; el launcher dinámico 4.4.32 conserva puertos/RP_PORT "
            "y rechaza antes de instalar cualquier app.py que requiera un módulo app_* no incluido. Una dependencia "
            "obligatoria ausente o corrupta marca la instalación incoherente y se autorepara incluso en la misma versión. "
            "No modifica .env, data, pacientes, citas, facturas ni bases de datos."
        ),
        "files": files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    require([x["path"] for x in files] == required_paths, "El release no es acumulativo")
    print("BUILD_V4437_V2_OK")
    print("LAUNCHER_SHA", sha(launcher_bytes))
    print("BASE_SHA", sha(base_bytes))
    print("APP_SHA", sha(app_bytes))


if __name__ == "__main__":
    build()
