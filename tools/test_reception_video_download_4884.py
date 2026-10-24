"""Offline private R2 MP4 download: attachment headers and fail-closed WhatsApp."""
import ast
from pathlib import Path
from types import SimpleNamespace
import tempfile
import urllib
import urllib.request
from unittest.mock import patch
import re

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
tree=ast.parse(source)
func={v.name:v for v in tree.body if isinstance(v,ast.FunctionDef)}
assert "_upload_r2" in func and "_verify_benchmark_r2" in func
assert "Content-Disposition" in source
assert "attachment; filename=" in source
assert "require_download=True" in source
assert "Enviar ESTE video para DESCARGAR a MI WhatsApp de pruebas" in ui
assert "La descarga del MP4 original funciona sin FFmpeg" in ui
section=source.split("def _send_archived_video_to_test_phone(",1)[1].split("@app.post(",1)[0]
assert "_delivery_faststart_copy(" not in section
assert "_faststart_ffmpeg_path(" not in section
assert "_verify_benchmark_r2(key,expected,require_download=True)" in section
assert "_send_template(" in section
assert section.index("_verify_benchmark_r2(")<section.index("_send_template(")
assert 'test_mode=True' in section
assert "CLINICAL_DELIVERY_LIVE_ENABLED" in source
assert "hmac.compare_digest(raw,allow)" in source
assert "patient_authorized_staff_delivery" in source

calls=[]
class Response:
    status=200
    def read(self,n):return b""
class Connection:
    def __init__(self,host,timeout):
        assert host=="test.r2.cloudflarestorage.com"
        self.headers={}
        self.sent=0
        calls.append(self)
    def putrequest(self,verb,url):
        assert verb=="PUT"
        assert "/clinical-temp/" in url
    def putheader(self,key,value):self.headers[key]=value
    def endheaders(self):pass
    def send(self,data):self.sent+=len(data)
    def getresponse(self):return Response()
    def close(self):pass
env={
    "Path":Path,
    "re":re,
    "urllib":urllib,
    "http":SimpleNamespace(client=SimpleNamespace(HTTPSConnection=Connection)),
    "_r2_url":lambda method,key,expiration=3600:
        "https://test.r2.cloudflarestorage.com/dr-revelo-clinical-2026/"+key+"?fake=signed",
}
module=ast.Module(body=[func["_upload_r2"],func["_verify_benchmark_r2"]],type_ignores=[])
exec(compile(module,"offline_download_contract","exec"),env)
with tempfile.NamedTemporaryFile(suffix=".mp4") as file:
    file.write(b"\x00\x00\x00\x18ftypisom"+b"synthetic" * 1000)
    file.flush()
    size=Path(file.name).stat().st_size
    env["_upload_r2"](file.name,"clinical-temp/authorized-test/synthetic.mp4","video/mp4")
    assert calls[-1].sent==size
    assert calls[-1].headers["Content-Type"]=="video/mp4"
    assert calls[-1].headers["Content-Disposition"]=='attachment; filename="Videocistoscopia.mp4"'
    assert calls[-1].headers["Cache-Control"]=="private, no-store"
    env["_upload_r2"](file.name,"clinical-temp/speed-test/synthetic.mp4","video/mp4")
    assert calls[-1].headers["Content-Disposition"].startswith("attachment;")
    env["_upload_r2"](file.name,"clinical-temp/self-test/synthetic.pdf","application/pdf")
    assert "Content-Disposition" not in calls[-1].headers

class HeadResponse:
    status=200
    def __init__(self,headers):self.headers=headers
    def __enter__(self):return self
    def __exit__(self,*_args):return False
def read_headers(headers,required):
    def responder(request,timeout):
        assert request.get_method()=="HEAD" and timeout==30
        return HeadResponse(headers)
    with patch.object(urllib.request,"urlopen",side_effect=responder):
        return env["_verify_benchmark_r2"]("clinical-temp/authorized-test/synthetic.mp4",
                                            12345,require_download=required)
valid={"Content-Length":"12345","Content-Type":"video/mp4",
       "Content-Disposition":'attachment; filename="Videocistoscopia.mp4"'}
assert read_headers(valid,True) is True
assert read_headers({"Content-Length":"12345"},False) is True
for broken in [
    {**valid,"Content-Disposition":"inline"},
    {**valid,"Content-Disposition":""},
    {**valid,"Content-Type":"application/octet-stream"},
    {**valid,"Content-Length":"999"},
]:
    try:read_headers(broken,True)
    except RuntimeError:pass
    else:raise AssertionError("Reject unsuitable real MP4 download metadata before Meta")
print("CLINICAL_R2_ORIGINAL_MP4_DOWNLOAD_ATTACHMENT_NO_FFMPEG_NO_META_OFFLINE_OK")
