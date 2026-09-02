from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'updates' / 'v4_4_44_weekly_appointment_guard'


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    subprocess.run([sys.executable, str(HERE / 'build_v4444_cloud_sync.py')], cwd=ROOT, check=True)

    app_path = OUT / 'app.py'
    raw = app_path.read_bytes()
    text = raw.decode('utf-8-sig')
    compile(text, str(app_path), 'exec')
    ast.parse(text)

    # Contrato de guardia semanal de PC: primer intento bloqueado, override solo
    # mediante allow_same_week explícito y el guardado real sigue delegado en la
    # función estable core.agenda_create.
    pc_markers = (
        'APP_VERSION = "4.4.44"',
        'class AgendaGuardedAppointmentIn',
        '/api/agenda/appointments/guarded',
        '/api/agenda/week-conflict',
        '_v4444_same_week_conflict',
        'allow_same_week',
        'core.agenda_create(stable_data, db, user)',
        'Agendar de todas formas',
        'window.__v4444WeeklyAppointmentGuard=true',
    )
    for m in pc_markers:
        require(m in text, f'Falta guardia semanal PC: {m}')

    # Contrato Cloud/WhatsApp -> SQLite visible.
    cloud_markers = (
        '_v4444_sync_cloud_staged_for_dates',
        'v4444_cloud_staged_agenda_catchup',
        'request.url.path == "/api/agenda/week"',
        'core.queue_count() > 0',
        'core.check_cloud(force=False)',
        'core.ConfirmafyAgendaItem.fecha.in_(normalized)',
        'source_hash == source_hash',
        'mobile:whatsapp-cloud-test:',
        'if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:',
    )
    for m in cloud_markers:
        require(m in text, f'Falta sync cloud: {m}')

    start = text.index('# v4.4.44 — puente seguro Cloud/WhatsApp')
    end = text.index('FEATURE_BOOT_OK = True', start)
    sync = text[start:end]
    for forbidden in ('core.Patient(', 'delete(core.ConfirmafyAgendaItem)', 'drop(', 'ALTER TABLE', 'CREATE TABLE'):
        require(forbidden not in sync, f'Operación prohibida en sync: {forbidden}')
    require('FORCE_OFFLINE' in sync and 'queue_count() > 0' in sync, 'Faltan protecciones local-first')
    require('except Exception:' in sync and 'return 0' in sync, 'Falta fallback offline ante error cloud')

    # Archivos no modificados: deben ser byte idénticos a la estable 4.4.43.
    stable_hashes = {
        'app_base_4428.py': 'e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba',
        'static/app.js': '0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90',
        'static/index.html': '16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728',
    }
    for rel, expected in stable_hashes.items():
        require(digest((OUT / rel).read_bytes()) == expected, f'Cambio inesperado: {rel}')

    launcher = b''.join((OUT / f'ABRIR_RECEPCION.part{i}').read_bytes() for i in range(1, 5))
    require(digest(launcher) == '39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e', 'Launcher estable cambió')
    compile(launcher.decode('utf-8-sig'), 'ABRIR_RECEPCION.py', 'exec')

    manifest = json.loads((OUT / 'update_manifest.json').read_text(encoding='utf-8'))
    candidate = json.loads((OUT / 'candidate_latest.json').read_text(encoding='utf-8'))
    require(manifest.get('version') == '4.4.44', 'Manifest interno no es 4.4.44')
    require(candidate.get('version') == '4.4.44' and candidate.get('app_version') == '4.4.44', 'Canal candidato no es 4.4.44')
    require('WhatsApp/Agenda Cloud' in str(candidate.get('message') or ''), 'Release no describe sync WhatsApp')

    # El manifest publicado debe describir exactamente los bytes generados.
    for item in candidate.get('files') or []:
        rel = item['path']
        data = launcher if rel == 'ABRIR_RECEPCION.py' else (OUT / rel).read_bytes()
        require(digest(data) == item['sha256'], f'SHA incorrecto en candidato: {rel}')

    print('VALIDATE_V4444_RELEASE_STATIC_OK')


if __name__ == '__main__':
    main()
