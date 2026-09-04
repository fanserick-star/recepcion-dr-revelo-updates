from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_58_report_turn_none_fix"
VERSION = "4.4.58"


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
            req=urllib.request.Request(url+sep+'rp='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'v4458-safe-release'})
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
        require(legacy._local_package_version(install)==VERSION,'Updater 4.4.43 no dejó manifest 4.4.58')
        require(legacy._installed_app_version(install)==VERSION,'Updater 4.4.43 no dejó app 4.4.58')
        require(legacy._installation_consistent(install),'Updater 4.4.43 dejó instalación incoherente')
        for path,data in sentinels.items(): require(path.read_bytes()==data,f'Updater tocó protegido: {path.name}')
        require('app_base_4428.py' in (result.get('paths') or []),'Raw no incluyó app_base_4428.py')
    print('RAW_LEGACY_443_ACCEPTANCE_V4458_OK')


def validate_full_report_logic(base_text: str) -> None:
    tree=ast.parse(base_text)
    wanted={'_v4457_counts_as_medical_turn','_v4457_consultation_turns','build_report_data'}
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
    require({n.name for n in nodes}==wanted,'Faltan funciones de reporte/turnos')
    mod=ast.Module(body=nodes,type_ignores=[]);ast.fix_missing_locations(mod)

    def is_procedure(v): return bool(str(getattr(v,'procedimiento',None) or '').strip())
    def p_dict(p): return {'id':p.id,'nombre':p.nombre}
    def v_dict(v): return {'id':v.id,'fecha':v.fecha,'procedimiento':v.procedimiento}
    ns={'is_procedure':is_procedure,'p_dict':p_dict,'v_dict':v_dict}
    exec(compile(mod,'report_logic','exec'),ns)

    class P:
        def __init__(self,pid,nombre): self.id=pid;self.nombre=nombre
    class V:
        def __init__(self,vid,pid,procedimiento=None,tipo='S',valor=20):
            self.id=vid;self.patient_id=pid;self.fecha=date(2026,9,3);self.procedimiento=procedimiento;self.tipo=tipo;self.valor=valor;self.observacion=''

    rows=[
        (V(1,50,'INSTILACION'),P(50,'VILLAMIL')),
        (V(2,40,None),P(40,'AROCA')),
        (V(3,40,'GASTROSCOPIA'),P(40,'AROCA')),
        (V(4,30,None),P(30,'TIPANTUNA')),
        (V(5,20,None),P(20,'JORGE')),
        (V(6,10,None),P(10,'ZAMBRANO')),
        (V(7,50,'DILATACION'),P(50,'VILLAMIL')),
    ]
    data=ns['build_report_data'](rows)
    by_patient={}
    for item in data['details']:
        by_patient.setdefault(item['patient_id'],set()).add(item['turno'])
    require(by_patient[50]=={None},'Paciente solo procedimiento recibió turno')
    require(by_patient[40]=={1} and by_patient[30]=={2} and by_patient[20]=={3} and by_patient[10]=={4},'Turnos de consulta incorrectos')
    require(data['consultations']==4 and data['P']==3,'Conteos de reporte cambiaron incorrectamente')
    require(data['patients']==5,'Pacientes atendidos cambió incorrectamente')
    print('V4458_FULL_REPORT_MIXED_OK')


def main() -> None:
    subprocess.run([sys.executable,str(HERE/'build_v4458.py')],cwd=ROOT,check=True)
    app_text=(OUT/'app.py').read_text(encoding='utf-8-sig')
    base_text=(OUT/'app_base_4428.py').read_text(encoding='utf-8-sig')
    require('APP_VERSION = "4.4.58"' in app_text,'Versión app incorrecta')
    require('turns[kv[0]] is None' in base_text,'No está el orden seguro para turnos None')
    require('turns = _v4457_consultation_turns(patient_days)' in base_text,'Se perdió turnos solo consulta')
    require("${num?num+'.':'—'}" in base_text,'Se perdió — visual de procedimientos')
    require('__v4456ReadablePatientError' in app_text,'Se perdió arreglo 4.4.56')
    validate_full_report_logic(base_text)
    compile(app_text,'app.py','exec');compile(base_text,'app_base_4428.py','exec')
    print('V4458_CONTRACT_OK')

    candidate=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    current=json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json').decode('utf-8-sig'))
    require(version_tuple(current.get('version'))<=version_tuple(VERSION),f"Canal más nuevo: {current.get('version')}")

    git('config','user.name','github-actions[bot]');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','updates/v4_4_58_report_turn_none_fix')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: payload v4.4.58 reparar reportes sin turno')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')

    for item in candidate['files']:
        data=wait_payload(item)
        if item['path']=='app.py':
            text=data.decode('utf-8-sig');require('APP_VERSION = "4.4.58"' in text,'Raw app incorrecta')
        if item['path']=='app_base_4428.py':
            text=data.decode('utf-8-sig');validate_full_report_logic(text)
    raw_legacy_acceptance(candidate)

    latest=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (ROOT/'latest-v3.json').write_bytes(latest);(ROOT/'latest.json').write_bytes(latest)
    git('add','latest-v3.json','latest.json')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: publicar v4.4.58 reportes turnos seguros')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')
    print('PUBLISH_V4458_OK')


if __name__=='__main__': main()
