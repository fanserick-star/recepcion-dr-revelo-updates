import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ROOT = new URL("../", import.meta.url);
const html = readFileSync(new URL("agenda/index.html", ROOT), "utf8");
const worker = readFileSync(new URL("cloudflare/whatsapp_worker.js", ROOT), "utf8");
const reception = readFileSync(new URL("recepcion/app/core_runtime.py", ROOT), "utf8");
const spans = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
assert.ok(spans.length >= 1, "Agenda web must have JavaScript");
for (const p of spans) new vm.Script(p[1], { filename: "agenda/index.html" });

// Verify all three admin mutations preserve their existing Neon RPCs, then
// schedule an alarm only AFTER those RPCs succeeded. Doctor is read-only.
for (const action of ["create", "moveTo", "cancelRow"]) {
  assert.match(html, new RegExp("async function " + action + "\\("));
}
for (const rpc of ["agenda_web_create", "agenda_web_move", "agenda_web_cancel"]) {
  assert.match(html, new RegExp("await rpc\\('" + rpc + "'[^\\n]*?;const scheduled=await notifyWhatsappAlarms\\(\\)"));
}
assert.match(html, /if\(state\.role!=='reception'\|\|!state\.key\)return true/);
assert.match(html, /window\.addEventListener\('online'/);
assert.match(html, /if\(state\.role==='reception'\)void notifyWhatsappAlarms\(1\)/);
assert.ok(!html.includes("setInterval(()=>notifyWhatsappAlarms"), "No browser polling for reminders");
assert.match(reception, /_whatsapp_alarm_notify_async\(source_type=source_type, source_id=source_id\)/);
assert.match(reception, /if alarm_relevant_change:/);
assert.match(reception, /_whatsapp_alarm_notify_async\(source_type="staged", source_id=item_id\)/);
assert.match(reception, /_whatsapp_alarm_notify_async\(source_type="appointment", source_id=appointment_id\)/);
assert.match(reception, /pending_this_event/);

const start = worker.indexOf("async function serveAdminAgendaAlarmHint(request, env) {");
const end = worker.indexOf("async function verifyReceptionAlarmHint(request, env)", start);
assert.ok(start > 0 && end > start);
const handlerSource = worker.slice(start, end);
assert.doesNotMatch(handlerSource, /sendMeta\(|sendTextMeta\(|runScheduler\(/);

let role = "reception", dbCalls = 0, alarmCalls = 0, alarmOk = true;
const context = {
  BOOKING_ALLOWED_ORIGIN: "https://fanserick-star.github.io",
  bookingOptions: () => ({ status: 204 }),
  bookingJson: (_request, result, status) => ({ status, result }),
  withClient: async (_env, fn) => fn({
    query: async (query, args) => {
      dbCalls++;
      assert.match(query, /SELECT public\.agenda_web_role\(\$1::text\) AS role/);
      assert.equal(args.length, 1);
      return { rows: [{ role }] };
    },
  }),
  refreshWhatsappAlarm: async () => {
    alarmCalls++;
    return { ok: alarmOk };
  },
  console: { error() {} },
};
vm.runInNewContext(handlerSource + "\nglobalThis.handler = serveAdminAgendaAlarmHint;", context);
const request = (origin, token = "r".repeat(40), method = "POST") => ({
  method,
  headers: { get: (key) => key.toLowerCase() === "origin" ? origin : null },
  json: async () => ({ token }),
});
const env = { DATABASE_URL: "mock-db-present" };

assert.equal((await context.handler(request("https://bad.example"), env)).status, 403);
assert.equal(dbCalls, 0);
assert.equal((await context.handler(request(context.BOOKING_ALLOWED_ORIGIN, "bad"), env)).status, 403);
assert.equal(dbCalls, 0);
role = "doctor";
assert.equal((await context.handler(request(context.BOOKING_ALLOWED_ORIGIN), env)).status, 403);
assert.equal(alarmCalls, 0);
role = "reception";
assert.equal((await context.handler(request(context.BOOKING_ALLOWED_ORIGIN), env)).status, 200);
assert.equal(alarmCalls, 1);
alarmOk = false;
assert.equal((await context.handler(request(context.BOOKING_ALLOWED_ORIGIN), env)).status, 503);
assert.equal(alarmCalls, 2);
assert.equal((await context.handler(request(context.BOOKING_ALLOWED_ORIGIN, undefined, "OPTIONS"), env)).status, 204);

assert.match(worker, /"\/alarms\/notify-web"\) return serveAdminAgendaAlarmHint\(request, env\)/);
assert.match(worker, /WHERE coalesce\(status,''\) NOT IN \('SENT','DELIVERED','READ','SENDING','CANCELLED','FAILED'\)/);
assert.match(worker, /response_alarm_registration_failed/);
console.log("ADMIN_WEB_EVENTS_NOTIFY_DURABLE_ALARM_NO_PATIENT_MESSAGES_TEST_OK");
