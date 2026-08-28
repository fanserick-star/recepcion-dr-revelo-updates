from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v469'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.69' and meta['base_version']=='4.3.68'
assert meta['base_sha256']=='4d8ac7054c1697c6a98a6889c7211ece3fe8c0d67d7594ff8c72473bd3f16dd3'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
source=raw.decode('utf-8');ast.parse(source)
assert 'APP_VERSION = "4.3.69"' in source
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
# Cambios previos de Agenda permanecen.
assert 'Tel. ${eh(p.celular)}' in agenda_js
assert 'Tel. ${eh(st.celular)}' in agenda_js
assert "classList.add('v467-agenda-modal-shell')" in agenda_js
# La ficha Agenda queda compacta y con altura natural.
assert "const VERSION='4.3.69';" in overlay
assert 'width:min(600px,calc(100vw - 56px))' in overlay
assert 'height:auto!important' in overlay
assert 'min-height:0!important' in overlay
assert 'max-height:calc(100vh - 44px)!important' in overlay
# Regresión encontrada: la clase compacta no puede quedarse pegada al modal reutilizable.
assert '__v469ModalGuard' in overlay
assert "document.querySelectorAll('.v467-agenda-modal-shell')" in overlay
assert "el.classList.remove('v467-agenda-modal-shell')" in overlay
assert 'window.openModal=function(...args)' in overlay
assert 'clearAgendaModalShell();' in overlay
assert 'return original.apply(this,args);' in overlay
# No se toca la web Agenda.
builder=(ROOT/'build'/'v469'/'build_v469.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder and 'agenda/index.html' not in builder
print('V469_OK',meta['app_size'],meta['app_sha256'])
