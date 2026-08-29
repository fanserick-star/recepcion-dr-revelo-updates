from __future__ import annotations
import ast, hashlib, json, math, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v480'
OUT=ROOT/'updates'/'v481'
VERSION='4.3.81'
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
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text: raise SystemExit(f'{prefix}: reconstrucción inválida')
    return names

CSS=r'''
/* v4.3.81 — Remaster completo de Paciente nuevo */
#modal .modalbox.v481-patient-modal{width:min(780px,94vw)!important;max-height:92vh!important;padding:20px 22px 18px!important;border-radius:18px!important;overflow:auto!important}
.v481-patient-modal .v481-remastered-form{display:grid!important;gap:12px!important}
.v481-patient-modal .modal-form-heading{margin-bottom:2px!important;padding-right:38px!important}
.v481-patient-modal .modal-form-heading h2{font-size:23px!important;letter-spacing:-.015em!important;margin-bottom:3px!important}
.v481-patient-modal .modal-form-heading p{font-size:10.5px!important;color:#6e7f94!important;margin:0!important}
.v481-section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px;padding:12px 13px;border:1px solid #dce5ef;border-radius:14px;background:#fbfcfe}
.v481-section.v481-identity{background:#f8fbff;border-color:#d6e4f4}
.v481-section.v481-contact{background:#fbfcfe}
.v481-section-head{grid-column:1/-1;display:flex;align-items:end;justify-content:space-between;gap:12px;padding-bottom:7px;margin-bottom:1px;border-bottom:1px solid #e5ebf2}
.v481-section-head div{display:grid;gap:1px}.v481-section-head b{font-size:9px;letter-spacing:.11em;color:#3c5f86}.v481-section-head span{font-size:9px;color:#7b899b}.v481-section-head .v481-section-icon{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;background:#eaf3fd;color:#2f679e;font-size:14px}
.v481-patient-modal label,.v481-patient-modal .field,.v481-patient-modal .form-field,.v481-patient-modal .form-group{min-width:0}
.v481-patient-modal label{font-size:10px!important;color:#53667e!important;font-weight:800!important}
.v481-patient-modal input:not([type="checkbox"]),.v481-patient-modal textarea,.v481-patient-modal select{width:100%!important;min-height:43px!important;border-radius:11px!important;padding:9px 11px!important;font-size:12.5px!important;background:#fff!important}
.v481-patient-modal textarea{min-height:72px!important;resize:vertical!important}
.v481-role-name{grid-column:1/-1!important}.v481-role-name input{font-size:14px!important;font-weight:800!important;text-transform:uppercase!important;letter-spacing:.01em!important}
.v481-role-id{grid-column:1/-1!important}.v481-role-id input{font-size:14px!important;font-weight:850!important;letter-spacing:.035em!important}
.v481-role-foreign{grid-column:1/-1!important;padding:2px 1px!important}.v481-role-foreign label,.v481-role-foreign{font-size:9.5px!important}
.v481-id-status{grid-column:1/-1;display:flex;align-items:center;gap:7px;min-height:31px;padding:7px 9px;border-radius:10px;border:1px solid #e0e7ef;background:#fff;color:#68798f;font-size:9.5px;font-weight:800}
.v481-id-status.ok{border-color:#b9dfc9;background:#f2fbf6;color:#237247}.v481-id-status.bad{border-color:#ecc4c0;background:#fff6f5;color:#9a4a43}.v481-id-status.foreign{border-color:#cbd9ec;background:#f4f8fd;color:#446687}
.v481-age-pill{display:inline-flex;align-items:center;margin-top:5px;padding:3px 7px;border-radius:999px;background:#edf4fb;color:#3f6388;font-size:8.5px;font-weight:850}
.v481-field-invalid input{border-color:#d7847d!important;box-shadow:0 0 0 2px rgba(190,75,65,.08)!important}.v481-inline-error{display:block;margin-top:4px;font-size:8.5px;color:#a44d45;font-weight:750}
.v481-duplicate-card{grid-column:1/-1;display:none;align-items:flex-start;justify-content:space-between;gap:12px;padding:10px 11px;border-radius:11px;border:1px solid #edd1a9;background:#fff9ef;color:#74521f}.v481-duplicate-card.show{display:flex}.v481-duplicate-card.danger{border-color:#e9bbb7;background:#fff5f4;color:#873f39}.v481-duplicate-card .copy{display:grid;gap:2px;min-width:0}.v481-duplicate-card b{font-size:10.5px}.v481-duplicate-card span{font-size:9px;line-height:1.3}.v481-duplicate-card button{flex:0 0 auto;border:1px solid currentColor;background:#fff;border-radius:8px;padding:6px 8px;font-size:8.5px;font-weight:850;cursor:pointer}
.v481-more-details{border:1px solid #dfe6ee;border-radius:12px;background:#fafbfd;overflow:hidden}.v481-more-details>summary{cursor:pointer;list-style:none;padding:10px 12px;font-size:9.5px;font-weight:900;color:#536981;display:flex;align-items:center;justify-content:space-between}.v481-more-details>summary::-webkit-details-marker{display:none}.v481-more-details>summary:after{content:'Abrir';font-size:8px;color:#77879a}.v481-more-details[open]>summary:after{content:'Ocultar'}.v481-more-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px;padding:0 12px 12px}.v481-role-notes{grid-column:1/-1!important}
.v481-patient-modal .actions,.v481-patient-modal .form-actions,.v481-patient-modal .modal-actions{position:sticky;bottom:-18px;z-index:5;margin:4px -2px -1px!important;padding:10px 2px 1px!important;background:linear-gradient(to bottom,rgba(255,255,255,.82),#fff 32%)!important;display:flex!important;justify-content:flex-end!important;gap:7px!important}.v481-create-btn{min-width:145px!important;min-height:39px!important;border-radius:10px!important;font-size:10.5px!important;font-weight:900!important}.v481-create-btn:disabled{opacity:.48!important;cursor:not-allowed!important}
@media(max-width:680px){#modal .modalbox.v481-patient-modal{width:94vw!important;padding:17px!important}.v481-section,.v481-more-body{grid-template-columns:1fr}.v481-role-name,.v481-role-id,.v481-role-foreign,.v481-role-notes{grid-column:1!important}.v481-duplicate-card{flex-direction:column}.v481-section-head{align-items:flex-start}}
'''

JS=r''';(()=>{
 if(window.__v481PatientRemaster)return;window.__v481PatientRemaster=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const digits=v=>String(v||'').replace(/\D/g,'');
 let installTries=0;

 function ecuadorPhone(v){const d=digits(v);if(d.startsWith('593')&&d.length===12)return '0'+d.slice(3);return d}
 function validEcuadorCedula(value){
   const d=digits(value);if(d.length!==10)return false;
   const province=Number(d.slice(0,2)),third=Number(d[2]);if(province<1||province>24||third>=6)return false;
   let sum=0;for(let i=0;i<9;i++){let n=Number(d[i])*(i%2===0?2:1);if(n>9)n-=9;sum+=n}
   const check=(10-(sum%10))%10;return check===Number(d[9]);
 }
 function labelText(el){
   const id=el.id||'';const direct=el.closest('label');
   const byFor=id?[...document.querySelectorAll('label[for]')].find(l=>l.htmlFor===id):null;
   return norm([el.name,el.id,el.placeholder,el.getAttribute('aria-label'),direct?.textContent,byFor?.textContent].filter(Boolean).join(' '));
 }
 function field(root,words,type){
   const els=[...root.querySelectorAll('input,textarea,select')].filter(x=>!['button','submit','hidden'].includes(String(x.type||'').toLowerCase()));
   if(type){const exact=els.find(x=>String(x.type||'').toLowerCase()===type&&words.some(w=>labelText(x).includes(w)));if(exact)return exact}
   return els.find(x=>words.some(w=>labelText(x).includes(w)))||null;
 }
 function wrap(el,root){
   if(!el)return null;
   const w=el.closest('label,.field,.form-field,.form-group,.input-group,.control');
   if(w&&w!==root&&root.contains(w))return w;
   const p=el.parentElement;return p&&p!==root?p:el;
 }
 function topUnique(list){
   const x=[...new Set(list.filter(Boolean))];return x.filter(a=>!x.some(b=>a!==b&&b.contains(a)));
 }
 function heading(title,subtitle,icon){const h=document.createElement('div');h.className='v481-section-head';h.innerHTML=`<div><b>${esc(title)}</b><span>${esc(subtitle)}</span></div><span class="v481-section-icon">${icon}</span>`;return h}
 function makeSection(parent,before,title,subtitle,icon,wrappers,cls){
   wrappers=topUnique(wrappers).filter(w=>w.parentElement===parent);if(!wrappers.length)return null;
   const s=document.createElement('section');s.className='v481-section '+cls;s.appendChild(heading(title,subtitle,icon));parent.insertBefore(s,before||wrappers[0]);wrappers.forEach(w=>s.appendChild(w));return s;
 }
 async function searchPatients(q){
   try{
     if(!q)return [];
     const url=`/api/patients?q=${encodeURIComponent(q)}&limit=12`;
     let d;
     if(typeof window.api==='function')d=await window.api(url);else{const r=await fetch(url,{credentials:'same-origin'});if(!r.ok)return [];d=await r.json()}
     return Array.isArray(d)?d:(Array.isArray(d?.items)?d.items:(Array.isArray(d?.patients)?d.patients:(Array.isArray(d?.results)?d.results:[])));
   }catch(_e){return []}
 }
 function patientCore(x){return x?.patient&&typeof x.patient==='object'?x.patient:x||{}}
 function patientName(x){const p=patientCore(x);return String(p.nombre||p.name||'Paciente registrado')}
 function patientPhone(x){const p=patientCore(x);return String(p.celular||p.phone||'')}
 function patientCedula(x){const p=patientCore(x);return String(p.cedula||p.identificacion||'')}
 function patientDate(x){const p=patientCore(x);return String(x?.last_visit_date||p.last_visit_date||p.ultima_atencion||'')}
 function ageFromISO(v){
   const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(v||''));if(!m)return null;
   const b=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]));if(Number.isNaN(b.getTime()))return null;
   const t=new Date();let a=t.getFullYear()-b.getFullYear();if(t.getMonth()<b.getMonth()||(t.getMonth()===b.getMonth()&&t.getDate()<b.getDate()))a--;return a>=0&&a<130?a:null;
 }
 function findActionButton(root){return [...root.querySelectorAll('button')].reverse().find(b=>/guardar|crear paciente|registrar paciente/.test(norm(b.textContent)))||null}

 function remaster(fromAttention){
   const modal=document.querySelector('#modal .modalbox');if(!modal||modal.dataset.v481Patient==='1')return;
   const name=field(modal,['apellidos y nombres','nombre completo','nombre','paciente']);
   const cedula=field(modal,['cedula','identificacion']);
   if(!name||!cedula)return;
   modal.dataset.v481Patient='1';modal.classList.add('v481-patient-modal');
   const root=name.closest('form')||cedula.closest('form')||name.parentElement?.parentElement||modal;
   root.classList.add('v481-remastered-form');
   const birth=field(modal,['fecha de nacimiento','nacimiento'],'date');
   const phone=field(modal,['celular','telefono','whatsapp']);
   const email=field(modal,['correo','email']);
   const place=field(modal,['lugar','ciudad','direccion']);
   const notes=field(modal,['notas','observacion']);
   const foreign=field(modal,['extranjero','extranjera'],'checkbox')||[...modal.querySelectorAll('input[type="checkbox"]')].find(x=>labelText(x).includes('extranj'))||null;
   const wId=wrap(cedula,root),wName=wrap(name,root),wBirth=wrap(birth,root),wForeign=wrap(foreign,root),wPhone=wrap(phone,root),wEmail=wrap(email,root),wPlace=wrap(place,root),wNotes=wrap(notes,root);
   [[wId,'v481-role-id'],[wName,'v481-role-name'],[wBirth,'v481-role-birth'],[wForeign,'v481-role-foreign'],[wPhone,'v481-role-phone'],[wEmail,'v481-role-email'],[wPlace,'v481-role-place'],[wNotes,'v481-role-notes']].forEach(([w,c])=>w?.classList?.add(c));
   const commonParent=wName?.parentElement===wId?.parentElement?wName.parentElement:root;
   if(commonParent&&commonParent!==modal){
     const idWrappers=topUnique([wId,wForeign,wName,wBirth]).filter(w=>w?.parentElement===commonParent);
     if(idWrappers.length){makeSection(commonParent,idWrappers[0],'IDENTIDAD','Datos principales del paciente','ID',idWrappers,'v481-identity')}
     const contactWrappers=topUnique([wPhone,wEmail]).filter(w=>w?.parentElement===commonParent);
     if(contactWrappers.length){makeSection(commonParent,contactWrappers[0],'CONTACTO','Información para comunicarnos con el paciente','☎',contactWrappers,'v481-contact')}
     const extras=topUnique([wPlace,wNotes]).filter(w=>w?.parentElement===commonParent);
     if(extras.length){
       const det=document.createElement('details');det.className='v481-more-details';if(extras.some(w=>w.querySelector('input,textarea')?.value))det.open=true;
       const sum=document.createElement('summary');sum.textContent='＋ Más datos';const body=document.createElement('div');body.className='v481-more-body';det.append(sum,body);commonParent.insertBefore(det,extras[0]);extras.forEach(w=>body.appendChild(w));
     }
   }
   const idSection=modal.querySelector('.v481-identity')||wId?.parentElement;
   const idStatus=document.createElement('div');idStatus.className='v481-id-status';idStatus.textContent='Ingresa la cédula para validarla localmente.';
   const duplicate=document.createElement('div');duplicate.className='v481-duplicate-card';duplicate.innerHTML='<div class="copy"><b></b><span></span></div>';
   if(idSection){idSection.appendChild(idStatus);idSection.appendChild(duplicate)}
   let agePill=null;if(birth&&wBirth){agePill=document.createElement('span');agePill.className='v481-age-pill';agePill.textContent='Edad —';wBirth.appendChild(agePill)}
   let emailError=null;if(email&&wEmail){emailError=document.createElement('small');emailError.className='v481-inline-error';emailError.textContent='Correo no válido';emailError.style.display='none';wEmail.appendChild(emailError)}
   const save=findActionButton(modal);if(save){save.classList.add('v481-create-btn');if(/guardar|registrar/.test(norm(save.textContent)))save.textContent='Crear paciente'}
   const state={duplicateCedula:false,phoneDuplicate:false,seqId:0,seqPhone:0};
   function showDup(kind,p){
     if(!p){duplicate.classList.remove('show','danger');duplicate.querySelector('b').textContent='';duplicate.querySelector('span').textContent='';duplicate.querySelector('button')?.remove();return}
     const nm=patientName(p),ph=patientPhone(p),last=patientDate(p);duplicate.classList.add('show');duplicate.classList.toggle('danger',kind==='cedula');
     duplicate.querySelector('b').textContent=kind==='cedula'?'⚠ Este paciente ya está registrado':'⚠ Este celular ya está registrado';
     duplicate.querySelector('span').textContent=`${nm}${ph?' · '+ph:''}${last?' · Última atención: '+String(last).slice(0,10):''}`;
     duplicate.querySelector('button')?.remove();if(kind==='cedula'&&fromAttention&&typeof window.newAttention==='function'){const b=document.createElement('button');b.type='button';b.textContent='Volver a buscarlo';b.onclick=()=>window.newAttention();duplicate.appendChild(b)}
   }
   function updateAge(){if(!agePill)return;const a=ageFromISO(birth?.value);agePill.textContent=a===null?'Edad —':`Edad: ${a} año${a===1?'':'s'}`}
   function updateStatus(){
     const foreignOn=!!foreign?.checked,raw=String(cedula.value||'').trim(),d=digits(raw);
     idStatus.className='v481-id-status';
     if(foreignOn){idStatus.classList.add('foreign');idStatus.textContent='Identificación extranjera · no se aplica validación ecuatoriana.'}
     else if(!raw){idStatus.textContent='Ingresa la cédula para validarla localmente.'}
     else if(d.length<10){idStatus.textContent=`Cédula ecuatoriana · ${d.length}/10 dígitos`}
     else if(validEcuadorCedula(d)){idStatus.classList.add('ok');idStatus.textContent='✓ Cédula ecuatoriana válida'}
     else{idStatus.classList.add('bad');idStatus.textContent='✕ La cédula no pasa la validación ecuatoriana'}
   }
   function emailOk(){if(!email||!String(email.value||'').trim())return true;return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(String(email.value||'').trim())}
   function updateSave(){
     if(!save)return;const foreignOn=!!foreign?.checked,raw=String(cedula.value||'').trim(),idOk=foreignOn||!raw||validEcuadorCedula(raw),mailOk=emailOk(),required=[...modal.querySelectorAll('input[required],textarea[required],select[required]')].every(x=>String(x.value||'').trim());
     wEmail?.classList.toggle('v481-field-invalid',!mailOk);if(emailError)emailError.style.display=mailOk?'none':'block';
     save.disabled=!String(name.value||'').trim()||!idOk||!mailOk||!required||state.duplicateCedula;
   }
   async function checkCedula(){
     const q=digits(cedula.value);state.duplicateCedula=false;if(foreign?.checked||q.length!==10||!validEcuadorCedula(q)){if(!state.phoneDuplicate)showDup(null,null);updateSave();return}
     const seq=++state.seqId,rows=await searchPatients(q);if(seq!==state.seqId)return;const hit=rows.find(x=>digits(patientCedula(x))===q)||null;state.duplicateCedula=!!hit;if(hit)showDup('cedula',hit);else if(!state.phoneDuplicate)showDup(null,null);updateSave();
   }
   async function checkPhone(){
     if(!phone)return;const q=ecuadorPhone(phone.value);state.phoneDuplicate=false;if(q.length<9){if(!state.duplicateCedula)showDup(null,null);return}
     const seq=++state.seqPhone,rows=await searchPatients(q);if(seq!==state.seqPhone)return;const hit=rows.find(x=>ecuadorPhone(patientPhone(x))===q)||null;state.phoneDuplicate=!!hit;if(!state.duplicateCedula){if(hit)showDup('phone',hit);else showDup(null,null)}
   }
   let idTimer=0,phoneTimer=0;
   cedula.addEventListener('input',()=>{updateStatus();updateSave();clearTimeout(idTimer);idTimer=setTimeout(checkCedula,260)});
   cedula.addEventListener('blur',checkCedula);
   foreign?.addEventListener('change',()=>{state.duplicateCedula=false;updateStatus();updateSave();checkCedula()});
   name.addEventListener('input',()=>{const s=name.selectionStart,e=name.selectionEnd;name.value=String(name.value||'').toUpperCase();try{name.setSelectionRange(s,e)}catch(_e){}updateSave()});
   birth?.addEventListener('change',updateAge);birth?.addEventListener('input',updateAge);
   email?.addEventListener('input',updateSave);
   phone?.addEventListener('input',()=>{clearTimeout(phoneTimer);phoneTimer=setTimeout(checkPhone,340)});phone?.addEventListener('blur',()=>{const d=digits(phone.value);if(d.startsWith('593')&&d.length===12)phone.value='0'+d.slice(3);checkPhone()});
   updateAge();updateStatus();updateSave();setTimeout(checkCedula,50);if(phone?.value)setTimeout(checkPhone,80);
 }
 function install(){
   if(window.newPatient&&window.newPatient.__v481Wrapped)return true;
   if(typeof window.newPatient!=='function')return false;
   const base=window.newPatient;const wrapped=function(...args){const r=base.apply(this,args);const fromAttention=!!args[0];requestAnimationFrame(()=>remaster(fromAttention));setTimeout(()=>remaster(fromAttention),40);if(r&&typeof r.then==='function')r.finally(()=>setTimeout(()=>remaster(fromAttention),0));return r};wrapped.__v481Wrapped=true;window.newPatient=wrapped;return true;
 }
 function boot(){if(install())return;if(++installTries<12)setTimeout(boot,120)}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();setTimeout(boot,350);
})();'''


def patch_app(s):
    original_routes=re.findall(r'@app\.(?:get|post|put|delete|patch)\(',s)
    if s.count('APP_VERSION = "4.3.80"')!=1: raise SystemExit('APP_VERSION 4.3.80 no encontrado')
    s=s.replace('APP_VERSION = "4.3.80"','APP_VERSION = "4.3.81"',1)
    visual="const VERSION=\\'4.3.80\\';"
    if visual not in s: raise SystemExit('versión visual 4.3.80 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.81\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inválido')
    injected=('V481_PATIENT_CSS = r"""'+CSS+'"""\n'+'V481_PATIENT_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V481_PATIENT_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V481_PATIENT_JS\n\n'+marker)
    out=s.replace(marker,injected,1)
    if re.findall(r'@app\.(?:get|post|put|delete|patch)\(',out)!=original_routes: raise SystemExit('v4.3.81 no debe cambiar rutas backend')
    return out


def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V481_PATIENT_JS' in names: js=ast.literal_eval(node.value)
            if 'V481_PATIENT_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v4.3.81 no encontrado')
    for token in ['validEcuadorCedula','/api/patients?q=','duplicateCedula','Edad:','Más datos','Identificación extranjera','Volver a buscarlo','window.newPatient=wrapped']:
        if token not in js: raise SystemExit('falta '+token)
    for token in ['v481-patient-modal','v481-section','v481-duplicate-card','v481-create-btn','v481-more-details']:
        if token not in css: raise SystemExit('falta CSS '+token)
    for token in ['V480_POLISH_JS','data-v480-zero-rejected','V478_REMIX_JS','MAÑANA','TARDE','V476_JS','b.estado = "EMITIDA"','@app.post(\\"/api/patients\\")']:
        if token not in app: raise SystemExit('regresión: '+token)
    if 'APP_VERSION = "4.3.81"' not in app or "const VERSION=\\'4.3.81\\';" not in app: raise SystemExit('versiones incorrectas')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8');lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v481/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.81: remasteriza Paciente nuevo con validación local de cédula, edad automática, detección de duplicados y formulario por secciones.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__':main()
