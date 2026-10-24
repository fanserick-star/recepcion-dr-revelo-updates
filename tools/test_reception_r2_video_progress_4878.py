"""Offline 4.8.78 clinical video upload benchmark; never reads patients or sends WhatsApp."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ast
import hashlib
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.parse

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
tree=ast.parse(source)
lookup={v.name:v for v in tree.body if isinstance(v,ast.FunctionDef)}
names=["_upload_r2","_progress_set","_progress_snapshot",
       "_upload_progress_hook","_r2_video_benchmark"]
assert all(x in lookup for x in names)
assert "video-speed-test/start" in source
assert "video-speed-test/{job_id}" in source
assert "video-speed-test/{job_id}/upload" in source
assert "upload_consent" in source and "confirmed_patient" in source
assert 'if not _setup()["ready_r2"]' in source
assert 'CLINICAL_DELIVERY_LIVE_ENABLED' in source
assert '"clinical-temp/speed-test/"' in source
assert 'asyncio.to_thread(_r2_video_benchmark,job_id,tmp)' in source
assert "XMLHttpRequest" in ui
assert "xhr.upload.onprogress" in ui
assert "progress.upload_mibps" in ui
assert "Medir subida REAL a Cloudflare R2" in ui
assert "No se enviará WhatsApp" in ui
assert "if(state.sending||state.benchmarking||!state.ready_video)return" in ui
assert "_send_template(" not in source.split("def _r2_video_benchmark(",1)[1].split("class VideoProgressStart",1)[0]
assert "_deliver_temp(" not in source.split("def _r2_video_benchmark(",1)[1].split("class VideoProgressStart",1)[0]
assert "INSERT INTO" not in source.split("def _r2_video_benchmark(",1)[1].split("class VideoProgressStart",1)[0]

class HttpError(Exception):
    def __init__(self,status,detail):
        self.status_code=status
        super().__init__(detail)

class Resp:
    status=200
    def read(self,n): return b""
class Conn:
    def __init__(self,host,timeout):
        assert host=="fake.r2.example"
        self.size=0
        self.timeout=timeout
        self.headers={}
    def putrequest(self,method,url):
        assert method=="PUT"
        assert "/clinical-temp/" in url
    def putheader(self,k,v):self.headers[k]=v
    def endheaders(self):pass
    def send(self,x): self.size+=len(x)
    def getresponse(self):
        assert self.size==int(self.headers["Content-Length"])
        return Resp()
    def close(self):pass

ns={
    "Path":Path,"threading":threading,"time":time,"secrets":secrets,"os":os,
    "re":re,
    "urllib":urllib,"http":SimpleNamespace(client=SimpleNamespace(HTTPSConnection=Conn)),
    "_r2_url":lambda method,key,expires=0:"https://fake.r2.example/dr-revelo-clinical-2026/"+key+"?sig=synthetic",
    "core":SimpleNamespace(HTTPException=HttpError),
    "_PROGRESS_LOCK":threading.Lock(),"_PROGRESS_JOBS":{},
}
exec(compile(ast.Module(body=[lookup[n] for n in names],type_ignores=[]),
             "reception_progress_isolated","exec"),ns)
with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
    payload=b"\0\0\0\x18ftypisom"+b"0"*(2*1048576+123)
    tmp.write(payload)
    name=tmp.name
calls=[]
ns["_upload_r2"](name,"clinical-temp/speed-test/mock.mp4","video/mp4",
                 lambda done,total:calls.append((done,total)))
assert len(calls)>2 and calls[-1]==(len(payload),len(payload))
assert all(calls[i][0]<calls[i+1][0] for i in range(len(calls)-1))
assert all(total==len(payload) for _,total in calls)
os.unlink(name)
with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
    tmp.write(b"\0\0\0\x18ftypisom"+b"a"*(1024*1024))
    filename=tmp.name
size=Path(filename).stat().st_size
jid="test-job"
ns["_PROGRESS_JOBS"][jid]={
    "pid":1,"size":size,"mode":"velocidad","stage":"preparando",
    "created":time.monotonic(),"local_bytes":size,"r2_bytes":0
}
ns["_verify_benchmark_r2"]=lambda key,expected:expected==size
deleted=[]
ns["_delete_benchmark_r2"]=lambda key:deleted.append(key) or True
ns["_r2_video_benchmark"](jid,filename)
status=ns["_progress_snapshot"](jid)
assert status["stage"]=="complete"
assert status["done"] is True and status["r2_verified"] is True and status["r2_deleted"] is True
assert status["r2_bytes"]==size
assert len(deleted)==1
assert not Path(filename).exists()
assert status["upload_mibps"]>=0
assert "phone" not in status and "name" not in status and "signed_url" not in status

# A failed HEAD must not masquerade as verified or delivered and still attempt DELETE.
with tempfile.NamedTemporaryFile(suffix=".mp4",delete=False) as tmp:
    tmp.write(b"ftyp"+b"x"*1024)
    badname=tmp.name
ns["_PROGRESS_JOBS"]["failure"]={
    "pid":1,"size":Path(badname).stat().st_size,"mode":"velocidad",
    "stage":"preparando","created":time.monotonic(),"r2_bytes":0
}
ns["_verify_benchmark_r2"]=lambda *_:False if False else (_ for _ in ()).throw(ValueError("synthetic verification failure"))
ns["_r2_video_benchmark"]("failure",badname)
bad=ns["_progress_snapshot"]("failure")
assert bad["stage"]=="error" and not bad["r2_verified"]
assert bad["r2_deleted"] and not Path(badname).exists()
assert len(deleted)==2
print("RECEPTION_REAL_R2_PROGRESS_NO_META_NO_PATIENTS_CLEANUP_OFFLINE_OK")
