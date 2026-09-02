from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import validate_v4444 as legacy

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    # 1) Pruebas que sí corresponden a lo modificado: contrato de guardia y
    # browser real del diálogo Cancelar / Agendar de todas formas.
    legacy.build()
    legacy.contract()
    legacy.browser_guard()

    # 2) Generar el artefacto final con el puente WhatsApp/Cloud -> SQLite.
    subprocess.run([sys.executable, str(HERE / "build_v4444_cloud_sync.py")], cwd=ROOT, check=True)
    app_path = OUT / "app.py"
    text = app_path.read_text(encoding="utf-8-sig")
    compile(text, str(app_path), "exec")

    for marker in (
        'APP_VERSION = "4.4.44"',
        '/api/agenda/appointments/guarded',
        'Agendar de todas formas',
        '_v4444_sync_cloud_staged_for_dates',
        'v4444_cloud_staged_agenda_catchup',
        'request.url.path == "/api/agenda/week"',
        'core.queue_count() > 0',
        'core.check_cloud(force=False)',
        'core.ConfirmafyAgendaItem.fecha.in_(normalized)',
        'mobile:whatsapp-cloud-test:',
    ):
        require(marker in text, f"Falta contrato: {marker}")

    start = text.index('# v4.4.44 — puente seguro Cloud/WhatsApp')
    end = text.index('FEATURE_BOOT_OK = True', start)
    sync = text[start:end]
    require('core.Patient(' not in sync, 'El puente no puede crear Patients')
    require('delete(core.ConfirmafyAgendaItem)' not in sync, 'El puente no puede borrar citas locales')
    require('FORCE_OFFLINE' in sync, 'Falta protección offline')
    require('queue_count() > 0' in sync, 'Falta protección de cola local pendiente')
    require('if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:' in sync, 'Falta protección contra colisión de ID local')

    # 3) Todo lo que NO debía cambiar debe seguir siendo exactamente el mismo
    # byte que la estable 4.4.43. Esto reemplaza la simulación lenta del updater:
    # no hay ningún launcher/base/UI nuevo que pueda romper el arranque.
    expected = {
        'app_base_4428.py': 'e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba',
        'static/app.js': '0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90',
        'static/index.html': '16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728',
    }
    for rel, digest in expected.items():
        require(sha(OUT / rel) == digest, f"Cambió archivo estable prohibido: {rel}")
    launcher = b''.join((OUT / f'ABRIR_RECEPCION.part{i}').read_bytes() for i in range(1, 5))
    require(hashlib.sha256(launcher).hexdigest() == '39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e', 'Cambió launcher estable')
    compile(launcher.decode('utf-8-sig'), 'ABRIR_RECEPCION.py', 'exec')

    candidate = json.loads((OUT / 'candidate_latest.json').read_text(encoding='utf-8'))
    require(candidate.get('version') == '4.4.44' and candidate.get('app_version') == '4.4.44', 'Candidato incorrecto')
    require('WhatsApp/Agenda Cloud' in str(candidate.get('message') or ''), 'Mensaje de release no describe sync')
    for item in candidate.get('files') or []:
        rel = item['path']
        if rel == 'ABRIR_RECEPCION.py':
            data = launcher
        else:
            data = (OUT / rel).read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['sha256'], f"SHA candidato incorrecto: {rel}")

    print('VALIDATE_V4444_RELEASE_FAST_OK')


if __name__ == '__main__':
    main()
