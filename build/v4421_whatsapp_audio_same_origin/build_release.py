from __future__ import annotations
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_20_whatsapp_audio_proxy'
OUT=ROOT/'updates/v4_4_21_whatsapp_audio_same_origin'
VERSION='4.4.21'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')
assert 'APP_VERSION = "4.4.20"' in app
assert "const VERSION=\\'4.4.20\\';" in app
assert '/static/app.js?v=4.4.20' in html

app=app.replace('APP_VERSION = "4.4.20"','APP_VERSION = "4.4.21"',1)
app=app.replace("const VERSION=\\'4.4.20\\';","const VERSION=\\'4.4.21\\';",1)
html=html.replace('/static/app.js?v=4.4.20','/static/app.js?v=4.4.21',1)

old_sig='def whatsapp_response_audio(response_id: int, user: User = Depends(current_user)):'
new_sig='def whatsapp_response_audio(response_id: int, request: Request, user: User = Depends(current_user)):'
if old_sig not in app: raise SystemExit('No encontré firma del endpoint de audio v4.4.20')
app=app.replace(old_sig,new_sig,1)

old='''        if message_id and re.fullmatch(r"[A-Za-z0-9._:-]{3,250}", message_id) and re.fullmatch(r"[A-Fa-f0-9]{64,160}", playback_token):\n            target = (\n                "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio/"\n                + quote(message_id, safe="")\n                + "?token=" + quote(playback_token, safe="")\n            )\n            return Response(status_code=307, headers={\n                "Location": target,\n                "Cache-Control": "private, no-store, max-age=0",\n            })'''
new='''        if message_id and re.fullmatch(r"[A-Za-z0-9._:-]{3,250}", message_id) and re.fullmatch(r"[A-Fa-f0-9]{64,160}", playback_token):\n            target = (\n                "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio/"\n                + quote(message_id, safe="")\n                + "?token=" + quote(playback_token, safe="")\n            )\n            # v4.4.21: WebView2 ya no sigue un redirect cross-origin.\n            # FastAPI obtiene el audio protegido desde Cloudflare y lo entrega\n            # al reproductor como recurso local. También reenvía Range para\n            # permitir play/seek correctamente sin cargar más de lo necesario.\n            proxy_headers = {\n                "User-Agent": "Recepcion-Dr-Revelo/4.4.21",\n                "Accept": "audio/*,*/*;q=0.8",\n                "Cache-Control": "no-cache",\n            }\n            range_header = str(request.headers.get("range") or "").strip()\n            if range_header and re.fullmatch(r"bytes=\\d*-\\d*", range_header):\n                proxy_headers["Range"] = range_header\n            proxy_req = urllib.request.Request(target, headers=proxy_headers)\n            try:\n                with urllib.request.urlopen(proxy_req, timeout=20) as resp:\n                    status_code = int(getattr(resp, "status", 200) or 200)\n                    content_type = str(resp.headers.get("content-type") or row.get("media_mime_type") or "audio/ogg").strip()\n                    data = resp.read(20 * 1024 * 1024 + 1)\n                    response_headers = {\n                        "Cache-Control": "private, no-store, max-age=0",\n                        "Accept-Ranges": str(resp.headers.get("accept-ranges") or "bytes"),\n                    }\n                    content_range = str(resp.headers.get("content-range") or "").strip()\n                    if content_range:\n                        response_headers["Content-Range"] = content_range\n                if len(data) > 20 * 1024 * 1024:\n                    raise HTTPException(413, "El audio es demasiado grande para reproducirlo aquí")\n                return Response(content=data, status_code=status_code, media_type=content_type, headers=response_headers)\n            except urllib.error.HTTPError as exc:\n                raise HTTPException(502, f"Cloudflare no pudo entregar el audio ({exc.code})")'''
if old not in app: raise SystemExit('No encontré redirect Cloudflare v4.4.20')
app=app.replace(old,new,1)

# Mensaje visible si el navegador reporta un error de codec/red. No cambia la lógica.
old_audio='''<audio controls preload="none" src="/api/whatsapp-responses/${Number(item.id)}/audio"></audio>'''
new_audio='''<audio controls preload="metadata" src="/api/whatsapp-responses/${Number(item.id)}/audio" onerror="this.nextElementSibling?.classList.remove('hidden')"></audio><small class="wa-audio-error hidden">No se pudo cargar el audio. Pulsa Actualizar y vuelve a intentarlo.</small>'''
if old_audio not in js: raise SystemExit('No encontré reproductor de audio esperado')
js=js.replace(old_audio,new_audio,1)

manifest={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
 'copy':['app.py','static/app.js','static/index.html','update_manifest.json']}

if OUT.exists():shutil.rmtree(OUT)
write(OUT/'app.py',app);write(OUT/'static/app.js',js);write(OUT/'static/index.html',html)
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_21_whatsapp_audio_same_origin'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel;files.append({'path':rel,'url':f'{base}/{rel}','sha256':sha(p),'encoding':'utf-8'})
channel={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'mandatory':True,'channel':'files-v3',
 'message':'v4.4.21: corrige la reproducción de audios WhatsApp en WebView2 eliminando el redirect externo. Recepción entrega el audio desde el mismo origen y soporta Range para reproducción y avance.',
 'files':files}
write(ROOT/'build/v4421_whatsapp_audio_same_origin/candidate_latest.json',json.dumps(channel,ensure_ascii=False,indent=2)+'\n')

assert 'APP_VERSION = "4.4.21"' in app
assert 'def whatsapp_response_audio(response_id: int, request: Request' in app
assert 'WebView2 ya no sigue un redirect cross-origin' in app
assert 'proxy_headers["Range"] = range_header' in app
assert 'return Response(content=data, status_code=status_code, media_type=content_type' in app
assert 'status_code=307' not in app[app.index('@app.get("/api/whatsapp-responses/{response_id}/audio")'):app.index('@app.post("/api/whatsapp-responses/{response_id}/resolve")')]
assert 'preload="metadata"' in js
assert '/static/app.js?v=4.4.21' in html
print('V4421_BUILD_OK')
