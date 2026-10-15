import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const worker=readFileSync(new URL("../cloudflare/whatsapp_worker.js",import.meta.url),"utf8");
const core=readFileSync(new URL("../recepcion/app/core_runtime.py",import.meta.url),"utf8");
const start=worker.indexOf("async function serveFreshReceptionBookingNotice(request, env, appointmentId) {");
const end=worker.indexOf("// Invocación exclusiva de Recepción: un envío manual",start);
assert.ok(start>0&&end>start,"No se encontró el código de envío puntual");

let authorized=true, fresh=true, claimed=false, sent=0, metaFails=false;
const statements=[];
const client={async query(sql,args){
  statements.push(sql);
  if(sql.includes("SELECT a.id,a.fecha::text AS fecha")) {
    return {rows:fresh?[{id:555,fecha:"2026-12-11",hora:"09:20",nombre:"PERSONA FICTICIA",celular:"0991234567"}]:[]};
  }
  if(sql.includes("INSERT INTO whatsapp_cloud.events")) {
    if(claimed)return{rows:[]};
    claimed=true;return{rows:[{event_key:"fake-hash"}]};
  }
  return{rows:[]};
}};
const ctx={
  Number,String,Date,
  json:(body,status=200)=>({body,status}),
  text:(body,status=200)=>({body,status}),
  verifyReceptionSignedPayload:async(_request,_env,msg)=>{
    assert.equal(msg,"reception_fresh_booking_v1:555");
    return authorized;
  },
  enabled:()=>true,
  withClient:async(_env,fn)=>fn(client),
  materializeCandidate:(row)=>({...row,phone:"593991234567",template_name:"cita_agendada",patient_name:"PERSONA FICTICIA"}),
  sha256:async()=>"fake-hash",
  sendMeta:async()=>{sent++;if(metaFails)throw Error("simulated");return{messages:[{id:"fake-meta-id"}]};},
  markSent:async()=>{},
  console:{error(){}}
};
vm.runInNewContext(worker.slice(start,end)+"\nglobalThis.testPush=serveFreshReceptionBookingNotice;",ctx);
const env={DATABASE_URL:"dummy",WHATSAPP_ACCESS_TOKEN:"dummy",WHATSAPP_PHONE_NUMBER_ID:"dummy"};
let a=await ctx.testPush({method:"POST"},env,555);
assert.equal(a.status,200);
assert.equal(a.body.sent,true);
assert.equal(sent,1);
assert.ok(statements.some(s=>s.includes("interval '145 seconds'")),"No se permite replay histórico");
assert.ok(statements.some(s=>s.includes("interval '24 hours'")),"No enviar citas próximas");
assert.ok(statements.some(s=>s.includes("ON CONFLICT(event_key) DO NOTHING")),"Sin bloqueo de duplicados");
assert.ok(statements.some(s=>s.includes("a.origen <> 'CONFIRMAFY_ATENDIDO'")));
a=await ctx.testPush({method:"POST"},env,555);
assert.equal(a.body.reason,"already_claimed");
assert.equal(sent,1,"Nunca reenviar una cita ya reclamada");

authorized=false;
assert.equal((await ctx.testPush({method:"POST"},env,555)).status,403);
assert.equal(sent,1);
authorized=true;fresh=false;
assert.equal((await ctx.testPush({method:"POST"},env,555)).body.reason,"not_fresh_or_ineligible");
assert.equal(sent,1);
fresh=true;claimed=false;metaFails=true;
assert.equal((await ctx.testPush({method:"POST"},env,555)).status,502);
assert.equal(sent,2);
assert.ok(statements.some(s=>s.includes("status='FAILED'")));
assert.equal((await ctx.testPush({method:"POST"},env,555)).body.reason,"already_claimed");
assert.equal(sent,2,"Un fallo incierto no provoca un segundo mensaje");

const cloudCreate=core.split('@app.post("/api/agenda/appointments")')[1].split('@app.put("/api/agenda/appointments/{appointment_id}")')[0];
const cloudUpdate=core.split('@app.put("/api/agenda/appointments/{appointment_id}")')[1].split('def set_appointment_state')[0];
assert.match(cloudCreate,/result\["offline"\] = True/);
assert.match(cloudCreate,/_wa_push_fresh_reception_booking_async\(a.id\)\s*result = appointment_dict\(a\); result\["offline"\] = False/);
assert.match(cloudUpdate,/_wa_push_fresh_reception_booking_async\(a.id\)/);
assert.doesNotMatch(core.split('def _wa_push_fresh_reception_booking_async')[1].split('def _whatsapp_alarm_notify_async')[0],/runScheduler|setInterval|cron/);
assert.match(worker,/receptionFreshMatch/);
assert.match(worker,/verifyReceptionSignedPayload\(request, env, "reception_fresh_booking_v1:"/);
assert.match(worker,/failed.*terminal/i);
console.log("RECEPTION_FRESH_BOOKING_SIGNED_NO_REPLAY_NO_DUPLICATE_NO_REAL_SEND_OK");
