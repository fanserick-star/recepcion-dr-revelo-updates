from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v499'
OUT=ROOT/'updates'/'v4100'
VERSION='4.3.100'
LAUNCHER_VERSION='4.3.100-standalone-7'


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
    s=replace_once(s,'APP_VERSION = "4.3.99"','APP_VERSION = "4.3.100"','version backend')
    s=replace_once(s,"const VERSION=\\'4.3.99\\';","const VERSION=\\'4.3.100\\';",'version visual')
    s=replace_once(
        s,
        'APP_VERSION = "4.3.100"\n',
        'APP_VERSION = "4.3.100"\ntry:\n    APP_PORT = int((os.getenv("RP_PORT") or "8000").strip())\nexcept Exception:\n    APP_PORT = 8000\nif not (1024 <= APP_PORT <= 65535):\n    APP_PORT = 8000\n',
        'puerto configurable backend',
    )
    s=replace_once(s,"busy = sock.connect_ex(('127.0.0.1', 8000)) == 0","busy = sock.connect_ex(('127.0.0.1', {APP_PORT})) == 0",'reinicio puerto dinámico')
    s=replace_once(s,'MOBILE_LAN_PORT = 8000','MOBILE_LAN_PORT = APP_PORT','LAN usa puerto activo')
    s=replace_once(s,'remote_start_quick_tunnel(DATA_DIR, origin="http://127.0.0.1:8000", wait_seconds=18)','remote_start_quick_tunnel(DATA_DIR, origin=f"http://127.0.0.1:{APP_PORT}", wait_seconds=18)','túnel usa puerto activo')
    s=replace_once(s,'uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, access_log=False, log_level="warning", workers=1)','uvicorn.run("app:app", host="0.0.0.0", port=APP_PORT, reload=False, access_log=False, log_level="warning", workers=1)','uvicorn puerto dinámico')
    compile(s,'app.py','exec')
    for token in ['APP_VERSION = "4.3.100"','APP_PORT = int','MOBILE_LAN_PORT = APP_PORT','port=APP_PORT','origin=f"http://127.0.0.1:{APP_PORT}"','V497_ATTENTION_JS','button.service-card[data-service]','v497-native-consult','Revisando AZUR','Emitir por lotes']:
        if token not in s: raise SystemExit('app falta '+token)
    return s


def patch_launcher(s):
    if 'import socket\n' not in s:
        s=replace_once(s,'from __future__ import annotations\n','from __future__ import annotations\nimport socket\n','import socket')
    s=replace_once(s,'LAUNCHER_VERSION = "4.3.99-standalone-6"','LAUNCHER_VERSION = "4.3.100-standalone-7"','version launcher')
    s=replace_once(
        s,
        'URL = "http://127.0.0.1:8000"\nVERSION_URL = URL + "/api/version"',
        'DEFAULT_PORT = 8765\nACTIVE_PORT = DEFAULT_PORT\nURL = f"http://127.0.0.1:{ACTIVE_PORT}"\nVERSION_URL = URL + "/api/version"',
        'URL dinámica',
    )
    root_marker='ROOT = Path(__file__).resolve().parent\n'
    port_helpers=r'''ROOT = Path(__file__).resolve().parent


def _port_state_file() -> Path:
    return _data_dir(ROOT) / "active_port.txt"


def _set_active_port(port: int, persist: bool = False) -> int:
    global ACTIVE_PORT, URL, VERSION_URL
    try:
        port = int(port)
    except Exception:
        port = DEFAULT_PORT
    if not (1024 <= port <= 65535):
        port = DEFAULT_PORT
    ACTIVE_PORT = port
    URL = f"http://127.0.0.1:{ACTIVE_PORT}"
    VERSION_URL = URL + "/api/version"
    if persist:
        try:
            p = _port_state_file()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(ACTIVE_PORT), encoding="utf-8")
        except Exception as exc:
            _log("No se pudo guardar el puerto activo: " + repr(exc))
    return ACTIVE_PORT


def _load_active_port() -> int:
    try:
        p = _port_state_file()
        if p.exists():
            value = int(p.read_text(encoding="utf-8").strip())
            if 1024 <= value <= 65535:
                return value
    except Exception:
        pass
    return DEFAULT_PORT


def _port_is_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _find_free_port(exclude=None) -> int:
    blocked = {int(x) for x in (exclude or set())}
    candidates = [DEFAULT_PORT] + list(range(8766, 8800))
    for port in candidates:
        if port not in blocked and _port_is_free(port):
            return port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()
'''
    s=replace_once(s,root_marker,port_helpers,'helpers puerto')

    start=s.index('def _port_8000_pids() -> list[int]:')
    end=s.index('\ndef _python_exe(', start)
    port_block=r'''def _port_pids(port: int) -> list[int]:
    """Devuelve PID que usan un puerto TCP local concreto."""
    if os.name != "nt":
        return []
    wanted = str(int(port))
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
            if local.rsplit(":", 1)[-1] != wanted:
                continue
            try:
                pid = int(parts[-1])
            except Exception:
                continue
            if pid > 0 and pid != os.getpid():
                pids.add(pid)
    except Exception as exc:
        _log(f"No se pudo leer netstat para puerto {wanted}: {exc!r}")
    return sorted(pids)


def _active_port_pids() -> list[int]:
    return _port_pids(ACTIVE_PORT)


def _listening_pid() -> int | None:
    pids = _active_port_pids()
    return pids[0] if pids else None


def _wait_active_port_free(seconds: float = 4.0) -> bool:
    deadline = time.time() + max(0.5, float(seconds))
    while time.time() < deadline:
        if _port_is_free(ACTIVE_PORT):
            return True
        time.sleep(0.15)
    return _port_is_free(ACTIVE_PORT)


def _stop_server() -> None:
    """Intenta cerrar nuestro backend. Si Windows lo impide, abandona ese puerto y sigue en otro."""
    if os.name != "nt":
        return
    old_port = ACTIVE_PORT
    for _round in range(2):
        pids = _active_port_pids()
        if not pids:
            return
        for pid in pids:
            try:
                proc = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=7,
                    check=False,
                    creationflags=_hidden_flags(),
                )
                if proc.returncode not in (0, 128):
                    _log(f"taskkill PID {pid} en puerto {old_port} devolvió {proc.returncode}")
            except Exception as exc:
                _log(f"No se pudo cerrar PID {pid} del puerto {old_port}: {exc!r}")
        if _wait_active_port_free(1.2):
            return
    remaining = _active_port_pids()
    if remaining:
        new_port = _find_free_port(exclude={old_port})
        _log(f"Puerto {old_port} no liberable (PID={','.join(map(str, remaining))}); continuando automáticamente en {new_port}")
        _set_active_port(new_port, persist=True)

'''
    s=s[:start]+port_block+s[end+1:]

    start=s.index('def _start_server() -> None:')
    end=s.index('\ndef _wait_server(', start)
    start_server=r'''def _start_server() -> None:
    if not _port_is_free(ACTIVE_PORT):
        _stop_server()
    if not _port_is_free(ACTIVE_PORT):
        _set_active_port(_find_free_port(exclude={ACTIVE_PORT}), persist=True)
    else:
        _set_active_port(ACTIVE_PORT, persist=True)
    py = _python_exe(windowless=True)
    env = os.environ.copy()
    env["RP_DESKTOP_LAUNCH"] = "1"
    env["DISABLE_SQLALCHEMY_CEXT_RUNTIME"] = "1"
    env["RP_PORT"] = str(ACTIVE_PORT)
    d = _data_dir(ROOT)
    d.mkdir(parents=True, exist_ok=True)
    log_path = d / "backend_startup.log"
    fh = open(log_path, "a", encoding="utf-8")
    fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando app.py en puerto {ACTIVE_PORT}\n")
    fh.flush()
    flags = _hidden_flags()
    if os.name == "nt":
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [str(py), str(ROOT / "app.py")],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=fh,
        stderr=fh,
        creationflags=flags,
        close_fds=True,
    )

'''
    s=s[:start]+start_server+s[end+1:]

    old_main='''def main() -> None:\n    _set_windows_identity()\n\n    # Protección doble: mutex mientras el launcher/WebView está vivo y detección\n    # de ventana para el caso excepcional de fallback Edge.\n    if _running_version(timeout=0.45) is not None and _focus_existing_window():\n        return\n'''
    new_main='''def main() -> None:\n    _set_windows_identity()\n    _set_active_port(_load_active_port())\n\n    # Solo reutilizamos una ventana existente si el backend que responde en el\n    # puerto persistido coincide con la versión instalada actualmente. Un servidor\n    # viejo o ajeno nunca bloquea una actualización nueva.\n    installed_expected = _expected_app_version(ROOT)\n    if _running_version(timeout=0.45) == installed_expected and _focus_existing_window():\n        return\n'''
    s=replace_once(s,old_main,new_main,'main puerto persistido')

    compile(s,'ABRIR_RECEPCION.py','exec')
    for token in ['LAUNCHER_VERSION = "4.3.100-standalone-7"','DEFAULT_PORT = 8765','def _find_free_port','def _port_pids(port: int)','env["RP_PORT"] = str(ACTIVE_PORT)','Puerto {old_port} no liberable','_set_active_port(_load_active_port())','installed_expected = _expected_app_version(ROOT)','def _relaunch_updated_launcher()']:
        if token not in s: raise SystemExit('launcher falta '+token)
    return s


def main():
    app=patch_app(joined('app.part',7)); launcher=patch_launcher(joined('ABRIR_RECEPCION.part',4))
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8')
    index_target=OUT/'static'/'index.html'; index_target.parent.mkdir(parents=True,exist_ok=True); index_target.write_text(index,encoding='utf-8',newline='')
    ab=app.encode(); lb=launcher.encode(); ib=index.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode(); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4100/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.100: elimina la dependencia del puerto 8000. Recepción usa un puerto local administrado y cambia automáticamente si Windows mantiene otro proceso bloqueado.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb))

if __name__=='__main__': main()
