from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v499'
OUT=ROOT/'updates'/'v43100'
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

    port_config='''APP_VERSION = "4.3.100"\ntry:\n    LOCAL_HTTP_PORT = int((os.getenv("RP_PORT") or "8000").strip())\nexcept Exception:\n    LOCAL_HTTP_PORT = 8000\nif not (1024 <= LOCAL_HTTP_PORT <= 65535):\n    LOCAL_HTTP_PORT = 8000\n'''
    s=replace_once(s,'APP_VERSION = "4.3.100"\n',port_config,'config puerto backend')

    s=replace_once(
        s,
        "busy = sock.connect_ex(('127.0.0.1', 8000)) == 0",
        "busy = sock.connect_ex(('127.0.0.1', {LOCAL_HTTP_PORT})) == 0",
        'reinicio interno puerto dinamico',
    )
    s=replace_once(s,'MOBILE_LAN_PORT = 8000','MOBILE_LAN_PORT = LOCAL_HTTP_PORT','puerto LAN dinamico')
    s=replace_once(
        s,
        'remote_start_quick_tunnel(DATA_DIR, origin="http://127.0.0.1:8000", wait_seconds=18)',
        'remote_start_quick_tunnel(DATA_DIR, origin=f"http://127.0.0.1:{LOCAL_HTTP_PORT}", wait_seconds=18)',
        'tunel dinamico',
    )
    s=replace_once(
        s,
        'uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, access_log=False, log_level="warning", workers=1)',
        'uvicorn.run("app:app", host="0.0.0.0", port=LOCAL_HTTP_PORT, reload=False, access_log=False, log_level="warning", workers=1)',
        'uvicorn puerto dinamico',
    )
    # Corrige el comentario para no volver a asumir un puerto fijo.
    s=s.replace('el helper espera a que el puerto 8000 quede realmente','el helper espera a que el puerto local quede realmente',1)

    compile(s,'app.py','exec')
    for token in [
        'APP_VERSION = "4.3.100"','LOCAL_HTTP_PORT','port=LOCAL_HTTP_PORT',
        'MOBILE_LAN_PORT = LOCAL_HTTP_PORT','origin=f"http://127.0.0.1:{LOCAL_HTTP_PORT}"',
        'V497_ATTENTION_JS','button.service-card[data-service]','v497-native-consult',
        '_POSTGRES_DRIVER = "pg8000"','Revisando AZUR','Emitir por lotes'
    ]:
        if token not in s: raise SystemExit('app falta '+token)
    # No debe quedar ningún 8000 funcional salvo defaults y el nombre pg8000.
    forbidden=["('127.0.0.1', 8000)",'MOBILE_LAN_PORT = 8000','127.0.0.1:8000','port=8000']
    for token in forbidden:
        if token in s: raise SystemExit('app conserva puerto fijo: '+token)
    return s


def patch_launcher(s):
    s=replace_once(s,'LAUNCHER_VERSION = "4.3.99-standalone-6"','LAUNCHER_VERSION = "4.3.100-standalone-7"','version launcher')
    # socket se usa para comprobar de forma segura si un puerto realmente puede enlazarse.
    marker='LAUNCHER_VERSION = "4.3.100-standalone-7"'
    s=replace_once(s,marker,'import socket\n\n'+marker,'import socket')

    old_constants='''URL = "http://127.0.0.1:8000"\nVERSION_URL = URL + "/api/version"\n'''
    new_constants='''APP_PORT = 8000\nURL = f"http://127.0.0.1:{APP_PORT}"\nVERSION_URL = URL + "/api/version"\n'''
    s=replace_once(s,old_constants,new_constants,'constantes URL dinamicas')

    start=s.index('def _port_8000_pids() -> list[int]:')
    end=s.index('\ndef _python_exe(',start)
    dynamic=r'''def _set_app_port(port: int) -> int:
    global APP_PORT, URL, VERSION_URL
    APP_PORT = int(port)
    URL = f"http://127.0.0.1:{APP_PORT}"
    VERSION_URL = URL + "/api/version"
    return APP_PORT


def _port_file() -> Path:
    return _data_dir(ROOT) / "local_port.txt"


def _read_saved_port() -> int | None:
    try:
        value = int(_port_file().read_text(encoding="utf-8").strip())
        return value if 1024 <= value <= 65535 else None
    except Exception:
        return None


def _save_port(port: int) -> None:
    try:
        path = _port_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(int(port)), encoding="utf-8")
    except Exception as exc:
        _log("No se pudo guardar el puerto local: " + repr(exc))


def _can_bind_port(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.bind(("0.0.0.0", int(port)))
        return True
    except OSError:
        return False
    finally:
        try: sock.close()
        except Exception: pass


def _choose_app_port(force_new: bool = False) -> int:
    """Elige un puerto de Recepción sin cerrar ni interferir con programas ajenos."""
    saved = _read_saved_port()
    if saved and not force_new:
        _set_app_port(saved)
        # Si responde /api/version es nuestra copia ya levantada; se conserva.
        if _running_version(timeout=0.30) is not None:
            return saved
        if _can_bind_port(saved):
            return saved

    candidates = []
    if not force_new:
        candidates.append(8000)
    candidates.extend(range(8765, 8800))
    candidates.extend(range(18000, 18021))
    current = int(APP_PORT or 0)
    for port in candidates:
        if force_new and int(port) == current:
            continue
        if _can_bind_port(port):
            _set_app_port(port)
            _save_port(port)
            _log(f"Puerto local seleccionado: {port}")
            return port
    raise RuntimeError("No se encontró un puerto local libre para Recepción")


def _port_pids(port: int | None = None) -> list[int]:
    if os.name != "nt":
        return []
    wanted = str(int(port or APP_PORT))
    pids = set()
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
            timeout=6, check=False, creationflags=_hidden_flags(),
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0].upper() != "TCP":
                continue
            local = parts[1].strip()
            if local.rsplit(":", 1)[-1] != wanted:
                continue
            try: pid = int(parts[-1])
            except Exception: continue
            if pid > 0 and pid != os.getpid(): pids.add(pid)
    except Exception as exc:
        _log(f"No se pudo leer netstat para puerto {wanted}: {exc!r}")
    return sorted(pids)


def _listening_pid() -> int | None:
    pids = _port_pids()
    return pids[0] if pids else None


def _wait_app_port_free(seconds: float = 7.0) -> bool:
    deadline = time.time() + max(0.5, float(seconds))
    while time.time() < deadline:
        if not _port_pids(): return True
        time.sleep(0.15)
    return not _port_pids()


def _stop_server() -> None:
    if os.name != "nt": return
    pids = _port_pids()
    if not pids: return
    # Nunca matamos un proceso desconocido. Solo cerramos el dueño del puerto si
    # ese puerto está respondiendo como Recepción.
    if _running_version(timeout=0.45) is None:
        _log(f"Puerto {APP_PORT} ocupado por proceso ajeno; se conservará y se elegirá otro puerto")
        return
    for _round in range(4):
        pids = _port_pids()
        if not pids: return
        for pid in pids:
            try:
                proc = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=8, check=False, creationflags=_hidden_flags(),
                )
                if proc.returncode not in (0,128):
                    _log(f"taskkill PID {pid} devolvió {proc.returncode}")
            except Exception as exc:
                _log(f"No se pudo cerrar PID {pid} del puerto {APP_PORT}: {exc!r}")
        if _wait_app_port_free(2.5): return
    remaining=_port_pids()
    if remaining:
        raise RuntimeError(f"No se pudo liberar el puerto local {APP_PORT}. Procesos: " + ", ".join(map(str,remaining)))

'''
    s=s[:start]+dynamic+s[end+1:]

    start=s.index('def _start_server() -> None:')
    end=s.index('\ndef _wait_server(',start)
    start_server=r'''def _start_server() -> None:
    # Si el puerto guardado fue tomado por un programa ajeno, NO lo cerramos:
    # elegimos otro puerto y actualizamos URL/VERSION_URL antes de arrancar.
    if os.name == "nt" and _port_pids():
        if _running_version(timeout=0.45) is not None:
            _stop_server()
        else:
            _choose_app_port(force_new=True)
    if os.name == "nt" and _port_pids():
        raise RuntimeError(f"El puerto local {APP_PORT} sigue ocupado")
    py = _python_exe(windowless=True)
    env = os.environ.copy()
    env["RP_DESKTOP_LAUNCH"] = "1"
    env["DISABLE_SQLALCHEMY_CEXT_RUNTIME"] = "1"
    env["RP_PORT"] = str(APP_PORT)
    d = _data_dir(ROOT)
    d.mkdir(parents=True, exist_ok=True)
    log_path = d / "backend_startup.log"
    fh = open(log_path, "a", encoding="utf-8")
    fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando app.py en puerto {APP_PORT}\n")
    fh.flush()
    flags = _hidden_flags()
    if os.name == "nt": flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        [str(py), str(ROOT / "app.py")], cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=fh, stderr=fh,
        creationflags=flags, close_fds=True,
    )

'''
    s=s[:start]+start_server+s[end+1:]

    # El puerto se resuelve antes de cualquier sonda al backend.
    main_old='''def main() -> None:\n    _set_windows_identity()\n\n    # Protección doble:'''
    main_new='''def main() -> None:\n    _set_windows_identity()\n    _choose_app_port()\n\n    # Protección doble:'''
    s=replace_once(s,main_old,main_new,'seleccion puerto al iniciar')

    # El relanzamiento hereda el puerto elegido, aunque también queda persistido.
    helper_old='''def _relaunch_updated_launcher() -> None:\n    """Abre el launcher recién escrito en disco y deja terminar el proceso viejo."""\n    py = _python_exe(windowless=True)\n    env = os.environ.copy()\n'''
    helper_new='''def _relaunch_updated_launcher() -> None:\n    """Abre el launcher recién escrito en disco y deja terminar el proceso viejo."""\n    py = _python_exe(windowless=True)\n    env = os.environ.copy()\n    env["RP_PORT"] = str(APP_PORT)\n'''
    s=replace_once(s,helper_old,helper_new,'heredar puerto en relaunch')

    compile(s,'ABRIR_RECEPCION.py','exec')
    for token in [
        'LAUNCHER_VERSION = "4.3.100-standalone-7"','def _choose_app_port(','def _port_pids(',
        'local_port.txt','env["RP_PORT"] = str(APP_PORT)','_choose_app_port()','_choose_app_port(force_new=True)',
        'Puerto local seleccionado','def _relaunch_updated_launcher()','"abrir_recepcion.py" in updated_paths'
    ]:
        if token not in s: raise SystemExit('launcher falta '+token)
    if 'def _port_8000_pids' in s or '_wait_port_8000_free' in s:
        raise SystemExit('launcher conserva logica fija de puerto 8000')
    return s


def main():
    app=patch_app(joined('app.part',7)); launcher=patch_launcher(joined('ABRIR_RECEPCION.part',4))
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8')
    index_target=OUT/'static'/'index.html'; index_target.parent.mkdir(parents=True,exist_ok=True); index_target.write_text(index,encoding='utf-8',newline='')
    ab=app.encode(); lb=launcher.encode(); ib=index.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode(); (OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v43100/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.100: elimina la dependencia del puerto 8000; Recepción selecciona y recuerda automáticamente un puerto libre sin cerrar procesos ajenos.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n'; (ROOT/'latest.json').write_text(txt,encoding='utf-8',newline=''); (ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb))

if __name__=='__main__': main()
