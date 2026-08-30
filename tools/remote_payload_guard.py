from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

PRODUCT = "recepcion-pacientes"
PROTECTED_TOP = {"data", ".venv"}
PROTECTED_FILES = {".env", "BASE DE DATOS 2026.xlsx"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(url: str, attempts: int = 8, timeout: float = 20.0) -> bytes:
    last = None
    for n in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Recepcion-Release-Guard/1",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(25_000_000)
                if len(data) >= 25_000_000:
                    raise RuntimeError("Payload demasiado grande para la guardia")
                return data
        except Exception as exc:
            last = exc
            if n + 1 < attempts:
                time.sleep(min(1.0 + n * 0.5, 4.0))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def _is_immutable_raw(url: str) -> bool:
    m = re.match(
        r"^https://raw\.githubusercontent\.com/[^/]+/[^/]+/([^/]+)/.+$",
        url,
        re.I,
    )
    if not m:
        return False
    ref = m.group(1)
    # Git commit SHA completo: evita que el contenido cambie después de publicar.
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", ref))


def _safe_path(rel: str) -> None:
    norm = str(rel or "").replace("\\", "/").lstrip("/")
    parts = [x for x in norm.split("/") if x]
    if not parts or any(x in {".", ".."} for x in parts):
        raise RuntimeError(f"Ruta inválida en manifiesto: {rel!r}")
    if parts[0].lower() in {x.lower() for x in PROTECTED_TOP}:
        raise RuntimeError(f"Ruta protegida en actualización: {rel}")
    if len(parts) == 1 and parts[0].lower() in {x.lower() for x in PROTECTED_FILES}:
        raise RuntimeError(f"Archivo protegido en actualización: {rel}")


def validate_manifest(path: Path, require_immutable: bool = False) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("product") != PRODUCT:
        raise RuntimeError("Producto incorrecto en manifiesto")
    version = str(manifest.get("version") or "").strip()
    if not version:
        raise RuntimeError("Manifiesto sin versión")
    files = manifest.get("files") or []
    if not files:
        raise RuntimeError("Manifiesto sin archivos")

    seen = set()
    for item in files:
        rel = str(item.get("path") or "")
        _safe_path(rel)
        if rel in seen:
            raise RuntimeError(f"Ruta duplicada: {rel}")
        seen.add(rel)

        expected = str(item.get("sha256") or "").lower().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeError(f"SHA inválido en manifiesto para {rel}")

        urls = list(item.get("parts") or [])
        if not urls:
            url = str(item.get("url") or "").strip()
            if not url:
                raise RuntimeError(f"Falta URL para {rel}")
            urls = [url]

        if require_immutable:
            bad = [u for u in urls if not _is_immutable_raw(u)]
            if bad:
                raise RuntimeError(
                    f"{rel} no apunta a un commit inmutable: {bad[0]}"
                )

        payload = b"".join(_download(u) for u in urls)
        got = _sha(payload)
        if got != expected:
            raise RuntimeError(
                f"SHA REMOTO inválido para {rel}: {got} != {expected}"
            )
        print(f"REMOTE_SHA_OK {rel} {got}")

    print(f"REMOTE_PAYLOAD_GUARD_OK {version} ({len(files)} archivos)")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--require-immutable", action="store_true")
    args = p.parse_args()
    validate_manifest(Path(args.manifest), require_immutable=args.require_immutable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
