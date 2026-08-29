from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v481'
OUT=ROOT/'updates'/'v482'
VERSION='4.3.82'
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
/* v4.3.82 — recupera emisión por lotes + remaster persistente de Paciente nuevo */
#facturacion .v482-quick-head{position:relative!important;padding-right:170px!important;min-height:42px!important}
#facturacion .v482-batch-btn{position:absolute!important;right:0!important;top:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:6px!important;min-height:36px!important;padding:8px 12px!important;border:1px solid #8eb3dc!important;border-radius:10px!important;background:#edf5ff!important;color:#245785!important;font-size:10px!important;font-weight:900!important;cursor:pointer!important;white-space:nowrap!important}
#facturacion .v482-batch-btn:hover{background:#e2effd!important}
#facturacion .v482-batch-btn[hidden]{display:none!important}
@media(max-width:720px){#facturacion .v482-quick-head{padding-right:0!important;padding-bottom:46px!important}#facturacion .v482-batch-btn{left:0!important;right:auto!important;top:auto!important;bottom:4px!important}}
'''

JS=r''';(()=>{
 if(window.__v482Hotfix)return;window.__v482Hotfix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 let guard=false;
 function readPending(){
   const box=document.querySelector('#billingSummary');if(!box)return 0;
   const el=[...box.children].find(x=>{const t=norm(x.textContent);return t.includes('por emitir')||t.includes('pendiente')});
   if(!el)return 0;const m=String(el.textContent||'').match(/\d+/);return m?Number(m[0]):0;
 }
 function ensureBatchButton(){
   const sec=document.querySelector('#facturacion');if(!sec)return;
   const nodes=[...sec.querySelectorAll('h2,h3,h4,b,strong,p,div')];
   const title=nodes.find(x=>norm(x.textContent)==='accion rapida')||nodes.find(x=>norm(x.textContent).startsWith('accion rapida'));
   if(!title)return;
   const host=title.parentElement;if(!host)return;host.classList.add('v482-quick-head');
   let btn=document.querySelector('#v482BatchEmit');
   if(!btn){btn=document.createElement('button');btn.id='v482BatchEmit';btn.type='button';btn.className='v482-batch-btn';btn.innerHTML='⚡ Emitir por lotes';btn.addEventListener('click',async()=>{if(typeof window.emitAllPendingInvoices==='function')await window.emitAllPendingInvoices();else alert('La emisión por lotes no está disponible.');});host.appendChild(btn)}
   btn.hidden=readPending()<2;
 }
 function patientFieldsPresent(modal){
   if(!modal)return false;const t=norm(modal.textContent);
   const inputs=[...modal.querySelectorAll('input,textarea')];
   const id=inputs.some(x=>/cedula|identificacion/.test(norm([x.name,x.id,x.placeholder,x.getAttribute('aria-label')].join(' '))))||t.includes('cedula o identificacion');
   const name=inputs.some(x=>/nombre/.test(norm([x.name,x.id,x.placeholder,x.getAttribute('aria-label')].join(' '))))||t.includes('apellidos y nombres');
   return id&&name;
 }
 function ensurePatientRemaster(){
   if(guard)return;const modal=document.querySelector('#modal .modalbox');if(!patientFieldsPresent(modal))return;
   if(modal.querySelector('.v481-section')&&modal.querySelector('.v481-remastered-form'))return;
   if(typeof window.v481RemasterPatient!=='function')return;
   guard=true;
   try{delete modal.dataset.v481Patient;modal.classList.remove('v481-patient-modal');window.v481RemasterPatient(true)}finally{guard=false}
 }
 function apply(){ensureBatchButton();ensurePatientRemaster()}
 const observer=new MutationObserver(()=>queueMicrotask(apply));
 observer.observe(document.documentElement,{childList:true,subtree:true,characterData:true});
 const oldLoad=window.loadBilling;if(typeof oldLoad==='function')window.loadBilling=async function(){const r=await oldLoad.apply(this,arguments);ensureBatchButton();return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(apply,30),{once:true});else setTimeout(apply,30);
 setTimeout(apply,250);setTimeout(apply,900);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.81"')!=1: raise SystemExit('APP_VERSION .81 no encontrado')
    s=s.replace('APP_VERSION = "4.3.81"','APP_VERSION = "4.3.82"',1)
    visual="const VERSION=\\'4.3.81\\';"
    if visual not in s: raise SystemExit('version visual .81 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.82\\';",1)
    # Exporta el remaster interno de v481 para poder reaplicarlo cuando un flujo
    # histórico sustituye el contenido del mismo modal sin crear un modal nuevo.
    token='window.newPatient=wrapped'
    if token not in s: raise SystemExit('wrapper v481 no encontrado')
    s=s.replace(token,'window.v481RemasterPatient=remaster;window.newPatient=wrapped',1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V482_HOTFIX_CSS = r"""'+CSS+'"""\n'+'V482_HOTFIX_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V482_HOTFIX_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V482_HOTFIX_JS\n\n'+marker)
    return s.replace(marker,injected,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V482_HOTFIX_JS' in names: js=ast.literal_eval(node.value)
            if 'V482_HOTFIX_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('hotfix v482 ausente')
    for token in ['Emitir por lotes','emitAllPendingInvoices','v481RemasterPatient','MutationObserver','v481-section']:
        if token not in js and token not in app: raise SystemExit('falta '+token)
    for token in ['v482-batch-btn','v482-quick-head']:
        if token not in css: raise SystemExit('falta css '+token)
    for token in ['V481_PATIENT_JS','validEcuadorCedula','V480_POLISH_JS','data-v480-zero-rejected','V476_JS','b.estado = "EMITIDA"']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.82"' not in app or "const VERSION=\\'4.3.82\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v482/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.82: recupera Emitir por lotes y mantiene el remaster de Paciente nuevo también al identificar pacientes históricos.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__':main()
