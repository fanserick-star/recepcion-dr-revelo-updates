import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Cero red, cero Meta, cero Neon: pruebas solo con paciente ficticio.
const ROOT=new URL("../",import.meta.url);
const worker=readFileSync(new URL("cloudflare/whatsapp_worker.js",ROOT),"utf8");
const core=readFileSync(new URL("recepcion/app/core_runtime.py",ROOT),"utf8");
const ui=readFileSync(new URL("recepcion/app/static/app.js",ROOT),"utf8");
const start=worker.indexOf("async function serveManualBookingNotice(request, env, appointmentId, gatewayAuthorized = false) {");
const end=worker.indexOf("var whatsapp_worker_v2_6_responses_default = {",start);
assert.ok(start>0&&end>start,"No se encontró la implementación manual");
let reserved=false,delivered=0,metaFails=false;
let queries=[];
const client={
  async query(sql,args){
    queries.push(sql);
    if(sql.includes("SELECT a.id,a.fecha::text")) return {rows:[{
      id:113,fecha:"2026-11-18",hora:"17:00",nombre:"PACIENTE DE PRUEBA",celular:"0991111111"
    }]};
    if(sql.includes("INSERT INTO whatsapp_cloud.events")){
      if(reserved)return{rows:[]};
      reserved=true;
      return{rows:[{event_key:"hash-de-prueba"}]};
    }
    return {rows:[]};
  }
};
const scope={
  Number, String, json:(body,status=200)=>({body,status}),
  text:(body,status=200)=>({body,status}),
  sha256: async ()=>"hash-de-prueba",
  withClient:async(_env,fn)=>fn(client),
  normalizePhone:p=>String(p),
  dateLabel:()=> "18 noviembre 2026",
  timeLabel:()=> "5:00 p. m.",
  DEFAULT_HEADER_IMAGE_URL:"https://example.org/img.jpg",
  sendMeta:async ()=>{
    delivered++;
    if(metaFails)throw Object.assign(new Error("Fallo simulado"),{code:"SIM"});
    return {messages:[{id:"simulado-id"}]};
  }
};
vm.runInNewContext(worker.slice(start,end)+"\nglobalThis.send=serveManualBookingNotice;",scope);
const env={DATABASE_URL:"dummy",WHATSAPP_ACCESS_TOKEN:"dummy",WHATSAPP_PHONE_NUMBER_ID:"dummy"};
const req={method:"POST"};
let one=await scope.send(req,env,113,true);
assert.equal(one.status,200);
assert.equal(one.body.ok,true);
assert.equal(delivered,1,"Solo se permite un mensaje");
assert.match(queries.join("\n"),/ON CONFLICT\(event_key\) DO NOTHING/);
assert.match(queries.join("\n"),/AND NOT EXISTS\(/);
assert.match(queries.join("\n"),/interval '3 minutes'/);
let twice=await scope.send(req,env,113,true);
assert.equal(twice.status,409);
assert.equal(delivered,1,"El segundo intento no debe llegar a Meta");
assert.equal((await scope.send(req,env,113,false)).status,403);
assert.equal(delivered,1);
reserved=false;metaFails=true;delivered=0;
assert.equal((await scope.send(req,env,113,true)).status,502);
assert.equal(delivered,1);
assert.equal((await scope.send(req,env,113,true)).status,409);
assert.equal(delivered,1,"Error de Meta no habilita reenvío ciego");

// Contrato Reactivo UI -> Backend -> Worker, con confirmación del usuario.
assert.match(core,/\/api\/whatsapp\/appointments\/\{appointment_id\}\/manual-cita-agendada/);
assert.match(core,/purpose="manual", source_type="appointment"/);
assert.match(core,/_wa_gateway_request\(/);
assert.match(ui,/async function manualResendCitaAgendada\(/);
assert.match(ui,/can_manual_resend/);
assert.match(ui,/window\.rpConfirm/);
assert.match(worker,/manual_booking_notice: "one_time_signed_v1"/);
assert.ok(worker.includes('async function serveReceptionGateway(request,env) {'));
assert.ok(!worker.includes('async function verifyReceptionSignedPayload('));
assert.doesNotMatch(worker.slice(start,end),/refreshWhatsappAlarm|setInterval|scheduled\(/);
console.log("MANUAL_BOOKING_NOTICE_ONE_SHOT_NO_REAL_SEND_OK");
