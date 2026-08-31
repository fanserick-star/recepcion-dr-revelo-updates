from __future__ import annotations
import hashlib,json,re,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_18_whatsapp_responses'
OUT=ROOT/'updates/v4_4_19_whatsapp_test_retention'
VERSION='4.4.19'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')
assert 'APP_VERSION = "4.4.18"' in app
assert "const VERSION=\\'4.4.18\\';" in app
assert '/static/app.js?v=4.4.18' in html

app=app.replace('APP_VERSION = "4.4.18"','APP_VERSION = "4.4.19"',1)
app=app.replace("const VERSION=\\'4.4.18\\';","const VERSION=\\'4.4.19\\';",1)
html=html.replace('/static/app.js?v=4.4.18','/static/app.js?v=4.4.19',1)

old='''                if stored_token and hmac.compare_digest(stored_token, str(token or "")):\n                    cdb.execute(text("DELETE FROM public.confirmafy_agenda_items WHERE id=:source_id"), {"source_id": int(test_id)})\n                    cdb.commit()\n        return {"ok": True, "message": "Prueba técnica finalizada. No se modificó ningún paciente ni cita real."}'''
new='''                if stored_token and hmac.compare_digest(stored_token, str(token or "")):\n                    # v4.4.19: no borrar inmediatamente la cita técnica. El Worker\n                    # necesita esta fila temporal para poder interpretar texto/audio\n                    # y devolver el acuse de prueba después de que llegó la plantilla.\n                    # Sigue totalmente excluida de Agenda/Inicio y el limpiador la\n                    # elimina automáticamente al cumplir 2 horas.\n                    pass\n        return {"ok": True, "message": "Prueba técnica cerrada en pantalla. Se conservará temporalmente solo para validar respuestas y se eliminará automáticamente."}'''
if old not in app: raise SystemExit('No encontré el cierre de prueba WhatsApp esperado')
app=app.replace(old,new,1)

manifest={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
 'copy':['app.py','static/app.js','static/index.html','update_manifest.json']}

if OUT.exists():shutil.rmtree(OUT)
write(OUT/'app.py',app);write(OUT/'static/app.js',js);write(OUT/'static/index.html',html)
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_19_whatsapp_test_retention'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel;files.append({'path':rel,'url':f'{base}/{rel}','sha256':sha(p),'encoding':'utf-8'})
channel={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'mandatory':True,'channel':'files-v3',
 'message':'v4.4.19: mejora la prueba técnica de WhatsApp para permitir responder por texto o audio y comprobar el acuse automático sin tocar citas reales. La cita temporal permanece oculta y se elimina sola después de 2 horas.',
 'files':files}
write(ROOT/'build/v4419_whatsapp_test_retention/candidate_latest.json',json.dumps(channel,ensure_ascii=False,indent=2)+'\n')

assert 'Prueba técnica cerrada en pantalla' in app
assert 'elimina automáticamente al cumplir 2 horas' in app
assert 'mobile:whatsapp-cloud-test:' in app
assert '/static/app.js?v=4.4.19' in html
assert 'data-section="whatsappRespuestas"' in html
assert 'resolveWhatsappResponse' in js
print('V4419_BUILD_OK')
