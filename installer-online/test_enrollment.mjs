import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import installer, { buildPrivateConfig, encryptForDevice } from './enrollment_worker.mjs';
globalThis.crypto ??= webcrypto;
const e=new TextEncoder(),d=new TextDecoder();
const b64=bytes=>Buffer.from(bytes).toString('base64');
const b64u=bytes=>Buffer.from(bytes).toString('base64url');
const raw=b64=>Uint8Array.from(Buffer.from(b64,'base64'));
class KV {
  constructor(){this.db=new Map();}
  async put(k,v,opts={}){this.db.set(k,{value:v,expires:Date.now()+(opts.expirationTtl||900)*1000});}
  async get(k,kind){const it=this.db.get(k);if(!it||it.expires<Date.now())return null;return kind==='json'?JSON.parse(it.value):it.value;}
}
const fakeEnv={
  ENROLLMENTS:new KV(),
  DR_REVELO_ADMIN_TOKEN:'ONLY_FOR_LOCAL_CI_TEST_012345678901234',
  RECEPTION_ENV_B64:b64(e.encode(
    'DATABASE_URL=postgresql://reception-test:test@ep-reception-testing.us-west-2.aws.neon.tech/db\n'+
    'HISTORIA_DATABASE_URL=postgresql://bridge-test:test@ep-sweet-mud-arlsk7qa-pooler.c-4.us-west-2.aws.neon.tech/db\n'+
    'AZUR_BASE_URL=https://billing.invalid\nAZUR_API_KEY=CI-TEST-PRIVATE-KEY\n'+
    'MOBILE_DOCTOR_TOKEN=CI-DOCTOR-TOKEN\nMOBILE_RECEPTION_TOKEN=CI-RECEPTION-TOKEN\n'+
    'WHATSAPP_ENABLED=1\nRP_WORKSTATION_NAME=OLD-CLINIC-PC\n')),
  HISTORIA_ENV_B64:b64(e.encode('HISTORIA_DATABASE_URL=postgresql://clinical-test:test@ep-sweet-mud-arlsk7qa-pooler.c-4.us-west-2.aws.neon.tech/db\nHISTORIA_SYNC_ENABLED=0\n'))
};
async function call(path,data,secret='',env=fakeEnv){
  const req=new Request('https://worker.local'+path,{method:'POST',headers:{
    'Content-Type':'application/json',...(secret?{'Authorization':'Bearer '+secret}:{})},body:JSON.stringify(data)});
  const res=await installer.fetch(req,env);
  return {status:res.status,body:await res.json(),headers:res.headers};
}
const health=await installer.fetch(new Request('https://worker.local/health'),fakeEnv);
assert.equal((await health.json()).configured,true);
const keys=await crypto.subtle.generateKey({name:'RSA-OAEP',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['encrypt','decrypt']);
const jwk=await crypto.subtle.exportKey('jwk',keys.publicKey);
let enrolled=await call('/enroll',{pc:'PC-DE-PRUEBA',public_key:{n:jwk.n,e:jwk.e}});
assert.equal(enrolled.status,200);
const {ticket,token,code}=enrolled.body;
assert.match(ticket,/^[a-f0-9]{16}$/);
assert.match(code,/^\d{6}$/);
assert.equal((await call('/poll',{ticket,token:'A'.repeat(44)})).status,404);
assert.equal((await call('/poll',{ticket,token})).body.status,'pending');
assert.equal((await call('/admin/pending',{ticket})).status,403);
assert.equal((await call('/admin/approve',{ticket,code},'wrong')).status,403);
assert.equal((await call('/admin/approve',{ticket,code:'000000'},fakeEnv.DR_REVELO_ADMIN_TOKEN)).status,409);
let pending=await call('/admin/pending',{ticket},fakeEnv.DR_REVELO_ADMIN_TOKEN);
assert.equal(pending.body.pc,'PC-DE-PRUEBA');
assert.equal('code' in pending.body,false,'Admin ticket lookup must never reveal confirmation code');
assert.equal((await call('/admin/approve',{ticket,code},fakeEnv.DR_REVELO_ADMIN_TOKEN)).status,200);
const debugEnvelope=await encryptForDevice(buildPrivateConfig(fakeEnv),{n:jwk.n,e:jwk.e},ticket);
assert.ok(debugEnvelope.mac);
const approved=await call('/poll',{ticket,token});
assert.equal(approved.status,200);
assert.equal(approved.body.status,'approved');
assert.equal(approved.headers.get('Cache-Control'),'no-store, max-age=0');
const p=approved.body;
const material=await crypto.subtle.decrypt({name:'RSA-OAEP'},keys.privateKey,raw(p.wrapped_key));
const macKey=await crypto.subtle.importKey('raw',new Uint8Array(material).slice(32),{name:'HMAC',hash:'SHA-256'},false,['verify']);
const signed=e.encode([p.ticket,p.wrapped_key,p.iv,p.ciphertext].join('|'));
assert.equal(await crypto.subtle.verify('HMAC',macKey,raw(p.mac),signed),true);
const aes=await crypto.subtle.importKey('raw',new Uint8Array(material).slice(0,32),'AES-CBC',false,['decrypt']);
const plain=d.decode(await crypto.subtle.decrypt({name:'AES-CBC',iv:raw(p.iv)},aes,raw(p.ciphertext)));
assert.ok(plain.includes('AZUR_API_KEY=CI-TEST-PRIVATE-KEY'));
assert.ok(plain.includes('[HISTORIA]\nHISTORIA_DATABASE_URL=postgresql://clinical-test:test@ep-sweet-mud-arlsk7qa-pooler.c-4.us-west-2.aws.neon.tech/db'));
assert.ok(plain.includes('HISTORIA_DATABASE_URL=postgresql://bridge-test:test@ep-sweet-mud-arlsk7qa-pooler.c-4.us-west-2.aws.neon.tech/db'));
assert.ok(plain.includes('WHATSAPP_ENABLED=0'));
assert.ok(plain.includes('WHATSAPP_CLOUD_MODE=1'));
assert.ok(plain.includes('HISTORIA_SYNC_ENABLED=1'));
assert.ok(!plain.includes('RP_WORKSTATION_NAME='));
assert.equal((await call('/poll',{ticket,token})).status,410);
// The public endpoint cannot fill up KV indefinitely from one IP/hour.
for(let i=0;i<9;i++) {
  const next=await call('/enroll',{pc:'PC-TEST-'+i,public_key:{n:jwk.n,e:jwk.e}});
  assert.equal(next.status,200);
}
assert.equal((await call('/enroll',{pc:'PC-EXCESS',public_key:{n:jwk.n,e:jwk.e}})).status,429);
// Reject a bridge pointing at another project's endpoint, even if credentials exist.
const wrongBridge={...fakeEnv,RECEPTION_ENV_B64:b64(e.encode(
  'DATABASE_URL=postgresql://reception-test:test@ep-reception-testing.us-west-2.aws.neon.tech/db\\n'+
  'HISTORIA_DATABASE_URL=postgresql://bridge-test:test@ep-other-testing.us-west-2.aws.neon.tech/db\\n'+
  'AZUR_BASE_URL=https://billing.invalid\\nAZUR_API_KEY=TEST\\n'+
  'MOBILE_DOCTOR_TOKEN=CI-TEST\\nMOBILE_RECEPTION_TOKEN=CI-TEST\\n'))};
assert.throws(()=>buildPrivateConfig(wrongBridge),/neon_projects_do_not_match/);
// Reject reuse of bridge role as the doctor's privileged clinical role.
const sharedRole={...fakeEnv,HISTORIA_ENV_B64:b64(e.encode(
  'HISTORIA_DATABASE_URL=postgresql://bridge-test:other@ep-sweet-mud-arlsk7qa-pooler.c-4.us-west-2.aws.neon.tech/db\\n'))};
assert.throws(()=>buildPrivateConfig(sharedRole),/neon_projects_do_not_match/);
const damaged={...fakeEnv,RECEPTION_ENV_B64:''};
assert.equal((await call('/enroll',{pc:'PC',public_key:{n:jwk.n,e:jwk.e}},'',damaged)).status,503);
console.log('ENROLLMENT_DENY_UNAUTHORIZED_AND_RSA_CRYPTO_ROUNDTRIP_OK_DUMMY_ONLY');
