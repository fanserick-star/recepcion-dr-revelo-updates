from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v497'
OUT=ROOT/'updates'/'v498'
VERSION='4.3.98'
LAUNCHER_VERSION='4.3.98-standalone-5'


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
    s=replace_once(s,'APP_VERSION = "4.3.97"','APP_VERSION = "4.3.98"','version backend')
    s=replace_once(s,"const VERSION=\\'4.3.97\\';","const VERSION=\\'4.3.98\\';",'version visual')
    compile(s,'app.py','exec')
    for token in ['APP_VERSION = "4.3.98"','V497_ATTENTION_JS','button.service-card[data-service]','v497-native-consult','_POSTGRES_DRIVER = "pg8000"','Revisando AZUR','Emitir por lotes']:
        if token not in s: raise SystemExit('falta '+token)
    return s


def patch_launcher(s):
    s=replace_once(s,'LAUNCHER_VERSION = "4.3.76-standalone-3"','LAUNCHER_VERSION = "4.3.98-standalone-5"','version launcher') if 'LAUNCHER_VERSION = "4.3.76-standalone-3"' in s else s
    s=replace_once(s,'LAUNCHER_VERSION = "4.3.96-standalone-4"','LAUNCHER_VERSION = "4.3.98-standalone-5"','version launcher') if 'LAUNCHER_VERSION = "4.3.96-standalone-4"' in s else s

    start=s.index('def _listening_pid() -> int | None:')
    end=s.index('\ndef _python_exe(', start)
    robust=r'''def _port_8000_pids() -> list[int]:
    """Devuelve todos los PID que usan el puerto local 8000, sin depender del idioma de netstat."""
    if os.name != "nt":
        return []
    pids = set()
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
            creationflags=_hidden_flags(),
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0].upper() != "TCP":
                continue
            local = parts[1].strip()
            try:
                port = local.rsplit(":", 1)[-1]
            except Exception:
                continue
            if port != "8000":
                continue
            try:
                pid = int(parts[-1])
            except Exception:
                continue
            if pid > 0 and pid != os.getpid():
                pids.add(pid)
    except Exception as exc:
        _log("No se pudo leer netstat para puerto 8000: " + repr(exc))
    return sorted(pids)


def _listening_pid() -> int | None:
    pids = _port_8000_pids()
    return pids[0] if pids else None


def _wait_port_8000_free(seconds: float = 7.0) -> bool:
    deadline = time.time() + max(0.5, float(seconds))
    while time.time() < deadline:
        if not _port_8000_pids():
            return True
        time.sleep(0.15)
    return not _port_8000_pids()


def _stop_server() -> None:
    if os.name != "nt":
        return
    # v4.3.98: no dependemos del texto LISTENING/ESCUCHANDO. Si Windows todavía
    # conserva el proceso anterior, cerramos todos los PID cuyo puerto LOCAL es 8000.
    for _round in range(4):
        pids = _port_8000_pids()
        if not pids:
            return
        for pid in pids:
            try:
                proc = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                    check=False,
                    creationflags=_hidden_flags(),
                )
                if proc.returncode not in (0, 128):
                    _log(f"taskkill PID {pid} devolvió {proc.returncode}")
            except Exception as exc:
                _log(f"No se pudo cerrar PID {pid} del puerto 8000: {exc!r}")
        if _wait_port_8000_free(2.5):
            return
    remaining = _port_8000_pids()
    if remaining:
        raise RuntimeError("No se pudo liberar el puerto 8000. Procesos: " + ", ".join(map(str, remaining)))

'''
    s=s[:start]+robust+s[end+1:]

    old='''def _start_server() -> None:\n    py = _python_exe(windowless=True)\n'''
    new='''def _start_server() -> None:\n    if os.name == "nt" and _port_8000_pids():\n        _stop_server()\n    if os.name == "nt" and not _wait_port_8000_free(6.0):\n        raise RuntimeError("El puerto 8000 sigue ocupado y no es seguro iniciar otra copia de Recepción")\n    py = _python_exe(windowless=True)\n'''
    s=replace_once(s,old,new,'guardia antes de iniciar backend')
    compile(s,'ABRIR_RECEPCION.py','exec')
    for token in ['LAUNCHER_VERSION = "4.3.98-standalone-5"','def _port_8000_pids()','_wait_port_8000_free','taskkill','port != "8000"','El puerto 8000 sigue ocupado']:
        if token not in s: raise SystemExit('launcher falta '+token)
    return s


def main():
    app=patch_app(joined('app.part',7)); launcher=patch_launcher(joined('ABRIR_RECEPCION.part',4))
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    # Conserva el index con favicon publicado en v4.3.97.
    index_src=SRC/'static'/'index.html'; index= index_src.read_text(encoding='utf-8')
    index_target=OUT/'static'/'index.html';index_target.parent.mkdir(parents=True,exist_ok=True);index_target.write_text(index,encoding='utf-8',newline='')
    ab=app.encode(); lb=launcher.encode(); ib=index.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v498/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.98: corrige el reinicio tras actualizar liberando de forma robusta el puerto 8000 antes de arrancar el backend.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb))

if __name__=='__main__': main()
