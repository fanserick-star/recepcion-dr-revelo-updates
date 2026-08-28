from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.67'
BASE_VERSION='4.3.66'
BASE_SHA='70a97679078eb9dfd549a03f7a10f880f7f2a2fc307c3e4f4ce969bade31b7fd'
oldroot=ROOT/'updates'/'v466'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.66 no coincide con la publicada')
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

one('APP_VERSION = "4.3.66"','APP_VERSION = "4.3.67"','APP_VERSION')
one('/v460/overlay.css?v=4.3.66','/v460/overlay.css?v=4.3.67','overlay css cache')
one('/v460/overlay.js?v=4.3.66','/v460/overlay.js?v=4.3.67','overlay js cache')

# Agenda: teléfono únicamente dentro de la ficha al abrir una cita.
def patch_agenda_detail(js):
    linked_old='<div class="modal-form-heading"><h2>${eh(p.nombre||\'Paciente\')}</h2><p>${eh(date)} · ${eh(time)}</p></div>'
    linked_new='<div class="modal-form-heading v467-agenda-heading"><h2>${eh(p.nombre||\'Paciente\')}</h2><div class="v467-agenda-meta"><span>${eh(date)} · ${eh(time)}</span>${p.celular?`<span class="v467-agenda-phone">Tel. ${eh(p.celular)}</span>`:\'\'}</div></div>'
    staged_old='<div class="modal-form-heading"><h2>${eh(st.nombre||\'Paciente\')}</h2><p>${eh(date)} · ${eh(time)}</p></div>'
    staged_new='<div class="modal-form-heading v467-agenda-heading"><h2>${eh(st.nombre||\'Paciente\')}</h2><div class="v467-agenda-meta"><span>${eh(date)} · ${eh(time)}</span>${st.celular?`<span class="v467-agenda-phone">Tel. ${eh(st.celular)}</span>`:\'\'}</div></div>'
    if js.count(linked_old)!=1: raise SystemExit(f'ficha agenda vinculada: hubo {js.count(linked_old)} coincidencias')
    if js.count(staged_old)!=1: raise SystemExit(f'ficha agenda importada: hubo {js.count(staged_old)} coincidencias')
    js=js.replace(linked_old,linked_new,1).replace(staged_old,staged_new,1)
    linked_tail="const host=q('#v459TimelineHost');if(host)loadTimeline('appointment',Number(a.id),host)"
    staged_tail="const host=q('#v459TimelineHost');if(host)loadTimeline('staged',Number(itemId),host)"
    linked_mark="requestAnimationFrame(()=>{const x=q('.native-appointment-detail');x?.parentElement?.classList.add('v467-agenda-modal-shell')});\n   "+linked_tail
    staged_mark="requestAnimationFrame(()=>{const x=q('.native-appointment-detail');x?.parentElement?.classList.add('v467-agenda-modal-shell')});\n   "+staged_tail
    if js.count(linked_tail)!=1: raise SystemExit('No se encontró cierre de ficha vinculada')
    if js.count(staged_tail)!=1: raise SystemExit('No se encontró cierre de ficha importada')
    return js.replace(linked_tail,linked_mark,1).replace(staged_tail,staged_mark,1)
rewrite_js_assignment('V459_SETTINGS_JS',patch_agenda_detail)

COMPACT_UI=r'''
;(()=>{
  function installV467CompactStyle(){
    if(document.getElementById('v467CompactStyle'))return;
    const st=document.createElement('style');st.id='v467CompactStyle';st.textContent=`
      /* Ficha de Agenda: compacta, centrada y con teléfono solo al abrir la cita. */
      .v467-agenda-modal-shell{width:min(720px,calc(100vw - 72px))!important;max-width:720px!important;padding:18px 20px!important;border-radius:18px!important}
      .native-appointment-detail{width:100%!important;max-width:none!important}
      .native-appointment-detail .v467-agenda-heading{margin:0 0 9px!important}
      .native-appointment-detail .v467-agenda-heading h2{margin:0 0 5px!important;font-size:22px!important;line-height:1.16!important;letter-spacing:-.2px}
      .v467-agenda-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;color:#607087;font-size:13px;font-weight:650}
      .v467-agenda-phone{display:inline-flex;align-items:center;padding:3px 8px;border:1px solid #dbe5ef;border-radius:999px;background:#f6f9fc;color:#334e68;font-weight:750}
      .native-appointment-detail .native-detail-status{margin:5px 0 8px!important;padding:5px 9px!important;font-size:11px!important}
      .native-appointment-detail>.muted{margin:4px 0 9px!important;font-size:12px!important}
      .native-appointment-detail .native-detail-note{margin:7px 0!important;padding:8px 10px!important}
      .native-appointment-detail .v459-whatsapp-timeline{margin-top:9px!important;padding:11px 13px!important;border-radius:13px!important}
      .native-appointment-detail .v459-whatsapp-timeline h3{margin:0 0 7px!important;font-size:13px!important}
      .native-appointment-detail .v459-wa-flow{gap:2px!important}
      .native-appointment-detail .v459-wa-step{padding:6px 0!important;min-height:0!important}
      .native-appointment-detail .v459-wa-dot{width:22px!important;height:22px!important;min-width:22px!important;font-size:11px!important}
      .native-appointment-detail .v459-wa-title{min-height:22px!important;gap:8px!important}
      .native-appointment-detail .v459-wa-title b{font-size:13px!important}
      .native-appointment-detail .v459-wa-copy small{font-size:11px!important;line-height:1.35!important}
      .native-appointment-detail .v459-wa-badge{font-size:10px!important;padding:3px 6px!important}
      .native-appointment-detail .actions{margin-top:11px!important;gap:7px!important}
      .native-appointment-detail .actions button{padding:8px 12px!important;font-size:12px!important;border-radius:9px!important}

      /* Configuración: ancho de lectura cómodo en monitor ancho. */
      #config.v458-settings{width:min(1120px,calc(100% - 32px))!important;max-width:1120px!important;margin-left:auto!important;margin-right:auto!important}
      #config.v458-settings .config-title-row{margin-bottom:12px!important}
      #config.v458-settings .config-title-row h2{margin-bottom:4px!important}
      #config.v458-settings .config-tabs{gap:3px!important;padding:4px 5px!important;margin-bottom:12px!important;overflow-x:auto!important}
      #config.v458-settings .config-tabs button{padding:8px 11px!important;font-size:12px!important;white-space:nowrap!important}
      #config.v458-settings [data-config-section]{width:100%!important;max-width:980px!important;margin-left:auto!important;margin-right:auto!important}
      #config.v458-settings [data-config-section]>.panel,
      #config.v458-settings [data-config-section] details>.panel{padding:15px 17px!important;border-radius:14px!important}
      #config.v458-settings .config-panel-head{margin-bottom:10px!important}
      #config.v458-settings .config-panel-head h3{margin-bottom:3px!important}
      #config.v458-settings .v458-template-grid{gap:9px!important}
      #config.v458-settings .v458-template-card{padding:11px 12px!important;border-radius:12px!important}
      #config.v458-settings .v458-service-grid{gap:9px!important}
      #config.v458-settings .v458-service-card{padding:11px 12px!important;border-radius:12px!important}
      #config.v458-settings .v458-link-grid{gap:10px!important}
      #config.v458-settings .v458-link-card{padding:12px!important}
      @media(max-width:900px){
        .v467-agenda-modal-shell{width:calc(100vw - 28px)!important;padding:15px!important}
        #config.v458-settings{width:calc(100% - 18px)!important}
        #config.v458-settings [data-config-section]{max-width:none!important}
      }
    `;document.head.appendChild(st)
  }
  function bootV467Compact(){installV467CompactStyle()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bootV467Compact,{once:true});else bootV467Compact();
})();
'''

def patch_overlay(js):
    if 'v467CompactStyle' in js: raise SystemExit('El overlay ya contiene v4.3.67')
    old="const VERSION='4.3.66';"
    if js.count(old)!=1: raise SystemExit(f'versión overlay: hubo {js.count(old)} coincidencias')
    return js.replace(old,"const VERSION='4.3.67';",1)+COMPACT_UI
rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v467';out.mkdir(parents=True,exist_ok=True)
raw=s.encode('utf-8');PART=70000
for p in out.glob('app.part*'):p.unlink()
chunks=[raw[i:i+PART] for i in range(0,len(raw),PART)]
for i,chunk in enumerate(chunks,1):(out/f'app.part{i}').write_bytes(chunk)
manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':'4.3.57-standalone-1','updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
meta={'product':'recepcion-pacientes','version':VERSION,'base_version':BASE_VERSION,'base_sha256':BASE_SHA,'app_sha256':hashlib.sha256(raw).hexdigest(),'app_size':len(raw),'parts_count':len(chunks),'part_max_bytes':PART,'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}
(out/'release_meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('V467_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
