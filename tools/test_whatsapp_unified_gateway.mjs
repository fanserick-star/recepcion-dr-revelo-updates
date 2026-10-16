import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Solo datos ficticios; no hay red, Neon ni mensajes reales.
const worker=readFileSync(new URL("../cloudflare/whatsapp_worker.js",import.meta.url),"utf8");
const reception=readFileSync(new URL("../recepcion/app/core_runtime.py",import.meta.url),"utf8");
const start=worker.indexOf("async function serveReceptionGateway(request,env) {");
const end=worker.indexOf("// Invocación exclusiva de Recepción: un envío manual",start);
assert.ok(start>0 && end>start);
let operation="auth_check", sourceType="", sourceId=null, alive=true;
let alarmCount=0,manualCount=0,checks=0,claimed=false,metaMessages=0;
const client={query:async(sql,args)=>{
 checks++;
 if(sql.includes("FROM whatsapp_cloud.reception_alarm_requests WHERE"))
   return {rows:alive?[{purpose:operation,source_type:sourceType,source_id:sourceId}]:[]};
 if(sql.startsWith("SELECT id FROM public.appointments")||sql.startsWith("SELECT id FROM public.confirmafy_agenda_items"))
   return {rows:[{id:sourceId}]};
 if(sql.startsWith("UPDATE whatsapp_cloud.reception_alarm_requests SET consumed_at")) {
   if(claimed)return {rows:[]};claimed=true;return {rows:[{token_hash:args[0]}]};
 }
 return {rows:[]};
}};
const ctx={
  Number,String,JSON,
  json:(body,status=200)=>({body,status}),
  withClient:async(_env,fn)=>fn(client),
  sha256:async()=> "b".repeat(64),
  refreshWhatsappAlarm:async()=>{alarmCount++;return {ok:true};},
  serveManualBookingNotice:async(_req,_env,id,authorized)=>{assert.equal(authorized,true);assert.equal(id,501);manualCount++;return {status:200,body:{ok:true}};},
  console:{error(){}}
};
vm.runInNewContext(worker.slice(start,end)+"\nglobalThis.handler=serveReceptionGateway;",ctx);
const token="x".repeat(43);
const req=(t=token)=>({method:"POST",text:async()=>JSON.stringify({token:t})});
const env={DATABASE_URL:"mock://db"};
let result=await ctx.handler(req(),env);
assert.equal(result.status,200);assert.equal(result.body.no_messages_sent,true);
assert.equal(alarmCount,0);
result=await ctx.handler(req("invalid"),env);
assert.equal(result.status,403);
alive=false;result=await ctx.handler(req(),env);assert.equal(result.status,403);
alive=true;operation="refresh";sourceType="appointment";sourceId=501;
result=await ctx.handler(req(),env);assert.equal(result.status,200);
assert.equal(result.body.alarm_scheduled,true);
assert.equal(result.body.no_messages_sent,true);
assert.equal(alarmCount,1);
operation="manual";
result=await ctx.handler(req(),env);assert.equal(result.status,200);
assert.equal(manualCount,1);
result=await ctx.handler(req(),env);assert.equal(result.status,409);
assert.equal(manualCount,1);
assert.equal(metaMessages,0);
assert.doesNotMatch(worker.slice(start,end),/sendMeta\(|sendTextMeta\(|runScheduler\(|setInterval\(/);
assert.match(worker,/u.pathname === "\/reception\/gateway"/);
assert.match(worker,/const alarm=await refreshWhatsappAlarm\(env\)/);
assert.doesNotMatch(worker,/serveFreshReceptionBookingNotice|verifyReceptionSignedPayload|receptionSigningCache|\/alarms\/notify" &&/);
assert.match(reception,/def _wa_gateway_issue\(/);
assert.match(reception,/secrets\.token_urlsafe\(32\)/);
assert.match(reception,/hashlib\.sha256\(token\.encode\("ascii"\)\)\.hexdigest\(\)/);
assert.match(reception,/def _whatsapp_alarm_notify_async\(/);
assert.match(reception,/if pending is not None: return/);
assert.doesNotMatch(reception,/_wa_alarm_signal_state|_wa_push_fresh_reception_booking_async|_wa_shared_signing_key/);
assert.match(reception,/@app\.get\("\/api\/whatsapp\/auth-check"\)/);
console.log("UNIFIED_WA_GATEWAY_NO_HMAC_NO_CRON_NO_DUPLICATES_NO_META_TEST_OK");
