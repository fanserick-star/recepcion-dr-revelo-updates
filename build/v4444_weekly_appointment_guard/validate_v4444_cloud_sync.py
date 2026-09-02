from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    # Primero debe pasar íntegra la validación heredada: compile, browser smoke,
    # updater smoke y todas las protecciones de la guardia semanal.
    subprocess.run([sys.executable, str(HERE / "validate_v4444.py")], cwd=ROOT, check=True)

    # Después generamos exactamente el payload que se publicará con el puente
    # Cloud -> SQLite y lo volvemos a validar byte por byte.
    subprocess.run([sys.executable, str(HERE / "build_v4444_cloud_sync.py")], cwd=ROOT, check=True)

    app_path = OUT / "app.py"
    app_text = app_path.read_text(encoding="utf-8-sig")
    compile(app_text, str(app_path), "exec")

    markers = [
        'APP_VERSION = "4.4.44"',
        '/api/agenda/appointments/guarded',
        'Agendar de todas formas',
        '_v4444_sync_cloud_staged_for_dates',
        'v4444_cloud_staged_agenda_catchup',
        'request.url.path == "/api/agenda/week"',
        'core.ConfirmafyAgendaItem.fecha.in_(normalized)',
        'core.queue_count() > 0',
        'mobile:whatsapp-cloud-test:',
        'No sobreescribimos jamás otra fila local',
    ]
    for marker in markers:
        require(marker in app_text, f"Falta marcador de seguridad/sync: {marker}")

    # El parche no puede convertir la Agenda en dependiente de Internet ni crear
    # fichas Patient a partir de citas externas.
    sync_start = app_text.index('# v4.4.44 — puente seguro Cloud/WhatsApp')
    sync_end = app_text.index('FEATURE_BOOT_OK = True', sync_start)
    sync_block = app_text[sync_start:sync_end]
    require('core.Patient(' not in sync_block, "El sync no debe crear pacientes")
    require('delete(core.ConfirmafyAgendaItem)' not in sync_block, "El sync no debe borrar citas locales")
    require('FORCE_OFFLINE' in sync_block and 'queue_count() > 0' in sync_block, "Faltan resguardos offline/local-first")

    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(candidate.get("version") == "4.4.44", "Versión candidata incorrecta")
    require("WhatsApp/Agenda Cloud" in str(candidate.get("message") or ""), "El canal no describe el arreglo cloud")

    for item in candidate.get("files") or []:
        rel = item["path"]
        if rel == "ABRIR_RECEPCION.py":
            data = b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))
        else:
            data = (OUT / rel).read_bytes()
        require(sha(data) == item["sha256"], f"SHA candidato incorrecto: {rel}")

    require(
        sha((OUT / "app.py").read_bytes()) == next(x["sha256"] for x in candidate["files"] if x["path"] == "app.py"),
        "app.py no coincide con candidate_latest.json",
    )
    print("VALIDATE_V4444_CLOUD_SYNC_OK")


if __name__ == "__main__":
    main()
