from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "updates" / "v4_6_0_stabilization"
SOURCE_MAP = CANDIDATE / "runtime_sources.json"
RUNTIME_ZIP = CANDIDATE / "recepcion_legacy_runtime.zip"
RUNTIME_MANIFEST = CANDIDATE / "runtime_manifest.json"

OUTSIDE_RUNTIME = {"historia_bridge.py", "historia_lan_transport.py"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(f"blob {len(data)}\0".encode("ascii"))
    h.update(data)
    return h.hexdigest()


def verify_source(path: Path, expected_blob: str) -> bytes:
    data = path.read_bytes()
    got = git_blob_sha(data)
    if got != expected_blob:
        raise RuntimeError(
            f"Fuente alterada: {path.relative_to(ROOT)}; blob {got}, esperado {expected_blob}"
        )
    return data


def compile_python(name: str, data: bytes) -> None:
    compile(data.decode("utf-8"), name, "exec")


def patch_base_dir(data: bytes) -> bytes:
    text = data.decode("utf-8")
    old = 'BASE_DIR = os.path.dirname(os.path.abspath(__file__))'
    new = (
        'BASE_DIR = (os.getenv("RP_APP_ROOT") or '
        'os.path.dirname(os.path.abspath(__file__))).strip()'
    )
    if text.count(old) != 1:
        raise RuntimeError("No se encontró una única asignación BASE_DIR en app_base_4428.py")
    return text.replace(old, new, 1).encode("utf-8")


def build() -> dict:
    cfg = json.loads(SOURCE_MAP.read_text(encoding="utf-8"))
    if cfg.get("candidate_version") != "4.6.0":
        raise RuntimeError("runtime_sources.json no corresponde a 4.6.0")

    runtime: dict[str, bytes] = {}
    outside: dict[str, bytes] = {}

    for name, meta in cfg["modules"].items():
        path = ROOT / meta["path"]
        data = verify_source(path, meta["blob_sha"])
        if name == "app_base_4428.py":
            data = patch_base_dir(data)
        compile_python(name, data)
        if name in OUTSIDE_RUNTIME:
            outside[name] = data
        else:
            runtime[name] = data

    for name, meta in cfg.get("extracted_modules", {}).items():
        archive = ROOT / meta["archive"]
        with zipfile.ZipFile(archive) as zf:
            data = zf.read(meta["member"])
        compile_python(name, data)
        runtime[name] = data

    for name, rel in cfg.get("generated_modules", {}).items():
        data = (ROOT / rel).read_bytes()
        compile_python(name, data)
        runtime[name] = data

    # Dos módulos necesitan una ruta física real porque mantienen outboxes/LAN.
    for name, data in outside.items():
        (CANDIDATE / name).write_bytes(data)

    # ZIP determinista: orden fijo y timestamp fijo para que el SHA sea reproducible.
    with zipfile.ZipFile(RUNTIME_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(runtime):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, runtime[name])

    members = {
        name: {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        for name, data in sorted(runtime.items())
    }
    runtime_manifest = {
        "schema": 1,
        "version": "4.6.0",
        "base": "4.5.44",
        "member_count": len(members),
        "members": members,
        "runtime_zip_sha256": sha256(RUNTIME_ZIP),
        "runtime_zip_size": RUNTIME_ZIP.stat().st_size,
    }
    RUNTIME_MANIFEST.write_text(
        json.dumps(runtime_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Frontend estable: congelamos la última base estática conocida; las mejoras
    # visuales posteriores siguen viniendo de la capa de runtime.
    for target, source in cfg.get("static_files", {}).items():
        dest = CANDIDATE / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, dest)

    required = [
        "app.py",
        "recepcion_legacy_runtime.zip",
        "historia_bridge.py",
        "historia_lan_transport.py",
        "static/app.js",
        "static/index.html",
        "recepcion-version.json",
        "update_manifest.json",
        "requirements.txt",
        "runtime_manifest.json",
    ]
    manifest = {
        "product": "recepcion-pacientes",
        "version": "4.6.0",
        "app_version": "4.6.0",
        "runtime_version": "4.6.0",
        "mandatory": True,
        "version_source": "recepcion-version.json",
        "launcher_minimum": "1.0.13",
        "updater_version": "launcher-v1-atomic-runtime",
        "required_dependencies": required,
        "required_python_packages": [
            {"import": "pg8000", "pip": "pg8000==1.31.2"},
        ],
        "copy": required,
        "notes": {
            "candidate_only": True,
            "base_stable_version": "4.5.44",
            "protected_data": True,
            "protected_env": True,
            "preserves_data_env_excel": True,
            "automatic_updates_only": True,
            "transactional_updater": True,
            "sha256_required": True,
            "isolated_preflight": True,
            "rollback": True,
            "atomic_legacy_runtime_zip": True,
            "scattered_patch_files_required": False,
            "duplicate_routes_canonicalized": True,
            "legacy_health_handlers_consolidated": True,
            "legacy_cloudflare_tunnel_removed": True,
            "legacy_zip_updater_retired": True,
            "experimental_dataphone_api_default_off": True,
            "bendo_manual_flow_preserved": True,
            "whatsapp_cloud_mode_preserved": True,
            "patient_duplicate_guard_normalized": True,
            "read_only_data_audit": True,
            "database_schema_changes": False,
            "patient_data_destructive_changes": False,
            "historia_changes": False,
            "facturacion_logic_rewritten": False,
            "print_logic_rewritten": False,
            "purpose": (
                "Estabilización estructural: runtime histórico atómico, rutas únicas, "
                "superficies obsoletas retiradas y diagnóstico/auditoría unificados."
            ),
        },
        "channel": "launcher-v1-candidate",
    }
    (CANDIDATE / "update_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validación de sintaxis del entrypoint, sin importarlo todavía.
    compile_python("app.py", (CANDIDATE / "app.py").read_bytes())

    return {
        "runtime_zip": str(RUNTIME_ZIP.relative_to(ROOT)),
        "runtime_sha256": runtime_manifest["runtime_zip_sha256"],
        "runtime_members": len(members),
        "required_files": required,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(build(), indent=2, ensure_ascii=False))
