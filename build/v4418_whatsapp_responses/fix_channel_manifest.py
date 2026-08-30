from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'updates/v4_4_18_whatsapp_responses'
VERSION='4.4.18'
ref=str(os.getenv('RP_PAYLOAD_SHA') or 'main').strip()
if ref!='main' and not re.fullmatch(r'[0-9a-f]{40}',ref):
    raise SystemExit('RP_PAYLOAD_SHA inválido')
BASE=f'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/{ref}/updates/v4_4_18_whatsapp_responses'

def sha(path: Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

# El manifiesto que viaja dentro del programa conserva el formato histórico
# esperado por el launcher. El canal externo contiene SHA de cada archivo.
update_manifest={
    'product':'recepcion-pacientes',
    'version':VERSION,
    'app_version':VERSION,
    'runtime_version':VERSION,
    'launcher_version':'4.3.100-standalone-7',
    'updater_version':'integrado-en-launcher',
    'copy':['app.py','static/app.js','static/index.html','update_manifest.json'],
}
(OUT/'update_manifest.json').write_text(json.dumps(update_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel
    if not p.exists(): raise SystemExit(f'Falta {rel}')
    files.append({'path':rel,'url':f'{BASE}/{rel}','sha256':sha(p),'encoding':'utf-8'})

channel={
    'product':'recepcion-pacientes',
    'version':VERSION,
    'app_version':VERSION,
    'runtime_version':VERSION,
    'mandatory':True,
    'channel':'files-v3',
    'message':'v4.4.18: nueva bandeja Respuestas WhatsApp con contador en el menú y alerta en Inicio; permite revisar texto y audio, ver transcripciones y resolver como Confirmado, No asistirá o Resuelto. Los casos ambiguos nunca cambian una cita automáticamente.',
    'files':files,
}
(ROOT/'build/v4418_whatsapp_responses/candidate_latest.json').write_text(json.dumps(channel,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
# Evita que py_compile termine publicando archivos internos de Python.
for cache in OUT.rglob('__pycache__'):
    shutil.rmtree(cache,ignore_errors=True)
print(f'V4418_CHANNEL_MANIFEST_OK ref={ref}')
