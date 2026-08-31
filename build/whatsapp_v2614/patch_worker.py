from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'cloudflare/whatsapp_worker_v2_6_responses.js'
w=ROOT/'cloudflare/wrangler.whatsapp.jsonc'
s=p.read_text(encoding='utf-8')

assert 'worker_version:"2.6.13"' in s, 'Se esperaba Worker v2.6.13 como base'
assert 'async function updateStatuses(env,statuses)' in s
assert 'async function handleFreeformInbound(env,message)' in s
assert 'async function serveBookingCreate(request,env)' in s

# Versión / salud.
s=s.replace('worker_version:"2.6.13"','worker_version:"2.6.14"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.13','Dr-Revelo-WhatsApp-Worker/2.6.14')
s=s.replace('scheduler:"*/5 * * * *"','scheduler:"business_window_30m"',1)
s=s.replace('booking_confirmation:"cita_agendada_within_5m"','booking_confirmation:"cita_agendada_immediate"',1)
s=s.replace('audio_proxy:"tokenized_cloudflare",booking:', 'audio_proxy:"tokenized_cloudflare",neon_optimization:"v1",status_persistence:"failed_only",direct_message_fast_path:true,booking:',1)

# No recorrer citas históricas en cada ciclo del programador.
old="""WHERE upper(coalesce(a.estado,'')) NOT IN ('CANCELADA','CANCELADO') AND a.origen <> 'CONFIRMAFY_ATENDIDO'\n  UNION ALL\n  SELECT 'staged'::text,c.id,c.nombre,c.celular,c.fecha,c.hora,c.created_at,'PENDIENTE'::text,'MOVIL'::text,c.source_hash::text\n  FROM public.confirmafy_agenda_items c\n  WHERE coalesce(c.source_hash,'') <> ''"""
new="""WHERE upper(coalesce(a.estado,'')) NOT IN ('CANCELADA','CANCELADO') AND a.origen <> 'CONFIRMAFY_ATENDIDO'\n    AND a.fecha >= ((now() AT TIME ZONE 'America/Guayaquil')::date - 1)\n  UNION ALL\n  SELECT 'staged'::text,c.id,c.nombre,c.celular,c.fecha,c.hora,c.created_at,'PENDIENTE'::text,'MOVIL'::text,c.source_hash::text\n  FROM public.confirmafy_agenda_items c\n  WHERE coalesce(c.source_hash,'') <> ''\n    AND c.fecha >= ((now() AT TIME ZONE 'America/Guayaquil')::date - 1)"""
assert old in s
s=s.replace(old,new,1)

# Los webhooks SENT/DELIVERED/READ son informativos y pueden llegar horas después.
# El envío ya queda como SENT al aceptar Meta. Persistimos únicamente FAILED,
# porque sí requiere diagnóstico y evita despertar Neon por una simple lectura.
a=s.index('async function updateStatuses(env,statuses)')
b=s.index('async function serveInboundAudio',a)
status_fn=r'''async function updateStatuses(env,statuses){
  const failed=(statuses||[]).filter(s=>String(s?.status||'').toLowerCase()==='failed'&&String(s?.id||'').trim());
  if(!failed.length)return;
  await withClient(env,async client=>{
    for(const s of failed){
      const mid=String(s.id||'').trim(),err=s.errors?.[0]||{};
      await client.query(`UPDATE whatsapp_cloud.events SET status='FAILED',error_code=$2,error_text=$3,updated_at=now() WHERE message_id=$1`,[mid,String(err.code||''),String(err.title||err.message||'Meta reportó fallo').slice(0,1500)]);
    }
  });
}
'''
s=s[:a]+status_fn+s[b:]

# Mensajes directos sin contexto (hola, preguntas generales, audio sin intención)
# reciben el aviso sin abrir Postgres. Sí/No claros siguen consultando el último
# recordatorio para conservar el flujo de confirmación existente.
needle='''  const intent=classifyInboundText(type==="audio"?transcription:rawText);\n  const hasExplicitContext=Boolean(String(message?.context?.id||"").trim());\n  let ackAction="",directReply="";\n  await withClient(env,async client=>{'''
replacement='''  const intent=classifyInboundText(type==="audio"?transcription:rawText);\n  const hasExplicitContext=Boolean(String(message?.context?.id||"").trim());\n  let ackAction="",directReply="";\n  if(!hasExplicitContext && ["sin_intencion_clara","sin_texto"].includes(String(intent.reason||""))){\n    try{await sendTextMeta(phone,automaticAssistantNotice(env),env,messageId);}catch(e){console.error("whatsapp_direct_fast_notice_failed",e);}\n    return;\n  }\n  await withClient(env,async client=>{'''
assert needle in s
s=s.replace(needle,replacement,1)

# Autoagendamiento: dispara el scheduler en background justo después de guardar.
# Como Neon ya está despierto por la reserva, el coste incremental es mínimo y
# la confirmación no depende del cron periódico.
s=s.replace('async function serveBookingCreate(request,env){','async function serveBookingCreate(request,env,ctx){',1)
needle2='''    if(!row)return bookingJson(request,{ok:false,error:"Ese horario acaba de ser reservado. Seleccione otro horario.",code:"SLOT_TAKEN"},409);\n    return bookingJson(request,{ok:true,booking_id:Number(row.id||0),patient_name:name,date:String(row.fecha||date).slice(0,10),time:String(row.hora||time).slice(0,5),message:"Su cita quedó registrada correctamente."},201,{"cache-control":"no-store"});'''
replacement2='''    if(!row)return bookingJson(request,{ok:false,error:"Ese horario acaba de ser reservado. Seleccione otro horario.",code:"SLOT_TAKEN"},409);\n    if(ctx?.waitUntil)ctx.waitUntil(runScheduler(env).catch(e=>console.error("booking_confirmation_background_failed",e)));\n    return bookingJson(request,{ok:true,booking_id:Number(row.id||0),patient_name:name,date:String(row.fecha||date).slice(0,10),time:String(row.hora||time).slice(0,5),message:"Su cita quedó registrada correctamente."},201,{"cache-control":"no-store"});'''
assert needle2 in s
s=s.replace(needle2,replacement2,1)
s=s.replace('async fetch(request,env){const u=new URL(request.url);if(u.pathname==="/booking/availability")return serveBookingAvailability(request,env,u);if(u.pathname==="/booking/book")return serveBookingCreate(request,env);', 'async fetch(request,env,ctx){const u=new URL(request.url);if(u.pathname==="/booking/availability")return serveBookingAvailability(request,env,u);if(u.pathname==="/booking/book")return serveBookingCreate(request,env,ctx);',1)

# Cron: de 2016 despertares/semana a ~92. Ecuador = UTC-5.
# Mié: 08:00-17:59 local. Jue-Sáb: 06:00-17:59 local.
cfg=json.loads(w.read_text(encoding='utf-8'))
cfg['triggers']={'crons':['*/30 11-22 * * 4-6','*/30 13-22 * * 3']}
w.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

for marker in [
    'worker_version:"2.6.14"',
    'scheduler:"business_window_30m"',
    'neon_optimization:"v1"',
    'status_persistence:"failed_only"',
    'direct_message_fast_path:true',
    'booking_confirmation:"cita_agendada_immediate"',
    'whatsapp_direct_fast_notice_failed',
    "a.fecha >= ((now() AT TIME ZONE 'America/Guayaquil')::date - 1)",
    'ctx.waitUntil(runScheduler(env)'
]: assert marker in s,marker
assert "st==='read'" not in status_fn
assert "st==='delivered'" not in status_fn
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V2614_NEON_OPTIMIZED')
