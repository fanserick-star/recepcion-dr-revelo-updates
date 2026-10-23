"""Historia 1.4.30: video catalogue legacy database + JSON failure regressions.

All fixtures are synthetic. No patient data, live LAN, Neon or media upload.
"""
from __future__ import annotations

import ast
import json
import logging
import re
import sqlite3
import tempfile
import urllib.error
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"historia-clinica/app/clinical_video_library.py").read_text(encoding="utf-8")
browser=(ROOT/"historia-clinica/app/static/clinical_video_library.js").read_text(encoding="utf-8")
tree=ast.parse(src)
install=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="install")
functions=[]
for node in install.body:
    if isinstance(node,ast.FunctionDef) and node.name in {"_existing_patient","patient_videos"}:
        node.decorator_list=[]
        functions.append(node)
assert len(functions)==2
module=ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[]))

class FakeHTTP(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code
        self.detail=detail
        super().__init__(detail)
class FakeJSON(dict):
    def __init__(self,content,status_code):
        super().__init__(content)
        self.status_code=status_code
class FakeResponse:
    def __init__(self,data):
        self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,size):return self.data[:size]

def scope_for(db_path):
    ns={
        "_SAFE":re.compile(r"^[A-Za-z0-9_-]{1,100}$"),
        "sqlite3":sqlite3,"db_path":db_path,"HTTPException":FakeHTTP,
        "JSONResponse":FakeJSON,"logging":logging,"json":json,
        "urllib":SimpleNamespace(error=urllib.error),
        "_JSON_LIMIT":256*1024,
        "_local_only":lambda request:None,
        "_url":lambda action,pid,vid,path:"http://private-reception/catalog",
        "_fetch":lambda url,timeout:FakeResponse(
            b'{"ok":true,"videos":[{"id":"sample-video","recorded_at":"2026-10-22T10:00:00", "size_bytes":1234,"backup":false}]}'),
    }
    exec(compile(module,"isolated_video_catalog","exec"),ns)
    return ns

with tempfile.TemporaryDirectory(prefix="historia_video_json_1430_") as path:
    p=Path(path)/"legacy.sqlite"
    with sqlite3.connect(p) as db:
        db.executescript("""
        CREATE TABLE patients(id TEXT PRIMARY KEY,name TEXT);
        INSERT INTO patients VALUES ('clinical-1','SYNTHETIC RECORD');
        """)
    ns=scope_for(p)
    assert ns["_existing_patient"]("clinical-1")=="clinical-1"
    records=ns["patient_videos"]("clinical-1",SimpleNamespace())
    assert records["ok"] and len(records["videos"])==1
    assert records["videos"][0]["id"]=="sample-video"

    # The latest schema has soft-delete and merge markers. Never expose
    # deleted/merged cards or silently remap to another patient.
    p2=Path(path)/"current.sqlite"
    with sqlite3.connect(p2) as db:
        db.executescript("""
        CREATE TABLE patients(id TEXT PRIMARY KEY,name TEXT,deleted_at TEXT,merged_into_patient_id TEXT);
        INSERT INTO patients VALUES ('live','SYNTHETIC',NULL,NULL);
        INSERT INTO patients VALUES ('deleted','SYNTHETIC','2026-10-20',NULL);
        INSERT INTO patients VALUES ('merged','SYNTHETIC',NULL,'live');
        """)
    ns2=scope_for(p2)
    assert ns2["_existing_patient"]("live")=="live"
    for bad in ("deleted","merged","absent"):
        try:ns2["_existing_patient"](bad)
        except FakeHTTP as ex:assert ex.status_code==404
        else:raise AssertionError("Unfit clinical card accepted: "+bad)
    try:ns2["_existing_patient"]("../clinical-1")
    except FakeHTTP as ex:assert ex.status_code==400
    else:raise AssertionError("Invalid path accepted")

    # A missing/incompatible SQLite must return a JSON HTTP error instead
    # of a 500 text response and JavaScript JSON SyntaxError.
    missing=scope_for(Path(path)/"missing.sqlite")
    try:missing["_existing_patient"]("clinical-1")
    except FakeHTTP as ex:assert ex.status_code==503
    else:raise AssertionError("Missing schema should fail safely")

    ns["_fetch"]=lambda url,timeout:FakeResponse(b"Internal Server Error")
    failed=ns["patient_videos"]("clinical-1",SimpleNamespace())
    assert isinstance(failed,FakeJSON) and failed.status_code==503
    assert failed["ok"] is False and "error" in failed

    ns["_fetch"]=lambda url,timeout:FakeResponse(b'{"ok": true, "videos":"bad"}')
    bad_catalog=ns["patient_videos"]("clinical-1",SimpleNamespace())
    assert isinstance(bad_catalog,FakeJSON) and bad_catalog.status_code==503

    ns["_url"]=lambda *args:(_ for _ in ()).throw(RuntimeError("synthetic internal problem"))
    interrupted=ns["patient_videos"]("clinical-1",SimpleNamespace())
    assert isinstance(interrupted,FakeJSON) and interrupted.status_code==503
    assert "Internal Server Error" not in interrupted["error"]

assert "media.includes('application/json')" in browser
assert "data=await response.json()" in browser
assert "HTTP '+response.status+" in browser
assert "status.textContent=(error&&error.message)" in browser
assert "clinical_video_library.js?v=1.4.35" in (
    ROOT/"historia-clinica/app/patient_document_panel.py").read_text(encoding="utf-8")
print("HISTORIA_VIDEO_1430_LEGACY_SQLITE_JSON_ERRORS_FAIL_SAFE_OK")
