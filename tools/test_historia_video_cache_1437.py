"""Synthetic 1.4.37 on-disk video-cache safety and 8MB Wi-Fi diagnostic.

No actual patient video, personal data, Neon database, cloud service, real LAN
or Windows firewall access.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import tempfile
import time
import sys
import types
from pathlib import Path
from types import SimpleNamespace

# Canonical-source CI runs before runtime requirements are installed.
# Stub the three FastAPI types in this isolated test only.
class HTTPException(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code
        self.detail=detail
        super().__init__(detail)
fake_fastapi=types.ModuleType("fastapi")
fake_fastapi.HTTPException=HTTPException
fake_fastapi.Request=object
fake_responses=types.ModuleType("fastapi.responses")
fake_responses.FileResponse=lambda path,**kw:SimpleNamespace(path=path,headers=kw.get("headers",{}))
fake_responses.JSONResponse=lambda *args,**kw:SimpleNamespace(args=args,kwargs=kw)
sys.modules["fastapi"]=fake_fastapi
sys.modules["fastapi.responses"]=fake_responses

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/"historia-clinica/app/clinical_video_cache.py"
spec=importlib.util.spec_from_file_location("clinical_video_cache_synthetic_test",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def wait(cache,pid,vid):
    for _ in range(150):
        result=cache.snapshot(pid,vid)
        if result["state"] in {"ready","error"}:
            return result
        time.sleep(.01)
    raise AssertionError("Synthetic cache worker failed to finish")

with tempfile.TemporaryDirectory(prefix="safe_video_cache_local_") as d:
    data=Path(d)
    mp4=(b"\x00\x00\x00\x18ftypisom"+b"SYNTHETIC_MP4_NOT_A_PATIENT_FILE_"*600)
    checksum=hashlib.sha256(mp4).hexdigest()
    speed=b"\0"*(8*1024*1024)
    wrong_hash=False
    def url(action,patient,video,route):
        return f"{action}:{patient}:{video}"
    class MockResponse(io.BytesIO):
        def __init__(self,payload,media):
            super().__init__(payload)
            self.status=200
            self.headers={"Content-Type":media,"Content-Length":str(len(payload))}
        def __enter__(self):return self
        def __exit__(self,*ignored):self.close()
    def fetch(url,timeout=0,headers=None):
        nonlocal_fingerprint=hashlib.sha256(b"wrong-original").hexdigest() if wrong_hash else checksum
        if url.startswith("catalog:"):
            return MockResponse(json.dumps({"ok":True,"videos":[{
                "id":"test-video-1","size_bytes":len(mp4),"sha256":nonlocal_fingerprint
            }]}).encode(),"application/json")
        if url.startswith("stream:"):
            return MockResponse(mp4,"video/mp4")
        if url.startswith("speed:"):
            return MockResponse(speed,"application/octet-stream")
        raise RuntimeError("Unrecognized synthetic URL")
    cache=module.LocalVideoCache(data,url,fetch)
    cache.initialize()
    assert cache.directory.exists()
    assert cache.snapshot("patient-A","test-video-1")["state"]=="not_started"
    first=cache.begin("patient-A","test-video-1")
    assert first["state"] in {"downloading","ready"}
    done=wait(cache,"patient-A","test-video-1")
    assert done["state"]=="ready",done
    file=cache.playable("patient-A","test-video-1").path
    assert Path(file).read_bytes()==mp4
    assert "patient-A" not in str(file) and "test-video-1" not in str(file)
    assert list(cache.directory.glob("*.part"))==[]
    assert cache.begin("patient-A","test-video-1")["state"]=="ready"
    assert len(list(cache.directory.glob("*.mp4")))==1
    try:cache.playable("patient-B","test-video-1")
    except HTTPException as e:assert e.status_code==409
    else:raise AssertionError("Cross-patient local video leaked")
    try:cache.begin("patient-A","different-video")
    except HTTPException as e:assert e.status_code==404
    else:raise AssertionError("Unlinked remote video was downloadable")
    diagnostic=cache.diagnostic()
    assert diagnostic["ok"] and diagnostic["test_bytes"]==8*1024*1024
    assert diagnostic["megabytes_per_second"]>0
    # Reject a corrupted copy even if its received byte count is correct.
    wrong_hash=True
    cache.begin("patient-B","test-video-1")
    corrupted=wait(cache,"patient-B","test-video-1")
    assert corrupted["state"]=="error"
    assert not (cache.directory/(cache._key("patient-B","test-video-1")+".mp4")).exists()
    wrong_hash=False
    # Clear cached clinical content after an app restart.
    restarted=module.LocalVideoCache(data,url,fetch)
    restarted.initialize()
    assert not list(restarted.directory.glob("*.mp4"))
    assert not list(restarted.directory.glob("*.part"))
    restarted.shutdown()

root=ROOT/"historia-clinica/app"
code=(root/"clinical_video_library.py").read_text(encoding="utf-8")
front=(root/"static/clinical_video_library.js").read_text(encoding="utf-8")
assert "clinical_video_cache.install(app, root, _url, _fetch, _local_only, _existing_patient)" in code
assert "def cache_play(" in path.read_text(encoding="utf-8")
assert "existing_patient(patient_id)" in path.read_text(encoding="utf-8")
assert "sha256" in path.read_text(encoding="utf-8")
assert "url+'/prepare/'" in front
assert "url+'/cached-play/'" in front
assert "video_cache_local" in path.read_text(encoding="utf-8")
assert "clinical_video_library.js?v=1.4.39" in (root/"patient_document_panel.py").read_text(encoding="utf-8")
print("HISTORIA_VIDEO_1437_VERIFIED_TEMP_CACHE_NO_CLOUD_SPEED_8MB_PATIENT_ISOLATION_OK")
