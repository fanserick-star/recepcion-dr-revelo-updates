import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { deliveryWindowTimestamp, alarmAtLeastNow, canSendAutomaticMessages } from "../cloudflare/whatsapp_alarm_time.mjs";

const ROOT = new URL("../", import.meta.url);
const worker = readFileSync(new URL("cloudflare/whatsapp_worker.js", ROOT), "utf8");
const config = JSON.parse(readFileSync(new URL("cloudflare/wrangler.whatsapp.jsonc", ROOT), "utf8"));
const deploy = readFileSync(new URL(".github/workflows/deploy-whatsapp.yml", ROOT), "utf8");
const reception = readFileSync(new URL("recepcion/app/core_runtime.py", ROOT), "utf8");

const stamp = v => Date.parse(v);
assert.equal(deliveryWindowTimestamp(stamp("2026-10-08T07:03:00Z")), stamp("2026-10-08T13:00:00Z")); // 02:03 Ecuador
assert.equal(deliveryWindowTimestamp(stamp("2026-10-08T12:59:00Z")), stamp("2026-10-08T13:00:00Z")); // 07:59
assert.equal(deliveryWindowTimestamp(stamp("2026-10-08T13:00:00Z")), stamp("2026-10-08T13:00:00Z")); // 08:00
assert.equal(deliveryWindowTimestamp(stamp("2026-10-08T23:59:00Z")), stamp("2026-10-08T23:59:00Z")); // 18:59
assert.equal(deliveryWindowTimestamp(stamp("2026-10-09T00:59:00Z")), stamp("2026-10-09T00:59:00Z")); // 19:59
assert.equal(deliveryWindowTimestamp(stamp("2026-10-09T01:00:00Z")), stamp("2026-10-09T13:00:00Z")); // 20:00 -> next 08:00
assert.equal(canSendAutomaticMessages(stamp("2026-10-08T07:03:00Z")), false);
assert.equal(canSendAutomaticMessages(stamp("2026-10-08T13:00:00Z")), true);
assert.equal(alarmAtLeastNow(stamp("2026-10-08T07:04:00Z"), stamp("2026-10-08T07:03:00Z")),
             stamp("2026-10-08T13:00:00Z"));

assert.equal(config.triggers?.crons?.length ?? 0, 0);
assert.deepEqual(config.durable_objects.bindings, [{ name: "WHATSAPP_ALARMS", class_name: "WhatsappAlarmCoordinator" }]);
assert.deepEqual(config.migrations[0].new_sqlite_classes, ["WhatsappAlarmCoordinator"]);
assert.match(deploy, /assert crons == \[\], crons/);
assert.match(worker, /export class WhatsappAlarmCoordinator/);
assert.match(worker, /async alarm\(\)/);
assert.match(worker, /if \(!canSendAutomaticMessages\(\)\)/);
assert.match(worker, /setAlarm\(alarmAtLeastNow/);
assert.match(worker, /async function nextWhatsappReminderTimestamp\(env\)/);
assert.match(worker, /ORDER BY e.updated_at DESC LIMIT 1/);
assert.match(worker, /bootstrapped_v1/);
assert.match(worker, /"\/alarms\/notify"/);
assert.match(worker, /verifyReceptionAlarmHint/);
assert.match(worker, /"\/alarms\/status"/);
assert.match(worker, /refreshWhatsappAlarm\(env, true\)/);
assert.match(worker, /"\/booking\/availability"/);
assert.match(worker, /"\/booking\/book"/);
assert.match(worker, /if \(status === "CREATED" && ctx\?\.waitUntil\) ctx.waitUntil\(refreshWhatsappAlarm/);
assert.match(worker, /booking_alarm_registration_failed/);
assert.doesNotMatch(worker, /async scheduled\(/);
assert.doesNotMatch(worker, /ctx\.waitUntil\(runScheduler\(env\)\)/);
assert.match(worker, /ON CONFLICT\(event_key\)/); // idempotent Meta sending retained
assert.match(worker, /AND \(e\.appointment_date=ev\.fecha|AND e\.appointment_date=ev\.fecha/);
assert.match(reception, /def _whatsapp_alarm_notify_async\(\)/);
assert.match(reception, /hmac\.new\(key\.encode\("utf-8"\)/);
assert.match(reception, /_WA_ALARM_NOTIFY_URL = "https:\/\/dr-revelo-whatsapp-cloud/);
assert.match(reception, /if alarm_relevant_change and pending == 0:\s*_whatsapp_alarm_notify_async\(\)/);
assert.match(reception, /_whatsapp_alarm_notify_async\(\)\s*return \{"queued": queued\}/);
assert.match(reception, /def process_offline_queue\(/);
assert.match(reception, /def schedule_whatsapp_for_contact\(/);
assert.match(reception, /@app\.get\("\/api\/agenda\/week"\)/);
assert.match(reception, /@app\.post\("\/api\/agenda\/appointments"\)/);
console.log("WHATSAPP_EVENT_DRIVEN_ALARMS_NO_OVERNIGHT_SEND_OK");
