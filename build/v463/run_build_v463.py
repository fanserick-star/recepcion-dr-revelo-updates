from pathlib import Path
import hashlib, json, runpy

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
runpy.run_path(str(HERE/'build_v463.py'),run_name='__main__')

out=ROOT/'updates'/'v463'
parts=sorted(out.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
s=b''.join(p.read_bytes() for p in parts).decode('utf-8')
old='''    # Compatibilidad con emisiones antiguas que no guardaban los ids de líneas.\n    return billing_group_records(db, int(record.patient_id), record.fecha)\n'''
new='''    # Compatibilidad con emisiones antiguas que no guardaban los ids de líneas.\n    # Congelamos por el momento en que nació la emisión: una atención creada\n    # después jamás puede entrar retroactivamente en ese comprobante.\n    if record.created_at:\n        return db.execute(\n            select(BillingRecord, Visit)\n            .join(Visit, BillingRecord.visit_id == Visit.id)\n            .where(\n                Visit.patient_id == int(record.patient_id),\n                Visit.fecha == record.fecha,\n                Visit.created_at <= record.created_at,\n            )\n            .order_by(Visit.id.asc())\n        ).all()\n    return billing_group_records(db, int(record.patient_id), record.fecha)\n'''
if s.count(old)!=1:
    raise SystemExit(f'Fallback AZUR legado: se esperaba 1 coincidencia y hubo {s.count(old)}')
s=s.replace(old,new,1)
raw=s.encode('utf-8')
PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
meta=json.loads((out/'release_meta.json').read_text(encoding='utf-8'))
meta['app_sha256']=hashlib.sha256(raw).hexdigest();meta['app_size']=len(raw);meta['parts_count']=len(chunks)
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V463_FINALIZED',len(raw),meta['app_sha256'],'parts',len(chunks))
