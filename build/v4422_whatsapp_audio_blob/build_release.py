from __future__ import annotations
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_21_whatsapp_audio_same_origin'
OUT=ROOT/'updates/v4_4_22_whatsapp_audio_blob'
VERSION='4.4.22'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')
assert 'APP_VERSION = "4.4.21"' in app
assert "const VERSION=\\'4.4.21\\';" in app
assert '/static/app.js?v=4.4.21' in html

app=app.replace('APP_VERSION = "4.4.21"','APP_VERSION = "4.4.22"',1)
app=app.replace("const VERSION=\\'4.4.21\\';","const VERSION=\\'4.4.22\\';",1)
html=html.replace('/static/app.js?v=4.4.21','/static/app.js?v=4.4.22',1)

old_cond='''        if message_id and re.fullmatch(r"[A-Za-z0-9._:-]{3,250}", message_id) and re.fullmatch(r"[A-Fa-f0-9]{64,160}", playback_token):'''
new_cond='''        if message_id and len(message_id) <= 500 and re.fullmatch(r"[A-Fa-f0-9]{64,160}", playback_token):'''
if old_cond not in app: raise SystemExit('No encontré condición de message_id v4.4.21')
app=app.replace(old_cond,new_cond,1)

old_target='''            target = (\n                "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio/"\n                + quote(message_id, safe="")\n                + "?token=" + quote(playback_token, safe="")\n            )'''
new_target='''            target = (\n                "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio"\n                + "?message_id=" + quote(message_id, safe="")\n                + "&token=" + quote(playback_token, safe="")\n            )'''
if old_target not in app: raise SystemExit('No encontré target de audio v4.4.21')
app=app.replace(old_target,new_target,1)
app=app.replace('"User-Agent": "Recepcion-Dr-Revelo/4.4.21"','"User-Agent": "Recepcion-Dr-Revelo/4.4.22"',1)

old_audio='''const audioBlock=audio?`<div class="wa-audio-card"><div><b>🎙 Audio del paciente</b><span>${transcript?'Transcripción disponible':'Sin transcripción automática'}</span></div><audio controls preload="metadata" src="/api/whatsapp-responses/${Number(item.id)}/audio" onerror="this.nextElementSibling?.classList.remove('hidden')"></audio><small class="wa-audio-error hidden">No se pudo cargar el audio. Pulsa Actualizar y vuelve a intentarlo.</small></div>`:'';'''
new_audio='''const audioBlock=audio?`<div class="wa-audio-card"><div><b>🎙 Audio del paciente</b><span>${transcript?'Transcripción disponible':'Sin transcripción automática'}</span></div><audio id="waAudioPlayer${Number(item.id)}" controls preload="none"></audio><small id="waAudioStatus${Number(item.id)}" class="wa-audio-error">Cargando audio…</small></div>`:'';'''
if old_audio not in js: raise SystemExit('No encontré bloque audio v4.4.21')
js=js.replace(old_audio,new_audio,1)

marker='''async function resolveWhatsappResponse(id,action){'''
helper='''async function loadWhatsappAudioBlob(id){\n  const audio=$('#waAudioPlayer'+Number(id)),status=$('#waAudioStatus'+Number(id));\n  if(!audio)return;\n  try{\n    const r=await fetch(`/api/whatsapp-responses/${Number(id)}/audio`,{cache:'no-store',headers:{'Accept':'audio/*,*/*;q=0.8'}});\n    if(!r.ok){\n      let detail=`No se pudo cargar el audio (HTTP ${r.status}).`;\n      try{const d=await r.json();if(d?.detail)detail=String(d.detail)}catch{}\n      throw Error(detail);\n    }\n    const bytes=await r.arrayBuffer();\n    if(!bytes.byteLength)throw Error('El servidor devolvió un audio vacío.');\n    let type=String(r.headers.get('content-type')||'audio/ogg').trim();\n    if(type.toLowerCase()==='audio/ogg')type='audio/ogg; codecs=opus';\n    const blob=new Blob([bytes],{type});\n    const old=audio.dataset.blobUrl||'';if(old){try{URL.revokeObjectURL(old)}catch{}}\n    const url=URL.createObjectURL(blob);audio.dataset.blobUrl=url;audio.src=url;audio.load();\n    if(status){status.textContent='Audio listo para reproducir.';status.classList.add('hidden')}\n  }catch(e){\n    if(status){status.textContent=String(e?.message||e||'No se pudo cargar el audio.');status.classList.remove('hidden')}\n  }\n}\n\n'''+marker
if marker not in js: raise SystemExit('No encontré resolveWhatsappResponse')
js=js.replace(marker,helper,1)

old_open='''  $('#modal').classList.remove('hidden');\n}\nasync function loadWhatsappAudioBlob'''
new_open='''  $('#modal').classList.remove('hidden');\n  if(audio)setTimeout(()=>loadWhatsappAudioBlob(Number(item.id)),0);\n}\nasync function loadWhatsappAudioBlob'''
if old_open not in js: raise SystemExit('No encontré cierre del modal de respuesta')
js=js.replace(old_open,new_open,1)

manifest={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
 'copy':['app.py','static/app.js','static/index.html','update_manifest.json']}

if OUT.exists():shutil.rmtree(OUT)
write(OUT/'app.py',app);write(OUT/'static/app.js',js);write(OUT/'static/index.html',html)
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_22_whatsapp_audio_blob'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel;files.append({'path':rel,'url':f'{base}/{rel}','sha256':sha(p),'encoding':'utf-8'})
channel={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'mandatory':True,'channel':'files-v3',
 'message':'v4.4.22: reproducción de audios WhatsApp más robusta. Acepta IDs reales de Meta, solicita el audio con URL codificada y lo carga como Blob local en WebView2; si falla, muestra el error real.',
 'files':files}
write(ROOT/'build/v4422_whatsapp_audio_blob/candidate_latest.json',json.dumps(channel,ensure_ascii=False,indent=2)+'\n')

assert 'APP_VERSION = "4.4.22"' in app
assert '?message_id=' in app
assert 'len(message_id) <= 500' in app
assert 'loadWhatsappAudioBlob' in js
assert "audio/ogg; codecs=opus" in js
assert 'Cargando audio…' in js
assert '/static/app.js?v=4.4.22' in html
print('V4422_BUILD_OK')
