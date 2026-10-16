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
// Cancellation deletes the source BEFORE refreshing its alarm: the gateway
// must not look up a now-missing row (which would yield HTTP 409).
for (const [start, end] of [
  ['@app.delete("/api/mobile/unlinked/{item_id}")', '@app.put("/api/mobile/appointments/{appointment_id}")'],
  ['@app.delete("/api/mobile/appointments/{appointment_id}")', '@app.get("/api/whatsapp/outbox")'],
  ['@app.delete("/api/agenda/appointments/{appointment_id}")', 'def _decode_confirmafy_csv(']
]) {
  const a = reception.indexOf(start), b = reception.indexOf(end, a);
  assert.ok(a >= 0 && b > a, "Existing cancellation handler required: " + start);
  const handler = reception.slice(a, b);
  assert.match(handler, /_whatsapp_alarm_notify_async\(\)/, "Refresh must use no deleted ID");
  assert.doesNotMatch(handler, /_whatsapp_alarm_notify_async\(source_type=/);
}
assert.match(reception, /if pending is not None: return/);

const start = worker.indexOf("async function serveAdminAgendaAlarmHint(request, env) {");
const end = worker.indexOf("// Un único coordinador WhatsApp para Agenda Web y Recepción.", start);
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
  registerUnifiedAgendaAlarm: async (_env,origin) => {
    assert.equal(origin,"admin_web");
    alarmCalls++;
    if (!alarmOk) throw new Error("Simulated scheduler unavailable");
    return { ok: true, alarm_scheduled: true };
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
