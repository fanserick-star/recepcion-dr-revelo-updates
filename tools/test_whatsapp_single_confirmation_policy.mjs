import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const worker = readFileSync(new URL("cloudflare/whatsapp_worker.js",root),"utf8");
// Use the actual production query generators, but replace DB with a pure mock.
// No production connection, Meta API, Cloudflare worker execution, or sends.
function isolate(start,end,exportName,context) {
  const a=worker.indexOf(start),b=worker.indexOf(end,a);
  assert.ok(a>=0 && b>a, "Worker query generator must exist: "+start);
  vm.runInNewContext(worker.slice(a,b)+"\nglobalThis.extracted="+exportName+";",context);
  return context.extracted;
}
const statements=[];
const fakeClient={query:async(sql,params)=>{
  statements.push({sql:String(sql),params:Array.from(params)});
  return {rows:statements.length===1?[]:[{next_due:null}]};
}};
const env={DATABASE_URL:"not-a-real-db",ENABLE_RECORDATORIO_CITA:"true",
  ENABLE_RECORDATORIO_HOY:"true",ENABLE_CITA_AGENDADA:"true"};
const context={
 enabled:(v)=>String(v)==="true",
 withClient:async(_env,fn)=>fn(fakeClient),
 Date, console
};
const due=isolate("async function dueCandidates(client, env) {",
                  "function materializeCandidate(r, env)","dueCandidates",context);
const alarm=isolate("async function nextWhatsappReminderTimestamp(env) {",
                    "export class WhatsappAlarmCoordinator","nextWhatsappReminderTimestamp",context);
await due(fakeClient,env);
await alarm(env);
assert.equal(statements.length,2,"Both worker scheduler and DO alarm must be exercised");
const [scheduler,doAlarm]=statements.map(x=>x.sql);
for(const [label,sql] of [["sender",scheduler],["alarm",doAlarm]]){
  // Every source follows the same rule. Do not allow autoagenda to override it.
  assert.doesNotMatch(sql,/coalesce\(b\.source_hash,''\) LIKE 'mobile:autoagenda:%'/);
  const booking=sql.match(/SELECT b\.\*, 'cita_agendada'::text[\s\S]*?(?=UNION ALL)/)?.[0];
  assert.ok(booking,label+": booking policy missing");
  assert.match(booking,/b\.created_at AT TIME ZONE 'UTC'\) >= interval '24 hours'/);
  assert.match(booking,/AT TIME ZONE 'America\/Guayaquil'\)::date < \(b\.fecha\s*-\s*1\)/);
  const confirmation=sql.match(/SELECT b\.\*, 'recordatorio_cita'::text[\s\S]*?(?=UNION ALL)/)?.[0];
  assert.ok(confirmation,label+": confirmation policy missing");
  assert.match(confirmation,/b\.fecha > \(now\(\) AT TIME ZONE 'America\/Guayaquil'\)::date/);
  assert.match(sql,/NOT LIKE 'mobile:whatsapp-cloud-test:%'/);
}
assert.match(worker,/ON CONFLICT\(event_key\)/,"Do not break idempotent event claims");
assert.match(worker,/worker_version: "2\.6\.29"/);
const ecu=(stamp)=>new Date(new Date(stamp).getTime()-5*3600e3).toISOString().slice(0,10);
const dayBefore=(date)=>new Date(Date.parse(date+"T00:00:00Z")-86400e3).toISOString().slice(0,10);
const bookingAllowed=(created,appointment)=>{
 const d=appointment.slice(0,10);
 return Date.parse(appointment)-Date.parse(created)>=24*3600e3 && ecu(created)<dayBefore(d);
};
const isDayBefore=(created,appointment)=>ecu(created)<appointment.slice(0,10);
const cases=[
 ["Valentina: autoagenda for tomorrow, 22h31m", "2026-10-08T20:48:58.624Z","2026-10-09T19:20:00Z",false,true],
 ["Tomorrow same-day booking 6h lead","2026-10-09T13:20:00Z","2026-10-09T19:20:00Z",false,false],
 ["Booking 25 hours ahead on day before","2026-10-08T18:20:00Z","2026-10-09T19:20:00Z",false,true],
 ["Booking many days ahead","2026-10-06T20:48:58Z","2026-10-09T19:20:00Z",true,true]
];
for(const [name,created,appointment,wantBooking,wantConfirm] of cases){
 assert.equal(bookingAllowed(created,appointment),wantBooking,name+": cita_agendada");
 assert.equal(isDayBefore(created,appointment),wantConfirm,name+": confirmation day");
}
console.log("WHATSAPP_SINGLE_CONFIRMATION_POLICY_NO_SEND_OK 4 scenarios; sender=alarm matched");
