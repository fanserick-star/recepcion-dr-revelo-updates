"""4.8.144: read-only LAN document lookup diagnostic, without real LAN or patients."""
import ast
import hashlib
import hmac
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
front=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
fn=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=="_lan_documents")
secret="SYNTHETIC-no-real-secret-111122223333444455556666"
class HTTPErrorSafe(Exception):
    def __init__(self,status,message):
        self.status_code=status;self.detail=message
class Response:
    headers={"Content-Type":"application/json"}
    def __init__(self):self.body=json.dumps({"ok":True,"source":"historia_local","documents":[{"id":"rx-1","date":"2026-11-13","kind":"receta"}]}).encode()
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,_n):return self.body
class FakeLan:
    LAN_HTTP_PORT=8765
    def __init__(self):self.active="";self.requests=[];self.fail_http=None
    def _snapshot(self):return {"lan_host":self.active}
    def _candidate_hosts(self):return ["stale-doctor"]
    def _udp_discover(self,timeout=0.35):return {"host":"current-doctor"}
    def _challenge(self,host,timeout=0.7):return {"token":"test-token"} if host=="current-doctor" else None
    def open(self,req,timeout=0):
        self.requests.append(req)
        if self.fail_http:
            raise urllib.error.HTTPError(req.full_url,self.fail_http,"test",{},io.BytesIO(b""))
        return Response()
lan=FakeLan()
ns={"json":json,"hashlib":hashlib,"hmac":hmac,"re":re,"time":time,"urllib":SimpleNamespace(
   parse=urllib.parse,error=urllib.error,request=SimpleNamespace(
      Request=urllib.request.Request,urlopen=lan.open)),"lan":lan,
   "core":SimpleNamespace(HTTPException=HTTPErrorSafe),
   "_clinical_setting":lambda k:secret if k=="CLINICAL_DELIVERY_LAN_SECRET" else "",
   "LABELS":{"receta":"Receta médica","certificado":"Certificado médico","reposo":"Certificado de reposo","informe":"Informe médico"}}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),"lan_offline","exec"),ns)
docs=ns["_lan_documents"]("reception-synthetic","clinical-synthetic")
assert len(docs)==1 and docs[0]["id"]=="rx-1"
assert len(lan.requests)==1 and "current-doctor:8765" in lan.requests[0].full_url
lan.active="current-doctor";lan.requests.clear()
assert len(ns["_lan_documents"]("reception-synthetic","clinical-synthetic"))==1
assert len(lan.requests)==1
lan.fail_http=503
try:ns["_lan_documents"]("reception-synthetic","clinical-synthetic")
except HTTPErrorSafe as e:
    assert e.status_code==503 and "archivo clínico local" in e.detail and "conexión LAN" not in e.detail
else:raise AssertionError("Doctor HTTP 503 must not be reported as network offline")
lan.fail_http=None
lan.active=""
lan._udp_discover=lambda timeout=0.35:None
try:ns["_lan_documents"]("reception-synthetic","clinical-synthetic")
except HTTPErrorSafe as e:
    assert e.status_code==503 and "puerto 8765" in e.detail
else:raise AssertionError("No LAN host must explain service unreachable")
assert "'Reintentar consulta'" in front
assert "'— documentos'" in front and "'— videos'" in front
print("RECEPTION_48144_LAN_DOCUMENT_DISCOVERY_DIAGNOSTICS_AND_RETRY_OK")
