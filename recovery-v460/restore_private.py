from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


ALLOWED_ROOT = {
    ".env",
    "HISTORICO_PACIENTES_2020_2025.csv",
    "BASE DE DATOS 2026.xlsx",
    "data",
    "RESPALDO_INFO.json",
}


def safe_member(name: str) -> Path:
    normalized = name.replace("\\", "/").lstrip("/")
    path = Path(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"Ruta insegura dentro del respaldo: {name}")
    if path.parts[0] not in ALLOWED_ROOT:
        raise RuntimeError(f"Archivo no permitido dentro del respaldo: {name}")
    return path


def normalize_env(path: Path) -> None:
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    found = False
    out = []
    for line in lines:
        if line.strip().upper().startswith("RP_DATA_DIR="):
            out.append("RP_DATA_DIR=data")
            found = True
        else:
            out.append(line)
    if not found:
        out.append("RP_DATA_DIR=data")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def backup_existing(root: Path) -> Path | None:
    candidates = [
        root / ".env",
        root / "HISTORICO_PACIENTES_2020_2025.csv",
        root / "BASE DE DATOS 2026.xlsx",
        root / "data",
    ]
    if not any(x.exists() for x in candidates):
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "_pre_restore_backup" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    for src in candidates:
        if not src.exists():
            continue
        dst = backup / src.name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    return backup


def restore(source: Path, root: Path) -> dict:
    source = source.resolve()
    root = root.resolve()
    if not source.is_file():
        raise RuntimeError(f"No existe el respaldo: {source}")
    root.mkdir(parents=True, exist_ok=True)

    previous = backup_existing(root)

    if source.name.lower() == ".env" or source.suffix.lower() == ".env":
        shutil.copy2(source, root / ".env")
        normalize_env(root / ".env")
        return {"ok": True, "mode": "env", "pre_restore_backup": str(previous or "")}

    if source.suffix.lower() != ".zip":
        raise RuntimeError("El respaldo debe ser ZIP o .env")

    with tempfile.TemporaryDirectory(prefix="recepcion_restore_") as td:
        temp = Path(td)
        with zipfile.ZipFile(source) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = safe_member(info.filename)
                target = temp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

        # Primero validamos manifest si existe.
        info_file = temp / "RESPALDO_INFO.json"
        if info_file.is_file():
            json.loads(info_file.read_text(encoding="utf-8"))

        for name in (".env", "HISTORICO_PACIENTES_2020_2025.csv", "BASE DE DATOS 2026.xlsx"):
            src = temp / name
            if src.is_file():
                shutil.copy2(src, root / name)

        src_data = temp / "data"
        if src_data.is_dir():
            (root / "data").mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_data, root / "data", dirs_exist_ok=True)

    normalize_env(root / ".env")
    return {
        "ok": True,
        "mode": "zip",
        "pre_restore_backup": str(previous or ""),
        "source": str(source),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    result = restore(Path(args.source), Path(args.root))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
