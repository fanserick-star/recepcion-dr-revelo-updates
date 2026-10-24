"""No-network regression: short link manifest + synthetic MP4 without PHI."""
import ast
import base64
from datetime import datetime, timezone, timedelta
import json
import re
import tempfile
import os
import secrets
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/"recepcion"/"app"
source=(ROOT/"clinical_delivery.py").read_text(encoding="utf-8")
manifest=json.loads((ROOT/"update_manifest.json").read_text(encoding="utf-8"))
assert "clinical_selftest_mp4.b64" in manifest["copy"], "MP4 must be shipped to Windows"
assert "clinical_selftest_mp4.b64" in manifest["required_dependencies"], "Missing fixture must fail before runtime"

ui=(ROOT/"static/clinical_delivery.js").read_text(encoding="utf-8")
tree=ast.parse(source)
lookup={f.name:f for f in tree.body if isinstance(f,ast.FunctionDef)}
assert "clinical_selftest_mp4.b64" in source
video=base64.b64decode((ROOT/"clinical_selftest_mp4.b64").read_text().strip(),validate=True)
assert len(video)==1904 and b"ftypisom" in video[:32]
assert b"moov" in video[:1200] and b"mdat" in video
assert '@app.post("/api/clinical-delivery/send-self-test-video")' in source
assert "VIDEO DE PRUEBA (SIN DATOS MEDICOS)" in source
assert "send-self-test-video" in ui
assert "_test_send_video" in source
assert '"CLINICAL_DELIVERY_LIVE_ENABLED"' in source
assert 'test_mode=True' in source

class HttpException(Exception):
    def __init__(self,status,detail):
        self.status_code=status
        super().__init__(detail)

class FakeResponse:
    def __init__(self, url):self.url=url
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return b"x"
    def geturl(self):return self.url

sent=[]
cfg={"CLINICAL_R2_ACCOUNT_ID":"a"*32}
signed=("https://"+cfg["CLINICAL_R2_ACCOUNT_ID"]+
    ".r2.cloudflarestorage.com/dr-revelo-clinical-2026/clinical-temp/self-test/mock.mp4?"+
    "X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature="+("f"*64)+
    "&X-Amz-Expires=604800")
fake_upload=lambda path,key,content_type:sent.append((key,content_type,Path(path).read_bytes()))
ns={
    "ROOT":ROOT,"core":SimpleNamespace(HTTPException=HttpException),
    "tempfile":tempfile,"os":os,"time":time,
    "json":json,"re":re,"secrets":secrets,
    "urllib":urllib,"base64":base64,
    "_setup":lambda:{"ready_r2":True},
    "_clinical_settings":lambda:cfg,
    "_upload_r2":fake_upload,
    "CLINICAL_SHORT_BASE":"https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/d/"
}
compiled=compile(ast.Module(body=[lookup["_test_video_bytes"],lookup["_short_r2_link"]],type_ignores=[]),"short_test","exec")
exec(compiled,ns)
assert ns["_test_video_bytes"]()==video

expiry=datetime.now(timezone.utc)+timedelta(days=6)
with patch.object(urllib.request,"urlopen",side_effect=lambda req,timeout:FakeResponse(signed)):
    short=ns["_short_r2_link"](signed,expiry)
assert re.fullmatch(r"https://dr-revelo-whatsapp-cloud\.drrevelo\.workers\.dev/d/[A-Za-z0-9_-]{22}",short)
assert len(sent)==1
key,mimetype,data=sent[0]
assert re.fullmatch(r"clinical-temp/short-links/[A-Za-z0-9_-]{22}\.json",key)
assert mimetype=="application/json"
record=json.loads(data)
assert record["signed_get_url"]==signed
assert record["expires_epoch"]==int(expiry.timestamp())
assert not any(p in data.lower() for p in [b"patient_name",b"phone",b"patient_id"])
assert "WHATSAPP_ACCESS_TOKEN" not in source.split("def _short_r2_link(",1)[1].split("def _send_template(",1)[0]
print("CLINICAL_SHORT_URL_AND_SYNTHETIC_MP4_1904_BYTES_NO_NETWORK_OK")
