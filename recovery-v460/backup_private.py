from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


PRIVATE_ROOT_FILES = (
    ".env",
    "HISTORICO_PACIENTES_2020_2025.csv",
    "BASE DE DATOS 2026.xlsx",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sqlite_snapshot(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(src), timeout=10)
    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def build_backup(root: Path, output: Path, include_backups: bool = False) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"No existe la instalación: {root}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="recepcion_private_backup_") as temp_name:
        temp = Path(temp_name)
        copied: list[Path] = []

        for name in PRIVATE_ROOT_FILES:
            src = root / name
            if src.is_file():
                dst = temp / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(dst)

        data = root / "data"
        if data.is_dir():
            for src in data.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(root)
                if not include_backups and len(rel.parts) >= 2 and rel.parts[1].lower() == "backups":
                    continue
                dst = temp / rel
                if src.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                    sqlite_snapshot(src, dst)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                copied.append(dst)

        if not copied:
            raise SystemExit("No encontré datos privados de Recepción para respaldar")

        manifest = {
            "schema": 1,
            "product": "recepcion-dr-revelo",
            "created_at": datetime.now().astimezone().isoformat(),
            "source_root": str(root),
            "include_old_backups": bool(include_backups),
            "files": [],
        }
        for path in sorted(copied):
            manifest["files"].append({
                "path": path.relative_to(temp).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            })

        (temp / "RESPALDO_INFO.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        tmp_zip = output.with_suffix(output.suffix + ".tmp")
        if tmp_zip.exists():
            tmp_zip.unlink()
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path in sorted(temp.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(temp).as_posix())
        tmp_zip.replace(output)

    return {
        "ok": True,
        "output": str(output),
        "size": output.stat().st_size,
        "sha256": sha256(output),
        "files": len(manifest["files"]),
        "warning": "Este ZIP contiene información privada del consultorio y puede contener credenciales.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=r"C:\Recepcion Dr Revelo")
    parser.add_argument("--output", default="")
    parser.add_argument("--include-old-backups", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    if args.output:
        output = Path(args.output)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = Path.home() / "Desktop" / f"RESPALDO_PRIVADO_RECEPCION_{stamp}.zip"

    result = build_backup(root, output, args.include_old_backups)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
