from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

s=s.replace('// v2.6.6 — respuestas libres + aviso correcto para mensajes directos.','// v2.6.7 — ventana de confirmación: cierra al resolver o a las 2 horas.',1)
s=s.replace('worker_version:"2.6.6"','worker_version:"2.6.7"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.6','Dr-Revelo-WhatsApp-Worker/2.6.7',1)

old_resp='''function responseWasApplied(result){\n  const r=String(result||"").trim().toUpperCase();\n  if(!r || ["NOT_FOUND","STALE","UNKNOWN"].includes(r)) return false;\n  if(r.startsWith("ERROR") || r.startsWith("INVALID")) return false;\n  return true;\n}'''
new_resp='''function responseWasApplied(result){\n  const r=String(result||"").trim().toUpperCase();\n  if(!r || ["NOT_FOUND","STALE","UNKNOWN","WINDOW_CLOSED","WINDOW_EXPIRED"].includes(r)) return false;\n  if(r.startsWith("ERROR") || r.startsWith("INVALID")) return false;\n  return true;\n}'''
assert old_resp in s
s=s.replace(old_resp,new_resp,1)

needle='''  return {sourceType:String(a.source_type||""),sourceId:Number(a.source_id||0),date:String(a.appointment_date||"").slice(0,10),time:String(a.appointment_time||"").slice(0,5),patientName:String(a.patient_name||""),matchMethod:"ultimo_recordatorio"};\n}\nasync function applyFreeformResponse'''
insert='''  return {sourceType:String(a.source_type||""),sourceId:Number(a.source_id||0),date:String(a.appointment_date||"").slice(0,10),time:String(a.appointment_time||"").slice(0,5),patientName:String(a.patient_name||""),matchMethod:"ultimo_recordatorio"};\n}\nasync function confirmationWindowState(client,target,phone=""){\n  if(!target||!["appointment","staged"].includes(String(target.sourceType||""))||!Number.isInteger(Number(target.sourceId))||Number(target.sourceId)<=0)return {open:false,reason:"sin_target"};\n  const normalized=normalizePhone(phone);\n  const r=await client.query(`WITH ev AS (\n    SELECT COALESCE(sent_at,updated_at) opened_at\n    FROM whatsapp_cloud.events\n    WHERE template_name='recordatorio_cita'\n      AND source_type=$1 AND source_id=$2\n      AND appointment_date=$3::date AND appointment_time::time=$4::time\n      AND ($5='' OR regexp_replace(coalesce(phone,''),'\\\\D','','g')=$5)\n      AND status IN ('SENT','DELIVERED','READ')\n    ORDER BY sent_at DESC NULLS LAST,updated_at DESC\n    LIMIT 1\n  )\n  SELECT opened_at,\n         (opened_at > now()-interval '2 hours') AS fresh,\n         EXISTS(\n           SELECT 1 FROM whatsapp_cloud.inbound_responses ir\n           WHERE ir.source_type=$1 AND ir.source_id=$2\n             AND ir.appointment_date=$3::date AND ir.appointment_time::time=$4::time\n             AND ir.resolved_at IS NOT NULL\n             AND ir.received_at >= ev.opened_at - interval '1 minute'\n         ) AS resolved\n  FROM ev`,[String(target.sourceType),Number(target.sourceId),String(target.date||"").slice(0,10),String(target.time||"").slice(0,5),normalized]);\n  if(!r.rows?.length)return {open:false,reason:"sin_recordatorio"};\n  const row=r.rows[0];\n  if(row.resolved)return {open:false,reason:"resuelta",openedAt:row.opened_at};\n  if(!row.fresh)return {open:false,reason:"expirada",openedAt:row.opened_at};\n  return {open:true,reason:"abierta",openedAt:row.opened_at};\n}\nasync function applyFreeformResponse'''
assert needle in s
s=s.replace(needle,insert,1)

old_guard='''    if(!hasExplicitContext && ["sin_intencion_clara","sin_texto"].includes(String(intent.reason||""))){\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;'''
new_guard='''    if(!hasExplicitContext && ["sin_intencion_clara","sin_texto"].includes(String(intent.reason||""))){\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    const windowState=await confirmationWindowState(client,target,phone);\n    if(!windowState.open){\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;'''
assert old_guard in s
s=s.replace(old_guard,new_guard,1)

old_apply='''async function applyResponse(env,p,messageId,phone){ return withClient(env,async client=>{const slot=await currentSlot(client,p); if(!slot)return "NOT_FOUND";'''
new_apply='''async function applyResponse(env,p,messageId,phone){ return withClient(env,async client=>{const windowState=await confirmationWindowState(client,p,phone); if(!windowState.open)return windowState.reason==="resuelta"?"WINDOW_CLOSED":"WINDOW_EXPIRED"; const slot=await currentSlot(client,p); if(!slot)return "NOT_FOUND";'''
assert old_apply in s
s=s.replace(old_apply,new_apply,1)

old_log='''async function logButtonInbound(env,message,p,result){\n  if(!p||p.action.startsWith("TEST_"))return;'''
new_log='''async function logButtonInbound(env,message,p,result){\n  if(!p||p.action.startsWith("TEST_"))return;\n  if(["WINDOW_CLOSED","WINDOW_EXPIRED"].includes(String(result||"").toUpperCase()))return;'''
assert old_log in s
s=s.replace(old_log,new_log,1)

old_ack='''      if(responseWasApplied(result)){\n        const ackAction=result==="TEST_CONFIRMED"?"TEST_CONFIRMAR":result==="TEST_CANCELLED"?"TEST_CANCELAR":p.action;\n        const ack=acknowledgementText(ackAction,env);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_ack_failed",e);}}\n      }\n      await logButtonInbound(env,m,p,result);'''
new_ack='''      if(responseWasApplied(result)){\n        const ackAction=result==="TEST_CONFIRMED"?"TEST_CONFIRMAR":result==="TEST_CANCELLED"?"TEST_CANCELAR":p.action;\n        const ack=acknowledgementText(ackAction,env);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_ack_failed",e);}}\n      }else if(["WINDOW_CLOSED","WINDOW_EXPIRED"].includes(String(result||"").toUpperCase())){\n        try{await sendTextMeta(phone,automaticAssistantNotice(env),env,messageId);}catch(e){console.error("whatsapp_closed_window_notice_failed",e);}\n      }\n      await logButtonInbound(env,m,p,result);'''
assert old_ack in s
s=s.replace(old_ack,new_ack,1)

old_health='''inbound_target:"origin_fallback",audio_proxy:"tokenized_cloudflare",automation:'''
new_health='''inbound_target:"origin_fallback",confirmation_window_minutes:120,audio_proxy:"tokenized_cloudflare",automation:'''
assert old_health in s
s=s.replace(old_health,new_health,1)

assert 'worker_version:"2.6.7"' in s
assert 'confirmationWindowState' in s
assert "interval '2 hours'" in s
assert 'confirmation_window_minutes:120' in s
assert 'WINDOW_CLOSED' in s and 'WINDOW_EXPIRED' in s
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V267_PATCHED')
