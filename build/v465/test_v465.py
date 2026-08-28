from __future__ import annotations
import ast, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UP=ROOT/'updates'/'v465'
meta=json.loads((UP/'release_meta.json').read_text(encoding='utf-8'))
assert meta['version']=='4.3.65'
assert meta['base_version']=='4.3.64'
assert meta['base_sha256']=='33ba932ef73ae28722c5f8f1a75d439a82cfb4a67adb78d837430522b786f9a8'
parts=sorted(UP.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
assert len(parts)==int(meta['parts_count'])
assert len(raw)==int(meta['app_size'])
assert hashlib.sha256(raw).hexdigest()==meta['app_sha256']
assert hashlib.sha256((UP/'update_manifest.json').read_bytes()).hexdigest()==meta['manifest_sha256']
source=raw.decode('utf-8')
ast.parse(source)
assert 'APP_VERSION = "4.3.65"' in source

# Regresiones v4.3.64 / facturación previa deben permanecer.
assert 'BillingRecord.estado != "EMITIDA"' in source
assert '_azur_group_key_for_rows' in source
assert '_billing_visit_ids' in source
assert 'Usar correo registrado del paciente' in source
assert '__v464WaTemplateValue' in source
assert 'v464-template-picker' in source
assert 'v464BindAlert' in source

# Historial 2020-2025: la búsqueda de Atender recibe la última cita real.
assert '"ultima_atencion": h.last_visit_date' in source
assert '"historical_last_visit_date": h.last_visit_date' in source

# Agenda PC: el request ya no espera a Neon; sincroniza en hilo daemon con su propia sesión SQLite.
assert '_agenda_status_kick_lock = threading.Lock()' in source
assert '_agenda_status_kick_running' in source
assert 'with LocalSessionLocal() as ldb:' in source
assert '_sync_agenda_states_from_cloud(ldb, dates)' in source
assert 'threading.Thread(target=worker, name="agenda-state-sync-bg", daemon=True).start()' in source
assert '_kick_agenda_status_sync(dates)' in source
assert '_sync_agenda_states_from_cloud(db, dates)' not in source

# UI: solo se oculta la tarjeta redundante por su título, sin tocar endpoints/listado inferior.
tree=ast.parse(source)
overlay=None
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='V460_OVERLAY_JS':
        overlay=ast.literal_eval(n.value);break
assert overlay is not None
assert "const VERSION='4.3.65';" in overlay
assert 'v465BillingQueueHidden' in overlay
assert "wanted='cola de facturacion'" in overlay
assert "box.style.display='none'" in overlay
assert '/api/billing/next' in source
assert '@app.get("/api/billing")' in source
assert '@app.get("/api/billing/next")' in source

# La web pública Agenda no forma parte del paquete ni de las transformaciones.
builder=(ROOT/'build'/'v465'/'build_v465.py').read_text(encoding='utf-8')
assert "ROOT/'agenda'" not in builder
assert "agenda/index.html" not in builder

print('V465_OK',meta['app_size'],meta['app_sha256'])
