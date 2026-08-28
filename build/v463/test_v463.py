from __future__ import annotations
import ast, hashlib, json, os, sys, tempfile
from pathlib import Path
from datetime import date, datetime

ROOT=Path(__file__).resolve().parents[2]/'updates'/'v463'
meta=json.loads((ROOT/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.63'
assert meta['base_version']=='4.3.62'
parts=sorted(ROOT.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert len(parts)==int(meta['parts_count'])
assert len(raw)==int(meta['app_size'])
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
assert hashlib.sha256((ROOT/'update_manifest.json').read_bytes()).hexdigest()==meta['manifest_sha256']
source=raw.decode('utf-8')
assert 'APP_VERSION = "4.3.63"' in source
assert "const VERSION='4.3.63';" in source
assert 'BillingRecord.estado != "EMITIDA"' in source
assert '_azur_group_key_for_rows' in source
assert '_billing_visit_ids' in source
assert 'window.alert=(message)=>prettyAlert(message)' in source
assert 'window.rpConfirm=' in source
assert 'Usar correo registrado del paciente' in source
assert 'v463Hidden' in source
assert '[:19]' in source

# JavaScript del overlay debe parsear por separado en CI; aquí verificamos que se extraiga.
tree=ast.parse(source)
consts={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'V459_SETTINGS_JS','V460_OVERLAY_JS'}:
        consts[n.targets[0].id]=ast.literal_eval(n.value)
assert set(consts)=={'V459_SETTINGS_JS','V460_OVERLAY_JS'}

START=Path.cwd()
with tempfile.TemporaryDirectory() as td:
    d=Path(td)
    (d/'app.py').write_bytes(raw)
    (d/'static').mkdir()
    (d/'static'/'index.html').write_text('<!doctype html><html><head></head><body><div id="connectionBadge"></div><section id="config"></section></body></html>',encoding='utf-8')
    (d/'azur_client.py').write_text('class AzurError(Exception): pass\ndef emit_invoice(*a,**k): raise AssertionError("No emitir facturas reales en test")\ndef query_comprobante(*a,**k): return {}\ndef mask_api_key(v): return "***" if v else ""\ndef normalize_base_url(v): return str(v).rstrip("/")\ndef test_connection(*a,**k): return {"ok":True}\n',encoding='utf-8')
    (d/'whatsapp_client.py').write_text('class WhatsAppError(Exception): pass\ndef build_template_payload(**k): return k\ndef send_template(*a,**k): raise AssertionError("No enviar WhatsApp en test")\n',encoding='utf-8')
    (d/'remote_agenda.py').write_text('def normalize_public_base_url(v): return str(v)\ndef start_quick_tunnel(*a,**k): return {}\ndef start_named_tunnel(*a,**k): return {}\ndef start_named_tunnel_background(*a,**k): return {}\ndef stop_managed_tunnel(*a,**k): return None\ndef tunnel_status(*a,**k): return {}\n',encoding='utf-8')
    (d/'psycopg.py').write_text('def connect(*a,**k): raise RuntimeError("stub")\n',encoding='utf-8')
    for key in ('DATABASE_URL','AZUR_BASE_URL','AZUR_API_KEY','RP_FORCE_OFFLINE'):
        os.environ.pop(key,None)
    os.environ['RP_DATA_DIR']=str(d/'runtime-data')
    sys.path.insert(0,str(d));os.chdir(d)
    import app
    assert app.APP_VERSION=='4.3.63'
    user=app.User(id=1,username='admin',password_hash='',role='admin')
    day=date(2026,8,28)
    with app.LocalSessionLocal() as db:
        p=app.Patient(cedula='1200000000',nombre='PACIENTE PRUEBA',correo='paciente@correo.test')
        db.add(p);db.flush()
        v_old=app.Visit(patient_id=p.id,fecha=day,tipo='N',procedimiento=None,valor=40,created_at=datetime(2026,8,28,8,0))
        db.add(v_old);db.flush()
        b_old=app.BillingRecord(visit_id=v_old.id,estado='EMITIDA',numero_factura='F-OLD',approved_at=datetime(2026,8,28,8,10),emitted_at=datetime(2026,8,28,8,15))
        db.add(b_old)
        v_new=app.Visit(patient_id=p.id,fecha=day,tipo='S',procedimiento='PROCEDIMIENTO NUEVO',valor=25,created_at=datetime(2026,8,28,10,0))
        db.add(v_new);db.flush()
        b_new=app.BillingRecord(visit_id=v_new.id,estado='PENDIENTE')
        db.add(b_new);db.commit()
        pid=int(p.id);old_id=int(v_old.id);new_id=int(v_new.id)

        opened=app.billing_group_records(db,pid,day)
        assert [v.id for _b,v in opened]==[new_id],[(b.estado,v.id) for b,v in opened]

        pending=app.billing_list(estado='PENDIENTE',db=db,user=user)
        assert [x['visit']['id'] for x in pending['items']]==[new_id]
        emitted=app.billing_list(estado='EMITIDA',desde=day,hasta=day,db=db,user=user)
        assert [x['visit']['id'] for x in emitted['items']]==[old_id]

        app.billing_approve(app.BillingGroupIn(patient_id=pid,fecha=day),db=db,user=user)
        db.refresh(b_old);db.refresh(b_new)
        assert b_old.estado=='EMITIDA' and b_old.numero_factura=='F-OLD'
        assert b_new.estado=='APROBADA' and b_new.numero_factura is None

        app.billing_emit(app.BillingEmitIn(patient_id=pid,fecha=day,numero_factura='F-NEW'),db=db,user=user)
        db.refresh(b_old);db.refresh(b_new)
        assert b_old.estado=='EMITIDA' and b_old.numero_factura=='F-OLD'
        assert b_new.estado=='EMITIDA' and b_new.numero_factura=='F-NEW'

        rows_new=[(b_new,v_new)]
        new_key=app._azur_group_key_for_rows(pid,day,rows_new)
        legacy_key=app._azur_group_key(pid,day)
        assert new_key!=legacy_key and new_key.endswith(f':{new_id}')
        rec=app.AzurEmission(group_key=new_key,patient_id=pid,fecha=day,estado='AUTORIZADA',numero_factura='F-NEW',created_at=datetime(2026,8,28,10,5))
        rec.response_json=app._azur_pack_response({'ok':True},rows_new)
        db.add(rec);db.commit();db.refresh(rec)
        frozen=app._azur_rows_from_record(db,rec)
        assert [v.id for _b,v in frozen]==[new_id]

        # Si existe una emisión heredada sin snapshot, no debe absorber una visita creada después.
        legacy=app.AzurEmission(group_key=f'{legacy_key}:legacy-test',patient_id=pid,fecha=day,estado='EN_PROCESO',created_at=datetime(2026,8,28,9,0))
        db.add(legacy);db.commit();db.refresh(legacy)
        legacy_rows=app._azur_rows_from_record(db,legacy)
        assert new_id not in [v.id for _b,v in legacy_rows]

    for name in ('local_engine','cloud_engine'):
        engine=getattr(app,name,None)
        if engine is not None: engine.dispose()
    os.chdir(START)
    try: sys.path.remove(str(d))
    except ValueError: pass

prefix='mobile:whatsapp-cloud-test:'
assert max(len(f'{prefix}{k}:'+('x'*19)) for k in ('recordatorio_cita','cita_agendada','recordatorio_hoy'))<=64
print('V463_BEHAVIOR_OK',meta['app_size'],meta['app_sha256'])
