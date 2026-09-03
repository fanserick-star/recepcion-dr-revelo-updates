from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_52_quick_unlinked_appointment"
OUT = ROOT / "updates" / "v4_4_53_slot_capture_fix"
VERSION = "4.4.53"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.52"' in app_text, "La base app no es 4.4.52")
    app_text = app_text.replace('APP_VERSION = "4.4.52"', 'APP_VERSION = "4.4.53"', 1)
    app_text = app_text.replace("const VERSION='4.4.52';", "const VERSION='4.4.53';")

    old = '''  function slotFromModal(box){
    const dateInput=box?.querySelector('#agendaDate,input[type=\"date\"]');
    const timeInput=box?.querySelector('#agendaTime,input[type=\"time\"]');
    const fecha=String(dateInput?.value||'').slice(0,10),hora=String(timeInput?.value||'').slice(0,5);'''
    new = '''  function slotFromModal(box){
    // El flujo estable guarda usando $('#agendaDate') / $('#agendaTime') a nivel
    // documento. En algunas composiciones visuales esos inputs quedan fuera del
    // .modalbox interno aunque pertenecen a la misma ventana Nueva cita.
    const dateInput=document.querySelector('#agendaDate')||box?.querySelector('input[type=\"date\"]');
    const timeInput=document.querySelector('#agendaTime')||box?.querySelector('input[type=\"time\"]');
    const fecha=String(dateInput?.value||'').slice(0,10),hora=String(timeInput?.value||'').slice(0,5);'''
    require(old in app_text, "No se encontró slotFromModal v4.4.52")
    app_text = app_text.replace(old, new, 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
    app_base = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
    compile(app_base.decode("utf-8-sig"), "app_base_4428.py", "exec")
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

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_53_slot_capture_fix/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.53: Crear cita nueva toma correctamente la fecha y hora ya seleccionadas usando los mismos controles globales del guardado estable. Conserva todo v4.4.52.",
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4453_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()
