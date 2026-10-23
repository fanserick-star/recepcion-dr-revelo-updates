"""Offline regression: Reception must HMAC-bind the verified Neon patient identity
to the document and never fetch another patient's signed PDF.
No access to real Neon, LAN, files, R2 or WhatsApp.
"""
from __future__ import annotations
import ast
import hashlib
import hmac
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
src=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
tree=ast.parse(src)
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="_signed_pdf")
isolated=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
secret="SYNTHETIC-no-real-secret-for-regression-123456789"
pdf=b"%PDF-1.4\nSYNTHETIC, NOT A REAL PATIENT DOCUMENT\n%%EOF"
calls=[]
class HTTPException(Exception):
    def __init__(self,code,detail):
        self.status_code=code
        self.detail=detail
class PDFReply:
    headers={"Content-Type":"application/pdf","Content-Length":str(len(pdf))}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return pdf[:n]
def fake_urlopen(req,timeout=0):
    calls.append(req)
    return PDFReply()
url=SimpleNamespace(
    parse=urllib.parse,
    error=urllib.error,
    request=SimpleNamespace(Request=urllib.request.Request,urlopen=fake_urlopen)
)
docs=[{"id":"document-1","kind":"certificado"}]
def only_linked_document(pid):
    assert pid==123
    return docs,"reception-remote-id","clinical-verified-id"
ns={"re":re,"hashlib":hashlib,"hmac":hmac,"urllib":url,"time":time,
    "core":SimpleNamespace(HTTPException=HTTPException),
    "LABELS":{"certificado":"Certificado médico","receta":"Receta médica"},
    "_documents":only_linked_document,
    "_clinical_setting":lambda k:secret if k=="CLINICAL_DELIVERY_LAN_SECRET" else "",
    "lan":SimpleNamespace(_candidate_hosts=lambda:["synthetic-local-host"],
                          _challenge=lambda h,timeout:{"token":"test-token"},
                          LAN_HTTP_PORT=8765),
    "LIMIT_PDF":20*1024*1024}
exec(compile(isolated,"reception_signed_pdf_offline","exec"),ns)
signed=ns["_signed_pdf"]
assert signed(123,"certificado","document-1")==pdf
assert len(calls)==1
request=calls[0]
args=urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
assert args["reception_id"]==["reception-remote-id"]
assert args["clinical_patient_id"]==["clinical-verified-id"]
assert args["doc_id"]==["document-1"]
assert args["kind"]==["certificado"]
headers={key.lower():value for key,value in request.header_items()}
stamp=headers["x-revelo-delivery-time"]
proof=headers["x-revelo-delivery-proof"]
data=f"reception-remote-id|clinical-verified-id|certificado|document-1|{stamp}"
assert hmac.compare_digest(proof,hmac.new(secret.encode(),data.encode(),hashlib.sha256).hexdigest())
old=f"reception-remote-id|certificado|document-1|{stamp}"
assert not hmac.compare_digest(proof,hmac.new(secret.encode(),old.encode(),hashlib.sha256).hexdigest())
for kind,doc_id in [("certificado","document-2"),("informe","document-1"),("video","document-1")]:
    try:signed(123,kind,doc_id)
    except HTTPException as exc:assert exc.status_code in (400,404)
    else:raise AssertionError("Unexpected cross-document signed PDF retrieval")
assert len(calls)==1
assert "docs,_,_=_documents(pid)" in src
assert "l.verified=1" in src
assert 'p.deleted_at IS NULL' in src
assert 'WHATSAPP_CLINICAL_TEMPLATES_APPROVED' in src
print("RECEPTION_4864_SIGNED_PDF_NEON_ID_HMAC_NO_CROSS_PATIENT_OK")
