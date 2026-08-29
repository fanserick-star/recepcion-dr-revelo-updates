from __future__ import annotations
import ast, hashlib, json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v486'
OUT=ROOT/'updates'/'v487'
VERSION='4.3.87'
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

CSS=r'''/* v4.3.87 — iconos vectoriales compatibles */
.v487-section-svg{width:18px;height:18px;display:block;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.v481-section-icon.v487-identity-icon{color:#356da7!important;background:#eaf3fd!important}
.v481-section-icon.v487-contact-icon{color:#397b58!important;background:#edf8f1!important}
.v486-place-in-contact{position:relative}
.v486-place-in-contact>label:first-child,.v486-place-in-contact .field-label:first-child{display:flex!important;align-items:center!important;gap:5px!important}
.v487-place-label-icon{width:12px;height:12px;display:inline-block;vertical-align:-2px;stroke:#9b6a26;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
'''

JS=r''';(()=>{
 if(window.__v487Icons)return;window.__v487Icons=true;
 const idSvg='<svg class="v487-section-svg" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2.5"></rect><circle cx="8" cy="10" r="2.1"></circle><path d="M5.8 15c.8-1.6 3.6-1.6 4.4 0"></path><path d="M13 9h5M13 12h5M13 15h3.5"></path></svg>';
 const phoneSvg='<svg class="v487-section-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M7.2 4.5 9.6 8 8.1 9.7c1.1 2.2 2.9 4 5.1 5.1l1.7-1.5 3.6 2.4-.6 3c-.2.9-1 1.5-1.9 1.4C9.4 19.3 4.7 14.6 3.9 8c-.1-.9.5-1.7 1.4-1.9l1.9-.4z"></path></svg>';
 const pinSvg='<svg class="v487-place-label-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11z"></path><circle cx="12" cy="10" r="2"></circle></svg>';
 function applyIcons(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact');
   const ii=identity?.querySelector('.v481-section-icon');if(ii){ii.classList.add('v487-identity-icon');ii.innerHTML=idSvg}
   const ci=contact?.querySelector('.v481-section-icon');if(ci){ci.classList.add('v487-contact-icon');ci.innerHTML=phoneSvg}
   const place=contact?.querySelector('.v486-place-in-contact,.v481-role-place');
   if(place&&!place.dataset.v487Pin){
     place.dataset.v487Pin='1';
     const label=place.querySelector('label,.field-label');
     if(label&&!label.querySelector('.v487-place-label-icon'))label.insertAdjacentHTML('afterbegin',pinSvg);
   }
 }
 const oldNew=window.newPatient;if(typeof oldNew==='function')window.newPatient=function(){const r=oldNew.apply(this,arguments);setTimeout(applyIcons,25);setTimeout(applyIcons,110);return r};
 const oldEdit=window.editPatientFromBilling;if(typeof oldEdit==='function')window.editPatientFromBilling=function(){const r=oldEdit.apply(this,arguments);setTimeout(applyIcons,25);setTimeout(applyIcons,110);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(applyIcons,100),{once:true});else setTimeout(applyIcons,100);
})();'''

AUTO_HELPER=r'''def _auto_link_safe_review_duplicates(db: Session, user: User) -> dict:
    """Fusiona automáticamente duplicados actuales con similitud >= 75%.

    Se ejecuta únicamente al abrir Pacientes -> Por revisar. Conserva la ficha
    con más historial/datos y usa la fusión completa para trasladar atenciones y
    citas. Dos cédulas válidas diferentes nunca se fusionan automáticamente.
    """
    if is_offline_db(db):
        return {"linked": 0, "skipped": True, "threshold": 0.75}
    patients = list(db.scalars(select(Patient).order_by(Patient.id)))
    if len(patients) < 2:
        return {"linked": 0, "skipped": False, "threshold": 0.75}

    visit_counts = {int(pid): int(n or 0) for pid, n in db.execute(
        select(Visit.patient_id, func.count(Visit.id)).group_by(Visit.patient_id)
    ).all()}
    appointment_counts = {int(pid): int(n or 0) for pid, n in db.execute(
        select(Appointment.patient_id, func.count(Appointment.id)).where(Appointment.patient_id.is_not(None)).group_by(Appointment.patient_id)
    ).all()}

    def valid_ident(p):
        d = re.sub(r"\D", "", str(p.cedula or ""))
        if len(d) not in {10, 13} or not d or set(d) == {"0"}:
            return ""
        return d

    def completeness(p):
        return sum(bool(str(getattr(p, f, None) or "").strip()) for f in ("cedula", "fecha_nacimiento", "celular", "correo", "lugar"))

    pairs=[]
    for i, left in enumerate(patients):
        for right in patients[i+1:]:
            lc, rc = valid_ident(left), valid_ident(right)
            if lc and rc and lc != rc:
                continue
            score, why = patient_similarity(left, right)
            if float(score or 0) < 0.75:
                continue
            pairs.append((float(score), int(left.id), int(right.id), str(why or "similitud >= 75%")))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))

    linked=0
    skipped_conflict=0
    for score, aid, bid, why in pairs:
        a=db.get(Patient, aid); b=db.get(Patient, bid)
        if not a or not b or int(a.id)==int(b.id):
            continue
        ac, bc = valid_ident(a), valid_ident(b)
        if ac and bc and ac != bc:
            skipped_conflict += 1
            continue
        # Preferimos como ficha definitiva la que concentra más historia y datos.
        def rank(p):
            pid=int(p.id)
            return (visit_counts.get(pid,0), appointment_counts.get(pid,0), completeness(p), -pid)
        target, source = (a,b) if rank(a) >= rank(b) else (b,a)
        # Recalcular la similitud porque una fusión anterior pudo completar el target.
        current_score, current_why = patient_similarity(source, target)
        if float(current_score or 0) < 0.75:
            continue
        sc, tc = valid_ident(source), valid_ident(target)
        if sc and tc and sc != tc:
            skipped_conflict += 1
            continue
        try:
            result = merge_patient_confirmed(int(source.id), int(target.id), db=db, user=user)
            if result.get("deleted_source"):
                linked += 1
                tid=int(target.id)
                visit_counts[tid]=visit_counts.get(tid,0)+visit_counts.get(int(source.id),0)
                appointment_counts[tid]=appointment_counts.get(tid,0)+appointment_counts.get(int(source.id),0)
        except HTTPException:
            continue
        except Exception:
            continue
    return {"linked": linked, "skipped": False, "threshold": 0.75, "cedula_conflicts": skipped_conflict}
'''

def must_replace(s,old,new,count=1,label='reemplazo'):
    found=s.count(old)
    if found!=count: raise SystemExit(f'{label}: esperado {count}, encontrado {found}')
    return s.replace(old,new,count)

def patch_app(s):
    s=must_replace(s,'APP_VERSION = "4.3.86"','APP_VERSION = "4.3.87"',1,'version backend')
    s=must_replace(s,"const VERSION=\\'4.3.86\\';","const VERSION=\\'4.3.87\\';",1,'version visual')
    pattern=r'def _auto_link_safe_review_duplicates\(db: Session, user: User\) -> dict:.*?\n\ndef _patient_review_rows\('
    repl=AUTO_HELPER+'\n\ndef _patient_review_rows('
    s,n=re.subn(pattern,repl,s,count=1,flags=re.S)
    if n!=1: raise SystemExit(f'helper auto-link: esperado 1, encontrado {n}')
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V487_ICON_CSS = r"""'+CSS+'"""\n'+'V487_ICON_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V487_ICON_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V487_ICON_JS\n\n'+marker)
    return s.replace(marker,injected,1)

def main():
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec'); compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app); js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V487_ICON_JS' in names: js=ast.literal_eval(node.value)
            if 'V487_ICON_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('v487 ausente')
    for token in ['v487-section-svg','v487-identity-icon','v487-contact-icon','v487-place-label-icon']:
        if token not in js and token not in css: raise SystemExit('falta icono '+token)
    for token in ['threshold": 0.75','float(score or 0) < 0.75','merge_patient_confirmed','lc and rc and lc != rc','visit_counts','appointment_counts']:
        if token not in app: raise SystemExit('falta auto-link 75 '+token)
    for token in ['V486_FIX_JS','v486-place-in-contact','v486OpenAzur','Ver recibo','Reimprimir','V485_FIX_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'MutationObserver' in js: raise SystemExit('v487 no debe observar modal')
    if 'APP_VERSION = "4.3.87"' not in app or "const VERSION=\\'4.3.87\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8'); lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8'); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v487/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.87: auto-vincula duplicados con similitud desde 75% y restaura iconos vectoriales compatibles en Paciente nuevo.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
