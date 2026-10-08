import assert from "node:assert/strict";
import { createHmac, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// No real keys, no network and no messages are used in this check.
const source = readFileSync(new URL("../cloudflare/whatsapp_worker.js", import.meta.url), "utf8");
const start = source.indexOf("async function verifyReceptionAlarmHint(request, env)");
const end = source.indexOf("var whatsapp_worker_v2_6_responses_default =", start);
assert.ok(start > 0 && end > start);
const fn = source.slice(start, end);
const context = { URL, crypto: webcrypto, TextEncoder };
vm.runInNewContext(fn + "\nglobalThis.validate = verifyReceptionAlarmHint;", context);
const password = "not-a-real-database-passphrase-1234";
const DATABASE_URL = "postgresql://reception:" + encodeURIComponent(password) + "@fake.example:5432/db";
function build({timestamp = Math.floor(Date.now()/1000), message = "agenda_changed_v1",
                signKey = password, badSignature = false} = {}) {
  let sig = createHmac("sha256", signKey).update(String(timestamp) + "." + message).digest("hex");
  if (badSignature) sig = "0".repeat(64);
  return {
    headers: {get: key => key === "x-revelo-timestamp" ? String(timestamp) :
                      key === "x-revelo-signature" ? sig : null},
    text: async () => message
  };
}
assert.equal(await context.validate(build(), {DATABASE_URL}), true);
assert.equal(await context.validate(build({timestamp: Math.floor(Date.now()/1000)-400}), {DATABASE_URL}), false);
assert.equal(await context.validate(build({message:"agenda_changed_v2"}), {DATABASE_URL}), false);
assert.equal(await context.validate(build({signKey:"different-passphrase"}), {DATABASE_URL}), false);
assert.equal(await context.validate(build({badSignature:true}), {DATABASE_URL}), false);
assert.equal(await context.validate(build(), {DATABASE_URL:""}), false);
assert.match(source, /"\/alarms\/notify" && request\.method === "POST"/);
const py = readFileSync(new URL("../recepcion/app/core_runtime.py", import.meta.url), "utf8");
assert.match(py, /hmac\.new\(key\.encode\("utf-8"\), ts\.encode\("ascii"\) \+ b"\." \+ body, hashlib\.sha256\)\.hexdigest\(\)/);
console.log("RECEPTION_CLOUDFLARE_ALARM_HMAC_ANTI_REPLAY_OK");
