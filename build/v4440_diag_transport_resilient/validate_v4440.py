from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import types

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'updates'/'v4_4_40_diag_transport_resilient'
SRC_REF='18ad823ce89a36393fdeba1c6c1c0bd62020a077'
SRC='updates/v4_4_39_diag_transport'


def req(c,m):
    if not c: raise AssertionError(m)
def sha(b): return hashlib.sha256(b).hexdigest()
def git_bytes(path): return subprocess.check_output(['git','show',f'{SRC_REF}:{SRC}/{path}'],cwd=ROOT)
def old_launcher(): return b''.join(git_bytes(f'ABRIR_RECEPCION.part{i}') for i in range(1,5))
def new_launcher(): return b''.join((OUT/f'ABRIR_RECEPCION.part{i}').read_bytes() for i in range(1,5))

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); req(spec and spec.loader,'spec')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

class FC:
    def __init__(self): self.rows=[]; self.commits=0
    def cursor(self):
        owner=self
        class C:
            def execute(self,sql,params=None): owner.rows.append((str(sql),params))
            def close(self): pass
        return C()
    def commit(self): self.commits+=1
    def close(self): pass


def write_install(root, launcher):
    root.mkdir(parents=True,exist_ok=True); (root/'data').mkdir(exist_ok=True); (root/'.venv'/'Scripts').mkdir(parents=True,exist_ok=True)
    (root/'ABRIR_RECEPCION.py').write_bytes(launcher)
    for rel in ('app.py','app_base_4428.py','update_manifest.json'):
        (root/rel).write_bytes((OUT/rel).read_bytes())
    (root/'.env').write_text('DATABASE_URL=postgresql+pg8000://u:p%40ss@host.example/neondb?sslmode=require\n',encoding='utf-8')


def main():
    subprocess.run([sys.executable,str(ROOT/'build'/'v4440_diag_transport_resilient'/'build_v4440.py')],check=True)
    launcher=new_launcher(); text=launcher.decode('utf-8-sig'); compile(text,'ABRIR_RECEPCION.py','exec')
    c=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    req(c['version']=='4.4.40' and c['app_version']=='4.4.36','versión')
    req([x['path'] for x in c['files']]==['ABRIR_RECEPCION.py','app_base_4428.py','app.py','static/app.js','static/index.html','update_manifest.json'],'acumulativo')
    req('4.4.40-dynamic-port-dependency-diagnostics-resilient-1' in text,'launcher marker')
    for marker in ('_rp_diag_upload_via_venv','--diag-upload-file','import psycopg as _psycopg','import psycopg2 as _psycopg2','_rp_v4437_required_files','_choose_app_port'):
        req(marker in text,'falta '+marker)
    req(sha((OUT/'app.py').read_bytes())=='2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e','app cambió')
    print('V4440_STATIC_OK')

    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'i'; write_install(root,launcher); m=load(root/'ABRIR_RECEPCION.py','v4440_conn')
        req(m._rp_diag_connection_url().startswith('postgresql+pg8000://'),'no lee env')
        # Simula pg8000 averiado y psycopg disponible: debe caer al segundo driver.
        old_pg=sys.modules.get('pg8000'); old_psy=sys.modules.get('psycopg'); sentinel=FC()
        fakepg=types.ModuleType('pg8000'); fakepg.dbapi=types.SimpleNamespace(connect=lambda **kw: (_ for _ in ()).throw(RuntimeError('pg fail')))
        fakepsy=types.ModuleType('psycopg'); fakepsy.connect=lambda *a,**k: sentinel
        sys.modules['pg8000']=fakepg; sys.modules['psycopg']=fakepsy
        try:
            got=m._rp_diag_db_connect(); req(got is sentinel,'no hizo fallback driver')
        finally:
            if old_pg is None: sys.modules.pop('pg8000',None)
            else: sys.modules['pg8000']=old_pg
            if old_psy is None: sys.modules.pop('psycopg',None)
            else: sys.modules['psycopg']=old_psy
        print('MULTI_DRIVER_FALLBACK_OK')

        # Simula fallo directo: el wrapper debe usar obligatoriamente el camino .venv.
        seen=[]; m._rp_diag_upload_payload_direct=lambda p: (_ for _ in ()).throw(RuntimeError('direct'))
        m._rp_diag_upload_via_venv=lambda p: seen.append(p['incident_id'])
        m._rp_diag_upload_payload({'incident_id':'INC-TEST'})
        req(seen==['INC-TEST'],'no usó fallback .venv')
        print('VENV_FALLBACK_OK')

        # Privacidad sigue vigente.
        sample='DATABASE_URL=postgresql://u:PASS@host/db Bearer SECRET real@example.com cedula: 1207087550 IP 8.8.8.8 C:\\Users\\Consultorio\\x.py'
        clean=m._rp_diag_sanitize(sample)
        for secret in ('PASS','SECRET','real@example.com','1207087550','8.8.8.8','C:\\Users\\Consultorio'):
            req(secret not in clean,'fuga '+secret)
        print('PRIVACY_OK')

        # Cola antigua sobrevive y se vacía solo tras un envío exitoso.
        outbox,_,_=m._rp_diag_paths(); outbox.mkdir(parents=True,exist_ok=True)
        payload={'incident_id':'INC-20260901-122352-475059','created_epoch':1,'signature':'x','metadata':{}}
        q=outbox/(payload['incident_id']+'.json'); m._rp_diag_save_json(q,payload)
        m._rp_diag_upload_payload=lambda p: seen.append('sent:'+p['incident_id'])
        sent=m._rp_diag_flush_outbox(3)
        req(sent==1 and not q.exists() and 'sent:'+payload['incident_id'] in seen,'cola no reenvía')
        print('QUEUED_INCIDENT_FLUSH_OK')

        # Selftests históricos y puerto dinámico.
        sk=socket.socket(); occupied=False
        try:
            try: sk.bind(('127.0.0.1',8000)); sk.listen(1); occupied=True
            except OSError: pass
            m._set_app_port(8000); chosen=m._choose_app_port(force_new=True); req(chosen!=8000,'puerto dinámico')
        finally: sk.close()
        proc=subprocess.run([sys.executable,str(root/'ABRIR_RECEPCION.py'),'--self-test-core'],cwd=str(root),capture_output=True,text=True,timeout=150)
        print(proc.stdout,end=''); req(proc.returncode==0 and 'SELFTEST OK' in proc.stdout,'selftest launcher')
        print('PORT_AND_SELFTEST_OK',occupied)

    print('VALIDATE_V4440_OK')

if __name__=='__main__': main()
