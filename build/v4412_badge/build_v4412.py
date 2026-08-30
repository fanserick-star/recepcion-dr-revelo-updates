from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.4.12'
SOURCE_APP='updates/v4_4_9_clean_444/app.py'
SOURCE_JS='updates/v4_4_11_attention_ux/static/app.js'
SOURCE_INDEX='updates/v4_4_11_attention_ux/static/index.html'
OUT=ROOT/'updates'/'v4_4_12_badge'
EXPECTED_APP='148e1cd846ec848f8e75dac1eb5baa60f059176966b374a90be2f563afb96133'
EXPECTED_JS='852ac51d912740b6faa4a0a9d95826a4c5384e7aac8fe6f69b744f8fb081be66'
EXPECTED_INDEX='39de6d73f782c73540fa7773f207da25a121437309168a71a3eb6e7a62895d02'

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def git_bytes(p:str)->bytes:return subprocess.check_output(['git','show',f'HEAD:{p}'],cwd=ROOT)

def main():
    app_raw=git_bytes(SOURCE_APP)
    js_raw=git_bytes(SOURCE_JS)
    index_raw=git_bytes(SOURCE_INDEX)
    if sha(app_raw)!=EXPECTED_APP:raise SystemExit('app fuente cambió: '+sha(app_raw))
    if sha(js_raw)!=EXPECTED_JS:raise SystemExit('js fuente cambió: '+sha(js_raw))
    if sha(index_raw)!=EXPECTED_INDEX:raise SystemExit('index fuente cambió: '+sha(index_raw))

    app=app_raw.decode('utf-8-sig')
    if app.count('APP_VERSION = "4.4.9"')!=1:raise SystemExit('APP_VERSION fuente inesperada')
    app=app.replace('APP_VERSION = "4.4.9"','APP_VERSION = "4.4.12"',1)
    old="const VERSION=\\'4.4.3\\';"
    new="const VERSION=\\'4.4.12\\';"
    count=app.count(old)
    if count<1:raise SystemExit('No se encontró VERSION visual 4.4.3')
    app=app.replace(old,new)
    if old in app:raise SystemExit('Quedó un badge 4.4.3')
    if 'RP_PORT' not in app or 'pg8000' not in app:raise SystemExit('Se perdió infraestructura estable')

    index=index_raw.decode('utf-8-sig')
    if index.count('/static/app.js?v=4.4.11')!=1:raise SystemExit('cache 4.4.11 inesperado')
    index=index.replace('/static/app.js?v=4.4.11','/static/app.js?v=4.4.12',1)

    OUT.mkdir(parents=True,exist_ok=True);(OUT/'static').mkdir(exist_ok=True)
    app_b=app.encode('utf-8');js_b=js_raw;index_b=index.encode('utf-8')
    (OUT/'app.py').write_bytes(app_b)
    (OUT/'static'/'app.js').write_bytes(js_b)
    (OUT/'static'/'index.html').write_bytes(index_b)
    inner={
      'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
      'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
      'copy':['app.py','static/app.js','static/index.html','update_manifest.json']}
    inner_b=(json.dumps(inner,ensure_ascii=False,indent=2)+'\n').encode()
    (OUT/'update_manifest.json').write_bytes(inner_b)
    latest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'mandatory':True,'channel':'files-v3',
      'message':'v4.4.12: incluye UX de búsqueda v4.4.11 y corrige el badge de versión heredado 4.4.3. Mantiene RP_PORT dinámico y pg8000.',
      'files':[
       {'path':'app.py','url':'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_12_badge/app.py','sha256':sha(app_b),'encoding':'utf-8'},
       {'path':'static/app.js','url':'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_12_badge/static/app.js','sha256':sha(js_b),'encoding':'utf-8'},
       {'path':'static/index.html','url':'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_12_badge/static/index.html','sha256':sha(index_b),'encoding':'utf-8'},
       {'path':'update_manifest.json','url':'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_12_badge/update_manifest.json','sha256':sha(inner_b),'encoding':'utf-8'}]}
    (ROOT/'build'/'v4412_badge'/'candidate_latest.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='')
    print('V4412_BUILT',count,sha(app_b),sha(js_b),sha(index_b),sha(inner_b))

if __name__=='__main__':main()
