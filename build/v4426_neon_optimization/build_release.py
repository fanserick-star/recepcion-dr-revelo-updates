from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_25_auto_booking'
OUT=ROOT/'updates/v4_4_26_neon_optimization'
VERSION='4.4.26'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')

assert 'APP_VERSION = "4.4.25"' in app
assert "const VERSION=\\'4.4.25\\';" in app
assert '/static/app.js?v=4.4.25' in html
assert 'CLOUD_CHECK_SECONDS = 180.0' in app

app=app.replace('APP_VERSION = "4.4.25"','APP_VERSION = "4.4.26"',1)
app=app.replace("const VERSION=\\'4.4.25\\';","const VERSION=\\'4.4.26\\';",1)
html=html.replace('/static/app.js?v=4.4.25','/static/app.js?v=4.4.26',1)

# Las pantallas ya leen SQLite. Antes de operaciones reales, reutilizamos el
# estado conocido durante 10 minutos en lugar de hacer SELECT 1 cada 3 minutos.
# Los fallos de una escritura siguen entrando al mecanismo offline/sincronización.
app=app.replace('CLOUD_CHECK_SECONDS = 180.0','CLOUD_CHECK_SECONDS = 600.0',1)

write(OUT/'app.py',app)
write(OUT/'static/app.js',js)
write(OUT/'static/index.html',html)
manifest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
  'copy':['app.py','static/app.js','static/index.html','update_manifest.json']
}
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
base_url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_26_neon_optimization/'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel
    files.append({'path':rel,'url':base_url+rel,'sha256':sha(p),'encoding':'utf-8'})
latest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'mandatory':True,'channel':'files-v3',
  'message':'v4.4.26: optimiza aún más el uso de Neon. Recepción reutiliza el estado de conexión hasta 10 minutos entre operaciones, mantiene todas las pantallas habituales en SQLite local y conserva AFK/sincronización offline. No modifica las bases de datos locales ni el Excel.',
  'files':files
}
write(ROOT/'build/v4426_neon_optimization/candidate_latest.json',json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
print('V4426_NEON_OPTIMIZATION_BUILD_OK')
