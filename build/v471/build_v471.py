from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.71'
BASE_VERSION='4.3.70'
BASE_SHA='5ff5107cc4776fa616b4b1e49a9f4d6e08ce0035daed26f9c2cdde17693364ad'
oldroot=ROOT/'updates'/'v470'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.70 no coincide con la publicada')
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

one('APP_VERSION = "4.3.70"','APP_VERSION = "4.3.71"','APP_VERSION')
one('/v460/overlay.css?v=4.3.70','/v460/overlay.css?v=4.3.71','overlay css cache')
one('/v460/overlay.js?v=4.3.70','/v460/overlay.js?v=4.3.71','overlay js cache')

# Marcar también el contenedor exterior real de la ficha de Agenda.
def patch_agenda(js):
    old="requestAnimationFrame(()=>{const x=q('.native-appointment-detail');x?.parentElement?.classList.add('v467-agenda-modal-shell')});"
    new="requestAnimationFrame(()=>{const x=q('.native-appointment-detail'),body=x?.parentElement,outer=x?.closest('.modal-content,.modal-card,[role=\"dialog\"]')||body?.parentElement;body?.classList.add('v467-agenda-modal-shell');outer?.classList.add('v471-agenda-outer')});"
    n=js.count(old)
    if n!=2: raise SystemExit(f'Marcado ficha Agenda: se esperaban 2 coincidencias y hubo {n}')
    return js.replace(old,new)
rewrite_js_assignment('V459_SETTINGS_JS',patch_agenda)

# Mantener el contenido como está y recortar únicamente el marco exterior visible.
def patch_overlay(js):
    old="const VERSION='4.3.70';"
    if js.count(old)!=1: raise SystemExit('Versión overlay base no encontrada')
    js=js.replace(old,"const VERSION='4.3.71';",1)
    oldguard="document.querySelectorAll('.v467-agenda-modal-shell').forEach(el=>el.classList.remove('v467-agenda-modal-shell'));"
    newguard="document.querySelectorAll('.v467-agenda-modal-shell,.v471-agenda-outer').forEach(el=>el.classList.remove('v467-agenda-modal-shell','v471-agenda-outer'));"
    if js.count(oldguard)!=1: raise SystemExit(f'Guard modal: hubo {js.count(oldguard)} coincidencias')
    js=js.replace(oldguard,newguard,1)
    extra=r'''
;(()=>{
  function installV471AgendaOuterStyle(){
    if(document.getElementById('v471AgendaOuterStyle'))return;
    const st=document.createElement('style');st.id='v471AgendaOuterStyle';st.textContent=`
      .v471-agenda-outer{width:min(590px,calc(100vw - 40px))!important;max-width:590px!important;min-width:0!important;height:auto!important;min-height:0!important;max-height:calc(100vh - 24px)!important}
      @media(max-width:680px){.v471-agenda-outer{width:calc(100vw - 24px)!important;max-width:none!important}}
    `;document.head.appendChild(st)
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installV471AgendaOuterStyle,{once:true});else installV471AgendaOuterStyle();
})();
'''
    if 'v471AgendaOuterStyle' in js: raise SystemExit('Estilo v4.3.71 ya existe')
    return js+extra
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v471';out.mkdir(parents=True,exist_ok=True)
raw=s.encode('utf-8');PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={'product':'recepcion-pacientes','version':VERSION,'base_version':BASE_VERSION,'base_sha256':BASE_SHA,'app_sha256':hashlib.sha256(raw).hexdigest(),'app_size':len(raw),'parts_count':len(chunks),'part_max_bytes':PART,'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V471_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
