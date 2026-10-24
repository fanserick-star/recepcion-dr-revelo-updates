// Strictly simulated offline test: no Cloudflare, Meta, Neon or patient data.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const src=fs.readFileSync(new URL('../cloudflare/whatsapp_worker.js',import.meta.url),'utf8');
const start=src.indexOf('async function serveClinicalDispatch(request, env) {');
const end=src.indexOf('// Invocaci',start);
assert(start>0&&end>start,'Clinical-only Worker handler missing');
const section=src.slice(start,end);
assert(!/registerUnifiedAgendaAlarm|runScheduler|appointments|\bcron\b|reception_alarm_requests/.test(section));
assert(!/INSERT INTO whatsapp_cloud.events|patient_name|signed_pdf|patient_id/.test(section));
assert(src.includes('if (u.pathname === "/clinical/dispatch") return serveClinicalDispatch(request,env);'));
let deliveries=0,claims=0;
let authRows=new Map();
let captured=null;
const json=(body,status=200)=>({body,status});
const ctx={
  URL, Set, Number, String, Boolean, JSON, json,
  sha256:async val=>'sha-'+val,
  withClient:async(_env,fn)=>fn({query:async(sql,args)=>{
    assert(sql.includes('UPDATE whatsapp_cloud.clinical_delivery_caps'));
    assert(sql.includes('claimed_at IS NULL'));
    assert(sql.includes('recipient_hash=$2'));
    assert(sql.includes('mode=$3'));
    claims++;
    const row=authRows.get(args[0]);
    if(!row || row.recipient!==(args[1]) || row.mode!==args[2] || row.used)
      return {rows:[]};
    row.used=true;
    return {rows:[{token_hash:args[0]}]};
  }}),
  sendMeta:async(message,_env)=>{
    deliveries++;captured=message;
    return {messages:[{id:'synthetic-message-accepted'}]};
  }
};
vm.runInNewContext(section+'\nglobalThis.clinical=serveClinicalDispatch;',ctx);
const token='x'.repeat(43);
const phone='593999999999';
const link='https://'+ 'a'.repeat(32)+'.r2.cloudflarestorage.com/dr-revelo-clinical-2026/clinical-temp/self-test/test.pdf?X-Amz-Signature=abc123&X-Amz-Expires=604800';
const original={token,mode:'test',phone,template:'entrega_documento_clinico',
  body_params:['PACIENTE DE PRUEBA','DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)','31/10/2026 a las 11:00',link]};
const env={DATABASE_URL:'offline-test',WHATSAPP_ACCESS_TOKEN:'fake-worker-secret',WHATSAPP_PHONE_NUMBER_ID:'1234'};
const call=(body)=>ctx.clinical({method:'POST',text:async()=>JSON.stringify(body)},env);
let denied=await call(original);
assert.equal(denied.status,403);
assert.equal(deliveries,0);
assert.equal(claims,1);
authRows.set('sha-'+token,{recipient:'sha-'+phone,mode:'test',used:false});
let wrong={...original,phone:'593988888888'};
assert.equal((await call(wrong)).status,403);
assert.equal(deliveries,0);
let invalid={...original,template:'recordatorio_cita'};
assert.equal((await call(invalid)).status,400);
let badUrl={...original,body_params:[...original.body_params.slice(0,3),'https://example.com/clinical.pdf']};
assert.equal((await call(badUrl)).status,400);
let wrongMode={...original,mode:'patient'};
assert.equal((await call(wrongMode)).status,403);
assert.equal(deliveries,0);
const accepted=await call(original);
assert.equal(accepted.status,200);
assert.equal(accepted.body.accepted_by_meta,true);
assert.equal(accepted.body.message_id,'synthetic-message-accepted');
assert.equal(deliveries,1);
assert.equal(captured.template_name,'entrega_documento_clinico');
assert.equal(captured.language,'es_EC');
assert.equal(captured.phone,phone);
assert.equal((await call(original)).status,403);
assert.equal(deliveries,1);
const responseText=JSON.stringify(accepted.body);
for(const secret of [token,phone,link,'fake-worker-secret','PACIENTE DE PRUEBA'])assert(!responseText.includes(secret));
console.log('WHATSAPP_CLINICAL_SINGLE_USE_WORKER_NO_ALARMS_NO_DUPLICATES_SYNTHETIC_OK');
