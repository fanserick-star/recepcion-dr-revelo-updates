from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v489'
OUT=ROOT/'updates'/'v490'
VERSION='4.3.90'
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

CSS=r'''/* v4.3.90 — remaster de Nueva atención: acción siempre visible */
.modalbox.v490-attention-remaster{width:min(900px,96vw)!important;max-height:88vh!important;padding:17px 20px 16px!important;overflow:auto!important;scrollbar-gutter:stable}
.v490-attention-remaster .v490-attention-bar{position:sticky;top:-1px;z-index:90;display:flex;align-items:center;justify-content:space-between;gap:12px;margin:9px 0 13px;padding:9px 10px 9px 12px;border:1px solid #d7e3ef;border-radius:12px;background:rgba(248,251,255,.97);box-shadow:0 5px 16px rgba(40,64,92,.10)}
.v490-attention-remaster .v490-attention-bar-left{display:flex;align-items:center;gap:9px;min-width:0}
.v490-attention-remaster .v490-attention-bar-icon{width:28px;height:28px;display:grid;place-items:center;border-radius:9px;background:#e8f4ee;color:#28704d;flex:0 0 28px}
.v490-attention-remaster .v490-attention-bar-icon svg{width:16px;height:16px;display:block;stroke:currentColor;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
.v490-attention-remaster .v490-attention-copy{display:grid;gap:1px;min-width:0}.v490-attention-remaster .v490-attention-copy b{font-size:9px;line-height:1;letter-spacing:.09em;color:#5c6d82;text-transform:uppercase}.v490-attention-remaster .v490-attention-copy span{font-size:11px;font-weight:800;color:#263b55;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.v490-attention-remaster .v490-save-btn{border:0;border-radius:10px;min-height:37px;padding:8px 15px;background:#287fc4;color:#fff;font-size:10.5px;font-weight:900;box-shadow:0 4px 10px rgba(40,127,196,.18);white-space:nowrap;cursor:pointer}
.v490-attention-remaster .v490-save-btn:hover:not(:disabled){filter:brightness(.96)}.v490-attention-remaster .v490-save-btn:disabled{background:#c9d4df;color:#f8fafc;box-shadow:none;cursor:not-allowed}
.v490-attention-remaster textarea{min-height:52px!important;max-height:74px!important}
.v490-attention-remaster .modal-form-heading{margin-bottom:6px!important}.v490-attention-remaster .modal-form-heading h2{margin-bottom:2px!important}
@media(max-width:700px){.modalbox.v490-attention-remaster{width:96vw!important;padding:14px 13px 12px!important}.v490-attention-remaster .v490-attention-bar{gap:8px;padding:8px}.v490-attention-remaster .v490-attention-copy span{font-size:10px}.v490-attention-remaster .v490-save-btn{padding:8px 11px;font-size:9.5px}}
'''

JS=r''';(()=>{
 if(window.__v490AttentionRemaster)return;window.__v490AttentionRemaster=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 function attentionBox(){
   const boxes=[...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')];
   return boxes.find(box=>[...box.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención')&&findOriginalSave(box))||null;
 }
 function findOriginalSave(box){
   return [...box.querySelectorAll('button,input[type="button"],input[type="submit"]')].find(el=>{
     if(el.classList?.contains('v490-save-btn'))return false;
     const t=norm(el.textContent||el.value);return t.includes('guardar atención')||t.includes('guardando');
   })||null;
 }
 function selectionText(box){
   const leaves=[...box.querySelectorAll('span,b,small,div')].filter(el=>el.children.length===0&&/seleccionad/.test(norm(el.textContent)));
   leaves.sort((a,b)=>String(a.textContent||'').length-String(b.textContent||'').length);
   if(leaves.length){
     let txt=String(leaves[0].textContent||'').replace(/puedes elegir varias\s*[·•-]?\s*/i,'').trim();
     if(txt)return txt;
   }
   const count=[...box.querySelectorAll('input[type="checkbox"]:checked,input[type="radio"]:checked')].filter(x=>!x.disabled).length;
   return count===1?'1 seleccionada':`${count} seleccionadas`;
 }
 function sync(box){
   if(!box)return;const original=findOriginalSave(box),bar=box.querySelector('.v490-attention-bar');if(!original||!bar)return;
   const clone=bar.querySelector('.v490-save-btn'),status=bar.querySelector('.v490-attention-status');
   if(status)status.textContent=selectionText(box);
   if(clone){clone.disabled=!!original.disabled;clone.textContent=norm(original.textContent||original.value).includes('guardando')?'Guardando…':'Guardar atención';}
 }
 function enhance(){
   const box=attentionBox();if(!box)return;
   box.classList.add('v490-attention-remaster');
   let bar=box.querySelector('.v490-attention-bar');
   if(!bar){
     bar=document.createElement('div');bar.className='v490-attention-bar';
     bar.innerHTML='<div class="v490-attention-bar-left"><span class="v490-attention-bar-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4 4L19 7"></path></svg></span><div class="v490-attention-copy"><b>ATENCIÓN</b><span class="v490-attention-status">0 seleccionadas</span></div></div><button class="v490-save-btn" type="button">Guardar atención</button>';
     const title=[...box.querySelectorAll('h1,h2,h3')].find(h=>norm(h.textContent)==='nueva atención');
     const heading=title?.closest('.modal-form-heading')||title?.parentElement;
     if(heading&&heading.parentElement===box)heading.insertAdjacentElement('afterend',bar);else box.insertBefore(bar,box.children[1]||box.firstChild);
   }
   if(!box.dataset.v490Bound){
     box.dataset.v490Bound='1';
     box.addEventListener('click',e=>{
       const save=e.target.closest?.('.v490-save-btn');
       if(save){e.preventDefault();const original=findOriginalSave(box);if(original&&!original.disabled)original.click();return;}
       setTimeout(()=>sync(box),0);setTimeout(()=>sync(box),80);
     });
     box.addEventListener('change',()=>{setTimeout(()=>sync(box),0);setTimeout(()=>sync(box),60)});
     box.addEventListener('input',()=>setTimeout(()=>sync(box),0));
   }
   sync(box);setTimeout(()=>sync(box),80);
 }
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,80);setTimeout(enhance,180)},true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,120),{once:true});else setTimeout(enhance,120);
})();'''


def patch_app(s):
    if s.count('APP_VERSION = "4.3.89"')!=1: raise SystemExit('version backend inesperada')
    s=s.replace('APP_VERSION = "4.3.89"','APP_VERSION = "4.3.90"',1)
    if s.count("const VERSION=\\'4.3.89\\';")!=1: raise SystemExit('version visual inesperada')
    s=s.replace("const VERSION=\\'4.3.89\\';","const VERSION=\\'4.3.90\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=(
      'V490_ATTENTION_CSS = r"""'+CSS+'"""\n'
      'V490_ATTENTION_JS = r"""'+JS+'"""\n'
      'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V490_ATTENTION_CSS\n'
      'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V490_ATTENTION_JS\n\n'+marker
    )
    return s.replace(marker,inject,1)


def main():
    app=patch_app(joined('app.part',7));launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app);js=css=None
    for node in tree.body:
        if isinstance(node,ast.Assign):
            names=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'V490_ATTENTION_JS' in names: js=ast.literal_eval(node.value)
            if 'V490_ATTENTION_CSS' in names: css=ast.literal_eval(node.value)
    if not js or not css: raise SystemExit('overlay v490 ausente')
    for token in ['v490-attention-bar','v490-save-btn','Guardar atención','selectionText','findOriginalSave']:
        if token not in js and token not in css: raise SystemExit('falta '+token)
    if 'MutationObserver' in js: raise SystemExit('v490 no debe usar MutationObserver')
    for token in ['historical_matches=_historical_review_matches(current,per_patient=24)','V488_HOME_CSS','v488-home-action-svg','V487_ICON_JS','Revisando AZUR','V486_FIX_JS','v486OpenAzur','V485_FIX_JS','Emitir por lotes']:
        if token not in app: raise SystemExit('regresion '+token)
    if 'APP_VERSION = "4.3.90"' not in app or "const VERSION=\\'4.3.90\\';" not in app: raise SystemExit('version incorrecta')
    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode();lb=launcher.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v490/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.90: remasteriza Nueva atención con Guardar atención siempre visible y resumen fijo de selección.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()
