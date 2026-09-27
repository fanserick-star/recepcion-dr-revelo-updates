from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "updates" / "v4_6_6_fast_attention_save"
FLAT = ROOT / "refactor_build" / "reception_flat_466"

PROBE = r'''
import hashlib, json, os, re, sys
from pathlib import Path
os.environ['RP_FORCE_OFFLINE']='1'
os.environ['DATABASE_URL']=''
os.environ['HISTORIA_DATABASE_URL']=''
os.environ['REMOTE_AGENDA_AUTOSTART']='0'
os.environ['WHATSAPP_ENABLED']='0'
sys.path.insert(0, os.getcwd())
import app
core = getattr(app, 'core', None)
if core is None and hasattr(app, '_rf_legacy'):
    core = app._rf_legacy._rf_layers['app_base_4428']
routes=[]
for r in app.app.router.routes:
    methods=sorted(getattr(r,'methods',set()) or set())
    ep=getattr(r,'endpoint',None)
    routes.append({'path':getattr(r,'path',None),'methods':methods,'endpoint':getattr(ep,'__name__',None)})
route_keys=[(x['path'],tuple(x['methods'])) for x in routes]
tables=[]
base=getattr(core,'Base',None)
if base is not None:
    for name, table in sorted(base.metadata.tables.items()):
        cols=[]
        for c in table.columns:
            cols.append((c.name, str(c.type), bool(c.nullable), bool(c.primary_key)))
        tables.append((name, cols))
def sh(v): return hashlib.sha256(str(v or '').encode('utf-8')).hexdigest()
openapi = app.app.openapi()
openapi_blob = json.dumps(openapi, ensure_ascii=False, sort_keys=True, separators=(',',':'))
out={
 'version':str(getattr(app,'APP_VERSION','')),
 'route_count':len(routes),
 'routes':sorted(routes,key=lambda x:(str(x['path']),','.join(x['methods']),str(x['endpoint']))),
 'duplicate_route_keys':len(route_keys)-len(set(route_keys)),
 'tables':tables,
 'overlay_js_sha':sh(getattr(core,'V460_OVERLAY_JS','')),
 'overlay_css_sha':sh(getattr(core,'V460_OVERLAY_CSS','')),
 'openapi_sha':hashlib.sha256(openapi_blob.encode('utf-8')).hexdigest(),
 'openapi_paths':len(openapi.get('paths') or {}),
 'openapi_schemas':len(((openapi.get('components') or {}).get('schemas') or {})),
 'historical_modules_loaded':sorted(k for k in sys.modules if re.match(r'^app_(?:base|prev|patch)_\d+$',k)),
 'core_sync_name':getattr(getattr(core,'sync_one_operation',None),'__name__',None),
 'core_normalize_patient_name':getattr(getattr(core,'normalize_patient_payload',None),'__name__',None),
}
Path(os.environ['PROBE_OUT']).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
'''


def probe(runtime: Path, label: str):
    out = Path(tempfile.mkdtemp(prefix=f"rp-{label}-")) / "probe.json"
    data_dir = Path(tempfile.mkdtemp(prefix=f"rp-{label}-data-"))
    env = os.environ.copy()
    env.update({
        "RP_DATA_DIR": str(data_dir),
        "RP_FORCE_OFFLINE": "1",
        "DATABASE_URL": "",
        "HISTORIA_DATABASE_URL": "",
        "REMOTE_AGENDA_AUTOSTART": "0",
        "WHATSAPP_ENABLED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PROBE_OUT": str(out),
    })
    p = subprocess.run([sys.executable, "-c", PROBE], cwd=runtime, env=env, text=True, capture_output=True, timeout=60)
    if p.returncode:
        print(f"--- {label} STDOUT ---\n{p.stdout}\n--- STDERR ---\n{p.stderr}")
        raise SystemExit(f"probe {label} failed rc={p.returncode}")
    return json.loads(out.read_text(encoding="utf-8"))


orig = probe(ORIGINAL, "original")
flat = probe(FLAT, "flat")

assert orig['version'] == flat['version'] == '4.6.6', (orig['version'], flat['version'])
assert orig['duplicate_route_keys'] == 0
assert flat['duplicate_route_keys'] == 0

# Route contract: same path+method and endpoint function names.
def route_contract(rows):
    return sorted((r['path'], tuple(r['methods']), r['endpoint']) for r in rows)
assert route_contract(orig['routes']) == route_contract(flat['routes']), (
    len(orig['routes']), len(flat['routes']),
    sorted(set(route_contract(orig['routes'])) - set(route_contract(flat['routes'])))[:10],
    sorted(set(route_contract(flat['routes'])) - set(route_contract(orig['routes'])))[:10],
)
assert orig['tables'] == flat['tables'], 'SQLAlchemy metadata drift'
assert orig['overlay_js_sha'] == flat['overlay_js_sha'], (orig['overlay_js_sha'], flat['overlay_js_sha'])
assert orig['overlay_css_sha'] == flat['overlay_css_sha'], (orig['overlay_css_sha'], flat['overlay_css_sha'])
# OpenAPI is a stronger API contract than route names alone: it captures path
# params, query/body validation, request/response schemas and operation metadata.
assert orig['openapi_sha'] == flat['openapi_sha'], (
    orig['openapi_sha'], flat['openapi_sha'],
    orig['openapi_paths'], flat['openapi_paths'],
    orig['openapi_schemas'], flat['openapi_schemas'],
)
# The production 4.6.6 embedded loader cleans historical module names from
# sys.modules after bootstrap, so their post-import count is not a production
# contract. The definitive candidate must still guarantee that no historical
# app_base/app_prev/app_patch modules remain loaded.
assert flat['historical_modules_loaded'] == [], flat['historical_modules_loaded']
assert flat['core_sync_name'] == orig['core_sync_name']
assert flat['core_normalize_patient_name'] == orig['core_normalize_patient_name']

# Structural gate: definitive candidate has no embedded source loader or historical imports.
combined = (FLAT/'app.py').read_text(encoding='utf-8-sig') + (FLAT/'features_runtime.py').read_text(encoding='utf-8-sig')
assert '_EMBEDDED_RUNTIME_SOURCES' not in combined
assert 'MetaPathFinder' not in combined
assert not re.search(r'^\s*(?:import|from)\s+app_(?:base|prev|patch)_\d+', combined, re.M)

# Functional 4.6.6 contract on candidate only.
os.environ.update({
    'RP_DATA_DIR': tempfile.mkdtemp(prefix='rp-flat-functional-'),
    'RP_FORCE_OFFLINE': '1',
    'DATABASE_URL': '',
    'HISTORIA_DATABASE_URL': '',
    'REMOTE_AGENDA_AUTOSTART': '0',
    'WHATSAPP_ENABLED': '0',
})
os.chdir(FLAT)
sys.path.insert(0, str(FLAT))
import app as candidate
candidate.core.Base.metadata.create_all(candidate.core.local_engine)

from datetime import date, datetime
from reception_payment_terminal import V4504VisitBatchPaymentIn

def required_patient_kwargs():
    out={}
    for col in candidate.core.Patient.__table__.columns:
        if col.primary_key or col.nullable or col.default is not None or col.server_default is not None:
            continue
        typ=type(col.type).__name__.lower(); name=col.name
        if name=='nombre': value='PACIENTE REFACTOR PRUEBA'
        elif 'date' in typ and 'time' not in typ: value=date(1990,1,1)
        elif 'datetime' in typ: value=datetime.utcnow()
        elif 'int' in typ: value=0
        elif 'numeric' in typ or 'float' in typ: value=0
        else: value='TESTREF'
        out[name]=value
    return out

with candidate.core.LocalSessionLocal() as db:
    p=candidate.core.Patient(**required_patient_kwargs())
    if hasattr(p,'cedula'): p.cedula='TESTREF'
    db.add(p); db.commit(); db.refresh(p); patient_id=int(p.id)

User=SimpleNamespace(username='refactor-test')
Service=candidate.core.VisitBatchServiceIn
# Use the semantic payment module directly. The old `_rf_legacy._rf_layers`
# registry is intentionally absent from the consolidated runtime.
Batch=V4504VisitBatchPaymentIn

def local_db():
    g=candidate._v466_local_attention_db(); db=next(g); return g,db

proc=Batch(patient_id=patient_id,fecha=date.today(),tipo=None,services=[Service(procedimiento='INSTILACION',valor=80.0)],observacion='REFACTOR',payment_method='EFECTIVO')
g,db=local_db(); result=candidate.v466_fast_local_attention_save(proc,db=db,user=User)
try: next(g)
except StopIteration: pass
proc_id=int(result['items'][0]['id'])
with candidate.core.LocalSessionLocal() as db:
    v=db.get(candidate.core.Visit,proc_id); assert v and str(v.procedimiento or '').upper()=='INSTILACION'
    b=db.scalar(candidate.core.select(candidate.core.BillingRecord).where(candidate.core.BillingRecord.visit_id==proc_id)); assert b
    q=db.scalar(candidate.core.select(candidate.core.OfflineQueue).where(candidate.core.OfflineQueue.operation=='visit.create',candidate.core.OfflineQueue.local_entity_id==proc_id)); assert q

g,db=local_db()
try: pr=candidate.v466_print_visit_local_first(proc_id,data=candidate._V4544PrintVisitIn(),db=db,user=User)
finally:
    try: next(g)
    except StopIteration: pass
assert pr.get('printed') is False and pr.get('reason')=='procedure_only', pr

consult=Batch(patient_id=patient_id,fecha=date.today(),tipo=None,services=[Service(procedimiento=None,valor=40.0)],observacion='REFACTOR CONSULTA',payment_method='EFECTIVO')
g,db=local_db(); result2=candidate.v466_fast_local_attention_save(consult,db=db,user=User)
try: next(g)
except StopIteration: pass
consult_id=int(result2['items'][0]['id'])
with candidate.core.LocalSessionLocal() as db:
    v=db.get(candidate.core.Visit,consult_id); assert v and not str(v.procedimiento or '').strip()
    b=db.scalar(candidate.core.select(candidate.core.BillingRecord).where(candidate.core.BillingRecord.visit_id==consult_id)); assert b

print('FLAT EQUIVALENCE OK')
print('routes', flat['route_count'], 'tables', len(flat['tables']))
print('openapi paths', flat['openapi_paths'], 'schemas', flat['openapi_schemas'], flat['openapi_sha'])
print('original historical modules', len(orig['historical_modules_loaded']), 'flat', len(flat['historical_modules_loaded']))
print('overlay js', flat['overlay_js_sha'])
