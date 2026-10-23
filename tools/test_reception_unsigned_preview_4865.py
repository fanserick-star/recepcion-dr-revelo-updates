"""Offline check of authenticated unsigned HTML access from Reception.
Never accesses real Neon, R2, WhatsApp, patient records or the LAN.
"""
from __future__ import annotations
import ast
import hashlib
import hmac
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
src=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
tree=ast.parse(src)
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="_unsigned_preview_html")
secret="synthetic-secret-not-a-production-token-123456789"
calls=[]
html=b"<html><body>SIMULATED SIN FIRMA ELECTR\xc3\x93NICA</body></html>"
class MockResponse:
    headers={"Content-Type":"text/html; charset=utf-8",
             "Content-Length":str(len(html)),
             "X-Clinical-Preview-Unsigned":"1"}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return html[:n]
def request_get(request,timeout=0):
    calls.append(request)
    return MockResponse()
class HttpError(Exception):
    def __init__(self,status,detail):
        self.status_code=status
        self.detail=detail
ns={
    "re":__import__("re"),"hashlib":hashlib,"hmac":hmac,"time":time,
    "urllib":SimpleNamespace(parse=urllib.parse,request=SimpleNamespace(
        Request=urllib.request.Request,urlopen=request_get),error=urllib.error),
    "core":SimpleNamespace(HTTPException=HttpError),
    "_clinical_setting":lambda key: secret if key=="CLINICAL_DELIVERY_LAN_SECRET" else "",
    "lan":SimpleNamespace(_candidate_hosts=lambda:["synthetic-host"],
                          _challenge=lambda h,timeout:{"token":"fake-challenge"},
                          LAN_HTTP_PORT=8765),
    "_documents":lambda pid:([{"id":"doc-1","kind":"certificado"}],
                            "reception-1","clinical-1") if pid==42 else ([],
                            "reception-2","clinical-2"),
}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),"reception_unsigned_mock","exec"),ns)
lookup=ns["_unsigned_preview_html"]
assert lookup(42,"certificado","doc-1")==html
assert len(calls)==1
r=calls[0]
parts=urllib.parse.urlsplit(r.full_url)
assert parts.path=="/delivery/unsigned-preview"
q=urllib.parse.parse_qs(parts.query)
assert q["clinical_patient_id"]==["clinical-1"]
assert q["reception_id"]==["reception-1"]
headers={k.lower():v for k,v in r.header_items()}
stamp=headers["x-revelo-delivery-time"]
digest=hmac.new(secret.encode(),
    f"reception-1|clinical-1|certificado|doc-1|{stamp}".encode(),hashlib.sha256).hexdigest()
assert hmac.compare_digest(headers["x-revelo-delivery-proof"],digest)
for pid,kind,doc in [(43,"certificado","doc-1"),(42,"certificado","doc-2"),(42,"informe","doc-1")]:
    try:lookup(pid,kind,doc)
    except HttpError as exc:assert exc.status_code==404
    else:raise AssertionError("Unauthorized unsigned document was exposed")
assert len(calls)==1
assert "/api/clinical-delivery/patients/{pid}/unsigned/{kind}/{doc_id}" in src
assert 'data=_unsigned_preview_html(pid,kind,doc_id)' in src
assert "pdf=await asyncio.to_thread(_signed_pdf,pid,data.kind,data.document_id)" in src
print("RECEPTION_UNSIGNED_PREVIEW_4865_NEON_ID_HMAC_ONLY_READ_OK")
