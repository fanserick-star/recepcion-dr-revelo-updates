from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v482'
OUT=ROOT/'updates'/'v484'
VERSION='4.3.84'
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
        name=f'{prefix}{i+1}'; (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline=''); names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text: raise SystemExit('reconstruccion invalida '+prefix)
    return names

CSS=r'''
/* v4.3.84 — hotfix seguro + pulido de Nuevo paciente */
#modal .modalbox.v481-patient-modal{width:min(730px,94vw)!important;max-height:90vh!important;padding:18px 20px 16px!important}
.v481-patient-modal .v481-remastered-form{gap:10px!important}
.v481-patient-modal .modal-form-heading h2{font-size:22px!important}
.v481-patient-modal .modal-form-heading p{font-size:10px!important}
.v481-section{gap:8px 11px!important;padding:11px 12px!important;border-radius:13px!important}
.v481-section-head{padding-bottom:6px!important;margin-bottom:0!important;align-items:center!important}
.v481-section-head b{font-size:9px!important;letter-spacing:.1em!important}
.v481-section-head span{font-size:8.7px!important}
.v481-section-head .v481-section-icon{width:30px!important;height:30px!important;border-radius:10px!important;font-size:15px!important;background:#eef5fd!important}
.v481-identity{border-left:3px solid #8fb4dc!important}
.v481-contact{border-left:3px solid #9bcbb1!important}
.v484-location{grid-column:1/-1!important;display:grid!important;grid-template-columns:1fr!important;border-left:3px solid #d2b36f!important;background:#fffdf8!important}
.v484-location .v481-role-place{grid-column:1/-1!important}
.v484-location .v481-role-place input{width:100%!important}
.v481-patient-modal input:not([type="checkbox"]),.v481-patient-modal textarea,.v481-patient-modal select{min-height:40px!important;padding:8px 10px!important;font-size:12px!important;border-radius:10px!important}
.v481-role-id input,.v481-role-name input{font-size:12.5px!important;font-weight:750!important;letter-spacing:0!important}
.v481-role-id input::placeholder,.v481-role-name input::placeholder{font-size:10.5px!important;font-weight:600!important;letter-spacing:0!important;color:#8a96a6!important;opacity:1!important}
.v481-role-phone input::placeholder,.v481-role-email input::placeholder,.v481-role-place input::placeholder,.v481-role-birth input::placeholder{font-size:10.5px!important;font-weight:550!important;color:#929dac!important;opacity:1!important}
.v481-id-status{min-height:29px!important;padding:6px 8px!important;font-size:9px!important}
.v481-age-pill{font-size:8.5px!important;padding:3px 7px!important}
.v481-role-notes{display:none!important}
.v484-hide-more{display:none!important}
.v484-date-error{display:none;margin-top:4px;font-size:8.5px;font-weight:750;color:#a44d45}
.v484-date-error.show{display:block}
.v484-date-invalid{border-color:#d7847d!important;box-shadow:0 0 0 2px rgba(190,75,65,.08)!important}
.v481-patient-modal .actions,.v481-patient-modal .form-actions,.v481-patient-modal .modal-actions{padding-top:8px!important}
.v481-create-btn{min-height:37px!important;font-size:10px!important}
@media(max-width:680px){#modal .modalbox.v481-patient-modal{width:94vw!important;padding:15px!important}.v481-section{padding:10px!important}}
'''

JS=r''';(()=>{
 if(window.__v484PatientHotfix)return;window.__v484PatientHotfix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function parseDMY(v){
   const m=/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(v||'').trim());if(!m)return null;
   const d=Number(m[1]),mo=Number(m[2]),y=Number(m[3]);if(y<1900||y>new Date().getFullYear()||mo<1||mo>12||d<1||d>31)return null;
   const x=new Date(y,mo-1,d);if(x.getFullYear()!==y||x.getMonth()!==mo-1||x.getDate()!==d)return null;
   return {d,mo,y,iso:`${String(y).padStart(4,'0')}-${String(mo).padStart(2,'0')}-${String(d).padStart(2,'0')}`,display:`${String(d).padStart(2,'0')}/${String(mo).padStart(2,'0')}/${String(y).padStart(4,'0')}`};
 }
 function isoToDMY(v){const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v||''));return m?`${m[3]}/${m[2]}/${m[1]}`:String(v||'')}
 function age(p){if(!p)return null;const t=new Date();let a=t.getFullYear()-p.y;if(t.getMonth()+1<p.mo||(t.getMonth()+1===p.mo&&t.getDate()<p.d))a--;return a>=0&&a<130?a:null}
 function sectionHead(title,subtitle,icon){const h=document.createElement('div');h.className='v481-section-head';h.innerHTML=`<div><b>${title}</b><span>${subtitle}</span></div><span class="v481-section-icon" aria-hidden="true">${icon}</span>`;return h}
 function findSave(modal){return [...modal.querySelectorAll('button')].reverse().find(b=>/guardar|crear paciente|registrar paciente/.test(norm(b.textContent)))||null}
 function polishOnce(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return false;
   const root=modal.querySelector('.v481-remastered-form');if(!root||root.dataset.v484Polished==='1')return false;
   const cedula=root.querySelector('.v481-role-id input'),name=root.querySelector('.v481-role-name input');if(!cedula||!name)return false;
   root.dataset.v484Polished='1';modal.classList.add('v481-patient-modal');
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact');
   const ii=identity?.querySelector('.v481-section-icon');if(ii)ii.textContent='🪪';
   const ci=contact?.querySelector('.v481-section-icon');if(ci)ci.textContent='☎';
   const heading=modal.querySelector('.modal-form-heading p');if(heading)heading.textContent='Registra al paciente y continúa a su atención.';
   cedula.placeholder='Ingrese 10 dígitos';name.placeholder='Apellidos y nombres';

   const placeWrap=root.querySelector('.v481-role-place'),notesWrap=root.querySelector('.v481-role-notes');
   if(notesWrap)notesWrap.style.display='none';
   if(placeWrap){
     let sec=root.querySelector('.v484-location');
     if(!sec){sec=document.createElement('section');sec.className='v481-section v484-location';sec.appendChild(sectionHead('LUGAR','Ciudad o sector del paciente','📍'));
       const actions=root.querySelector(':scope > .actions,:scope > .form-actions,:scope > .modal-actions')||root.querySelector('.actions,.form-actions,.modal-actions');
       const more=root.querySelector(':scope > .v481-more-details')||root.querySelector('.v481-more-details');root.insertBefore(sec,actions||more||null)}
     sec.appendChild(placeWrap);const p=placeWrap.querySelector('input');if(p)p.placeholder='Ciudad o sector';
   }
   for(const det of root.querySelectorAll('.v481-more-details')){
     const useful=[...det.querySelectorAll('input,textarea,select')].filter(el=>!el.closest('.v481-role-notes')&&!el.closest('.v481-role-place'));
     if(!useful.length)det.classList.add('v484-hide-more');
   }

   const birth=root.querySelector('.v481-role-birth input');
   if(birth&&birth.dataset.v484Manual!=='1'){
     birth.dataset.v484Manual='1';const initial=isoToDMY(birth.value);birth.type='text';birth.value=initial;birth.placeholder='dd/mm/aaaa';birth.inputMode='numeric';birth.maxLength=10;birth.autocomplete='off';
     const err=document.createElement('small');err.className='v484-date-error';err.textContent='Fecha inválida · usa dd/mm/aaaa';birth.parentElement?.appendChild(err);
     const pill=root.querySelector('.v481-age-pill');
     const render=()=>{const raw=birth.value.trim(),p=parseDMY(raw);birth.classList.toggle('v484-date-invalid',!!raw&&!p);err.classList.toggle('show',!!raw&&!p);if(pill){const a=age(p);pill.textContent=a===null?'Edad —':`Edad: ${a} año${a===1?'':'s'}`}};
     birth.addEventListener('input',()=>{let d=String(birth.value||'').replace(/\D/g,'').slice(0,8);if(d.length>4)d=d.slice(0,2)+'/'+d.slice(2,4)+'/'+d.slice(4);else if(d.length>2)d=d.slice(0,2)+'/'+d.slice(2);birth.value=d;render()});birth.addEventListener('blur',render);render();
     const save=findSave(modal);if(save&&!save.dataset.v484DateGuard){save.dataset.v484DateGuard='1';save.addEventListener('click',e=>{const raw=birth.value.trim();if(!raw)return;const p=parseDMY(raw);if(!p){e.preventDefault();e.stopImmediatePropagation();render();birth.focus();return}birth.value=p.iso;setTimeout(()=>{if(document.body.contains(birth)){birth.value=p.display;render()}},700)},true)}
   }
   return true;
 }
 const previousExport=window.v481RemasterPatient;
 if(typeof previousExport==='function')window.v481RemasterPatient=function(){const r=previousExport.apply(this,arguments);queueMicrotask(polishOnce);setTimeout(polishOnce,30);return r};
 const previousNew=window.newPatient;
 if(typeof previousNew==='function')window.newPatient=async function(){const r=await previousNew.apply(this,arguments);setTimeout(polishOnce,0);setTimeout(polishOnce,60);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(polishOnce,80),{once:true});else setTimeout(polishOnce,80);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.82"')!=1: raise SystemExit('APP_VERSION .82 no encontrado')
    s=s.replace('APP_VERSION = "4.3.82"','APP_VERSION = "4.3.84"',1)
    visual="const VERSION=\\'4.3.82\\';"
    if visual not in s: raise SystemExit('version visual .82 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.84\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V484_PATIENT_CSS = r"""'+CSS+'"""\n'+'V484_PATIENT_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V484_PATIENT_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V484_PATIENT_JS\n\n'+marker)
    return s.replace(marker,injected,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V484_PATIENT_JS' in names: js=ast.literal_eval(node.value)
            if 'V484_PATIENT_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('v484 ausente')
    for token in ['🪪','📍','dd/mm/aaaa','parseDMY','v484-location','v484DateGuard','previousNew','previousExport']:
        if token not in js: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v484 no debe usar MutationObserver')
    for token in ['v481-role-notes','v484-location','font-size:10.5px','width:min(730px']:
        if token not in css: raise SystemExit('falta css '+token)
    for token in ['V482_HOTFIX_JS','Emitir por lotes','V481_PATIENT_JS','validEcuadorCedula','V480_POLISH_JS','data-v480-zero-rejected','V476_JS','b.estado = "EMITIDA"']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'V483_PATIENT_JS' in app: raise SystemExit('no se debe heredar el overlay defectuoso v483')
    if 'APP_VERSION = "4.3.84"' not in app or "const VERSION=\\'4.3.84\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8');lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v484/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.84: corrige el bloqueo al abrir Paciente nuevo y conserva el pulido visual sin observadores en bucle.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
