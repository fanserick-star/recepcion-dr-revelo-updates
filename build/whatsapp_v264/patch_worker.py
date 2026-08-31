from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8-sig')
if 'worker_version:"2.6.3"' not in s:
    raise SystemExit('La fuente base no es Worker v2.6.3')

# Token aleatorio por audio. Solo se guarda en raw_payload; nunca guardamos bytes de audio en Neon.
old='''    await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation,confidence,target,applyResult,resolved,resolution,rawPayload:{message,audio_error:audioError,intent_reason:intent.reason,template_name:origin?.templateName||"recordatorio_cita"}});'''
new='''    const playbackToken=type==="audio" ? (crypto.randomUUID().replaceAll("-","")+crypto.randomUUID().replaceAll("-","")) : "";
    await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation,confidence,target,applyResult,resolved,resolution,rawPayload:{message,audio_error:audioError,intent_reason:intent.reason,template_name:origin?.templateName||"recordatorio_cita",playback_token:playbackToken}});'''
if old not in s:
    raise SystemExit('No encontré guardado de respuesta entrante')
s=s.replace(old,new,1)

# Proxy autenticado por token de alta entropía. Meta sigue siendo el origen; Cloudflare no persiste el audio.
anchor='''async function verifyWebhook(request,env){'''
proxy=r'''async function serveInboundAudio(request,env,u){
  if(request.method!=="GET")return text("Method not allowed",405);
  const messageId=decodeURIComponent(String(u.pathname||"").slice("/media/audio/".length));
  const token=String(u.searchParams.get("token")||"").trim();
  if(!messageId||messageId.length>250||!/^[A-Za-z0-9._:-]+$/.test(messageId))return text("Not found",404);
  if(!/^[a-f0-9]{64,160}$/i.test(token))return text("Forbidden",403);
  if(!env.DATABASE_URL||!env.WHATSAPP_ACCESS_TOKEN)return text("Audio service unavailable",503);
  let row=null;
  try{
    row=await withClient(env,async client=>{
      const r=await client.query(`SELECT media_id,media_mime_type,raw_payload->>'playback_token' playback_token
        FROM whatsapp_cloud.inbound_responses
        WHERE message_id=$1 AND message_type='audio' AND received_at > now()-interval '7 days'
        LIMIT 1`,[messageId]);
      return r.rows?.[0]||null;
    });
  }catch(e){console.error("whatsapp_audio_proxy_lookup_failed",e);return text("Audio service unavailable",503);}
  const expected=String(row?.playback_token||"");
  if(!expected||expected.length!==token.length||expected!==token)return text("Forbidden",403);
  const mediaId=String(row?.media_id||"").trim();
  if(!mediaId)return text("Audio unavailable",404);
  try{
    const graph=String(env.GRAPH_VERSION||"v26.0").replace(/^\//,"");
    const auth={Authorization:`Bearer ${env.WHATSAPP_ACCESS_TOKEN}`};
    const metaResp=await fetch(`https://graph.facebook.com/${graph}/${encodeURIComponent(mediaId)}`,{headers:auth});
    if(!metaResp.ok)return text("Audio unavailable",502);
    const meta=await metaResp.json();
    const mediaUrl=String(meta?.url||"");
    if(!mediaUrl.startsWith("https://"))return text("Audio unavailable",502);
    const headers={...auth};
    const range=String(request.headers.get("range")||"").trim();
    if(range)headers.Range=range;
    const mediaResp=await fetch(mediaUrl,{headers});
    if(!mediaResp.ok && mediaResp.status!==206)return text("Audio unavailable",502);
    const outHeaders=new Headers();
    outHeaders.set("content-type",String(mediaResp.headers.get("content-type")||row?.media_mime_type||"audio/ogg").split(";",1)[0]);
    outHeaders.set("cache-control","private, no-store, max-age=0");
    outHeaders.set("accept-ranges",mediaResp.headers.get("accept-ranges")||"bytes");
    for(const h of ["content-range","content-length","etag","last-modified"]){const v=mediaResp.headers.get(h);if(v)outHeaders.set(h,v);}
    outHeaders.set("x-content-type-options","nosniff");
    return new Response(mediaResp.body,{status:mediaResp.status,headers:outHeaders});
  }catch(e){console.error("whatsapp_audio_proxy_fetch_failed",e);return text("Audio unavailable",502);}
}
'''
if anchor not in s:
    raise SystemExit('No encontré verifyWebhook')
s=s.replace(anchor,proxy+anchor,1)

old_route='''async fetch(request,env){const u=new URL(request.url);if(u.pathname==="/header.jpg")'''
new_route='''async fetch(request,env){const u=new URL(request.url);if(u.pathname.startsWith("/media/audio/"))return serveInboundAudio(request,env,u);if(u.pathname==="/header.jpg")'''
if old_route not in s:
    raise SystemExit('No encontré router principal')
s=s.replace(old_route,new_route,1)

# Release/health.
s=s.replace('2.6.3','2.6.4')
old_health='''inbound_target:"origin_fallback",automation:'''
new_health='''inbound_target:"origin_fallback",audio_proxy:"tokenized_cloudflare",automation:'''
if old_health not in s:
    raise SystemExit('No encontré health v2.6.3')
s=s.replace(old_health,new_health,1)

for marker in [
    'worker_version:"2.6.4"',
    'audio_proxy:"tokenized_cloudflare"',
    'playback_token:playbackToken',
    'async function serveInboundAudio',
    'raw_payload->>\'playback_token\'',
    'u.pathname.startsWith("/media/audio/")',
    'received_at > now()-interval \'7 days\''
]:
    if marker not in s:
        raise SystemExit(f'Falta marcador v2.6.4: {marker}')

p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V264_AUDIO_PROXY_OK')
