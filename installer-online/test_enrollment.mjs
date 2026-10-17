import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import installer from './enrollment_worker.mjs';
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
    'DATABASE_URL=postgresql://dummy-reception.invalid/db\n'+
    'HISTORIA_DATABASE_URL=postgresql://dummy-historia.invalid/db\n'+
    'AZUR_BASE_URL=https://billing.invalid\nAZUR_API_KEY=CI-TEST-PRIVATE-KEY\n'+
    'MOBILE_DOCTOR_TOKEN=CI-DOCTOR-TOKEN\nMOBILE_RECEPTION_TOKEN=CI-RECEPTION-TOKEN\n'+
    'WHATSAPP_ENABLED=1\nRP_WORKSTATION_NAME=OLD-CLINIC-PC\n')),
  HISTORIA_ENV_B64:b64(e.encode('HISTORIA_DATABASE_URL=postgresql://dummy-historia.invalid/db\nHISTORIA_SYNC_ENABLED=0\n'))
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
assert.equal((await call('/admin/approve',{ticket,code},fakeEnv.DR_REVELO_ADMIN_TOKEN)).status,200);
const approved=await call('/poll',{ticket,token});
assert.equal(approved.status,200);
assert.equal(approved.body.status,'approved');
assert.equal(approved.headers.get('Cache-Control'),'no-store, max-age=0');
const p=approved.body;
const material=await crypto.subtle.decrypt({name:'RSA-OAEP'},keys.privateKey,raw(p.wrapped_key));
const macKey=await crypto.subtle.importKey('raw',new Uint8Array(material).slice(32),'HMAC',false,['verify']);
const signed=e.encode([p.ticket,p.wrapped_key,p.iv,p.ciphertext].join('|'));
assert.equal(await crypto.subtle.verify('HMAC',macKey,raw(p.mac),signed),true);
const aes=await crypto.subtle.importKey('raw',new Uint8Array(material).slice(0,32),'AES-CBC',false,['decrypt']);
const plain=d.decode(await crypto.subtle.decrypt({name:'AES-CBC',iv:raw(p.iv)},aes,raw(p.ciphertext)));
assert.ok(plain.includes('AZUR_API_KEY=CI-TEST-PRIVATE-KEY'));
assert.ok(plain.includes('HISTORIA_DATABASE_URL=postgresql://dummy-historia.invalid/db'));
assert.ok(plain.includes('WHATSAPP_ENABLED=0'));
assert.ok(plain.includes('WHATSAPP_CLOUD_MODE=1'));
assert.ok(plain.includes('HISTORIA_SYNC_ENABLED=1'));
assert.ok(!plain.includes('RP_WORKSTATION_NAME='));
assert.equal((await call('/poll',{ticket,token})).status,410);
const damaged={...fakeEnv,RECEPTION_ENV_B64:''};
assert.equal((await call('/enroll',{pc:'PC',public_key:{n:jwk.n,e:jwk.e}},'',damaged)).status,503);
console.log('ENROLLMENT_DENY_UNAUTHORIZED_AND_RSA_CRYPTO_ROUNDTRIP_OK_DUMMY_ONLY');
