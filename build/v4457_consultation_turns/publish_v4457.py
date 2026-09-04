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

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_57_consultation_turns"
VERSION = "4.4.57"


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
            req=urllib.request.Request(url+sep+'rp='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'v4457-safe-release'})
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
        require(legacy._local_package_version(install)==VERSION,'Updater 4.4.43 no dejó manifest 4.4.57')
        require(legacy._installed_app_version(install)==VERSION,'Updater 4.4.43 no dejó app 4.4.57')
        require(legacy._installation_consistent(install),'Updater 4.4.43 dejó instalación incoherente')
        for path,data in sentinels.items(): require(path.read_bytes()==data,f'Updater tocó protegido: {path.name}')
        require('app_base_4428.py' in (result.get('paths') or []),'Raw no incluyó app_base_4428.py')
    print('RAW_LEGACY_443_ACCEPTANCE_V4457_OK')


def validate_python_turn_logic(base_text: str) -> None:
    tree=ast.parse(base_text)
    nodes=[]
    for name in ('_v4457_counts_as_medical_turn','_v4457_consultation_turns'):
        node=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        require(node is not None,f'No se encontró helper {name}')
        nodes.append(node)
    mod=ast.Module(body=nodes,type_ignores=[]);ast.fix_missing_locations(mod)
    ns={}
    exec(compile(mod,'turn_helpers','exec'),ns)
    fn=ns['_v4457_consultation_turns']

    class V:
        def __init__(self, vid, procedimiento=None):
            self.id=vid;self.procedimiento=procedimiento

    # Mismo patrón de la foto: 4 pacientes con consulta y 1 con solo procedimientos.
    d='2026-09-03'
    patient_days={
        (d,10):[(V(6,None),None)],                         # Zambrano -> 4
        (d,20):[(V(5,''),None)],                           # Jorge -> 3
        (d,30):[(V(4,None),None)],                         # Tipantuna -> 2
        (d,40):[(V(2,None),None),(V(3,'GASTROSCOPIA'),None)], # Aroca -> 1
        (d,50):[(V(1,'INSTILACION'),None),(V(7,'DILATACION'),None),(V(8,'GASTROSCOPIA'),None)], # Villamil -> sin turno
    }
    turns=fn(patient_days)
    require(turns[(d,40)]==1,'Consulta + procedimiento no quedó como turno 1')
    require(turns[(d,30)]==2 and turns[(d,20)]==3 and turns[(d,10)]==4,'Numeración de consultas incorrecta')
    require(turns[(d,50)] is None,'Procedimiento aislado todavía consume turno')
    require(len([x for x in turns.values() if x is not None])==4,'Cantidad de turnos médicos incorrecta')
    print('V4457_PY_TURN_LOGIC_OK')


def validate_js_turn_logic(base_text: str) -> None:
    start=base_text.index('  function v4457ConsultationTurnMap(groups){')
    end=base_text.index('  function remasterHomeTable(rows){',start)
    helper=base_text[start:end]
    with tempfile.TemporaryDirectory() as td:
        td=pathlib.Path(td)
        harness=td/'turns.js'
        harness.write_text(helper+r"""
const zam={visits:[{procedimiento:null}]};
const jorge={visits:[{procedimiento:''}]};
const tip={visits:[{procedimiento:null}]};
const aroca={visits:[{procedimiento:null},{procedimiento:'GASTROSCOPIA'}]};
const vill={visits:[{procedimiento:'INSTILACION'},{procedimiento:'DILATACION'},{procedimiento:'GASTROSCOPIA'}]};
const groups=[zam,jorge,tip,aroca,vill];
const m=v4457ConsultationTurnMap(groups);
if(m.get(aroca)!==1||m.get(tip)!==2||m.get(jorge)!==3||m.get(zam)!==4)process.exit(2);
if(m.has(vill))process.exit(3);
console.log('V4457_JS_TURN_LOGIC_OK');
""",encoding='utf-8',newline='')
        syntax=subprocess.run(['node','--check',str(harness)],capture_output=True,text=True)
        require(syntax.returncode==0,f'JS turno inválido: {syntax.stderr}')
        run=subprocess.run(['node',str(harness)],capture_output=True,text=True)
        require(run.returncode==0,f'Prueba JS turno falló: {run.stdout}\n{run.stderr}')
        require('V4457_JS_TURN_LOGIC_OK' in run.stdout,'JS no confirmó numeración de consultas')
    require("${num?num+'.':'—'}" in base_text,'La UI no muestra — para procedimiento sin turno')
    require('num=turnMap.get(g)||null' in base_text,'La tabla sigue usando el total de pacientes para N.º')
    print('V4457_JS_TURN_LOGIC_OK')


def main() -> None:
    subprocess.run([sys.executable,str(HERE/'build_v4457.py')],cwd=ROOT,check=True)
    app_text=(OUT/'app.py').read_text(encoding='utf-8-sig')
    base_text=(OUT/'app_base_4428.py').read_text(encoding='utf-8-sig')
    require('APP_VERSION = "4.4.57"' in app_text,'Versión app incorrecta')
    require('fecha_nacimiento: Optional[str] = None' in base_text,'Se perdió arreglo 4.4.56 de nacimiento')
    require('__v4456ReadablePatientError' in app_text,'Se perdió guardia 4.4.56 de errores de paciente')
    require('turns = _v4457_consultation_turns(patient_days)' in base_text,'Reporte no usa turnos solo consulta')
    require('first_id = min(v.id for v, _ in items)' not in base_text,'Quedó numeración antigua que cuenta procedimientos')
    validate_python_turn_logic(base_text)
    validate_js_turn_logic(base_text)
    for marker in ('/api/agenda/unlinked/guarded','window.__v4454SelectedAgendaSlot','PAYMENT_SENTINELS','_v4450_mirror_patient_to_local','Actualizar datos y atender'):
        require(marker in app_text,f'Se perdió arreglo acumulativo: {marker}')
    compile(app_text,'app.py','exec');compile(base_text,'app_base_4428.py','exec')
    print('V4457_CONTRACT_OK')

    candidate=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    current=json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json').decode('utf-8-sig'))
    require(version_tuple(current.get('version'))<=version_tuple(VERSION),f"Canal más nuevo: {current.get('version')}")

    git('config','user.name','github-actions[bot]');git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','updates/v4_4_57_consultation_turns')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: payload v4.4.57 turnos solo consultas')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')

    for item in candidate['files']:
        data=wait_payload(item)
        if item['path']=='app.py':
            text=data.decode('utf-8-sig')
            require('APP_VERSION = "4.4.57"' in text,'Raw app incorrecta')
            require('__v4456ReadablePatientError' in text,'Raw perdió guardia de paciente')
        if item['path']=='app_base_4428.py':
            text=data.decode('utf-8-sig')
            validate_python_turn_logic(text)
            validate_js_turn_logic(text)
    raw_legacy_acceptance(candidate)

    latest=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (ROOT/'latest-v3.json').write_bytes(latest);(ROOT/'latest.json').write_bytes(latest)
    git('add','latest-v3.json','latest.json')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: publicar v4.4.57 turnos solo consultas')
        git('pull','--rebase','origin','main');git('push','origin','HEAD:main')
    print('PUBLISH_V4457_OK')


if __name__=='__main__': main()
