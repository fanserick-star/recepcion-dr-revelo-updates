from __future__ import annotations
import ast, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v466'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.66'
assert meta['base_version']=='4.3.65'
assert meta['base_sha256']=='e9763acd0bbf7792a8b90a88093a5ce0749bcc9fddce2dd75e9495cf89d81958'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert len(parts)==int(meta['parts_count'])
assert len(raw)==int(meta['app_size'])
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
assert hashlib.sha256((UP/'update_manifest.json').read_bytes()).hexdigest()==meta['manifest_sha256']
source=raw.decode('utf-8')
ast.parse(source)
assert 'APP_VERSION = "4.3.66"' in source

# Regresiones importantes de v4.3.65 y anteriores permanecen intactas.
assert 'BillingRecord.estado != "EMITIDA"' in source
assert '_azur_group_key_for_rows' in source
assert '_billing_visit_ids' in source
assert 'Usar correo registrado del paciente' in source
assert '__v464WaTemplateValue' in source
assert 'v464-template-picker' in source
assert 'v464BindAlert' in source
assert '"ultima_atencion": h.last_visit_date' in source
assert '"historical_last_visit_date": h.last_visit_date' in source
assert '_agenda_status_kick_lock = threading.Lock()' in source
assert 'with LocalSessionLocal() as ldb:' in source
assert '_kick_agenda_status_sync(dates)' in source
assert 'threading.Thread(target=worker, name="agenda-state-sync-bg", daemon=True).start()' in source
assert 'v465BillingQueueHidden' in source

# Endpoints centrales de facturación/AZUR no se cambian ni se sustituyen.
for marker in (
    '@app.post("/api/billing/approve")',
    '@app.post("/api/billing/approve-all-pending")',
    '@app.post("/api/billing/azur/preview")',
    '@app.post("/api/billing/azur/emit")',
    '@app.post("/api/billing/azur/emit-all-pending")',
):
    assert marker in source

# Extraer los JS incrustados que intervienen en las confirmaciones.
tree=ast.parse(source)
consts={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
        if n.targets[0].id in {'V458_SETTINGS_JS','V459_SETTINGS_JS','V460_OVERLAY_JS'}:
            consts[n.targets[0].id]=ast.literal_eval(n.value)
assert set(consts)=={'V458_SETTINGS_JS','V459_SETTINGS_JS','V460_OVERLAY_JS'}
settings=consts['V458_SETTINGS_JS']
whatsapp=consts['V459_SETTINGS_JS']
overlay=consts['V460_OVERLAY_JS']

# v4.3.65 continúa ocultando solo la tarjeta redundante de la cola.
assert 'v465BillingQueueHidden' in overlay
assert "wanted='cola de facturacion'" in overlay
assert "box.style.display='none'" in overlay

# Configuración y prueba WhatsApp ya no tienen fallback nativo conocido.
assert "window.rpConfirm('¿Renovar el enlace editable de Recepción / Ayudante?" in settings
assert "'Renovar acceso web'" in settings
assert "if(!confirm('¿Renovar el enlace editable" not in settings
assert "'Confirmar prueba WhatsApp'" in whatsapp
assert 'Promise.resolve(confirm(' not in whatsapp

# Bridge de compatibilidad: transforma confirmaciones antiguas de Facturación/AZUR
# en rpConfirm, pero deja la acción original continuar solo tras aceptar.
assert "const VERSION='4.3.66';" in overlay
assert '__v466BillingBridge' in overlay
assert 'v466BillingPrompt=/factur|azur|sri|comprobante/i' in overlay
assert 'Date.now()-v466ClickAt<10000' in overlay
assert 'window.rpConfirm(text,title)' in overlay
assert "'Confirmar emisión en AZUR':'Confirmar facturación'" in overlay
assert 'if(v466Pending)return false;' in overlay
assert 'v466AllowTarget=target' in overlay
assert 'target.click()' in overlay
assert '720-(Date.now()-originalClickAt)' in overlay
assert 'if(v466AllowTarget&&target===v466AllowTarget){v466AllowTarget=null;return true;}' in overlay

# La web pública Agenda sigue fuera del parche.
builder=(ROOT/'build'/'v466'/'build_v466.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder
assert 'agenda/index.html' not in builder

print('V466_OK',meta['app_size'],meta['app_sha256'])
