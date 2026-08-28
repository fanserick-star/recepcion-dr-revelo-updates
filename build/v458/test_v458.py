from __future__ import annotations
import ast, os, shutil, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
parts=sorted(ROOT.glob('app.part*'), key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
app_source=raw.decode('utf-8')
assert 'APP_VERSION = "4.3.58"' in app_source
assert 'program_update_tmp' not in app_source
assert '@app.post("/api/services/check")' in app_source
assert '_agenda_cloud_payload(doctor, reception, force_sync=bool(force_cloud))' in app_source
compile(app_source,'app.py','exec')

tree=ast.parse(app_source)
consts={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'V458_SETTINGS_JS','V458_SETTINGS_CSS'}:
        consts[n.targets[0].id]=ast.literal_eval(n.value)
assert 'Estado de servicios' in consts['V458_SETTINGS_JS']
assert 'Prueba controlada de WhatsApp (avanzado)' in consts['V458_SETTINGS_JS']
assert 'Respaldo local dentro del consultorio (avanzado)' in consts['V458_SETTINGS_JS']
assert 'Una sola instancia' in consts['V458_SETTINGS_JS']

with tempfile.TemporaryDirectory() as td:
    d=Path(td)
    (d/'app.py').write_bytes(raw)
    (d/'static').mkdir()
    (d/'static'/'index.html').write_text('<!doctype html><html><head></head><body><section id="config"></section></body></html>',encoding='utf-8')
    (d/'azur_client.py').write_text('''class AzurError(Exception): pass\ndef emit_invoice(*a,**k): return {"created":True}\ndef query_comprobante(*a,**k): return {}\ndef mask_api_key(v): return "***" if v else ""\ndef normalize_base_url(v): return str(v).rstrip("/")\ndef test_connection(*a,**k): return {"ok":True}\n''',encoding='utf-8')
    (d/'whatsapp_client.py').write_text('''class WhatsAppError(Exception): pass\ndef build_template_payload(**k): return k\ndef send_template(*a,**k): return {"messages":[{"id":"test"}]}\n''',encoding='utf-8')
    (d/'remote_agenda.py').write_text('''def normalize_public_base_url(v): return str(v)\ndef start_quick_tunnel(*a,**k): return {}\ndef start_named_tunnel(*a,**k): return {}\ndef start_named_tunnel_background(*a,**k): return {}\ndef stop_managed_tunnel(*a,**k): return None\ndef tunnel_status(*a,**k): return {}\n''',encoding='utf-8')
    (d/'psycopg.py').write_text('def connect(*a,**k): raise RuntimeError("stub")\n',encoding='utf-8')
    os.environ.pop('DATABASE_URL',None)
    os.environ['RP_DATA_DIR']=str(d/'runtime-data')
    sys.path.insert(0,str(d)); os.chdir(d)
    import app
    assert app.APP_VERSION=='4.3.58'
    html=app.home(); assert '/v458/settings.js?v=4.3.58' in html

    class Client: host='127.0.0.1'
    class Req: client=Client(); headers={}
    user=app.User(id=1,username='admin',password_hash='',role='admin')

    app._ensure_mobile_tokens=lambda:('doc','rec')
    app._preferred_lan_ip=lambda:''
    app._mobile_firewall_present=lambda:True
    app._try_add_mobile_firewall_rule=lambda:True
    seen=[]
    app._agenda_cloud_payload=lambda d,r,force_sync=False:(seen.append(force_sync) or {'registered':True})
    app.mobile_config(Req(),False,user); app.mobile_config(Req(),True,user)
    assert seen==[False,True]

    app._probe_local_service=lambda:{'label':'Recepción local','status':'ONLINE','detail':'ok'}
    for name,label in [('_probe_neon_service','Neon'),('_probe_azur_service','AZUR'),('_probe_whatsapp_service','WhatsApp Meta'),('_probe_messages_service','Mensajes 24/7'),('_probe_agenda_service','Agenda web 24/7'),('_probe_updates_service','Actualizaciones')]:
        setattr(app,name,lambda label=label:{'label':label,'status':'ONLINE','detail':'ok'})
    svc=app.services_check(Req(),user)
    assert set(svc['services'])=={'local','neon','azur','whatsapp','mensajes','agenda','updates'}
    assert all(x['status']=='ONLINE' for x in svc['services'].values())

    app._read_update_channel_status=lambda:{'local':'4.3.58','latest':'4.3.59','update_available':True,'latency_ms':1}
    up=app.program_update_now(); assert up['update'] and 'Cierra y vuelve a abrir' in up['message']

    ws=app.whatsapp_status(user)
    assert ws['templates']['recordatorio_cita']['approved'] is True
    assert ws['templates']['cita_agendada']['approved'] is False
    assert ws['templates']['recordatorio_hoy']['approved'] is False

    # Windows no permite borrar SQLite mientras el engine conserva handles abiertos.
    # Cerramos explícitamente los pools al terminar; esto solo afecta al entorno temporal de CI.
    for engine_name in ('local_engine','cloud_engine'):
        engine=getattr(app,engine_name,None)
        if engine is not None:
            engine.dispose()

print('V458_BEHAVIOR_OK')
