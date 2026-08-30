from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_RAW = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates"
VERSION = "4.4.7"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_url(ref: str, path: str) -> str:
    return f"{REPO_RAW}/{ref}/{path}"


def sorted_parts(folder: Path, prefix: str) -> list[Path]:
    parts = list(folder.glob(prefix + "*"))
    def n(p: Path) -> int:
        m = re.search(r"(\d+)$", p.name)
        return int(m.group(1)) if m else 0
    return sorted(parts, key=n)


def direct_entry(ref: str, rel: str, repo_path: str) -> dict:
    data = (ROOT / repo_path).read_bytes()
    return {
        "path": rel,
        "url": raw_url(ref, repo_path.replace("\\", "/")),
        "sha256": sha(data),
        "encoding": "utf-8",
    }


def parts_entry(ref: str, rel: str, parts: list[Path]) -> dict:
    if not parts:
        raise SystemExit(f"No se encontraron partes para {rel}")
    data = b"".join(p.read_bytes() for p in parts)
    urls = [raw_url(ref, p.relative_to(ROOT).as_posix()) for p in parts]
    return {
        "path": rel,
        "parts": urls,
        "sha256": sha(data),
        "encoding": "utf-8",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="Commit SHA inmutable que contiene los payloads")
    args = ap.parse_args()
    ref = args.ref.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        raise SystemExit("--ref debe ser un commit SHA completo de 40 caracteres")

    launcher_parts = sorted_parts(ROOT / "updates" / "v443", "ABRIR_RECEPCION.part")
    app_parts = sorted_parts(ROOT / "updates" / "v4_4_7_recovery", "app.part")
    if len(launcher_parts) != 4:
        raise SystemExit(f"Launcher incompleto: {len(launcher_parts)} partes")
    if len(app_parts) != 7:
        raise SystemExit(f"app.py incompleto: {len(app_parts)} partes")

    files = [
        parts_entry(ref, "ABRIR_RECEPCION.py", launcher_parts),
        parts_entry(ref, "app.py", app_parts),
        direct_entry(ref, "static/index.html", "updates/v4_4_7_recovery/static/index.html"),
        direct_entry(ref, "static/app.js", "updates/v4_4_7_recovery/static/app.js"),
        direct_entry(ref, "static/app_base.js", "updates/v4_4_7_recovery/static/app_base.js"),
        direct_entry(ref, "update_manifest.json", "updates/v4_4_7_recovery/update_manifest.json"),
    ]

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.7 recuperación segura: restaura la base estable con pg8000. "
            "Payload fijado a commit inmutable y SHA verificado contra GitHub Raw antes de publicar."
        ),
        "payload_ref": ref,
        "files": files,
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "latest-v3.json").write_text(text, encoding="utf-8", newline="\n")
    (ROOT / "latest.json").write_text(text, encoding="utf-8", newline="\n")
    print("V447_MANIFEST_REBUILT", ref)
    for item in files:
        print(item["path"], item["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
