from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v482'
OUT=ROOT/'updates'/'v483'
VERSION='4.3.83'
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
/* v4.3.83 — pulido final de Nuevo paciente */
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
.v483-location{border-left:3px solid #d2b36f!important;background:#fffdf8!important}
.v481-patient-modal input:not([type="checkbox"]),.v481-patient-modal textarea,.v481-patient-modal select{min-height:40px!important;padding:8px 10px!important;font-size:12px!important;border-radius:10px!important}
.v481-role-id input,.v481-role-name input{font-size:12.5px!important;font-weight:750!important;letter-spacing:0!important}
.v481-role-id input::placeholder,.v481-role-name input::placeholder{font-size:10.5px!important;font-weight:600!important;letter-spacing:0!important;color:#8a96a6!important;opacity:1!important}
.v481-role-phone input::placeholder,.v481-role-email input::placeholder,.v481-role-place input::placeholder{font-size:10.5px!important;font-weight:550!important;color:#929dac!important;opacity:1!important}
.v481-id-status{min-height:29px!important;padding:6px 8px!important;font-size:9px!important}
.v481-age-pill{font-size:8.5px!important;padding:3px 7px!important}
.v483-location{grid-column:1/-1!important;display:grid!important;grid-template-columns:1fr!important}
.v483-location .v481-role-place{grid-column:1/-1!important}
.v483-location .v481-role-place input{width:100%!important}
.v481-role-notes{display:none!important}
.v483-empty-more{display:none!important}
.v481-patient-modal input[type="date"]::-webkit-calendar-picker-indicator{display:none!important;-webkit-appearance:none!important;width:0!important;height:0!important;opacity:0!important}
.v481-patient-modal input[type="date"]::-webkit-inner-spin-button{display:none!important;-webkit-appearance:none!important}
.v481-patient-modal input[type="date"]{appearance:textfield!important;-webkit-appearance:textfield!important;padding-right:10px!important}
.v481-patient-modal .actions,.v481-patient-modal .form-actions,.v481-patient-modal .modal-actions{padding-top:8px!important}
.v481-create-btn{min-height:37px!important;font-size:10px!important}
@media(max-width:680px){#modal .modalbox.v481-patient-modal{width:94vw!important;padding:15px!important}.v481-section{padding:10px!important}}
'''

JS=r''';(()=>{
 if(window.__v483PatientPolish)return;window.__v483PatientPolish=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 let busy=false;
 function labelText(el){
   const id=el?.id||'',direct=el?.closest?.('label');
   const byFor=id?[...document.querySelectorAll('label[for]')].find(l=>l.htmlFor===id):null;
   return norm([el?.name,el?.id,el?.placeholder,el?.getAttribute?.('aria-label'),direct?.textContent,byFor?.textContent].filter(Boolean).join(' '));
 }
 function field(root,words,type){
   const els=[...root.querySelectorAll('input,textarea,select')].filter(x=>!['button','submit','hidden'].includes(String(x.type||'').toLowerCase()));
   if(type){const x=els.find(el=>String(el.type||'').toLowerCase()===type&&words.some(w=>labelText(el).includes(w)));if(x)return x}
   return els.find(el=>words.some(w=>labelText(el).includes(w)))||null;
 }
 function wrapper(el,root){
   if(!el)return null;const w=el.closest('label,.field,.form-field,.form-group,.input-group,.control');
   if(w&&w!==root&&root.contains(w))return w;return el.parentElement&&el.parentElement!==root?el.parentElement:el;
 }
 function sectionHead(title,subtitle,icon){
   const h=document.createElement('div');h.className='v481-section-head';
   h.innerHTML=`<div><b>${title}</b><span>${subtitle}</span></div><span class="v481-section-icon" aria-hidden="true">${icon}</span>`;return h;
 }
 function ensureBaseRemaster(modal){
   if(modal?.querySelector('.v481-section'))return true;
   if(typeof window.v481RemasterPatient==='function'){
     try{delete modal.dataset.v481Patient;window.v481RemasterPatient(true)}catch(_e){}
   }
   return !!modal?.querySelector('.v481-section');
 }
 function disableDatePicker(birth){
   if(!birth||birth.dataset.v483ManualDate==='1')return;
   birth.dataset.v483ManualDate='1';birth.setAttribute('autocomplete','off');birth.setAttribute('inputmode','numeric');
   birth.title='Escribe la fecha manualmente en formato día/mes/año';
   birth.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();birth.focus({preventScroll:true})},true);
 }
 function movePlaceAndRemoveNotes(modal,root){
   const place=field(modal,['lugar','ciudad','sector','direccion']);
   const notes=field(modal,['notas','observacion']);
   const wPlace=wrapper(place,root),wNotes=wrapper(notes,root);
   if(wNotes){wNotes.classList.add('v481-role-notes');wNotes.style.display='none';if(notes)notes.value=''}
   let sec=modal.querySelector('.v483-location');
   if(wPlace){
     wPlace.classList.add('v481-role-place');
     if(!sec){sec=document.createElement('section');sec.className='v481-section v483-location';sec.appendChild(sectionHead('LUGAR','Ciudad o sector del paciente','📍'));
       const actions=root.querySelector(':scope > .actions,:scope > .form-actions,:scope > .modal-actions')||root.querySelector('.actions,.form-actions,.modal-actions');
       const more=root.querySelector(':scope > .v481-more-details')||root.querySelector('.v481-more-details');
       root.insertBefore(sec,actions||more||null);
     }
     if(wPlace.parentElement!==sec)sec.appendChild(wPlace);
     if(place)place.placeholder='Ciudad o sector';
   }
   for(const det of modal.querySelectorAll('.v481-more-details')){
     const visible=[...det.querySelectorAll('input,textarea,select')].filter(el=>el!==notes&&el!==place&&getComputedStyle(el).display!=='none');
     if(!visible.length)det.classList.add('v483-empty-more');
   }
 }
 function decorate(modal){
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact');
   const ii=identity?.querySelector('.v481-section-icon');if(ii)ii.textContent='🪪';
   const ci=contact?.querySelector('.v481-section-icon');if(ci)ci.textContent='☎';
   const heading=modal.querySelector('.modal-form-heading p');if(heading)heading.textContent='Registra al paciente y continúa a su atención.';
 }
 function polish(){
   if(busy)return;const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const text=norm(modal.textContent);if(!text.includes('nuevo paciente')&&!text.includes('cedula o identificacion'))return;
   busy=true;
   try{
     if(!ensureBaseRemaster(modal))return;
     modal.classList.add('v481-patient-modal');
     const name=field(modal,['apellidos y nombres','nombre completo','nombre']);
     const cedula=field(modal,['cedula','identificacion']);
     if(!name||!cedula)return;
     const root=name.closest('form')||cedula.closest('form')||modal.querySelector('.v481-remastered-form')||modal;
     const birth=field(modal,['fecha de nacimiento','nacimiento'],'date')||field(modal,['fecha de nacimiento','nacimiento']);
     cedula.placeholder='Ingrese 10 dígitos';name.placeholder='Apellidos y nombres';
     disableDatePicker(birth);decorate(modal);movePlaceAndRemoveNotes(modal,root);
   }finally{busy=false}
 }
 const observer=new MutationObserver(()=>queueMicrotask(polish));observer.observe(document.documentElement,{childList:true,subtree:true,characterData:true});
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(polish,40),{once:true});else setTimeout(polish,40);
 setTimeout(polish,250);setTimeout(polish,900);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.82"')!=1: raise SystemExit('APP_VERSION .82 no encontrado')
    s=s.replace('APP_VERSION = "4.3.82"','APP_VERSION = "4.3.83"',1)
    visual="const VERSION=\\'4.3.82\\';"
    if visual not in s: raise SystemExit('version visual .82 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.83\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V483_PATIENT_CSS = r"""'+CSS+'"""\n'+'V483_PATIENT_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V483_PATIENT_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V483_PATIENT_JS\n\n'+marker)
    return s.replace(marker,injected,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V483_PATIENT_JS' in names: js=ast.literal_eval(node.value)
            if 'V483_PATIENT_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('v483 ausente')
    for token in ['🪪','📍','Ingrese 10 dígitos','Apellidos y nombres','v483-location','v483ManualDate','pointerdown','Registra al paciente y continúa a su atención.']:
        if token not in js: raise SystemExit('falta '+token)
    for token in ['::-webkit-calendar-picker-indicator','v481-role-notes','v483-location','font-size:10.5px','width:min(730px']:
        if token not in css: raise SystemExit('falta css '+token)
    for token in ['V482_HOTFIX_JS','Emitir por lotes','V481_PATIENT_JS','validEcuadorCedula','V480_POLISH_JS','data-v480-zero-rejected','V476_JS','b.estado = "EMITIDA"']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.83"' not in app or "const VERSION=\\'4.3.83\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8');lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v483/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.83: pule Nuevo paciente con iconos sutiles, Lugar visible, sin Notas y fecha de nacimiento manual sin selector.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
