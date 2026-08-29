from __future__ import annotations
import ast, hashlib, json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v485'
OUT=ROOT/'updates'/'v486'
VERSION='4.3.86'
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

CSS=r'''/* v4.3.86 — Paciente nuevo + Inicio + acceso AZUR */
.v481-contact{grid-template-columns:repeat(2,minmax(0,1fr))!important}
.v481-contact .v486-place-in-contact{grid-column:1/-1!important;margin-top:1px!important}
.v481-contact .v486-place-in-contact input{width:100%!important}
.v484-location{display:none!important}
.v486-home-delete{border-color:#efd0cd!important;color:#99453f!important;background:#fff7f6!important}
.v486-home-delete:hover{background:#ffefed!important}
#facturacion .v486-azur-link{display:inline-flex!important;align-items:center!important;gap:6px!important;min-height:34px!important;padding:7px 11px!important;border:1px solid #cfdced!important;border-radius:10px!important;background:#f5f9ff!important;color:#315f94!important;font-size:9.5px!important;font-weight:900!important;cursor:pointer!important}
#facturacion .v486-azur-link:hover{background:#eaf3ff!important}
'''

JS=r''';(()=>{
 if(window.__v486Fixes)return;window.__v486Fixes=true;
 const domains=new Set(['@gmail.com','@hotmail.com','@outlook.com','@yahoo.com']);
 function patientFix(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const contact=modal.querySelector('.v481-contact');
   const location=modal.querySelector('.v484-location');
   const place=(location?.querySelector('.v481-role-place'))||modal.querySelector('.v481-role-place');
   if(contact&&place&&!contact.contains(place)){contact.appendChild(place);place.classList.add('v486-place-in-contact');if(location)location.remove()}
   if(contact&&!contact.dataset.v486EmailShortcuts){
     contact.dataset.v486EmailShortcuts='1';
     contact.addEventListener('click',ev=>{
       const b=ev.target.closest('button');if(!b)return;
       const domain=String(b.textContent||'').trim().toLowerCase();if(!domains.has(domain))return;
       const email=contact.querySelector('.v481-role-email input,input[type="email"]');if(!email)return;
       ev.preventDefault();ev.stopImmediatePropagation();
       let local=String(email.value||'').trim().toLowerCase().split('@')[0].replace(/\s+/g,'');
       if(!local){email.focus();return}
       email.value=local+domain;
       email.dispatchEvent(new Event('input',{bubbles:true}));email.dispatchEvent(new Event('change',{bubbles:true}));
       email.focus();try{email.setSelectionRange(email.value.length,email.value.length)}catch(_e){}
     },true);
   }
 }
 async function openAzur(){
   try{if(typeof window.api==='function')await window.api('/api/open-external/azur',{method:'POST',body:'{}'});else await fetch('/api/open-external/azur',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'})}
   catch(e){alert(e?.message||'No se pudo abrir AZUR')}
 }
 function ensureAzurButton(){
   const sec=document.querySelector('#facturacion');if(!sec||sec.querySelector('#v486OpenAzur'))return;
   let row=sec.querySelector('.billing-title-row')||sec.querySelector('.page-title-row')||sec.querySelector('h1')?.parentElement;if(!row)return;
   let actions=row.querySelector('.billing-title-actions');if(!actions){actions=document.createElement('div');actions.className='billing-title-actions';row.appendChild(actions)}
   const b=document.createElement('button');b.id='v486OpenAzur';b.type='button';b.className='external-billing-link v486-azur-link';b.textContent='↗ Abrir AZUR';b.onclick=openAzur;actions.appendChild(b);
 }
 const oldNew=window.newPatient;if(typeof oldNew==='function')window.newPatient=function(){const r=oldNew.apply(this,arguments);setTimeout(patientFix,20);setTimeout(patientFix,100);return r};
 const oldEdit=window.editPatientFromBilling;if(typeof oldEdit==='function')window.editPatientFromBilling=function(){const r=oldEdit.apply(this,arguments);setTimeout(patientFix,20);setTimeout(patientFix,100);return r};
 const oldBilling=window.loadBilling;if(typeof oldBilling==='function')window.loadBilling=async function(){const r=await oldBilling.apply(this,arguments);ensureAzurButton();return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{setTimeout(patientFix,80);setTimeout(ensureAzurButton,100)},{once:true});else{setTimeout(patientFix,80);setTimeout(ensureAzurButton,100)}
})();'''

AUTO_HELPER=r'''
def _auto_link_safe_review_duplicates(db: Session, user: User) -> dict:
    # Solo une duplicados actuales inequívocos; nunca mueve automáticamente una ficha con atenciones.
    if is_offline_db(db):
        return {"linked": 0, "skipped": True}
    patients = list(db.scalars(select(Patient).order_by(Patient.id)))
    if len(patients) < 2:
        return {"linked": 0, "skipped": False}
    visit_counts = {int(pid): int(n or 0) for pid, n in db.execute(
        select(Visit.patient_id, func.count(Visit.id)).group_by(Visit.patient_id)
    ).all()}
    def ident(p):
        d = re.sub(r"\D", "", str(p.cedula or ""))
        return d if len(d) in {10, 13} and set(d) != {"0"} else ""
    def complete(p):
        return sum(bool(getattr(p, f, None)) for f in ("cedula","fecha_nacimiento","celular","correo","lugar"))
    groups: dict[str, list[int]] = {}
    for p in patients:
        pid = int(p.id); cid = ident(p)
        if cid: groups.setdefault("I:"+cid, []).append(pid)
        name = normalize_lookup_name(p.nombre or ""); phone = normalize_lookup_phone(p.celular or "")
        if name and phone and len(re.sub(r"\D", "", phone)) >= 8:
            groups.setdefault("P:"+name+"|"+phone, []).append(pid)
    linked = 0; handled: set[int] = set()
    for key in sorted(groups, key=lambda x: (0 if x.startswith("I:") else 1, x)):
        ids = list(dict.fromkeys(groups[key]))
        if len(ids) < 2: continue
        alive = [db.get(Patient, pid) for pid in ids if pid not in handled]; alive = [p for p in alive if p is not None]
        if len(alive) < 2: continue
        target = max(alive, key=lambda p: (visit_counts.get(int(p.id), 0), complete(p), -int(p.id)))
        for source in alive:
            sid, tid = int(source.id), int(target.id)
            if sid == tid or sid in handled or visit_counts.get(sid, 0) != 0: continue
            scid, tcid = ident(source), ident(target)
            if scid and tcid and scid != tcid: continue
            exact_id = bool(scid and tcid and scid == tcid)
            exact_name_phone = normalize_lookup_name(source.nombre or "") == normalize_lookup_name(target.nombre or "") and bool(normalize_lookup_phone(source.celular or "")) and normalize_lookup_phone(source.celular or "") == normalize_lookup_phone(target.celular or "")
            if not (exact_id or exact_name_phone): continue
            try:
                result = link_duplicate_patient(sid, tid, db=db, user=user)
                if result.get("deleted_source"):
                    linked += 1; handled.add(sid)
            except HTTPException:
                continue
            except Exception:
                continue
    return {"linked": linked, "skipped": False}
'''

def must_replace(s,old,new,count=1,label='reemplazo'):
    found=s.count(old)
    if found!=count: raise SystemExit(f'{label}: esperado {count}, encontrado {found}')
    return s.replace(old,new,count)

def regex_replace(s,pattern,repl,label):
    out,n=re.subn(pattern,repl,s,count=1,flags=re.S)
    if n!=1: raise SystemExit(f'{label}: esperado 1, encontrado {n}')
    return out

def patch_app(s):
    s=must_replace(s,'APP_VERSION = "4.3.85"','APP_VERSION = "4.3.86"',1,'version backend')
    s=must_replace(s,"const VERSION=\\'4.3.85\\';","const VERSION=\\'4.3.86\\';",1,'version visual')
    old='''    "facturero": "https://app.factureromovil.com/documentos/facturas",\n}'''
    new='''    "facturero": "https://app.factureromovil.com/documentos/facturas",\n    "azur": "https://azur.com.ec/plataforma",\n}'''
    s=must_replace(s,old,new,1,'destino AZUR')
    marker='def _patient_review_rows(db: Session, limit: int = 30, confirmafy_only: bool = False) -> list[dict]:'
    if s.count(marker)!=1: raise SystemExit('marker patient review invalido')
    s=s.replace(marker,AUTO_HELPER+'\n\n'+marker,1)
    old_review='''    if mode == "review":\n        return _patient_review_rows(db, lim)'''
    new_review='''    if mode == "review":\n        _auto_link_safe_review_duplicates(db, user)\n        return _patient_review_rows(db, lim)'''
    s=must_replace(s,old_review,new_review,1,'auto vinculo review')
    pattern=r'''  function homeMore\(v\)\{.*?\n  function remasterHomeTable'''
    replacement=r'''  function homeMore(v){const id=Number(v?.id||0),fecha=String(v?.fecha||selectedHomeDate||'').slice(0,10);return `<button class="v486-home-delete" type="button" onclick="deleteVisitFromHome(${id},'${eh(fecha)}')">Borrar</button>`}
  function homeActions(g,fecha,primary){const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||'').trim());const pid=Number(g.patient?.id||0);return `<div class="v478-home-actions">${hasConsultation?`<button type="button" onclick="viewReceiptFromHome(${pid},'${eh(fecha)}')">Ver recibo</button><button type="button" onclick="reprintReceiptFromHome(${pid},'${eh(fecha)}')">Reimprimir</button>`:''}${homeMore(primary)}</div>`}
  function remasterHomeTable'''
    s=regex_replace(s,pattern,replacement,'acciones visibles Inicio')
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V486_FIX_CSS = r"""'+CSS+'"""\n'+'V486_FIX_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V486_FIX_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V486_FIX_JS\n\n'+marker)
    return s.replace(marker,injected,1)

def main():
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec'); compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app); js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V486_FIX_JS' in names: js=ast.literal_eval(node.value)
            if 'V486_FIX_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('v486 ausente')
    for token in ['v486-place-in-contact','@hotmail.com','v486OpenAzur','/api/open-external/azur']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    for token in ['_auto_link_safe_review_duplicates','exact_name_phone','_auto_link_safe_review_duplicates(db, user)','"azur": "https://azur.com.ec/plataforma"']:
        if token not in app: raise SystemExit('falta '+token)
    for token in ['Ver recibo','Reimprimir','v486-home-delete']:
        if token not in app: raise SystemExit('acciones Inicio incompletas '+token)
    hm=re.search(r'function homeMore\(v\).*?function remasterHomeTable',app,re.S)
    if not hm or '<summary class="v478-more-summary"' in hm.group(0): raise SystemExit('los puntos de Inicio siguen activos')
    for token in ['V485_FIX_JS','V484_PATIENT_JS','V482_HOTFIX_JS','V481_PATIENT_JS','V480_POLISH_JS','V476_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'MutationObserver' in js: raise SystemExit('v486 no debe observar el modal')
    if 'APP_VERSION = "4.3.86"' not in app or "const VERSION=\\'4.3.86\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8'); lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8'); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v486/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.86: integra Lugar en Contacto, corrige atajos de correo, auto-vincula duplicados seguros en Por revisar, restaura acciones visibles y añade acceso a AZUR.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
