from pathlib import Path
import ast, copy, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v472'
BASE=ROOT/'updates'/'v471'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.72' and meta['base_version']=='4.3.71'
assert meta['base_sha256']=='18bdb05cff6b03c7c06da98f29888f5880af34df23578ddbe5fe3f1ee26a56c6'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
source=raw.decode('utf-8');candidate_tree=ast.parse(source)
assert 'APP_VERSION = "4.3.72"' in source

base_parts=sorted(BASE.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
base_raw=b''.join(p.read_bytes() for p in base_parts)
assert hashlib.sha256(base_raw).hexdigest()==meta['base_sha256']
base_source=base_raw.decode('utf-8');base_tree=ast.parse(base_source)

old_alert="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setInterval(v464BindAlert,5000);"
new_alert="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setTimeout(v464BindAlert,1500);"
old_watch="function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch='1';new MutationObserver(()=>{paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()}).observe(root,{childList:true,subtree:true})}}"
new_watch="let v472UiTimer=0;function scheduleV472UiRefresh(){if(v472UiTimer)return;v472UiTimer=setTimeout(()=>{v472UiTimer=0;paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()},140)}function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch='1';new MutationObserver(scheduleV472UiRefresh).observe(root,{childList:true,subtree:true})}}"
old_picker="new MutationObserver(()=>installV464TemplatePicker()).observe(document.documentElement,{childList:true,subtree:true});"
new_picker="let v472PickerTimer=0;new MutationObserver(()=>{if(v472PickerTimer)return;v472PickerTimer=setTimeout(()=>{v472PickerTimer=0;installV464TemplatePicker()},160)}).observe(document.documentElement,{childList:true,subtree:true});"

# Mapa de asignaciones literales top-level: comparamos TODAS, no solo las tocadas.
def literal_assignments(tree):
    out={}
    for n in tree.body:
        if not (isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)):
            continue
        try: value=ast.literal_eval(n.value)
        except Exception: continue
        out[n.targets[0].id]=value
    return out

base_literals=literal_assignments(base_tree)
candidate_literals=literal_assignments(candidate_tree)
assert set(base_literals)==set(candidate_literals), 'Cambió el conjunto de asignaciones literales'

picker_hosts=[name for name,value in base_literals.items() if isinstance(value,str) and old_picker in value]
assert len(picker_hosts)==1, f'Watcher WhatsApp base ambiguo: {picker_hosts}'
picker_host=picker_hosts[0]

for name,base_value in base_literals.items():
    expected=base_value
    if name=='APP_VERSION':
        expected='4.3.72'
    if isinstance(expected,str):
        expected=expected.replace('/v460/overlay.css?v=4.3.71','/v460/overlay.css?v=4.3.72')
        expected=expected.replace('/v460/overlay.js?v=4.3.71','/v460/overlay.js?v=4.3.72')
        if name=='V460_OVERLAY_JS':
            expected=expected.replace("const VERSION='4.3.71';","const VERSION='4.3.72';",1)
            expected=expected.replace(old_alert,new_alert,1)
            expected=expected.replace(old_watch,new_watch,1)
        if old_picker in expected:
            expected=expected.replace(old_picker,new_picker,1)
    assert candidate_literals[name]==expected, f'Cambio no autorizado en asignación {name}'

# Además de comparar todos los literales, verificamos que ninguna función, clase,
# llamada, endpoint o estructura Python fuera de ellos haya cambiado.
def scrub_literals(tree):
    tree=copy.deepcopy(tree)
    for n in tree.body:
        if not (isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)):
            continue
        try: ast.literal_eval(n.value)
        except Exception: continue
        n.value=ast.Constant(value='__LITERAL__')
    return ast.dump(tree,include_attributes=False)

assert scrub_literals(base_tree)==scrub_literals(candidate_tree), 'Cambió código Python fuera de asignaciones literales'

# Verifica presencia exacta de las optimizaciones y ausencia del timer permanente.
assert new_alert in source and old_alert not in source
assert new_watch in source and old_watch not in source
assert new_picker in source and old_picker not in source
assert 'setInterval(v464BindAlert,5000)' not in source
assert 'scheduleV472UiRefresh' in source and 'v472PickerTimer' in source

# Extraer JS críticos e invariantes visuales.
overlay=candidate_literals.get('V460_OVERLAY_JS')
settings=candidate_literals.get('V459_SETTINGS_JS')
assert isinstance(overlay,str) and isinstance(settings,str)
assert "const VERSION='4.3.72';" in overlay
assert 'width:min(520px,calc(100vw - 56px))' in overlay
assert '.v471-agenda-outer{width:min(590px,calc(100vw - 40px))' in overlay
assert "document.querySelectorAll('.v467-agenda-modal-shell,.v471-agenda-outer')" in overlay
assert '__v469ModalGuard' in overlay
assert settings.count("classList.add('v471-agenda-outer')")==2
assert 'Tel. ${eh(p.celular)}' in settings
assert 'Tel. ${eh(st.celular)}' in settings
assert new_picker in candidate_literals[picker_host]

# Servicios y datos sensibles siguen presentes. La comparación semántica anterior
# garantiza que su implementación sea idéntica a v4.3.71.
critical=[
    'WHATSAPP_CLOUD_MODE = (os.getenv("WHATSAPP_CLOUD_MODE") or "1").strip() != "0"',
    'WHATSAPP_CLOUD_TEST_PREFIX = "mobile:whatsapp-cloud-test:"',
    'threading.Thread(target=_whatsapp_background_loop',
    '@app.post("/api/whatsapp/cloud-test")',
    '@app.post("/api/billing/azur/emit-all-pending")',
    '_agenda_status_kick_lock = threading.Lock()',
    'HISTORICAL_REGISTRY_FILE',
    'OFFLINE_DB_PATH',
    'pool_size=3',
    'pool_size=1',
    'threading.Thread(target=_deferred_cloud_init',
]
for marker in critical:
    assert marker in source, marker

# El constructor no puede tocar Agenda web ni Worker Cloud.
builder=(ROOT/'build'/'v472'/'build_v472.py').read_text(encoding='utf-8')
for forbidden in ("ROOT/'agenda'", 'agenda/index.html', "ROOT/'cloudflare'", 'whatsapp_worker_v2_5'):
    assert forbidden not in builder, forbidden

print('V472_OK',meta['app_size'],meta['app_sha256'],'picker',picker_host)
