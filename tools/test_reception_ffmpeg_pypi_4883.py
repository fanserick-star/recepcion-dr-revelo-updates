"""Test official PyPI SHA-256 verification and portable FFmpeg installation offline.

Never touches cloud, patients, app secrets, system FFmpeg or WhatsApp.
"""
import ast
import hashlib
import io
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import urllib.request
import urllib.parse
import zipfile
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
tree=ast.parse(source)
items={v.name:v for v in tree.body if isinstance(v,ast.FunctionDef)}
assert "_clinical_install_ffmpeg_pypi" in items
assert "_FFMPEG_PYPI_WHEELS" in source
assert "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a" in source
assert "196faa79366b4a82f95c0f4053191d2013f4714a715780f0ad2a68ff37483cc2" in source
assert 'if received>max_wheel:' in source
assert "hmac.compare_digest(digest.hexdigest(),expected_hash)" in source
assert 'actual_url.hostname!="files.pythonhosted.org"' in source
assert "os.replace(str(stage_path),str(target_dir/\"ffmpeg.exe\"))" in source
assert "Instalar FFmpeg aquí (sin requerir WinGet)" in ui
assert "_clinical_install_ffmpeg_winget if use_winget else _clinical_install_ffmpeg_pypi" in source
section=source.split("def _clinical_install_ffmpeg_pypi():",1)[1].split('@app.post("/api/clinical-delivery/ffmpeg/install")',1)[0]
assert "_send_template(" not in section and "_upload_r2(" not in section
assert "core.DATA_DIR" in section and "--scope" not in section
assert "ZipFile(package_path)" in section

class FakeWebResponse:
    def __init__(self,body,url):self.body=io.BytesIO(body);self.url=url
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return self.body.read(n)
    def geturl(self):return self.url

with tempfile.TemporaryDirectory(prefix="pypi_ffmpeg_4883_") as temp:
    storage=Path(temp)
    payload=b"MZ"+b"Q"* (1024*1024 + 100)
    packed=io.BytesIO()
    with zipfile.ZipFile(packed,"w",compression=zipfile.ZIP_DEFLATED) as wheel:
        wheel.writestr("imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.0.exe",payload)
    correct=packed.getvalue()
    sha=hashlib.sha256(correct).hexdigest()
    fakeurl="https://files.pythonhosted.org/packages/mock/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl"
    download_calls=[]
    def urlopen(url,timeout):
        assert url==fakeurl and timeout==45
        download_calls.append(url)
        return FakeWebResponse(correct,fakeurl)
    run_calls=[]
    def run(cmd,**opts):
        assert cmd[-1]=="-version"
        assert opts["timeout"]==20
        assert "shell" not in opts
        assert Path(cmd[0]).read_bytes()==payload
        run_calls.append(cmd)
        return SimpleNamespace(returncode=0)
    ns={
        "Path":Path,"core":SimpleNamespace(DATA_DIR=str(storage)),
        "struct":SimpleNamespace(calcsize=lambda fmt:8),
        "hashlib":hashlib,"hmac":__import__("hmac"),
        "shutil":SimpleNamespace(disk_usage=lambda _p:SimpleNamespace(free=1_000_000_000)),
        "os":os,"tempfile":tempfile,"urllib":__import__("urllib"),
        "zipfile":zipfile,
        "subprocess":SimpleNamespace(run=run,DEVNULL=subprocess.DEVNULL,
                                     CREATE_NO_WINDOW=0),
        "_FFMPEG_SETUP_LOCK":threading.Lock(),"_FFMPEG_SETUP":{"state":"running","detail":""},
        "_FFMPEG_PYPI_WHEELS":{"win_amd64":(fakeurl,sha,35*1024*1024)},
    }
    exec(compile(ast.Module(body=[items["_clinical_install_ffmpeg_pypi"]],type_ignores=[]),
                 "test_pypi_downloader","exec"),ns)
    with patch.object(urllib.request,"urlopen",side_effect=urlopen):
        ns["_clinical_install_ffmpeg_pypi"]()
    installed=storage/"tools"/"ffmpeg.exe"
    assert installed.read_bytes()==payload
    assert ns["_FFMPEG_SETUP"]["state"]=="ready"
    assert len(run_calls)==1 and len(download_calls)==1
    assert list((storage/"tools").glob("ffmpeg_verified_*.whl"))==[]
    assert list((storage/"tools").glob("ffmpeg_candidate_*.exe"))==[]
    # Tampering / hash mismatch must fail closed and NOT replace valid original.
    ns["_FFMPEG_SETUP"]={"state":"running","detail":""}
    ns["_FFMPEG_PYPI_WHEELS"]["win_amd64"]=(fakeurl,"f"*64,35*1024*1024)
    with patch.object(urllib.request,"urlopen",side_effect=urlopen):
        ns["_clinical_install_ffmpeg_pypi"]()
    assert installed.read_bytes()==payload
    assert ns["_FFMPEG_SETUP"]["state"]=="error"
    assert len(run_calls)==1, "Corrupted wheel should never execute"
    assert list((storage/"tools").glob("ffmpeg_verified_*.whl"))==[]
    assert list((storage/"tools").glob("ffmpeg_candidate_*.exe"))==[]
print("RECEPTION_FFMPEG_OFFLINE_VERIFIED_PYPI_BINARY_NO_WINGET_NO_PATIENTS_OK")
