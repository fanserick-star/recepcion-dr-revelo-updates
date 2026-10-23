"""Synthetic integration of the Reception video-only reverse LAN listener.

No real videos, patient records, Neon, credentials, or medical data.
Tests real HTTP requests on a random localhost port (no firewall changes).
"""
from __future__ import annotations
import hashlib
import hmac
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"recepcion/app/clinical_video_lan_server.py").read_text(encoding="utf-8")
frontend=(ROOT/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
history=(ROOT/"historia-clinica/app/clinical_video_library.py").read_text(encoding="utf-8")
app_source=(ROOT/"recepcion/app/app.py").read_text(encoding="utf-8")
assert "clinical_video_lan_server.install(app)" in app_source
assert 'values.get("RECEPTION_VIDEO_LAN_PORT") or "8766"' in history
assert '"Habilitar acceso de Historia (Windows)"' not in frontend or "Habilitar acceso de Historia (Windows)" in frontend
assert 'remoteip=localsubnet' in source and 'profile=private' in source
assert 'localport={self.port}' in source
assert "localport=8000" not in source
assert "def log_message(self, _format, *_args)" in source
assert "CLINICAL_DELIVERY_LAN_SECRET" in (ROOT/"recepcion/app/clinical_video_library.py").read_text(encoding="utf-8")
assert "function addPrivateVideoLanTools(section)" in frontend
assert "api('/api/clinical-videos/lan-firewall',{method:'POST'})" in frontend
assert 'url = _url("catalog"' in history
assert '"RECEPTION_VIDEO_LAN_HOST"' in history

with tempfile.TemporaryDirectory(prefix="clinical_video_private_listener_") as tmp:
    mp4=Path(tmp)/"synthetic.mp4"
    contents=b"\x00\x00\x00\x18ftypisom" + b"only-test-video-stream"*60
    mp4.write_bytes(contents)
    secret="testing-clinical-delivery-secret-abcdef-123456789"
    def check(request,action,patient,video_id):
        stamp=request.query_params.get("ts","")
        proof=request.query_params.get("proof","")
        data=f"{action}|{patient}|{video_id}|{stamp}".encode()
        expected=hmac.new(secret.encode(),data,hashlib.sha256).hexdigest()
        if (request.client.host not in ("127.0.0.1","::1") or
            not hmac.compare_digest(proof,expected) or
            abs(int(time.time())-int(stamp))>90):
            raise ValueError("synthetic unauthorized access")
    class FakeClinicalHttpError(Exception):
        status_code=404
    synthetic_video=SimpleNamespace(
        _verify_lan=check,
        _records=lambda patient: [{"id":"test-video-1","recorded_at":"2026-10-23T12:00:00",
                                   "size_bytes":len(contents),"backup":False}]
             if patient=="patient-1" else [],
        _row_by_id=lambda vid,patient:
            {"file":"synthetic.mp4","sha256":hashlib.sha256(contents).hexdigest()} if vid=="test-video-1" and patient=="patient-1"
            else (_ for _ in ()).throw(FakeClinicalHttpError()),
        _local_file=lambda row:mp4,
        BASE=Path(tmp),
    )
    previous=sys.modules.get("clinical_video_library")
    sys.modules["clinical_video_library"]=synthetic_video
    spec=importlib.util.spec_from_file_location("private_video_listener_test",
            ROOT/"recepcion/app/clinical_video_lan_server.py")
    mod=importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        svc=mod.PrivateVideoLanServer()
        svc.port=0
        svc.start()
        assert svc.status()["ready"] is True
        port=svc.httpd.server_address[1]
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def url(action,patient="patient-1",video="test-video-1",timestamp=None,key=secret):
            stamp=str(timestamp or int(time.time()))
            signature=hmac.new(key.encode(),f"{action}|{patient}|{video}|{stamp}".encode(),
                               hashlib.sha256).hexdigest()
            qs=urllib.parse.urlencode({"clinical_id":patient,"ts":stamp,"proof":signature})
            base=f"http://127.0.0.1:{port}/api/clinical-videos/lan/"
            return base+("catalog" if action=="catalog" else "speed" if action=="speed" else "stream/"+video)+"?"+qs
        def get(link,headers=None):
            return opener.open(urllib.request.Request(link,headers=headers or {}),timeout=5)
        catalog=url("catalog",video="-")
        with get(catalog) as response:
            doc=json.loads(response.read())
            assert response.status==200
            assert len(doc["videos"])==1
            assert doc["videos"][0]["size_bytes"]==len(contents)
            assert doc["videos"][0]["sha256"]==hashlib.sha256(contents).hexdigest()
        with get(url("speed",patient="-",video="-")) as response:
            assert response.status==200
            assert response.headers["Content-Type"]=="application/octet-stream"
            packet=response.read()
            assert len(packet)==8*1024*1024 and not any(packet)
        with get(url("stream")) as response:
            assert response.status==200
            assert response.read()==contents
            assert response.headers.get("Accept-Ranges")=="bytes"
        with get(url("stream"),{"Range":"bytes=5-24"}) as response:
            assert response.status==206
            assert response.headers["Content-Range"]==f"bytes 5-24/{len(contents)}"
            assert response.read()==contents[5:25]
        with get(url("stream"),{"Range":"bytes=-10"}) as response:
            assert response.status==206 and response.read()==contents[-10:]
        for link,code in [
            (url("catalog",video="-",key="wrong-key-abcdefghijklmnopqrstuvwxyz"),403),
            (url("catalog",video="-",timestamp=int(time.time())-180),403),
            (url("stream",patient="patient-2"),404),
            (f"http://127.0.0.1:{port}/api/program/update-now",404)]:
            try:get(link)
            except urllib.error.HTTPError as e:assert e.code==code,(link,code,e.code)
            else:raise AssertionError(f"Unauthorized/unrelated route accepted, expected {code}")
        try:get(url("stream"),{"Range":"bytes=999999-"})
        except urllib.error.HTTPError as e:assert e.code==416
        else:raise AssertionError("Invalid Range accepted")
        req=urllib.request.Request(catalog,method="POST")
        try:opener.open(req,timeout=5)
        except urllib.error.HTTPError as e:assert e.code==405
        else:raise AssertionError("POST accepted by read-only service")
    finally:
        try:svc.stop()
        except NameError:pass
        if previous is None:sys.modules.pop("clinical_video_library",None)
        else:sys.modules["clinical_video_library"]=previous
print("PRIVATE_VIDEO_LAN_1431_4869_LOCAL_ONLY_HMAC_RANGE_206_FIREWALL_GUARD_OK")
