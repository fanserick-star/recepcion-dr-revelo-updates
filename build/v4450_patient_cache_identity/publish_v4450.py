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
OUT=ROOT/"updates"/"v4_4_50_patient_cache_identity"
VERSION="4.4.50"
sys.path.insert(0,str(HERE))
import validate_v4450 as validation


def require(cond: bool,msg: str)->None:
    if not cond: raise RuntimeError(msg)

def sha(data: bytes)->str:return hashlib.sha256(data).hexdigest()

def version_tuple(value: object)->tuple[int,...]:
    out=[]
    for part in str(value or "0").split('.'):
        try:out.append(int(part))
        except Exception:out.append(0)
    return tuple((out+[0,0,0,0])[:4])

def git(*args: str)->None:subprocess.run(["git",*args],cwd=ROOT,check=True)

def fetch(url: str,attempts: int=4,timeout: float=25.0)->bytes:
    last=None
    for i in range(max(1,attempts)):
        try:
            sep='&' if '?' in url else '?'
            req=urllib.request.Request(url+sep+'rp='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'v4450-safe-release'})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                require(getattr(r,'status',200)==200,f"HTTP {getattr(r,'status','?')}")
                return r.read()
        except Exception as exc:
            last=exc
            if i+1<attempts:time.sleep(min(4.0,0.6+i*0.6))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")

def wait_payload(item: dict,attempts: int=55)->bytes:
    last=None
    for i in range(attempts):
        try:
            urls=item.get('parts') or [item.get('url')]
            data=b''.join(fetch(str(u),attempts=1) for u in urls if u)
            if sha(data)==str(item.get('sha256') or ''):return data
            last=f"sha {sha(data)}"
        except Exception as exc:last=exc
        time.sleep(min(5.0,0.8+i*0.18))
    raise RuntimeError(f"Payload Raw no propagó {item.get('path')}: {last}")

def raw_legacy_acceptance(candidate: dict)->None:
    sys.path.insert(0,str(ROOT/'build'/'v4449_agenda_flow_speed'))
    import validate_v4449 as helpers
    with tempfile.TemporaryDirectory() as td:
        temp=pathlib.Path(td);install=temp/'install';sentinels=helpers.seed_legacy_install(install);legacy=helpers.legacy_module(temp)
        result=legacy._apply_remote(candidate,install,attempts=3,timeout=25,allow_test_sources=False)
        require(legacy._local_package_version(install)==VERSION,'Updater 4.4.43 no dejó manifest 4.4.50')
        require(legacy._installed_app_version(install)==VERSION,'Updater 4.4.43 no dejó app 4.4.50')
        require(legacy._installation_consistent(install),'Updater 4.4.43 dejó instalación incoherente')
        for path,data in sentinels.items():require(path.read_bytes()==data,f"Updater tocó protegido: {path.name}")
        require('app_base_4428.py' in (result.get('paths') or []),'Raw no incluyó app_base_4428.py')
    print('RAW_LEGACY_443_ACCEPTANCE_V4450_OK')

def main()->None:
    subprocess.run([sys.executable,str(HERE/'validate_v4450.py')],cwd=ROOT,check=True)
    candidate=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    require(candidate.get('version')==VERSION,'Versión candidata incorrecta')
    current=json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json').decode('utf-8-sig'))
    require(version_tuple(current.get('version'))<=version_tuple(VERSION),f"Canal más nuevo: {current.get('version')}")

    git('config','user.name','github-actions[bot]');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','updates/v4_4_50_patient_cache_identity')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: payload v4.4.50 cache e identidad de pacientes')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')

    for item in candidate['files']:
        data=wait_payload(item)
        if item['path']=='app.py':
            text=data.decode('utf-8-sig')
            require('APP_VERSION = "4.4.50"' in text,'Raw app incorrecta')
            require('/api/local-cache/reconcile-patients' in text,'Raw perdió reparación cache')
            require('activate-for-staged' in text,'Raw perdió guardia histórica staged')
            require('Paciente movido a Papelera' in text,'Raw perdió borrado seguro')
    raw_legacy_acceptance(candidate)

    latest=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (ROOT/'latest-v3.json').write_bytes(latest);(ROOT/'latest.json').write_bytes(latest)
    git('add','latest-v3.json','latest.json')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: publicar v4.4.50 pacientes sin fantasmas ni duplicados staged')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')
    require(json.loads((ROOT/'latest-v3.json').read_text(encoding='utf-8')).get('version')==VERSION,'latest-v3 local incorrecto')
    print('PUBLISH_V4450_OK')

if __name__=='__main__':main()
