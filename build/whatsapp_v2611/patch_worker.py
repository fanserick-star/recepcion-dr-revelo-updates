from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

assert 'worker_version:"2.6.10"' in s, 'Se esperaba Worker v2.6.10 como base'
assert 'async function verifyWebhook' in s
assert 'async fetch(request,env){const u=new URL(request.url);' in s

s=s.replace('worker_version:"2.6.10"','worker_version:"2.6.11"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.10','Dr-Revelo-WhatsApp-Worker/2.6.11',1)
s=s.replace('audio_proxy:"tokenized_cloudflare"','audio_proxy:"tokenized_cloudflare",booking:"public_v1",booking_cache_seconds:60',1)

booking=r'''
const BOOKING_ALLOWED_ORIGIN="https://fanserick-star.github.io";
const BOOKING_SOURCE_PREFIX="mobile:autoagenda:";
const BOOKING_MAX_DAYS=45;
const BOOKING_CACHE_SECONDS=60;

function bookingToday(){
  const parts=new Intl.DateTimeFormat("en-US",{timeZone:"America/Guayaquil",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
  const x=Object.fromEntries(parts.map(p=>[p.type,p.value]));
  return `${x.year}-${x.month}-${x.day}`;
}
function bookingDateObj(v){const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v||""));return m?new Date(Date.UTC(Number(m[1]),Number(m[2])-1,Number(m[3]),12)):null;}
function bookingValidDay(v){const d=bookingDateObj(v);return !!d&&[4,5,6].includes(d.getUTCDay());}
function bookingTimes(){const out=[];for(let m=480;m<=1020;m+=20){if(m>=750&&m<840)continue;out.push(`${String(Math.floor(m/60)).padStart(2,"0")}:${String(m%60).padStart(2,"0")}`);}return out;}
const BOOKING_TIMES=new Set(bookingTimes());
function bookingHeaders(request,extra={}){
  const h=new Headers(extra);h.set("content-type","application/json; charset=utf-8");h.set("x-content-type-options","nosniff");
  const origin=String(request.headers.get("origin")||"");if(origin===BOOKING_ALLOWED_ORIGIN){h.set("access-control-allow-origin",origin);h.set("vary","Origin");}
  return h;
}
function bookingJson(request,obj,status=200,extra={}){return new Response(JSON.stringify(obj),{status,headers:bookingHeaders(request,extra)});}
function bookingOptions(request){const h=bookingHeaders(request);h.set("access-control-allow-methods","GET, POST, OPTIONS");h.set("access-control-allow-headers","Content-Type");h.set("access-control-max-age","86400");h.delete("content-type");return new Response(null,{status:204,headers:h});}
function bookingOriginAllowed(request){const origin=String(request.headers.get("origin")||"");return !origin||origin===BOOKING_ALLOWED_ORIGIN;}
function bookingCleanPhone(v){let d=String(v||"").replace(/\D/g,"");if(d.startsWith("593")&&d.length===12)d="0"+d.slice(3);return /^09\d{8}$/.test(d)?d:"";}
function bookingCleanName(v){return String(v||"").normalize("NFKC").replace(/\s+/g," ").trim().toUpperCase().slice(0,220);}
function bookingDateWithinHorizon(v){const today=bookingDateObj(bookingToday()),d=bookingDateObj(v);if(!today||!d)return false;const days=Math.round((d-today)/86400000);return days>=0&&days<=BOOKING_MAX_DAYS;}
async function bookingRateAllowed(request){
  try{
    const ip=String(request.headers.get("cf-connecting-ip")||"unknown");const k=await sha256(`booking:${ip}`);const cache=caches.default;
    const key=new Request(new URL(`/__booking_rate/${k}`,request.url).toString(),{method:"GET"});const old=await cache.match(key);const count=old?Number(await old.text())||0:0;
    if(count>=6)return false;await cache.put(key,new Response(String(count+1),{headers:{"Cache-Control":"max-age=60"}}));return true;
  }catch{return true;}
}
async function serveBookingAvailability(request,env,u){
  if(request.method==="OPTIONS")return bookingOptions(request);if(request.method!=="GET")return bookingJson(request,{ok:false,error:"Método no permitido"},405);
  if(!bookingOriginAllowed(request))return bookingJson(request,{ok:false,error:"Origen no permitido"},403);
  if(!env.DATABASE_URL)return bookingJson(request,{ok:false,error:"Agenda temporalmente no disponible"},503);
  const from=String(u.searchParams.get("from")||bookingToday()),to=String(u.searchParams.get("to")||"");
  const a=bookingDateObj(from),b=bookingDateObj(to);if(!a||!b||b<a||Math.round((b-a)/86400000)>BOOKING_MAX_DAYS)return bookingJson(request,{ok:false,error:"Rango de fechas no válido"},400);
  const cache=caches.default;const cacheKey=new Request(`${u.origin}/__booking_cache?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,{method:"GET"});
  const cached=await cache.match(cacheKey);if(cached){const body=await cached.text();return new Response(body,{status:200,headers:bookingHeaders(request,{"cache-control":"public, max-age=30","x-booking-cache":"HIT"})});}
  try{
    const occupied=await withClient(env,async client=>{
      const r=await client.query(`SELECT CAST(fecha AS text) fecha,CAST(hora AS text) hora FROM public.appointments
        WHERE fecha BETWEEN $1::date AND $2::date AND upper(coalesce(estado,'')) NOT IN ('CANCELADA','CANCELADO') AND coalesce(origen,'') <> 'CONFIRMAFY_ATENDIDO'
        UNION
        SELECT CAST(fecha AS text),CAST(hora AS text) FROM public.confirmafy_agenda_items WHERE fecha BETWEEN $1::date AND $2::date`,[from,to]);
      return (r.rows||[]).map(x=>({date:String(x.fecha||"").slice(0,10),time:String(x.hora||"").slice(0,5)}));
    });
    const payload=JSON.stringify({ok:true,today:bookingToday(),max_days:BOOKING_MAX_DAYS,days:[4,5,6],times:bookingTimes(),occupied});
    await cache.put(cacheKey,new Response(payload,{headers:{"Cache-Control":`max-age=${BOOKING_CACHE_SECONDS}`,"content-type":"application/json; charset=utf-8"}}));
    return new Response(payload,{status:200,headers:bookingHeaders(request,{"cache-control":"public, max-age=30","x-booking-cache":"MISS"})});
  }catch(e){console.error("booking_availability_failed",e);return bookingJson(request,{ok:false,error:"No se pudo consultar la agenda. Intente nuevamente."},503);}
}
async function serveBookingCreate(request,env){
  if(request.method==="OPTIONS")return bookingOptions(request);if(request.method!=="POST")return bookingJson(request,{ok:false,error:"Método no permitido"},405);
  if(!bookingOriginAllowed(request))return bookingJson(request,{ok:false,error:"Origen no permitido"},403);
  if(!env.DATABASE_URL)return bookingJson(request,{ok:false,error:"Agenda temporalmente no disponible"},503);
  if(!(await bookingRateAllowed(request)))return bookingJson(request,{ok:false,error:"Demasiados intentos. Espere un minuto e intente nuevamente."},429);
  let data={};try{data=await request.json();}catch{return bookingJson(request,{ok:false,error:"Solicitud no válida"},400);}
  if(String(data.website||"").trim())return bookingJson(request,{ok:false,error:"Solicitud no válida"},400);
  const name=bookingCleanName(data.name),phone=bookingCleanPhone(data.phone),date=String(data.date||"").slice(0,10),time=String(data.time||"").slice(0,5);
  if(name.length<5)return bookingJson(request,{ok:false,error:"Ingrese sus apellidos y nombres completos."},400);
  if(!phone)return bookingJson(request,{ok:false,error:"Ingrese un celular ecuatoriano válido de 10 dígitos."},400);
  if(!bookingValidDay(date)||!bookingDateWithinHorizon(date)||!BOOKING_TIMES.has(time))return bookingJson(request,{ok:false,error:"El horario seleccionado no está disponible para autoagendamiento."},400);
  const sourceHash=BOOKING_SOURCE_PREFIX+crypto.randomUUID().replaceAll("-","").slice(0,32);
  try{
    const row=await withClient(env,async client=>{
      await client.query("BEGIN");
      try{
        await client.query("SELECT pg_advisory_xact_lock(hashtext($1))",[`${date}|${time}`]);
        const occ=await client.query(`SELECT 1 FROM (
          SELECT 1 FROM public.appointments WHERE fecha=$1::date AND hora=$2 AND upper(coalesce(estado,'')) NOT IN ('CANCELADA','CANCELADO') AND coalesce(origen,'') <> 'CONFIRMAFY_ATENDIDO'
          UNION ALL SELECT 1 FROM public.confirmafy_agenda_items WHERE fecha=$1::date AND hora=$2
        ) z LIMIT 1`,[date,time]);
        if(occ.rows?.length){await client.query("ROLLBACK");return null;}
        const r=await client.query(`INSERT INTO public.confirmafy_agenda_items(nombre,celular,fecha,hora,duracion,source_hash,created_at)
          VALUES($1,$2,$3::date,$4,20,$5,now()) RETURNING id,CAST(fecha AS text) fecha,CAST(hora AS text) hora,created_at`,[name,phone,date,time,sourceHash]);
        await client.query("COMMIT");return r.rows?.[0]||null;
      }catch(e){try{await client.query("ROLLBACK");}catch{}throw e;}
    });
    if(!row)return bookingJson(request,{ok:false,error:"Ese horario acaba de ser reservado. Seleccione otro horario.",code:"SLOT_TAKEN"},409);
    return bookingJson(request,{ok:true,booking_id:Number(row.id||0),patient_name:name,date:String(row.fecha||date).slice(0,10),time:String(row.hora||time).slice(0,5),message:"Su cita quedó registrada correctamente."},201,{"cache-control":"no-store"});
  }catch(e){console.error("booking_create_failed",e);return bookingJson(request,{ok:false,error:"No se pudo registrar la cita. Intente nuevamente."},503);}
}
'''

s=s.replace('async function verifyWebhook',booking+'\nasync function verifyWebhook',1)
s=s.replace('async fetch(request,env){const u=new URL(request.url);','async fetch(request,env){const u=new URL(request.url);if(u.pathname==="/booking/availability")return serveBookingAvailability(request,env,u);if(u.pathname==="/booking/book")return serveBookingCreate(request,env);',1)

for marker in ['worker_version:"2.6.11"','booking:"public_v1"','serveBookingAvailability','serveBookingCreate','BOOKING_SOURCE_PREFIX="mobile:autoagenda:"','pg_advisory_xact_lock']:
    assert marker in s,marker
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V2611_BOOKING_PATCHED')
