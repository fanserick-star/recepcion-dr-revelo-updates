from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v490'
OUT=ROOT/'updates'/'v491'
VERSION='4.3.91'
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

CSS=r'''/* v4.3.91 — Nueva atención profesional, compacta y sin redundancias */
.v490-attention-bar{display:none!important}
.modalbox.v491-attention-pro{width:min(920px,96vw)!important;max-height:88vh!important;padding:16px 18px 15px!important;overflow:auto!important;scrollbar-gutter:stable}
.v491-attention-pro .modal-form-heading{margin:0 0 9px!important}.v491-attention-pro .modal-form-heading h2{margin:0 0 2px!important;font-size:24px!important;line-height:1.05!important;letter-spacing:-.02em}.v491-attention-pro .modal-form-heading p{margin:0!important;font-size:9.5px!important;color:#6e7f91!important}
.v491-attention-pro .v491-hidden{display:none!important}
.v491-attention-pro .v491-overview-grid{display:grid!important;grid-template-columns:minmax(0,1.7fr) minmax(180px,.75fr) minmax(205px,.8fr)!important;gap:9px!important;align-items:stretch!important;margin:0 0 12px!important}
.v491-attention-pro .v491-overview-grid>.v491-patient-card,.v491-attention-pro .v491-overview-grid>.v491-type-card,.v491-attention-pro .v491-overview-grid>.v491-date-card{margin:0!important;min-height:0!important;height:auto!important}
.v491-attention-pro .v491-patient-card,.v491-attention-pro .v491-type-card,.v491-attention-pro .v491-date-card{padding:11px 12px!important;border-radius:12px!important}
.v491-attention-pro .v491-patient-card{background:#fff!important;border:1px solid #dfe6ee!important}.v491-attention-pro .v491-patient-card h3,.v491-attention-pro .v491-patient-card strong{line-height:1.12!important}
.v491-attention-pro .v491-type-card{background:#eef8f2!important;border:1px solid #cee6d7!important;display:flex!important;flex-direction:column!important;justify-content:center!important;gap:3px!important}
.v491-attention-pro .v491-type-label{display:none!important}.v491-attention-pro .v491-type-value{display:inline-flex!important;align-items:center!important;width:max-content!important;max-width:100%;padding:4px 8px!important;border-radius:999px!important;background:#dff2e7!important;color:#286946!important;font-size:9px!important;font-weight:950!important;letter-spacing:.055em!important}
.v491-attention-pro .v491-type-card small,.v491-attention-pro .v491-type-card span:not(.v491-type-value){font-size:8.5px!important;line-height:1.2!important;color:#557363!important}
.v491-attention-pro .v491-date-card{background:#f8fafc!important;border:1px solid #dfe6ee!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:8px!important}.v491-attention-pro .v491-date-card input{min-height:36px!important;height:36px!important;font-size:10.5px!important;padding:7px 9px!important}
.v491-attention-pro .v491-attention-title{margin-top:3px!important;margin-bottom:2px!important;font-size:18px!important;letter-spacing:-.01em!important}.v491-attention-pro .v491-selection-help{font-size:8.5px!important;color:#7a8998!important;margin:0 0 7px!important}.v491-attention-pro .v491-selection-count{display:inline-flex!important;align-items:center!important;padding:4px 8px!important;border-radius:999px!important;background:#edf6f2!important;color:#376c56!important;font-size:8.5px!important;font-weight:850!important;white-space:nowrap!important}
.v491-attention-pro .v491-observation-wrap{display:none!important}
.v491-attention-pro textarea[placeholder*="Observ" i]{display:none!important}
.v491-attention-pro .modal-actions,.v491-attention-pro .form-actions{margin-top:10px!important;padding-top:9px!important;border-top:1px solid #e7edf3!important;background:#fff!important}
.v491-attention-pro button{transition:background .12s ease,border-color .12s ease,transform .08s ease}.v491-attention-pro button:active{transform:translateY(1px)}
@media(max-width:760px){.v491-attention-pro .v491-overview-grid{grid-template-columns:1fr!important}.modalbox.v491-attention-pro{width:96vw!important;padding:14px 13px!important}.v491-attention-pro .v491-date-card{justify-content:flex-start!important}}
'''

JS=r''';(()=>{
 if(window.__v491AttentionPro)return;window.__v491AttentionPro=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=(box)=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function attentionBox(){
   return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(box=>[...box.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención'))||null;
 }
 function leaf(box,test){return leaves(box).find(el=>test(norm(el.textContent),el))||null}
 function sectionFor(el,needles,box){
   let cur=el;
   for(let i=0;cur&&cur!==box&&i<6;i++,cur=cur.parentElement){
     const txt=norm(cur.textContent);
     if(needles.every(n=>txt.includes(n))&&txt.length<900)return cur;
   }
   return el?.parentElement||null;
 }
 function hideObservation(box){
   [...box.querySelectorAll('textarea')].forEach(ta=>{
     const ph=norm(ta.getAttribute('placeholder'));
     let lab=null;let prev=ta.previousElementSibling;
     if(prev&&/observ/.test(norm(prev.textContent)))lab=prev;
     const parent=ta.parentElement;
     if(ph.includes('observ')||lab||/observ/.test(norm(parent?.textContent||''))){
       const wrap=parent&&parent!==box?parent:ta;
       wrap.classList.add('v491-observation-wrap');
       ta.value='';
     }
   });
   leaves(box).filter(el=>/^observaci[oó]n/.test(norm(el.textContent))).forEach(el=>el.classList.add('v491-hidden'));
 }
 function compactOverview(box){
   const patientLabel=leaf(box,t=>t==='paciente');
   const typeLabel=leaf(box,t=>t==='tipo de paciente detectado');
   const dateLabel=leaf(box,t=>t==='fecha de atención');
   const pCard=patientLabel?sectionFor(patientLabel,['paciente'],box):null;
   const tCard=typeLabel?sectionFor(typeLabel,['tipo de paciente detectado'],box):null;
   let dCard=null;
   if(dateLabel){
     let cur=dateLabel;
     for(let i=0;cur&&cur!==box&&i<6;i++,cur=cur.parentElement){if(cur.querySelector?.('input')){dCard=cur;break}}
     dCard=dCard||dateLabel.parentElement;
   }
   if(pCard)pCard.classList.add('v491-patient-card');
   if(tCard){tCard.classList.add('v491-type-card');typeLabel.classList.add('v491-type-label');const val=leaf(tCard,t=>t==='subsecuente'||t==='nuevo');if(val)val.classList.add('v491-type-value')}
   if(dCard)dCard.classList.add('v491-date-card');
   if(pCard&&tCard&&dCard&&pCard!==tCard&&pCard!==dCard&&tCard!==dCard){
     const parent=pCard.parentElement;
     if(parent&&tCard.parentElement===parent&&dCard.parentElement===parent)parent.classList.add('v491-overview-grid');
   }
   const missing=leaf(box,t=>t.includes('faltan datos'));
   if(missing){const redundant=leaf(box,t=>t.includes('sin cédula o identificación registrada')||t.includes('sin cedula o identificacion registrada'));if(redundant)redundant.classList.add('v491-hidden')}
 }
 function cleanSelection(box){
   const title=leaf(box,t=>t==='selecciona la atención');if(title){title.textContent='Atención realizada';title.classList.add('v491-attention-title')}
   const redundant=leaf(box,t=>t.includes('no hay ninguna opción marcada por defecto'));if(redundant)redundant.classList.add('v491-hidden');
   const count=leaf(box,t=>t.includes('puedes elegir varias')&&t.includes('seleccionad'));
   if(count){count.textContent=String(count.textContent||'').replace(/puedes elegir varias\s*[·•-]?\s*/i,'').trim()||'0 seleccionadas';count.classList.add('v491-selection-count')}
   const procHelp=leaf(box,t=>t.includes('selecciona uno o varios si corresponde'));if(procHelp){procHelp.textContent='Puedes seleccionar uno o varios';procHelp.classList.add('v491-selection-help')}
 }
 function enhance(){
   const box=attentionBox();if(!box)return;
   box.classList.add('v491-attention-pro');
   box.querySelectorAll('.v490-attention-bar').forEach(x=>x.remove());
   hideObservation(box);compactOverview(box);cleanSelection(box);
 }
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,80);setTimeout(enhance,180)},true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,120),{once:true});else setTimeout(enhance,120);
})();'''

def patch_app(s):
    if s.count('APP_VERSION = "4.3.90"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.90"','APP_VERSION = "4.3.91"',1)
    if s.count("const VERSION=\\'4.3.90\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.90\\';","const VERSION=\\'4.3.91\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=(
      'V491_ATTENTION_CSS = r"""'+CSS+'"""\n'
      'V491_ATTENTION_JS = r"""'+JS+'"""\n'
      'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V491_ATTENTION_CSS\n'
      'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V491_ATTENTION_JS\n\n'+marker
    )
    return s.replace(marker,inject,1)

def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V491_ATTENTION_JS' in names: js=ast.literal_eval(node.value)
            if 'V491_ATTENTION_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v491 ausente')
    for token in ['v491-attention-pro','v491-overview-grid','Atención realizada','hideObservation','v490-attention-bar']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v491 no debe usar MutationObserver')
    if 'v490-attention-bar{display:none!important}' not in css: raise SystemExit('no se revierte barra v490')
    for token in ['historical_matches=_historical_review_matches(current,per_patient=24)','V488_HOME_CSS','v488-home-action-svg','V487_ICON_JS','Revisando AZUR','V486_FIX_JS','v486OpenAzur','V485_FIX_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.91"' not in app or "const VERSION=\\'4.3.91\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v491/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.91: remaster profesional de Nueva atención, elimina Observación y redundancias y compacta paciente/tipo/fecha sin duplicar Guardar.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
