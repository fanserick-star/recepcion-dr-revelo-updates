from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# Contrato del runtime instalado en la PC del consultorio.
# Si una futura versión necesita un módulo nuevo, primero debe actualizarse y
# probarse el runtime/instalador. El app.py NO puede introducirlo silenciosamente.
ALLOWED_THIRD_PARTY = {
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "dotenv",
    "pg8000",
    "uvicorn",
    "anyio",
}
# Imports usados únicamente en ramas opcionales de Windows/WebView. No son
# requisito para que el backend arranque; el smoke test real valida que sigan
# siendo realmente opcionales.
OPTIONAL_IMPORTS = {
    "clr",
    "System",
}
LOCAL_MODULES = {
    "azur_client",
    "whatsapp_client",
    "remote_agenda",
}
BANNED_IMPORTS = {
    "psycopg",
    "psycopg2",
}
PROTECTED_TOP = {"data", ".venv"}
PROTECTED_FILES = {".env", "BASE DE DATOS 2026.xlsx"}


def imported_toplevel(source: str) -> set[str]:
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".", 1)[0])
    return out


def validate_app(path: Path, expected_version: str) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compile(source, str(path), "exec")
    imports = imported_toplevel(source)

    banned = sorted(imports & BANNED_IMPORTS)
    if banned:
        raise SystemExit("Dependencia prohibida/no instalada: " + ", ".join(banned))

    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    unknown = sorted(imports - stdlib - ALLOWED_THIRD_PARTY - OPTIONAL_IMPORTS - LOCAL_MODULES)
    if unknown:
        raise SystemExit(
            "app.py introdujo dependencias fuera del contrato del runtime: "
            + ", ".join(unknown)
        )

    m = re.search(r'(?m)^\s*APP_VERSION\s*=\s*["\']([^"\']+)["\']', source)
    found = m.group(1).strip() if m else ""
    if found != expected_version:
        raise SystemExit(f"APP_VERSION={found!r}; se esperaba {expected_version!r}")

    # La conexión de Neon debe usar el driver puro que ya forma parte del runtime.
    if "pg8000" not in imports:
        raise SystemExit("app.py no importa pg8000; se detiene para evitar otra incompatibilidad de Neon")


def validate_manifest(path: Path, expected_version: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if str(data.get("version") or "").strip() != expected_version:
        raise SystemExit("El manifiesto interno no coincide con la versión esperada")
    app_version = str(data.get("app_version") or data.get("runtime_version") or "").strip()
    if app_version and app_version != expected_version:
        raise SystemExit("app_version/runtime_version no coincide con package version")

    for rel in data.get("copy") or []:
        norm = str(rel).replace("\\", "/").lstrip("/")
        parts = [p for p in norm.split("/") if p]
        if not parts:
            raise SystemExit("Ruta vacía en copy")
        if parts[0].lower() in {x.lower() for x in PROTECTED_TOP}:
            raise SystemExit(f"La actualización intenta tocar ruta protegida: {rel}")
        if len(parts) == 1 and parts[0].lower() in {x.lower() for x in PROTECTED_FILES}:
            raise SystemExit(f"La actualización intenta tocar archivo protegido: {rel}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--version", required=True)
    args = p.parse_args()

    validate_app(Path(args.app), args.version)
    validate_manifest(Path(args.manifest), args.version)
    print("RELEASE_GUARD_OK", args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
