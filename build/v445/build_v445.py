from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.5"
APP_VERSION = "4.4.3"
BASE = ROOT / "updates" / "v443"
HOTFIX = ROOT / "updates" / "v4_4_5_search"
RAW = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def joined(prefix: str, count: int) -> bytes:
    return b"".join((BASE / f"{prefix}{i}").read_bytes() for i in range(1, count + 1))


def file_item(path: str, url: str, data: bytes) -> dict:
    return {"path": path, "url": url, "sha256": sha(data), "encoding": "utf-8"}


def main() -> None:
    launcher_parts = [f"{RAW}/updates/v443/ABRIR_RECEPCION.part{i}" for i in range(1, 5)]
    app_parts = [f"{RAW}/updates/v443/app.part{i}" for i in range(1, 8)]
    launcher = joined("ABRIR_RECEPCION.part", 4)
    app = joined("app.part", 7)
    index = (BASE / "static" / "index.html").read_bytes()
    base_js = (BASE / "static" / "app.js").read_bytes()
    hotfix_js = (HOTFIX / "static" / "app.js").read_bytes()
    manifest = (HOTFIX / "update_manifest.json").read_bytes()

    payload = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.5: restaura en Nueva atención el buscador por nombre, apellido, cédula o celular; "
            "mantiene la agenda semanal y elimina el botón Facturero Móvil únicamente del modal clínico."
        ),
        "files": [
            {
                "path": "ABRIR_RECEPCION.py",
                "parts": launcher_parts,
                "sha256": sha(launcher),
                "encoding": "utf-8",
            },
            {
                "path": "app.py",
                "parts": app_parts,
                "sha256": sha(app),
                "encoding": "utf-8",
            },
            file_item(
                "static/index.html",
                f"{RAW}/updates/v443/static/index.html",
                index,
            ),
            file_item(
                "static/app_base.js",
                f"{RAW}/updates/v443/static/app.js",
                base_js,
            ),
            file_item(
                "static/app.js",
                f"{RAW}/updates/v4_4_5_search/static/app.js",
                hotfix_js,
            ),
            file_item(
                "update_manifest.json",
                f"{RAW}/updates/v4_4_5_search/update_manifest.json",
                manifest,
            ),
        ],
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "latest.json").write_text(text, encoding="utf-8", newline="")
    (ROOT / "latest-v3.json").write_text(text, encoding="utf-8", newline="")
    print("V445_MANIFESTS_READY")


if __name__ == "__main__":
    main()
