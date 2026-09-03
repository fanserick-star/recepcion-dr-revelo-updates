from __future__ import annotations

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
OUT = ROOT / "updates" / "v4_4_54_slot_event_capture"
VERSION = "4.4.54"


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
            req=urllib.request.Request(url+sep+'rp='+str(time.time_ns()),headers={'Cache-Control':'no-cache','Pragma':'no-cache','User-Agent':'v4454-safe-release'})
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
        require(legacy._local_package_version(install)==VERSION,'Updater 4.4.43 no dejó manifest 4.4.54')
        require(legacy._installed_app_version(install)==VERSION,'Updater 4.4.43 no dejó app 4.4.54')
        require(legacy._installation_consistent(install),'Updater 4.4.43 dejó instalación incoherente')
        for path,data in sentinels.items(): require(path.read_bytes()==data,f'Updater tocó protegido: {path.name}')
        require('app_base_4428.py' in (result.get('paths') or []),'Raw no incluyó app_base_4428.py')
    print('RAW_LEGACY_443_ACCEPTANCE_V4454_OK')


def validate_slot_js(app_text: str) -> None:
    start=app_text.index('V4454_SLOT_EVENT_JS = r"""')+len('V4454_SLOT_EVENT_JS = r"""')
    end=app_text.index('\n"""\n    core.V460_OVERLAY_JS',start)
    js=app_text[start:end]
    with tempfile.TemporaryDirectory() as td:
        td=pathlib.Path(td)
        js_path=td/'slot.js'; js_path.write_text(js,encoding='utf-8',newline='')
        syntax=subprocess.run(['node','--check',str(js_path)],capture_output=True,text=True)
        require(syntax.returncode==0,f'JS v4.4.54 inválido: {syntax.stderr}')
        harness=td/'test.js'
        harness.write_text("""
global.window={openAgendaSlotPicker:function(f,h){global.called=[f,h]}};
global.document={addEventListener:function(){}};
global.setTimeout=function(fn){fn();};
require('./slot.js');
window.openAgendaSlotPicker('2026-09-17','10:00');
const s=window.__v4454SelectedAgendaSlot;
if(!s||s.fecha!=='2026-09-17'||s.hora!=='10:00')process.exit(3);
if(!global.called||global.called[0]!=='2026-09-17'||global.called[1]!=='10:00')process.exit(4);
console.log('V4454_EVENT_CAPTURE_OK');
""",encoding='utf-8')
        run=subprocess.run(['node',str(harness)],cwd=td,capture_output=True,text=True)
        require(run.returncode==0,f'Captura evento falló: {run.stdout}\n{run.stderr}')
        require('V4454_EVENT_CAPTURE_OK' in run.stdout,'Prueba no confirmó captura')
    print('V4454_EVENT_CAPTURE_OK')


def main() -> None:
    subprocess.run([sys.executable,str(HERE/'build_v4454.py')],cwd=ROOT,check=True)
    app_text=(OUT/'app.py').read_text(encoding='utf-8-sig')
    require('APP_VERSION = "4.4.54"' in app_text,'Versión app incorrecta')
    require('window.__v4454SelectedAgendaSlot' in app_text,'Falta almacenamiento directo de horario')
    require("[onclick*=\"openAgendaSlotPicker\"]" in app_text,'Falta captura de clic de horario')
    require('const slot=(remembered&&Date.now()-Number(remembered.ts||0)<300000?remembered:null)||slotFromModal(source);' in app_text,'Crear cita nueva no usa horario recordado')
    require('/api/agenda/unlinked/guarded' in app_text,'Perdió cita rápida')
    require('core.ConfirmafyAgendaItem(' in app_text,'Perdió cita staged')
    compile(app_text,'app.py','exec')
    validate_slot_js(app_text)
    print('V4454_CONTRACT_OK')

    candidate=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    current=json.loads(fetch('https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json').decode('utf-8-sig'))
    require(version_tuple(current.get('version'))<=version_tuple(VERSION),f"Canal más nuevo: {current.get('version')}")

    git('config','user.name','github-actions[bot]'); git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    git('add','updates/v4_4_54_slot_event_capture')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: payload v4.4.54 captura directa de horario')
        git('pull','--rebase','origin','main'); git('push','origin','HEAD:main')

    for item in candidate['files']:
        data=wait_payload(item)
        if item['path']=='app.py':
            text=data.decode('utf-8-sig')
            require('APP_VERSION = "4.4.54"' in text,'Raw app incorrecta')
            require('window.__v4454SelectedAgendaSlot' in text,'Raw perdió captura de horario')
            require('/api/agenda/unlinked/guarded' in text,'Raw perdió cita rápida')
    raw_legacy_acceptance(candidate)

    latest=(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    (ROOT/'latest-v3.json').write_bytes(latest); (ROOT/'latest.json').write_bytes(latest)
    git('add','latest-v3.json','latest.json')
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    if staged:
        git('commit','-m','release: publicar v4.4.54 captura directa del horario')
        git('pull','--rebase','origin','main'); git('push','origin','HEAD:main')
    print('PUBLISH_V4454_OK')


if __name__=='__main__': main()
