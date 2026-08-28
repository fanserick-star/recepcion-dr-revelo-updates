from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.62'
BASE_VERSION='4.3.61'
BASE_SHA='2be72df19eef0ba005fdb9aa2d8bf9d74f7a5ef0f5661809d7feb354372c369d'
oldroot=ROOT/'updates'/'v461'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.61 no coincide con la publicada')

s=raw.decode('utf-8')

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: se esperaba 1 coincidencia y hubo {n}')
    s=s.replace(old,new,1)

one('APP_VERSION = "4.3.61"','APP_VERSION = "4.3.62"','APP_VERSION')
one("const VERSION='4.3.61';","const VERSION='4.3.62';",'badge version')
one('/v460/overlay.css?v=4.3.61','/v460/overlay.css?v=4.3.62','overlay css cache')
one('/v460/overlay.js?v=4.3.61','/v460/overlay.js?v=4.3.62','overlay js cache')
one('token = secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:22]','token = secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:19]','cloud test token length')

# Guard permanente: source_hash en Neon es varchar(64).
prefix='mobile:whatsapp-cloud-test:'
for template in ('recordatorio_cita','cita_agendada','recordatorio_hoy'):
    candidate=f'{prefix}{template}:'+('x'*19)
    if len(candidate)>64:
        raise SystemExit(f'source_hash demasiado largo para {template}: {len(candidate)}')

final=s.encode('utf-8')
app_sha=hashlib.sha256(final).hexdigest()
out=ROOT/'updates'/'v462'
out.mkdir(parents=True,exist_ok=True)
for p in out.glob('app.part*'):
    p.unlink()
PART=70000
chunks=[final[i:i+PART] for i in range(0,len(final),PART)]
for i,chunk in enumerate(chunks,1):
    (out/f'app.part{i}').write_bytes(chunk)
manifest={
  'product':'recepcion-pacientes',
  'version':VERSION,
  'app_version':VERSION,
  'runtime_version':VERSION,
  'launcher_version':'4.3.57-standalone-1',
  'updater_version':'integrado-en-launcher',
  'copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json'],
}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={
  'product':'recepcion-pacientes',
  'version':VERSION,
  'base_version':BASE_VERSION,
  'base_sha256':BASE_SHA,
  'app_sha256':app_sha,
  'app_size':len(final),
  'part_max_bytes':PART,
  'parts_count':len(chunks),
  'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V462_BUILT',len(final),app_sha,'parts',len(chunks))
