from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
OUT=ROOT/"updates"/"v4_4_50_patient_cache_identity"
VERSION="4.4.50"
sys.path.insert(0,str(ROOT/"build"/"v4449_agenda_flow_speed"))
import validate_v4449 as legacy_helpers


def require(cond: bool,msg: str)->None:
    if not cond: raise AssertionError(msg)


def launcher_bytes(folder: pathlib.Path)->bytes:
    return b"".join((folder/f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1,5))


def build()->None:
    subprocess.run([sys.executable,str(HERE/"build_v4450.py")],cwd=ROOT,check=True)


def contracts()->None:
    app=(OUT/"app.py").read_text(encoding="utf-8-sig")
    base=(OUT/"app_base_4428.py").read_text(encoding="utf-8-sig")
    launcher=launcher_bytes(OUT).decode("utf-8-sig")
    compile(app,"app.py","exec");compile(base,"app_base_4428.py","exec");compile(launcher,"ABRIR_RECEPCION.py","exec")
    for marker in (
        'APP_VERSION = "4.4.50"',
        '_v4450_force_delete_patient_local',
        '/api/local-cache/reconcile-patients',
        '/api/historical/{hid}/activate-for-staged/{item_id}',
        'reused_by_staged_phone',
        'window.__v4450PatientCacheIdentity',
        'Paciente movido a Papelera',
        'currentRows=rows=>',
        'useHistoricalForStaged=async function',
        'window.__v4449AgendaFlowSpeed',
        'window.__v4446PhoneDuplicateGuard',
        '/api/agenda/appointments/guarded',
    ):
        require(marker in app,f"Falta contrato: {marker}")
    manifest=json.loads((OUT/"update_manifest.json").read_text(encoding="utf-8"))
    candidate=json.loads((OUT/"candidate_latest.json").read_text(encoding="utf-8"))
    expected=["app.py","app_base_4428.py","ABRIR_RECEPCION.py","update_manifest.json"]
    require(manifest.get("version")==VERSION,"Manifest incorrecto")
    require(manifest.get("required_dependencies")==["app_base_4428.py"],"Dependencia incompleta")
    require([x.get("path") for x in candidate.get("files",[])]==expected,"Candidate incompleto")
    start=app.index('V4450_PATIENT_CACHE_JS = r"""')+len('V4450_PATIENT_CACHE_JS = r"""')
    end=app.index('\n"""\n\n    core.V460_OVERLAY_JS',start)
    js=app[start:end]
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"v4450.js";p.write_text(js,encoding="utf-8",newline="")
        r=subprocess.run(["node","--check",str(p)],text=True,capture_output=True)
        require(r.returncode==0,f"JS inválido: {r.stderr}")
    print("V4450_CONTRACT_OK")


def legacy_acceptance()->None:
    candidate=json.loads((OUT/"candidate_latest.json").read_text(encoding="utf-8"))
    server,base=legacy_helpers.start_server()
    try:
        server.RequestHandlerClass.files=legacy_helpers.localize_candidate(candidate,OUT,base)
        with tempfile.TemporaryDirectory() as td:
            temp=pathlib.Path(td);install=temp/"install";sentinels=legacy_helpers.seed_legacy_install(install);legacy=legacy_helpers.legacy_module(temp)
            result=legacy.check_and_apply_update(install,base+"/manifest",attempts=1,timeout=8,allow_test_sources=True)
            require(result.get("ok") and result.get("updated"),f"Updater 4.4.43 rechazó v4.4.50: {result}")
            require(legacy._local_package_version(install)==VERSION,"Manifest final incorrecto")
            require(legacy._installed_app_version(install)==VERSION,"app final incorrecta")
            require(legacy._installation_consistent(install),"Instalación incoherente")
            for path,data in sentinels.items():require(path.read_bytes()==data,f"Se alteró protegido: {path.name}")
    finally:
        server.shutdown();server.server_close()
    print("V4450_ACCEPTED_BY_LEGACY_443")


def launcher_selftests()->None:
    with tempfile.TemporaryDirectory() as td:
        path=pathlib.Path(td)/"ABRIR_RECEPCION.py";path.write_bytes(launcher_bytes(OUT))
        proc=subprocess.run([sys.executable,str(path),"--self-test-core"],cwd=td,text=True,capture_output=True,timeout=100)
        require(proc.returncode==0,f"Launcher self-test falló: {proc.stdout}\n{proc.stderr}")
        require("SELFTEST OK:" in proc.stdout,"Launcher no reportó SELFTEST OK")
    print("V4450_LAUNCHER_SELFTESTS_OK")


def main()->None:
    build();contracts();legacy_acceptance();launcher_selftests();print("VALIDATE_V4450_OK")

if __name__=="__main__":main()
