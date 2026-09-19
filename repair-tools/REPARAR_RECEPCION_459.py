from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.parse, zipfile
from pathlib import Path

ROOT=Path(r"C:\Recepcion Dr Revelo")
LATEST="https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v4.json"
OFFICIAL="https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/"
TARGET_VERSION="4.5.9"
PROTECTED_TOP={"data",".venv"}
PROTECTED_FILES={".env","BASE DE DATOS 2026.xlsx"}

def msg(text,title="Reparar Recepción"):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(text),title,0x40)
    except Exception:
        print(text)

def cache_bust(url):
    p=urllib.parse.urlsplit(url);q=urllib.parse.parse_qsl(p.query,keep_blank_values=True);q.append(("repair_ts",str(time.time_ns())))
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(q),p.fragment))

def fetch(url,timeout=20):
    if not url.startswith(OFFICIAL):
        raise RuntimeError("Fuente no autorizada")
    req=urllib.request.Request(cache_bust(url),headers={"User-Agent":"Recepcion-Repair/4.5.9","Cache-Control":"no-cache","Pragma":"no-cache"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        if getattr(r,"status",200)!=200: raise RuntimeError("HTTP "+str(getattr(r,"status","?")))
        return r.read()

def safe_target(rel):
    rel=str(rel or "").replace("\\","/").lstrip("/")
    parts=[x for x in rel.split("/") if x]
    if not parts or any(x in {".",".."} for x in parts): raise RuntimeError("Ruta inválida")
    if parts[0].lower() in {x.lower() for x in PROTECTED_TOP}: raise RuntimeError("Ruta protegida: "+rel)
    if len(parts)==1 and parts[0].lower() in {x.lower() for x in PROTECTED_FILES}: raise RuntimeError("Archivo protegido: "+rel)
    dest=(ROOT/Path(*parts)).resolve(); rr=ROOT.resolve()
    if dest!=rr and rr not in dest.parents: raise RuntimeError("Ruta fuera de Recepción")
    return dest

def download_item(item):
    urls=item.get("parts") or ([item.get("url")] if item.get("url") else [])
    payload=b"".join(fetch(str(u)) for u in urls if u)
    expected=str(item.get("sha256") or "").lower().strip()
    got=hashlib.sha256(payload).hexdigest()
    if not expected or got!=expected: raise RuntimeError("SHA inválido: "+str(item.get("path")))
    rel=str(item.get("path") or "").replace("\\","/").lstrip("/")
    if rel.lower().endswith(".py"): compile(payload.decode("utf-8-sig"),rel,"exec")
    return rel,payload

def backup(paths):
    d=ROOT/"data"/"repair_backups";d.mkdir(parents=True,exist_ok=True)
    z=d/f"antes_reparacion_{time.strftime('%Y%m%d_%H%M%S')}.zip"; existed=set()
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as out:
        for rel in paths:
            p=safe_target(rel)
            if p.is_file(): out.write(p,rel);existed.add(rel)
    olds=sorted(d.glob("antes_reparacion_*.zip"),key=lambda p:p.stat().st_mtime,reverse=True)
    for p in olds[3:]:
        try:p.unlink()
        except:pass
    return z,existed

def rollback(z,paths,existed):
    for rel in paths:
        if rel not in existed:
            try:safe_target(rel).unlink(missing_ok=True)
            except:pass
    if z.is_file():
        with zipfile.ZipFile(z,"r") as src:
            for name in src.namelist():
                dest=safe_target(name);dest.parent.mkdir(parents=True,exist_ok=True)
                tmp=dest.with_name(dest.name+".rollback");tmp.write_bytes(src.read(name));os.replace(tmp,dest)

def ensure_pg8000():
    py=ROOT/".venv"/"Scripts"/"python.exe"
    if not py.is_file(): return
    probe=subprocess.run([str(py),"-c","import pg8000"],cwd=str(ROOT),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if probe.returncode!=0:
        subprocess.run([str(py),"-m","pip","install","--disable-pip-version-check","pg8000==1.31.2"],cwd=str(ROOT),check=True)

def reset_update_state():
    p=ROOT/"data"/"auto_update_state.json"
    if not p.is_file(): return
    try:
        data=json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:data={}
    data.update({
        "failed_candidate_version":"",
        "failed_candidate_fingerprint":"",
        "failed_candidate_count":0,
        "candidate_quarantined":False,
        "candidate_last_error":"",
        "forced_repair_version":TARGET_VERSION,
        "forced_repair_at":time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    tmp=p.with_suffix(".repair.tmp");tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");os.replace(tmp,p)

def recreate_shortcut():
    pyw=ROOT/".venv"/"Scripts"/"pythonw.exe"; launcher=ROOT/"ABRIR_RECEPCION.py"
    if not pyw.is_file() or not launcher.is_file(): return
    desktop=Path(os.environ.get("USERPROFILE",""))/"Desktop"
    if not desktop.is_dir(): desktop=Path(os.environ.get("USERPROFILE",""))/"OneDrive"/"Desktop"
    if not desktop.is_dir(): return
    lnk=desktop/"Recepción Dr. Armando Revelo.lnk"
    ps=("$W=New-Object -ComObject WScript.Shell;"
        f"$S=$W.CreateShortcut('{str(lnk).replace("'","''")}');"
        f"$S.TargetPath='{str(pyw).replace("'","''")}';"
        f"$S.Arguments='\"{str(launcher).replace("'","''")}\"';"
        f"$S.WorkingDirectory='{str(ROOT).replace("'","''")}';"
        "$S.Description='Recepción Dr. Armando Revelo';"
        "$S.Save()")
    subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-Command",ps],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def main():
    if not ROOT.is_dir(): raise RuntimeError("No encontré C:\\Recepcion Dr Revelo")
    manifest=json.loads(fetch(LATEST).decode("utf-8-sig"))
    if str(manifest.get("version"))!=TARGET_VERSION: raise RuntimeError("El canal estable no está en "+TARGET_VERSION)
    files=manifest.get("files") or []
    stage=Path(tempfile.mkdtemp(prefix="recepcion_repair_"))
    staged=[]
    try:
        for i,item in enumerate(files,1):
            rel,payload=download_item(item)
            safe_target(rel)
            sp=stage/rel;sp.parent.mkdir(parents=True,exist_ok=True);sp.write_bytes(payload)
            staged.append((rel,sp,str(item.get("sha256") or "").lower()))
        paths=[x[0] for x in staged]
        z,existed=backup(paths)
        try:
            for rel,sp,sha in staged:
                dest=safe_target(rel);dest.parent.mkdir(parents=True,exist_ok=True)
                tmp=dest.with_name(dest.name+".repair_new");shutil.copyfile(sp,tmp);os.replace(tmp,dest)
                if hashlib.sha256(dest.read_bytes()).hexdigest()!=sha: raise RuntimeError("Verificación final falló: "+rel)
            app=(ROOT/"app.py").read_text(encoding="utf-8-sig",errors="ignore")
            if 'APP_VERSION = "4.5.9"' not in app and "APP_VERSION='4.5.9'" not in app:
                raise RuntimeError("app.py no quedó en 4.5.9")
            ensure_pg8000(); reset_update_state(); recreate_shortcut()
        except Exception:
            rollback(z,paths,existed);raise
    finally:
        shutil.rmtree(stage,ignore_errors=True)
    msg("Recepción quedó reparada y actualizada a v4.5.9.\n\nTus datos, .env y BASE DE DATOS 2026.xlsx no fueron reemplazados.\n\nAbre Recepción desde el acceso directo del escritorio.")
    pyw=ROOT/".venv"/"Scripts"/"pythonw.exe";launcher=ROOT/"ABRIR_RECEPCION.py"
    if pyw.is_file() and launcher.is_file():
        subprocess.Popen([str(pyw),str(launcher)],cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)|getattr(subprocess,"CREATE_NO_WINDOW",0))

if __name__=="__main__":
    try: main()
    except Exception as exc:
        msg("No se pudo reparar Recepción.\n\n"+type(exc).__name__+": "+str(exc),"Error al reparar Recepción")
        raise
