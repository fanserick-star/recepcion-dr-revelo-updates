from __future__ import annotations
import ast, hashlib, json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v487'
OUT=ROOT/'updates'/'v488'
VERSION='4.3.88'
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

CSS=r'''/* v4.3.88 — iconos visibles en acciones de Inicio */
.v478-home-actions>button{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:5px!important}
.v488-home-action-svg{width:13px;height:13px;display:block;flex:0 0 13px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.v486-home-delete .v488-home-action-svg{width:12px;height:12px;flex-basis:12px}
@media(max-width:760px){.v478-home-actions>button{gap:4px!important}.v488-home-action-svg{width:12px;height:12px;flex-basis:12px}}
'''

JS=r''';(()=>{
 if(window.__v488ReviewCopy)return;window.__v488ReviewCopy=true;
 function fixReviewCopy(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const title=[...modal.querySelectorAll('h1,h2,h3')].find(x=>String(x.textContent||'').toLowerCase().includes('revisar paciente'));
   if(!title)return;
   const p=title.parentElement?.querySelector('p')||title.nextElementSibling;
   if(p&&String(p.textContent||'').toLowerCase().includes('fusion'))p.textContent='Las coincidencias de 75% o más se vinculan automáticamente. Las menores quedan para revisión manual.';
 }
 const oldOpen=window.openModal;
 if(typeof oldOpen==='function')window.openModal=function(){const r=oldOpen.apply(this,arguments);setTimeout(fixReviewCopy,0);setTimeout(fixReviewCopy,50);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(fixReviewCopy,100),{once:true});else setTimeout(fixReviewCopy,100);
})();'''

AUTO_HELPER=r'''def _auto_link_safe_review_duplicates(db: Session, user: User) -> dict:
    """Auto-vincula Por revisar con umbral >=75%, incluidas coincidencias históricas.

    - Actual↔actual: fusiona fichas y conserva la que tenga más historial/datos.
    - Histórico↔actual: crea el vínculo local y completa huecos seguros mediante
      la misma rutina manual existente.
    - Dos cédulas válidas diferentes nunca se unen automáticamente.
    """
    if is_offline_db(db):
        return {"linked": 0, "historical_linked": 0, "skipped": True, "threshold": 0.75}

    patients = list(db.scalars(select(Patient).order_by(Patient.id)))
    visit_counts = {int(pid): int(n or 0) for pid, n in db.execute(
        select(Visit.patient_id, func.count(Visit.id)).group_by(Visit.patient_id)
    ).all()}
    appointment_counts = {int(pid): int(n or 0) for pid, n in db.execute(
        select(Appointment.patient_id, func.count(Appointment.id)).where(Appointment.patient_id.is_not(None)).group_by(Appointment.patient_id)
    ).all()}

    def valid_ident(p):
        d = re.sub(r"\D", "", str(p.cedula or ""))
        if len(d) not in {10, 13} or not d or set(d) == {"0"}: return ""
        return d

    def completeness(p):
        return sum(bool(str(getattr(p, f, None) or "").strip()) for f in ("cedula", "fecha_nacimiento", "celular", "correo", "lugar"))

    pairs=[]
    for i, left in enumerate(patients):
        for right in patients[i+1:]:
            lc, rc = valid_ident(left), valid_ident(right)
            if lc and rc and lc != rc: continue
            score, why = patient_similarity(left, right)
            if float(score or 0) < 0.75: continue
            pairs.append((float(score), int(left.id), int(right.id), str(why or "similitud >= 75%")))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))

    linked=0; skipped_conflict=0
    for score, aid, bid, why in pairs:
        a=db.get(Patient, aid); b=db.get(Patient, bid)
        if not a or not b or int(a.id)==int(b.id): continue
        ac, bc = valid_ident(a), valid_ident(b)
        if ac and bc and ac != bc:
            skipped_conflict += 1; continue
        def rank(p):
            pid=int(p.id)
            return (visit_counts.get(pid,0), appointment_counts.get(pid,0), completeness(p), -pid)
        target, source = (a,b) if rank(a) >= rank(b) else (b,a)
        current_score, current_why = patient_similarity(source, target)
        if float(current_score or 0) < 0.75: continue
        sc, tc = valid_ident(source), valid_ident(target)
        if sc and tc and sc != tc:
            skipped_conflict += 1; continue
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

    # La .87 solo procesaba Patient↔Patient. Releemos las fichas supervivientes y
    # aplicamos el MISMO 75% a los candidatos históricos 2020-2025 que aparecen
    # en Por revisar. Vincular histórico no crea otro Patient ni borra historia.
    historical_linked=0; historical_conflicts=0
    try:
        db.expire_all()
        current=list(db.scalars(select(Patient).order_by(Patient.id)))
        historical_matches=_historical_review_matches(current, per_patient=12)
        for p in current:
            for item in historical_matches.get(int(p.id), []):
                score=float(item.get("similarity") or 0)
                if score < 0.75: continue
                hid=int(item.get("historical_id") or 0)
                if not hid: continue
                try:
                    result=link_historical_to_patient(int(p.id), hid, db=db, user=user)
                    if result.get("ok"):
                        historical_linked += 1
                except HTTPException as exc:
                    if int(getattr(exc, "status_code", 0) or 0) == 409:
                        historical_conflicts += 1
                    continue
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "linked": linked,
        "historical_linked": historical_linked,
        "skipped": False,
        "threshold": 0.75,
        "cedula_conflicts": skipped_conflict,
        "historical_conflicts": historical_conflicts,
    }
'''

HOME_BLOCK=r'''  function homeActionIcon(kind){
    if(kind==='receipt')return '<svg class="v488-home-action-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3z"></path><path d="M9 8h6M9 12h6M9 16h4"></path></svg>';
    if(kind==='print')return '<svg class="v488-home-action-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8V3h10v5"></path><rect x="5" y="14" width="14" height="7" rx="1.5"></rect><path d="M5 16H3V9h18v7h-2"></path><circle cx="18" cy="11.5" r=".7"></circle></svg>';
    return '<svg class="v488-home-action-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"></path></svg>';
  }
  function homeMore(v){const id=Number(v?.id||0),fecha=String(v?.fecha||selectedHomeDate||'').slice(0,10);return `<button class="v486-home-delete" type="button" onclick="deleteVisitFromHome(${id},'${eh(fecha)}')">${homeActionIcon('trash')}<span>Borrar</span></button>`}
  function homeActions(g,fecha,primary){const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||'').trim());const pid=Number(g.patient?.id||0);return `<div class="v478-home-actions">${hasConsultation?`<button type="button" onclick="viewReceiptFromHome(${pid},'${eh(fecha)}')">${homeActionIcon('receipt')}<span>Ver recibo</span></button><button type="button" onclick="reprintReceiptFromHome(${pid},'${eh(fecha)}')">${homeActionIcon('print')}<span>Reimprimir</span></button>`:''}${homeMore(primary)}</div>`}
  function remasterHomeTable'''


def must_replace(s,old,new,count=1,label='reemplazo'):
    found=s.count(old)
    if found!=count: raise SystemExit(f'{label}: esperado {count}, encontrado {found}')
    return s.replace(old,new,count)


def patch_app(s):
    s=must_replace(s,'APP_VERSION = "4.3.87"','APP_VERSION = "4.3.88"',1,'version backend')
    s=must_replace(s,"const VERSION=\\'4.3.87\\';","const VERSION=\\'4.3.88\\';",1,'version visual')

    pattern=r'def _auto_link_safe_review_duplicates\(db: Session, user: User\) -> dict:.*?\n\ndef _patient_review_rows\('
    repl=AUTO_HELPER+'\n\ndef _patient_review_rows('
    s,n=re.subn(pattern,lambda _m: repl,s,count=1,flags=re.S)
    if n!=1: raise SystemExit(f'helper auto-link: esperado 1, encontrado {n}')

    pattern=r'  function homeMore\(v\)\{.*?\n  function remasterHomeTable'
    s,n=re.subn(pattern,lambda _m: HOME_BLOCK,s,count=1,flags=re.S)
    if n!=1: raise SystemExit(f'iconos Inicio: esperado 1, encontrado {n}')

    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V488_HOME_CSS = r"""'+CSS+'"""\n'+'V488_REVIEW_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V488_HOME_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V488_REVIEW_JS\n\n'+marker)
    return s.replace(marker,injected,1)


def main():
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec'); compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app); js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V488_REVIEW_JS' in names: js=ast.literal_eval(node.value)
            if 'V488_HOME_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('v488 ausente')

    for token in ['historical_matches=_historical_review_matches','link_historical_to_patient','score < 0.75','historical_linked']:
        if token not in app: raise SystemExit('falta historico 75 '+token)
    for token in ['homeActionIcon','v488-home-action-svg','Ver recibo','Reimprimir','Borrar']:
        if token not in app and token not in css: raise SystemExit('falta icono Inicio '+token)
    for token in ['Las coincidencias de 75% o más','oldOpen','fixReviewCopy']:
        if token not in js: raise SystemExit('falta texto revisar '+token)
    for token in ['V487_ICON_JS','v487-azur-loading','Revisando AZUR','V486_FIX_JS','v486OpenAzur','v486-place-in-contact','V485_FIX_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'MutationObserver' in js: raise SystemExit('v488 no debe observar modal')
    if 'APP_VERSION = "4.3.88"' not in app or "const VERSION=\\'4.3.88\\';" not in app: raise SystemExit('version incorrecta')

    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8'); lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8'); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v488/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.88: vincula también coincidencias históricas desde 75% y restaura iconos vectoriales en las acciones de Inicio.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
