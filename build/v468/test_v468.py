from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v468'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.68' and meta['base_version']=='4.3.67'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
source=raw.decode('utf-8');ast.parse(source)
assert 'APP_VERSION = "4.3.68"' in source
assert 'Tel. ${eh(p.celular)}' in source
assert 'Tel. ${eh(st.celular)}' in source
assert '_agenda_status_kick_lock = threading.Lock()' in source
assert 'v465BillingQueueHidden' in source
assert '__v466BillingBridge' in source

t=ast.parse(source);overlay=None
for n in t.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='V460_OVERLAY_JS':
        overlay=ast.literal_eval(n.value);break
assert overlay is not None
assert "const VERSION='4.3.68';" in overlay
assert 'width:min(600px,calc(100vw - 56px))' in overlay
assert 'max-width:600px' in overlay
assert 'justify-content:flex-end' in overlay
assert 'width:min(720px,calc(100vw - 72px))' not in overlay
builder=(ROOT/'build'/'v468'/'build_v468.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder and 'agenda/index.html' not in builder
print('V468_OK',meta['app_size'],meta['app_sha256'])
