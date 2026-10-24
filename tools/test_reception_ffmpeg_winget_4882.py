"""Offline installer contract: explicit loopback and fixed WinGet package, no patients."""
import ast
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
src=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
nodes={n.name:n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)}
names=["_clinical_install_local_only","_clinical_find_winget","_clinical_install_ffmpeg_winget"]
assert all(n in nodes for n in names)
assert '"/api/clinical-delivery/ffmpeg/install"' in src
assert '"/api/clinical-delivery/ffmpeg/status"' in src
assert '"ffmpeg_available":bool(_faststart_ffmpeg_path())' in src
assert 'Gyan.FFmpeg' in src and '"9.0.2"' in src
assert '"--accept-package-agreements"' in src
assert '"--accept-source-agreements"' in src
assert '"--source","winget"' in src
assert '"--scope","user"' in src
assert "background_tasks.add_task(_clinical_install_ffmpeg_winget)" in src
assert "Instalar FFmpeg en esta PC (Windows)" in ui
assert "window.confirm('INSTALAR FFMPEG EN ESTA PC" in ui
assert 'patient_authorized_staff_delivery:true' in ui
assert 'CLINICAL_DELIVERY_LIVE_ENABLED' in src
assert 'shutil.which("winget")' in src
assert 'WinGet"/"Links"/"ffmpeg.exe"' in src
assert 'packages.glob("Gyan.FFmpeg_*")' in src
assert "_send_template(" not in src.split("# FFmpeg installation is an EXPLICIT",1)[1].split("def _delivery_faststart_copy(",1)[0]
assert "_upload_r2(" not in src.split("# FFmpeg installation is an EXPLICIT",1)[1].split("def _delivery_faststart_copy(",1)[0]
assert 'request.client' not in ui

with tempfile.TemporaryDirectory() as folder:
    base=Path(folder)
    winget=base/"winget.exe"
    winget.write_bytes(b"synthetic_win_get_binary")
    ffmpeg=base/"ffmpeg.exe"
    ffmpeg.write_bytes(b"synthetic_ffmpeg_binary")
    run_calls=[]
    ready=[False]
    def fake_run(args,**kwargs):
        run_calls.append((args,kwargs))
        if args[0]==str(winget.resolve()):
            assert args[1:5]==["install","--exact","--id","Gyan.FFmpeg"]
            assert args[5:7]==["--version","9.0.2"]
            assert args[7:9]==["--source","winget"]
            assert args[9:11]==["--scope","user"]
            assert kwargs.get("timeout")==420
            assert "shell" not in kwargs
            assert kwargs.get("stdout")==subprocess.DEVNULL
            assert kwargs.get("stderr")==subprocess.DEVNULL
            ready[0]=True
            return SimpleNamespace(returncode=0)
        assert args==[str(ffmpeg),"-version"]
        assert kwargs.get("timeout")==15
        return SimpleNamespace(returncode=0)
    nspace={
        "os":SimpleNamespace(name="nt",environ={}),
        "Path":Path,
        "shutil":SimpleNamespace(which=lambda value:str(winget) if value=="winget" else None),
        "subprocess":SimpleNamespace(run=fake_run,DEVNULL=subprocess.DEVNULL,CREATE_NO_WINDOW=0,
                                    SubprocessError=subprocess.SubprocessError),
        "_FFMPEG_SETUP_LOCK":threading.Lock(),
        "_FFMPEG_SETUP":{"state":"running","detail":""},
        "_FFMPEG_WINGET_PACKAGE":"Gyan.FFmpeg",
        "_FFMPEG_WINGET_VERSION":"9.0.2",
        "_faststart_ffmpeg_path":lambda:str(ffmpeg) if ready[0] else None,
        "core":SimpleNamespace(HTTPException=lambda code,reason:Exception(str(code)+" "+reason)),
    }
    astmod=ast.Module(body=[nodes[n] for n in names],type_ignores=[])
    exec(compile(astmod,"offline_winget_setup","exec"),nspace)
    check=nspace["_clinical_install_local_only"]
    check(SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")))
    try:
        check(SimpleNamespace(client=SimpleNamespace(host="192.168.1.4")))
    except Exception as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("LAN caller must be denied")
    assert nspace["_clinical_find_winget"]()==str(winget.resolve())
    nspace["_clinical_install_ffmpeg_winget"]()
    assert nspace["_FFMPEG_SETUP"]["state"]=="ready"
    assert len(run_calls)==2

    def rejected(args,**kwargs):
        return SimpleNamespace(returncode=1)
    nspace["_subprocess"]=None
    nspace["subprocess"].run=rejected
    nspace["_FFMPEG_SETUP"]={"state":"running","detail":""}
    ready[0]=False
    nspace["_clinical_install_ffmpeg_winget"]()
    assert nspace["_FFMPEG_SETUP"]["state"]=="error"
    assert "Gyan.FFmpeg" not in nspace["_FFMPEG_SETUP"]["detail"]
    assert not ready[0]
print("RECEPTION_FFMPEG_LOCAL_WINGET_MANUAL_INSTALL_NO_CLINICAL_SENDING_OFFLINE_OK")
