from __future__ import annotations
APP_VERSION = "4.3.49"
import base64,hashlib,json,os,sys,zipfile,zlib
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BACKUP=ROOT/"data"/"update_backups"
TARGET_APP="f52c47436d005bba0c5546fff8ef4ebbdf0782c779c9a652a32abca2b4f50cf8"
APP_448="5ec6b484e2bdf6a15a798a276a3bafa7415d64a6f0c98d7eefc5ca20983247b6"
APP_447="d856e2e6b8dc2bea28d2b06b4b593b7cf5dd091eeafb1c67a9ba28ef62cd8ad3"
APP_446="f63a9466fef0c24f977a48d08e347504b7d582cc36aca465b07d004c43c02fd6"
APP_DELTA='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'

def hb(b): return hashlib.sha256(b).hexdigest()
def edits(blob): return json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
def patch(base,blob):
    lines=base.decode("utf-8").splitlines(keepends=True)
    for a,b,r in reversed(edits(blob)):
        lines[int(a):int(b)]=r
    return "".join(lines).encode("utf-8")

def make_app():
    p=ROOT/"app.py"
    b=p.read_bytes()
    h=hb(b)
    if h==TARGET_APP:
        return b
    if h==APP_446:
        b=b.replace(b'APP_VERSION = "4.3.46"',b'APP_VERSION = "4.3.48"',1)
    elif h==APP_447:
        b=b.replace(b'APP_VERSION = "4.3.47"',b'APP_VERSION = "4.3.48"',1)
    if hb(b)!=APP_448:
        raise RuntimeError("app.py no reconocido para v4.3.49")
    b=patch(b,APP_DELTA)
    if hb(b)!=TARGET_APP:
        raise RuntimeError("SHA final inválido: app.py")
    return b

def aw(path,data):
    tmp=path.with_name(path.name+".v449_tmp")
    tmp.write_bytes(data)
    os.replace(tmp,path)

def backup(path):
    BACKUP.mkdir(parents=True,exist_ok=True)
    z=BACKUP/("v449_antes_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as q:
        if path.exists():
            q.write(path,path.relative_to(ROOT).as_posix())
    return z

def restore(z):
    try:
        with zipfile.ZipFile(z) as q:
            for n in q.namelist():
                aw(ROOT/n,q.read(n))
    except Exception:
        pass

def main():
    app_path=ROOT/"app.py"
    fa=make_app()
    z=backup(app_path)
    try:
        aw(app_path,fa)
        if hb(app_path.read_bytes())!=TARGET_APP:
            raise RuntimeError("Verificación final de app.py falló")
    except Exception:
        restore(z)
        raise
    if os.getenv("RP_V449_NO_EXEC")=="1":
        print("v4.3.49 reconstruida y verificada")
        return 0
    os.execv(sys.executable,[sys.executable,str(app_path),*sys.argv[1:]])

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("No se pudo completar v4.3.49:",e,file=sys.stderr)
        raise
