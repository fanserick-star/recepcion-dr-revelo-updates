from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.68'
BASE_VERSION='4.3.67'
BASE_SHA='35560b2bb6542f8a453d4d195576c2de914aa34b8f977f86d0720ae4944c348a'
oldroot=ROOT/'updates'/'v467'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.67 no coincide con la publicada')
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

one('APP_VERSION = "4.3.67"','APP_VERSION = "4.3.68"','APP_VERSION')
one('/v460/overlay.css?v=4.3.67','/v460/overlay.css?v=4.3.68','overlay css cache')
one('/v460/overlay.js?v=4.3.67','/v460/overlay.js?v=4.3.68','overlay js cache')

def patch_overlay(js):
    if "const VERSION='4.3.67';" not in js: raise SystemExit('Versión overlay base no encontrada')
    js=js.replace("const VERSION='4.3.67';","const VERSION='4.3.68';",1)
    old='.v467-agenda-modal-shell{width:min(720px,calc(100vw - 72px))!important;max-width:720px!important;padding:18px 20px!important;border-radius:18px!important}'
    new='.v467-agenda-modal-shell{width:min(600px,calc(100vw - 56px))!important;max-width:600px!important;padding:16px 18px!important;border-radius:17px!important}'
    if js.count(old)!=1: raise SystemExit(f'CSS shell Agenda: hubo {js.count(old)} coincidencias')
    js=js.replace(old,new,1)
    old2='.native-appointment-detail .v459-whatsapp-timeline{margin-top:9px!important;padding:11px 13px!important;border-radius:13px!important}'
    new2='.native-appointment-detail .v459-whatsapp-timeline{margin-top:8px!important;padding:10px 11px!important;border-radius:12px!important}'
    if js.count(old2)!=1: raise SystemExit('CSS timeline Agenda no encontrado')
    js=js.replace(old2,new2,1)
    old3='.native-appointment-detail .actions{margin-top:11px!important;gap:7px!important}'
    new3='.native-appointment-detail .actions{margin-top:9px!important;gap:6px!important;justify-content:flex-end!important}'
    if js.count(old3)!=1: raise SystemExit('CSS acciones Agenda no encontrado')
    js=js.replace(old3,new3,1)
    return js
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v468';out.mkdir(parents=True,exist_ok=True)
raw=s.encode('utf-8');PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={'product':'recepcion-pacientes','version':VERSION,'base_version':BASE_VERSION,'base_sha256':BASE_SHA,'app_sha256':hashlib.sha256(raw).hexdigest(),'app_size':len(raw),'parts_count':len(chunks),'part_max_bytes':PART,'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V468_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
