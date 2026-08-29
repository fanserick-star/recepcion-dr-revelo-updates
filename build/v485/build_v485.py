from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v484'
OUT=ROOT/'updates'/'v485'
VERSION='4.3.85'
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
/* v4.3.85 — identidad compatible + Lugar debajo de Contacto */
.v481-section-icon .v485-id-card{display:block;width:20px;height:14px;border:1.5px solid currentColor;border-radius:3px;position:relative;box-sizing:border-box}
.v481-section-icon .v485-id-card:before{content:'';position:absolute;left:3px;top:3px;width:4px;height:4px;border:1px solid currentColor;border-radius:50%;box-sizing:border-box}
.v481-section-icon .v485-id-card:after{content:'';position:absolute;right:3px;top:4px;width:7px;height:1.5px;border-radius:2px;background:currentColor;box-shadow:0 3px 0 currentColor}
.v484-location.v485-location-under-contact{grid-column:2!important;align-self:start!important;margin-top:0!important;min-height:auto!important}
.v484-location.v485-location-under-contact .v481-section-head{margin-bottom:2px!important}
@media(max-width:680px){.v484-location.v485-location-under-contact{grid-column:1!important}}
'''

JS=r''';(()=>{
 if(window.__v485Fixes)return;window.__v485Fixes=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let batchBusy=false;

 function visualFix(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact'),location=modal.querySelector('.v484-location');
   const icon=identity?.querySelector('.v481-section-icon');
   if(icon&&!icon.querySelector('.v485-id-card'))icon.innerHTML='<span class="v485-id-card" aria-hidden="true"></span>';
   if(location&&contact&&location.parentElement===contact.parentElement){contact.insertAdjacentElement('afterend',location);location.classList.add('v485-location-under-contact')}
 }

 async function req(url,opt={}){
   if(typeof window.api==='function')return await window.api(url,opt);
   const r=await fetch(url,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
   const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||d.message||'No se pudo completar la operación');return d;
 }
 async function ask(text,title){return typeof window.rpConfirm==='function'?await window.rpConfirm(text,title):window.confirm(text)}
 function notice(text,title){if(typeof window.rpNotice==='function')return window.rpNotice(text,title);alert(text)}

 window.emitAllPendingInvoices=async function(){
   if(batchBusy)return;batchBusy=true;
   const btn=document.querySelector('#v482BatchEmit');const old=btn?.textContent;
   try{
     if(btn){btn.disabled=true;btn.textContent='Revisando…'}
     const pre=await req('/api/billing/azur/batch-preview');
     const c=pre.counts||{},ready=Number(c.ready||0),skipped=Number(c.skipped||0);
     if(!ready){notice(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`,'Facturación');return}
     const examples=(pre.ready||[]).slice(0,5).map(x=>`• ${x.nombre||'Paciente'} · $${Number(x.total||0).toFixed(2)}`).join('\n');
     const text=`¿Emitir ${ready} factura${ready===1?'':'s'} por lotes en AZUR?\n\nSe enviarán una por una para evitar duplicados.${examples?'\n\n'+examples:''}`;
     if(!(await ask(text,'Emitir por lotes')))return;
     if(btn)btn.textContent='Emitiendo…';
     const result=await req('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}'});
     const r=result.counts||{};
     let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
     const failed=(result.failed||[]).slice(0,5);if(failed.length)detail+='\n\nCon error:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason||'Error'}`).join('\n');
     notice(detail,'Emisión por lotes');
     try{await window.loadBilling?.()}catch(_e){}try{window.refreshPendingBadges?.()}catch(_e){}
   }catch(e){notice(e?.message||String(e),'Facturación')}
   finally{batchBusy=false;if(btn){btn.disabled=false;btn.textContent=old||'⚡ Emitir por lotes'}}
 };

 const oldEdit=window.editPatientFromBilling;
 if(typeof oldEdit==='function')window.editPatientFromBilling=function(id){
   window.__v485EditingPatientId=Number(id)||id||true;
   try{return oldEdit.apply(this,arguments)}finally{setTimeout(()=>{window.__v485EditingPatientId=null},1500)}
 };

 const oldRemaster=window.v481RemasterPatient;
 if(typeof oldRemaster==='function')window.v481RemasterPatient=function(){const r=oldRemaster.apply(this,arguments);setTimeout(visualFix,0);setTimeout(visualFix,60);return r};
 const oldNew=window.newPatient;
 if(typeof oldNew==='function')window.newPatient=function(){const r=oldNew.apply(this,arguments);setTimeout(visualFix,20);setTimeout(visualFix,90);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(visualFix,80),{once:true});else setTimeout(visualFix,80);
})();'''

def must_replace(s,old,new,count=1,label='reemplazo'):
    found=s.count(old)
    if found!=count: raise SystemExit(f'{label}: esperado {count}, encontrado {found}')
    return s.replace(old,new,count)

def patch_app(s):
    s=must_replace(s,'APP_VERSION = "4.3.84"','APP_VERSION = "4.3.85"',1,'version backend')
    s=must_replace(s,"const VERSION=\\'4.3.84\\';","const VERSION=\\'4.3.85\\';",1,'version visual')

    # Duplicados: la protección sigue activa al CREAR, pero al EDITAR/COMPLETAR
    # no puede bloquear al paciente contra su propia ficha.
    old="const save=findActionButton(modal);if(save){save.classList.add('v481-create-btn');if(/guardar|registrar/.test(norm(save.textContent)))save.textContent='Crear paciente'}"
    new="const save=findActionButton(modal);const initialSaveLabel=norm(save?.textContent);const headingText=norm(modal.querySelector('.modal-form-heading h2,h1,h2,h3')?.textContent||'');const editMode=!!window.__v485EditingPatientId||/editar|completar/.test(headingText)||/guardar cambios|actualizar/.test(initialSaveLabel);if(save){save.classList.add('v481-create-btn');if(!editMode&&/guardar|registrar/.test(norm(save.textContent)))save.textContent='Crear paciente'}"
    s=must_replace(s,old,new,1,'modo editar paciente')
    s=must_replace(s,"save.disabled=!String(name.value||'').trim()||!idOk||!mailOk||!required||state.duplicateCedula;","save.disabled=!String(name.value||'').trim()||!idOk||!mailOk||!required||(!editMode&&state.duplicateCedula);",1,'bloqueo duplicado')
    s=must_replace(s,"async function checkCedula(){\n     const q=digits(cedula.value);state.duplicateCedula=false;","async function checkCedula(){\n     if(editMode){state.duplicateCedula=false;if(!state.phoneDuplicate)showDup(null,null);updateSave();return}\n     const q=digits(cedula.value);state.duplicateCedula=false;",1,'cedula editar')
    s=must_replace(s,"async function checkPhone(){\n     if(!phone)return;","async function checkPhone(){\n     if(!phone)return;if(editMode){state.phoneDuplicate=false;if(!state.duplicateCedula)showDup(null,null);return}\n",1,'telefono editar')

    # Facturación v4.3.75 eliminó el paso APROBADA visible. El lote debe aceptar
    # PENDIENTE/APROBADA igual que la emisión individual /api/billing/approve.
    s=must_replace(s,'BillingRecord.estado == "APROBADA"','BillingRecord.estado.in_(["PENDIENTE", "APROBADA"])',2,'cola lote pendiente/aprobada')
    s=must_replace(s,'any(b.estado != "APROBADA" for b, _ in rows)','any(str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"} for b, _ in rows)',2,'validacion lote estados')
    s=s.replace('"La factura todavía no está completamente aprobada"','"La factura tiene estados que ya no están disponibles para emitir"')
    old_block='''            # La emisión masiva trabaja únicamente sobre facturas ya aprobadas.\n            db.commit()\n            mirror_azur_emission_to_local(record)\n            sent.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "numero_factura": invoice_number, "clave_acceso": access_key})'''
    new_block='''            touched=[]\n            for b, _v in rows:\n                b.estado = "EMITIDA"\n                b.approved_at = now\n                b.numero_factura = invoice_number\n                b.emitted_at = now\n                touched.append(b)\n            db.commit()\n            mirror_azur_emission_to_local(record)\n            for b in touched:\n                mirror_billing_to_local(b)\n            sent.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "numero_factura": invoice_number, "clave_acceso": access_key})'''
    s=must_replace(s,old_block,new_block,1,'cerrar facturas emitidas por lote')

    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V485_FIX_CSS = r"""'+CSS+'"""\n'+'V485_FIX_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V485_FIX_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V485_FIX_JS\n\n'+marker)
    return s.replace(marker,injected,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V485_FIX_JS' in names: js=ast.literal_eval(node.value)
            if 'V485_FIX_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('v485 ausente')
    for token in ['v485-id-card','v485-location-under-contact','emitAllPendingInvoices','/api/billing/azur/emit-all-pending','__v485EditingPatientId']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    for token in ['editMode','!editMode&&state.duplicateCedula','BillingRecord.estado.in_(["PENDIENTE", "APROBADA"])','b.estado = "EMITIDA"','mirror_billing_to_local(b)']:
        if token not in app: raise SystemExit('falta correccion '+token)
    if app.count('BillingRecord.estado.in_(["PENDIENTE", "APROBADA"])')<2: raise SystemExit('lote aun no usa cola unificada')
    for token in ['V484_PATIENT_JS','V482_HOTFIX_JS','V481_PATIENT_JS','validEcuadorCedula','V480_POLISH_JS','data-v480-zero-rejected','V476_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.85"' not in app or "const VERSION=\\'4.3.85\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8');lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v485/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.85: corrige emisión por lotes, completar datos sin falso duplicado y ajusta Identidad/Lugar en Paciente nuevo.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
