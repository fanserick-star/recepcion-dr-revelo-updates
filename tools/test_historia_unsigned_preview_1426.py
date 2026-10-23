"""Offline safety test: unsigned document preview is read-only and never signs.
No private data, Neon, R2, WhatsApp, network, or real clinical files are used.
"""
from __future__ import annotations
import ast
import re
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
src=(root/"historia-clinica/app/lan_bridge.py").read_text(encoding="utf-8")
tree=ast.parse(src)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="LanService")
fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef)
        and n.name=="unsigned_document_for_reception")
scope={"re":re}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),"offline_unsigned", "exec"),scope)
preview=scope["unsigned_document_for_reception"]
calls=[]
source=b'<html><head><style>body{color:#111}</style></head><body><h1>SIMULADO</h1><script>alert(123)</script></body></html>'
class TestDoc:
    def __init__(self, signed=False, missing_original=False, linked=True):
        self.signed=signed
        self.missing_original=missing_original
        self.linked=linked
        self._clinical_preview_app=SimpleNamespace(routes=[
            SimpleNamespace(path="/certificados/{cert_id}/vista",endpoint=lambda cert_id: SimpleNamespace(status_code=200,body=source))
        ])
    def signed_document_for_reception(self, rid,kind,doc,clinical_id):
        calls.append((rid,kind,doc,clinical_id))
        if not self.linked:raise PermissionError("Documento pertenece a otra ficha")
        if self.missing_original:raise FileNotFoundError("La copia original firmada no está disponible")
        if self.signed:return b"%PDF-1.4 SIMULATED SIGNED"
        raise FileNotFoundError("El doctor todavía no ha guardado un PDF firmado")
doc=TestDoc()
result=preview(doc,"reception-1","certificado","doc-1","patient-1")
assert b"SIN FIRMA ELECTR" in result
assert b"Content-Security-Policy" in result
assert b"script-src 'none'" in result
assert b"<script" not in result
assert b"SIMULADO" in result
assert calls==[("reception-1","certificado","doc-1","patient-1")]
for test,expected in [
    (TestDoc(signed=True),ValueError),
    (TestDoc(missing_original=True),FileNotFoundError),
    (TestDoc(linked=False),PermissionError)]:
    try:preview(test,"reception-1","certificado","doc-1","patient-1")
    except expected:pass
    else:raise AssertionError("Unsigned path must fail closed")
try:preview(doc,"reception-1","certificado","doc-1","")
except PermissionError:pass
else:raise AssertionError("Missing cloud identity must fail closed")
assert '/delivery/unsigned-preview' in src
assert 'service._valid_delivery_proof(' in src
assert 'service._valid_token(self.remote_ip, token)' in src
assert 'service._clinical_preview_app = app' in src
section=src.split("def unsigned_document_for_reception(",1)[1].split("def _handler_class",1)[0]
for token in ["_sign_pdf(", "INSERT INTO", "UPDATE patients", "DELETE FROM", "R2", "Meta WhatsApp"]:
    assert token not in section,token
print("HISTORIA_UNSIGNED_PREVIEW_1426_READONLY_FAIL_CLOSED_OK")
