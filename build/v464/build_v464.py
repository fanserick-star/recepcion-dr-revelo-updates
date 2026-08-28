from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.64'
BASE_VERSION='4.3.63'
BASE_SHA='4a5802fcb04c402dcac40d6738b0bd7cb675d8daf4fb49023af5c900c230eab2'
oldroot=ROOT/'updates'/'v463'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.63 no coincide con la publicada')
s=raw.decode('utf-8')

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: se esperaba 1 coincidencia y hubo {n}')
    s=s.replace(old,new,1)

def rewrite_js_assignment(name, transform):
    global s
    tree=ast.parse(s)
    node=None
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name:
            node=n;break
    if node is None:
        raise SystemExit(f'No se encontró {name}')
    value=ast.literal_eval(node.value)
    new_value=transform(value)
    old_expr=ast.get_source_segment(s,node.value)
    if old_expr is None:
        raise SystemExit(f'No se pudo extraer {name}')
    old_assign=f'{name} = {old_expr}'
    new_assign=f'{name} = {new_value!r}'
    if s.count(old_assign)!=1:
        raise SystemExit(f'Asignación {name}: se esperaba 1 coincidencia y hubo {s.count(old_assign)}')
    s=s.replace(old_assign,new_assign,1)

one('APP_VERSION = "4.3.63"','APP_VERSION = "4.3.64"','APP_VERSION')
one("const VERSION='4.3.63';","const VERSION='4.3.64';",'badge version')
one('/v460/overlay.css?v=4.3.63','/v460/overlay.css?v=4.3.64','overlay css cache')
one('/v460/overlay.js?v=4.3.63','/v460/overlay.js?v=4.3.64','overlay js cache')

PICKER_PATCH=r'''
;(()=>{
  function installV464TemplatePicker(){
    const sel=document.querySelector('#waTestTemplate');
    if(!sel||sel.dataset.v464Picker==='1')return;
    sel.dataset.v464Picker='1';
    sel.style.display='none';
    const current=window.__v464WaTemplateValue||sel.value||'recordatorio_cita';
    window.__v464WaTemplateValue=current;
    const wrap=document.createElement('div');wrap.className='v464-template-picker';wrap.setAttribute('role','group');wrap.setAttribute('aria-label','Mensaje a probar');
    const defs=[['recordatorio_cita','Confirmación'],['cita_agendada','Cita agendada'],['recordatorio_hoy','Recordatorio de hoy']];
    const paint=()=>wrap.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.template===window.__v464WaTemplateValue));
    defs.forEach(([value,label])=>{const b=document.createElement('button');b.type='button';b.dataset.template=value;b.textContent=label;b.addEventListener('click',()=>{window.__v464WaTemplateValue=value;sel.value=value;paint();});wrap.appendChild(b)});
    sel.insertAdjacentElement('afterend',wrap);paint();
  }
  function installV464PickerStyle(){if(document.getElementById('v464PickerStyle'))return;const st=document.createElement('style');st.id='v464PickerStyle';st.textContent=`.v464-template-picker{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:4px}.v464-template-picker button{border:1px solid #cfd9e6;background:#fff;color:#38516f;border-radius:11px;padding:10px 9px;font-weight:800;cursor:pointer}.v464-template-picker button.active{background:#2767ad;color:#fff;border-color:#2767ad;box-shadow:0 4px 14px rgba(39,103,173,.18)}@media(max-width:850px){.v464-template-picker{grid-template-columns:1fr}}`;document.head.appendChild(st)}
  function boot(){installV464PickerStyle();installV464TemplatePicker()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(boot,250);setTimeout(boot,900);
  new MutationObserver(()=>installV464TemplatePicker()).observe(document.documentElement,{childList:true,subtree:true});
})();
'''

def patch_settings(js):
    old="function testTemplate(){return q('#waTestTemplate')?.value||'recordatorio_cita'}"
    new="function testTemplate(){return window.__v464WaTemplateValue||q('#waTestTemplate')?.value||'recordatorio_cita'}"
    if js.count(old)!=1:
        raise SystemExit(f'testTemplate: se esperaba 1 coincidencia y hubo {js.count(old)}')
    js=js.replace(old,new,1)
    # Los avisos de esta sección deben usar el modal interno, no alertas nativas.
    js=js.replace('alert(', 'window.rpNotice(')
    return js+PICKER_PATCH


def patch_overlay(js):
    marker='window.rpNotice=prettyAlert;window.alert=(message)=>prettyAlert(message);'
    repl="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setInterval(v464BindAlert,5000);"
    if js.count(marker)!=1:
        raise SystemExit(f'alert bridge: se esperaba 1 coincidencia y hubo {js.count(marker)}')
    js=js.replace(marker,repl,1)
    # También sustituimos llamadas directas que quedaban en el overlay (p. ej. lote AZUR).
    js=js.replace('alert(', 'window.rpNotice(')
    return js

rewrite_js_assignment('V459_SETTINGS_JS',patch_settings)
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v464';out.mkdir(parents=True,exist_ok=True)
raw=s.encode('utf-8')
PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
manifest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher',
  'copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']
}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={
  'product':'recepcion-pacientes','version':VERSION,'base_version':BASE_VERSION,'base_sha256':BASE_SHA,
  'app_sha256':hashlib.sha256(raw).hexdigest(),'app_size':len(raw),'parts_count':len(chunks),'part_max_bytes':PART,
  'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V464_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
