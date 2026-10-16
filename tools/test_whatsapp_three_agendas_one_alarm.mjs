import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Contrato de los tres orígenes: solo fixtures; cero Neon, red y Meta reales.
const worker=readFileSync(new URL("../cloudflare/whatsapp_worker.js",import.meta.url),"utf8");
const reception=readFileSync(new URL("../recepcion/app/core_runtime.py",import.meta.url),"utf8");
const web=readFileSync(new URL("../agenda/index.html",import.meta.url),"utf8");
const originNames=["whatsapp_message","public_web","admin_web","reception","patient_reply"];
const a=worker.indexOf("async function registerUnifiedAgendaAlarm(env, origin) {");
const b=worker.indexOf("async function nextWhatsappReminderTimestamp(env) {",a);
assert.ok(a>0 && b>a,"La función central de alarmas no existe");
let calls=0, fail=false;
const sandbox={
  Error,console,
  refreshWhatsappAlarm:async()=>{calls++;if(fail)throw Error("Alarm unavailable");return {ok:true};}
};
vm.runInNewContext(worker.slice(a,b)+"\nglobalThis.unifiedAlarm=registerUnifiedAgendaAlarm;",sandbox);
for (const origin of originNames) {
  const result=await sandbox.unifiedAlarm({fake:true},origin);
  assert.equal(result.ok,true);
  assert.equal(result.alarm_scheduled,true);
  assert.equal(result.no_messages_sent,true);
}
assert.equal(calls,originNames.length,"Los cinco casos llaman al mismo coordinador DO");
await assert.rejects(()=>sandbox.unifiedAlarm({}, "unknown_origin"));
fail=true;await assert.rejects(()=>sandbox.unifiedAlarm({}, "reception"));
assert.equal(calls,originNames.length+1);
const sourceCases=[
  ['public_web', /ctx\.waitUntil\(registerUnifiedAgendaAlarm\(env, "public_web"\)/],
  ['whatsapp_message', /ctx\.waitUntil\(registerUnifiedAgendaAlarm\(env, "whatsapp_message"\)/],
  ['admin_web', /await registerUnifiedAgendaAlarm\(env, "admin_web"\)/],
  ['reception', /await registerUnifiedAgendaAlarm\(env, "reception"\)/]
];
for(const [label,rx] of sourceCases)assert.match(worker,rx,label);
const wa=worker.slice(worker.indexOf("async function handleAutoagendaForward("),
  worker.indexOf("// v2.6.18 — enrolamiento privado",worker.indexOf("async function handleAutoagendaForward(")));
assert.ok(wa.indexOf('registerUnifiedAgendaAlarm(env, "whatsapp_message")')<
          wa.indexOf("await sendTextMeta(sender, autoagendaReply("),
          "El aviso de la cita se registra antes de la respuesta al administrador");
assert.match(wa,/if \(status === "CREATED" && ctx\?\.waitUntil\)/);
assert.match(worker,/async function dueCandidates\(client, env\)/);
assert.match(worker,/async function claim\(client, c\)/);
assert.match(worker,/ON CONFLICT\(event_key\)/);
assert.match(worker,/async function runScheduler\(env\)/);
assert.match(worker,/export class WhatsappAlarmCoordinator/);
assert.match(worker,/const alarm=await registerUnifiedAgendaAlarm\(env, "reception"\)/);
assert.match(reception,/def _wa_gateway_request\(/);
assert.match(reception,/def _wa_gateway_signal_async\(/);
assert.match(reception,/def _whatsapp_alarm_notify_async\(/);
assert.match(web,/await notifyWhatsappAlarms\(\)/);
assert.match(web,/agenda_web_create/);
assert.match(web,/agenda_web_move/);
assert.match(web,/agenda_web_cancel/);
assert.doesNotMatch(worker,/async scheduled\(/);
assert.doesNotMatch(worker,/serveFreshReceptionBookingNotice|verifyReceptionSignedPayload/);
assert.doesNotMatch(worker.slice(a,b),/sendMeta\(|sendTextMeta\(|setInterval\(/);
assert.doesNotMatch(worker.slice(a,b),/fetch\(.*graph\.facebook\.com/);
console.log("THREE_AGENDAS_ONE_CLOUDFLARE_ALARM_NO_DUPLICATE_SENDER_NO_CRON_NO_META_OK");
