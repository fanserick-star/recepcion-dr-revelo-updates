from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_DIR = "updates/v4_4_9_clean_444"
VERSION = "4.4.9"
FILES = [
    "app.py",
    "static/index.html",
    "static/app.js",
    "static/app_base.js",
    "update_manifest.json",
]


def git_bytes(ref: str, rel: str) -> bytes:
    try:
        return subprocess.check_output(["git", "show", f"{ref}:{rel}"], cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"No se pudo leer {rel} desde {ref}: {exc}") from exc


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ref", required=True)
    p.add_argument("--out", default="candidate-v449-latest.json")
    args = p.parse_args()

    ref = args.ref.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        raise SystemExit("--ref debe ser un commit SHA completo de 40 caracteres")

    inner = json.loads(git_bytes(ref, f"{PAYLOAD_DIR}/update_manifest.json").decode("utf-8-sig"))
    if inner.get("version") != VERSION or inner.get("app_version") != VERSION:
        raise SystemExit("El manifiesto interno del payload no es 4.4.9")

    base = f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/{ref}/{PAYLOAD_DIR}/"
    items = []
    for rel in FILES:
        data = git_bytes(ref, f"{PAYLOAD_DIR}/{rel}")
        items.append({
            "path": rel,
            "url": base + rel,
            "sha256": sha(data),
            "encoding": "utf-8",
        })

    latest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "payload_ref": ref,
        "message": (
            "v4.4.9: recupera la interfaz real de v4.4.4 en un solo app.js, "
            "neutraliza el app_base.js legado, conserva RP_PORT dinámico y usa pg8000. "
            "Payload fijado a commit inmutable y verificado contra GitHub Raw antes de publicar."
        ),
        "files": items,
    }

    out = ROOT / args.out
    out.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    print("V449_CHANNEL_CANDIDATE", ref)
    for item in items:
        print(item["path"], item["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
