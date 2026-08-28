from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--release-dir', required=True, help='Ej: updates/v460')
    ap.add_argument('--message', required=True)
    args=ap.parse_args()

    release_dir=(ROOT/args.release_dir).resolve()
    if ROOT not in release_dir.parents:
        raise SystemExit('release-dir fuera del repositorio')
    meta=json.loads((release_dir/'release_meta.json').read_text(encoding='utf-8'))
    version=str(meta['version'])
    parts_count=int(meta['parts_count'])
    parts=[release_dir/f'app.part{i}' for i in range(1,parts_count+1)]
    if not all(p.is_file() for p in parts):
        raise SystemExit('Faltan partes de app.py')
    app=b''.join(p.read_bytes() for p in parts)
    if len(app)!=int(meta['app_size']) or sha256(app)!=meta['app_sha256']:
        raise SystemExit('La candidata no coincide con release_meta.json')
    manifest=(release_dir/'update_manifest.json').read_bytes()
    if sha256(manifest)!=meta['manifest_sha256']:
        raise SystemExit('update_manifest.json no coincide con release_meta.json')
    manifest_obj=json.loads(manifest.decode('utf-8'))
    if str(manifest_obj.get('version'))!=version or str(manifest_obj.get('app_version'))!=version:
        raise SystemExit('Versión inconsistente en update_manifest.json')
    if f'APP_VERSION = "{version}"' not in app.decode('utf-8'):
        raise SystemExit('APP_VERSION no coincide con release_meta.json')

    current=json.loads((ROOT/'latest-v3.json').read_text(encoding='utf-8'))
    launcher=next((x for x in current.get('files',[]) if x.get('path')=='ABRIR_RECEPCION.py'),None)
    if not launcher or not launcher.get('sha256'):
        raise SystemExit('No se pudo conservar el launcher estable del canal actual')

    repo='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/'
    rel=args.release_dir.strip('/')
    channel={
        'product':'recepcion-pacientes',
        'version':version,
        'mandatory':True,
        'channel':'files-v3',
        'message':args.message,
        'files':[
            launcher,
            {
                'path':'app.py',
                'parts':[f'{repo}{rel}/app.part{i}' for i in range(1,parts_count+1)],
                'sha256':meta['app_sha256'],
                'encoding':'utf-8',
            },
            {
                'path':'update_manifest.json',
                'url':f'{repo}{rel}/update_manifest.json',
                'sha256':meta['manifest_sha256'],
                'encoding':'utf-8',
            },
        ],
    }
    text=json.dumps(channel,ensure_ascii=False,indent=2)+'\n'
    (ROOT/'latest-v3.json').write_text(text,encoding='utf-8',newline='')
    (ROOT/'latest.json').write_text(text,encoding='utf-8',newline='')
    print('CHANNEL_READY',version,meta['app_size'],meta['app_sha256'],meta['manifest_sha256'])


if __name__=='__main__':
    main()
