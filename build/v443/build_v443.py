from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v442'
OUT = ROOT / 'updates' / 'v443'
VERSION = '4.4.3'
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
    c=text.count(old)
    if c != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontró {c}')
    return text.replace(old,new,1)


V443_CSS = r'''/* v4.4.3 — limpia restos visuales de Nueva atención */
.v443-attention-empty-hidden{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
.v492-attention .attention-form-modal>.v492-selection-head,
.v492-attention .attention-form-modal>.v491-attention-title,
.v492-attention .attention-form-modal>.v491-selection-help{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
'''

V443_JS = r''';(()=>{
 if(window.__v443Cleanup)return;window.__v443Cleanup=true;
 function deadHash(a){
   if(!a||a.tagName!=='A'||!a.hasAttribute('href'))return false;
   const raw=String(a.getAttribute('href')||'').trim();
   return raw==='#'||raw==='./#'||raw==='/#';
 }
 function sanitizeHashLinks(root=document){
   root.querySelectorAll?.('a[href]').forEach(a=>{
     if(!deadHash(a))return;
     a.removeAttribute('href');
     if(!a.hasAttribute('role'))a.setAttribute('role','button');
     if(!a.hasAttribute('tabindex'))a.tabIndex=0;
   });
 }
 function cleanAttentionGhostRows(){
   const box=document.querySelector('#modal .modalbox');
   const form=box?.querySelector('.attention-form-modal');
   if(!form||!box.classList.contains('v492-attention'))return;
   if(!box.querySelector('.v492-clinical-head')||!form.querySelector('.service-groups.v43103-native-services,.service-groups'))return;
   const candidates=[
     form.querySelector('#attentionStatus'),
     form.querySelector('.attention-date-card'),
     form.querySelector('.service-title.enhanced'),
     ...form.querySelectorAll('.v492-selection-head,.v491-attention-title,.v491-selection-help,.v492-empty-source,.v493-old-alert,.v494-ghost-hidden')
   ];
   candidates.forEach(el=>{
     if(!el||el.closest('.v492-clinical-head')||el.closest('.service-groups'))return;
     const text=String(el.innerText||'').replace(/\s+/g,' ').trim();
     const live=el.querySelector('input:not([type="hidden"]),select,textarea,button:not([style*="display: none"])');
     if(!text&&!live)el.classList.add('v443-attention-empty-hidden');
     else if(el.matches('.service-title.enhanced,.v492-selection-head,.v491-attention-title,.v491-selection-help'))el.classList.add('v443-attention-empty-hidden');
   });
 }
 function run(){sanitizeHashLinks();cleanAttentionGhostRows()}
 document.addEventListener('pointerover',e=>{const a=e.target?.closest?.('a');if(deadHash(a))sanitizeHashLinks(a.parentElement||document)},true);
 document.addEventListener('focusin',e=>{const a=e.target?.closest?.('a');if(deadHash(a))sanitizeHashLinks(a.parentElement||document)},true);
 document.addEventListener('click',()=>{setTimeout(run,0);setTimeout(run,80);setTimeout(run,220)},true);
 document.addEventListener('change',()=>setTimeout(cleanAttentionGhostRows,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(run,120),{once:true});else setTimeout(run,120);
})();'''


def patch_app(s: str) -> str:
    s=replace_once(s,'APP_VERSION = "4.4.2"','APP_VERSION = "4.4.3"','versión backend')
    s=replace_once(s,"const VERSION=\\'4.4.2\\';","const VERSION=\\'4.4.3\\';",'versión visual')
    marker='@app.get("/v460/overlay.css")'
    inject=(
        'V443_CLEANUP_CSS = r"""'+V443_CSS+'"""\n'
        'V443_CLEANUP_JS = r"""'+V443_JS+'"""\n'
        'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V443_CLEANUP_CSS\n'
        'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V443_CLEANUP_JS\n\n'
    )
    s=replace_once(s,marker,inject+marker,'overlay v443')
    compile(s,'app.py','exec')
    required=['APP_VERSION = "4.4.3"','V443_CLEANUP_CSS','V443_CLEANUP_JS','v443-attention-empty-hidden','sanitizeHashLinks','cleanAttentionGhostRows','TRASH_RETENTION_DAYS = 7','Actividad local-first estricta','Resumen de datos y servicios','V43104_ALERT_JS','Procedimientos y servicios',"price.textContent='$40.00'",'Emitir por lotes']
    for token in required:
        if token not in s: raise SystemExit('app falta '+token)
    forbidden=['MutationObserver','/api/patients/{pid}/quick','/api/ops/agenda-smart']
    for token in forbidden:
        if token in V443_JS: raise SystemExit('v443 js conserva '+token)
    return s


def main() -> None:
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    (OUT/'static').mkdir(parents=True,exist_ok=True)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8')
    static_app=(SRC/'static'/'app.js').read_text(encoding='utf-8')
    (OUT/'static'/'index.html').write_text(index,encoding='utf-8',newline='')
    (OUT/'static'/'app.js').write_text(static_app,encoding='utf-8',newline='')
    ab,lb,ib,jb=app.encode(),launcher.encode(),index.encode(),static_app.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','static/app.js','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v443/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.4.3: elimina las dos filas vacías de Nueva atención y neutraliza enlaces internos # residuales que mostraban 127.0.0.1/# al pasar el mouse, sin añadir consultas a Neon.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'static/app.js','url':base+'static/app.js','sha256':sha(jb),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb),sha(jb))

if __name__=='__main__': main()
