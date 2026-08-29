from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v494'
OUT=ROOT/'updates'/'v495'
VERSION='4.3.95'
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

CSS=r'''/* v4.3.95 — CONSULTA enlazada al selector oculto real */
.v495-consult-card{order:-2000!important;position:relative!important;min-height:66px!important;padding:10px 34px 9px 40px!important;border:1.5px solid #79bd94!important;border-radius:12px!important;background:#eaf7ef!important;display:flex!important;align-items:center!important;gap:8px!important;cursor:pointer!important;box-shadow:0 2px 9px rgba(37,110,68,.08)!important;user-select:none!important}
.v495-consult-card:hover{background:#e1f4e8!important;border-color:#55a978!important}.v495-consult-card:active{transform:translateY(1px)}
.v495-consult-icon{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:22px;height:22px;border-radius:7px;background:#d4ecde;color:#267248;display:grid;place-items:center;font-size:15px;font-weight:950}.v495-consult-copy{display:grid;gap:3px;min-width:0}.v495-consult-copy b{font-size:11.5px!important;color:#215d3d!important;line-height:1!important}.v495-consult-copy small{font-size:8.5px!important;color:#557565!important}.v495-consult-price{margin-left:auto;padding:3px 7px;border-radius:999px;background:#d5ecde;color:#246743;font-size:8px;font-weight:950;white-space:nowrap}
.v495-consult-card.is-selected{background:#d9f0e2!important;border-color:#398b5e!important;box-shadow:0 0 0 2px rgba(49,135,86,.11)!important}.v495-consult-card.is-selected .v495-consult-icon{background:#398b5e;color:#fff;font-size:0}.v495-consult-card.is-selected .v495-consult-icon:before{content:'✓';font-size:12px}
.v495-hidden-source{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
'''

JS=r''';(()=>{
 if(window.__v495ConsultFix)return;window.__v495ConsultFix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function gridNow(box){return box?.querySelector('.v492-services-grid')||null}
 function inputText(inp,box){
   let txt=[inp.id,inp.name,inp.value,inp.getAttribute('aria-label'),inp.dataset?.service,inp.dataset?.name].filter(Boolean).join(' ');
   let cur=inp.parentElement;
   for(let i=0;cur&&cur!==box&&i<5;i++,cur=cur.parentElement){const t=norm(cur.textContent);if(t&&t.length<260)txt+=' '+t}
   return norm(txt);
 }
 function hiddenConsultInput(box){
   const grid=gridNow(box);if(!grid)return null;
   const all=[...box.querySelectorAll('input[type="checkbox"],input[type="radio"]')].filter(i=>!i.disabled);
   const outside=all.filter(i=>!grid.contains(i)&&!i.closest('.v492-clinical-head')&&!i.closest('.v493-alert-band'));
   if(!outside.length)return null;
   const scored=outside.map(i=>{const t=inputText(i,box);let s=0;if(t.includes('consulta'))s+=30;if(t.includes('40'))s+=10;if(t.includes('atencion medica'))s+=10;if(t.includes('cisto'))s-=25;if(i.offsetParent===null)s+=6;return [i,s,t]}).sort((a,b)=>b[1]-a[1]);
   if(scored[0][1]>0)return scored[0][0];
   return outside.length===1?outside[0]:null;
 }
 function hideSource(inp,box){
   if(!inp)return;let cur=inp.parentElement;
   for(let i=0;cur&&cur!==box&&i<5;i++,cur=cur.parentElement){const t=norm(cur.textContent);if(t.includes('consulta')&&!t.includes('cistoscopia')&&t.length<280){cur.classList.add('v495-hidden-source');return}}
 }
 function sync(box){const grid=gridNow(box),card=grid?.querySelector('.v495-consult-card'),inp=hiddenConsultInput(box);if(card)card.classList.toggle('is-selected',!!inp?.checked)}
 function ensure(box){
   const grid=gridNow(box);if(!grid)return;
   let card=grid.querySelector('.v495-consult-card');const inp=hiddenConsultInput(box);
   if(!inp)return;
   hideSource(inp,box);
   if(!card){
     card=document.createElement('div');card.className='v495-consult-card';card.setAttribute('role','button');card.setAttribute('tabindex','0');card.innerHTML='<span class="v495-consult-icon">+</span><span class="v495-consult-copy"><b>CONSULTA</b><small>Atención médica</small></span><span class="v495-consult-price">$40 fijo</span>';
     const activate=()=>{inp.click();inp.dispatchEvent(new Event('change',{bubbles:true}));setTimeout(()=>sync(box),0);setTimeout(()=>sync(box),80)};
     card.addEventListener('click',e=>{e.preventDefault();activate()});card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}});
     grid.insertBefore(card,grid.firstElementChild);
   } else if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   sync(box);
 }
 function cleanup(box){
   const band=box.querySelector('.v493-alert-band'),grid=gridNow(box);if(!band||!grid)return;
   let el=band.nextElementSibling,guard=0;while(el&&el!==grid&&guard++<10){const next=el.nextElementSibling;const t=norm(el.textContent),interactive=!!el.querySelector?.('button,input:not([type="hidden"]),select,textarea');if(!t&&!interactive)el.classList.add('v495-hidden-source');el=next}
 }
 function enhance(){const box=boxNow();if(!box)return;ensure(box);cleanup(box);sync(box)}
 document.addEventListener('click',()=>{setTimeout(enhance,20);setTimeout(enhance,100);setTimeout(enhance,220)},true);
 document.addEventListener('change',()=>setTimeout(enhance,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,240),{once:true});else setTimeout(enhance,240);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.94"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.94"','APP_VERSION = "4.3.95"',1)
    if s.count("const VERSION=\\'4.3.94\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.94\\';","const VERSION=\\'4.3.95\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=('V495_ATTENTION_CSS = r"""'+CSS+'"""\n'+'V495_ATTENTION_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V495_ATTENTION_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V495_ATTENTION_JS\n\n'+marker)
    return s.replace(marker,inject,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V495_ATTENTION_JS' in names: js=ast.literal_eval(node.value)
            if 'V495_ATTENTION_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v495 ausente')
    for token in ['hiddenConsultInput','input[type="checkbox"]','v495-consult-card','inp.click()','grid.insertBefore(card,grid.firstElementChild)']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v495 no debe usar MutationObserver')
    for token in ['V494_ATTENTION_JS','V493_ATTENTION_JS','V492_ATTENTION_JS','v492-services-grid','v492-sticky-actions','historical_matches=_historical_review_matches(current,per_patient=24)','Revisando AZUR','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.95"' not in app or "const VERSION=\\'4.3.95\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v495/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.95: recupera CONSULTA enlazando directamente el selector oculto real en Nueva atención.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
