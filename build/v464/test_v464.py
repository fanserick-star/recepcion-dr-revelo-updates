from __future__ import annotations
import ast, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]/'updates'/'v464'
meta=json.loads((ROOT/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.64'
assert meta['base_version']=='4.3.63'
parts=sorted(ROOT.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert len(parts)==int(meta['parts_count'])
assert len(raw)==int(meta['app_size'])
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
assert hashlib.sha256((ROOT/'update_manifest.json').read_bytes()).hexdigest()==meta['manifest_sha256']
source=raw.decode('utf-8')
assert 'APP_VERSION = "4.3.64"' in source
assert "const VERSION='4.3.64';" in source
# Regresiones de facturación v4.3.63 deben permanecer.
assert 'BillingRecord.estado != "EMITIDA"' in source
assert '_azur_group_key_for_rows' in source
assert '_billing_visit_ids' in source
assert 'Usar correo registrado del paciente' in source
# UI v4.3.64
assert '__v464WaTemplateValue' in source
assert 'v464-template-picker' in source
assert 'Confirmación' in source and 'Cita agendada' in source and 'Recordatorio de hoy' in source
assert 'v464BindAlert' in source

tree=ast.parse(source)
consts={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'V459_SETTINGS_JS','V460_OVERLAY_JS'}:
        consts[n.targets[0].id]=ast.literal_eval(n.value)
assert set(consts)=={'V459_SETTINGS_JS','V460_OVERLAY_JS'}
settings=consts['V459_SETTINGS_JS'];overlay=consts['V460_OVERLAY_JS']
assert "function testTemplate(){return window.__v464WaTemplateValue||q('#waTestTemplate')?.value||'recordatorio_cita'}" in settings
assert "['recordatorio_cita','Confirmación']" in settings
assert "['cita_agendada','Cita agendada']" in settings
assert "['recordatorio_hoy','Recordatorio de hoy']" in settings
assert 'window.rpNotice(' in settings
assert 'v464BindAlert' in overlay
assert 'setInterval(v464BindAlert,5000)' in overlay
print('V464_UI_OK',meta['app_size'],meta['app_sha256'])
