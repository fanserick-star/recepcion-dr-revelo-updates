from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "updates" / "v4_6_6_fast_attention_save"
NEW = ROOT / "updates" / "v4_6_7_consolidated_runtime"
HIST = re.compile(r"^app_(?:base|prev|patch)_\d+$")


def offline_env(data_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "RP_DATA_DIR": str(data_dir),
        "RP_FORCE_OFFLINE": "1",
        "DATABASE_URL": "",
        "NEON_DATABASE_URL": "",
        "HISTORIA_DATABASE_URL": "",
        "REMOTE_AGENDA_AUTOSTART": "0",
        "WHATSAPP_ENABLED": "0",
        "PYTHONIOENCODING": "utf-8",
    })
    return env


PROBE = r'''
import hashlib, json, os, re, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, os.getcwd())
import app
core = app.core
core.Base.metadata.create_all(core.local_engine)
routes=[]
for r in app.app.router.routes:
    routes.append((getattr(r,'path',None), sorted(getattr(r,'methods',set()) or set()), getattr(getattr(r,'endpoint',None),'__name__',None)))
tables=[]
for name, table in sorted(core.Base.metadata.tables.items()):
    tables.append((name, [(c.name,str(c.type),bool(c.nullable),bool(c.primary_key)) for c in table.columns]))
schema=app.app.openapi()
if isinstance(schema.get('info'),dict):
    schema=dict(schema); info=dict(schema['info']); info.pop('version',None); schema['info']=info
blob=json.dumps(schema,ensure_ascii=False,sort_keys=True,separators=(',',':'))
endpoint_versions=[]
for r in app.app.router.routes:
    fn=getattr(r,'endpoint',None)
    if not hasattr(fn,'__globals__'): continue
    if 'APP_VERSION' in getattr(fn,'__code__',()).co_names and 'APP_VERSION' in fn.__globals__:
        endpoint_versions.append(str(fn.__globals__['APP_VERSION']))
try:
    with core.LocalSessionLocal() as db:
        empty=core.billing_group_records(db,987654321,date(2026,1,1))
except RecursionError:
    empty='RecursionError'
out={
 'version':str(getattr(app,'APP_VERSION','')),
 'routes':routes,
 'tables':tables,
 'overlay_js':hashlib.sha256(str(getattr(core,'V460_OVERLAY_JS','')).encode()).hexdigest(),
 'overlay_css':hashlib.sha256(str(getattr(core,'V460_OVERLAY_CSS','')).encode()).hexdigest(),
 'openapi':hashlib.sha256(blob.encode()).hexdigest(),
 'openapi_paths':len(schema.get('paths') or {}),
 'openapi_schemas':len(((schema.get('components') or {}).get('schemas') or {})),
 'historical':sorted(k for k in sys.modules if re.match(r'^app_(?:base|prev|patch)_\d+$',k)),
 'endpoint_versions':endpoint_versions,
 'empty_billing_group':empty,
}
Path(os.environ['PROBE_OUT']).write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
'''


def probe(runtime: Path, label: str) -> dict:
    root = Path(tempfile.mkdtemp(prefix=f"rp467-{label}-"))
    try:
        out = root / "probe.json"
        env = offline_env(root / "data")
        env["PROBE_OUT"] = str(out)
        p = subprocess.run([sys.executable, "-c", PROBE], cwd=runtime, env=env, text=True, capture_output=True, timeout=90)
        if p.returncode:
            raise RuntimeError(f"{label} probe failed\n{p.stdout}\n{p.stderr}")
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def structural_gate() -> None:
    manifest = json.loads((NEW / "update_manifest.json").read_text(encoding="utf-8-sig"))
    payload = [str(x).replace("\\", "/") for x in manifest["copy"]]
    assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == "4.6.7"
    assert manifest["notes"]["previous_version"] == "4.6.6"
    assert manifest["notes"]["external_patch_chain_required"] is False
    assert len(payload) == len(set(payload))
    problems=[]
    for rel in payload:
        path=NEW/rel
        assert path.is_file(), rel
        if not rel.endswith('.py'): continue
        text=path.read_text(encoding='utf-8-sig')
        tree=ast.parse(text,filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:
                    if HIST.match(alias.name): problems.append(f'{rel}: import {alias.name}')
                    if alias.name=='runtime_registry': problems.append(f'{rel}: imports runtime_registry')
            elif isinstance(node,ast.ImportFrom):
                name=node.module or ''
                if HIST.match(name): problems.append(f'{rel}: from {name}')
                if name=='runtime_registry': problems.append(f'{rel}: imports runtime_registry')
            elif isinstance(node,ast.Name) and node.id in {'_rf_layers','_rf_legacy','_rf_module_lookup'}:
                problems.append(f'{rel}: {node.id}')
        if path.name!='runtime_registry.py' and ('getattr(_mod, \'previous\'' in text or 'getattr(_mod, "previous"' in text):
            problems.append(f'{rel}: previous chain walk')
    assert not problems, problems[:40]


def functional_flow() -> None:
    code = r'''
import os,sys,tempfile
from datetime import date, datetime
sys.path.insert(0,os.getcwd())
import app
from reception_payment_terminal import V4504VisitBatchPaymentIn
core=app.core
core.Base.metadata.create_all(core.local_engine)
assert app.APP_VERSION=='4.6.7'

def kwargs():
    out={}
    for col in core.Patient.__table__.columns:
        if col.primary_key or col.nullable or col.default is not None or col.server_default is not None: continue
        typ=type(col.type).__name__.lower(); name=col.name
        if name=='nombre': value='PACIENTE RELEASE 467'
        elif 'date' in typ and 'time' not in typ: value=date(1990,1,1)
        elif 'datetime' in typ: value=datetime.utcnow()
        elif 'int' in typ: value=0
        elif 'numeric' in typ or 'float' in typ: value=0
        else: value='REL467'
        out[name]=value
    return out
with core.LocalSessionLocal() as db:
    p=core.Patient(**kwargs())
    if hasattr(p,'cedula'): p.cedula='REL467'
    db.add(p); db.commit(); db.refresh(p); pid=int(p.id)
User=type('U',(),{'username':'release-test'})()
Service=core.VisitBatchServiceIn
Batch=V4504VisitBatchPaymentIn

def local_db():
    g=app._v466_local_attention_db(); db=next(g); return g,db
proc=Batch(patient_id=pid,fecha=date.today(),tipo=None,services=[Service(procedimiento='INSTILACION',valor=80.0)],observacion='REL467',payment_method='EFECTIVO')
g,db=local_db(); result=app.v466_fast_local_attention_save(proc,db=db,user=User)
try: next(g)
except StopIteration: pass
vid=int(result['items'][0]['id'])
with core.LocalSessionLocal() as db:
    assert db.get(core.Visit,vid)
    assert db.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id==vid))
    assert db.scalar(core.select(core.OfflineQueue).where(core.OfflineQueue.operation=='visit.create',core.OfflineQueue.local_entity_id==vid))
g,db=local_db()
try: pr=app.v466_print_visit_local_first(vid,data=app._V4544PrintVisitIn(),db=db,user=User)
finally:
    try: next(g)
    except StopIteration: pass
assert pr.get('printed') is False and pr.get('reason')=='procedure_only',pr
consult=Batch(patient_id=pid,fecha=date.today(),tipo=None,services=[Service(procedimiento=None,valor=40.0)],observacion='REL467 CONSULTA',payment_method='EFECTIVO')
g,db=local_db(); r2=app.v466_fast_local_attention_save(consult,db=db,user=User)
try: next(g)
except StopIteration: pass
cid=int(r2['items'][0]['id'])
with core.LocalSessionLocal() as db:
    v=db.get(core.Visit,cid); assert v and not str(v.procedimiento or '').strip()
    assert db.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id==cid))
print('FUNCTIONAL FLOW OK')
'''
    root=Path(tempfile.mkdtemp(prefix='rp467-functional-'))
    try:
        p=subprocess.run([sys.executable,'-c',code],cwd=NEW,env=offline_env(root/'data'),text=True,capture_output=True,timeout=90)
        if p.returncode: raise RuntimeError(p.stdout+p.stderr)
        print(p.stdout.strip())
    finally: shutil.rmtree(root,ignore_errors=True)


def import_probe(runtime: Path, expected: str) -> None:
    root=Path(tempfile.mkdtemp(prefix='rp467-import-'))
    try:
        code="import sys,os;sys.path.insert(0,os.getcwd());import app;print(app.APP_VERSION);print(len(app.app.router.routes))"
        p=subprocess.run([sys.executable,'-c',code],cwd=runtime,env=offline_env(root/'data'),text=True,capture_output=True,timeout=90)
        if p.returncode: raise RuntimeError(p.stdout+p.stderr)
        lines=[x.strip() for x in p.stdout.splitlines() if x.strip()]
        assert expected in lines and '243' in lines, lines
    finally: shutil.rmtree(root,ignore_errors=True)


def packaged_staging() -> None:
    manifest=json.loads((NEW/'update_manifest.json').read_text(encoding='utf-8-sig'))
    stage=Path(tempfile.mkdtemp(prefix='rp467-stage-'))
    try:
        for rel in manifest['copy']:
            src=NEW/rel; dst=stage/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        import_probe(stage,'4.6.7')
        assert not any(p.name.startswith(('app_patch_','app_prev_','app_base_')) for p in stage.glob('*.py'))
    finally: shutil.rmtree(stage,ignore_errors=True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_rollback() -> None:
    manifest=json.loads((NEW/'update_manifest.json').read_text(encoding='utf-8-sig'))
    payload=[str(x).replace('\\','/') for x in manifest['copy']]
    old_payload=['app.py','recepcion-version.json','update_manifest.json','static/runtime_keep.txt','historia_bridge.py','historia_lan_transport.py']
    install=Path(tempfile.mkdtemp(prefix='rp467-install-')); backup=Path(tempfile.mkdtemp(prefix='rp467-backup-'))
    try:
        def cp(src,dst): dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        for rel in old_payload: cp(OLD/rel,install/rel)
        protected={'.env':b'SECRET=keep\n','BASE DE DATOS 2026.xlsx':b'keep-excel','backups/keep.txt':b'keep-backup'}
        for rel,data in protected.items(): p=install/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
        dbp=install/'data/recepcion.db'; dbp.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(dbp) as c: c.execute('create table sentinel(id integer primary key,value text)'); c.execute("insert into sentinel(value) values('keep')"); c.commit()
        protected_paths=list(protected)+['data/recepcion.db']; protected_hash={r:sha(install/r) for r in protected_paths}
        baseline={r:sha(install/r) for r in old_payload}
        entries=[]
        for rel in payload:
            cur=install/rel; existed=cur.is_file(); entries.append((rel,existed))
            if existed: cp(cur,backup/rel)
        for rel in payload:
            dest=install/rel; dest.parent.mkdir(parents=True,exist_ok=True); tmp=dest.with_name(dest.name+'.new'); shutil.copy2(NEW/rel,tmp); os.replace(tmp,dest)
        import_probe(install,'4.6.7')
        for r,h in protected_hash.items(): assert sha(install/r)==h,r
        for rel,existed in entries:
            dest=install/rel; src=backup/rel
            if existed: cp(src,dest)
            elif dest.exists(): dest.unlink()
        for r,h in baseline.items(): assert sha(install/r)==h,r
        for r,h in protected_hash.items(): assert sha(install/r)==h,r
        assert not [r for r in set(payload)-set(old_payload) if (install/r).exists()]
        import_probe(install,'4.6.6')
    finally:
        shutil.rmtree(install,ignore_errors=True); shutil.rmtree(backup,ignore_errors=True)


def main() -> None:
    structural_gate()
    old=probe(OLD,'old'); new=probe(NEW,'new')
    assert old['version']=='4.6.6' and new['version']=='4.6.7',(old['version'],new['version'])
    assert old['routes']==new['routes']
    assert old['tables']==new['tables']
    assert old['overlay_js']==new['overlay_js'] and old['overlay_css']==new['overlay_css']
    assert old['openapi']==new['openapi'],(old['openapi'],new['openapi'])
    assert new['openapi_paths']==220 and new['openapi_schemas']==36
    assert new['historical']==[]
    assert new['empty_billing_group']==[]
    assert new['endpoint_versions'] and set(new['endpoint_versions'])=={'4.6.7'},set(new['endpoint_versions'])
    functional_flow()
    packaged_staging()
    update_rollback()
    print('RECEPTION 4.6.7 RELEASE VERIFIED')
    print('routes',len(new['routes']),'tables',len(new['tables']),'openapi',new['openapi_paths'],new['openapi_schemas'])
    print('historical modules',len(new['historical']),'endpoint versions',len(new['endpoint_versions']))
    print('upgrade 4.6.6 -> 4.6.7 -> rollback 4.6.6 OK')


if __name__=='__main__':
    main()
