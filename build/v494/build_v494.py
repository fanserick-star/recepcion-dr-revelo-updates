from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v493'
OUT=ROOT/'updates'/'v494'
VERSION='4.3.94'
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

CSS=r'''/* v4.3.94 — CONSULTA garantizada + alerta legible + limpieza de huecos */
.v493-alert-band{grid-template-columns:34px minmax(0,1fr) auto!important;gap:12px!important;padding:13px 14px!important;border-width:1.5px!important;border-color:#d8a51f!important;background:linear-gradient(135deg,#fff3ad 0%,#ffe989 100%)!important;box-shadow:0 4px 14px rgba(139,96,8,.12)!important}
.v493-alert-icon{font-size:28px!important;line-height:1!important}
.v493-alert-copy{gap:5px!important}.v493-alert-title{font-size:13px!important;line-height:1.15!important;font-weight:950!important;color:#5c4107!important}.v493-alert-line{font-size:11.5px!important;line-height:1.3!important;color:#654d17!important}.v493-alert-line b{font-weight:950!important;color:#4d3504!important}
.v493-alert-actions button{min-height:39px!important;padding:8px 14px!important;font-size:10.5px!important;border-width:1.5px!important;background:#fff9dc!important}
.v494-consult-proxy{order:-1000!important;position:relative!important;min-height:64px!important;padding:10px 30px 9px 39px!important;border:1.5px solid #8fc9a6!important;border-radius:12px!important;background:#ebf8f0!important;box-shadow:0 2px 8px rgba(38,112,70,.07)!important;display:flex!important;align-items:center!important;cursor:pointer!important;color:#245f41!important;user-select:none!important}
.v494-consult-proxy:hover{background:#e2f5ea!important;border-color:#62ac80!important}.v494-consult-proxy:active{transform:translateY(1px)}
.v494-consult-proxy .v494-consult-mark{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:21px;height:21px;border-radius:7px;background:#d8efe1;color:#28754c;display:grid;place-items:center;font-size:15px;font-weight:950}.v494-consult-proxy .v494-consult-copy{display:grid;gap:3px;min-width:0}.v494-consult-proxy .v494-consult-copy b{font-size:11px!important;line-height:1!important;color:#245f41!important}.v494-consult-proxy .v494-consult-copy small{font-size:8px!important;color:#557764!important}.v494-consult-proxy .v494-consult-price{margin-left:auto;padding:3px 6px;border-radius:999px;background:#d8efe1;color:#276b49;font-size:7.5px;font-weight:950;white-space:nowrap}
.v494-consult-proxy.is-selected{background:#dff3e7!important;border-color:#45966a!important;box-shadow:0 0 0 2px rgba(49,135,86,.11)!important}.v494-consult-proxy.is-selected .v494-consult-mark{background:#418c62;color:#fff;font-size:0}.v494-consult-proxy.is-selected .v494-consult-mark::before{content:'✓';font-size:12px}
.v494-ghost-hidden{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
@media(max-width:700px){.v493-alert-band{grid-template-columns:32px 1fr!important}.v493-alert-actions{grid-column:1/-1!important}.v493-alert-title{font-size:12px!important}.v493-alert-line{font-size:10.5px!important}}
'''

JS=r''';(()=>{
 if(window.__v494AttentionHotfix)return;window.__v494AttentionHotfix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function gridNow(box){return box?.querySelector('.v492-services-grid')||null}
 function candidateScore(el){
   const t=norm(el.textContent);if(!t.includes('consulta'))return -1;if(t.includes('cistoscopia')||t.includes('consulta nuevamente'))return -1;
   let s=5;if(t.includes('$40')||t.includes('40 fijo')||t.includes('atencion medica'))s+=8;
   if(el.matches('button,label,[role="button"]'))s+=7;if(el.querySelector?.('input[type="checkbox"],input[type="radio"],button'))s+=5;
   if(t.length<180)s+=4;if(el.closest('.v492-services-grid'))s-=4;return s;
 }
 function originalConsult(box){
   const all=[...box.querySelectorAll('button,label,div,section,article,span')].filter(el=>el!==box&&norm(el.textContent).includes('consulta'));
   all.sort((a,b)=>candidateScore(b)-candidateScore(a)||norm(a.textContent).length-norm(b.textContent).length);
   const host=all.find(el=>candidateScore(el)>=9)||null;if(!host)return null;
   let root=host;
   for(let i=0;root&&root!==box&&i<5;i++,root=root.parentElement){
     const t=norm(root.textContent),n=root.querySelectorAll?.('input[type="checkbox"],input[type="radio"]').length||0;
     if(t.includes('consulta')&&!t.includes('cistoscopia')&&t.length<260&&(n===1||root.matches?.('button,label,[role="button"]')))return root;
   }
   return host;
 }
 function actionInside(host){
   if(!host)return null;
   const inp=host.matches?.('input[type="checkbox"],input[type="radio"]')?host:host.querySelector?.('input[type="checkbox"],input[type="radio"]');if(inp)return inp;
   const btn=host.matches?.('button,[role="button"],label')?host:host.querySelector?.('button,[role="button"],label');return btn||host;
 }
 function selected(host){const inp=host?.matches?.('input[type="checkbox"],input[type="radio"]')?host:host?.querySelector?.('input[type="checkbox"],input[type="radio"]');if(inp)return !!inp.checked;return host?.classList?.contains('is-selected')||host?.classList?.contains('selected')||false}
 function triggerOriginal(host){
   const act=actionInside(host);if(!act)return;
   if(act.matches?.('input[type="checkbox"],input[type="radio"]')){act.click();return}
   act.click?.();
 }
 function ensureConsult(box){
   const grid=gridNow(box);if(!grid)return;
   const oldVisible=[...grid.children].find(el=>/\bconsulta\b/.test(norm(el.textContent))&&!norm(el.textContent).includes('cistoscopia'));
   if(oldVisible){oldVisible.classList.add('v493-consult');return}
   const original=originalConsult(box);let proxy=grid.querySelector('.v494-consult-proxy');
   if(!proxy){proxy=document.createElement('div');proxy.className='v494-consult-proxy';proxy.setAttribute('role','button');proxy.setAttribute('tabindex','0');proxy.innerHTML='<span class="v494-consult-mark">+</span><span class="v494-consult-copy"><b>CONSULTA</b><small>Atención médica</small></span><span class="v494-consult-price">$40 fijo</span>';grid.insertBefore(proxy,grid.firstElementChild);proxy.addEventListener('click',e=>{e.preventDefault();const h=originalConsult(box);triggerOriginal(h);setTimeout(()=>syncConsult(box),0);setTimeout(()=>syncConsult(box),80)});proxy.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();proxy.click()}})}
   proxy.classList.toggle('is-selected',selected(original));
 }
 function syncConsult(box){const p=gridNow(box)?.querySelector('.v494-consult-proxy');if(!p)return;const h=originalConsult(box);p.classList.toggle('is-selected',selected(h))}
 function cleanGhosts(box){
   const band=box.querySelector('.v493-alert-band'),grid=gridNow(box);if(!band||!grid)return;
   let el=band.nextElementSibling;let guard=0;
   while(el&&el!==grid&&guard++<12){const next=el.nextElementSibling;const t=norm(el.textContent);const interactive=!!el.querySelector?.('button,input,select,textarea');const structural=el.classList?.contains('v492-selection-head')||el.classList?.contains('v492-empty-source')||el.classList?.contains('v491-attention-title')||el.classList?.contains('v493-old-alert');if((!t&&!interactive)||structural)el.classList.add('v494-ghost-hidden');el=next}
   [...box.querySelectorAll('.v492-empty-source,.v493-old-alert')].forEach(el=>{if(!el.contains(grid)&&!el.contains(band))el.classList.add('v494-ghost-hidden')});
 }
 function enlargeAlert(box){const band=box.querySelector('.v493-alert-band');if(!band)return;const title=band.querySelector('.v493-alert-title');if(title)title.textContent='⚠️ Atención al registro del paciente'}
 function enhance(){const box=boxNow();if(!box)return;ensureConsult(box);enlargeAlert(box);cleanGhosts(box);syncConsult(box)}
 document.addEventListener('click',()=>{setTimeout(enhance,20);setTimeout(enhance,100);setTimeout(enhance,220)},true);
 document.addEventListener('change',()=>setTimeout(enhance,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,250),{once:true});else setTimeout(enhance,250);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.93"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.93"','APP_VERSION = "4.3.94"',1)
    if s.count("const VERSION=\\'4.3.93\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.93\\';","const VERSION=\\'4.3.94\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=('V494_ATTENTION_CSS = r"""'+CSS+'"""\n'+'V494_ATTENTION_JS = r"""'+JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V494_ATTENTION_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V494_ATTENTION_JS\n\n'+marker)
    return s.replace(marker,inject,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V494_ATTENTION_JS' in names: js=ast.literal_eval(node.value)
            if 'V494_ATTENTION_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v494 ausente')
    for token in ['v494-consult-proxy','originalConsult','triggerOriginal','cleanGhosts','v494-ghost-hidden','font-size:13px','font-size:11.5px']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v494 no debe usar MutationObserver')
    for token in ['V493_ATTENTION_JS','V492_ATTENTION_JS','v492-clinical-head','v492-services-grid','v492-sticky-actions','historical_matches=_historical_review_matches(current,per_patient=24)','v488-home-action-svg','Revisando AZUR','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.94"' not in app or "const VERSION=\\'4.3.94\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v494/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.94: garantiza CONSULTA como primera tarjeta, agranda alertas y elimina franjas vacías en Nueva atención.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
