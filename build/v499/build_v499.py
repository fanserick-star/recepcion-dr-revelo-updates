from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v498'
OUT=ROOT/'updates'/'v499'
VERSION='4.3.99'
LAUNCHER_VERSION='4.3.99-standalone-6'


def joined(prefix,n):
    ps=sorted(SRC.glob(prefix+'*'),key=lambda p:int(p.name.replace(prefix,'')))
    if len(ps)!=n: raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(ps)}')
    return ''.join(p.read_text(encoding='utf-8') for p in ps)


def sha(b): return hashlib.sha256(b).hexdigest()


def write_parts(text,prefix,n):
    OUT.mkdir(parents=True,exist_ok=True)
    for p in OUT.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/n); names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names)!=text:
        raise SystemExit('reconstruccion invalida '+prefix)
    return names


def replace_once(text,old,new,label):
    c=text.count(old)
    if c!=1: raise SystemExit(f'{label}: esperaba 1 coincidencia y encontro {c}')
    return text.replace(old,new,1)


def patch_app(s):
    s=replace_once(s,'APP_VERSION = "4.3.98"','APP_VERSION = "4.3.99"','version backend')
    s=replace_once(s,"const VERSION=\\'4.3.98\\';","const VERSION=\\'4.3.99\\';",'version visual')
    compile(s,'app.py','exec')
    for token in ['APP_VERSION = "4.3.99"','V497_ATTENTION_JS','button.service-card[data-service]','v497-native-consult','_POSTGRES_DRIVER = "pg8000"','Revisando AZUR','Emitir por lotes']:
        if token not in s: raise SystemExit('falta '+token)
    return s


def patch_launcher(s):
    s=replace_once(s,'LAUNCHER_VERSION = "4.3.98-standalone-5"','LAUNCHER_VERSION = "4.3.99-standalone-6"','version launcher')

    # Agrega diagnóstico explícito para la colisión del puerto en PCs reales.
    old_start='''def _start_server() -> None:\n    if os.name == "nt" and _port_8000_pids():\n        _stop_server()\n'''
    new_start='''def _start_server() -> None:\n    if os.name == "nt":\n        before = _port_8000_pids()\n        if before:\n            _log("Puerto 8000 ocupado antes de iniciar; PID=" + ",".join(map(str, before)))\n            _stop_server()\n        after = _port_8000_pids()\n        if after:\n            _log("Puerto 8000 todavía ocupado después de cierre; PID=" + ",".join(map(str, after)))\n'''
    s=replace_once(s,old_start,new_start,'diagnostico start server')

    helper='''def _relaunch_updated_launcher() -> None:\n    """Abre el launcher recién escrito en disco y deja terminar el proceso viejo."""\n    py = _python_exe(windowless=True)\n    env = os.environ.copy()\n    flags = _hidden_flags()\n    if os.name == "nt":\n        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)\n    subprocess.Popen(\n        [str(py), str(ROOT / "ABRIR_RECEPCION.py")],\n        cwd=str(ROOT),\n        env=env,\n        stdin=subprocess.DEVNULL,\n        stdout=subprocess.DEVNULL,\n        stderr=subprocess.DEVNULL,\n        creationflags=flags,\n        close_fds=True,\n    )\n\n\n'''
    marker='def main() -> None:\n'
    if s.count(marker)!=1: raise SystemExit('main inesperado')
    s=s.replace(marker,helper+marker,1)

    old='''        if result.get("blocked"):\n            splash.close()\n            _message(result.get("error") or "La instalación local necesita reparación.")\n            return\n\n        if result.get("updated"):\n'''
    new='''        if result.get("blocked"):\n            splash.close()\n            _message(result.get("error") or "La instalación local necesita reparación.")\n            return\n\n        updated_paths = {str(p).replace("\\\\", "/").lower() for p in result.get("paths", [])}\n        if result.get("updated") and "abrir_recepcion.py" in updated_paths:\n            # El archivo del launcher ya cambió en disco, pero este proceso sigue\n            # ejecutando el código anterior en memoria. Soltamos el mutex y abrimos\n            # inmediatamente la copia recién instalada para que el fix sea efectivo\n            # en este mismo intento.\n            splash.set("Aplicando lanzador nuevo…", f"Versión {result.get('version') or ''}")\n            splash.close()\n            _release_mutex(handle)\n            handle = None\n            _relaunch_updated_launcher()\n            return\n\n        if result.get("updated"):\n'''
    s=replace_once(s,old,new,'relaunch inmediato tras update launcher')

    compile(s,'ABRIR_RECEPCION.py','exec')
    for token in ['LAUNCHER_VERSION = "4.3.99-standalone-6"','def _relaunch_updated_launcher()','updated_paths','"abrir_recepcion.py" in updated_paths','_release_mutex(handle)','handle = None','Puerto 8000 ocupado antes de iniciar','def _port_8000_pids()']:
        if token not in s: raise SystemExit('launcher falta '+token)
    return s


def main():
    app=patch_app(joined('app.part',7)); launcher=patch_launcher(joined('ABRIR_RECEPCION.part',4))
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    index= (SRC/'static'/'index.html').read_text(encoding='utf-8')
    index_target=OUT/'static'/'index.html';index_target.parent.mkdir(parents=True,exist_ok=True);index_target.write_text(index,encoding='utf-8',newline='')
    ab=app.encode(); lb=launcher.encode(); ib=index.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v499/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.99: al actualizar el launcher, reinicia inmediatamente con el código nuevo y conserva la liberación robusta del puerto 8000.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb))

if __name__=='__main__': main()
