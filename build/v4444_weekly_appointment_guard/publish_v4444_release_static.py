from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'updates' / 'v4_4_44_weekly_appointment_guard'


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> None:
    subprocess.run(['git', *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 12) -> bytes:
    last = None
    for i in range(attempts):
        try:
            sep = '&' if '?' in url else '?'
            req = urllib.request.Request(url + sep + 'ts=' + str(time.time_ns()), headers={
                'Cache-Control': 'no-cache',
                'User-Agent': 'v4444-static-publisher',
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                require(getattr(r, 'status', 200) == 200, 'Raw HTTP no-200')
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(min(3.0, 0.4 + i * 0.35))
    raise RuntimeError(f'No propagó Raw {url}: {last}')


def main() -> None:
    subprocess.run([sys.executable, str(HERE / 'validate_v4444_release_static.py')], cwd=ROOT, check=True)
    candidate = json.loads((OUT / 'candidate_latest.json').read_text(encoding='utf-8'))
    require(candidate.get('version') == '4.4.44', 'Candidato incorrecto')

    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')

    # 1. Payload primero. latest.json no se toca hasta que Raw GitHub contenga
    # exactamente los SHA anunciados.
    git('add', 'updates/v4_4_44_weekly_appointment_guard')
    staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT, text=True).strip()
    if staged:
        git('commit', '-m', 'release: payload v4.4.44 guardia semanal y sync WhatsApp')
        git('pull', '--rebase', 'origin', 'main')
        git('push', 'origin', 'HEAD:main')

    for item in candidate['files']:
        data = b''.join(fetch(u) for u in item['parts']) if item.get('parts') else fetch(item['url'])
        require(sha(data) == item['sha256'], f'Raw SHA incorrecto: {item["path"]}')
    app_item = next(x for x in candidate['files'] if x['path'] == 'app.py')
    remote_app = fetch(app_item['url']).decode('utf-8-sig')
    require('_v4444_sync_cloud_staged_for_dates' in remote_app, 'Payload remoto no tiene sync Cloud')
    require('/api/agenda/appointments/guarded' in remote_app, 'Payload remoto no tiene guardia semanal')

    # 2. Mover canal público únicamente después de la verificación anterior.
    latest = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (ROOT / 'latest.json').write_bytes(latest)
    (ROOT / 'latest-v3.json').write_bytes(latest)
    git('add', 'latest.json', 'latest-v3.json')
    staged_latest = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT, text=True).strip()
    if staged_latest:
        git('commit', '-m', 'release: v4.4.44 pública guardia semanal y sync WhatsApp')
        git('pull', '--rebase', 'origin', 'main')
        git('push', 'origin', 'HEAD:main')

    remote = json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest.json').decode('utf-8-sig'))
    require(remote.get('version') == '4.4.44' and remote.get('app_version') == '4.4.44', 'Canal público no es 4.4.44')
    require('WhatsApp/Agenda Cloud' in str(remote.get('message') or ''), 'Canal público no describe sync')
    published_app = next(x for x in remote['files'] if x['path'] == 'app.py')
    require(published_app['sha256'] == app_item['sha256'], 'latest.json apunta a otro app.py')
    print('PUBLISH_V4444_RELEASE_STATIC_OK')


if __name__ == '__main__':
    main()
