"""Offline regression for explicit read-only Meta diagnostics: no patients or sends."""
import ast
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
source = (root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui = (root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
tree = ast.parse(source)
fn = next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="_meta_readonly_diagnostic")
namespace = {
    "json":json, "re":re, "urllib":urllib,
    "core":SimpleNamespace(WHATSAPP_GRAPH_VERSION="v26.0",
                           WHATSAPP_PHONE_NUMBER_ID="1234567890",
                           HTTPException=lambda status,message: RuntimeError(message)),
}
config = {
    "WHATSAPP_GRAPH_VERSION":"v26.0",
    "WHATSAPP_PHONE_NUMBER_ID":"1234567890",
    "WHATSAPP_CLINICAL_ACCESS_TOKEN":"fake-separate-clinical-token-1234567890",
}
namespace["_clinical_settings"] = lambda:config
exec(compile(ast.Module(body=[fn],type_ignores=[]),"safe_readonly_test","exec"),namespace)
check = namespace["_meta_readonly_diagnostic"]
calls = []

class Response:
    def __init__(self,data):
        self.data = json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,_limit): return self.data

def succeed(request,timeout):
    calls.append(request)
    assert request.get_method()=="GET"
    assert request.data is None
    assert urllib.parse.urlsplit(request.full_url).hostname=="graph.facebook.com"
    assert request.get_header("Authorization")=="Bearer "+config["WHATSAPP_CLINICAL_ACCESS_TOKEN"]
    return Response({"id":"secret-meta-id","display_phone_number":"+593999999999"})

with patch.object(urllib.request,"urlopen",side_effect=succeed):
    result = check()
assert len(calls)==2
assert result["no_message_sent"] is True
assert result["checks"]["token_identity"]["ok"] is True
assert result["checks"]["phone_metadata"]["ok"] is True
dump=json.dumps(result)
assert "secret-meta-id" not in dump and "+5939" not in dump and "fake-separate" not in dump
assert calls[0].full_url.endswith("/me?fields=id")
assert calls[1].full_url.endswith("/1234567890?fields=id,display_phone_number")

def deny_phone(request,timeout):
    if request.full_url.endswith("/me?fields=id"):
        return Response({"id":"secret-meta-id"})
    error = {"error":{"code":10,"error_subcode":2593181,
             "message":"FAKE_TOKEN_SECRET +593999999999 signed-url-private"}}
    raise urllib.error.HTTPError(request.full_url,400,"Forbidden",{},
                                 io.BytesIO(json.dumps(error).encode()))

with patch.object(urllib.request,"urlopen",side_effect=deny_phone):
    denied=check()
assert denied["checks"]["token_identity"]["ok"] is True
assert denied["checks"]["phone_metadata"] == {
    "ok":False, "http_status":400, "meta_code":10
} or denied["checks"]["phone_metadata"] == {
    "ok":False, "http_status":400, "meta_code":10
}  # Unknown oversized subcodes are safely omitted.
dump=json.dumps(denied)
for term in ("FAKE_TOKEN_SECRET","+593999999999","signed-url-private","secret-meta-id"):
    assert term not in dump

config["WHATSAPP_CLINICAL_ACCESS_TOKEN"]=""
try:
    check()
except RuntimeError:
    pass
else:
    raise AssertionError("Missing clinical token must fail closed")

assert '@app.post("/api/clinical-delivery/check-meta")' in source
assert 'user=core.Depends(core.current_user)' in source
assert "check-meta" in ui
assert "sin enviar mensajes" in ui
print("CLINICAL_META_READ_ONLY_NO_SEND_NO_SECRETS_OK")
