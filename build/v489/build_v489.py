from __future__ import annotations
import hashlib, json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v488'
OUT=ROOT/'updates'/'v489'
VERSION='4.3.89'
LAUNCHER_VERSION='4.3.76-standalone-3'

def joined(prefix,n):
    ps=sorted(SRC.glob(prefix+'*'),key=lambda p:int(p.name.replace(prefix,'')))
    if len(ps)!=n: raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(ps)}')
    return ''.join(p.read_text(encoding='utf-8') for p in ps)

def sha(b): return hashlib.sha256(b).hexdigest()

def write_parts(text,prefix,n):
    OUT.mkdir(parents=True,exist_ok=True)
    for p in OUT.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/n); names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text:
        raise SystemExit('reconstruccion invalida '+prefix)
    return names

AUTO_HELPER=r'''def _auto_link_safe_review_duplicates(db: Session, user: User) -> dict:
    """Auto-vincula Por revisar con umbral >=75%.

    Los históricos 2020-2025 viven solo en SQLite, así que se pueden vincular
    incluso cuando la pantalla Por revisar está leyendo la copia local. Una misma
    ficha actual puede absorber todos sus históricos >=75% en una sola apertura.
    La cédula histórica nunca reemplaza la cédula de la ficha actual.
    """
    local_read = is_offline_db(db)
    patients = list(db.scalars(select(Patient).order_by(Patient.id)))

    # Actual↔actual requiere la base principal para mover atenciones/citas. Se
    # conserva la protección de cédulas distintas porque fusionar dos Patients
    # actuales sí sería destructivo. Esta rama no corre en el GET local.
    linked=0; skipped_conflict=0
    if not local_read:
        visit_counts = {int(pid): int(n or 0) for pid, n in db.execute(
            select(Visit.patient_id, func.count(Visit.id)).group_by(Visit.patient_id)
        ).all()}
        appointment_counts = {int(pid): int(n or 0) for pid, n in db.execute(
            select(Appointment.patient_id, func.count(Appointment.id)).where(Appointment.patient_id.is_not(None)).group_by(Appointment.patient_id)
        ).all()}
        def valid_ident(p):
            d=re.sub(r"\D","",str(p.cedula or ""))
            return d if len(d) in {10,13} and d and set(d)!={"0"} else ""
        def completeness(p):
            return sum(bool(str(getattr(p,f,None) or "").strip()) for f in ("cedula","fecha_nacimiento","celular","correo","lugar"))
        pairs=[]
        for i,left in enumerate(patients):
            for right in patients[i+1:]:
                lc,rc=valid_ident(left),valid_ident(right)
                if lc and rc and lc!=rc: continue
                score,why=patient_similarity(left,right)
                if float(score or 0)<0.75: continue
                pairs.append((float(score),int(left.id),int(right.id),str(why or "similitud >= 75%")))
        pairs.sort(key=lambda x:(-x[0],x[1],x[2]))
        for _score,aid,bid,_why in pairs:
            a=db.get(Patient,aid); b=db.get(Patient,bid)
            if not a or not b or int(a.id)==int(b.id): continue
            ac,bc=valid_ident(a),valid_ident(b)
            if ac and bc and ac!=bc:
                skipped_conflict+=1; continue
            def rank(p):
                pid=int(p.id)
                return (visit_counts.get(pid,0),appointment_counts.get(pid,0),completeness(p),-pid)
            target,source=(a,b) if rank(a)>=rank(b) else (b,a)
            score,_=patient_similarity(source,target)
            if float(score or 0)<0.75: continue
            try:
                result=merge_patient_confirmed(int(source.id),int(target.id),db=db,user=user)
                if result.get("deleted_source"):
                    linked+=1
                    tid=int(target.id)
                    visit_counts[tid]=visit_counts.get(tid,0)+visit_counts.get(int(source.id),0)
                    appointment_counts[tid]=appointment_counts.get(tid,0)+appointment_counts.get(int(source.id),0)
            except Exception:
                continue

    # Histórico↔actual: SIEMPRE puede ejecutarse porque el vínculo es local.
    # Se enlazan todos los candidatos >=75%, aunque sean varios para el mismo
    # paciente y aunque el histórico solo tenga un nombre + un apellido.
    historical_linked=0
    try:
        current=list(db.scalars(select(Patient).order_by(Patient.id)))
        historical_matches=_historical_review_matches(current,per_patient=24)
        for p in current:
            for item in historical_matches.get(int(p.id),[]):
                if float(item.get("similarity") or 0)<0.75: continue
                hid=int(item.get("historical_id") or 0)
                if not hid: continue
                try:
                    with LocalSessionLocal() as ldb:
                        h=ldb.get(HistoricalPatient,hid)
                        if not h: continue
                        source_key=str(h.source_key)
                    _historical_link_patient(source_key,int(p.id))
                    historical_linked+=1
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "linked": linked,
        "historical_linked": historical_linked,
        "skipped": False,
        "threshold": 0.75,
        "local_review": bool(local_read),
        "cedula_conflicts": skipped_conflict,
    }
'''

def patch_historical_review(s):
    pat=r'def _historical_review_matches\(patients: list\[Patient\], per_patient: int = 6\) -> dict\[int, list\[dict\]\]:.*?\n\ndef _confirmafy_patient_status_map'
    m=re.search(pat,s,re.S)
    if not m: raise SystemExit('no se encontro _historical_review_matches')
    block=m.group(0)
    old='''            # Cédulas distintas son evidencia suficiente para no sugerir una fusión.\n            if p_ced and h_ceds and p_ced not in h_ceds:\n                continue\n'''
    if old not in block: raise SystemExit('no se encontro barrera de cedula historica')
    block=block.replace(old,'            # v4.3.89: la cédula histórica no bloquea el vínculo por similitud; la ficha actual conserva su cédula.\n',1)
    if 'elif score >= 0.78:' not in block: raise SystemExit('no se encontro umbral historico 0.78')
    block=block.replace('elif score >= 0.78:','elif score >= 0.75:',1)
    return s[:m.start()]+block+s[m.end():]

def patch_app(s):
    if s.count('APP_VERSION = "4.3.88"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.88"','APP_VERSION = "4.3.89"',1)
    if s.count("const VERSION=\\'4.3.88\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.88\\';","const VERSION=\\'4.3.89\\';",1)
    s=patch_historical_review(s)
    pat=r'def _auto_link_safe_review_duplicates\(db: Session, user: User\) -> dict:.*?\n\ndef _patient_review_rows\('
    s,n=re.subn(pat,lambda _m:AUTO_HELPER+'\n\ndef _patient_review_rows(',s,count=1,flags=re.S)
    if n!=1: raise SystemExit(f'helper auto-link: esperado 1, encontrado {n}')
    return s

def main():
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec'); compile(launcher,'ABRIR_RECEPCION.py','exec')
    helper=re.search(r'def _auto_link_safe_review_duplicates.*?\n\ndef _patient_review_rows',app,re.S)
    hist=re.search(r'def _historical_review_matches.*?\n\ndef _confirmafy_patient_status_map',app,re.S)
    if not helper or not hist: raise SystemExit('bloques de validacion ausentes')
    hb=helper.group(0); hh=hist.group(0)
    for token in ['local_read = is_offline_db(db)','historical_matches=_historical_review_matches(current,per_patient=24)','_historical_link_patient(source_key,int(p.id))','historical_linked']:
        if token not in hb: raise SystemExit('falta '+token)
    if 'if is_offline_db(db):\n        return' in hb: raise SystemExit('todavia salta el GET local')
    if 'p_ced and h_ceds and p_ced not in h_ceds' in hh: raise SystemExit('todavia bloquea cedula historica')
    if 'elif score >= 0.75:' not in hh: raise SystemExit('umbral historico no es 75')
    for token in ['V488_HOME_CSS','v488-home-action-svg','V487_ICON_JS','Revisando AZUR','V486_FIX_JS','v486OpenAzur','V485_FIX_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.89"' not in app or "const VERSION=\\'4.3.89\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode(); lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode(); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v489/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.89: vincula todos los históricos con 75% o más desde la copia local, incluso varios por paciente y nombres cortos.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'
    (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='')
    (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
