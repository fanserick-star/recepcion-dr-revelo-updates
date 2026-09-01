from __future__ import annotations

import hashlib, importlib.util, json, pathlib, socket, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'updates'/'v4_4_37_dependency_guard'
LAUNCHER_REF='5661754088197cafc7a9381156c193f22130ced7'
LAUNCHER_PREFIX='updates/v4_4_32_launcher_port_patch'

def require(c,m):
    if not c: raise AssertionError(m)
def sha(b): return hashlib.sha256(b).hexdigest()
def git_bytes(ref,path): return subprocess.check_output(['git','show',f'{ref}:{path}'],cwd=ROOT)
def old_launcher_bytes(): return b''.join(git_bytes(LAUNCHER_REF,f'{LAUNCHER_PREFIX}/ABRIR_RECEPCION.part{i}') for i in range(1,5))
def new_launcher_bytes(): return b''.join((OUT/f'ABRIR_RECEPCION.part{i}').read_bytes() for i in range(1,5))

class H(BaseHTTPRequestHandler):
    files={}
    def do_GET(self):
        item=self.files.get(self.path.split('?',1)[0])
        if not item:self.send_response(404);self.end_headers();return
        b,t=item;self.send_response(200);self.send_header('Content-Type',t);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*_):pass

def server(files=None):
    H.files=files or {};s=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=s.serve_forever,daemon=True).start();return s,f'http://127.0.0.1:{s.server_address[1]}'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);require(spec and spec.loader,f'No carga {path}');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def payloads():
    c=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    p={'ABRIR_RECEPCION.py':new_launcher_bytes(),'app_base_4428.py':(OUT/'app_base_4428.py').read_bytes(),'app.py':(OUT/'app.py').read_bytes(),
       'static/app.js':(OUT/'static'/'app.js').read_bytes(),'static/index.html':(OUT/'static'/'index.html').read_bytes(),'update_manifest.json':(OUT/'update_manifest.json').read_bytes()}
    for x in c['files']:require(sha(p[x['path']])==x['sha256'],f"SHA local {x['path']}")
    return c,p

def served(c,p):
    s,b=server();remote={k:v for k,v in c.items() if k!='files'};remote['files']=[]
    files={'/manifest':(b'','application/json')}
    for i,x in enumerate(c['files']):
        remote['files'].append({'path':x['path'],'url':f'{b}/p/{i}','sha256':sha(p[x['path']]),'encoding':'utf-8'});files[f'/p/{i}']=(p[x['path']],'application/octet-stream')
    files['/manifest']=(json.dumps(remote).encode(),'application/json');H.files=files;return s,b

def broken_root():
    root=pathlib.Path(tempfile.mkdtemp(prefix='rp4437-'))/'install';root.mkdir()
    (root/'app.py').write_bytes((OUT/'app.py').read_bytes());(root/'ABRIR_RECEPCION.py').write_bytes(old_launcher_bytes())
    local={'product':'recepcion-pacientes','version':'4.4.36','app_version':'4.4.36','runtime_version':'4.4.36','copy':['app.py','update_manifest.json']}
    (root/'update_manifest.json').write_text(json.dumps(local,indent=2)+'\n',encoding='utf-8')
    (root/'static').mkdir();(root/'static'/'app.js').write_text('OLD',encoding='utf-8');(root/'static'/'index.html').write_text('OLD',encoding='utf-8')
    (root/'.env').write_text('KEEP_ENV=YES\n',encoding='utf-8');(root/'data').mkdir();(root/'data'/'keep.txt').write_text('KEEP_DATA',encoding='utf-8');(root/'.venv').mkdir();(root/'.venv'/'keep.txt').write_text('KEEP_VENV',encoding='utf-8')
    require(not (root/'app_base_4428.py').exists(),'Fixture debe carecer de base');return root

def direct_jump(c,p):
    root=broken_root();s,b=served(c,p)
    try:
        old=load(root/'ABRIR_RECEPCION.py','old4432');r=old.check_and_apply_update(root,b+'/manifest',attempts=1,timeout=3,allow_test_sources=True)
        require(r.get('ok') and r.get('updated'),f'No reparó salto: {r}');require((root/'app_base_4428.py').is_file(),'No repuso base')
        require(sha((root/'app_base_4428.py').read_bytes())=='e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba','Base incorrecta')
        require((root/'.env').read_text()=='KEEP_ENV=YES\n' and (root/'data'/'keep.txt').read_text()=='KEEP_DATA' and (root/'.venv'/'keep.txt').read_text()=='KEEP_VENV','Tocó protegidos')
        m=json.loads((root/'update_manifest.json').read_text());require(m['version']=='4.4.37' and m['app_version']=='4.4.36','Manifest final malo')
        compile((root/'app.py').read_text(encoding='utf-8-sig'),'app.py','exec');compile((root/'app_base_4428.py').read_text(encoding='utf-8-sig'),'base.py','exec')
        print('CONSULTORIO_BROKEN_JUMP_REPAIR_OK')
    finally:s.shutdown();s.server_close()
    return root

def same_version(root,c,p):
    g=load(root/'ABRIR_RECEPCION.py','guard4437');require(g._installation_consistent(root),'Inicio reparado incoherente')
    for mode in ('missing','corrupt'):
        if mode=='missing':(root/'app_base_4428.py').unlink()
        else:(root/'app_base_4428.py').write_text('def broken(:\n',encoding='utf-8')
        require(not g._installation_consistent(root),f'No detectó {mode}');s,b=served(c,p)
        try:
            r=g.check_and_apply_update(root,b+'/manifest',attempts=1,timeout=3,allow_test_sources=True);require(r.get('ok') and r.get('updated'),f'No autoreparó {mode}: {r}')
            require(g._installation_consistent(root),f'No quedó coherente {mode}');require(sha((root/'app_base_4428.py').read_bytes())=='e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba','SHA base reparada malo')
            print('SAME_VERSION_SELF_REPAIR_OK',mode)
        finally:s.shutdown();s.server_close()

def reject_future(root):
    g=load(root/'ABRIR_RECEPCION.py','reject4437');oa=(root/'app.py').read_bytes();om=(root/'update_manifest.json').read_bytes()
    app=b'APP_VERSION = "4.4.38"\nimport app_missing_future\n';inner=(json.dumps({'product':'recepcion-pacientes','version':'4.4.38','app_version':'4.4.38','runtime_version':'4.4.38','copy':['app.py','update_manifest.json']},indent=2)+'\n').encode()
    s,b=server();remote={'product':'recepcion-pacientes','version':'4.4.38','app_version':'4.4.38','runtime_version':'4.4.38','files':[{'path':'app.py','url':b+'/app','sha256':sha(app),'encoding':'utf-8'},{'path':'update_manifest.json','url':b+'/inner','sha256':sha(inner),'encoding':'utf-8'}]};H.files={'/manifest':(json.dumps(remote).encode(),'application/json'),'/app':(app,'text/plain'),'/inner':(inner,'application/json')}
    try:
        r=g.check_and_apply_update(root,b+'/manifest',attempts=1,timeout=3,allow_test_sources=True);require(r.get('ok') and r.get('deferred'),f'No rechazó seguro: {r}')
        require((root/'app.py').read_bytes()==oa and (root/'update_manifest.json').read_bytes()==om,'Tocó instalación al rechazar');require(g._installation_consistent(root),'Quedó incoherente')
        print('FUTURE_MISSING_DEP_BLOCKED_PRE_SWAP_OK')
    finally:s.shutdown();s.server_close()

def port_test(root):
    g=load(root/'ABRIR_RECEPCION.py','port4437');require(g.LAUNCHER_VERSION=='4.4.32-dynamic-port-patch-1','Cambió launcher base')
    sk=socket.socket();occupied=False
    try:
        try:sk.bind(('127.0.0.1',8000));sk.listen(1);occupied=True
        except OSError:pass
        g._set_app_port(8000);chosen=g._choose_app_port(force_new=True);require(chosen!=8000 and 1024<=chosen<=65535,f'Puerto malo {chosen}');print('DYNAMIC_PORT_PRESERVED_OK',chosen,occupied)
    finally:sk.close()
def selftest(root):
    r=subprocess.run([sys.executable,str(root/'ABRIR_RECEPCION.py'),'--self-test-core'],cwd=str(root),capture_output=True,text=True,timeout=120);print(r.stdout,end='');
    if r.returncode:print(r.stderr,end='')
    require(r.returncode==0 and 'SELFTEST OK' in r.stdout,f'Selftest falló {r.returncode}');print('LAUNCHER_SELFTEST_OK')

def main():
    subprocess.run([sys.executable,str(ROOT/'build'/'v4437_dependency_guard'/'build_v4437_v3.py')],check=True)
    c,p=payloads();req=['ABRIR_RECEPCION.py','app_base_4428.py','app.py','static/app.js','static/index.html','update_manifest.json'];require([x['path'] for x in c['files']]==req,'No acumulativo')
    require(c['app_version']=='4.4.36' and sha(p['app.py'])=='2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e','App incorrecta');require(sha(p['app_base_4428.py'])=='e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba','Base incorrecta');print('PINNED_RELEASE_CONTRACT_OK')
    root=direct_jump(c,p);same_version(root,c,p);reject_future(root);port_test(root);selftest(root);print('VALIDATE_V4437_V3_OK')
if __name__=='__main__':main()
