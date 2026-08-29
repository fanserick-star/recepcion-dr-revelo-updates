from __future__ import annotations
import ast, hashlib, json, math, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v496'
OUT=ROOT/'updates'/'v497'
VERSION='4.3.97'
LAUNCHER_VERSION='4.3.96-standalone-4'

CSS=r'''/* v4.3.97 — CONSULTA nativa visible dentro del remaster */
.v497-native-consult{order:-3000!important;display:grid!important;visibility:visible!important;opacity:1!important;height:auto!important;min-height:62px!important;background:#f2fbf6!important;border-color:#79bd96!important}
.v497-native-consult .service-icon{background:#dcf4e5!important;color:#257249!important}
.v497-native-consult:hover{border-color:#55a978!important;background:#ebf9f0!important}
.v497-native-consult.selected{background:#e3f7eb!important;border-color:#43a66e!important;box-shadow:0 0 0 2px #43a66e22!important}
.v497-native-consult.selected .service-icon{background:#2f925a!important;color:#fff!important}
.v497-native-section-empty{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
'''

JS=r''';(()=>{
 if(window.__v497NativeConsult)return;window.__v497NativeConsult=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function nativeConsult(box){return [...box.querySelectorAll('button.service-card[data-service]')].find(b=>norm(b.dataset.service)==='consulta')||null}
 function hideEmptyNativeSections(box){
   for(const sec of box.querySelectorAll('.consultation-service-section,.procedures-service-section')){
     if(!sec.querySelector('.service-card'))sec.classList.add('v497-native-section-empty');
   }
   for(const groups of box.querySelectorAll('.service-groups')){
     if(!groups.querySelector('.service-card'))groups.classList.add('v497-native-section-empty');
   }
 }
 function repairConsult(){
   const box=boxNow();if(!box)return false;
   const grid=box.querySelector('.v492-services-grid');if(!grid)return false;
   const card=nativeConsult(box);if(!card)return false;
   const oldSection=card.closest('.consultation-service-section');
   card.classList.remove('v492-empty-source','v493-old-alert','v495-hidden-source','hidden');
   card.style.removeProperty('display');card.style.removeProperty('height');card.style.removeProperty('visibility');
   card.classList.add('v492-service-card','v492-consult','v497-native-consult');
   grid.querySelectorAll('.v494-consult-proxy,.v495-consult-card').forEach(el=>{if(el!==card)el.remove()});
   if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   if(oldSection&&!oldSection.querySelector('.service-card'))oldSection.classList.add('v497-native-section-empty');
   hideEmptyNativeSections(box);
   return true;
 }
 function installFavicon(){
   let link=document.querySelector('link[data-rp-favicon="497"]');
   if(!link){link=document.createElement('link');link.rel='icon';link.type='image/x-icon';link.dataset.rpFavicon='497';document.head.appendChild(link)}
   link.href='/static/doctor_icon.ico?v=4.3.97';
 }
 function enhance(){installFavicon();repairConsult()}
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,50);setTimeout(enhance,140);setTimeout(enhance,300)},true);
 document.addEventListener('change',()=>setTimeout(enhance,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{installFavicon();setTimeout(enhance,120)},{once:true});else{installFavicon();setTimeout(enhance,120)}
})();'''

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

def replace_once(text,old,new,label):
    c=text.count(old)
    if c!=1: raise SystemExit(f'{label}: esperaba 1 coincidencia y encontro {c}')
    return text.replace(old,new,1)

def patch_app(s):
    s=replace_once(s,'APP_VERSION = "4.3.96"','APP_VERSION = "4.3.97"','version backend')
    s=replace_once(s,"const VERSION=\\'4.3.96\\';","const VERSION=\\'4.3.97\\';",'version visual')
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker inesperado')
    inject=(
        'V497_ATTENTION_CSS = r"""'+CSS+'"""\n'
        'V497_ATTENTION_JS = r"""'+JS+'"""\n'
        'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V497_ATTENTION_CSS\n'
        'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V497_ATTENTION_JS\n\n'+marker
    )
    s=s.replace(marker,inject,1)
    compile(s,'app.py','exec')
    for token in ['APP_VERSION = "4.3.97"','V497_ATTENTION_JS','button.service-card[data-service]','v497-native-consult','/static/doctor_icon.ico?v=4.3.97','_POSTGRES_DRIVER = "pg8000"','V495_ATTENTION_JS','Revisando AZUR','Emitir por lotes']:
        if token not in s: raise SystemExit('falta '+token)
    return s

def build_index():
    base=ROOT/'installer_clean'/'base'/'clean_base_resources.zip'
    with zipfile.ZipFile(base) as z:
        html=z.read('static/index.html').decode('utf-8-sig')
        appjs=z.read('static/app.js').decode('utf-8-sig')
    for token in ['data-service="CONSULTA"',"toggleService('CONSULTA')","if(name==='CONSULTA')return {procedimiento:null,valor:40}"]:
        if token not in appjs: raise SystemExit('frontend base no contiene '+token)
    favicon='  <link rel="icon" type="image/x-icon" href="/static/doctor_icon.ico?v=4.3.97">\n  <link rel="shortcut icon" type="image/x-icon" href="/static/doctor_icon.ico?v=4.3.97">\n'
    if '/static/doctor_icon.ico?v=4.3.97' not in html:
        html=replace_once(html,'  <title>Recepción de Pacientes</title>\n','  <title>Recepción de Pacientes</title>\n'+favicon,'favicon html')
    target=OUT/'static'/'index.html';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(html,encoding='utf-8',newline='')
    return target,html

def main():
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    compile(launcher,'ABRIR_RECEPCION.py','exec')
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    index_path,index=build_index()
    ab=app.encode();lb=launcher.encode();ib=index.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v497/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.97: restaura CONSULTA desde su boton nativo y aplica el icono del consultorio a la ventana Edge.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    tree=ast.parse(app);js=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='V497_ATTENTION_JS' for t in node.targets): js=ast.literal_eval(node.value)
    if not js or 'MutationObserver' in js: raise SystemExit('overlay v497 invalido')
    print('OK',VERSION,sha(ab),sha(lb),sha(ib))

if __name__=='__main__': main()
