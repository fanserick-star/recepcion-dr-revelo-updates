from __future__ import annotations
import ast, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v467'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.67'
assert meta['base_version']=='4.3.66'
assert meta['base_sha256']=='70a97679078eb9dfd549a03f7a10f880f7f2a2fc307c3e4f4ce969bade31b7fd'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert len(parts)==int(meta['parts_count'])
assert len(raw)==int(meta['app_size'])
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
assert hashlib.sha256((UP/'update_manifest.json').read_bytes()).hexdigest()==meta['manifest_sha256']
source=raw.decode('utf-8')
ast.parse(source)
assert 'APP_VERSION = "4.3.67"' in source

# Regresiones importantes conservadas.
for marker in (
    'BillingRecord.estado != "EMITIDA"',
    '_azur_group_key_for_rows',
    '_billing_visit_ids',
    'Usar correo registrado del paciente',
    '"ultima_atencion": h.last_visit_date',
    '_agenda_status_kick_lock = threading.Lock()',
    '__v466BillingBridge',
    'v465BillingQueueHidden',
):
    assert marker in source

# Extraer JS incrustados.
tree=ast.parse(source)
vals={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'V459_SETTINGS_JS','V460_OVERLAY_JS'}:
        vals[n.targets[0].id]=ast.literal_eval(n.value)
assert set(vals)=={'V459_SETTINGS_JS','V460_OVERLAY_JS'}
agenda=vals['V459_SETTINGS_JS']; overlay=vals['V460_OVERLAY_JS']

# Teléfono solo dentro de la ficha que se abre desde Agenda, para citas normales e importadas.
assert agenda.count('v467-agenda-phone')==2
assert "${p.celular?`<span class=\"v467-agenda-phone\">Tel. ${eh(p.celular)}</span>`:''}" in agenda
assert "${st.celular?`<span class=\"v467-agenda-phone\">Tel. ${eh(st.celular)}</span>`:''}" in agenda
assert agenda.count('v467-agenda-modal-shell')==2
assert 'window.openLinkedAgendaDetail' in agenda
assert 'window.openUnlinkedAgendaDetail' in agenda

# Compactación visual de ficha y Configuración.
assert "const VERSION='4.3.67';" in overlay
assert 'v467CompactStyle' in overlay
assert '.v467-agenda-modal-shell{width:min(720px,calc(100vw - 72px))' in overlay
assert '#config.v458-settings{width:min(1120px,calc(100% - 32px))' in overlay
assert '#config.v458-settings [data-config-section]{width:100%!important;max-width:980px' in overlay
assert '#config.v458-settings .config-tabs button{padding:8px 11px' in overlay
assert '.native-appointment-detail .v459-wa-step{padding:6px 0' in overlay

# No se modifican endpoints ni la web pública Agenda.
for marker in (
    '@app.post("/api/billing/approve")',
    '@app.post("/api/billing/azur/emit")',
    '@app.get("/api/agenda/week")',
): assert marker in source
builder=(ROOT/'build'/'v467'/'build_v467.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder
assert 'agenda/index.html' not in builder

print('V467_OK',meta['app_size'],meta['app_sha256'])
