from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request
import hashlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_56_patient_validation_origin_fix"
VERSION = "4.4.56"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version_tuple(value: object) -> tuple[int, ...]:
    out=[]
    for part in str(value or '0').split('.'):
        try: out.append(int(part))
        except Exception: out.append(0)
    return tuple((out+[0,0,0,0])[:4])


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 4, timeout: float = 25.0) -> bytes:
    last=None
    for i in range(attempts):
        try:
            sep='&' if '?' in url else '?'
            req=urllib.request.Request(url+sep+'rp='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'v4456-safe-release'})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                require(getattr(r,'status',200)==200,'HTTP inválido')
                return r.read()
        except Exception as exc:
            last=exc
            if i+1<attempts: time.sleep(1+i*.5)
    raise RuntimeError(f'No se pudo descargar {url}: {last}')


def wait_payload(item: dict, attempts: int = 50) -> bytes:
    last=None
    for i in range(attempts):
        try:
            urls=item.get('parts') or [item.get('url')]
            data=b''.join(fetch(str(u),attempts=1) for u in urls if u)
            if sha(data)==str(item.get('sha256') or ''): return data
            last='sha '+sha(data)
        except Exception as exc: last=exc
        time.sleep(min(4.0,.8+i*.15))
    raise RuntimeError(f"Payload Raw no propagó {item.get('path')}: {last}")


def raw_legacy_acceptance(candidate: dict) -> None:
    sys.path.insert(0,str(ROOT/'build'/'v4449_agenda_flow_speed'))
    import validate_v4449 as helpers
    with tempfile.TemporaryDirectory() as td:
        temp=pathlib.Path(td); install=temp/'install'
        sentinels=helpers.seed_legacy_install(install)
        legacy=helpers.legacy_module(temp)
        result=legacy._apply_remote(candidate,install,attempts=3,timeout=25,allow_test_sources=False)
        require(legacy._local_package_version(install)==VERSION,'Updater 4.4.43 no dejó manifest 4.4.56')
        require(legacy._installed_app_version(install)==VERSION,'Updater 4.4.43 no dejó app 4.4.56')
        require(legacy._installation_consistent(install),'Updater 4.4.43 dejó instalación incoherente')
        for path,data in sentinels.items(): require(path.read_bytes()==data,f'Updater tocó protegido: {path.name}')
        require('app_base_4428.py' in (result.get('paths') or []),'Raw no incluyó app_base_4428.py')
    print('RAW_LEGACY_443_ACCEPTANCE_V4456_OK')


def validate_patient_model(base_text: str) -> None:
    start=base_text.index('class PatientIn(BaseModel):')
    end=base_text.index('\n\nclass ',start+10)
    block=base_text[start:end]
    require('fecha_nacimiento: Optional[str] = None' in block,'PatientIn todavía valida nacimiento como date antes del normalizador')
    require('fecha_nacimiento: Optional[date] = None' not in block,'PatientIn conserva date prematuro')
    require('def normalize_patient_payload(data) -> dict:' in base_text,'Falta normalizador paciente')
    require('values["fecha_nacimiento"] = date.fromisoformat' in base_text,'Falta conversión final a date')
    print('V4456_PATIENT_MODEL_PREVALIDATION_OK')


def validate_error_guard_js(app_text: str) -> None:
    start=app_text.index('V4456_PATIENT_ERROR_JS = r"""')+len('V4456_PATIENT_ERROR_JS = r"""')
    end=app_text.index('\n"""\n    core.V460_OVERLAY_JS',start)
    js=app_text[start:end]
    with tempfile.TemporaryDirectory() as td:
        td=pathlib.Path(td)
        js_path=td/'patient_error.js';js_path.write_text(js,encoding='utf-8',newline='')
        syntax=subprocess.run(['node','--check',str(js_path)],capture_output=True,text=True)
        require(syntax.returncode==0,f'JS v4.4.56 inválido: {syntax.stderr}')
        harness=td/'test.js'
        harness.write_text(r"""
let shown=[];
function response(data){return {ok:false,status:422,clone(){return {json:async()=>data}}};}
global.window={
  fetch:async()=>response({detail:[{loc:['body','fecha_nacimiento'],msg:'Input should be a valid date or datetime'}]}),
  rpNotice:(m)=>shown.push(String(m)),
  alert:(m)=>shown.push(String(m))
};
require('./patient_error.js');
(async()=>{
  if(typeof window.__v4456ReadablePatientError!=='function')process.exit(2);
  await window.fetch('/api/patients',{method:'POST'});
  window.rpNotice('[object Object]');
  if(!shown[0]||shown[0].includes('[object Object]'))process.exit(3);
  if(!shown[0].includes('Fecha de nacimiento'))process.exit(4);
  if(!shown[0].includes('dd/mm/aaaa'))process.exit(5);
  shown=[];
  window.rpNotice({detail:[{loc:['body','correo'],msg:'Correo no válido'}]});
  if(!shown[0]||!shown[0].includes('Correo')||shown[0].includes('[object Object]'))process.exit(6);
  shown=[];
  window.alert({message:'[object Object]'});
  if(!shown[0]||shown[0].includes('[object Object]'))process.exit(7);
  console.log('V4456_RPNOTICE_ERROR_ORIGIN_OK');
})().catch(()=>process.exit(9));
""",encoding='utf-8')
        run=subprocess.run(['node',str(harness)],cwd=td,capture_output=True,text=True)
        require(run.returncode==0,f'Prueba rpNotice/fetch falló: {run.stdout}\n{run.stderr}')
        require('V4456_RPNOTICE_ERROR_ORIGIN_OK' in run.stdout,'No se confirmó recuperación del error estructurado')
    print('V4456_RPNOTICE_ERROR_ORIGIN_OK')


def main() -> None:
    subprocess.run([sys.executable,str(HERE/'build_v4456.py')],cwd=ROOT,check=True)
    app_text=(OUT/'app.py').read_text(encoding='utf-8-sig')
    base_text=(OUT/'app_base_4428.py').read_text(encoding='utf-8-sig')
    require('APP_VERSION = "4.4.56"' in app_text,'Versión app incorrecta')
    require('window.__v4456ReadablePatientError=readable' in app_text,'Falta guardia real de rpNotice')
    require('__v4456LastHttpError' in app_text,'Falta captura de detail HTTP')
    require('_v4455_normalize_birth_date_text' in app_text,'Se perdió normalizador dd/mm/aaaa previo')
    validate_patient_model(base_text)
    validate_error_guard_js(app_text)
    for marker in ('/api/agenda/unlinked/guarded','window.__v4454SelectedAgendaSlot','PAYMENT_SENTINELS','_v4450_mirror_patient_to_local','Actualizar datos y atender'):
        require(marker in app_text,f'Se perdió arreglo acumulativo: {marker}')
    compile(app_text,'app.py','exec');compile(base_text,'app_base_4428.py','exec')
    print('V4456_CONTRACT_OK')

    candidate=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    current=json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json').decode('utf-8-sig'))
    require(version_tuple(current.get('version'))<=version_tuple(VERSION),f"Canal más nuevo: {current.get('version')}")

    git('config','user.name','github-actions[bot]');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','updates/v4_4_56_patient_validation_origin_fix')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: payload v4.4.56 error paciente en origen')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')

    for item in candidate['files']:
        data=wait_payload(item)
        if item['path']=='app.py':
            text=data.decode('utf-8-sig')
            require('APP_VERSION = "4.4.56"' in text,'Raw app incorrecta')
            require('__v4456ReadablePatientError' in text,'Raw perdió guardia de error')
        if item['path']=='app_base_4428.py':
            text=data.decode('utf-8-sig')
            validate_patient_model(text)
    raw_legacy_acceptance(candidate)

    latest=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (ROOT/'latest-v3.json').write_bytes(latest);(ROOT/'latest.json').write_bytes(latest)
    git('add','latest-v3.json','latest.json')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: publicar v4.4.56 corrección real crear paciente')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')
    print('PUBLISH_V4456_OK')


if __name__=='__main__': main()
