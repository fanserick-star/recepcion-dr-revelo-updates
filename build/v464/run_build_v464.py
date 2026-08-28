from pathlib import Path
import ast, hashlib, json, re

ROOT = Path(__file__).resolve().parents[2]
VERSION = '4.3.64'
BASE_VERSION = '4.3.63'
BASE_SHA = '4a5802fcb04c402dcac40d6738b0bd7cb675d8daf4fb49023af5c900c230eab2'
oldroot = ROOT / 'updates' / 'v463'
parts = sorted(oldroot.glob('app.part*'), key=lambda p: int(p.name.split('part')[-1]))
raw = b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest() != BASE_SHA:
    raise SystemExit('La base v4.3.63 no coincide con la publicada')
s = raw.decode('utf-8')


def one(old: str, new: str, label: str):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'{label}: se esperaba 1 coincidencia y hubo {n}')
    s = s.replace(old, new, 1)


def replace_assignment_string(source: str, name: str, transform):
    tree = ast.parse(source)
    node = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == name:
            node = n
            break
    if node is None or not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
        raise SystemExit(f'No se encontró literal {name}')
    old_value = node.value.value
    new_value = transform(old_value)
    if new_value == old_value:
        raise SystemExit(f'{name}: la transformación no produjo cambios')
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[node.value.lineno - 1] + node.value.col_offset
    end = offsets[node.value.end_lineno - 1] + node.value.end_col_offset
    return source[:start] + repr(new_value) + source[end:]


one('APP_VERSION = "4.3.63"', 'APP_VERSION = "4.3.64"', 'APP_VERSION')
one("const VERSION='4.3.63';", "const VERSION='4.3.64';", 'badge version')
one('/v460/overlay.css?v=4.3.63', '/v460/overlay.css?v=4.3.64', 'overlay css cache')
one('/v460/overlay.js?v=4.3.63', '/v460/overlay.js?v=4.3.64', 'overlay js cache')


def patch_v459(js: str) -> str:
    old = "const sel=q('#waTestTemplate');if(sel){[...sel.options].forEach(o=>{const k=o.value||'';o.disabled=k!=='recordatorio_cita'});sel.value='recordatorio_cita'}"
    new = "const sel=q('#waTestTemplate');if(sel){[...sel.options].forEach(o=>{o.disabled=false});if(!['recordatorio_cita','cita_agendada','recordatorio_hoy'].includes(sel.value))sel.value='recordatorio_cita'}"
    if js.count(old) != 1:
        raise SystemExit(f'selector WhatsApp: se esperaba 1 coincidencia y hubo {js.count(old)}')
    js = js.replace(old, new, 1)
    return js


s = replace_assignment_string(s, 'V459_SETTINGS_JS', patch_v459)

# Evita los cuadros nativos de WebView2/Windows para avisos informativos.
# La v4.3.63 ya expone window.rpNotice; si por alguna razón aún no cargó, se
# conserva window.alert como fallback seguro.
s, alert_count = re.subn(r'(?<![\w.])alert\(', '(window.rpNotice||window.alert)(', s)
if alert_count < 3:
    raise SystemExit(f'Se esperaban varios alert() de interfaz y solo se reemplazaron {alert_count}')

final = s.encode('utf-8')
out = ROOT / 'updates' / 'v464'
out.mkdir(parents=True, exist_ok=True)
for p in out.glob('app.part*'):
    p.unlink()
PART = 70000
chunks = [final[i:i+PART] for i in range(0, len(final), PART)]
for i, chunk in enumerate(chunks, 1):
    (out / f'app.part{i}').write_bytes(chunk)

manifest = {
    'product': 'recepcion-pacientes',
    'version': VERSION,
    'app_version': VERSION,
    'runtime_version': VERSION,
    'launcher_version': '4.3.57-standalone-1',
    'updater_version': 'integrado-en-launcher',
    'copy': ['ABRIR_RECEPCION.py', 'app.py', 'update_manifest.json'],
}
manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
(out / 'update_manifest.json').write_bytes(manifest_bytes)
app_sha = hashlib.sha256(final).hexdigest()
meta = {
    'product': 'recepcion-pacientes',
    'version': VERSION,
    'base_version': BASE_VERSION,
    'base_sha256': BASE_SHA,
    'app_sha256': app_sha,
    'app_size': len(final),
    'part_max_bytes': PART,
    'parts_count': len(chunks),
    'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
}
(out / 'release_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print('V464_BUILT', len(final), app_sha, 'parts', len(chunks), 'alerts_replaced', alert_count)
