from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"updates"/"v4_4_49_agenda_flow_speed"
VERSION="4.4.49"
sys.path.insert(0,str(HERE))
import validate_v4449 as validation


def require(cond,msg):
    if not cond: raise RuntimeError(msg)

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def version_tuple(v):
    out=[]
    for p in str(v or "0").split("."):
        try:out.append(int(p))
        except Exception:out.append(0)
    return tuple((out+[0,0,0,0])[:4])

def git(*args):subprocess.run(["git",*args],cwd=ROOT,check=True)

def fetch(url,attempts=4,timeout=25.0):
    last=None
    for i in range(attempts):
        try:
            sep="&" if "?" in url else "?"
            req=urllib.request.Request(url+sep+"rp="+str(time.time_ns()),headers={"Cache-Control":"no-cache","Pragma":"no-cache","User-Agent":"v4449-run2"})
            with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
        except Exception as exc:
            last=exc
            if i+1<attempts:time.sleep(min(3.0,.5+i*.5))
    raise RuntimeError(f"fetch falló {url}: {last}")

def wait_payload(item,attempts=50):
    last=None
    for i in range(attempts):
        try:
            urls=item.get("parts") or [item.get("url")]
            data=b"".join(fetch(str(u),attempts=1) for u in urls if u)
            if sha(data)==str(item.get("sha256") or ""):return data
            last=sha(data)
        except Exception as exc:last=exc
        time.sleep(min(4.0,.7+i*.15))
    raise RuntimeError(f"Raw no propagó {item.get('path')}: {last}")

def normalize_app_base_and_candidate():
    path=OUT/"app_base_4428.py"
    # read_text usa universal-newline y elimina la diferencia CRLF del runner.
    text=path.read_text(encoding="utf-8-sig")
    data=text.encode("utf-8")
    path.write_bytes(data)
    compile(text,"app_base_4428.py","exec")
    candidate=json.loads((OUT/"candidate_latest.json").read_text(encoding="utf-8"))
    for item in candidate.get("files",[]):
        if item.get("path")=="app_base_4428.py":item["sha256"]=sha(data)
    (OUT/"candidate_latest.json").write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="")
    return candidate

def raw_legacy_acceptance(candidate):
    with tempfile.TemporaryDirectory() as td:
        temp=pathlib.Path(td);install=temp/"install";sentinels=validation.seed_legacy_install(install);legacy=validation.legacy_module(temp)
        result=legacy._apply_remote(candidate,install,attempts=3,timeout=25,allow_test_sources=False)
        require(legacy._local_package_version(install)==VERSION,"Updater 4.4.43 no dejó manifest 4.4.49")
        require(legacy._installed_app_version(install)==VERSION,"Updater 4.4.43 no dejó app 4.4.49")
        require(legacy._installation_consistent(install),"Instalación Raw incoherente")
        for path,data in sentinels.items():require(path.read_bytes()==data,f"Se alteró {path.name}")
        require("app_base_4428.py" in (result.get("paths") or []),"Raw no instaló app_base")
    print("RAW_LEGACY_443_ACCEPTANCE_V4449_OK")

def main():
    # Primero corren TODAS las pruebas originales sobre el build semánticamente idéntico.
    validation.build();validation.contracts();validation.accepted_by_real_443();validation.launcher_selftests()
    print("VALIDATE_V4449_RUN2_OK")
    candidate=normalize_app_base_and_candidate()
    require(candidate.get("version")==VERSION,"candidate incorrecto")
    current=json.loads(fetch("https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json").decode("utf-8-sig"))
    require(version_tuple(current.get("version"))<=version_tuple(VERSION),f"Canal más nuevo: {current.get('version')}")

    git("config","user.name","github-actions[bot]");git("config","user.email","41898282+github-actions[bot]@users.noreply.github.com")
    git("add","updates/v4_4_49_agenda_flow_speed")
    staged=subprocess.check_output(["git","diff","--cached","--name-only"],cwd=ROOT,text=True).strip()
    if staged:
        git("commit","-m","release: corregir payload v4.4.49 normalizado")
        git("pull","--rebase","origin","main");git("push","origin","HEAD:main")

    for item in candidate["files"]:
        data=wait_payload(item)
        if item["path"]=="app.py":
            txt=data.decode("utf-8-sig");require('APP_VERSION = "4.4.49"' in txt,"Raw app incorrecta");require("Actualizar datos y atender" in txt,"Raw perdió flujo")
    raw_legacy_acceptance(candidate)

    latest=(json.dumps(candidate,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    (ROOT/"latest-v3.json").write_bytes(latest);(ROOT/"latest.json").write_bytes(latest)
    git("add","latest-v3.json","latest.json")
    staged=subprocess.check_output(["git","diff","--cached","--name-only"],cwd=ROOT,text=True).strip()
    if staged:
        git("commit","-m","release: publicar v4.4.49 agenda rápida y ficha existente")
        git("pull","--rebase","origin","main");git("push","origin","HEAD:main")
    print("PUBLISH_V4449_RUN2_OK")

if __name__=="__main__":main()
