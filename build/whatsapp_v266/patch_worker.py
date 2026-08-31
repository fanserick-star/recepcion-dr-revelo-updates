from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

s=s.replace('// v2.6.5 — respuestas libres de pacientes (texto + audio) con revisión humana.','// v2.6.6 — respuestas libres + aviso correcto para mensajes directos.',1)
s=s.replace('worker_version:"2.6.5"','worker_version:"2.6.6"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.4','Dr-Revelo-WhatsApp-Worker/2.6.6',1)

old='''  const intent=classifyInboundText(type==="audio"?transcription:rawText);\n  let ackAction="",directReply="";'''
new='''  const intent=classifyInboundText(type==="audio"?transcription:rawText);\n  const hasExplicitContext=Boolean(String(message?.context?.id||"").trim());\n  let ackAction="",directReply="";'''
assert old in s
s=s.replace(old,new,1)

old2='''    if(!target){\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;'''
new2='''    if(!target){\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    // Un mensaje nuevo y conversacional no debe heredarse como respuesta de\n    // confirmación solo porque exista un recordatorio reciente del mismo número.\n    // Las confirmaciones/no-asistencias claras sí pueden usar ese respaldo.\n    if(!hasExplicitContext && ["sin_intencion_clara","sin_texto"].includes(String(intent.reason||""))){\n      directReply=automaticAssistantNotice(env);\n      return;\n    }\n    let interpretation=intent.interpretation,confidence=intent.confidence,applyResult="",resolution="",resolved=false;'''
assert old2 in s
s=s.replace(old2,new2,1)

assert 'worker_version:"2.6.6"' in s
assert 'hasExplicitContext' in s
assert '["sin_intencion_clara","sin_texto"]' in s
assert 'automaticAssistantNotice(env)' in s
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V266_PATCHED')
