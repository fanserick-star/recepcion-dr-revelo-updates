from __future__ import annotations
import ast, os, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
START_CWD=Path.cwd()
parts=sorted(ROOT.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
source=raw.decode('utf-8')
assert len(parts)==7
assert len(raw)==454939
assert 'APP_VERSION = "4.3.59"' in source
assert '/v459/settings.js?v=4.3.59' in source
assert '@app.post("/api/whatsapp/cloud-test")' in source
assert '@app.get("/api/agenda/appointments/{appointment_id}/whatsapp-timeline")' in source
assert 'mobile:whatsapp-cloud-test:' in source
cloud_block=source[source.index('def whatsapp_cloud_test('):source.index('@app.get("/api/whatsapp/cloud-test/{test_id}")')]
assert 'whatsapp_send_template' not in cloud_block
compile(source,'app.py','exec')

tree=ast.parse(source);consts={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'V459_SETTINGS_JS','V459_SETTINGS_CSS'}:
        consts[n.targets[0].id]=ast.literal_eval(n.value)
js=consts['V459_SETTINGS_JS']
assert 'Estado de servicios' in js
assert 'Enviar prueba por Cloud' in js
assert 'window.openLinkedAgendaDetail' in js
assert 'window.openUnlinkedAgendaDetail' in js
assert 'v459-wa-flow' in consts['V459_SETTINGS_CSS']

with tempfile.TemporaryDirectory() as td:
    d=Path(td);(d/'app.py').write_bytes(raw);(d/'static').mkdir()
    (d/'static'/'index.html').write_text('<!doctype html><html><head></head><body><section id="config"></section></body></html>',encoding='utf-8')
    (d/'azur_client.py').write_text('''class AzurError(Exception): pass\ndef emit_invoice(*a,**k): return {"created":True}\ndef query_comprobante(*a,**k): return {}\ndef mask_api_key(v): return "***" if v else ""\ndef normalize_base_url(v): return str(v).rstrip("/")\ndef test_connection(*a,**k): return {"ok":True}\n''',encoding='utf-8')
    (d/'whatsapp_client.py').write_text('''class WhatsAppError(Exception): pass\ndef build_template_payload(**k): return k\ndef send_template(*a,**k): raise AssertionError("Meta local no debe usarse en la prueba Cloud")\n''',encoding='utf-8')
    (d/'remote_agenda.py').write_text('''def normalize_public_base_url(v): return str(v)\ndef start_quick_tunnel(*a,**k): return {}\ndef start_named_tunnel(*a,**k): return {}\ndef start_named_tunnel_background(*a,**k): return {}\ndef stop_managed_tunnel(*a,**k): return None\ndef tunnel_status(*a,**k): return {}\n''',encoding='utf-8')
    (d/'psycopg.py').write_text('def connect(*a,**k): raise RuntimeError("stub")\n',encoding='utf-8')
    os.environ.pop('DATABASE_URL',None);os.environ['RP_DATA_DIR']=str(d/'runtime-data')
    sys.path.insert(0,str(d));os.chdir(d)
    import app
    assert app.APP_VERSION=='4.3.59'
    html=app.home();assert '/v458/settings.js?v=4.3.58' in html and '/v459/settings.js?v=4.3.59' in html
    future=app.date.today()+app.timedelta(days=2)
    timeline=app._wa_timeline_for_source(source_type='appointment',source_id=1,fecha=future,hora='15:00',appointment_state='PENDIENTE')
    assert [x['key'] for x in timeline['items']]==['cita_agendada','recordatorio_cita','recordatorio_hoy']
    assert timeline['items'][0]['status']=='META_PENDING'
    ok,reason=app._whatsapp_cloud_test_ready();assert not ok and 'Neon' in reason
    user=app.User(id=1,username='admin',password_hash='',role='admin')
    ws=app.whatsapp_status(user);assert ws['manual_test']['requires_local_meta_token'] is False
    with app.LocalSessionLocal() as db:
        target=app.date.today()+app.timedelta(days=(3-app.date.today().weekday())%7 or 7)
        item=app.ConfirmafyAgendaItem(nombre='PRUEBA',celular='593967841449',fecha=target,hora='08:00',duracion=20,source_hash='mobile:whatsapp-cloud-test:abc')
        db.add(item);db.commit()
        week=app.agenda_week(anchor=target,db=db,user=user)
        assert not any((r.get('staged') or {}).get('nombre')=='PRUEBA' for day in week['days'] for r in day['appointments'])
    for name in ('local_engine','cloud_engine'):
        engine=getattr(app,name,None)
        if engine is not None: engine.dispose()
    os.chdir(START_CWD)
    try: sys.path.remove(str(d))
    except ValueError: pass

print('V459_BEHAVIOR_OK')
