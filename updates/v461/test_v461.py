from __future__ import annotations
import ast, os, sys, tempfile, hashlib, json
from pathlib import Path
from datetime import date, datetime, timedelta

ROOT=Path(__file__).resolve().parent
START_CWD=Path.cwd()
meta=json.loads((ROOT/'release_meta.json').read_text(encoding='utf-8'))
assert meta['product']=='recepcion-pacientes'
assert meta['version']=='4.3.61'
assert meta['base_version']=='4.3.60'
assert len(meta['app_sha256'])==64 and int(meta['app_size'])>0 and int(meta['parts_count'])>0
parts=sorted(ROOT.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts); source=raw.decode('utf-8')
assert len(parts)==int(meta['parts_count']); assert len(raw)==int(meta['app_size']); assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
manifest_bytes=(ROOT/'update_manifest.json').read_bytes(); assert hashlib.sha256(manifest_bytes).hexdigest()==meta['manifest_sha256']
assert 'APP_VERSION = "4.3.61"' in source and '/v460/overlay.js?v=4.3.61' in source
assert 'WHATSAPP_CLOUD_TEST_TEMPLATES' in source and '_whatsapp_cloud_test_source_hash(template_key, token)' in source and '"template": template_key' in source
assert 'Omitido por regla' in source
assert 'WHATSAPP_AUTO_CITA_AGENDADA = (os.getenv("WHATSAPP_AUTO_CITA_AGENDADA") or "1").strip() != "0"' in source
assert 'WHATSAPP_AUTO_RECORDATORIO_HOY = (os.getenv("WHATSAPP_AUTO_RECORDATORIO_HOY") or "1").strip() != "0"' in source
assert 'WHATSAPP_APPROVED_CITA_AGENDADA = (os.getenv("WHATSAPP_APPROVED_CITA_AGENDADA") or "1").strip() != "0"' in source
assert 'WHATSAPP_APPROVED_RECORDATORIO_HOY = (os.getenv("WHATSAPP_APPROVED_RECORDATORIO_HOY") or "1").strip() != "0"' in source
cloud_block=source[source.index('def whatsapp_cloud_test('):source.index('@app.get("/api/whatsapp/cloud-test/{test_id}")')]
assert 'whatsapp_send_template' not in cloud_block
compile(source,'app.py','exec')
tree=ast.parse(source); consts={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'V459_SETTINGS_JS','V459_SETTINGS_CSS','V460_OVERLAY_JS','V460_OVERLAY_CSS'}:
        consts[n.targets[0].id]=ast.literal_eval(n.value)
js=consts['V459_SETTINGS_JS']
assert 'Enviar prueba por Cloud' in js
assert "['recordatorio_cita','cita_agendada','recordatorio_hoy'].includes(template)" in js
assert 'Esa plantilla todavía está pendiente de Meta' not in js
assert "VERSION='4.3.61'" in consts['V460_OVERLAY_JS'] and '#connectionBadge' in consts['V460_OVERLAY_JS']
with tempfile.TemporaryDirectory() as td:
    d=Path(td); (d/'app.py').write_bytes(raw); (d/'static').mkdir()
    (d/'static'/'index.html').write_text('<!doctype html><html><head></head><body><div id="connectionBadge"></div><section id="config"></section></body></html>',encoding='utf-8')
    (d/'azur_client.py').write_text('class AzurError(Exception): pass\ndef emit_invoice(*a,**k): return {}\ndef query_comprobante(*a,**k): return {}\ndef mask_api_key(v): return "***" if v else ""\ndef normalize_base_url(v): return str(v).rstrip("/")\ndef test_connection(*a,**k): return {"ok":True}\n',encoding='utf-8')
    (d/'whatsapp_client.py').write_text('class WhatsAppError(Exception): pass\ndef build_template_payload(**k): return k\ndef send_template(*a,**k): raise AssertionError("Meta local no debe usarse en prueba Cloud")\n',encoding='utf-8')
    (d/'remote_agenda.py').write_text('def normalize_public_base_url(v): return str(v)\ndef start_quick_tunnel(*a,**k): return {}\ndef start_named_tunnel(*a,**k): return {}\ndef start_named_tunnel_background(*a,**k): return {}\ndef stop_managed_tunnel(*a,**k): return None\ndef tunnel_status(*a,**k): return {}\n',encoding='utf-8')
    (d/'psycopg.py').write_text('def connect(*a,**k): raise RuntimeError("stub")\n',encoding='utf-8')
    for key in ['DATABASE_URL','WHATSAPP_AUTO_CITA_AGENDADA','WHATSAPP_AUTO_RECORDATORIO_CITA','WHATSAPP_AUTO_RECORDATORIO_HOY','WHATSAPP_APPROVED_CITA_AGENDADA','WHATSAPP_APPROVED_RECORDATORIO_CITA','WHATSAPP_APPROVED_RECORDATORIO_HOY']:
        os.environ.pop(key,None)
    os.environ['RP_DATA_DIR']=str(d/'runtime-data'); sys.path.insert(0,str(d)); os.chdir(d); import app
    assert app.APP_VERSION=='4.3.61'
    assert app.WHATSAPP_APPROVED_CITA_AGENDADA and app.WHATSAPP_APPROVED_RECORDATORIO_CITA and app.WHATSAPP_APPROVED_RECORDATORIO_HOY
    assert app.WHATSAPP_AUTO_CITA_AGENDADA and app.WHATSAPP_AUTO_RECORDATORIO_CITA and app.WHATSAPP_AUTO_RECORDATORIO_HOY
    token='abc123'
    for key in ('recordatorio_cita','cita_agendada','recordatorio_hoy'):
        h=app._whatsapp_cloud_test_source_hash(key,token); assert app._whatsapp_cloud_test_parse_source_hash(h)==(key,token); assert app._whatsapp_cloud_test_approved(key)
    assert app._whatsapp_cloud_test_parse_source_hash('mobile:whatsapp-cloud-test:legacy')==('recordatorio_cita','legacy')
    assert not app._wa_cita_agendada_allowed(date(2026,8,29),'15:00',datetime(2026,8,28,20,0))
    assert not app._wa_cita_agendada_allowed(date(2026,8,29),'15:00',datetime(2026,8,28,7,0))
    assert app._wa_cita_agendada_allowed(date(2026,8,30),'15:00',datetime(2026,8,28,9,0))
    assert not app._wa_cita_agendada_allowed(date(2026,8,30),'08:00',datetime(2026,8,29,8,0))
    timeline=app._wa_timeline_for_source(source_type='appointment',source_id=1,fecha=date.today()+timedelta(days=1),hora='15:00',created_at=datetime.now(),appointment_state='PENDIENTE')
    assert timeline['items'][0]['status']=='SKIPPED_RULE'
    ok,reason=app._whatsapp_cloud_test_ready(); assert not ok and 'Neon' in reason
    user=app.User(id=1,username='admin',password_hash='',role='admin'); status=app.whatsapp_status(user); assert all(status['templates'][k]['approved'] for k in ('cita_agendada','recordatorio_cita','recordatorio_hoy'))
    with app.LocalSessionLocal() as db:
        target=date.today()+timedelta(days=(3-date.today().weekday())%7 or 7)
        item=app.ConfirmafyAgendaItem(nombre='PRUEBA',celular='593967841449',fecha=target,hora='08:00',duracion=20,source_hash='mobile:whatsapp-cloud-test:recordatorio_hoy:abc')
        db.add(item); db.commit(); week=app.agenda_week(anchor=target,db=db,user=user)
        assert not any((r.get('staged') or {}).get('nombre')=='PRUEBA' for day in week['days'] for r in day['appointments'])
    for name in ('local_engine','cloud_engine'):
        engine=getattr(app,name,None)
        if engine is not None: engine.dispose()
    os.chdir(START_CWD)
    try: sys.path.remove(str(d))
    except ValueError: pass
print('V461_BEHAVIOR_OK',meta['app_size'],meta['app_sha256'])
