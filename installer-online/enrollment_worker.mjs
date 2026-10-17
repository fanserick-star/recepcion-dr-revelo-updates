// New, isolated service. NEVER route WhatsApp, patients or invoices here.
// Cloudflare secrets: DR_REVELO_ADMIN_TOKEN, RECEPTION_ENV_B64, HISTORIA_ENV_B64
// Cloudflare KV binding: ENROLLMENTS. No real keys or records belong in GitHub.
const enc = new TextEncoder();
const dec = new TextDecoder();
const ALLOWED = {
  rec: /^(DATABASE_URL|HISTORIA_DATABASE_URL|AZUR_[A-Z0-9_]+|MOBILE_DOCTOR_TOKEN|MOBILE_RECEPTION_TOKEN|AGENDA_CLOUD_BASE_URL)$/,
  hist: /^HISTORIA_[A-Z0-9_]+$/,
};
const noStore = { "Cache-Control": "no-store, max-age=0", "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff" };
function json(body, status=200) { return new Response(JSON.stringify(body), { status, headers: noStore }); }
function from64(s) { return Uint8Array.from(atob(s), c => c.charCodeAt(0)); }
function to64(bytes) { let s = ""; for (const v of new Uint8Array(bytes)) s += String.fromCharCode(v); return btoa(s); }
function hex(bytes) { return [...new Uint8Array(bytes)].map(v => v.toString(16).padStart(2,"0")).join(""); }
function safeEqual(a,b) {
  const aa=enc.encode(String(a||"")), bb=enc.encode(String(b||""));
  let diff=aa.length ^ bb.length;
  for(let i=0;i<Math.max(aa.length,bb.length);i++) diff |= (aa[i]||0)^(bb[i]||0);
  return diff===0;
}
async function sha(s) { return hex(await crypto.subtle.digest("SHA-256", enc.encode(s))); }
function random64(n) { const b=new Uint8Array(n); crypto.getRandomValues(b); return b; }
function parseEnv(encoded, pattern) {
  if(!encoded || encoded.length>80000) throw new Error("private_config_missing_or_too_large");
  const lines=dec.decode(from64(encoded)).replace(/\r/g,"").split("\n");
  const env={};
  for(const line of lines) {
    const value=line.trim();
    if(!value||value.startsWith("#")||!value.includes("="))continue;
    const cut=value.indexOf("="), key=value.slice(0,cut).trim();
    if(!pattern.test(key))continue;
    const secret=value.slice(cut+1).trim();
    if(secret && !secret.includes("\n"))env[key]=secret;
  }
  return env;
}
function buildPrivateConfig(env) {
  const rec=parseEnv(env.RECEPTION_ENV_B64,ALLOWED.rec);
  const hist=parseEnv(env.HISTORIA_ENV_B64,ALLOWED.hist);
  const required=["DATABASE_URL","HISTORIA_DATABASE_URL","AZUR_BASE_URL","AZUR_API_KEY",
    "MOBILE_DOCTOR_TOKEN","MOBILE_RECEPTION_TOKEN"];
  if(required.some(k=>!rec[k]) || !hist.HISTORIA_DATABASE_URL) throw new Error("required_secrets_missing");
  if(rec.DATABASE_URL===hist.HISTORIA_DATABASE_URL || rec.HISTORIA_DATABASE_URL!==hist.HISTORIA_DATABASE_URL)
    throw new Error("neon_projects_do_not_match");
  if(!/^postgres(ql)?:\/\//.test(rec.DATABASE_URL) || !/^postgres(ql)?:\/\//.test(hist.HISTORIA_DATABASE_URL))
    throw new Error("postgresql_url_invalid");
  // Prevent local WhatsApp sending on extra computers. Cloudflare remains sole dispatcher.
  rec.WHATSAPP_CLOUD_MODE="1";
  rec.WHATSAPP_ENABLED="0";
  hist.HISTORIA_SYNC_ENABLED="1";
  const render = obj => Object.keys(obj).sort().map(k=>k+"="+obj[k]).join("\n");
  const value="DR_REVELO_CONFIG_V2\n[RECEPTION]\n"+render(rec)+"\n[HISTORIA]\n"+render(hist)+"\n";
  if(enc.encode(value).byteLength>65000)throw new Error("configuration_too_large");
  return value;
}
async function bodyJson(req, limit=12000) {
  const len=Number(req.headers.get("Content-Length")||"0");
  if(len>limit)throw new Error("payload_too_large");
  const raw=await req.text();
  if(raw.length>limit)throw new Error("payload_too_large");
  return JSON.parse(raw);
}
function validTicket(s) { return typeof s==="string" && /^[a-f0-9]{32}$/.test(s); }
async function admin(req,env) {
  const authorization=req.headers.get("Authorization")||"";
  const expected=env.DR_REVELO_ADMIN_TOKEN;
  return !!(expected && expected.length>=32 && safeEqual(authorization, "Bearer "+expected));
}
async function encryptForDevice(cfg,publicKey,ticket) {
  const key=await crypto.subtle.importKey("jwk",{kty:"RSA",n:publicKey.n,e:publicKey.e,
    alg:"RSA-OAEP-256",ext:true,key_ops:["encrypt"]},
    {name:"RSA-OAEP",hash:"SHA-256"},false,["encrypt"]);
  const material=random64(64);
  const wrapped=await crypto.subtle.encrypt({name:"RSA-OAEP"},key,material);
  const iv=random64(16);
  const aes=await crypto.subtle.importKey("raw",material.slice(0,32),"AES-CBC",false,["encrypt"]);
  const ciphertext=await crypto.subtle.encrypt({name:"AES-CBC",iv},aes,enc.encode(cfg));
  const macKey=await crypto.subtle.importKey("raw",material.slice(32),"HMAC",false,["sign"]);
  const out={ticket,wrapped_key:to64(wrapped),iv:to64(iv),ciphertext:to64(ciphertext)};
  const signed=enc.encode([out.ticket,out.wrapped_key,out.iv,out.ciphertext].join("|"));
  const mac=await crypto.subtle.sign("HMAC",macKey,signed);
  material.fill(0);
  return {...out,mac:to64(mac),format:"DRRV2-RSAOAEP256-AESCBC-HMAC256"};
}
async function route(req,env) {
  const url=new URL(req.url);
  if(req.method==="GET"&&url.pathname==="/health")
    return json({ok:true,service:"consultorio-enrollment",version:1,configured:
      !!(env.ENROLLMENTS&&env.DR_REVELO_ADMIN_TOKEN&&env.RECEPTION_ENV_B64&&env.HISTORIA_ENV_B64)});
  if(req.method==="GET"&&url.pathname==="/approve") {
    const page='<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Autorizar PC · Dr. Revelo</title><style>body{background:#f5f7f9;color:#1d2830;font:16px system-ui;margin:8vh auto;max-width:440px;padding:20px}main{background:white;border:1px solid #dce2e9;border-radius:15px;padding:25px;box-shadow:0 8px 20px #243b5020}input,button{font:inherit;width:100%;box-sizing:border-box;padding:12px;margin:6px 0 16px;border-radius:8px;border:1px solid #aeb8c3}button{background:#143d6c;color:white;cursor:pointer}p{line-height:1.5}small{color:#536474}</style><main><h2>Autorizar nueva computadora</h2><p>Comprueba personalmente el código que aparece en la PC. Nunca introduzcas las claves de Neon ni de AZUR aquí.</p><form id="form"><label>Ticket de la PC<input id="ticket" pattern="[a-f0-9]{32}" required maxlength="32"></label><label>Código de seis cifras<input id="code" pattern="[0-9]{6}" required maxlength="6"></label><label>Contraseña administrativa de instalación<input id="admin" type="password" required autocomplete="off"></label><button>Autorizar esta PC</button></form><p id="result" aria-live="polite"></p><small>Si no reconoces la solicitud, no la apruebes.</small></main><script>document.getElementById("ticket").value=new URLSearchParams(location.search).get("ticket")||"";document.getElementById("form").addEventListener("submit",async e=>{e.preventDefault();const b=document.querySelector("button"),r=document.getElementById("result");b.disabled=true;r.textContent="Comprobando...";try{const a=await fetch("/admin/approve",{method:"POST",headers:{"Content-Type":"application/json","Authorization":"Bearer "+document.getElementById("admin").value},body:JSON.stringify({ticket:document.getElementById("ticket").value,code:document.getElementById("code").value})});const d=await a.json();r.textContent=a.ok&&d.ok?"Computadora autorizada. La instalación continuará.":"No se aprobó. Verifica ticket, código y contraseña.";document.getElementById("admin").value="";}catch(_){r.textContent="No fue posible conectar con el servicio.";}finally{b.disabled=false;}});</script></html>';
    return new Response(page,{status:200,headers:{"Content-Type":"text/html; charset=utf-8",
      "Cache-Control":"no-store","Referrer-Policy":"no-referrer",
      "X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY",
      "Content-Security-Policy":"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'"}});
  }
  if(req.method!=="POST")return json({error:"not_found"},404);
  if(!env.ENROLLMENTS)return json({error:"service_not_configured"},503);
  if(url.pathname==="/enroll") {
    if(!(env.DR_REVELO_ADMIN_TOKEN&&env.RECEPTION_ENV_B64&&env.HISTORIA_ENV_B64))
      return json({error:"service_not_configured"},503);
    const d=await bodyJson(req);
    const pc=String(d.pc||"").replace(/[^a-zA-Z0-9._ -]/g,"").slice(0,64);
    if(!pc || !d.public_key || typeof d.public_key!=="object" ||
      !/^[A-Za-z0-9_-]{300,700}$/.test(d.public_key.n||"") ||
      !/^[A-Za-z0-9_-]{2,8}$/.test(d.public_key.e||""))
      return json({error:"invalid_request"},400);
    // Admission control: no unauthenticated applicant can retrieve secrets.
    // Apply a Cloudflare edge rate limit to /enroll in production.
    const ticket=hex(random64(16)), token=to64(random64(32));
    const code=(100000+new DataView(random64(4).buffer).getUint32(0)%900000).toString();
    await env.ENROLLMENTS.put("ticket:"+ticket,JSON.stringify({
      status:"pending",ticket,code,pc,public_key:d.public_key,
      token_hash:await sha(token),created_at:Date.now()
    }),{expirationTtl:900});
    return json({ticket,token,code,expires_in_seconds:900});
  }
  if(url.pathname==="/poll") {
    const d=await bodyJson(req);
    if(!validTicket(d.ticket)||typeof d.token!=="string"||d.token.length<40)
      return json({error:"invalid_request"},400);
    const stored=await env.ENROLLMENTS.get("ticket:"+d.ticket,"json");
    if(!stored||!safeEqual(stored.token_hash,await sha(d.token)))
      return json({error:"not_found"},404);
    if(stored.status==="pending")return json({status:"pending"});
    if(stored.status!=="approved")return json({error:"enrollment_unavailable"},410);
    let cfg;
    try { cfg=buildPrivateConfig(env); } catch(_) { return json({error:"service_configuration_incomplete"},503); }
    const payload=await encryptForDevice(cfg,stored.public_key,stored.ticket);
    // Only enrolled device, in possession of RSA private key, can decrypt this.
    await env.ENROLLMENTS.put("ticket:"+stored.ticket,
      JSON.stringify({...stored,status:"delivered",public_key:null}),{expirationTtl:120});
    return json({status:"approved",...payload});
  }
  if(url.pathname==="/admin/pending"||url.pathname==="/admin/approve") {
    if(!await admin(req,env))return json({error:"forbidden"},403);
    if(url.pathname==="/admin/pending") {
      const d=await bodyJson(req);
      const ticket=String(d.ticket||"");
      if(!validTicket(ticket))return json({error:"invalid_request"},400);
      const stored=await env.ENROLLMENTS.get("ticket:"+ticket,"json");
      if(!stored)return json({error:"not_found"},404);
      return json({ticket,status:stored.status,code:stored.code,pc:stored.pc,
        created_at:stored.created_at});
    }
    const d=await bodyJson(req);
    if(!validTicket(d.ticket)|| !/^\d{6}$/.test(String(d.code||"")))
      return json({error:"invalid_request"},400);
    const stored=await env.ENROLLMENTS.get("ticket:"+d.ticket,"json");
    if(!stored || stored.status!=="pending" || !safeEqual(stored.code,String(d.code)))
      return json({error:"enrollment_not_pending_or_invalid_code"},409);
    await env.ENROLLMENTS.put("ticket:"+stored.ticket,
      JSON.stringify({...stored,status:"approved"}),{expirationTtl:300});
    return json({ok:true,status:"approved",pc:stored.pc});
  }
  return json({error:"not_found"},404);
}
export default {
  async fetch(req,env) {
    try { return await route(req,env); }
    catch(e) {
      // Never return exception detail that might include secret configuration.
      return json({error:"invalid_request_or_internal_failure"},400);
    }
  }
};
