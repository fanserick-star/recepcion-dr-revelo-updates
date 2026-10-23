"""Privacy regression: only verified Reception-patient MP4 originals may be imported.

Uses temporary synthetic video bytes and SQLite; never touches a patient,
real LAN, Neon, WhatsApp, Cloudflare, local office files, or real credentials.
"""
from __future__ import annotations
import ast
import asyncio
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime,timezone
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
rs=(root/"recepcion/app/clinical_video_library.py").read_text(encoding="utf-8")
hs=(root/"historia-clinica/app/clinical_video_library.py").read_text(encoding="utf-8")
js=(root/"historia-clinica/app/static/clinical_video_library.js").read_text(encoding="utf-8")
client=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
reception_app=(root/"recepcion/app/app.py").read_text(encoding="utf-8")
historia_app=(root/"historia-clinica/app/app.py").read_text(encoding="utf-8")
assert "import clinical_video_library" in reception_app
assert "clinical_video_library.install(app, ROOT, DB_PATH, LAN_SERVICE)" in historia_app
assert "data-clinical-video-patient" in (root/"historia-clinica/app/patient_document_panel.py").read_text(encoding="utf-8")
assert "player.controls=true" in js
assert "video/mp4" in js
assert "preload='none'" not in js or "preload='none'" in js
assert "saveVideo(file)" in client and "Guardar en Recepción" in client
assert "sendVideo(file)" in client
assert "ready_video" not in client.split("async function saveVideo",1)[1].split("async function sendVideo",1)[0]
assert "CLINICAL_VIDEO_BACKUP_DIR" in rs
assert "original.backup(copy)" in rs
assert "FileResponse(source" in rs
assert 'media_type="video/mp4"' in rs
assert "Request.stream" not in hs
assert "ProxyHandler({})" in hs
assert 'incoming_range' in hs and '"Content-Range"' in hs
assert "with sqlite3.connect(db_path" in hs and "_existing_patient(patient_id)" in hs
assert "with sqlite3.connect" not in rs.split("def _verify_lan",1)[1].split("def _records",1)[0]

class Denied(Exception):
    def __init__(self, code, message):
        self.status_code=code
        self.detail=message
        super().__init__(message)
def Depends(_):return None
fakecore=SimpleNamespace(Depends=Depends,get_db=None,current_user=None,
                         HTTPException=Denied)

tree=ast.parse(rs)
names={"_db","_safe_row","_local_file","_backup_path","_has_backup","_backup_copy",
       "_verify_lan","_records","_row_by_id","import_video"}
nodes=[]
for child in tree.body:
    if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)) and child.name in names:
        if child.name != "_db":
            child.decorator_list=[]
        nodes.append(child)
assert len(nodes)==len(names)
module=ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[]))
with tempfile.TemporaryDirectory(prefix="private_clinical_video_synthetic_") as folder:
    base=Path(folder)/"reception"
    store=base/"objects"
    backup=Path(folder)/"separate-backup"
    index=base/"library.sqlite3"
    scope=dict(core=fakecore, Request=object, BASE=base, STORE=store, INDEX=index,
         MAX_VIDEO=2*1024*1024*1024, CHUNK=1024*1024, _UUID=re.compile(r"^[A-Za-z0-9_-]{1,100}$"),
         _FILENAME=re.compile(r"[^a-zA-Z0-9_. -]"), Path=Path,sqlite3=sqlite3,contextmanager=contextmanager,
         os=os,re=re,hmac=hmac,hashlib=hashlib,secrets=secrets,ipaddress=ipaddress,
         tempfile=tempfile,time=time,shutil=shutil,datetime=datetime,timezone=timezone)
    exec(compile(module,"video_store_offline","exec"),scope)
    class StubConn:
        def close(self):pass
    def verified(pid):
        if pid not in (42,43):raise Denied(409,"Unverified patient")
        return ("clinical-A" if pid==42 else "clinical-B",str(pid),StubConn())
    fake_delivery=SimpleNamespace(_linked_patient=verified,
         _patient=lambda db,pid: verified(pid),
         _clinical_setting=lambda name: "synthetic-secret-1234567890-abcdefgh" if name=="CLINICAL_DELIVERY_LAN_SECRET" else "")
    old=sys.modules.get("clinical_delivery")
    sys.modules["clinical_delivery"]=fake_delivery
    class RequestFake:
        def __init__(self,payload=b"",ip="192.168.1.45",query=None):
            self.payload=payload
            self.headers={"content-type":"video/mp4"}
            self.client=SimpleNamespace(host=ip)
            self.query_params=query or {}
        async def stream(self):
            for at in range(0,len(self.payload),113):
                yield self.payload[at:at+113]
    sample=(b"\0\0\0\x18ftypisom" + b"A"*2048)
    async def imported(pid,payload=sample):
        return await scope["import_video"](pid,RequestFake(payload),filename="video-original.mp4",
                                           db=object(),user=object())
    try:
        a=asyncio.run(imported(42))
        assert a["ok"] and not a["duplicate"] and not a["backup"]
        assert len(scope["_records"]("clinical-A"))==1
        assert len(scope["_records"]("clinical-B"))==0
        again=asyncio.run(imported(42))
        assert again["duplicate"] and again["video"]["id"]==a["video"]["id"]
        other=asyncio.run(imported(43))
        assert other["ok"] and not other["duplicate"]
        assert len(scope["_records"]("clinical-A"))==len(scope["_records"]("clinical-B"))==1
        assert scope["_row_by_id"](a["video"]["id"],"clinical-A")["sha256"]==hashlib.sha256(sample).hexdigest()
        try:
            scope["_row_by_id"](a["video"]["id"],"clinical-B")
        except Denied as exc:assert exc.status_code==404
        else:raise AssertionError("Video from another patient was exposed")
        try:asyncio.run(imported(99))
        except Denied as exc:assert exc.status_code==409
        else:raise AssertionError("Unverified patient imported a file")
        try:asyncio.run(imported(42,b"WRONG_MP4_MAGIC"+b"X"*2000))
        except Denied as exc:assert exc.status_code==415
        else:raise AssertionError("Invalid mp4 was stored")
        with scope["_db"]() as db:
            assert db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]==2
            row=db.execute("SELECT * FROM videos WHERE clinical_patient_id='clinical-A'").fetchone()
        path=scope["_local_file"](row)
        assert path.read_bytes()==sample
        os.environ["CLINICAL_VIDEO_BACKUP_DIR"]=str(backup)
        assert scope["_backup_copy"](row,path)
        assert (backup/row["stored_name"]).read_bytes()==sample
        assert (backup/"library.sqlite3").is_file()
        with sqlite3.connect(backup/"library.sqlite3") as bdb:
            assert bdb.execute("SELECT COUNT(*) FROM videos").fetchone()[0]==2
        timestamp=str(int(time.time()))
        sig=hmac.new(fake_delivery._clinical_setting("CLINICAL_DELIVERY_LAN_SECRET").encode(),
              f"stream|clinical-A|{a['video']['id']}|{timestamp}".encode(),hashlib.sha256).hexdigest()
        valid=RequestFake(ip="192.168.1.45",query={"ts":timestamp,"proof":sig})
        assert scope["_verify_lan"](valid,"stream","clinical-A",a["video"]["id"]) is None
        for action,pid,ip,ts in [
            ("stream","clinical-B","192.168.1.45",timestamp),
            ("catalog","clinical-A","192.168.1.45",timestamp),
            ("stream","clinical-A","8.8.8.8",timestamp),
            ("stream","clinical-A","192.168.1.45",str(int(timestamp)-180)),
        ]:
            bad=RequestFake(ip=ip,query={"ts":ts,"proof":sig})
            try:scope["_verify_lan"](bad,action,pid,a["video"]["id"])
            except Denied as exc:assert exc.status_code==403
            else:raise AssertionError("Invalid or cross-patient LAN proof accepted")
    finally:
        if old is None:sys.modules.pop("clinical_delivery",None)
        else:sys.modules["clinical_delivery"]=old
        os.environ.pop("CLINICAL_VIDEO_BACKUP_DIR",None)
print("CLINICAL_VIDEO_PRIVATE_LOCAL_ARCHIVE_PATIENT_HMAC_BACKUP_RANGE_CONTRACT_OK")
