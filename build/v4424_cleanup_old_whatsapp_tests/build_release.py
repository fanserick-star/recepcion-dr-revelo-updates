from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_23_agenda_whatsapp'
OUT=ROOT/'updates/v4_4_24_cleanup_old_whatsapp_tests'
VERSION='4.4.24'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')

assert 'APP_VERSION = "4.4.23"' in app
assert "const VERSION=\\'4.4.23\\';" in app
assert '/static/app.js?v=4.4.23' in html

app=app.replace('APP_VERSION = "4.4.23"','APP_VERSION = "4.4.24"',1)
app=app.replace("const VERSION=\\'4.4.23\\';","const VERSION=\\'4.4.24\\';",1)
html=html.replace('/static/app.js?v=4.4.23','/static/app.js?v=4.4.24',1)

# Limpieza puntual y segura de las pruebas antiguas visibles en Agenda.
# Solo actúa sobre el número de prueba mostrado por el usuario y solo sobre
# respuestas REVISAR anteriores al corte. No modifica citas ni pacientes.
endpoint_marker='@app.get("/api/whatsapp-responses/count")\n'
assert endpoint_marker in app
cleanup_endpoint=r'''
WA_TEST_CLEANUP_PHONE_V4424 = "593967841449"
WA_TEST_CLEANUP_CUTOFF_V4424 = datetime(2026, 8, 31, 1, 29, 0)

@app.post("/api/whatsapp-responses/cleanup-old-tests")
def whatsapp_cleanup_old_tests_v4424(user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        return {"available": False, "cleaned": 0}
    try:
        with cloud_engine.begin() as conn:
            if not _wa_inbound_table_ready(conn):
                return {"available": True, "ready": False, "cleaned": 0}
            result = conn.execute(text("""
                UPDATE whatsapp_cloud.inbound_responses
                SET resolved_at = COALESCE(resolved_at, CURRENT_TIMESTAMP),
                    resolved_by = 'cleanup-v4.4.24',
                    resolution = 'RESUELTO'
                WHERE resolved_at IS NULL
                  AND upper(coalesce(interpretation,'')) = 'REVISAR'
                  AND regexp_replace(coalesce(phone,''), '[^0-9]', '', 'g') = :phone
                  AND received_at < :cutoff
            """), {
                "phone": WA_TEST_CLEANUP_PHONE_V4424,
                "cutoff": WA_TEST_CLEANUP_CUTOFF_V4424,
            })
            return {"available": True, "ready": True, "cleaned": max(0, int(result.rowcount or 0))}
    except Exception as exc:
        return {"available": False, "cleaned": 0, "error": str(exc)[:180]}

'''
app=app.replace(endpoint_marker,cleanup_endpoint+endpoint_marker,1)

# Ejecutar una sola vez por instalación. Si no hay nube, no guarda el marcador
# y volverá a intentar en el próximo arranque/entrada a Agenda.
js_marker='let agendaWhatsappReviewPanelOpen=false;'
assert js_marker in js
cleanup_js=r'''
let agendaOldWhatsappCleanupRunning=false;
async function cleanupOldWhatsappTestsOnce(){
  if(agendaOldWhatsappCleanupRunning)return;
  try{if(localStorage.getItem('rp-v4424-wa-old-tests-cleaned')==='1')return}catch{}
  agendaOldWhatsappCleanupRunning=true;
  try{
    const d=await api('/api/whatsapp-responses/cleanup-old-tests',{method:'POST'});
    if(d?.available===false)return;
    try{localStorage.setItem('rp-v4424-wa-old-tests-cleaned','1')}catch{}
    if(Number(d?.cleaned||0)>0){
      agendaWhatsappLoadedAt=0;
      whatsappReviewLastCheck=0;
      if(agendaNativeWeek)await loadAgendaWhatsappOverlay(agendaNativeWeek,true);
      await refreshWhatsappReviewBadge(true);
    }
  }catch{}
  finally{agendaOldWhatsappCleanupRunning=false}
}
'''
js=js.replace(js_marker,js_marker+'\n'+cleanup_js,1)

call_marker='    loadAgendaWhatsappOverlay(d,false);\n'
assert call_marker in js
js=js.replace(call_marker,call_marker+'    setTimeout(()=>cleanupOldWhatsappTestsOnce(),120);\n',1)

# Escribir payload.
write(OUT/'app.py',app)
write(OUT/'static/app.js',js)
write(OUT/'static/index.html',html)

manifest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
  'copy':['app.py','static/app.js','static/index.html','update_manifest.json']
}
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base_url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_24_cleanup_old_whatsapp_tests/'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel
    files.append({'path':rel,'url':base_url+rel,'sha256':sha(p),'encoding':'utf-8'})
latest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'mandatory':True,'channel':'files-v3',
  'message':'v4.4.24: limpia automáticamente las respuestas antiguas de prueba que quedaron en Por revisar. Solo marca como resueltas las pruebas previas del número de prueba identificado; no modifica citas, pacientes ni mensajes nuevos.',
  'files':files
}
write(ROOT/'build/v4424_cleanup_old_whatsapp_tests/candidate_latest.json',json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
print('V4424_BUILD_OK')
