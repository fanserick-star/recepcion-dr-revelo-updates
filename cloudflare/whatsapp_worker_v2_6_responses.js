import { Client } from "@neondatabase/serverless";

const encoder = new TextEncoder();
const decoder = new TextDecoder();
const WEEKDAYS = ["domingo","lunes","martes","miércoles","jueves","viernes","sábado"];
const MONTHS = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
const CLOUD_TEST_PREFIX = "mobile:whatsapp-cloud-test:";
const CLOUD_TEST_TEMPLATES = new Set(["cita_agendada","recordatorio_cita","recordatorio_hoy"]);

function testTemplateFromHash(value){
  const raw=String(value||"");
  if(!raw.startsWith(CLOUD_TEST_PREFIX)) return "";
  const first=raw.slice(CLOUD_TEST_PREFIX.length).split(":",1)[0];
  return CLOUD_TEST_TEMPLATES.has(first) ? first : "recordatorio_cita";
}
const DEFAULT_HEADER_IMAGE_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/assets/whatsapp/recordatorios_de_citas_header.jpg";

function text(body, status = 200) {
  return new Response(String(body ?? ""), { status, headers: {"content-type":"text/plain; charset=utf-8","cache-control":"no-store"} });
}
function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: {"content-type":"application/json; charset=utf-8","cache-control":"no-store"} });
}
function enabled(v) { return String(v ?? "0").trim() === "1"; }
function pad(n){ return String(n).padStart(2,"0"); }
function normalizePhone(v){
  let d=String(v??"").replace(/\D/g,"");
  if(d.startsWith("00")) d=d.slice(2);
  if(d.startsWith("0") && d.length===10) d="593"+d.slice(1);
  return d;
}
function dateParts(iso){ const [y,m,d]=String(iso).slice(0,10).split("-").map(Number); return {y,m,d}; }
function timeParts(t){ const [h,m]=String(t).slice(0,5).split(":").map(Number); return {h,m}; }
function dateLabel(iso){ const {y,m,d}=dateParts(iso); const wd=new Date(Date.UTC(y,m-1,d,12)).getUTCDay(); return `${WEEKDAYS[wd]} ${d} de ${MONTHS[m-1]} de ${y}`; }
function timeLabel(t){ const {h,m}=timeParts(t); return `${h%12||12}:${pad(m)} ${h>=12?"PM":"AM"}`; }
function recordatorioDateTimeLabel(iso,t){ const dp=dateParts(iso),tp=timeParts(t); const wd=new Date(Date.UTC(dp.y,dp.m-1,dp.d,12)).getUTCDay(); return `${WEEKDAYS[wd]}, ${dp.d} de ${MONTHS[dp.m-1]} de ${dp.y} a las ${tp.h%12||12}:${pad(tp.m)} ${tp.h>=12?"p. m.":"a. m."}`; }
async function sha256(s){ const b=await crypto.subtle.digest("SHA-256",encoder.encode(String(s))); return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,"0")).join(""); }
function hexToBytes(hex){ if(!/^[0-9a-f]+$/i.test(hex)||hex.length%2)return null; const out=new Uint8Array(hex.length/2); for(let i=0;i<out.length;i++)out[i]=parseInt(hex.slice(i*2,i*2+2),16); return out; }
async function validMetaSignature(rawBody,header,appSecret){ if(!appSecret||!header?.startsWith("sha256="))return false; const sig=hexToBytes(header.slice(7)); if(!sig)return false; const key=await crypto.subtle.importKey("raw",encoder.encode(appSecret),{name:"HMAC",hash:"SHA-256"},false,["verify"]); return crypto.subtle.verify("HMAC",key,sig,rawBody); }

function buildTemplatePayload(c, env){
  const components=[];
  if(c.header_image_url) components.push({type:"header",parameters:[{type:"image",image:{link:c.header_image_url}}]});
  else if(c.header_image_id) components.push({type:"header",parameters:[{type:"image",image:{id:c.header_image_id}}]});
  if(c.body_params?.length) components.push({type:"body",parameters:c.body_params.map(x=>({type:"text",text:String(x)}))});
  (c.buttons||[]).forEach((payload,index)=>components.push({type:"button",sub_type:"quick_reply",index:String(index),parameters:[{type:"payload",payload:String(payload)}]}));
  return { messaging_product:"whatsapp", recipient_type:"individual", to:c.phone, type:"template", template:{name:c.template_name,language:{code:c.language},components} };
}
async function sendMeta(c,env){
  const url=`https://graph.facebook.com/${String(env.GRAPH_VERSION||"v26.0").replace(/^\//,"")}/${env.WHATSAPP_PHONE_NUMBER_ID}/messages`;
  const r=await fetch(url,{method:"POST",headers:{Authorization:`Bearer ${env.WHATSAPP_ACCESS_TOKEN}`,"Content-Type":"application/json"},body:JSON.stringify(buildTemplatePayload(c,env))});
  const raw=await r.text(); let data={}; try{data=raw?JSON.parse(raw):{}}catch{data={raw}};
  if(!r.ok){ const err=data?.error||{}; const details=String(err?.error_data?.details||"").trim(); const e=new Error([err.message||raw||`HTTP ${r.status}`,details].filter(Boolean).join(" · ")); e.code=String(err.code||r.status); throw e; }
  return data;
}

function acknowledgementText(action,env={}){
  const a=String(action||"").toUpperCase();
  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";
  if(a==="TEST_CONFIRMAR") return "Prueba recibida: el botón Sí funciona correctamente. No se modificó ninguna cita real.";
  if(a==="TEST_CANCELAR") return "Prueba recibida: el botón No funciona correctamente. No se modificó ninguna cita real.";
  if(a==="CONFIRMAR") return "Gracias por confirmar su cita con el Dr. Armando Revelo. Su asistencia ha quedado registrada. Lo esperamos en la fecha y hora indicadas.";
  if(a==="CANCELAR") return `Gracias por informarnos. Hemos registrado que no podrá asistir a su cita. Para reagendar, por favor comuníquese directamente con el consultorio del Dr. Armando Revelo al ${doctorPhone}.`;
  return "";
}
function responseWasApplied(result){
  const r=String(result||"").trim().toUpperCase();
  if(!r || ["NOT_FOUND","STALE","UNKNOWN"].includes(r)) return false;
  if(r.startsWith("ERROR") || r.startsWith("INVALID")) return false;
  return true;
}
async function sendTextMeta(phone,body,env,replyToMessageId=""){
  const to=normalizePhone(phone);
  if(!to || !body) return null;
  const payload={messaging_product:"whatsapp",recipient_type:"individual",to,type:"text",text:{preview_url:false,body:String(body)}};
  if(replyToMessageId) payload.context={message_id:String(replyToMessageId)};
  const url=`https://graph.facebook.com/${String(env.GRAPH_VERSION||"v26.0").replace(/^\//,"")}/${env.WHATSAPP_PHONE_NUMBER_ID}/messages`;
  const r=await fetch(url,{method:"POST",headers:{Authorization:`Bearer ${env.WHATSAPP_ACCESS_TOKEN}`,"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const raw=await r.text(); let data={}; try{data=raw?JSON.parse(raw):{}}catch{data={raw}};
  if(!r.ok){ const err=data?.error||{}; const details=String(err?.error_data?.details||"").trim(); const e=new Error([err.message||raw||`HTTP ${r.status}`,details].filter(Boolean).join(" · ")); e.code=String(err.code||r.status); throw e; }
  return data;
}
async function withClient(env,fn){ const c=new Client(env.DATABASE_URL); try{await c.connect(); return await fn(c);} finally{try{await c.end();}catch{}} }

// v2.6.3 — respuestas libres de pacientes (texto + audio) con revisión humana.
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
  if(pos&&neg){
    const strongPositive=words.has("si")||hasAny(t,["confirmo","confirmado","ahi estare","alli estare","cuente conmigo"]);
    if(strongPositive)return {interpretation:"REVISAR",confidence:20,reason:"contradictorio"};
    return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};
  }
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
function automaticAssistantNotice(env={}){
  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";
  return `Hola. Este número corresponde a un asistente automático (IA) del consultorio del Dr. Armando Revelo y se utiliza únicamente para confirmaciones de citas. Para cualquier otra consulta, por favor comuníquese directamente con el consultorio al ${doctorPhone}.`;
}
async function findInboundOrigin(client,message,phone){
  const contextId=String(message?.context?.id||"").trim();
  if(contextId){
    const r=await client.query(`SELECT source_type,source_id,template_name,appointment_date::text appointment_date,appointment_time::text appointment_time,patient_name,phone
      FROM whatsapp_cloud.events WHERE message_id=$1 ORDER BY updated_at DESC LIMIT 1`,[contextId]);
    if(r.rows?.length){
      const x=r.rows[0];
      return {sourceType:String(x.source_type||""),sourceId:Number(x.source_id||0),templateName:String(x.template_name||""),date:String(x.appointment_date||"").slice(0,10),time:String(x.appointment_time||"").slice(0,5),patientName:String(x.patient_name||""),matchMethod:"contexto_mensaje"};
    }
  }
  const normalized=normalizePhone(phone);if(!normalized)return null;
  const r=await client.query(`SELECT source_type,source_id,template_name,appointment_date::text appointment_date,appointment_time::text appointment_time,patient_name
    FROM whatsapp_cloud.events
    WHERE regexp_replace(coalesce(phone,''),'\\D','','g')=$1
      AND status IN ('SENT','DELIVERED','READ')
      AND updated_at > now()-interval '7 days'
    ORDER BY sent_at DESC NULLS LAST,updated_at DESC LIMIT 1`,[normalized]);
  if(!r.rows?.length)return null;
  const x=r.rows[0];
  return {sourceType:String(x.source_type||""),sourceId:Number(x.source_id||0),templateName:String(x.template_name||""),date:String(x.appointment_date||"").slice(0,10),time:String(x.appointment_time||"").slice(0,5),patientName:String(x.patient_name||""),matchMethod:"ultimo_mensaje"};
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
  const q=target.sourceType==="staged"?`SELECT fecha::text d,hora::text t,source_hash::text source_hash FROM public.confirmafy_agenda_items WHERE id=$1`:`SELECT fecha::text d,hora::text t,NULL::text source_hash FROM public.appointments WHERE id=$1`;
  const slot=await client.query(q,[target.sourceId]);if(!slot.rows?.length)return "NOT_FOUND";
  const d=String(slot.rows[0].d||"").slice(0,10),t=String(slot.rows[0].t||"").slice(0,5);
  if(d!==target.date||t!==target.time)return "STALE";
  const isTest=String(slot.rows[0].source_hash||"").startsWith(CLOUD_TEST_PREFIX);
  if(isTest)return action==="CONFIRMAR"?"TEST_CONFIRMED":"TEST_CANCELLED";
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
  let ackAction="",directReply="";
  await withClient(env,async client=>{
    if(!(await ensureInboundSchema(client)))return;
    const origin=await findInboundOrigin(client,message,phone);
    if(origin && origin.templateName && origin.templateName!=="recordatorio_cita"){
      directReply=automaticAssistantNotice(env);
      return;
    }
    const directTarget=await findInboundTarget(client,message,phone);
    const target=directTarget || (origin && origin.templateName==="recordatorio_cita" ? origin : null);
    if(!target){
      directReply=automaticAssistantNotice(env);
      return;
    }
    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;
    if(!target && interpretation!=="REVISAR"){interpretation="REVISAR";confidence=Math.min(confidence,35);}
    if(target && interpretation!=="REVISAR"){
      const action=interpretation==="CONFIRMADO"?"CONFIRMAR":"CANCELAR";
      applyResult=await applyFreeformResponse(client,target,action,messageId,phone);
      if(responseWasApplied(applyResult)){
        resolved=true;resolution=action;
        ackAction=applyResult==="TEST_CONFIRMED"?"TEST_CONFIRMAR":applyResult==="TEST_CANCELLED"?"TEST_CANCELAR":action;
      }else{interpretation="REVISAR";confidence=Math.min(confidence,30);ackAction="";}
    }
    await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation,confidence,target,applyResult,resolved,resolution,rawPayload:{message,audio_error:audioError,intent_reason:intent.reason,template_name:origin?.templateName||"recordatorio_cita"}});
  });
  if(directReply){try{await sendTextMeta(phone,directReply,env,messageId);}catch(e){console.error("whatsapp_assistant_notice_failed",e);}return;}
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


async function dueCandidates(client,env){
  const params=[enabled(env.ENABLE_RECORDATORIO_CITA), enabled(env.ENABLE_RECORDATORIO_HOY), enabled(env.ENABLE_CITA_AGENDADA), env.PREVIOUS_DAY_TIME||"08:00", Number(env.TODAY_HOURS_BEFORE||2)];
  const q=`
WITH base AS (
  SELECT 'appointment'::text source_type,a.id source_id,p.nombre patient_name,p.celular phone,a.fecha,a.hora,a.created_at,a.estado,a.origen,NULL::text source_hash
  FROM public.appointments a JOIN public.patients p ON p.id=a.patient_id
  WHERE upper(coalesce(a.estado,'')) NOT IN ('CANCELADA','CANCELADO') AND a.origen <> 'CONFIRMAFY_ATENDIDO'
  UNION ALL
  SELECT 'staged'::text,c.id,c.nombre,c.celular,c.fecha,c.hora,c.created_at,'PENDIENTE'::text,'MOVIL'::text,c.source_hash::text
  FROM public.confirmafy_agenda_items c
  WHERE coalesce(c.source_hash,'') <> ''
), ev AS (
  SELECT b.*, 'recordatorio_cita'::text kind,
         GREATEST(
           ((b.fecha - 1) + $4::time) AT TIME ZONE 'America/Guayaquil',
           b.created_at AT TIME ZONE 'UTC'
         ) due_at,
         false::boolean is_test
  FROM base b
  WHERE $1::boolean AND coalesce(b.source_hash,'') NOT LIKE 'mobile:whatsapp-cloud-test:%'
  UNION ALL
  SELECT b.*, 'recordatorio_hoy'::text,
         ((b.fecha + b.hora::time) AT TIME ZONE 'America/Guayaquil') - ($5::text||' hours')::interval,
         false::boolean
  FROM base b
  WHERE $2::boolean AND coalesce(b.source_hash,'') NOT LIKE 'mobile:whatsapp-cloud-test:%'
  UNION ALL
  SELECT b.*, 'cita_agendada'::text,
         b.created_at AT TIME ZONE 'UTC',
         false::boolean
  FROM base b
  WHERE $3::boolean
    AND coalesce(b.source_hash,'') NOT LIKE 'mobile:whatsapp-cloud-test:%'
    AND (b.source_type='appointment' OR coalesce(b.source_hash,'') LIKE 'mobile:%')
    AND ((b.fecha + b.hora::time) AT TIME ZONE 'America/Guayaquil')
          - (b.created_at AT TIME ZONE 'UTC') >= interval '24 hours'
    AND ((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date < (b.fecha - 1)
  UNION ALL
  SELECT b.*,
         CASE
           WHEN b.source_hash LIKE 'mobile:whatsapp-cloud-test:cita_agendada:%' THEN 'cita_agendada'
           WHEN b.source_hash LIKE 'mobile:whatsapp-cloud-test:recordatorio_hoy:%' THEN 'recordatorio_hoy'
           ELSE 'recordatorio_cita'
         END::text kind,
         now() due_at,
         true::boolean is_test
  FROM base b
  WHERE b.source_type='staged' AND b.source_hash LIKE 'mobile:whatsapp-cloud-test:%'
)
SELECT source_type,source_id,patient_name,phone,fecha::text appointment_date,hora::text appointment_time,kind,due_at,is_test
FROM ev
WHERE ((fecha + hora::time) AT TIME ZONE 'America/Guayaquil') > now()
  AND due_at <= now()
  AND (
    is_test
    OR (
      source_type='staged'
      AND coalesce(source_hash,'') NOT LIKE 'mobile:%'
      AND kind='recordatorio_cita'
      AND fecha = ((now() AT TIME ZONE 'America/Guayaquil')::date + 1)
    )
    OR due_at > now() - CASE WHEN kind='cita_agendada' THEN interval '1 hour' ELSE interval '4 hours' END
  )
ORDER BY is_test DESC,due_at
LIMIT 50`;
  const r=await client.query(q,params); return r.rows||[];
}
function materializeCandidate(r,env){
  const phone=normalizePhone(r.phone); if(phone.length<10||phone.length>15)return null;
  const name=String(r.patient_name||"").trim().replace(/\s+/g," ").toUpperCase();
  const d=String(r.appointment_date).slice(0,10), t=String(r.appointment_time).slice(0,5);
  const header_image_url=String(env.WHATSAPP_HEADER_IMAGE_URL||DEFAULT_HEADER_IMAGE_URL).trim();
  if(r.kind==="recordatorio_cita") { const yes=r.is_test?"TEST_CONFIRMAR":"CONFIRMAR",no=r.is_test?"TEST_CANCELAR":"CANCELAR"; return {...r,phone,template_name:env.TEMPLATE_RECORDATORIO_CITA||"recordatorio_cita",language:env.LANG_RECORDATORIO_CITA||"es_ES",body_params:[name,recordatorioDateTimeLabel(d,t)],buttons:[`${yes}|${r.source_type}|${r.source_id}|${d}|${t}`,`${no}|${r.source_type}|${r.source_id}|${d}|${t}`]}; }
  if(r.kind==="recordatorio_hoy") return {...r,phone,template_name:env.TEMPLATE_RECORDATORIO_HOY||"recordatorio_hoy",language:env.LANG_RECORDATORIO_HOY||"es_EC",body_params:[name,timeLabel(t)],buttons:[]};
  return {...r,phone,template_name:env.TEMPLATE_CITA_AGENDADA||"cita_agendada",language:env.LANG_CITA_AGENDADA||"es_EC",body_params:[name,dateLabel(d),timeLabel(t)],buttons:[],header_image_url};
}
async function claim(client,c){
  const d=String(c.appointment_date).slice(0,10),t=String(c.appointment_time).slice(0,5); const key=await sha256(`${c.source_type}|${c.source_id}|${c.template_name}|${d}|${t}`); c.event_key=key;
  const r=await client.query(`INSERT INTO whatsapp_cloud.events(event_key,source_type,source_id,template_name,appointment_date,appointment_time,due_at,phone,patient_name,status,attempts,updated_at)
VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'SENDING',1,now())
ON CONFLICT(event_key) DO UPDATE SET status='SENDING',attempts=whatsapp_cloud.events.attempts+1,error_code=NULL,error_text=NULL,updated_at=now()
WHERE whatsapp_cloud.events.status='ERROR' AND whatsapp_cloud.events.attempts<5 AND whatsapp_cloud.events.updated_at < now()-interval '5 minutes'
RETURNING event_key`,[key,c.source_type,c.source_id,c.template_name,d,t,c.due_at,c.phone,c.patient_name]);
  return !!r.rows?.length;
}
async function markSent(client,c,data){ const mid=String(data?.messages?.[0]?.id||""); await client.query(`UPDATE whatsapp_cloud.events SET status='SENT',message_id=$2,sent_at=now(),updated_at=now() WHERE event_key=$1`,[c.event_key,mid]); }
async function markError(client,c,e){ await client.query(`UPDATE whatsapp_cloud.events SET status='ERROR',error_code=$2,error_text=$3,updated_at=now() WHERE event_key=$1`,[c.event_key,String(e.code||""),String(e.message||e).slice(0,1500)]); }
async function runScheduler(env){
  if(!env.DATABASE_URL||!env.WHATSAPP_ACCESS_TOKEN||!env.WHATSAPP_PHONE_NUMBER_ID)return {ok:false,reason:"missing_secrets"};
  return withClient(env,async client=>{ const rows=await dueCandidates(client,env); let claimed=0,sent=0,errors=0,skipped=0; for(const r of rows){const c=materializeCandidate(r,env); if(!c){skipped++;continue;} if(!(await claim(client,c))){skipped++;continue;} claimed++; try{const data=await sendMeta(c,env); await markSent(client,c,data); sent++;}catch(e){await markError(client,c,e); errors++;}} return {ok:true,candidates:rows.length,claimed,sent,errors,skipped}; });
}

function extractPayload(message){ if(message?.type==="button")return String(message.button?.payload||""); if(message?.type==="interactive"&&message.interactive?.type==="button_reply")return String(message.interactive.button_reply?.id||""); return ""; }
function parseActionPayload(payload){ const p=String(payload||"").split("|"); if(p.length<5)return null; const action=String(p[0]).toUpperCase(),sourceType=String(p[1]).toLowerCase(),sourceId=Number.parseInt(p[2],10),date=String(p[3]),time=String(p[4]).slice(0,5); if(!["CONFIRMAR","CANCELAR","TEST_CONFIRMAR","TEST_CANCELAR"].includes(action)||!["appointment","staged","linked"].includes(sourceType)||!Number.isInteger(sourceId)||sourceId<=0||!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^\d{2}:\d{2}$/.test(time))return null; return {action,sourceType:sourceType==="linked"?"appointment":sourceType,sourceId,date,time}; }
async function currentSlot(client,p){ const q=p.sourceType==="staged"?`SELECT fecha::text d,hora::text t,source_hash::text source_hash FROM public.confirmafy_agenda_items WHERE id=$1`:`SELECT fecha::text d,hora::text t,NULL::text source_hash FROM public.appointments WHERE id=$1`; const r=await client.query(q,[p.sourceId]); if(!r.rows?.length)return null; const sourceHash=String(r.rows[0].source_hash||""); return {date:String(r.rows[0].d).slice(0,10),time:String(r.rows[0].t).slice(0,5),isTest:sourceHash.startsWith(CLOUD_TEST_PREFIX)}; }
async function applyResponse(env,p,messageId,phone){ return withClient(env,async client=>{const slot=await currentSlot(client,p); if(!slot)return "NOT_FOUND"; if(slot.date!==p.date||slot.time!==p.time)return "STALE"; if(slot.isTest){ if(["CONFIRMAR","TEST_CONFIRMAR"].includes(p.action))return "TEST_CONFIRMED"; if(["CANCELAR","TEST_CANCELAR"].includes(p.action))return "TEST_CANCELLED"; return "IGNORED_TEST_ACTION"; } if(p.action.startsWith("TEST_"))return "IGNORED_TEST_ACTION"; const r=await client.query(`SELECT public.whatsapp_apply_response($1,$2,$3,$4,$5) AS result`,[p.action,p.sourceType,p.sourceId,String(messageId||""),String(phone||"")]); return String(r.rows?.[0]?.result||"UNKNOWN");}); }
async function updateStatuses(env,statuses){ if(!statuses?.length)return; await withClient(env,async client=>{for(const s of statuses){const mid=String(s.id||""); if(!mid)continue; const st=String(s.status||"").toLowerCase(); const err=s.errors?.[0]||{}; if(st==="delivered")await client.query(`UPDATE whatsapp_cloud.events SET status='DELIVERED',delivered_at=COALESCE(delivered_at,now()),updated_at=now() WHERE message_id=$1`,[mid]); else if(st==="read")await client.query(`UPDATE whatsapp_cloud.events SET status='READ',read_at=COALESCE(read_at,now()),delivered_at=COALESCE(delivered_at,now()),updated_at=now() WHERE message_id=$1`,[mid]); else if(st==="failed")await client.query(`UPDATE whatsapp_cloud.events SET status='FAILED',error_code=$2,error_text=$3,updated_at=now() WHERE message_id=$1`,[mid,String(err.code||""),String(err.title||err.message||"Meta reportó fallo").slice(0,1500)]); else if(st==="sent")await client.query(`UPDATE whatsapp_cloud.events SET status=CASE WHEN status='SENDING' THEN 'SENT' ELSE status END,sent_at=COALESCE(sent_at,now()),updated_at=now() WHERE message_id=$1`,[mid]); }}); }
async function verifyWebhook(request,env){const u=new URL(request.url);if(u.searchParams.get("hub.mode")==="subscribe"&&u.searchParams.get("hub.verify_token")===env.VERIFY_TOKEN)return text(u.searchParams.get("hub.challenge")||"",200);return text("Forbidden",403);}
async function receiveWebhook(request,env){
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
}

export default {
  async fetch(request,env){const u=new URL(request.url);if(u.pathname==="/header.jpg"){const source=String(env.WHATSAPP_HEADER_IMAGE_SOURCE_URL||DEFAULT_HEADER_IMAGE_URL).trim();const r=await fetch(source,{headers:{"User-Agent":"Dr-Revelo-WhatsApp-Worker/2.6.3"}});if(!r.ok)return text("Header unavailable",502);return new Response(r.body,{status:200,headers:{"content-type":r.headers.get("content-type")||"image/jpeg","cache-control":"public, max-age=3600"}});}if(u.pathname==="/health")return json({ok:true,service:"dr-revelo-whatsapp-cloud",worker_version:"2.6.3",scheduler:"*/5 * * * *",header_image_url:String(env.WHATSAPP_HEADER_IMAGE_URL||DEFAULT_HEADER_IMAGE_URL),inbound_policy:"recordatorio_cita_only",inbound_queue:"confirmation_only",inbound_target:"origin_fallback",automation:{cita_agendada:enabled(env.ENABLE_CITA_AGENDADA),recordatorio_cita:enabled(env.ENABLE_RECORDATORIO_CITA),recordatorio_hoy:enabled(env.ENABLE_RECORDATORIO_HOY)}});if(u.pathname==="/run"&&request.method==="POST"){if(!env.ADMIN_TOKEN||request.headers.get("authorization")!==`Bearer ${env.ADMIN_TOKEN}`)return text("Forbidden",403);return json(await runScheduler(env));}if(u.pathname!=="/webhook")return text("Not found",404);if(!env.DATABASE_URL||!env.VERIFY_TOKEN||!env.META_APP_SECRET)return text("Webhook not configured",503);if(request.method==="GET")return verifyWebhook(request,env);if(request.method==="POST")return receiveWebhook(request,env);return text("Method not allowed",405);},
  async scheduled(_controller,env,ctx){ctx.waitUntil(runScheduler(env));}
};

export { runScheduler,parseActionPayload,extractPayload,validMetaSignature,recordatorioDateTimeLabel,normalizePhone,acknowledgementText,responseWasApplied,sendTextMeta,testTemplateFromHash,materializeCandidate,buildTemplatePayload,classifyInboundText,normalizeIntentText,arrayBufferToBase64 };