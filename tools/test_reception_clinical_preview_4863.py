"""Offline regression: signed PDF preview must fail clearly and never open Edge on an API error."""
from __future__ import annotations
import ast
import io
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
html=(root/"recepcion/app/static/index.html").read_text(encoding="utf-8")
tree=ast.parse(source)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_lan_pdf_failure")
isolated=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
ns={"json":json}
exec(compile(isolated,"clinical_pdf_error_offline","exec"),ns)
translate=ns["_lan_pdf_failure"]

class FakeHttpError:
    def __init__(self,code,message):
        self.code=code
        self.body=io.BytesIO(json.dumps({"error":message}).encode("utf-8"))
    def read(self,n=-1):
        return self.body.read(n)

assert translate(FakeHttpError(404,"El doctor todavía no ha guardado un PDF firmado"))[0]==404
assert "todavía no tiene PDF firmado" in translate(FakeHttpError(404,"El doctor todavía no ha guardado un PDF firmado"))[1]
assert "original" in translate(FakeHttpError(404,"La copia original firmada no está disponible"))[1]
assert translate(FakeHttpError(404,"No existe una vinculación clínica verificada"))[0]==409
assert translate(FakeHttpError(404,"Documento no pertenece a la ficha vinculada"))[0]==409
assert translate(FakeHttpError(403,"Autorización clínica inválida"))[0]==503
assert translate(FakeHttpError(503,"No se pudo recuperar el PDF firmado"))[0]==503
assert "CLINICAL_DELIVERY_LAN_SECRET" in source
assert "def _signed_pdf(pid, kind, doc_id):" in source
assert 'except urllib.error.HTTPError as exc:' in source
assert "code, message = _lan_pdf_failure(exc)" in source
assert "previewSignedPdf(kind,id,pid,view,row,doc.label)" in ui
assert "frame.src=blobUrl" in ui
assert "await response.blob()" in ui
assert "response.json().catch" in ui
assert "URL.revokeObjectURL(blobUrl)" in ui
assert "window.open('/api/clinical-delivery/patients/'" not in ui
assert "clinical_delivery.js?v=4.8.63" in html
assert "CLINICAL_DELIVERY_LIVE_ENABLED" in source
assert "WHATSAPP_CLINICAL_TEMPLATES_APPROVED" in source
print("CLINICAL_PDF_PREVIEW_4863_FAIL_CLOSED_INLINE_NO_EDGE_OK")
