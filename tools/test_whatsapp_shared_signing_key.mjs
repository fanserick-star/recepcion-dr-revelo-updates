import assert from "node:assert/strict";
import {createHmac, webcrypto} from "node:crypto";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Solo datos ficticios; ninguna conexión, cita ni mensaje real.
const worker=readFileSync(new URL("../cloudflare/whatsapp_worker.js",import.meta.url),"utf8");
const core=readFileSync(new URL("../recepcion/app/core_runtime.py",import.meta.url),"utf8");
const a=worker.indexOf("let receptionSigningCache = ");
const b=worker.indexOf("// Notificación puntual firmada solo para citas NUEVAS de Recepción.",a);
assert.ok(a>0&&b>a);
const key="a1".repeat(32); // FICTICIA, sin relación con Neon
let reads=0,tableAvailable=true;
const context={
  URL,Date,TextEncoder,crypto:webcrypto,
  console:{error(){}},
  withClient:async(_env,fn)=>{
    reads++;
    if(!tableAvailable)throw Error("simulated key missing");
    return fn({query:async sql=>{
      assert.match(sql,/FROM whatsapp_cloud\.reception_signing_key WHERE id=1/);
      return {rows:[{signing_key:key}]};
    }});
  }
};
vm.runInNewContext(worker.slice(a,b)+"\nglobalThis.verify=verifyReceptionSignedPayload;",context);
const env={DATABASE_URL:"postgresql://worker:worker-password-2026@fake.example/db"};
const sign=(pass,body="agenda_changed_v1",ts=Math.floor(Date.now()/1000))=>({
  headers:{get:k=>k==="x-revelo-timestamp"?String(ts):k==="x-revelo-signature"?
    createHmac("sha256",pass).update(String(ts)+"."+body).digest("hex"):null},
  text:async()=>body
});
assert.equal(await context.verify(sign(key),env,"agenda_changed_v1"),true,
  "Different Neon-role passwords must NOT break authenticated Reception");
assert.equal(reads,1,"Neon key must be cached rather than polled");
assert.equal(await context.verify(sign(key),env,"agenda_changed_v1"),true);
assert.equal(reads,1);
assert.equal(await context.verify(sign("bad-key"),env,"agenda_changed_v1"),false);
assert.equal(await context.verify(sign(key,"incorrect"),env,"agenda_changed_v1"),false);
assert.equal(await context.verify(sign(key,"agenda_changed_v1",Math.floor(Date.now()/1000)-250),env,"agenda_changed_v1"),false);
assert.equal(await context.verify(sign(key,"reception_fresh_booking_v1:999"),env,"reception_fresh_booking_v1:999"),true);
assert.equal(await context.verify(sign(key,"manual_cita_agendada_v1:999"),env,"manual_cita_agendada_v1:999"),true);
tableAvailable=false;
const envLegacy={DATABASE_URL:"postgresql://legacy:worker-password-2026@fake.example/db"};
assert.equal(await context.verify(sign("worker-password-2026"),envLegacy,"agenda_changed_v1"),true,
 "Old desktop clients are tolerated during the migration");
assert.match(core,/def _wa_shared_signing_key\(\) -> str:/);
assert.match(core,/SELECT encode\(secret,'hex'\) FROM whatsapp_cloud.reception_signing_key WHERE id=1/);
assert.match(core,/key = _wa_shared_signing_key\(\)/);
assert.match(core,/secret = _wa_shared_signing_key\(\)/);
assert.doesNotMatch(worker.slice(a,b),/INSERT INTO|UPDATE whatsapp_cloud|DELETE FROM|setInterval|async scheduled/);
console.log("WA_SHARED_NEON_KEY_403_DIFFERENT_DB_PASSWORD_NO_CRON_NO_REAL_SEND_OK");
