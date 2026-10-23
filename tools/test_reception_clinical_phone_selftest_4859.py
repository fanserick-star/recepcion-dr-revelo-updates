"""Synthetic mobile test is never based on clinical data."""
import ast
import json
import re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
src=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
page=(root/"prueba-envio-clinico.html").read_text(encoding="utf-8")
hist=(root/"historia-clinica/app/lan_bridge.py").read_text(encoding="utf-8")
tree=ast.parse(src)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_test_pdf")
module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
ns={}
exec(compile(module,"synthetic_pdf","exec"),ns)
pdf=ns["_test_pdf"]()
assert pdf.startswith(b"%PDF-1.4\n")
assert b"PRUEBA SIN DATOS MEDICOS" in pdf
assert b"PACIENTE" not in pdf and b"CISTOSCOP" not in pdf
xref=pdf.split(b"xref\n0 6\n",1)[1].split(b"trailer\n",1)[0].splitlines()
assert len(xref)==6
for number,line in enumerate(xref[1:],1):
    position=int(line[:10])
    assert pdf[position:position+len(f"{number} 0 obj")]==f"{number} 0 obj".encode()
assert b"%%EOF" in pdf and len(pdf)<1500

assert "def _test_send(phone: str):" in src
assert 'core.WHATSAPP_TEST_PHONE' in src
assert 'hmac.compare_digest(raw, allow)' in src
assert '"ENVIAR PRUEBA"' in src
assert 'asyncio.to_thread(_test_send,data.phone)' in src
assert "with urllib.request.urlopen(url, timeout=25)" in src
assert "hmac.compare_digest(hashlib.sha256(downloaded).digest(),hashlib.sha256(pdf).digest())" in src
assert '"DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)"' in src
assert '"clinical-temp/self-test/"' in src
assert 'def _check_r2():' in src
assert '@app.post("/api/clinical-delivery/check-r2")' in src
assert 'x-amz-expiration' in src
assert '_r2_url("DELETE",key,180)' in src
assert "'/api/clinical-delivery/check-r2'" in ui
assert '"ready_test"' in src
assert 'time.monotonic() - _LAST_TEST_SEND < 300' in src
assert 'def _linked_patient(pid):' in src
assert 'def _signed_pdf(pid, kind, doc_id):' in src

assert 'send-self-test' in ui and 'confirmation:\'ENVIAR PRUEBA\'' in ui
assert 'WHATSAPP_TEST_PHONE' in ui
assert 'data-profile-tab="documentos"' in (root/"recepcion/app/static/app.js").read_text(encoding="utf-8")
assert 'clinical_delivery.js?v=4.8.60' in (root/"recepcion/app/static/index.html").read_text(encoding="utf-8")
assert 'noindex,nofollow' in page and 'SIN DATOS' in page
assert 'No enviado por Meta'.lower() in page.lower() or 'no enviado por Meta' in page
assert 'from cloud_sync import _load_env' in hist
assert 'CLINICAL_DELIVERY_LAN_SECRET' in hist
versions={
    "recepcion":json.loads((root/"recepcion/app/recepcion-version.json").read_text(encoding="utf-8"))["version"],
    "historia":json.loads((root/"historia-clinica/app/historia-version.json").read_text(encoding="utf-8"))["version"]
}
assert versions=={"recepcion":"4.8.61","historia":"1.4.22"}
print("CLINICAL_MOBILE_SYNTHETIC_PDF_SELFTEST_4859_OK")
