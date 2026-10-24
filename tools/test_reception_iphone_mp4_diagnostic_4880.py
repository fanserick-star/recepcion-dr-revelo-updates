"""Synthetic offline MP4 atom/codec and Cloudflare Range=206 safety regression."""
import ast
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import re
import secrets
import urllib.request
import urllib.error
from datetime import datetime

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
functions={n.name:n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
assert "_mp4_atom_details" in functions and "_r2_synthetic_range_206" in functions
assert '@app.post("/api/clinical-delivery/patients/{pid}/archived-video/{video_id}/iphone-diagnostic")' in source
assert 'from clinical_video_library import _row_by_id,_local_file' in source
assert '_linked_patient(pid)' in source
assert 'await asyncio.to_thread(_r2_synthetic_range_206)' in source
assert "Diagnosticar reproducción en iPhone" in ui
assert "sendArchivedVideoTest(v,testPhone)" in ui
assert "CLINICAL_DELIVERY_LIVE_ENABLED" in source
assert "_send_template(" not in source.split("def _mp4_atom_details(",1)[1].split("# Real clinical video test:",1)[0]
assert "api('/api/clinical-delivery/patients/'+pid+'/archived-video/'+id+'/iphone-diagnostic',{method:'POST'})" in ui
assert "No se pudo completar el diagnóstico" in ui
def atom(kind,payload):
    return (len(payload)+8).to_bytes(4,"big")+kind+payload
def specimen(codec,moov_first):
    entry=(16).to_bytes(4,"big")+codec+b"\x00"*8
    stsd=atom(b"stsd",b"\x00"*4+(1).to_bytes(4,"big")+entry)
    moov=atom(b"moov",atom(b"trak",atom(b"mdia",atom(b"minf",atom(b"stbl",stsd)))))
    ftyp=atom(b"ftyp",b"isom"+b"\0"*12)
    mdat=atom(b"mdat",b"\0"*1024)
    return ftyp+(moov+mdat if moov_first else mdat+moov)
namespace={"Path":Path,"re":re}
code=compile(ast.Module(body=[functions["_mp4_atom_details"]],type_ignores=[]),"mp4_diag","exec")
exec(code,namespace)
analyze=namespace["_mp4_atom_details"]
for codec,at_start,expected_hint in [
    (b"avc1",True,"likely_compatible"),
    (b"mp4v",True,"possible_unsupported_codec"),
    (b"avc1",False,"likely_compatible"),
]:
    with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as f:
        f.write(specimen(codec,at_start))
        path=f.name
    try:
        result=analyze(path)
        assert result["codecs"]==[codec.decode()],result
        assert result["metadata_before_video"] is at_start
        assert result["iphone_codec_hint"]==expected_hint
        assert result["moov_found"]
        assert not {"patient_id","phone","full_path","private_url"} & result.keys()  # iphone_codec_hint is safe metadata
    finally:os.unlink(path)
with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as f:
    f.write(b"not valid mp4"*5)
    bad=f.name
try:
    try:analyze(bad)
    except ValueError:pass
    else:raise AssertionError("Reject invalid video magic")
finally:os.unlink(bad)

class HttpResp:
    status=206
    headers={"Content-Range":"bytes 0-1/126"}
    def __init__(self,content):self.content=content
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return self.content[:n]

tmpkeys=[]
deleted=[]
def fake_upload(filename,key,kind):
    assert key.startswith("clinical-temp/self-test/ios-range-")
    assert kind=="application/octet-stream"
    data=Path(filename).read_bytes()
    tmpkeys.append((key,data))
def fake_download(req,timeout):
    assert req.get_method()=="GET"
    assert req.headers.get("Range")=="bytes=0-1"
    assert tmpkeys
    expected=tmpkeys[-1][1]
    resp=HttpResp(expected[:2])
    resp.headers={"Content-Range":f"bytes 0-1/{len(expected)}"}
    return resp
ns={
    "_setup":lambda:{"ready_r2":True},
    "_upload_r2":fake_upload,"_r2_url":lambda method,key,expiry=180:"https://synthetic.invalid/mp4",
    "_delete_benchmark_r2":lambda key:deleted.append(key),
    "secrets":secrets,"tempfile":tempfile,"os":os,
    "urllib":__import__("urllib"),"TimeoutError":TimeoutError,
    "Path":Path
}
exec(compile(ast.Module(body=[functions["_r2_synthetic_range_206"]],type_ignores=[]),
             "range_diag","exec"),ns)
with patch.object(urllib.request,"urlopen",side_effect=fake_download):
    good=ns["_r2_synthetic_range_206"]()
assert good=={"status":"ok","range_206":True},good
assert deleted==[tmpkeys[0][0]]
assert len(tmpkeys)==1 and len(tmpkeys[0][1])==126
def wrong_status(req,timeout):
    r=fake_download(req,timeout)
    r.status=200
    return r
with patch.object(urllib.request,"urlopen",side_effect=wrong_status):
    not_good=ns["_r2_synthetic_range_206"]()
assert not_good=={"status":"incompatible","range_206":False}
assert len(deleted)==2
print("RECEPTION_IPHONE_CODEC_FASTSTART_R2_HTTP206_NO_VIDEO_UPLOAD_NO_WHATSAPP_OK")
