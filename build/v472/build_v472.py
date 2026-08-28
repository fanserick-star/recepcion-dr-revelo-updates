from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.72'
BASE_VERSION='4.3.71'
BASE_SHA='18bdb05cff6b03c7c06da98f29888f5880af34df23578ddbe5fe3f1ee26a56c6'
oldroot=ROOT/'updates'/'v471'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.71 no coincide con la publicada')
s=raw.decode('utf-8')

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f'{label}: se esperaba 1 coincidencia y hubo {n}')
    s=s.replace(old,new,1)

def rewrite_js_assignment(name, transform):
    global s
    tree=ast.parse(s);node=None
    for n in tree.body:
        if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id==name:
            node=n;break
    if node is None: raise SystemExit(f'No se encontró {name}')
    value=ast.literal_eval(node.value);new_value=transform(value)
    old_expr=ast.get_source_segment(s,node.value)
    if old_expr is None: raise SystemExit(f'No se pudo extraer {name}')
    old_assign=f'{name} = {old_expr}';new_assign=f'{name} = {new_value!r}'
    if s.count(old_assign)!=1: raise SystemExit(f'Asignación {name} inválida')
    s=s.replace(old_assign,new_assign,1)

one('APP_VERSION = "4.3.71"','APP_VERSION = "4.3.72"','APP_VERSION')
one('/v460/overlay.css?v=4.3.71','/v460/overlay.css?v=4.3.72','overlay css cache')
one('/v460/overlay.js?v=4.3.71','/v460/overlay.js?v=4.3.72','overlay js cache')

# v4.3.72: limpieza de trabajo repetitivo exclusivamente en el frontend.
# No se modifican Neon, Cloudflare, WhatsApp, AZUR, Agenda web ni persistencia.
def patch_overlay(js):
    old="const VERSION='4.3.71';"
    if js.count(old)!=1: raise SystemExit('Versión overlay base no encontrada')
    js=js.replace(old,"const VERSION='4.3.72';",1)

    # 1) window.alert ya se enlaza al cargar el overlay. El setInterval de 5 s
    # mantenía un wake-up permanente aunque el programa estuviera quieto.
    old_alert="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setInterval(v464BindAlert,5000);"
    new_alert="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setTimeout(v464BindAlert,1500);"
    if js.count(old_alert)!=1: raise SystemExit(f'Alert timer: hubo {js.count(old_alert)} coincidencias')
    js=js.replace(old_alert,new_alert,1)

    # 2) El observador heredado de facturación recorría botones por cada mutación.
    # Se conserva el mismo resultado, pero como máximo se ejecuta una pasada por ráfaga.
    old_watch="function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch='1';new MutationObserver(()=>{paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()}).observe(root,{childList:true,subtree:true})}}"
    new_watch="let v472UiTimer=0;function scheduleV472UiRefresh(){if(v472UiTimer)return;v472UiTimer=setTimeout(()=>{v472UiTimer=0;paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()},140)}function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch='1';new MutationObserver(scheduleV472UiRefresh).observe(root,{childList:true,subtree:true})}}"
    if js.count(old_watch)!=1: raise SystemExit(f'Watcher legado UI: hubo {js.count(old_watch)} coincidencias')
    js=js.replace(old_watch,new_watch,1)

    # 3) El selector de plantillas WhatsApp también reaccionaba inmediatamente a
    # cualquier cambio del DOM completo. Se amortigua sin cambiar la funcionalidad.
    old_picker="new MutationObserver(()=>installV464TemplatePicker()).observe(document.documentElement,{childList:true,subtree:true});"
    new_picker="let v472PickerTimer=0;new MutationObserver(()=>{if(v472PickerTimer)return;v472PickerTimer=setTimeout(()=>{v472PickerTimer=0;installV464TemplatePicker()},160)}).observe(document.documentElement,{childList:true,subtree:true});"
    if js.count(old_picker)!=1: raise SystemExit(f'Watcher picker WhatsApp: hubo {js.count(old_picker)} coincidencias')
    js=js.replace(old_picker,new_picker,1)

    return js
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v472';out.mkdir(parents=True,exist_ok=True)
raw=s.encode('utf-8');PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={'product':'recepcion-pacientes','version':VERSION,'base_version':BASE_VERSION,'base_sha256':BASE_SHA,'app_sha256':hashlib.sha256(raw).hexdigest(),'app_size':len(raw),'parts_count':len(chunks),'part_max_bytes':PART,'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V472_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
