from __future__ import annotations
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "cloudflare/whatsapp_worker_v2_5_reglas_y_pruebas.js"
OUT = ROOT / "cloudflare/whatsapp_worker_v2_6_responses.js"

s = SRC.read_text(encoding="utf-8-sig")
assert 'worker_version:"2.5.2"' in s
assert 'async function receiveWebhook(request,env)' in s
assert 'async function withClient(env,fn)' in s

anchor = 'async function withClient(env,fn){ const c=new Client(env.DATABASE_URL); try{await c.connect(); return await fn(c);} finally{try{await c.end();}catch{}} }'
assert anchor in s

helpers = r'''

// v2.6.0 — respuestas libres de pacientes (texto + audio) con revisión humana.
let inboundSchemaReady=false;
function normalizeIntentText(value){
  return String(value||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9ñ]+/g," ").replace(/\s+/g," ").trim();
}
function hasAny(textValue,phrases){return phrases.some(p=>textValue.includes(p));}
function classifyInboundText(value){
  const t=normalizeIntentText(value);
  if(!t)return {interpretation:"REVISAR",confidence:0,reason:"sin_texto"};
  const reschedule=["quiero reagendar","quisiera reagendar","necesito reagendar","reagendar la cita","reprogramar la cita","quiero reprogramar","quisiera reprogramar","cambiarme la cita","cambiar la cita para","cambiar el dia","cambiar la hora","cambiarme el dia","cambiarme la hora","otra fecha","otro dia","otra hora","pasar la cita","mover la cita","puede cambiarme","podria cambiarme","deseo cambiar la cita"];
  if(hasAny(t,reschedule))return {interpretation:"NO_ASISTIRA",confidence:99,reason:"solicita_reagendar"};
  const uncertain=["no se si","tal vez","quizas","quiza","puede que","depende de","aun no se","todavia no se","no estoy seguro","no estoy segura","creo que podria","probablemente"];
  const negative=["no puedo","no podre","no voy a poder","no voy","no asistire","no voy a asistir","no llegare","no me es posible","no me sera posible","cancele","cancelar la cita","cancelemela","no cuente conmigo"];
  const positive=["confirmo","confirmado","ahi estare","alli estare","voy a ir","voy a asistir","asistire","si puedo","puedo asistir","si voy","si asistire","cuente conmigo","nos vemos alla","nos vemos ahi"];
  const words=new Set(t.split(" ").filter(Boolean));
  const pos=hasAny(t,positive)||words.has("si");
  const neg=hasAny(t,negative)||t==="no"||t.startsWith("no gracias");
  if(hasAny(t,uncertain))return {interpretation:"REVISAR",confidence:25,reason:"incertidumbre"};
  if(pos&&neg)return {interpretation:"REVISAR",confidence:20,reason:"contradictorio"};
  if(neg)return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};
  if(pos)return {interpretation:"CONFIRMADO",confidence:97,reason:"confirmacion_clara"};
  return {interpretation:"REVISAR",confidence:10,reason:"sin_intencion_clara"};
}
async function ensureInboundSchema(client){
  if(inboundSchemaReady)return true;
  try{
    await client.query(`CREATE SCHEMA IF NOT EXISTS whatsapp_cloud`);
    await client.query(`CREATE TABLE IF NOT EXISTS whatsapp_cloud.inbound_responses(
      id bigserial PRIMARY KEY,
      message_id text NOT NULL UNIQUE,
      phone text NOT NULL,
      message_type text NOT NULL,
      raw_text text,
      transcription text,
      media_id text,
      media_mime_type text,
      interpretation text NOT NULL DEFAULT 'REVISAR',
      confidence integer NOT NULL DEFAULT 0,
      source_type text,
      source_id bigint,
      appointment_date date,
      appointment_time time,
      patient_name text,
      match_method text,
      apply_result text,
      received_at timestamptz NOT NULL DEFAULT now(),
      resolved_at timestamptz,
      resolved_by text,
      resolution text,
      raw_payload jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )`);
    await client.query(`CREATE INDEX IF NOT EXISTS inbound_responses_review_idx ON whatsapp_cloud.inbound_responses(received_at DESC) WHERE resolved_at IS NULL AND interpretation='REVISAR'`);
    await client.query(`CREATE INDEX IF NOT EXISTS inbound_responses_phone_idx ON whatsapp_cloud.inbound_responses(phone,received_at DESC)`);
    inboundSchemaReady=true;return true;
  }catch(e){console.error("whatsapp_inbound_schema_failed",e);return false;}
}
async function findInboundTarget(client,message,phone){
  const contextId=String(message?.context?.id||"").trim();
  if(contextId){
    const r=await client.query(`SELECT source_type,source_id,appointment_date::text appointment_date,appointment_time::text appointment_time,patient_name,phone
      FROM whatsapp_cloud.events WHERE message_id=$1 AND template_name='recordatorio_cita' ORDER BY updated_at DESC LIMIT 1`,[contextId]);
    if(r.rows?.length){const x=r.rows[0];return {sourceType:String(x.source_type||""),sourceId:Number(x.source_id||0),date:String(x.appointment_date||"").slice(0,10),time:String(x.appointment_time||"").slice(0,5),patientName:String(x.patient_name||""),matchMethod:"contexto_mensaje"};}
  }
  const normalized=normalizePhone(phone);
  if(!normalized)return null;
  const r=await client.query(`SELECT source_type,source_id,appointment_date::text appointment_date,appointment_time::text appointment_time,patient_name,updated_at
    FROM whatsapp_cloud.events
    WHERE regexp_replace(coalesce(phone,''),'\\D','','g')=$1
      AND template_name='recordatorio_cita'
      AND status IN ('SENT','DELIVERED','READ')
      AND appointment_date >= ((now() AT TIME ZONE 'America/Guayaquil')::date - 1)
      AND updated_at > now()-interval '7 days'
    ORDER BY sent_at DESC NULLS LAST,updated_at DESC LIMIT 2`,[normalized]);
  if(!r.rows?.length)return null;
  const a=r.rows[0],b=r.rows[1];
  if(b && (String(a.source_type)!==String(b.source_type)||Number(a.source_id)!==Number(b.source_id)||String(a.appointment_date).slice(0,10)!==String(b.appointment_date).slice(0,10)||String(a.appointment_time).slice(0,5)!==String(b.appointment_time).slice(0,5)))return null;
  return {sourceType:String(a.source_type||""),sourceId:Number(a.source_id||0),date:String(a.appointment_date||"").slice(0,10),time:String(a.appointment_time||"").slice(0,5),patientName:String(a.patient_name||""),matchMethod:"ultimo_recordatorio"};
}
async function applyFreeformResponse(client,target,action,messageId,phone){
  if(!target||!["appointment","staged"].includes(target.sourceType)||!Number.isInteger(target.sourceId)||target.sourceId<=0)return "NOT_FOUND";
  const q=target.sourceType==="staged"?`SELECT fecha::text d,hora::text t FROM public.confirmafy_agenda_items WHERE id=$1`:`SELECT fecha::text d,hora::text t FROM public.appointments WHERE id=$1`;
  const slot=await client.query(q,[target.sourceId]);if(!slot.rows?.length)return "NOT_FOUND";
  const d=String(slot.rows[0].d||"").slice(0,10),t=String(slot.rows[0].t||"").slice(0,5);
  if(d!==target.date||t!==target.time)return "STALE";
  const r=await client.query(`SELECT public.whatsapp_apply_response($1,$2,$3,$4,$5) AS result`,[action,target.sourceType,target.sourceId,String(messageId||""),String(phone||"")]);
  return String(r.rows?.[0]?.result||"UNKNOWN");
}
function arrayBufferToBase64(buffer){
  const bytes=new Uint8Array(buffer);let binary="";const chunk=0x4000;
  for(let i=0;i<bytes.length;i+=chunk)binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+chunk,bytes.length)));
  return btoa(binary);
}
async function fetchWhatsAppAudio(message,env){
  const mediaId=String(message?.audio?.id||"").trim();if(!mediaId)return {mediaId:"",mimeType:"",buffer:null};
  const graph=String(env.GRAPH_VERSION||"v26.0").replace(/^\//,"");
  const auth={Authorization:`Bearer ${env.WHATSAPP_ACCESS_TOKEN}`};
  const metaResp=await fetch(`https://graph.facebook.com/${graph}/${encodeURIComponent(mediaId)}`,{headers:auth});
  if(!metaResp.ok)throw new Error(`media_meta_${metaResp.status}`);
  const meta=await metaResp.json();const url=String(meta?.url||"");if(!url.startsWith("https://"))throw new Error("media_url_missing");
  const mediaResp=await fetch(url,{headers:auth});if(!mediaResp.ok)throw new Error(`media_download_${mediaResp.status}`);
  const declared=Number(mediaResp.headers.get("content-length")||0);if(declared>8*1024*1024)throw new Error("audio_too_large");
  const buffer=await mediaResp.arrayBuffer();if(buffer.byteLength>8*1024*1024)throw new Error("audio_too_large");
  return {mediaId,mimeType:String(message?.audio?.mime_type||mediaResp.headers.get("content-type")||"audio/ogg").split(";",1)[0],buffer};
}
async function transcribeWhatsAppAudio(message,env){
  const media=await fetchWhatsAppAudio(message,env);
  if(!media.buffer||!env.AI)return {...media,text:"",error:env.AI?"audio_vacio":"ai_binding_missing"};
  try{
    const out=await env.AI.run("@cf/openai/whisper-large-v3-turbo",{audio:arrayBufferToBase64(media.buffer),task:"transcribe",language:"es",vad_filter:true,condition_on_previous_text:false,initial_prompt:"Cita médica del consultorio del Dr. Armando Revelo. El paciente responde si asistirá, no asistirá o desea cambiar su cita."});
    return {...media,text:String(out?.text||"").trim(),error:""};
  }catch(e){console.error("whatsapp_audio_transcription_failed",e);return {...media,text:"",error:String(e?.message||e).slice(0,160)};}
}
async function saveInboundRow(client,data){
  const rawPayload=JSON.stringify(data.rawPayload||{});
  const r=await client.query(`INSERT INTO whatsapp_cloud.inbound_responses(
    message_id,phone,message_type,raw_text,transcription,media_id,media_mime_type,interpretation,confidence,
    source_type,source_id,appointment_date,appointment_time,patient_name,match_method,apply_result,resolved_at,resolved_by,resolution,raw_payload,updated_at)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::date,$13::time,$14,$15,$16,$17,$18,$19,$20::jsonb,now())
    ON CONFLICT(message_id) DO UPDATE SET updated_at=now()
    RETURNING id`,[
      data.messageId,data.phone,data.messageType,data.rawText||null,data.transcription||null,data.mediaId||null,data.mediaMimeType||null,
      data.interpretation||"REVISAR",Number(data.confidence||0),data.target?.sourceType||null,data.target?.sourceId||null,data.target?.date||null,data.target?.time||null,
      data.target?.patientName||null,data.target?.matchMethod||null,data.applyResult||null,data.resolved?new Date().toISOString():null,data.resolved?"worker":null,data.resolution||null,rawPayload
    ]);
  return Number(r.rows?.[0]?.id||0);
}
async function handleFreeformInbound(env,message){
  const messageId=String(message?.id||"").trim(),phone=normalizePhone(message?.from||"");if(!messageId||!phone)return;
  const type=String(message?.type||"").toLowerCase();if(!["text","audio"].includes(type))return;
  let rawText=type==="text"?String(message?.text?.body||"").trim():"",transcription="",mediaId="",mediaMimeType="",audioError="";
  if(type==="audio"){
    try{const a=await transcribeWhatsAppAudio(message,env);transcription=a.text||"";mediaId=a.mediaId||String(message?.audio?.id||"");mediaMimeType=a.mimeType||String(message?.audio?.mime_type||"");audioError=a.error||"";}
    catch(e){mediaId=String(message?.audio?.id||"");mediaMimeType=String(message?.audio?.mime_type||"");audioError=String(e?.message||e).slice(0,160);console.error("whatsapp_audio_fetch_failed",e);}
  }
  const intent=classifyInboundText(type==="audio"?transcription:rawText);
  let ackAction="";
  await withClient(env,async client=>{
    if(!(await ensureInboundSchema(client)))return;
    const target=await findInboundTarget(client,message,phone);
    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;
    if(!target && interpretation!=="REVISAR"){interpretation="REVISAR";confidence=Math.min(confidence,35);}
    if(target && interpretation!=="REVISAR"){
      const action=interpretation==="CONFIRMADO"?"CONFIRMAR":"CANCELAR";
      applyResult=await applyFreeformResponse(client,target,action,messageId,phone);
      if(responseWasApplied(applyResult)){resolved=true;resolution=action;ackAction=action;}
      else{interpretation="REVISAR";confidence=Math.min(confidence,30);ackAction="";}
    }
    await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation,confidence,target,applyResult,resolved,resolution,rawPayload:{message,audio_error:audioError,intent_reason:intent.reason}});
  });
  if(ackAction){const ack=acknowledgementText(ackAction,env);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_freeform_ack_failed",e);}}}
}
async function logButtonInbound(env,message,p,result){
  if(!p||p.action.startsWith("TEST_"))return;
  try{await withClient(env,async client=>{
    if(!(await ensureInboundSchema(client)))return;
    let target=await findInboundTarget(client,message,message?.from||"");
    if(!target)target={sourceType:p.sourceType,sourceId:p.sourceId,date:p.date,time:p.time,patientName:"",matchMethod:"boton_payload"};
    const confirmed=p.action==="CONFIRMAR",applied=responseWasApplied(result);
    await saveInboundRow(client,{messageId:String(message?.id||`button:${Date.now()}`),phone:normalizePhone(message?.from||""),messageType:"button",rawText:confirmed?"Sí":"No",transcription:"",mediaId:"",mediaMimeType:"",interpretation:applied?(confirmed?"CONFIRMADO":"NO_ASISTIRA"):"REVISAR",confidence:100,target,applyResult:result,resolved:applied,resolution:applied?p.action:"",rawPayload:{message}});
  });}catch(e){console.error("whatsapp_button_log_failed",e);}
}
'''

s = s.replace(anchor, anchor + helpers, 1)

old_receive = re.search(r'async function receiveWebhook\(request,env\)\{.*?return text\("EVENT_RECEIVED",200\);\}', s, flags=re.S)
assert old_receive, "receiveWebhook no encontrado"
new_receive = r'''async function receiveWebhook(request,env){
  const raw=await request.arrayBuffer();
  if(!(await validMetaSignature(raw,request.headers.get("x-hub-signature-256")||"",env.META_APP_SECRET)))return text("Invalid signature",401);
  let body;try{body=JSON.parse(decoder.decode(raw));}catch{return text("Invalid JSON",400);}
  const messages=[],statuses=[];
  for(const e of body?.entry||[])for(const ch of e?.changes||[]){for(const m of ch?.value?.messages||[])messages.push(m);for(const st of ch?.value?.statuses||[])statuses.push(st);}
  if(statuses.length)await updateStatuses(env,statuses);
  for(const m of messages){
    const p=parseActionPayload(extractPayload(m));
    if(p){
      const messageId=String(m.id||""),phone=String(m.from||"");let result="UNKNOWN";
      try{result=await applyResponse(env,p,messageId,phone);}catch(e){console.error("whatsapp_apply_response_failed",e);continue;}
      if(responseWasApplied(result)){
        const ackAction=result==="TEST_CONFIRMED"?"TEST_CONFIRMAR":result==="TEST_CANCELLED"?"TEST_CANCELAR":p.action;
        const ack=acknowledgementText(ackAction,env);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_ack_failed",e);}}
      }
      await logButtonInbound(env,m,p,result);
      continue;
    }
    if(m?.type==="text"||m?.type==="audio"){
      try{await handleFreeformInbound(env,m);}catch(e){console.error("whatsapp_freeform_failed",e);}
    }
  }
  return text("EVENT_RECEIVED",200);
}'''
s = s[:old_receive.start()] + new_receive + s[old_receive.end():]

s = s.replace('Dr-Revelo-WhatsApp-Worker/2.5.2', 'Dr-Revelo-WhatsApp-Worker/2.6.0')
s = s.replace('worker_version:"2.5.2"', 'worker_version:"2.6.0"')
old_export = 'export { runScheduler,parseActionPayload,extractPayload,validMetaSignature,recordatorioDateTimeLabel,normalizePhone,acknowledgementText,responseWasApplied,sendTextMeta,testTemplateFromHash,materializeCandidate,buildTemplatePayload };'
new_export = 'export { runScheduler,parseActionPayload,extractPayload,validMetaSignature,recordatorioDateTimeLabel,normalizePhone,acknowledgementText,responseWasApplied,sendTextMeta,testTemplateFromHash,materializeCandidate,buildTemplatePayload,classifyInboundText,normalizeIntentText,arrayBufferToBase64 };'
assert old_export in s
s = s.replace(old_export,new_export,1)

assert 'worker_version:"2.6.0"' in s
assert 'whatsapp_cloud.inbound_responses' in s
assert 'solicita_reagendar' in s
assert '@cf/openai/whisper-large-v3-turbo' in s
assert 'if(m?.type==="text"||m?.type==="audio")' in s
assert 'classifyInboundText' in s
OUT.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V26_BUILD_OK')
