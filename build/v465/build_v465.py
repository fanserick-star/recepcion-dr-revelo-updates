from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.65'
BASE_VERSION='4.3.64'
BASE_SHA='33ba932ef73ae28722c5f8f1a75d439a82cfb4a67adb78d837430522b786f9a8'
oldroot=ROOT/'updates'/'v464'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.64 no coincide con la publicada')
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
one('APP_VERSION = "4.3.64"','APP_VERSION = "4.3.65"','APP_VERSION')
one("const VERSION='4.3.64';","const VERSION='4.3.65';",'badge version')
one('/v460/overlay.css?v=4.3.64','/v460/overlay.css?v=4.3.65','overlay css cache')
one('/v460/overlay.js?v=4.3.64','/v460/overlay.js?v=4.3.65','overlay js cache')

# 1) Historial 2020-2025: reutiliza el campo que la UI de Atender ya muestra como última atención.
one('        "ultima_atencion": None,\n        "historical_first_year": int(h.first_year or 2020),',
    '        "ultima_atencion": h.last_visit_date,\n        "historical_first_year": int(h.first_year or 2020),',
    'última cita histórica')

# 2) Agenda PC: la semana se dibuja inmediatamente desde SQLite y la actualización
# de estados de Neon corre detrás, en una sesión local propia. No se toca agenda/ web.
HELPER='''\n\n_agenda_status_kick_lock = threading.Lock()\n_agenda_status_kick_running: set[tuple[str, ...]] = set()\n\ndef _kick_agenda_status_sync(dates) -> None:\n    key = tuple(str(d) for d in dates)\n    with _agenda_status_kick_lock:\n        if key in _agenda_status_kick_running:\n            return\n        _agenda_status_kick_running.add(key)\n\n    def worker():\n        try:\n            with LocalSessionLocal() as ldb:\n                _sync_agenda_states_from_cloud(ldb, dates)\n        except Exception:\n            pass\n        finally:\n            with _agenda_status_kick_lock:\n                _agenda_status_kick_running.discard(key)\n\n    threading.Thread(target=worker, name="agenda-state-sync-bg", daemon=True).start()\n'''
marker='\n\n@app.get("/api/agenda/week")\ndef agenda_week(anchor: date, db: Session = Depends(get_db), user: User = Depends(current_user)):'
if s.count(marker)!=1:
    raise SystemExit(f'agenda week marker: se esperaba 1 coincidencia y hubo {s.count(marker)}')
s=s.replace(marker,HELPER+marker,1)
one('    _sync_agenda_states_from_cloud(db, dates)\n    linked_rows = db.execute(',
    '    _kick_agenda_status_sync(dates)\n    linked_rows = db.execute(',
    'agenda sync no bloqueante')

# 3) Facturación: oculta únicamente el recuadro redundante titulado "Cola de facturación".
# Se conserva en DOM la lógica inferior y no se interceptan endpoints ni acciones.
BILLING_PATCH=r'''\n;(()=>{\n  const normV465=s=>String(s||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').replace(/\\s+/g,' ').trim().toLowerCase();\n  let v465BillingTimer=0;\n  function hideV465BillingQueue(){\n    const wanted='cola de facturacion';\n    const selectors='h1,h2,h3,h4,h5,h6,legend,.card-title,.panel-title,.section-title,strong,b';\n    let title=[...document.querySelectorAll(selectors)].find(el=>normV465(el.textContent).startsWith(wanted));\n    if(!title){\n      title=[...document.querySelectorAll('div,span')].find(el=>{const t=normV465(el.textContent);return t.startsWith(wanted)&&t.length<90&&el.children.length<=2});\n    }\n    if(!title)return false;\n    let box=title.closest('.billing-queue,.billing-next,.queue-card,.card,.panel,.box');\n    if(!box){\n      const p=title.parentElement;\n      if(p&&normV465(p.textContent).startsWith(wanted)&&normV465(p.textContent).length<1200)box=p;\n    }\n    if(!box||box.dataset.v465BillingQueueHidden==='1')return !!box;\n    box.dataset.v465BillingQueueHidden='1';\n    box.style.display='none';\n    box.setAttribute('aria-hidden','true');\n    return true;\n  }\n  function scheduleV465BillingCleanup(){\n    if(v465BillingTimer)return;\n    v465BillingTimer=setTimeout(()=>{v465BillingTimer=0;hideV465BillingQueue()},100);\n  }\n  function bootV465Billing(){hideV465BillingQueue();setTimeout(hideV465BillingQueue,250);setTimeout(hideV465BillingQueue,900)}\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bootV465Billing,{once:true});else bootV465Billing();\n  const root=document.documentElement;\n  if(root)new MutationObserver(scheduleV465BillingCleanup).observe(root,{childList:true,subtree:true});\n})();\n'''

def patch_overlay(js):
    if 'v465BillingQueueHidden' in js:
        raise SystemExit('El overlay ya contiene el parche v4.3.65')
    return js+BILLING_PATCH

rewrite_js_assignment('V460_OVERLAY_JS',patch_overlay)

out=ROOT/'updates'/'v465';out.mkdir(parents=True,exist_ok=True)
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
print('V465_BUILT',len(raw),meta['app_sha256'],'parts',len(chunks))
