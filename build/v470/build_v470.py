from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.70'
BASE_VERSION='4.3.69'
BASE_SHA='0de0f09b7af4a8176fcde0f344e5628bd966db68bf21deaebc1068c32e7edf3a'
oldroot=ROOT/'updates'/'v469'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.69 no coincide con la publicada')
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

one('APP_VERSION = "4.3.69"','APP_VERSION = "4.3.70"','APP_VERSION')
one('/v460/overlay.css?v=4.3.69','/v460/overlay.css?v=4.3.70','overlay css cache')
one('/v460/overlay.js?v=4.3.69','/v460/overlay.js?v=4.3.70','overlay js cache')

def patch_overlay(js):
    old="const VERSION='4.3.69';"
    if js.count(old)!=1: raise SystemExit('Versión overlay base no encontrada')
    js=js.replace(old,"const VERSION='4.3.70';",1)
    oldcss='.v467-agenda-modal-shell{width:min(600px,calc(100vw - 56px))!important;max-width:600px!important;height:auto!important;min-height:0!important;max-height:calc(100vh - 44px)!important;padding:16px 18px!important;border-radius:17px!important;overflow:auto!important}'
    newcss='.v467-agenda-modal-shell{width:min(520px,calc(100vw - 56px))!important;max-width:520px!important;height:auto!important;min-height:0!important;max-height:calc(100vh - 44px)!important;padding:16px 18px!important;border-radius:17px!important;overflow:auto!important}'
    if js.count(oldcss)!=1: raise SystemExit(f'CSS agenda shell: hubo {js.count(oldcss)} coincidencias')
    return js.replace(oldcss,newcss,1)
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v470';out.mkdir(parents=True,exist_ok=True)
raw=s.encode('utf-8');PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={'product':'recepcion-pacientes','version':VERSION,'base_version':BASE_VERSION,'base_sha256':BASE_SHA,'app_sha256':hashlib.sha256(raw).hexdigest(),'app_size':len(raw),'parts_count':len(chunks),'part_max_bytes':PART,'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V470_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
