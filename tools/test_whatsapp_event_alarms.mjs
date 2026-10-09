import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { alarmAtLeastNow } from "../cloudflare/whatsapp_alarm_time.mjs";

const ROOT = new URL("../", import.meta.url);
const worker = readFileSync(new URL("cloudflare/whatsapp_worker.js", ROOT), "utf8");
const config = JSON.parse(readFileSync(new URL("cloudflare/wrangler.whatsapp.jsonc", ROOT), "utf8"));
const deploy = readFileSync(new URL(".github/workflows/deploy-whatsapp.yml", ROOT), "utf8");
const reception = readFileSync(new URL("recepcion/app/core_runtime.py", ROOT), "utf8");

const stamp = v => Date.parse(v);
// This is a scheduler unit test: it makes no requests and NEVER sends a message.
assert.equal(alarmAtLeastNow(stamp("2026-10-08T07:03:00Z"), stamp("2026-10-08T06:00:00Z")),
             stamp("2026-10-08T07:03:00Z")); // Keep existing booking 24/7
assert.equal(alarmAtLeastNow(stamp("2026-10-08T07:03:00Z"), stamp("2026-10-08T07:04:00Z")),
             stamp("2026-10-08T07:04:01.500Z")); // overdue future wake: no tight polling
assert.equal(alarmAtLeastNow(stamp("2026-10-08T13:00:00Z"), stamp("2026-10-08T12:59:00Z")),
             stamp("2026-10-08T13:00:00Z"));
assert.throws(() => alarmAtLeastNow(NaN), /Invalid reminder/);

assert.equal(config.triggers?.crons?.length ?? 0, 0);
assert.deepEqual(config.durable_objects.bindings, [{ name: "WHATSAPP_ALARMS", class_name: "WhatsappAlarmCoordinator" }]);
assert.deepEqual(config.migrations[0].new_sqlite_classes, ["WhatsappAlarmCoordinator"]);
assert.match(deploy, /assert crons == \[\], crons/);
assert.match(worker, /export class WhatsappAlarmCoordinator/);
assert.match(worker, /async alarm\(\)/);
assert.match(worker, /setAlarm\(alarmAtLeastNow/);
assert.match(worker, /async function nextWhatsappReminderTimestamp\(env\)/);
assert.match(worker, /ORDER BY e.updated_at DESC LIMIT 1/);
// SQL NULL must not discard a new appointment that has never been messaged.
assert.match(worker, /AND NOT \(coalesce\(status,\x27\x27\)=\x27ERROR\x27 AND coalesce\(attempts,0\)>=5\)/);
assert.doesNotMatch(worker, /AND NOT \(status=\x27ERROR\x27 AND attempts>=5\)/);
assert.match(worker, /bootstrapped_v1/);
assert.match(worker, /"\/alarms\/notify"/);
assert.match(worker, /verifyReceptionAlarmHint/);
assert.match(worker, /"\/alarms\/status"/);
assert.match(worker, /refreshWhatsappAlarm\(env, true\)/);
assert.match(worker, /alarm_delivery_policy: "preserve_24x7"/);
assert.match(worker, /"\/booking\/availability"/);
assert.match(worker, /"\/booking\/book"/);
assert.match(worker, /if \(status === "CREATED" && ctx\?\.waitUntil\) ctx.waitUntil\(refreshWhatsappAlarm/);
assert.match(worker, /booking_alarm_registration_failed/);
assert.doesNotMatch(worker, /async scheduled\(/);
assert.doesNotMatch(worker, /ctx\.waitUntil\(runScheduler\(env\)\)/);
assert.match(worker, /ON CONFLICT\(event_key\)/); // idempotent Meta sending retained
assert.match(worker, /AND e\.appointment_date=ev\.fecha/);
assert.match(worker, /interval '2 hours'/); // stale test events cannot be replayed
assert.match(reception, /def _whatsapp_alarm_notify_async\(\*, source_type: str/);
assert.match(reception, /hmac\.new\(key\.encode\("utf-8"\)/);
assert.match(reception, /_WA_ALARM_NOTIFY_URL = "https:\/\/dr-revelo-whatsapp-cloud/);
assert.match(reception, /if alarm_relevant_change:\s*_whatsapp_alarm_notify_async\(\)/);
assert.match(reception, /_whatsapp_alarm_notify_async\(source_type=source_type, source_id=source_id\)\s*return \{"queued": queued\}/);
assert.match(reception, /def process_offline_queue\(/);
assert.match(reception, /def schedule_whatsapp_for_contact\(/);
assert.match(reception, /@app\.get\("\/api\/agenda\/week"\)/);
assert.match(reception, /@app\.post\("\/api\/agenda\/appointments"\)/);
// No real messages: verify that Meta callbacks advance statuses monotonically.
const statusCode = worker.split("async function updateStatuses(env, statuses) {",2)[1]?.split("async function serveInboundAudio(",1)[0] || "";
assert.match(statusCode, /"sent", "delivered", "read", "failed"/);
assert.match(statusCode, /status='READ'/);
assert.match(statusCode, /status='DELIVERED'/);
assert.match(statusCode, /status='FAILED'/);
assert.match(statusCode, /read_at=COALESCE/);
assert.match(statusCode, /delivered_at=COALESCE/);
assert.match(statusCode, /status IN \('READ','DELIVERED','FAILED'\)/);
assert.match(statusCode, /status NOT IN \('READ','DELIVERED','CANCELLED'\)/);
assert.match(worker, /CASE WHEN kind='cita_agendada' THEN interval '3 minutes' ELSE interval '4 hours' END/);
assert.match(worker, /WHEN ev.kind='cita_agendada' THEN interval '3 minutes'/);
assert.doesNotMatch(worker, /interval '12 hours'/); // no replay of stale booking notices
const detailCode = reception.split('@app.get("/api/whatsapp/appointment-delivery/{appointment_id}")',2)[1]?.split('@app.get("/api/whatsapp/cloud-status")',1)[0] || "";
assert.match(detailCode, /whatsapp_cloud.events/);
assert.match(detailCode, /SIN_REGISTRO/);
assert.doesNotMatch(detailCode, /_whatsapp_alarm_notify_async|send_whatsapp|schedule_whatsapp_for_contact/);
console.log("WHATSAPP_EVENT_ALARMS_24X7_NO_CRON_NO_SEND_IN_TESTS_OK");
