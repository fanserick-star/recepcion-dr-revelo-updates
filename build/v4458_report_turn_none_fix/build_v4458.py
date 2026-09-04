from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_57_consultation_turns"
OUT = ROOT / "updates" / "v4_4_58_report_turn_none_fix"
VERSION = "4.4.58"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.57"' in app_text, "La base app no es 4.4.57")
    app_text = app_text.replace('APP_VERSION = "4.4.57"', 'APP_VERSION = "4.4.58"', 1)
    app_text = app_text.replace("const VERSION='4.4.57';", "const VERSION='4.4.58';")
    compile(app_text, "app.py", "exec")

    base_text = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    old = '    for (fecha, pid), items in sorted(patient_days.items(), key=lambda kv: (kv[0][0], turns[kv[0]])):\n'
    new = '    for (fecha, pid), items in sorted(patient_days.items(), key=lambda kv: (kv[0][0], turns[kv[0]] is None, turns[kv[0]] or 0, min(v.id for v, _p in kv[1]))):\n'
    require(base_text.count(old) == 1, "No se encontro exactamente el ordenamiento roto de reportes 4.4.57")
    base_text = base_text.replace(old, new, 1)
    require('_v4457_consultation_turns(patient_days)' in base_text, "Se perdio la regla de turnos solo consultas")
    require("${num?num+'.':'—'}" in base_text, "Se perdio el guion visual para procedimientos sin turno")
    require('fecha_nacimiento: Optional[str] = None' in base_text, "Se perdio correccion 4.4.56 de fecha")
    compile(base_text, "app_base_4428.py", "exec")

    app = app_text.encode("utf-8")
    app_base = base_text.encode("utf-8")
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
    compile(launcher.decode("utf-8-sig"), "ABRIR_RECEPCION.py", "exec")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app)
    (OUT / "app_base_4428.py").write_bytes(app_base)
    for i, data in enumerate(launcher_parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.4.48-update-before-focus-dependency-safe-1",
        "updater_version": "integrado-en-launcher-update-before-focus",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_58_report_turn_none_fix/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.58: corrige Reportes cuando hay pacientes con solo procedimientos y por tanto sin numero de turno. Conserva turnos solo para consultas de v4.4.57 y todo v4.4.56.",
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4458_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()
