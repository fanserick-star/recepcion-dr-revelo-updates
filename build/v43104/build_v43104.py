from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v43103'
OUT = ROOT / 'updates' / 'v43104'
VERSION = '4.3.104'
LAUNCHER_VERSION = '4.3.100-standalone-7'


def joined(prefix: str, n: int) -> str:
    parts = sorted(SRC.glob(prefix + '*'), key=lambda p: int(p.name.replace(prefix, '')))
    if len(parts) != n:
        raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(parts)}')
    return ''.join(p.read_text(encoding='utf-8') for p in parts)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_parts(text: str, prefix: str, n: int) -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob(prefix + '*'):
        p.unlink()
    step = math.ceil(len(text) / n)
    names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step], encoding='utf-8', newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names) != text:
        raise SystemExit('reconstrucción inválida '+prefix)
    return names


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontró {count}')
    return text.replace(old,new,1)


ALERT_CSS = r'''/* v4.3.104 — advertencias de registro independientes de servicios */
.v43104-alert-band{display:grid!important;grid-template-columns:32px minmax(0,1fr) auto!important;gap:12px!important;align-items:center!important;width:100%!important;box-sizing:border-box!important;margin:0 0 13px!important;padding:12px 13px!important;border:1px solid #e6ad19!important;border-radius:14px!important;background:linear-gradient(135deg,#fff3b5 0%,#ffe997 100%)!important;box-shadow:0 3px 10px rgba(143,101,14,.08)!important}
.v43104-alert-icon{display:grid!important;place-items:center!important;width:32px!important;height:32px!important;font-size:25px!important;line-height:1!important;color:#b66e00!important}
.v43104-alert-copy{display:grid!important;gap:3px!important;min-width:0!important}
.v43104-alert-title{font-size:13.5px!important;line-height:1.15!important;font-weight:950!important;color:#694807!important;letter-spacing:.005em!important}
.v43104-alert-lines{display:grid!important;gap:2px!important}
.v43104-alert-line{font-size:11.5px!important;line-height:1.25!important;color:#735719!important}
.v43104-alert-line b{font-weight:950!important;color:#5e4107!important}
.v43104-alert-actions{display:flex!important;align-items:center!important;justify-content:flex-end!important}
.v43104-alert-actions button{min-height:39px!important;padding:8px 14px!important;border-radius:10px!important;border:1px solid #d39b13!important;background:#fffaf0!important;color:#66490d!important;font-size:10.5px!important;font-weight:900!important;white-space:nowrap!important;box-shadow:0 2px 6px rgba(126,88,12,.08)!important}
.v43104-alert-actions button:hover{background:#fff5d4!important}
.v43104-old-warning-source{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
@media(max-width:700px){.v43104-alert-band{grid-template-columns:28px minmax(0,1fr)!important}.v43104-alert-icon{width:28px!important;height:28px!important;font-size:22px!important}.v43104-alert-actions{grid-column:1/-1!important}.v43104-alert-actions button{width:100%!important}}
'''

ALERT_JS = r''';(()=>{
 if(window.__v43104PatientWarnings)return;window.__v43104PatientWarnings=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=box=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function patientName(box){
   const root=box.querySelector('.v492-head-main')||box.querySelector('.v492-clinical-head')||box;
   const blocked=/^(paciente|subsecuente|nuevo|fecha de atencion|consulta|procedimientos y servicios)$/i;
   const candidates=[...root.querySelectorAll('h3,strong,b,span,div')]
     .filter(el=>el.children.length===0)
     .map(el=>String(el.textContent||'').replace(/\s+/g,' ').trim())
     .filter(t=>t&&t.length>5&&!blocked.test(t)&&!/^faltan datos/i.test(t)&&!/^ultima atencion/i.test(t));
   candidates.sort((a,b)=>b.length-a.length);return candidates[0]||'';
 }
 function incompleteName(name){const words=String(name||'').trim().split(/\s+/).filter(Boolean);return words.length>0&&words.length<4}
 function originalMissing(box){
   return leaves(box).find(el=>{
     if(el.closest('.v43104-alert-band'))return false;
     const t=norm(el.textContent);return t.startsWith('faltan datos:')||t==='faltan datos';
   })||null;
 }
 function completeButton(box){return [...box.querySelectorAll('button')].find(b=>!b.closest('.v43104-alert-band')&&norm(b.textContent).includes('completar datos'))||box.querySelector('.v43104-alert-actions button')||null}
 function sourceContainer(missing,complete,box){
   if(!missing)return complete?.parentElement||null;
   let cur=missing;
   for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){
     if(complete&&cur.contains(complete)&&norm(cur.textContent).length<500)return cur;
   }
   return missing.parentElement;
 }
 function ensureAlert(){
   const box=boxNow();if(!box)return false;
   const head=box.querySelector('.v492-clinical-head');if(!head)return false;
   const missing=originalMissing(box);
   let complete=completeButton(box);
   const name=patientName(box),badName=incompleteName(name);
   let band=box.querySelector('.v43104-alert-band');
   if(!missing&&!badName){if(band)band.remove();return false}
   if(!band){
     band=document.createElement('section');band.className='v43104-alert-band';
     band.innerHTML='<div class="v43104-alert-icon" aria-hidden="true">⚠</div><div class="v43104-alert-copy"><div class="v43104-alert-title">Atención al registro del paciente</div><div class="v43104-alert-lines"></div></div><div class="v43104-alert-actions"></div>';
     head.insertAdjacentElement('afterend',band);
   }
   const lines=band.querySelector('.v43104-alert-lines');lines.innerHTML='';
   if(missing){
     const raw=String(missing.textContent||'').replace(/^\s*[⚠️⚠\s]*/,'').trim();
     const colon=raw.indexOf(':');const detail=(colon>=0?raw.slice(colon+1):raw.replace(/^faltan datos\s*/i,'')).trim();
     const line=document.createElement('div');line.className='v43104-alert-line';line.innerHTML='⚠ <b>Faltan datos:</b> '+(detail||'completa la ficha del paciente');lines.appendChild(line);
   }
   if(badName){const line=document.createElement('div');line.className='v43104-alert-line';line.innerHTML='⚠ <b>Nombre incompleto:</b> ideal registrar dos apellidos y dos nombres';lines.appendChild(line)}
   const actions=band.querySelector('.v43104-alert-actions');
   if(complete&&!actions.contains(complete))actions.appendChild(complete);
   const old=sourceContainer(missing,complete,box);
   if(old&&old!==band&&!old.contains(band)&&!band.contains(old))old.classList.add('v43104-old-warning-source');
   if(missing)missing.style.display='none';
   return true;
 }
 function run(){ensureAlert()}
 document.addEventListener('click',()=>{setTimeout(run,0);setTimeout(run,80);setTimeout(run,220)},true);
 document.addEventListener('change',()=>setTimeout(run,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(run,180),{once:true});else setTimeout(run,180);
})();'''


def patch_app(s: str) -> str:
    s=replace_once(s,'APP_VERSION = "4.3.103"','APP_VERSION = "4.3.104"','versión backend')
    s=replace_once(s,"const VERSION=\\'4.3.103\\';","const VERSION=\\'4.3.104\\';",'versión visual')
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=(
      'V43104_ALERT_CSS = r"""'+ALERT_CSS+'"""\n'
      'V43104_ALERT_JS = r"""'+ALERT_JS+'"""\n'
      'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V43104_ALERT_CSS\n'
      'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V43104_ALERT_JS\n\n'+marker
    )
    s=s.replace(marker,inject,1)
    compile(s,'app.py','exec')
    for token in ['APP_VERSION = "4.3.104"','V43104_ALERT_JS','v43104-alert-band','Nombre incompleto','Faltan datos','Atención al registro del paciente','V43103_SERVICES_CSS','Procedimientos y servicios',"price.textContent='$40.00'",'Revisando AZUR','Emitir por lotes']:
        if token not in s: raise SystemExit('app falta '+token)
    return s


def main() -> None:
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8')
    static_app=(SRC/'static'/'app.js').read_text(encoding='utf-8')
    (OUT/'static').mkdir(parents=True,exist_ok=True)
    (OUT/'static'/'index.html').write_text(index,encoding='utf-8',newline='')
    (OUT/'static'/'app.js').write_text(static_app,encoding='utf-8',newline='')
    ab,lb,ib,jb=app.encode(),launcher.encode(),index.encode(),static_app.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','static/app.js','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v43104/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.104: restaura las advertencias profesionales de datos faltantes y nombre incompleto sin tocar la estructura nativa de Consulta y Procedimientos.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'static/app.js','url':base+'static/app.js','sha256':sha(jb),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(jb))

if __name__=='__main__': main()
