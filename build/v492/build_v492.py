from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v491'
OUT=ROOT/'updates'/'v492'
VERSION='4.3.92'
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

CSS=r'''/* v4.3.92 — remaster estructural real de Nueva atención */
.v490-attention-bar{display:none!important}
.modalbox.v492-attention{width:min(980px,97vw)!important;max-height:90vh!important;padding:15px 17px 0!important;overflow:auto!important;scrollbar-gutter:stable;background:#fbfcfe!important}
.v492-attention .modal-form-heading{margin:0 0 9px!important}.v492-attention .modal-form-heading h2{font-size:23px!important;line-height:1.05!important;margin:0 0 2px!important;letter-spacing:-.025em}.v492-attention .modal-form-heading p{font-size:9.5px!important;margin:0!important;color:#708095!important}
.v492-attention .v491-overview-grid{display:block!important;margin:0!important}.v492-attention .v491-patient-card,.v492-attention .v491-type-card,.v492-attention .v491-date-card{margin:0!important}
.v492-clinical-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(250px,310px);gap:10px;align-items:stretch;margin:0 0 13px;padding:10px 11px;border:1px solid #dbe4ed;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(39,61,83,.045)}
.v492-head-main{min-width:0;display:flex;align-items:center}.v492-head-main>.v491-patient-card{width:100%!important;padding:3px 5px!important;border:0!important;background:transparent!important;box-shadow:none!important;min-height:0!important}
.v492-head-main .v491-hidden{display:none!important}.v492-head-main strong,.v492-head-main h3{font-size:16px!important;line-height:1.12!important;letter-spacing:-.01em!important}.v492-head-main button{min-height:30px!important;padding:6px 9px!important;font-size:8.5px!important;border-radius:9px!important}
.v492-head-main [class*="warn"],.v492-head-main [class*="missing"]{font-size:8.5px!important;padding:5px 8px!important;border-radius:9px!important}
.v492-head-side{display:grid;grid-template-columns:1fr;gap:6px;align-content:center;border-left:1px solid #e6edf3;padding-left:10px;min-width:0}
.v492-head-side>.v491-type-card,.v492-head-side>.v491-date-card{padding:7px 9px!important;border:0!important;border-radius:10px!important;min-height:0!important;height:auto!important;box-shadow:none!important}
.v492-head-side>.v491-type-card{background:#edf8f2!important}.v492-head-side>.v491-date-card{background:#f5f8fb!important;display:flex!important;align-items:center!important;gap:7px!important}
.v492-head-side .v491-type-value{font-size:8.5px!important;padding:3px 7px!important}.v492-head-side .v491-type-card small,.v492-head-side .v491-type-card span:not(.v491-type-value){font-size:7.8px!important}
.v492-head-side .v491-date-card label,.v492-head-side .v491-date-card>span,.v492-head-side .v491-date-card>div:first-child{font-size:8px!important;font-weight:850!important;color:#6b7b8f!important}.v492-head-side .v491-date-card input{height:31px!important;min-height:31px!important;padding:5px 7px!important;font-size:9.5px!important;background:#fff!important}
.v492-attention .v492-selection-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:1px 2px 8px}.v492-attention .v492-selection-head h3{font-size:17px!important;margin:0!important;letter-spacing:-.015em;color:#25384f}.v492-attention .v492-selection-count{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:#edf6f2;color:#376d56;font-size:8.5px;font-weight:900;white-space:nowrap}
.v492-services-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 10px!important;padding:0!important}
.v492-service-card{position:relative!important;min-width:0!important;min-height:64px!important;height:auto!important;margin:0!important;padding:10px 31px 9px 38px!important;border:1px solid #dce5ee!important;border-radius:12px!important;background:#fff!important;box-shadow:0 2px 7px rgba(43,63,84,.035)!important;display:flex!important;align-items:center!important;cursor:pointer!important;transition:border-color .12s ease,background .12s ease,box-shadow .12s ease,transform .08s ease!important}
.v492-service-card:hover{border-color:#b9cce0!important;background:#f8fbfe!important}.v492-service-card:active{transform:translateY(1px)}
.v492-service-card.v492-consult{border-color:#c8e3d3!important;background:#f3faf6!important}.v492-service-card.is-selected{border-color:#6fa0ce!important;background:#eef6fd!important;box-shadow:0 0 0 2px rgba(69,129,184,.10)!important}.v492-service-card.v492-consult.is-selected{border-color:#65aa83!important;background:#eaf7ef!important;box-shadow:0 0 0 2px rgba(58,145,96,.10)!important}
.v492-service-mark{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:20px;height:20px;border-radius:7px;display:grid;place-items:center;background:#edf3f9;color:#4f769f;font-size:14px;font-weight:900;line-height:1}.v492-consult .v492-service-mark{background:#e0f2e7;color:#2d7850}.v492-service-card.is-selected .v492-service-mark{background:#5a8fbe;color:#fff}.v492-service-card.v492-consult.is-selected .v492-service-mark{background:#418c62;color:#fff}.v492-service-card.is-selected .v492-service-mark::before{content:'✓';font-size:12px}.v492-service-card.is-selected .v492-service-mark{font-size:0}
.v492-service-card input[type="checkbox"],.v492-service-card input[type="radio"]{position:absolute!important;right:9px!important;top:9px!important;width:16px!important;height:16px!important;margin:0!important;opacity:.38}.v492-service-card.is-selected input[type="checkbox"],.v492-service-card.is-selected input[type="radio"]{opacity:1}
.v492-service-card strong,.v492-service-card b{font-size:10.5px!important;line-height:1.08!important}.v492-service-card small,.v492-service-card span,.v492-service-card div{line-height:1.15}.v492-service-card small{font-size:8px!important;color:#748498!important}.v492-service-card .v492-editable{display:inline-flex!important;width:max-content!important;margin-top:3px!important;padding:2px 5px!important;border-radius:999px!important;background:#f0f3f7!important;color:#6a7788!important;font-size:7px!important;font-weight:850!important}
.v492-empty-source,.v492-observation-hidden{display:none!important}.v492-attention textarea[placeholder*="Observ" i]{display:none!important}
.v492-attention .v491-attention-title,.v492-attention .v491-selection-help,.v492-attention .v491-selection-count{display:none!important}
.v492-sticky-actions{position:sticky!important;bottom:0!important;z-index:80!important;margin:8px -17px 0!important;padding:9px 17px 11px!important;border-top:1px solid #dde6ef!important;background:rgba(251,252,254,.98)!important;box-shadow:0 -6px 18px rgba(36,57,78,.07)!important;backdrop-filter:blur(4px)}
.v492-sticky-actions button{min-height:36px!important;border-radius:10px!important;font-size:10px!important}.v492-sticky-actions button:last-child{padding-left:18px!important;padding-right:18px!important;font-weight:900!important}
@media(max-width:900px){.v492-services-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.v492-clinical-head{grid-template-columns:minmax(0,1fr) minmax(220px,270px)}}
@media(max-width:700px){.modalbox.v492-attention{width:97vw!important;padding:13px 12px 0!important}.v492-clinical-head{grid-template-columns:1fr}.v492-head-side{border-left:0;border-top:1px solid #e6edf3;padding-left:0;padding-top:7px;grid-template-columns:1fr 1fr}.v492-services-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.v492-sticky-actions{margin-left:-12px!important;margin-right:-12px!important;padding-left:12px!important;padding-right:12px!important}}
'''

JS=r''';(()=>{
 if(window.__v492Attention)return;window.__v492Attention=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=box=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención'))||null}
 function leaf(box,fn){return leaves(box).find(el=>fn(norm(el.textContent),el))||null}
 function cardAround(el,box,needsInput=false){
   let cur=el;
   for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){
     if(needsInput&&cur.querySelector?.('input'))return cur;
     const txt=norm(cur.textContent);if(!needsInput&&txt.length>0&&txt.length<700&&cur.children.length>0)return cur;
   }
   return el?.parentElement||null;
 }
 function findOverview(box){
   const pLab=leaf(box,t=>t==='paciente');
   const tLab=leaf(box,t=>t==='tipo de paciente detectado');
   const dLab=leaf(box,t=>t==='fecha de atención');
   const pCard=pLab?cardAround(pLab,box,false):null;
   let tCard=tLab?cardAround(tLab,box,false):null;
   let dCard=dLab?dLab.parentElement:null;
   if(dLab){let c=dLab;for(let i=0;c&&c!==box&&i<7;i++,c=c.parentElement){if(c.querySelector?.('input[type="date"],input')){dCard=c;break}}}
   if(tCard){tCard.classList.add('v491-type-card');tLab.classList.add('v491-type-label');const v=leaf(tCard,t=>t==='subsecuente'||t==='nuevo');if(v)v.classList.add('v491-type-value')}
   if(pCard)pCard.classList.add('v491-patient-card');if(dCard)dCard.classList.add('v491-date-card');
   return {pCard,tCard,dCard};
 }
 function buildHeader(box){
   let head=box.querySelector('.v492-clinical-head');if(head)return head;
   const {pCard,tCard,dCard}=findOverview(box);if(!pCard||!tCard||!dCard)return null;
   if(pCard===tCard||pCard===dCard||tCard===dCard)return null;
   head=document.createElement('section');head.className='v492-clinical-head';
   const main=document.createElement('div');main.className='v492-head-main';
   const side=document.createElement('div');side.className='v492-head-side';
   const heading=[...box.querySelectorAll('h1,h2,h3')].find(h=>norm(h.textContent)==='nueva atención');
   const headingWrap=heading?.closest('.modal-form-heading')||heading?.parentElement;
   if(headingWrap)headingWrap.insertAdjacentElement('afterend',head);else box.prepend(head);
   main.appendChild(pCard);side.appendChild(tCard);side.appendChild(dCard);head.append(main,side);
   const patientLabel=leaf(pCard,t=>t==='paciente');if(patientLabel)patientLabel.style.display='none';
   const redundant=leaf(pCard,t=>t.includes('sin cédula o identificación registrada')||t.includes('sin cedula o identificacion registrada'));const missing=leaf(pCard,t=>t.includes('faltan datos'));if(redundant&&missing)redundant.style.display='none';
   return head;
 }
 function serviceCardForInput(inp,box){
   let cur=inp.parentElement,best=null;
   for(let i=0;cur&&cur!==box&&i<6;i++,cur=cur.parentElement){
     const text=norm(cur.textContent);const inputCount=cur.querySelectorAll?.('input[type="checkbox"],input[type="radio"]').length||0;
     if(inputCount===1&&text.length>2&&text.length<260)best=cur;
   }
   return best||inp.parentElement;
 }
 function buildServices(box){
   let grid=box.querySelector('.v492-services-grid');
   const inputs=[...box.querySelectorAll('input[type="checkbox"],input[type="radio"]')].filter(i=>!i.disabled&&i.offsetParent!==null);
   const cards=[];const seen=new Set();
   for(const inp of inputs){const c=serviceCardForInput(inp,box);if(c&&!seen.has(c)){seen.add(c);cards.push(c)}}
   if(!cards.length)return null;
   if(!grid){
     grid=document.createElement('div');grid.className='v492-services-grid';
     const title=leaf(box,t=>t==='atención realizada'||t==='selecciona la atención');
     let anchor=title?.parentElement||null;
     const head=document.createElement('div');head.className='v492-selection-head';head.innerHTML='<h3>Atención realizada</h3><span class="v492-selection-count">0 seleccionadas</span>';
     if(anchor)anchor.insertAdjacentElement('beforebegin',head);else box.appendChild(head);
     head.insertAdjacentElement('afterend',grid);
     if(anchor)anchor.classList.add('v492-empty-source');
   }
   for(const card of cards){
     if(!card.classList.contains('v492-service-card')){
       const old=card.parentElement;card.classList.add('v492-service-card');
       const txt=norm(card.textContent);if(/(^|\s)consulta(\s|$)/.test(txt)&&!txt.includes('cisto'))card.classList.add('v492-consult');
       const mark=document.createElement('span');mark.className='v492-service-mark';mark.textContent='+';card.prepend(mark);
       const editable=[...card.querySelectorAll('small,span,div')].find(x=>x.children.length===0&&norm(x.textContent).includes('valor editable'));if(editable){editable.textContent='Editable';editable.classList.add('v492-editable')}
       grid.appendChild(card);
       if(old&&old!==box&&!old.querySelector('input[type="checkbox"],input[type="radio"]')&&norm(old.textContent).length<180)old.classList.add('v492-empty-source');
     } else if(card.parentElement!==grid){grid.appendChild(card)}
   }
   return grid;
 }
 function hideObservation(box){
   [...box.querySelectorAll('textarea')].forEach(ta=>{const ph=norm(ta.placeholder);if(ph.includes('observ')||norm(ta.parentElement?.textContent).includes('observ')){ta.value='';(ta.parentElement||ta).classList.add('v492-observation-hidden')}});
   leaves(box).filter(x=>/^observaci[oó]n/.test(norm(x.textContent))).forEach(x=>x.classList.add('v492-observation-hidden'));
 }
 function stickyActions(box){
   const save=[...box.querySelectorAll('button,input[type="button"],input[type="submit"]')].find(el=>!el.classList.contains('v490-save-btn')&&norm(el.textContent||el.value).includes('guardar atención'));
   if(!save)return null;let row=save.parentElement;
   for(let i=0;row&&row!==box&&i<4;i++,row=row.parentElement){const buttons=row.querySelectorAll?.('button,input[type="button"],input[type="submit"]').length||0;if(buttons>=2)break}
   row=row&&row!==box?row:save.parentElement;if(row)row.classList.add('v492-sticky-actions');return row;
 }
 function sync(box){
   const count=box.querySelectorAll('.v492-service-card input[type="checkbox"]:checked,.v492-service-card input[type="radio"]:checked').length;
   const pill=box.querySelector('.v492-selection-count');if(pill)pill.textContent=count===1?'1 seleccionada':`${count} seleccionadas`;
   box.querySelectorAll('.v492-service-card').forEach(c=>c.classList.toggle('is-selected',!!c.querySelector('input:checked')));
 }
 function enhance(){
   const box=boxNow();if(!box)return;box.classList.add('v492-attention');box.querySelectorAll('.v490-attention-bar').forEach(x=>x.remove());
   const sub=box.querySelector('.modal-form-heading p');if(sub)sub.textContent='Confirma el paciente y registra la atención realizada.';
   buildHeader(box);buildServices(box);hideObservation(box);stickyActions(box);
   const oldTitle=leaf(box,t=>t==='atención realizada'||t==='selecciona la atención');if(oldTitle&&oldTitle.closest('.v492-selection-head')==null){const parent=oldTitle.parentElement;if(parent)parent.classList.add('v492-empty-source')}
   ['consulta','procedimientos'].forEach(word=>{leaves(box).filter(x=>norm(x.textContent)===word).forEach(x=>{const p=x.parentElement;if(p&&!p.closest('.v492-service-card')&&!p.closest('.v492-selection-head'))p.classList.add('v492-empty-source')})});
   sync(box);
 }
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,70);setTimeout(enhance,170)},true);
 document.addEventListener('change',()=>setTimeout(()=>{const b=boxNow();if(b){enhance();sync(b)}},0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,120),{once:true});else setTimeout(enhance,120);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.91"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.91"','APP_VERSION = "4.3.92"',1)
    if s.count("const VERSION=\\'4.3.91\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.91\\';","const VERSION=\\'4.3.92\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=(
      'V492_ATTENTION_CSS = r"""'+CSS+'"""\n'
      'V492_ATTENTION_JS = r"""'+JS+'"""\n'
      'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V492_ATTENTION_CSS\n'
      'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V492_ATTENTION_JS\n\n'+marker
    )
    return s.replace(marker,inject,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V492_ATTENTION_JS' in names: js=ast.literal_eval(node.value)
            if 'V492_ATTENTION_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v492 ausente')
    for token in ['v492-clinical-head','v492-services-grid','v492-sticky-actions','buildHeader','buildServices','hideObservation','sync(box)','repeat(4,minmax(0,1fr))']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v492 no debe usar MutationObserver')
    if 'v490-attention-bar{display:none!important}' not in css: raise SystemExit('no revierte barra duplicada')
    for token in ['historical_matches=_historical_review_matches(current,per_patient=24)','V488_HOME_CSS','v488-home-action-svg','V487_ICON_JS','Revisando AZUR','V486_FIX_JS','v486OpenAzur','V485_FIX_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.92"' not in app or "const VERSION=\\'4.3.92\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v492/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.92: remaster estructural de Nueva atención con cabecera clínica única, servicios en cuadrícula, sin Observación y un solo Guardar sticky.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
