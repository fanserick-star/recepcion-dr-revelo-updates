from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.32"
APP_VERSION = "4.4.31"
SOURCE_DIR = ROOT / "updates" / "v443"
SOURCE_SHA256 = "f132607a6e0bb1285fcd643f43a1a5875d2a2d241d99acf3f52eeb67274e6efa"
OUT = ROOT / "updates" / "v4_4_32_launcher_port_patch"
PART_SIZE = 14000


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontré {n}")
    return text.replace(old, new, 1)


def load_latest_working_launcher() -> str:
    parts = [SOURCE_DIR / f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)]
    if not all(p.is_file() for p in parts):
        raise SystemExit("Faltan partes del launcher dinámico verificado")
    raw = b"".join(p.read_bytes() for p in parts)
    got = sha(raw)
    if got != SOURCE_SHA256:
        raise SystemExit(f"La fuente del launcher dinámico cambió: {got}")
    text = raw.decode("utf-8-sig")
    required = [
        "def _choose_app_port(force_new: bool = False)",
        'env["RP_PORT"] = str(APP_PORT)',
        "def _relaunch_updated_launcher()",
        "Puerto local seleccionado",
        "def _can_bind_port(port: int) -> bool",
    ]
    missing = [x for x in required if x not in text]
    if missing:
        raise SystemExit("La fuente no contiene el portfix esperado: " + ", ".join(missing))
    if "ABRIR_RECEPCION_base_4357" in text:
        raise SystemExit("La fuente no puede depender del launcher 4.3.57")
    return text


def build_launcher() -> bytes:
    text = load_latest_working_launcher()
    text = replace_once(
        text,
        'LAUNCHER_VERSION = "4.3.100-standalone-7"',
        'LAUNCHER_VERSION = "4.4.32-dynamic-port-patch-1"',
        "versión de launcher",
    )
    # Este parche NO reescribe la arquitectura del launcher. Conserva exactamente
    # la lógica dinámica que funcionaba hasta 4.4.30 y solo identifica el hotfix.
    compile(text, "ABRIR_RECEPCION.py", "exec")
    if 'URL = "http://127.0.0.1:8000"' in text:
        raise SystemExit("Regresión: quedó URL fija a 8000")
    if 'env["RP_PORT"] = str(APP_PORT)' not in text:
        raise SystemExit("Regresión: el backend no recibirá RP_PORT")
    if "def _choose_app_port" not in text:
        raise SystemExit("Regresión: falta elección dinámica de puerto")
    return text.encode("utf-8")


def write_parts(raw: bytes) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("ABRIR_RECEPCION.part*"):
        old.unlink()
    paths = []
    for idx, start in enumerate(range(0, len(raw), PART_SIZE), 1):
        p = OUT / f"ABRIR_RECEPCION.part{idx}"
        p.write_bytes(raw[start:start + PART_SIZE])
        paths.append(p)
    return paths


def main() -> None:
    raw = build_launcher()
    parts = write_parts(raw)
    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "launcher_version": "4.4.32-dynamic-port-patch-1",
        "updater_version": "integrado-en-launcher",
        "copy": ["ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (OUT / "update_manifest.json").write_bytes(manifest_raw)

    base = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_32_launcher_port_patch/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.32: parche mínimo del launcher. Restaura la selección dinámica de puerto "
            "que funcionaba antes de 4.4.31; reutiliza un backend sano y nunca obliga 8000/8766. "
            "No cambia app.py, interfaz, pacientes, citas, facturas, .env ni bases de datos."
        ),
        "files": [
            {
                "path": "ABRIR_RECEPCION.py",
                "parts": [base + p.name for p in parts],
                "sha256": sha(raw),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": base + "update_manifest.json",
                "sha256": sha(manifest_raw),
                "encoding": "utf-8",
            },
        ],
    }
    (OUT / "candidate_latest.json").write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("CANDIDATE_VERSION", VERSION)
    print("APP_UNCHANGED", APP_VERSION)
    print("LAUNCHER_SHA256", sha(raw))
    print("PARTS", len(parts))


if __name__ == "__main__":
    main()
