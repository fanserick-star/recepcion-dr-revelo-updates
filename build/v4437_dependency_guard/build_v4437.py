from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_37_dependency_guard"
OUT.mkdir(parents=True, exist_ok=True)

LAUNCHER_DIR = ROOT / "updates" / "v4_4_32_launcher_port_patch"
APP_4436 = ROOT / "updates" / "v4_4_36_default_cash" / "app.py"
BASE_4428 = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "app.py"
STATIC_APP = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "static" / "app.js"
STATIC_INDEX = ROOT / "updates" / "v4_4_28_overlay_hotfix" / "static" / "index.html"

VERSION = "4.4.37"
APP_VERSION = "4.4.36"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


GUARD = r'''

# ---------------------------------------------------------------------------
# v4.4.37 — guardia permanente de dependencias del runtime
# ---------------------------------------------------------------------------
# Parche mínimo sobre el launcher dinámico 4.4.32. No cambia la selección de
# puertos, RP_PORT, mutex, WebView/Edge ni el flujo de arranque. Solo endurece
# la coherencia de archivos y el preflight de actualizaciones.
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
    # Conserva TODAS las comprobaciones del launcher dinámico actual.
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
        # Si la actualización trae app.py, sus módulos locales app_* deben venir
        # EN EL MISMO manifiesto. No se permite depender por accidente de un
        # archivo que casualmente exista en una PC y falte en otra.
        if staged_app.is_file():
            imports = _rp_v4437_app_local_imports(staged_app)
            missing = sorted(rel for rel in imports if rel not in paths)
            if missing:
                raise RuntimeError(
                    "Actualización incompleta: app.py requiere archivo(s) no incluidos "
                    "en el manifiesto: " + ", ".join(missing)
                )
        # Si el manifiesto nuevo declara dependencias obligatorias, también deben
        # formar parte de la transacción atómica que se está instalando.
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
    for p in (APP_4436, BASE_4428, STATIC_APP, STATIC_INDEX):
        require(p.is_file(), f"Falta fuente requerida: {p}")

    app_text = APP_4436.read_text(encoding="utf-8")
    require('APP_VERSION = "4.4.36"' in app_text, "app.py fuente no es 4.4.36")
    tree = ast.parse(app_text)
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    require("app_base_4428" in imports, "La fuente ya no requiere app_base_4428; revisar arquitectura")

    parts = [(LAUNCHER_DIR / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    p4 = parts[3].decode("utf-8")
    anchor = '\nif __name__ == "__main__":\n'
    require(p4.count(anchor) == 1, "Cambió el ancla final del launcher 4.4.32")
    require("v4.4.37 — guardia permanente" not in p4, "Guardia duplicada")
    patched_p4 = p4.replace(anchor, GUARD + anchor, 1).encode("utf-8")
    (OUT / "ABRIR_RECEPCION.part4").write_bytes(patched_p4)

    launcher_bytes = b"".join(parts[:3] + [patched_p4])
    launcher_text = launcher_bytes.decode("utf-8-sig")
    compile(launcher_text, "ABRIR_RECEPCION.py", "exec")
    require('LAUNCHER_VERSION = "4.4.32-dynamic-port-patch-1"' in launcher_text,
            "Se perdió la base dinámica 4.4.32")
    require("_choose_app_port" in launcher_text and 'env["RP_PORT"] = str(APP_PORT)' in launcher_text,
            "Se perdió el manejo dinámico de puertos")
    require("_rp_v4437_required_files" in launcher_text, "No se insertó la guardia")

    inner = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "launcher_version": "4.4.32-dynamic-port-patch-1+dependency-guard-v4437",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "copy": [
            "ABRIR_RECEPCION.py",
            "app_base_4428.py",
            "app.py",
            "static/app.js",
            "static/index.html",
            "update_manifest.json",
        ],
    }
    inner_bytes = dump(inner)
    (OUT / "update_manifest.json").write_bytes(inner_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/"
    files = [
        {
            "path": "ABRIR_RECEPCION.py",
            "parts": [
                raw + "updates/v4_4_32_launcher_port_patch/ABRIR_RECEPCION.part1",
                raw + "updates/v4_4_32_launcher_port_patch/ABRIR_RECEPCION.part2",
                raw + "updates/v4_4_32_launcher_port_patch/ABRIR_RECEPCION.part3",
                raw + "updates/v4_4_37_dependency_guard/ABRIR_RECEPCION.part4",
            ],
            "sha256": sha(launcher_bytes),
            "encoding": "utf-8",
        },
        {
            "path": "app_base_4428.py",
            "url": raw + "updates/v4_4_28_overlay_hotfix/app.py",
            "sha256": sha(BASE_4428.read_bytes()),
            "encoding": "utf-8",
        },
        {
            "path": "app.py",
            "url": raw + "updates/v4_4_36_default_cash/app.py",
            "sha256": sha(APP_4436.read_bytes()),
            "encoding": "utf-8",
        },
        {
            "path": "static/app.js",
            "url": raw + "updates/v4_4_28_overlay_hotfix/static/app.js",
            "sha256": sha(STATIC_APP.read_bytes()),
            "encoding": "utf-8",
        },
        {
            "path": "static/index.html",
            "url": raw + "updates/v4_4_28_overlay_hotfix/static/index.html",
            "sha256": sha(STATIC_INDEX.read_bytes()),
            "encoding": "utf-8",
        },
        {
            "path": "update_manifest.json",
            "url": raw + "updates/v4_4_37_dependency_guard/update_manifest.json",
            "sha256": sha(inner_bytes),
            "encoding": "utf-8",
        },
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
            "Restaura app_base_4428.py en PCs que saltaron directamente desde versiones antiguas; "
            "el launcher dinámico 4.4.32 conserva puertos libres/RP_PORT y ahora rechaza antes de instalar "
            "un app.py que dependa de módulos app_* ausentes. Si una dependencia obligatoria desaparece, "
            "la instalación se marca incoherente y se repara incluso en la misma versión. No modifica .env, "
            "data, pacientes, citas, facturas ni bases de datos."
        ),
        "files": files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))

    expected_paths = [x["path"] for x in files]
    require(expected_paths == inner["copy"], f"Canal no es acumulativo: {expected_paths}")
    require(files[1]["sha256"] == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
            "Cambió inesperadamente la base estable 4.4.28")
    require(files[2]["sha256"] == "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e",
            "Cambió inesperadamente app.py 4.4.36")
    print("BUILD_V4437_OK")
    print("LAUNCHER_SHA", files[0]["sha256"])
    print("BASE_SHA", files[1]["sha256"])
    print("APP_SHA", files[2]["sha256"])


if __name__ == "__main__":
    build()
