from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v492'
OUT=ROOT/'updates'/'v493'
VERSION='4.3.93'
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

CSS=r'''/* v4.3.93 — CONSULTA restaurada + alertas clínicas visibles */
.v493-alert-band{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;margin:-3px 0 11px;padding:10px 12px;border:1px solid #e1b84d;border-radius:13px;background:linear-gradient(135deg,#fff8d8 0%,#fff1b5 100%);box-shadow:0 3px 10px rgba(155,111,22,.08)}
.v493-alert-icon{font-size:22px;line-height:1;filter:saturate(1.08)}
.v493-alert-copy{display:grid;gap:3px;min-width:0}.v493-alert-title{font-size:10px;font-weight:950;color:#6e4d08;letter-spacing:.015em}.v493-alert-line{font-size:9px;line-height:1.25;color:#735b23}.v493-alert-line b{font-weight:950;color:#5d430c}
.v493-alert-actions{display:flex;align-items:center}.v493-alert-actions button{min-height:33px!important;padding:6px 11px!important;border-radius:9px!important;border:1px solid #d3a83f!important;background:#fff9df!important;color:#684d12!important;font-size:8.5px!important;font-weight:900!important;white-space:nowrap!important;box-shadow:0 2px 6px rgba(128,92,18,.08)!important}.v493-alert-actions button:hover{background:#fff3c4!important}
.v493-old-alert{display:none!important}
.v492-services-grid>.v493-consult{order:-100!important;border-color:#b9ddc7!important;background:#eff9f3!important}.v492-services-grid>.v493-consult:hover{border-color:#7fbd98!important;background:#e9f7ef!important}.v492-services-grid>.v493-consult strong,.v492-services-grid>.v493-consult b{color:#245f41!important}.v492-services-grid>.v493-consult .v492-service-mark{background:#d9efe2!important;color:#267149!important}
.v492-services-grid>.v493-consult::after{content:'$40 fijo';display:inline-flex;margin-left:auto;padding:2px 5px;border-radius:999px;background:#def1e6;color:#286b49;font-size:7px;font-weight:900;white-space:nowrap}
.v492-services-grid>.v493-consult.is-selected::after{background:#cae8d6;color:#215d3e}
@media(max-width:700px){.v493-alert-band{grid-template-columns:auto 1fr}.v493-alert-actions{grid-column:1/-1}.v493-alert-actions button{width:100%}}
'''

JS=r''';(()=>{
 if(window.__v493AttentionFix)return;window.__v493AttentionFix=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=box=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención'))||null}
 function patientName(box){
   const root=box.querySelector('.v492-head-main')||box;
   const candidates=[...root.querySelectorAll('h3,strong,b,span,div')].filter(el=>el.children.length===0).map(el=>String(el.textContent||'').replace(/\s+/g,' ').trim()).filter(t=>t&&t.length>5&&!/^(paciente|subsecuente|nuevo)$/i.test(t)&&!/^faltan datos/i.test(t)&&!/^sin c[eé]dula/i.test(t));
   candidates.sort((a,b)=>b.length-a.length);return candidates[0]||'';
 }
 function incompleteName(name){
   const words=String(name||'').trim().split(/\s+/).filter(Boolean);return words.length>0&&words.length<4;
 }
 function smallestCommon(a,b,box){
   if(!a)return null;let cur=a;
   for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){if((!b||cur.contains(b))&&norm(cur.textContent).length<650)return cur}
   return a.parentElement;
 }
 function ensureAlert(box){
   const head=box.querySelector('.v492-clinical-head');if(!head)return;
   const all=leaves(box);const missing=all.find(el=>norm(el.textContent).includes('faltan datos'))||null;
   const complete=[...box.querySelectorAll('button')].find(b=>norm(b.textContent).includes('completar datos'))||null;
   const name=patientName(box),badName=incompleteName(name);
   let band=box.querySelector('.v493-alert-band');
   if(!missing&&!badName){if(band)band.remove();return}
   if(!band){
     band=document.createElement('section');band.className='v493-alert-band';
     band.innerHTML='<div class="v493-alert-icon" aria-hidden="true">⚠️</div><div class="v493-alert-copy"><div class="v493-alert-title">Atención al registro del paciente</div><div class="v493-alert-lines"></div></div><div class="v493-alert-actions"></div>';
     head.insertAdjacentElement('afterend',band);
   }
   const lines=band.querySelector('.v493-alert-lines');lines.innerHTML='';
   if(missing){
     let txt=String(missing.textContent||'').replace(/^\s*[⚠️⚠\s]*/,'').trim();
     const colon=txt.indexOf(':');const detail=colon>=0?txt.slice(colon+1).trim():txt.replace(/^faltan datos\s*/i,'').trim();
     const line=document.createElement('div');line.className='v493-alert-line';line.innerHTML='⚠️ <b>Faltan datos:</b> '+(detail||'completa la ficha del paciente');lines.appendChild(line);
   }
   if(badName){const line=document.createElement('div');line.className='v493-alert-line';line.innerHTML='⚠️ <b>Nombre incompleto:</b> ideal registrar dos apellidos y dos nombres';lines.appendChild(line)}
   if(complete){band.querySelector('.v493-alert-actions').appendChild(complete)}
   if(missing){missing.style.display='none'}
   const old=smallestCommon(missing,complete,box);if(old&&old!==head&&!old.classList.contains('v493-alert-band')&&!old.contains(band)){old.classList.add('v493-old-alert')}
 }
 function consultCard(box){
   const exact=leaves(box).filter(el=>norm(el.textContent)==='consulta');
   let fallback=null;
   for(const label of exact){
     let cur=label;
     for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){
       const txt=norm(cur.textContent);
       if(txt.includes('consulta')&&(txt.includes('$40')||txt.includes('40 fijo')||txt.includes('atención médica')||txt.includes('atencion medica'))&&txt.length<350){
         fallback=cur;
         if(cur.querySelector?.('input,button')||cur.onclick||cur.getAttribute?.('role'))return cur;
       }
     }
   }
   return fallback;
 }
 function ensureConsult(box){
   const grid=box.querySelector('.v492-services-grid');if(!grid)return;
   let card=grid.querySelector('.v492-consult,.v493-consult');
   if(!card)card=consultCard(box);
   if(!card)return;
   card.classList.remove('v492-empty-source','v491-hidden');card.style.removeProperty('display');
   card.classList.add('v492-service-card','v492-consult','v493-consult');
   if(!card.querySelector('.v492-service-mark')){const mark=document.createElement('span');mark.className='v492-service-mark';mark.textContent='+';card.prepend(mark)}
   if(card.parentElement!==grid)grid.insertBefore(card,grid.firstElementChild);else if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   let p=card.parentElement;while(p&&p!==box){p.classList.remove('v492-empty-source','v493-old-alert');p=p.parentElement}
 }
 function enhance(){const box=boxNow();if(!box)return;setTimeout(()=>{ensureConsult(box);ensureAlert(box)},0)}
 document.addEventListener('click',()=>{setTimeout(enhance,40);setTimeout(enhance,160)},true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,220),{once:true});else setTimeout(enhance,220);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.92"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.92"','APP_VERSION = "4.3.93"',1)
    if s.count("const VERSION=\\'4.3.92\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.92\\';","const VERSION=\\'4.3.93\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=(
      'V493_ATTENTION_CSS = r"""'+CSS+'"""\n'
      'V493_ATTENTION_JS = r"""'+JS+'"""\n'
      'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V493_ATTENTION_CSS\n'
      'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V493_ATTENTION_JS\n\n'+marker
    )
    return s.replace(marker,inject,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V493_ATTENTION_JS' in names: js=ast.literal_eval(node.value)
            if 'V493_ATTENTION_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v493 ausente')
    for token in ['ensureConsult','consultCard','v493-consult','⚠️','Nombre incompleto','Faltan datos','v493-alert-band']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v493 no debe usar MutationObserver')
    for token in ['V492_ATTENTION_JS','v492-clinical-head','v492-services-grid','v492-sticky-actions','historical_matches=_historical_review_matches(current,per_patient=24)','v488-home-action-svg','Revisando AZUR','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.93"' not in app or "const VERSION=\\'4.3.93\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v493/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.93: restaura CONSULTA como primera tarjeta y refuerza alertas de datos faltantes y nombre incompleto.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
