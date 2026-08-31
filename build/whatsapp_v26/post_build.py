from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8-sig')

# 1) Evita que frases como "No voy a asistir" queden contradictorias por contener "voy".
old='''  if(hasAny(t,uncertain))return {interpretation:"REVISAR",confidence:25,reason:"incertidumbre"};\n  if(pos&&neg)return {interpretation:"REVISAR",confidence:20,reason:"contradictorio"};\n  if(neg)return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};'''
new='''  if(hasAny(t,uncertain))return {interpretation:"REVISAR",confidence:25,reason:"incertidumbre"};\n  if(pos&&neg){\n    const strongPositive=words.has("si")||hasAny(t,["confirmo","confirmado","ahi estare","alli estare","cuente conmigo"]);\n    if(strongPositive)return {interpretation:"REVISAR",confidence:20,reason:"contradictorio"};\n    return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};\n  }\n  if(neg)return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};'''
if old not in s: raise SystemExit('No encontré el bloque de clasificación a corregir')
s=s.replace(old,new,1)

# 2) Solo recordatorio_cita puede interpretar respuestas y modificar la cita.
#    Si el paciente responde a cita_agendada o recordatorio_hoy, el Worker solo
#    devuelve un aviso de asistente automático con el número del consultorio.
anchor='''async function findInboundTarget(client,message,phone){'''
if anchor not in s: raise SystemExit('No encontré findInboundTarget')
helpers=r'''function automaticAssistantNotice(env={}){
  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";
  return `Hola. Este número corresponde a un asistente automático (IA) del consultorio del Dr. Armando Revelo y se utiliza únicamente para confirmaciones de citas. Para cualquier otra consulta, por favor comuníquese directamente con el consultorio al ${doctorPhone}.`;
}
async function findInboundOrigin(client,message,phone){
  const contextId=String(message?.context?.id||"").trim();
  if(contextId){
    const r=await client.query(`SELECT source_type,source_id,template_name,appointment_date::text appointment_date,appointment_time::text appointment_time,patient_name,phone
      FROM whatsapp_cloud.events WHERE message_id=$1 ORDER BY updated_at DESC LIMIT 1`,[contextId]);
    if(r.rows?.length){
      const x=r.rows[0];
      return {sourceType:String(x.source_type||""),sourceId:Number(x.source_id||0),templateName:String(x.template_name||""),date:String(x.appointment_date||"").slice(0,10),time:String(x.appointment_time||"").slice(0,5),patientName:String(x.patient_name||""),matchMethod:"contexto_mensaje"};
    }
  }
  const normalized=normalizePhone(phone);if(!normalized)return null;
  const r=await client.query(`SELECT source_type,source_id,template_name,appointment_date::text appointment_date,appointment_time::text appointment_time,patient_name
    FROM whatsapp_cloud.events
    WHERE regexp_replace(coalesce(phone,''),'\\D','','g')=$1
      AND status IN ('SENT','DELIVERED','READ')
      AND updated_at > now()-interval '7 days'
    ORDER BY sent_at DESC NULLS LAST,updated_at DESC LIMIT 1`,[normalized]);
  if(!r.rows?.length)return null;
  const x=r.rows[0];
  return {sourceType:String(x.source_type||""),sourceId:Number(x.source_id||0),templateName:String(x.template_name||""),date:String(x.appointment_date||"").slice(0,10),time:String(x.appointment_time||"").slice(0,5),patientName:String(x.patient_name||""),matchMethod:"ultimo_mensaje"};
}
'''
s=s.replace(anchor,helpers+anchor,1)

# 3) Las pruebas técnicas de recordatorio_cita nunca ejecutan la función que
#    modifica citas. Si la fila temporal sigue viva, respondemos como TEST_*.
old_apply='''async function applyFreeformResponse(client,target,action,messageId,phone){\n  if(!target||!["appointment","staged"].includes(target.sourceType)||!Number.isInteger(target.sourceId)||target.sourceId<=0)return "NOT_FOUND";\n  const q=target.sourceType==="staged"?`SELECT fecha::text d,hora::text t FROM public.confirmafy_agenda_items WHERE id=$1`:`SELECT fecha::text d,hora::text t FROM public.appointments WHERE id=$1`;\n  const slot=await client.query(q,[target.sourceId]);if(!slot.rows?.length)return "NOT_FOUND";\n  const d=String(slot.rows[0].d||"").slice(0,10),t=String(slot.rows[0].t||"").slice(0,5);\n  if(d!==target.date||t!==target.time)return "STALE";\n  const r=await client.query(`SELECT public.whatsapp_apply_response($1,$2,$3,$4,$5) AS result`,[action,target.sourceType,target.sourceId,String(messageId||""),String(phone||"")]);\n  return String(r.rows?.[0]?.result||"UNKNOWN");\n}'''
new_apply='''async function applyFreeformResponse(client,target,action,messageId,phone){\n  if(!target||!["appointment","staged"].includes(target.sourceType)||!Number.isInteger(target.sourceId)||target.sourceId<=0)return "NOT_FOUND";\n  const q=target.sourceType==="staged"?`SELECT fecha::text d,hora::text t,source_hash::text source_hash FROM public.confirmafy_agenda_items WHERE id=$1`:`SELECT fecha::text d,hora::text t,NULL::text source_hash FROM public.appointments WHERE id=$1`;\n  const slot=await client.query(q,[target.sourceId]);if(!slot.rows?.length)return "NOT_FOUND";\n  const d=String(slot.rows[0].d||"").slice(0,10),t=String(slot.rows[0].t||"").slice(0,5);\n  if(d!==target.date||t!==target.time)return "STALE";\n  const isTest=String(slot.rows[0].source_hash||"").startsWith(CLOUD_TEST_PREFIX);\n  if(isTest)return action==="CONFIRMAR"?"TEST_CONFIRMED":"TEST_CANCELLED";\n  const r=await client.query(`SELECT public.whatsapp_apply_response($1,$2,$3,$4,$5) AS result`,[action,target.sourceType,target.sourceId,String(messageId||""),String(phone||"")]);\n  return String(r.rows?.[0]?.result||"UNKNOWN");\n}'''
if old_apply not in s: raise SystemExit('No encontré applyFreeformResponse esperado')
s=s.replace(old_apply,new_apply,1)

old_handle='''  const intent=classifyInboundText(type==="audio"?transcription:rawText);\n  let ackAction="";\n  await withClient(env,async client=>{\n    if(!(await ensureInboundSchema(client)))return;\n    const target=await findInboundTarget(client,message,phone);\n    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;\n    if(!target && interpretation!=="REVISAR"){interpretation="REVISAR";confidence=Math.min(confidence,35);}\n    if(target && interpretation!=="REVISAR"){\n      const action=interpretation==="CONFIRMADO"?"CONFIRMAR":"CANCELAR";\n      applyResult=await applyFreeformResponse(client,target,action,messageId,phone);\n      if(responseWasApplied(applyResult)){resolved=true;resolution=action;ackAction=action;}\n      else{interpretation="REVISAR";confidence=Math.min(confidence,30);ackAction="";}\n    }\n    await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation,confidence,target,applyResult,resolved,resolution,rawPayload:{message,audio_error:audioError,intent_reason:intent.reason}});\n  });\n  if(ackAction){const ack=acknowledgementText(ackAction,env);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_freeform_ack_failed",e);}}}\n}'''
new_handle='''  const intent=classifyInboundText(type==="audio"?transcription:rawText);\n  let ackAction="",directReply="";\n  await withClient(env,async client=>{\n    if(!(await ensureInboundSchema(client)))return;\n    const origin=await findInboundOrigin(client,message,phone);\n    if(origin && origin.templateName && origin.templateName!=="recordatorio_cita"){\n      await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation:"REVISAR",confidence:100,target:origin,applyResult:"INFO_ONLY",resolved:true,resolution:"ASISTENTE_AUTOMATICO",rawPayload:{message,audio_error:audioError,intent_reason:"plantilla_solo_informativa",template_name:origin.templateName}});\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    const target=await findInboundTarget(client,message,phone);\n    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;\n    if(!target && interpretation!=="REVISAR"){interpretation="REVISAR";confidence=Math.min(confidence,35);}\n    if(target && interpretation!=="REVISAR"){\n      const action=interpretation==="CONFIRMADO"?"CONFIRMAR":"CANCELAR";\n      applyResult=await applyFreeformResponse(client,target,action,messageId,phone);\n      if(responseWasApplied(applyResult)){\n        resolved=true;resolution=action;\n        ackAction=applyResult==="TEST_CONFIRMED"?"TEST_CONFIRMAR":applyResult==="TEST_CANCELLED"?"TEST_CANCELAR":action;\n      }else{interpretation="REVISAR";confidence=Math.min(confidence,30);ackAction="";}\n    }\n    await saveInboundRow(client,{messageId,phone,messageType:type,rawText,transcription,mediaId,mediaMimeType,interpretation,confidence,target,applyResult,resolved,resolution,rawPayload:{message,audio_error:audioError,intent_reason:intent.reason,template_name:origin?.templateName||"recordatorio_cita"}});\n  });\n  if(directReply){try{await sendTextMeta(phone,directReply,env,messageId);}catch(e){console.error("whatsapp_assistant_notice_failed",e);}return;}\n  if(ackAction){const ack=acknowledgementText(ackAction,env);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_freeform_ack_failed",e);}}}\n}'''
if old_handle not in s: raise SystemExit('No encontré handleFreeformInbound esperado')
s=s.replace(old_handle,new_handle,1)

# 4) Identificador de release para verificar el parche exacto en Cloudflare.
s=s.replace('2.6.0','2.6.1')
s=s.replace('automation:{cita_agendada:', 'inbound_policy:"recordatorio_cita_only",automation:{cita_agendada:', 1)

for marker in ['automaticAssistantNotice','ASISTENTE_AUTOMATICO','recordatorio_cita_only','worker_version:"2.6.1"','TEST_CONFIRMED','source_hash::text source_hash']:
    if marker not in s: raise SystemExit(f'Falta marcador final: {marker}')

p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V261_POST_BUILD_OK')
