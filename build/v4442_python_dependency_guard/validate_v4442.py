from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_42_python_dependency_guard"


def require(cond, msg):
    if not cond:
        raise AssertionError(msg)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def launcher_bytes() -> bytes:
    return b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1,5))


def load(path: pathlib.Path, name: str):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec and spec.loader, "No carga launcher")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def static_contract():
    c=json.loads((OUT/'candidate_latest.json').read_text(encoding='utf-8'))
    require(c['version']=='4.4.42' and c['app_version']=='4.4.36','Versiones incorrectas')
    expected=["ABRIR_RECEPCION.py","app_base_4428.py","app.py","static/app.js","static/index.html","update_manifest.json"]
    require([x['path'] for x in c['files']]==expected,'Release no acumulativo')
    require(sha(OUT/'app.py')=='2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e','app.py cambió')
    require(sha(OUT/'app_base_4428.py')=='e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba','base cambió')
    inner=json.loads((OUT/'update_manifest.json').read_text(encoding='utf-8'))
    require(inner.get('required_python_packages')==[{'import':'pg8000','pip':'pg8000==1.31.2'}],'Falta pg8000 declarado')
    text=launcher_bytes().decode('utf-8-sig')
    compile(text,'ABRIR_RECEPCION.py','exec')
    require('_rp_ensure_python_runtime' in text and 'required_python_packages' in text,'Falta guardia Python')
    require('_rp_v4437_required_files' in text and '_rp_diag_upload_via_venv' in text and '_choose_app_port' in text,'Se perdió blindaje previo')
    print('V4442_STATIC_OK')


def real_repair_test():
    if sys.platform != 'win32':
        print('SKIP real_repair_test non-Windows')
        return
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'install'; root.mkdir()
        (root/'data').mkdir()
        (root/'ABRIR_RECEPCION.py').write_bytes(launcher_bytes())
        (root/'update_manifest.json').write_text(json.dumps({
            'product':'recepcion-pacientes','version':'4.4.42','app_version':'4.4.36','runtime_version':'4.4.36',
            'required_python_packages':[{'import':'pg8000','pip':'pg8000==1.31.2'}]
        }),encoding='utf-8')
        venv=root/'.venv'
        subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
        py=venv/'Scripts'/'python.exe'
        pre=subprocess.run([str(py),'-c','import pg8000'],capture_output=True)
        require(pre.returncode!=0,'Venv sintético ya tenía pg8000; prueba inválida')
        m=load(root/'ABRIR_RECEPCION.py','v4442_guard')
        repaired=m._rp_ensure_python_runtime(root,py)
        require(repaired==['pg8000'],f'No reparó pg8000: {repaired}')
        ok=subprocess.run([str(py),'-c','import pg8000; print(pg8000.__version__)'],capture_output=True,text=True)
        require(ok.returncode==0,'pg8000 no importó después de reparar')
        require(ok.stdout.strip()=='1.31.2',f'Versión pg8000 inesperada: {ok.stdout!r}')
        repaired2=m._rp_ensure_python_runtime(root,py)
        require(repaired2==[],'Segundo arranque reinstaló innecesariamente')
        require(not (root/'.env').exists(),'Creó .env inesperadamente')
        require(list((root/'data').iterdir()),'Debe existir launcher_errors.log de la reparación')
        print('V4442_REAL_PG8000_REPAIR_OK')


def selftests():
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)/'install'; root.mkdir()
        launcher=root/'ABRIR_RECEPCION.py'; launcher.write_bytes(launcher_bytes())
        p=subprocess.run([sys.executable,str(launcher),'--self-test-core'],cwd=root,capture_output=True,text=True,timeout=180)
        print(p.stdout,end='')
        if p.returncode: print(p.stderr,end='')
        require(p.returncode==0 and 'SELFTEST OK' in p.stdout,'Selftests históricos fallaron')
        print('V4442_LAUNCHER_SELFTEST_OK')


def main():
    subprocess.run([sys.executable,str(ROOT/'build'/'v4442_python_dependency_guard'/'build_v4442.py')],cwd=ROOT,check=True)
    static_contract()
    real_repair_test()
    selftests()
    print('VALIDATE_V4442_OK')


if __name__=='__main__':
    main()
