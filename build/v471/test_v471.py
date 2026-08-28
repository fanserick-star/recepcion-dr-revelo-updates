from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v471'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.71' and meta['base_version']=='4.3.70'
assert meta['base_sha256']=='5ff5107cc4776fa616b4b1e49a9f4d6e08ce0035daed26f9c2cdde17693364ad'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
source=raw.decode('utf-8');ast.parse(source)
assert 'APP_VERSION = "4.3.71"' in source
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
assert "const VERSION='4.3.71';" in overlay
# El contenido interno conserva los 520 px de v4.3.70.
assert 'width:min(520px,calc(100vw - 56px))' in overlay
assert 'max-width:520px' in overlay
# Se recorta únicamente el marco exterior visible.
assert 'v471AgendaOuterStyle' in overlay
assert '.v471-agenda-outer{width:min(590px,calc(100vw - 40px))' in overlay
assert 'max-width:590px' in overlay
# El guard limpia ambas clases al abrir cualquier otro modal: Nueva atención no hereda el tamaño.
assert "document.querySelectorAll('.v467-agenda-modal-shell,.v471-agenda-outer')" in overlay
assert "el.classList.remove('v467-agenda-modal-shell','v471-agenda-outer')" in overlay
assert '__v469ModalGuard' in overlay
assert 'window.openModal=function(...args)' in overlay
# Solo las dos fichas de Agenda marcan el marco exterior.
assert agenda_js.count("classList.add('v471-agenda-outer')")==2
assert "closest('.modal-content,.modal-card,[role=\"dialog\"]')" in agenda_js
# Teléfono y contenido previo se mantienen.
assert 'Tel. ${eh(p.celular)}' in agenda_js
assert 'Tel. ${eh(st.celular)}' in agenda_js
# No se toca Agenda web.
builder=(ROOT/'build'/'v471'/'build_v471.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder and 'agenda/index.html' not in builder
print('V471_OK',meta['app_size'],meta['app_sha256'])
