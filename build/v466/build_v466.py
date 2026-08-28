from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.66'
BASE_VERSION='4.3.65'
BASE_SHA='e9763acd0bbf7792a8b90a88093a5ce0749bcc9fddce2dd75e9495cf89d81958'
oldroot=ROOT/'updates'/'v465'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.65 no coincide con la publicada')
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

# Versión y cache de recursos del escritorio.
one('APP_VERSION = "4.3.65"','APP_VERSION = "4.3.66"','APP_VERSION')
one('/v460/overlay.css?v=4.3.65','/v460/overlay.css?v=4.3.66','overlay css cache')
one('/v460/overlay.js?v=4.3.65','/v460/overlay.js?v=4.3.66','overlay js cache')

# Configuración: la renovación del acceso web usa el modal interno, no confirm() del navegador.
def patch_settings(js):
    old="if(!confirm('¿Renovar el enlace editable de Recepción / Ayudante?\\n\\nEl enlace del Doctor permanecerá exactamente igual. El enlace editable anterior dejará de funcionar.'))return;"
    new="if(!(await window.rpConfirm('¿Renovar el enlace editable de Recepción / Ayudante?\\n\\nEl enlace del Doctor permanecerá exactamente igual. El enlace editable anterior dejará de funcionar.','Renovar acceso web')))return;"
    if js.count(old)!=1:
        raise SystemExit(f'confirm renovación: se esperaba 1 coincidencia y hubo {js.count(old)}')
    return js.replace(old,new,1)
rewrite_js_assignment('V458_SETTINGS_JS',patch_settings)

# WhatsApp: rpConfirm ya forma parte estable del overlay; quitamos el último fallback nativo.
def patch_whatsapp(js):
    old="if(!(await (window.rpConfirm?window.rpConfirm(`¿Enviar UNA prueba Cloud a ${phone}?\\n\\nNo se usará ningún token de Meta de esta PC y no se tocará ningún paciente real.`):Promise.resolve(confirm(`¿Enviar UNA prueba Cloud a ${phone}?\\n\\nNo se usará ningún token de Meta de esta PC y no se tocará ningún paciente real.`)))))return;"
    new="if(!(await window.rpConfirm(`¿Enviar UNA prueba Cloud a ${phone}?\\n\\nNo se usará ningún token de Meta de esta PC y no se tocará ningún paciente real.`,'Confirmar prueba WhatsApp')))return;"
    if js.count(old)!=1:
        raise SystemExit(f'fallback confirm WhatsApp: se esperaba 1 coincidencia y hubo {js.count(old)}')
    return js.replace(old,new,1)
rewrite_js_assignment('V459_SETTINGS_JS',patch_whatsapp)

# Facturación instalada: el frontend histórico todavía usa confirm() síncrono.
# El bridge deja la lógica original intacta: en el primer clic devuelve false y muestra
# rpConfirm; si el usuario acepta, repite ese mismo clic una sola vez y confirm() devuelve
# true solo para esa repetición. No se modifica ningún endpoint de facturación/AZUR.
CONFIRM_BRIDGE=r'''
;(()=>{
  const v466BillingPrompt=/factur|azur|sri|comprobante/i;
  const v466NativeConfirm=window.confirm.bind(window);
  let v466ClickTarget=null;
  let v466AllowTarget=null;
  let v466Pending=false;

  function v466ActionTarget(e){
    const path=typeof e.composedPath==='function'?e.composedPath():[];
    for(const el of path){
      if(!el||el===document||el===window||typeof el.matches!=='function')continue;
      if(el.matches('button,input[type="button"],input[type="submit"],a,[role="button"]'))return el;
    }
    const t=e.target;
    return t&&typeof t.closest==='function'?(t.closest('button,input[type="button"],input[type="submit"],a,[role="button"]')||t):t;
  }

  document.addEventListener('click',e=>{
    const target=v466ActionTarget(e);
    v466ClickTarget=target;
    queueMicrotask(()=>{if(v466ClickTarget===target)v466ClickTarget=null});
  },true);

  function v466InstallConfirmBridge(){
    if(window.confirm&&window.confirm.__v466BillingBridge)return;
    const bridge=function(message){
      const text=String(message??'');
      if(!v466BillingPrompt.test(text))return v466NativeConfirm(text);
      const target=v466ClickTarget;
      if(v466AllowTarget&&target===v466AllowTarget){v466AllowTarget=null;return true;}
      if(v466Pending)return false;
      if(!target||typeof window.rpConfirm!=='function')return v466NativeConfirm(text);
      v466Pending=true;
      const title=/azur|sri/i.test(text)?'Confirmar emisión en AZUR':'Confirmar facturación';
      Promise.resolve(window.rpConfirm(text,title)).then(ok=>{
        v466Pending=false;
        if(!ok)return;
        v466AllowTarget=target;
        try{target.click()}finally{setTimeout(()=>{if(v466AllowTarget===target)v466AllowTarget=null},0)}
      }).catch(()=>{v466Pending=false});
      return false;
    };
    bridge.__v466BillingBridge=true;
    window.confirm=bridge;
  }

  v466InstallConfirmBridge();
  setTimeout(v466InstallConfirmBridge,0);
  setTimeout(v466InstallConfirmBridge,500);
})();
'''

def patch_overlay(js):
    if '__v466BillingBridge' in js:
        raise SystemExit('El overlay ya contiene el bridge v4.3.66')
    old="const VERSION='4.3.65';"
    if js.count(old)!=1:
        raise SystemExit(f'badge version overlay: se esperaba 1 coincidencia y hubo {js.count(old)}')
    js=js.replace(old,"const VERSION='4.3.66';",1)
    return js+CONFIRM_BRIDGE
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v466';out.mkdir(parents=True,exist_ok=True)
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
print('V466_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
