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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_39_diag_transport"
SRC_REF = "953ab521d95e6ca3aa0bc65aba1ddc02100fa4cd"
SRC = "updates/v4_4_38_auto_diagnostics"


def require(c, m):
    if not c:
        raise AssertionError(m)


def sha(b): return hashlib.sha256(b).hexdigest()
def git_bytes(path): return subprocess.check_output(["git", "show", f"{SRC_REF}:{SRC}/{path}"], cwd=ROOT)
def old_launcher(): return b"".join(git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1,5))
def new_launcher(): return b"".join((OUT/f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1,5))


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path); require(spec and spec.loader,f"No carga {path}")
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class FakeCursor:
    def __init__(self, owner): self.owner=owner
    def execute(self, sql, params=None):
        self.owner.calls.append((str(sql),params))
        if "INSERT INTO rp_diagnostics_incidents" in str(sql): self.owner.inserts.append(params)
    def close(self): pass

class FakeConn:
    def __init__(self): self.calls=[]; self.inserts=[]; self.commits=0
    def cursor(self): return FakeCursor(self)
    def commit(self): self.commits+=1
    def close(self): pass


class H(BaseHTTPRequestHandler):
    files={}
    def do_GET(self):
        item=self.files.get(self.path.split('?',1)[0])
        if not item: self.send_response(404); self.end_headers(); return
        body,ctype=item; self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*_): pass

def server(files=None):
    H.files=files or {}; s=ThreadingHTTPServer(('127.0.0.1',0),H); threading.Thread(target=s.serve_forever,daemon=True).start(); return s,f"http://127.0.0.1:{s.server_address[1]}"


def payloads():
    c=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    p={'ABRIR_RECEPCION.py':new_launcher(),'app_base_4428.py':(OUT/'app_base_4428.py').read_bytes(),'app.py':(OUT/'app.py').read_bytes(),'static/app.js':(OUT/'static'/'app.js').read_bytes(),'static/index.html':(OUT/'static'/'index.html').read_bytes(),'update_manifest.json':(OUT/'update_manifest.json').read_bytes()}
    for x in c['files']: require(sha(p[x['path']])==x['sha256'],f"SHA candidato {x['path']}")
    return c,p


def served(c,p):
    s,b=server(); remote={k:v for k,v in c.items() if k!='files'}; remote['files']=[]; files={}
    for i,x in enumerate(c['files']):
        remote['files'].append({'path':x['path'],'url':f'{b}/p/{i}','sha256':sha(p[x['path']]),'encoding':'utf-8'})
        files[f'/p/{i}']=(p[x['path']],'application/octet-stream')
    files['/manifest']=(json.dumps(remote).encode(),'application/json'); H.files=files; return s,b


def write_source_install(root):
    root.mkdir(parents=True)
    (root/'ABRIR_RECEPCION.py').write_bytes(old_launcher())
    for rel in ('app_base_4428.py','app.py','update_manifest.json'):
        (root/rel).write_bytes(git_bytes(rel))
    (root/'static').mkdir(); (root/'static'/'app.js').write_bytes(git_bytes('static/app.js')); (root/'static'/'index.html').write_bytes(git_bytes('static/index.html'))
    (root/'data').mkdir(); (root/'.venv').mkdir()
    (root/'data'/'keep.txt').write_text('KEEP_DATA',encoding='utf-8'); (root/'.venv'/'keep.txt').write_text('KEEP_VENV',encoding='utf-8')
    (root/'.env').write_text('DATABASE_URL=postgresql+pg8000://diag_user:DIAG_SECRET@ep-example.neon.tech/neondb?sslmode=require\nKEEP_ENV=YES\n',encoding='utf-8')


def static_contract(c,p):
    require(c['version']=='4.4.39' and c['app_version']=='4.4.36','Versión incorrecta')
    expected=['ABRIR_RECEPCION.py','app_base_4428.py','app.py','static/app.js','static/index.html','update_manifest.json']
    require([x['path'] for x in c['files']]==expected,'No acumulativo')
    require(sha(p['app.py'])=='2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e','app.py cambió')
    require(sha(p['app_base_4428.py'])=='e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba','base cambió')
    text=p['ABRIR_RECEPCION.py'].decode('utf-8-sig'); compile(text,'ABRIR_RECEPCION.py','exec')
    markers=['4.4.39-dynamic-port-dependency-diagnostics-transport-1','postgresql+pg8000','postgresql+psycopg','_rp_diag_flush_outbox','_rp_v4437_required_files','_choose_app_port','privacy filter revision 2']
    require(all(x in text for x in markers),'Faltan contratos previos/nuevos')
    require('application_name="recepcion-diagnostics"' not in text,'Persistió application_name')
    require('Se enviará automáticamente cuando haya conexión.' not in text,'Persistió mensaje engañoso')
    require('se reintentará automáticamente en el próximo arranque' in text,'Falta nuevo mensaje')
    print('V4439_STATIC_CONTRACT_OK')


def connection_compat(p):
    import pg8000.dbapi as dbapi
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'install'; root.mkdir(); (root/'ABRIR_RECEPCION.py').write_bytes(p['ABRIR_RECEPCION.py']); (root/'data').mkdir()
        m=load(root/'ABRIR_RECEPCION.py','v4439_conn')
        old=dbapi.connect; seen=[]
        try:
            dbapi.connect=lambda **kw:(seen.append(kw) or kw)
            old_env=os.environ.pop('DATABASE_URL',None); old_neon=os.environ.pop('NEON_DATABASE_URL',None)
            try:
                variants=['postgresql+pg8000://u:p%40ss@host.example/neondb?sslmode=require','postgresql+psycopg://u:p%40ss@host.example/neondb','postgresql://u:p%40ss@host.example:5433/db2']
                for idx,url in enumerate(variants):
                    (root/'.env').write_text('DATABASE_URL='+url+'\n',encoding='utf-8'); m._rp_diag_db_connect()
                    kw=seen[-1]; require(kw['user']=='u' and kw['password']=='p@ss' and kw['host']=='host.example','Parse credenciales/host malo')
                    require(kw['timeout']==12 and 'ssl_context' in kw,'Timeout/SSL no conservador')
                    require('application_name' not in kw,'Se envió application_name')
                    if idx==2: require(kw['port']==5433 and kw['database']=='db2','Puerto/db explícito malo')
                print('NEON_URL_COMPAT_AND_SAFE_ARGS_OK')
            finally:
                if old_env is not None: os.environ['DATABASE_URL']=old_env
                if old_neon is not None: os.environ['NEON_DATABASE_URL']=old_neon
        finally: dbapi.connect=old


def privacy_test(p):
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'install'; root.mkdir(); (root/'ABRIR_RECEPCION.py').write_bytes(p['ABRIR_RECEPCION.py']); (root/'app.py').write_bytes(p['app.py']); (root/'app_base_4428.py').write_bytes(p['app_base_4428.py']); (root/'update_manifest.json').write_bytes(p['update_manifest.json']); (root/'data').mkdir()
        (root/'data'/'launcher_errors.log').write_text('DATABASE_URL=postgresql://u:PASS_X@host/db token=TOKEN_X correo: real@example.com cedula: 1207087550 IP 8.8.8.8\n',encoding='utf-8')
        (root/'data'/'backend_startup.log').write_text('Bearer BEARER_X telefono: 0989286631 C:\\Users\\Consultorio\\x.py\n',encoding='utf-8')
        m=load(root/'ABRIR_RECEPCION.py','v4439_priv'); fake=FakeConn(); m._rp_diag_db_connect=lambda:fake
        r=m._rp_diag_report('launcher_fatal',RuntimeError('correo admin@example.com token=EXC_TOKEN 1712345678'))
        require(r.get('status')=='sent' and len(fake.inserts)==1,'No envió fake')
        s=json.dumps(fake.inserts,ensure_ascii=False,default=str)
        forbidden=['PASS_X','TOKEN_X','real@example.com','1207087550','8.8.8.8','BEARER_X','0989286631','C:\\Users\\Consultorio','admin@example.com','EXC_TOKEN','1712345678']
        require(not [x for x in forbidden if x in s],'Regresión de privacidad')
        print('V4439_PRIVACY_OK')


def queued_incident_survives_update(c,p):
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'install'; write_source_install(root)
        env_before=(root/'.env').read_bytes(); keep_before=(root/'data'/'keep.txt').read_bytes(); venv_before=(root/'.venv'/'keep.txt').read_bytes()
        old=load(root/'ABRIR_RECEPCION.py','v4438_old_queue')
        old._rp_diag_db_connect=lambda: (_ for _ in ()).throw(OSError('transport failed'))
        (root/'data'/'launcher_errors.log').write_text('fatal synthetic\n',encoding='utf-8'); (root/'data'/'backend_startup.log').write_text('trace synthetic\n',encoding='utf-8')
        q=old._rp_diag_report('launcher_fatal',RuntimeError('backend synthetic'))
        require(q.get('status')=='queued','4.4.38 fixture no creó cola')
        outbox=root/'data'/'diagnostic_outbox'; files=list(outbox.glob('INC-*.json')); require(len(files)==1,'Cola fixture inválida')
        queued_name=files[0].name; queued_bytes=files[0].read_bytes()
        s,b=served(c,p)
        try:
            result=old.check_and_apply_update(root,b+'/manifest',attempts=1,timeout=3,allow_test_sources=True)
            require(result.get('ok') and result.get('updated'),f'No actualizó 4.4.38->39: {result}')
        finally: s.shutdown(); s.server_close()
        require((root/'.env').read_bytes()==env_before,'Tocó .env')
        require((root/'data'/'keep.txt').read_bytes()==keep_before,'Tocó data existente')
        require((root/'.venv'/'keep.txt').read_bytes()==venv_before,'Tocó .venv')
        qpath=outbox/queued_name; require(qpath.is_file() and qpath.read_bytes()==queued_bytes,'Perdió/modificó INC pendiente')
        new=load(root/'ABRIR_RECEPCION.py','v4439_new_flush'); fake=FakeConn(); new._rp_diag_db_connect=lambda:fake
        sent=new._rp_diag_flush_outbox(max_items=3)
        require(sent==1 and len(fake.inserts)==1 and not qpath.exists(),'Nuevo launcher no reenvió cola')
        print('QUEUED_INCIDENT_SURVIVES_UPDATE_AND_FLUSHES_OK',q.get('incident_id'))


def ports_and_selftest(p):
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'install'; root.mkdir(); (root/'ABRIR_RECEPCION.py').write_bytes(p['ABRIR_RECEPCION.py']); (root/'app.py').write_bytes(p['app.py']); (root/'app_base_4428.py').write_bytes(p['app_base_4428.py']); (root/'update_manifest.json').write_bytes(p['update_manifest.json']); (root/'data').mkdir()
        m=load(root/'ABRIR_RECEPCION.py','v4439_port')
        sk=socket.socket(); occupied=False
        try:
            try: sk.bind(('127.0.0.1',8000)); sk.listen(1); occupied=True
            except OSError: pass
            m._set_app_port(8000); chosen=m._choose_app_port(force_new=True); require(chosen!=8000 and 1024<=chosen<=65535,'Puerto dinámico roto')
        finally: sk.close()
        proc=subprocess.run([sys.executable,str(root/'ABRIR_RECEPCION.py'),'--self-test-core'],cwd=str(root),capture_output=True,text=True,timeout=140)
        print(proc.stdout,end='');
        if proc.returncode: print(proc.stderr,end='')
        require(proc.returncode==0 and 'SELFTEST OK' in proc.stdout,'Selftest histórico falló')
        print('DYNAMIC_PORT_AND_LAUNCHER_SELFTEST_OK',occupied)


def main():
    subprocess.run([sys.executable,str(ROOT/'build'/'v4439_diag_transport'/'build_v4439.py')],check=True)
    c,p=payloads(); static_contract(c,p); connection_compat(p); privacy_test(p); queued_incident_survives_update(c,p); ports_and_selftest(p); print('VALIDATE_V4439_OK')

if __name__=='__main__': main()
