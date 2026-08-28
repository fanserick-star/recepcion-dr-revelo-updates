from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v470'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.70' and meta['base_version']=='4.3.69'
assert meta['base_sha256']=='0de0f09b7af4a8176fcde0f344e5628bd966db68bf21deaebc1068c32e7edf3a'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
source=raw.decode('utf-8');ast.parse(source)
assert 'APP_VERSION = "4.3.70"' in source
assert '_agenda_status_kick_lock = threading.Lock()' in source
assert 'v465BillingQueueHidden' in source
assert '__v466BillingBridge' in source

t=ast.parse(source);overlay=None;agenda_js=None
for n in t.body:
    if not (isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)):
        continue
    name=n.targets[0].id
    if name=='V460_OVERLAY_JS': overlay=ast.literal_eval(n.value)
    elif name=='V459_SETTINGS_JS': agenda_js=ast.literal_eval(n.value)
assert overlay is not None and agenda_js is not None
assert "const VERSION='4.3.70';" in overlay
# Único ajuste visual buscado: 520 px en la ficha Agenda.
assert 'width:min(520px,calc(100vw - 56px))' in overlay
assert 'max-width:520px' in overlay
assert 'width:min(600px,calc(100vw - 56px))' not in overlay
# Se conserva altura automática y el guard que evita afectar Nueva atención.
assert 'height:auto!important' in overlay
assert 'min-height:0!important' in overlay
assert 'max-height:calc(100vh - 44px)!important' in overlay
assert '__v469ModalGuard' in overlay
assert "document.querySelectorAll('.v467-agenda-modal-shell')" in overlay
assert "el.classList.remove('v467-agenda-modal-shell')" in overlay
assert 'window.openModal=function(...args)' in overlay
# El teléfono y el marcado de la ficha Agenda permanecen.
assert 'Tel. ${eh(p.celular)}' in agenda_js
assert 'Tel. ${eh(st.celular)}' in agenda_js
assert "classList.add('v467-agenda-modal-shell')" in agenda_js
# No se toca Agenda web.
builder=(ROOT/'build'/'v470'/'build_v470.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder and 'agenda/index.html' not in builder
print('V470_OK',meta['app_size'],meta['app_sha256'])
