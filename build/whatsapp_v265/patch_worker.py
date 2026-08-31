from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8-sig')

old='''  const messageId=decodeURIComponent(String(u.pathname||"").slice("/media/audio/".length));\n  const token=String(u.searchParams.get("token")||"").trim();\n  if(!messageId||messageId.length>250||!/^[A-Za-z0-9._:-]+$/.test(messageId))return text("Not found",404);'''
new='''  // v2.6.5: Meta puede usar caracteres de codificación fuera de la regex antigua.\n  // El ID viaja URL-encoded por query y se usa únicamente como parámetro SQL.\n  const messageId=u.pathname==="/media/audio"\n    ? String(u.searchParams.get("message_id")||"")\n    : decodeURIComponent(String(u.pathname||"").slice("/media/audio/".length));\n  const token=String(u.searchParams.get("token")||"").trim();\n  if(!messageId||messageId.length>500)return text("Not found",404);'''
if old not in s:
    raise SystemExit('No encontré validación de messageId v2.6.4')
s=s.replace(old,new,1)

old_route='if(u.pathname.startsWith("/media/audio/"))return serveInboundAudio(request,env,u);'
new_route='if(u.pathname==="/media/audio"||u.pathname.startsWith("/media/audio/"))return serveInboundAudio(request,env,u);'
if old_route not in s:
    raise SystemExit('No encontré ruta media/audio v2.6.4')
s=s.replace(old_route,new_route,1)

if 'worker_version:"2.6.4"' not in s:
    raise SystemExit('No encontré worker_version 2.6.4')
s=s.replace('worker_version:"2.6.4"','worker_version:"2.6.5"',1)
s=s.replace('v2.6.4 — respuestas libres','v2.6.5 — respuestas libres',1)

for marker in [
    'worker_version:"2.6.5"',
    'u.pathname==="/media/audio"',
    'u.searchParams.get("message_id")',
    'messageId.length>500',
    'audio_proxy:"tokenized_cloudflare"',
    'inbound_policy:"recordatorio_cita_only"',
]:
    if marker not in s:
        raise SystemExit(f'Falta marcador: {marker}')

p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V265_MESSAGE_ID_OK')
