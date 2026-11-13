"""Regression: recent prescriptions visible only through authenticated current Historia LAN.

No real credentials, Neon, patient data, production writes or network requests.
"""
from __future__ import annotations
import ast
import hashlib
import hmac
import json
import sqlite3
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/"historia-clinica"/"app"))
from lan_bridge import LanService

class HTTPException(Exception):
    def __init__(self, code, detail):
        self.status_code=code
        self.detail=detail
        super().__init__(detail)

with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    db=root/"clinical.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE patient_links(reception_patient_id TEXT,clinical_patient_id TEXT)")
        con.execute("CREATE TABLE patients(id TEXT PRIMARY KEY,deleted_at TEXT)")
        con.execute("CREATE TABLE prescriptions(id TEXT PRIMARY KEY,patient_id TEXT,issued_at TEXT,deleted_at TEXT)")
        con.execute("CREATE TABLE certificates(id TEXT PRIMARY KEY,patient_id TEXT,issued_at TEXT,certificate_type TEXT,deleted_at TEXT)")
        con.execute("INSERT INTO patients VALUES('clinical-A',NULL)")
        con.execute("INSERT INTO patients VALUES('clinical-B',NULL)")
        con.execute("INSERT INTO patient_links VALUES('received-42','clinical-A')")
        con.execute("INSERT INTO prescriptions VALUES('rx-today','clinical-A','2026-11-13T15:12:00',NULL)")
        con.execute("INSERT INTO prescriptions VALUES('rx-deleted','clinical-A','2026-11-13T15:11:00','2026-11-13')")
        con.execute("INSERT INTO prescriptions VALUES('rx-other','clinical-B','2026-11-13T15:13:00',NULL)")
        con.execute("INSERT INTO certificates VALUES('report-a','clinical-A','2026-11-13T15:10:00','report_ultrasound',NULL)")
    svc=LanService(root,db,"1.4.95")
    docs=svc.documents_for_reception("received-42","clinical-A")
    assert [d["id"] for d in docs] == ["rx-today","report-a"],docs
    assert [d["kind"] for d in docs] == ["receta","informe"],docs
    for wrong in (("received-42","clinical-B"),("unknown","clinical-C")):
        try:
            svc.documents_for_reception(*wrong)
        except (PermissionError,FileNotFoundError):
            pass
        else:
            raise AssertionError("Identity conflict or missing patient must block")
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0]==3
        assert con.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0]==1

# Isolate the Reception function and verify HMAC and safe response handling.
source=(BASE/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
tree=ast.parse(source)
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="_lan_documents")
mocksecret="SYNTHETIC-private-LAN-credential-not-a-live-secret-123"
captured=[]
class FakeResponse:
    headers={"Content-Type":"application/json"}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return json.dumps({"ok":True,"source":"historia_local","documents":[{"id":"rx-today","date":"2026-11-13T15:12","kind":"receta"}]}).encode()
def fake_urlopen(req,timeout=None):
    captured.append(req)
    return FakeResponse()
def fake_challenge(host,timeout=None):
    assert host=="doctor-lan"
    return {"token":"fake-token"}
ns={
    "re":__import__("re"),"json":json,"hashlib":hashlib,"hmac":hmac,"time":time,
    "urllib":SimpleNamespace(parse=urllib.parse,error=urllib.error,request=SimpleNamespace(Request=urllib.request.Request,urlopen=fake_urlopen)),
    "core":SimpleNamespace(HTTPException=HTTPException),
    "_clinical_setting":lambda k:mocksecret if k=="CLINICAL_DELIVERY_LAN_SECRET" else "",
    "lan":SimpleNamespace(_candidate_hosts=lambda:["doctor-lan"],_challenge=fake_challenge,LAN_HTTP_PORT=8765),
    "LABELS":{"receta":"Receta médica","informe":"Informe médico","certificado":"Certificado médico","reposo":"Reposo"},
}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),"reception_documents_test","exec"),ns)
docs=ns["_lan_documents"]("received-42","clinical-A")
assert docs==[{"id":"rx-today","date":"2026-11-13T15:12","kind":"receta","label":"Receta médica"}]
assert len(captured)==1
req=captured[0]
qs=urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
assert qs["reception_id"]==["received-42"]
assert qs["clinical_patient_id"]==["clinical-A"]
headers={k.lower():v for k,v in req.header_items()}
stamp=headers["x-revelo-delivery-time"]
signed=f"received-42|clinical-A|lista|documentos|{stamp}"
assert hmac.compare_digest(headers["x-revelo-delivery-proof"],hmac.new(mocksecret.encode(),signed.encode(),hashlib.sha256).hexdigest())

# Prove listing uses local DB and not the stale cloud inventory.
assert "docs = _lan_documents(rid, clinical_id)" in source
assert "SELECT id::text,issued_at::text,'receta' AS kind" not in source
assert '"source": "historia_local"' in (BASE/"historia-clinica/app/lan_bridge.py").read_text(encoding="utf-8")
print("RECEPTION_LATEST_CLINICAL_DOCUMENTS_LAN_48138_OK")
