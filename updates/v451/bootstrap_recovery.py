from __future__ import annotations

APP_VERSION = "4.3.51"

import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PROGRAM_MARKER = "# v4.3.51 — PROGRAM_UPDATE_API"
PROGRAM_API = r'''

# v4.3.51 — PROGRAM_UPDATE_API
@app.post("/api/program/update-now")
def program_update_now():
    """Comprueba el canal oficial y aplica una versión nueva con SHA y respaldo."""
    import hashlib as _hashlib
    import json as _json
    import os as _os
    import subprocess as _subprocess
    import sys as _sys
    import threading as _threading
    import time as _time
    import urllib.parse as _urlparse
    import urllib.request as _urlrequest
    import zipfile as _zipfile
    from datetime import datetime as _datetime
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parent
    _url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json"

    def _ver(v):
        out=[]
        for p in str(v or "0").split("."):
            try: out.append(int(p))
            except Exception: out.append(0)
        return tuple((out+[0,0,0,0])[:4])

    def _fresh(url):
        parts=_urlparse.urlsplit(str(url))
        q=_urlparse.parse_qsl(parts.query,keep_blank_values=True)
        q.append(("rp_ts",str(_time.time_ns())))
        return _urlparse.urlunsplit((parts.scheme,parts.netloc,parts.path,_urlparse.urlencode(q),parts.fragment))

    def _download(url, attempts=3):
        last=None
        for i in range(attempts):
            try:
                req=_urlrequest.Request(_fresh(url),headers={"User-Agent":"Recepcion-Dr-Revelo-program-update","Cache-Control":"no-cache, no-store","Pragma":"no-cache"})
                with _urlrequest.urlopen(req,timeout=18+i*2) as r:
                    return r.read(12_000_000)
            except Exception as e:
                last=e
                if i+1<attempts:_time.sleep(.35*(i+1))
        raise last

    try:
        manifest=_json.loads(_download(_url).decode("utf-8-sig"))
        latest=str(manifest.get("version") or "").strip()
        current=str(APP_VERSION)
        if not latest:
            return {"ok":False,"message":"El canal de actualización no informó una versión."}
        if _ver(latest) <= _ver(current):
            return {"ok":True,"update":False,"current":current,"latest":latest,"message":"El programa ya está actualizado."}

        files=list(manifest.get("files") or [])
        if not files:
            return {"ok":False,"message":"La actualización publicada no contiene archivos."}

        prepared=[]
        for item in files:
            rel=str(item.get("path") or "").replace("\\","/").lstrip("/")
            if not rel or ".." in rel.split("/") or rel.split("/")[0] in {"data",".venv",".env","BASE DE DATOS 2026.xlsx"}:
                raise RuntimeError("Ruta no válida en la actualización: "+rel)
            urls=item.get("parts") or ([item.get("url")] if item.get("url") else [])
            if not urls: raise RuntimeError("Archivo sin origen: "+rel)
            data=b"".join(_download(u) for u in urls)
            want=str(item.get("sha256") or "").lower().strip()
            got=_hashlib.sha256(data).hexdigest()
            if not want or got!=want:
                raise RuntimeError("No se pudo verificar "+rel)
            if rel.endswith('.py'):
                compile(data.decode('utf-8-sig'),rel,'exec')
            prepared.append((rel,data))

        _backup=_root/"data"/"update_backups"
        _backup.mkdir(parents=True,exist_ok=True)
        z=_backup/("programa_antes_actualizacion_"+_datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
        with _zipfile.ZipFile(z,"w",_zipfile.ZIP_DEFLATED) as q:
            for rel,_data in prepared:
                p=_root/rel
                if p.exists():q.write(p,rel)

        for rel,data in prepared:
            p=_root/rel;p.parent.mkdir(parents=True,exist_ok=True)
            t=p.with_name(p.name+".program_update_tmp")
            t.write_bytes(data);_os.replace(t,p)

        py=str(_sys.executable);app=str(_root/"app.py")
        code=("import os,time; time.sleep(1.4); os.chdir("+repr(str(_root))+"); os.execv("+repr(py)+",["+repr(py)+","+repr(app)+"])")
        flags=getattr(_subprocess,"CREATE_NO_WINDOW",0)
        _subprocess.Popen([py,"-c",code],cwd=str(_root),creationflags=flags)
        _threading.Timer(.65,lambda:_os._exit(0)).start()
        return {"ok":True,"update":True,"current":current,"latest":latest,"message":"Actualización encontrada. Reiniciando el programa…"}
    except Exception as e:
        return {"ok":False,"update":False,"current":str(APP_VERSION),"message":str(e)}
'''


def _data_dir() -> Path:
    raw = (os.getenv("RP_DATA_DIR") or "").strip()
    if not raw and (ROOT / ".env").exists():
        try:
            for line in (ROOT / ".env").read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                if line.strip().startswith("RP_DATA_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if not raw:
        return ROOT / "data"
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    return p if p.is_absolute() else ROOT / p


def _log(message: str) -> None:
    try:
        d = _data_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / "v451_recovery.log"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def _backup_dirs() -> list[Path]:
    candidates = [
        _data_dir() / "update_backups",
        ROOT / "data" / "update_backups",
        ROOT.parent / "data" / "update_backups",
    ]
    out: list[Path] = []
    seen = set()
    for p in candidates:
        try: key = str(p.resolve()).lower()
        except Exception: key = str(p).lower()
        if key not in seen:
            seen.add(key); out.append(p)
    return out


def _is_v450(data: bytes) -> bool:
    try:
        head = data[:5000].decode("utf-8-sig", errors="ignore")
    except Exception:
        return False
    return bool(re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.50["\']', head, re.MULTILINE))


def _find_v450() -> tuple[bytes, str]:
    archives: list[Path] = []
    for directory in _backup_dirs():
        try: archives.extend(directory.glob("*.zip"))
        except Exception: pass

    def mt(p: Path) -> float:
        try:return p.stat().st_mtime
        except Exception:return 0.0

    seen = set()
    for archive in sorted(archives, key=mt, reverse=True)[:120]:
        try:
            key=str(archive.resolve()).lower()
            if key in seen: continue
            seen.add(key)
            with zipfile.ZipFile(archive) as zf:
                for name in zf.namelist():
                    if not name.replace("\\", "/").endswith("app.py"):
                        continue
                    data=zf.read(name)
                    if _is_v450(data):
                        return data, f"{archive.name}:{name}"
        except Exception:
            pass
    raise RuntimeError("No encontré un respaldo app.py v4.3.50 para consolidar la actualización.")


def _build_final(base: bytes) -> bytes:
    text = base.decode("utf-8-sig")
    text2, n = re.subn(
        r'^\s*APP_VERSION\s*=\s*["\']4\.3\.50["\']',
        'APP_VERSION = "4.3.51"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n != 1:
        raise RuntimeError("El respaldo v4.3.50 no contiene la versión esperada.")

    if PROGRAM_MARKER not in text2:
        m = re.search(r'(?m)^if\s+__name__\s*==\s*["\']__main__["\']\s*:', text2)
        if not m:
            raise RuntimeError("No encontré el arranque principal del programa.")
        text2 = text2[:m.start()] + PROGRAM_API + "\n" + text2[m.start():]

    compile(text2, "app.py", "exec")
    head=text2[:1000]
    if 'APP_VERSION = "4.3.51"' not in head:
        raise RuntimeError("La versión final no quedó marcada como 4.3.51.")
    if PROGRAM_MARKER not in text2:
        raise RuntimeError("No se incorporó el actualizador interno.")
    return text2.encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name(path.name+".v451_final_tmp")
    tmp.write_bytes(data)
    os.replace(tmp,path)


def _backup_live_app() -> Path | None:
    app=ROOT/"app.py"
    if not app.exists(): return None
    d=_data_dir()/"update_backups";d.mkdir(parents=True,exist_ok=True)
    z=d/("v451_recovery_live_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as q:q.write(app,"app.py")
    return z


def main() -> int:
    # Regla crítica: nunca escribimos v4.3.50 sobre el app.py vivo.
    # Primero encontramos la base, construimos y compilamos 4.3.51 en memoria;
    # solo cuando todo está verificado hacemos un único reemplazo atómico.
    base, source = _find_v450()
    _log("Base v4.3.50 encontrada en " + source)
    final = _build_final(base)
    _backup_live_app()
    _atomic_write(ROOT / "app.py", final)

    try:
        check=(ROOT/"app.py").read_text(encoding="utf-8-sig",errors="strict")
        compile(check,"app.py","exec")
        if not re.search(r'^\s*APP_VERSION\s*=\s*["\']4\.3\.51["\']',check,re.MULTILINE):
            raise RuntimeError("Verificación posterior de versión falló.")
    except Exception as exc:
        _log("Fallo de verificación final: "+repr(exc))
        raise

    try:
        marker=_data_dir()/"v451_consolidated.json"
        marker.write_text(json.dumps({"version":"4.3.51","source":source,"at":datetime.now().isoformat()},ensure_ascii=False,indent=2),encoding="utf-8")
    except Exception:pass

    _log("v4.3.51 consolidada correctamente")
    if os.getenv("RP_V451_RECOVERY_NO_EXEC") == "1":
        print("v4.3.51 consolidada y verificada")
        return 0
    os.execv(sys.executable,[sys.executable,str(ROOT/"app.py"),*sys.argv[1:]])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _log("ERROR: "+repr(exc))
        # No degradamos app.py a 4.3.50. Dejar el recovery 4.3.51 evita
        # que el updater vuelva a descargar la misma versión en bucle.
        print("No se pudo consolidar v4.3.51:",exc,file=sys.stderr)
        raise
