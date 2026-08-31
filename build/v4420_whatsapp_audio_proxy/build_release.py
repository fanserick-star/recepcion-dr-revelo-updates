from __future__ import annotations
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_19_whatsapp_test_retention'
OUT=ROOT/'updates/v4_4_20_whatsapp_audio_proxy'
VERSION='4.4.20'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')
assert 'APP_VERSION = "4.4.19"' in app
assert "const VERSION=\\'4.4.19\\';" in app
assert '/static/app.js?v=4.4.19' in html

app=app.replace('APP_VERSION = "4.4.19"','APP_VERSION = "4.4.20"',1)
app=app.replace("const VERSION=\\'4.4.19\\';","const VERSION=\\'4.4.20\\';",1)
html=html.replace('/static/app.js?v=4.4.19','/static/app.js?v=4.4.20',1)
app=app.replace('from urllib.parse import urlparse, urlunparse, unquote','from urllib.parse import urlparse, urlunparse, unquote, quote',1)

old='''@app.get("/api/whatsapp-responses/{response_id}/audio")\ndef whatsapp_response_audio(response_id: int, user: User = Depends(current_user)):\n    if FORCE_OFFLINE or cloud_engine is None:\n        raise HTTPException(503, "Se necesita conexión para escuchar el audio")\n    if not WHATSAPP_ACCESS_TOKEN:\n        raise HTTPException(503, "Falta el token de WhatsApp en esta PC")\n    try:\n        with cloud_engine.connect() as conn:\n            if not _wa_inbound_table_ready(conn):\n                raise HTTPException(404, "Audio no disponible")\n            row = conn.execute(text("""\n                SELECT media_id,media_mime_type FROM whatsapp_cloud.inbound_responses WHERE id=:id\n            """), {"id": int(response_id)}).mappings().first()\n        media_id = str((row or {}).get("media_id") or "").strip()\n        if not media_id or not re.fullmatch(r"[A-Za-z0-9._:-]{3,180}", media_id):\n            raise HTTPException(404, "Esta respuesta no tiene un audio disponible")\n        graph_version = (WHATSAPP_GRAPH_VERSION or "v26.0").strip().lstrip("/")\n        meta_req = urllib.request.Request(\n            f"https://graph.facebook.com/{graph_version}/{media_id}",\n            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": "Recepcion-Dr-Revelo/4.4.18"},\n        )\n        with urllib.request.urlopen(meta_req, timeout=12) as resp:\n            meta = json.loads(resp.read(512000).decode("utf-8"))\n        media_url = str(meta.get("url") or "").strip()\n        if not media_url.startswith("https://"):\n            raise HTTPException(502, "Meta no devolvió la dirección del audio")\n        audio_req = urllib.request.Request(\n            media_url,\n            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": "Recepcion-Dr-Revelo/4.4.18"},\n        )\n        with urllib.request.urlopen(audio_req, timeout=20) as resp:\n            content_type = str(resp.headers.get("content-type") or (row or {}).get("media_mime_type") or "audio/ogg").split(";", 1)[0]\n            data = resp.read(20 * 1024 * 1024 + 1)\n        if len(data) > 20 * 1024 * 1024:\n            raise HTTPException(413, "El audio es demasiado grande para reproducirlo aquí")\n        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=60"})\n    except HTTPException:\n        raise\n    except urllib.error.HTTPError as exc:\n        raise HTTPException(502, f"Meta no permitió descargar el audio ({exc.code})")\n    except Exception as exc:\n        raise HTTPException(502, f"No se pudo abrir el audio: {str(exc)[:160]}")'''

new='''@app.get("/api/whatsapp-responses/{response_id}/audio")\ndef whatsapp_response_audio(response_id: int, user: User = Depends(current_user)):\n    if FORCE_OFFLINE or cloud_engine is None:\n        raise HTTPException(503, "Se necesita conexión para escuchar el audio")\n    try:\n        with cloud_engine.connect() as conn:\n            if not _wa_inbound_table_ready(conn):\n                raise HTTPException(404, "Audio no disponible")\n            row = conn.execute(text("""\n                SELECT message_id,media_id,media_mime_type,raw_payload->>'playback_token' AS playback_token\n                FROM whatsapp_cloud.inbound_responses WHERE id=:id AND message_type='audio'\n            """), {"id": int(response_id)}).mappings().first()\n        if not row:\n            raise HTTPException(404, "Esta respuesta no tiene un audio disponible")\n\n        # v4.4.20: los audios nuevos se reproducen por el Worker de Cloudflare.\n        # La PC nunca necesita conocer el token de Meta y el audio no se guarda en Neon.\n        message_id = str(row.get("message_id") or "").strip()\n        playback_token = str(row.get("playback_token") or "").strip()\n        if message_id and re.fullmatch(r"[A-Za-z0-9._:-]{3,250}", message_id) and re.fullmatch(r"[A-Fa-f0-9]{64,160}", playback_token):\n            target = (\n                "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio/"\n                + quote(message_id, safe="")\n                + "?token=" + quote(playback_token, safe="")\n            )\n            return Response(status_code=307, headers={\n                "Location": target,\n                "Cache-Control": "private, no-store, max-age=0",\n            })\n\n        # Compatibilidad con audios previos a v2.6.4: si la PC conserva un token\n        # válido, mantenemos el método antiguo. Si no, pedimos una nueva prueba.\n        if not WHATSAPP_ACCESS_TOKEN:\n            raise HTTPException(409, "Este audio fue recibido antes de la mejora de reproducción. Envía una nueva prueba de audio.")\n        media_id = str(row.get("media_id") or "").strip()\n        if not media_id or not re.fullmatch(r"[A-Za-z0-9._:-]{3,180}", media_id):\n            raise HTTPException(404, "Esta respuesta no tiene un audio disponible")\n        graph_version = (WHATSAPP_GRAPH_VERSION or "v26.0").strip().lstrip("/")\n        meta_req = urllib.request.Request(\n            f"https://graph.facebook.com/{graph_version}/{media_id}",\n            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": "Recepcion-Dr-Revelo/4.4.20"},\n        )\n        with urllib.request.urlopen(meta_req, timeout=12) as resp:\n            meta = json.loads(resp.read(512000).decode("utf-8"))\n        media_url = str(meta.get("url") or "").strip()\n        if not media_url.startswith("https://"):\n            raise HTTPException(502, "Meta no devolvió la dirección del audio")\n        audio_req = urllib.request.Request(media_url, headers={\n            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",\n            "User-Agent": "Recepcion-Dr-Revelo/4.4.20",\n        })\n        with urllib.request.urlopen(audio_req, timeout=20) as resp:\n            content_type = str(resp.headers.get("content-type") or row.get("media_mime_type") or "audio/ogg").split(";", 1)[0]\n            data = resp.read(20 * 1024 * 1024 + 1)\n        if len(data) > 20 * 1024 * 1024:\n            raise HTTPException(413, "El audio es demasiado grande para reproducirlo aquí")\n        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, no-store, max-age=0"})\n    except HTTPException:\n        raise\n    except urllib.error.HTTPError as exc:\n        raise HTTPException(502, f"Meta no permitió descargar el audio ({exc.code})")\n    except Exception as exc:\n        raise HTTPException(502, f"No se pudo abrir el audio: {str(exc)[:160]}")'''

if old not in app:
    raise SystemExit('No encontré endpoint de audio v4.4.19')
app=app.replace(old,new,1)

manifest={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
 'copy':['app.py','static/app.js','static/index.html','update_manifest.json']}

if OUT.exists():shutil.rmtree(OUT)
write(OUT/'app.py',app);write(OUT/'static/app.js',js);write(OUT/'static/index.html',html)
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_20_whatsapp_audio_proxy'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel;files.append({'path':rel,'url':f'{base}/{rel}','sha256':sha(p),'encoding':'utf-8'})
channel={
 'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
 'mandatory':True,'channel':'files-v3',
 'message':'v4.4.20: corrige la reproducción de audios de respuestas WhatsApp. Los audios nuevos se sirven de forma temporal y protegida mediante Cloudflare, sin depender del token de Meta en la PC y sin guardar el archivo de audio en Neon.',
 'files':files}
write(ROOT/'build/v4420_whatsapp_audio_proxy/candidate_latest.json',json.dumps(channel,ensure_ascii=False,indent=2)+'\n')

assert 'APP_VERSION = "4.4.20"' in app
assert "raw_payload->>'playback_token'" in app
assert 'dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio/' in app
assert 'Response(status_code=307' in app
assert '/static/app.js?v=4.4.20' in html
assert 'data-section="whatsappRespuestas"' in html
assert 'resolveWhatsappResponse' in js
print('V4420_BUILD_OK')
