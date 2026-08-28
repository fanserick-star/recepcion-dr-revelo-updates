from pathlib import Path
import ast, hashlib, json

ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v472'
BASE=ROOT/'updates'/'v471'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.72' and meta['base_version']=='4.3.71'
assert meta['base_sha256']=='18bdb05cff6b03c7c06da98f29888f5880af34df23578ddbe5fe3f1ee26a56c6'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
source=raw.decode('utf-8');ast.parse(source)
assert 'APP_VERSION = "4.3.72"' in source

# La candidata debe ser exactamente v4.3.71 más tres optimizaciones de frontend
# y el cambio de número de versión. Esto impide tocar accidentalmente backend,
# Neon, WhatsApp Cloud, AZUR, persistencia o reglas de negocio.
base_parts=sorted(BASE.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
base_raw=b''.join(p.read_bytes() for p in base_parts)
assert hashlib.sha256(base_raw).hexdigest()==meta['base_sha256']
base_source=base_raw.decode('utf-8')

old_alert="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setInterval(v464BindAlert,5000);"
new_alert="window.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setTimeout(v464BindAlert,1500);"
old_watch="function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch='1';new MutationObserver(()=>{paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()}).observe(root,{childList:true,subtree:true})}}"
new_watch="let v472UiTimer=0;function scheduleV472UiRefresh(){if(v472UiTimer)return;v472UiTimer=setTimeout(()=>{v472UiTimer=0;paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()},140)}function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch='1';new MutationObserver(scheduleV472UiRefresh).observe(root,{childList:true,subtree:true})}}"
old_picker="new MutationObserver(()=>installV464TemplatePicker()).observe(document.documentElement,{childList:true,subtree:true});"
new_picker="let v472PickerTimer=0;new MutationObserver(()=>{if(v472PickerTimer)return;v472PickerTimer=setTimeout(()=>{v472PickerTimer=0;installV464TemplatePicker()},160)}).observe(document.documentElement,{childList:true,subtree:true});"

# Verifica presencia exacta de las optimizaciones.
assert new_alert in source and old_alert not in source
assert new_watch in source and old_watch not in source
assert new_picker in source and old_picker not in source
assert 'setInterval(v464BindAlert,5000)' not in source
assert 'scheduleV472UiRefresh' in source and 'v472PickerTimer' in source

# Prueba de delta exacto: revertimos solo las tres optimizaciones y la versión.
normalized=source.replace(new_alert,old_alert).replace(new_watch,old_watch).replace(new_picker,old_picker)
normalized=normalized.replace('4.3.72','4.3.71')
assert normalized==base_source, 'La candidata contiene cambios fuera del alcance aprobado'

# Extraer JS críticos y verificar invariantes de interfaz/servicios.
t=ast.parse(source);overlay=None;settings=None
for n in t.body:
    if not (isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)):
        continue
    name=n.targets[0].id
    if name=='V460_OVERLAY_JS': overlay=ast.literal_eval(n.value)
    elif name=='V459_SETTINGS_JS': settings=ast.literal_eval(n.value)
assert overlay is not None and settings is not None
assert "const VERSION='4.3.72';" in overlay

# Agenda visual definitiva de v4.3.71 debe permanecer idéntica.
assert 'width:min(520px,calc(100vw - 56px))' in overlay
assert '.v471-agenda-outer{width:min(590px,calc(100vw - 40px))' in overlay
assert "document.querySelectorAll('.v467-agenda-modal-shell,.v471-agenda-outer')" in overlay
assert '__v469ModalGuard' in overlay
assert settings.count("classList.add('v471-agenda-outer')")==2
assert 'Tel. ${eh(p.celular)}' in settings
assert 'Tel. ${eh(st.celular)}' in settings

# Funciones sensibles siguen presentes; el delta exacto de arriba garantiza que
# su implementación no cambió respecto a la versión estable.
critical=[
    'WHATSAPP_CLOUD_MODE = (os.getenv("WHATSAPP_CLOUD_MODE") or "1").strip() != "0"',
    'def start_whatsapp_worker_if_enabled()',
    'if WHATSAPP_CLOUD_MODE:',
    '@app.post("/api/whatsapp/cloud-test")',
    '@app.post("/api/billing/azur/emit")',
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

print('V472_OK',meta['app_size'],meta['app_sha256'])
