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

function acknowledgementText(action){
  const a=String(action||"").toUpperCase();
  if(a==="TEST_CONFIRMAR") return "✅ Prueba recibida: botón Sí funcionando correctamente. No se modificó ninguna cita real.";
  if(a==="TEST_CANCELAR") return "✅ Prueba recibida: botón No funcionando correctamente. No se modificó ninguna cita real.";
  if(a==="CONFIRMAR") return "✅ ¡Gracias por confirmar! Su cita con el Dr. Armando Revelo ha quedado confirmada. Lo esperamos en la fecha y hora indicadas. 😊";
  if(a==="CANCELAR") return "✅ Gracias por avisarnos. Hemos registrado que no podrá asistir a su cita. Si desea reagendar, puede escribirnos por este mismo medio y con gusto le ayudaremos.";
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
  WHERE c.source_hash LIKE 'mobile:%'
), ev AS (
  SELECT b.*, 'recordatorio_cita'::text kind,
         ((b.fecha - 1) + $4::time) AT TIME ZONE 'America/Guayaquil' due_at,
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
         b.created_at AT TIME ZONE 'America/Guayaquil',
         false::boolean
  FROM base b
  WHERE $3::boolean
    AND coalesce(b.source_hash,'') NOT LIKE 'mobile:whatsapp-cloud-test:%'
    AND ((b.fecha + b.hora::time) AT TIME ZONE 'America/Guayaquil')
          - (b.created_at AT TIME ZONE 'America/Guayaquil') >= interval '24 hours'
    AND (b.created_at AT TIME ZONE 'America/Guayaquil')::date < (b.fecha - 1)
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
  AND (is_test OR due_at > now() - CASE WHEN kind='cita_agendada' THEN interval '1 hour' ELSE interval '4 hours' END)
ORDER BY is_test DESC,due_at
LIMIT 50`;
  const r=await client.query(q,params); return r.rows||[];
}
function materializeCandidate(r,env){
  const phone=normalizePhone(r.phone); if(phone.length<10||phone.length>15)return null;
  const name=String(r.patient_name||"").trim().replace(/\s+/g," ").toUpperCase();
  const d=String(r.appointment_date).slice(0,10), t=String(r.appointment_time).slice(0,5);
  const header_image_url=String(env.WHATSAPP_HEADER_IMAGE_URL||DEFAULT_HEADER_IMAGE_URL).trim();
  if(r.kind==="recordatorio_cita") { const yes="CONFIRMAR",no="CANCELAR"; return {...r,phone,template_name:env.TEMPLATE_RECORDATORIO_CITA||"recordatorio_cita",language:env.LANG_RECORDATORIO_CITA||"es_ES",body_params:[name,recordatorioDateTimeLabel(d,t)],buttons:[`${yes}|${r.source_type}|${r.source_id}|${d}|${t}`,`${no}|${r.source_type}|${r.source_id}|${d}|${t}`],header_image_url}; }
  if(r.kind==="recordatorio_hoy") return {...r,phone,template_name:env.TEMPLATE_RECORDATORIO_HOY||"recordatorio_hoy",language:env.LANG_RECORDATORIO_HOY||"es_EC",body_params:[name,timeLabel(t)],buttons:[],header_image_url};
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
  return withClient(env,async client=>{ const rows=await dueCandidates(client,env); let claimed=0,sent=0,errors=0,skipped=0; for(const r of rows){const c=materializeCandidate(r,env); if(!c){skipped++;continue;} if(!c.header_image_url&&!c.header_image_id){skipped++;continue;} if(!(await claim(client,c))){skipped++;continue;} claimed++; try{const data=await sendMeta(c,env); await markSent(client,c,data); sent++;}catch(e){await markError(client,c,e); errors++;}} return {ok:true,candidates:rows.length,claimed,sent,errors,skipped}; });
}

function extractPayload(message){ if(message?.type==="button")return String(message.button?.payload||""); if(message?.type==="interactive"&&message.interactive?.type==="button_reply")return String(message.interactive.button_reply?.id||""); return ""; }
function parseActionPayload(payload){ const p=String(payload||"").split("|"); if(p.length<5)return null; const action=String(p[0]).toUpperCase(),sourceType=String(p[1]).toLowerCase(),sourceId=Number.parseInt(p[2],10),date=String(p[3]),time=String(p[4]).slice(0,5); if(!["CONFIRMAR","CANCELAR","TEST_CONFIRMAR","TEST_CANCELAR"].includes(action)||!["appointment","staged","linked"].includes(sourceType)||!Number.isInteger(sourceId)||sourceId<=0||!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^\d{2}:\d{2}$/.test(time))return null; return {action,sourceType:sourceType==="linked"?"appointment":sourceType,sourceId,date,time}; }
async function currentSlot(client,p){ const q=p.sourceType==="staged"?`SELECT fecha::text d,hora::text t,source_hash::text source_hash FROM public.confirmafy_agenda_items WHERE id=$1`:`SELECT fecha::text d,hora::text t,NULL::text source_hash FROM public.appointments WHERE id=$1`; const r=await client.query(q,[p.sourceId]); if(!r.rows?.length)return null; const sourceHash=String(r.rows[0].source_hash||""); return {date:String(r.rows[0].d).slice(0,10),time:String(r.rows[0].t).slice(0,5),isTest:sourceHash.startsWith(CLOUD_TEST_PREFIX)}; }
async function applyResponse(env,p,messageId,phone){ return withClient(env,async client=>{const slot=await currentSlot(client,p); if(!slot)return "NOT_FOUND"; if(slot.date!==p.date||slot.time!==p.time)return "STALE"; if(slot.isTest){ if(["CONFIRMAR","TEST_CONFIRMAR"].includes(p.action))return "TEST_CONFIRMED"; if(["CANCELAR","TEST_CANCELAR"].includes(p.action))return "TEST_CANCELLED"; return "IGNORED_TEST_ACTION"; } if(p.action.startsWith("TEST_"))return "IGNORED_TEST_ACTION"; const r=await client.query(`SELECT public.whatsapp_apply_response($1,$2,$3,$4,$5) AS result`,[p.action,p.sourceType,p.sourceId,String(messageId||""),String(phone||"")]); return String(r.rows?.[0]?.result||"UNKNOWN");}); }
async function updateStatuses(env,statuses){ if(!statuses?.length)return; await withClient(env,async client=>{for(const s of statuses){const mid=String(s.id||""); if(!mid)continue; const st=String(s.status||"").toLowerCase(); const err=s.errors?.[0]||{}; if(st==="delivered")await client.query(`UPDATE whatsapp_cloud.events SET status='DELIVERED',delivered_at=COALESCE(delivered_at,now()),updated_at=now() WHERE message_id=$1`,[mid]); else if(st==="read")await client.query(`UPDATE whatsapp_cloud.events SET status='READ',read_at=COALESCE(read_at,now()),delivered_at=COALESCE(delivered_at,now()),updated_at=now() WHERE message_id=$1`,[mid]); else if(st==="failed")await client.query(`UPDATE whatsapp_cloud.events SET status='FAILED',error_code=$2,error_text=$3,updated_at=now() WHERE message_id=$1`,[mid,String(err.code||""),String(err.title||err.message||"Meta reportó fallo").slice(0,1500)]); else if(st==="sent")await client.query(`UPDATE whatsapp_cloud.events SET status=CASE WHEN status='SENDING' THEN 'SENT' ELSE status END,sent_at=COALESCE(sent_at,now()),updated_at=now() WHERE message_id=$1`,[mid]); }}); }
async function verifyWebhook(request,env){const u=new URL(request.url);if(u.searchParams.get("hub.mode")==="subscribe"&&u.searchParams.get("hub.verify_token")===env.VERIFY_TOKEN)return text(u.searchParams.get("hub.challenge")||"",200);return text("Forbidden",403);}
async function receiveWebhook(request,env){const raw=await request.arrayBuffer();if(!(await validMetaSignature(raw,request.headers.get("x-hub-signature-256")||"",env.META_APP_SECRET)))return text("Invalid signature",401);let body;try{body=JSON.parse(decoder.decode(raw));}catch{return text("Invalid JSON",400);}const messages=[],statuses=[];for(const e of body?.entry||[])for(const ch of e?.changes||[]){for(const m of ch?.value?.messages||[])messages.push(m);for(const s of ch?.value?.statuses||[])statuses.push(s);}if(statuses.length)await updateStatuses(env,statuses);for(const m of messages){const p=parseActionPayload(extractPayload(m));if(!p)continue;const messageId=String(m.id||"");const phone=String(m.from||"");let result="UNKNOWN";try{result=await applyResponse(env,p,messageId,phone);}catch(e){console.error("whatsapp_apply_response_failed",e);continue;}if(responseWasApplied(result)){const ackAction=result==="TEST_CONFIRMED"?"TEST_CONFIRMAR":result==="TEST_CANCELLED"?"TEST_CANCELAR":p.action;const ack=acknowledgementText(ackAction);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_ack_failed",e);}}}}return text("EVENT_RECEIVED",200);}

export default {
  async fetch(request,env){const u=new URL(request.url);if(u.pathname==="/header.jpg"){const source=String(env.WHATSAPP_HEADER_IMAGE_SOURCE_URL||DEFAULT_HEADER_IMAGE_URL).trim();const r=await fetch(source,{headers:{"User-Agent":"Dr-Revelo-WhatsApp-Worker/2.5.1"}});if(!r.ok)return text("Header unavailable",502);return new Response(r.body,{status:200,headers:{"content-type":r.headers.get("content-type")||"image/jpeg","cache-control":"public, max-age=3600"}});}if(u.pathname==="/health")return json({ok:true,service:"dr-revelo-whatsapp-cloud",worker_version:"2.5.1",scheduler:"*/5 * * * *",header_image_url:String(env.WHATSAPP_HEADER_IMAGE_URL||DEFAULT_HEADER_IMAGE_URL),automation:{cita_agendada:enabled(env.ENABLE_CITA_AGENDADA),recordatorio_cita:enabled(env.ENABLE_RECORDATORIO_CITA),recordatorio_hoy:enabled(env.ENABLE_RECORDATORIO_HOY)}});if(u.pathname==="/run"&&request.method==="POST"){if(!env.ADMIN_TOKEN||request.headers.get("authorization")!==`Bearer ${env.ADMIN_TOKEN}`)return text("Forbidden",403);return json(await runScheduler(env));}if(u.pathname!=="/webhook")return text("Not found",404);if(!env.DATABASE_URL||!env.VERIFY_TOKEN||!env.META_APP_SECRET)return text("Webhook not configured",503);if(request.method==="GET")return verifyWebhook(request,env);if(request.method==="POST")return receiveWebhook(request,env);return text("Method not allowed",405);},
  async scheduled(_controller,env,ctx){ctx.waitUntil(runScheduler(env));}
};

export { runScheduler,parseActionPayload,extractPayload,validMetaSignature,recordatorioDateTimeLabel,normalizePhone,acknowledgementText,responseWasApplied,sendTextMeta,testTemplateFromHash };
