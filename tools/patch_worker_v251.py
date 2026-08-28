from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_5_reglas_y_pruebas.js')
s=p.read_text(encoding='utf-8')

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: esperado 1, hubo {n}')
    s=s.replace(old,new,1)

one('''if(r.kind==="recordatorio_cita") { const yes=r.is_test?"TEST_CONFIRMAR":"CONFIRMAR",no=r.is_test?"TEST_CANCELAR":"CANCELAR"; return {...r,phone,template_name:env.TEMPLATE_RECORDATORIO_CITA||"recordatorio_cita",language:env.LANG_RECORDATORIO_CITA||"es_ES",body_params:[name,recordatorioDateTimeLabel(d,t)],buttons:[`${yes}|${r.source_type}|${r.source_id}|${d}|${t}`,`${no}|${r.source_type}|${r.source_id}|${d}|${t}`],header_image_url}; }''','''if(r.kind==="recordatorio_cita") { const yes="CONFIRMAR",no="CANCELAR"; return {...r,phone,template_name:env.TEMPLATE_RECORDATORIO_CITA||"recordatorio_cita",language:env.LANG_RECORDATORIO_CITA||"es_ES",body_params:[name,recordatorioDateTimeLabel(d,t)],buttons:[`${yes}|${r.source_type}|${r.source_id}|${d}|${t}`,`${no}|${r.source_type}|${r.source_id}|${d}|${t}`],header_image_url}; }''','botones compatibles Meta')

old='''if(!r.ok){ const err=data?.error||{}; const e=new Error(err.message||raw||`HTTP ${r.status}`); e.code=String(err.code||r.status); throw e; }'''
new='''if(!r.ok){ const err=data?.error||{}; const details=String(err?.error_data?.details||"").trim(); const e=new Error([err.message||raw||`HTTP ${r.status}`,details].filter(Boolean).join(" · ")); e.code=String(err.code||r.status); throw e; }'''
n=s.count(old)
if n!=2:
    raise SystemExit(f'errores Meta: esperado 2, hubo {n}')
s=s.replace(old,new)

one('''if(responseWasApplied(result)){const ack=acknowledgementText(p.action);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_ack_failed",e);}}}''','''if(responseWasApplied(result)){const ackAction=result==="TEST_CONFIRMED"?"TEST_CONFIRMAR":result==="TEST_CANCELLED"?"TEST_CANCELAR":p.action;const ack=acknowledgementText(ackAction);if(ack){try{await sendTextMeta(phone,ack,env,messageId);}catch(e){console.error("whatsapp_ack_failed",e);}}}''','ack prueba aislada')
one('worker_version:"2.5"','worker_version:"2.5.1"','health version')
one('Dr-Revelo-WhatsApp-Worker/2.5','Dr-Revelo-WhatsApp-Worker/2.5.1','user agent')

# Guardas: una prueba usa payload Meta normal, pero la respuesta se aísla por source_hash.
assert 'r.is_test?"TEST_CONFIRMAR"' not in s
assert 'slot.isTest' in s and 'TEST_CONFIRMED' in s and 'TEST_CANCELLED' in s
assert 'error_data?.details' in s
assert 'worker_version:"2.5.1"' in s
p.write_text(s,encoding='utf-8')
print('WORKER_V251_PATCHED',len(s))
