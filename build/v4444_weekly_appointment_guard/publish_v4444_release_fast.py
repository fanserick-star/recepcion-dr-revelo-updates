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


def git(*args: str) -> None:
    subprocess.run(['git', *args], cwd=ROOT, check=True)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, attempts: int = 16) -> bytes:
    last = None
    for i in range(attempts):
        try:
            sep = '&' if '?' in url else '?'
            req = urllib.request.Request(
                url + sep + 'v=' + str(time.time_ns()),
                headers={'Cache-Control': 'no-cache', 'User-Agent': 'v4444-fast-release'},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                require(getattr(r, 'status', 200) == 200, f'HTTP {getattr(r, "status", "?")}')
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(min(4.0, 0.5 + i * 0.4))
    raise RuntimeError(f'Raw no propagó {url}: {last}')


def main() -> None:
    subprocess.run([sys.executable, str(HERE / 'validate_v4444_release_fast.py')], cwd=ROOT, check=True)
    candidate_path = OUT / 'candidate_latest.json'
    candidate = json.loads(candidate_path.read_text(encoding='utf-8'))
    require(candidate.get('version') == '4.4.44', 'Versión candidata incorrecta')

    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')

    # Publicar primero artefactos. El canal estable todavía no se mueve.
    git('add', 'updates/v4_4_44_weekly_appointment_guard')
    staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=ROOT, text=True).strip()
    if staged:
        git('commit', '-m', 'release: payload final v4.4.44 guardia y sync cloud')
        # Puede haber commits nuevos de CI; rebase para no pisarlos.
        git('pull', '--rebase', 'origin', 'main')
        git('push', 'origin', 'HEAD:main')

    # Verificar Raw GitHub byte por byte antes de anunciar la actualización.
    for item in candidate.get('files') or []:
        data = b''.join(fetch(u) for u in item['parts']) if item.get('parts') else fetch(item['url'])
        require(sha(data) == item['sha256'], f'SHA Raw incorrecto: {item["path"]}')
    remote_app_url = next(x['url'] for x in candidate['files'] if x['path'] == 'app.py')
    remote_app = fetch(remote_app_url).decode('utf-8-sig')
    require('_v4444_sync_cloud_staged_for_dates' in remote_app, 'Raw app no contiene sync cloud')
    require('/api/agenda/appointments/guarded' in remote_app, 'Raw app perdió guardia semanal')

    # Solo ahora mover latest.json/latest-v3.json.
    latest = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    (ROOT / 'latest-v3.json').write_bytes(latest)
    (ROOT / 'latest.json').write_bytes(latest)
    git('add', 'latest-v3.json', 'latest.json')
    git('commit', '-m', 'release: publicar v4.4.44 guardia semanal y sync WhatsApp')
    git('pull', '--rebase', 'origin', 'main')
    git('push', 'origin', 'HEAD:main')

    remote_latest = json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest.json').decode('utf-8-sig'))
    require(remote_latest.get('version') == '4.4.44' and remote_latest.get('app_version') == '4.4.44', 'latest.json no propagó 4.4.44')
    require('WhatsApp/Agenda Cloud' in str(remote_latest.get('message') or ''), 'latest.json propagado no describe el arreglo')
    remote_hash = next(x['sha256'] for x in remote_latest['files'] if x['path'] == 'app.py')
    local_hash = next(x['sha256'] for x in candidate['files'] if x['path'] == 'app.py')
    require(remote_hash == local_hash, 'Hash app.py de latest no coincide')
    print('PUBLISH_V4444_RELEASE_FAST_OK')


if __name__ == '__main__':
    main()
