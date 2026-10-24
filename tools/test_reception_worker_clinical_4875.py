"""No-network contract for Reception -> Worker clinical send; no patient data."""
import ast
import io
import json
import hashlib
import re
import secrets
import urllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
source=(root/"recepcion/app/clinical_delivery.py").read_text()
worker=(root/"cloudflare/whatsapp_worker.js").read_text()
tree=ast.parse(source)
functions=[node for node in tree.body if isinstance(node,ast.FunctionDef)
           and node.name in ("_send_template","_issue_clinical_capability")]
assert len(functions)==2
requests=[]
rows=[]
class Session:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,values):
        assert "whatsapp_cloud.clinical_delivery_caps" in sql
        assert set(values)=={"token_hash","recipient_hash","mode"}
        assert re.fullmatch("[0-9a-f]{64}",values["token_hash"])
        assert re.fullmatch("[0-9a-f]{64}",values["recipient_hash"])
        rows.append(values)
    def commit(self): pass
class HTTPException(Exception):
    def __init__(self,status,detail):
        self.status_code=status
        self.detail=detail
        super().__init__(detail)
core=SimpleNamespace(
    CloudSessionLocal=Session, FORCE_OFFLINE=False,
    HTTPException=HTTPException, text=lambda x:x,
)
ns={"core":core,"hashlib":hashlib,"re":re,"secrets":secrets,
    "urllib":urllib,"json":json,"LABELS":{"receta":"Receta médica"},
    "CLINICAL_WORKER_URL":"https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/clinical/dispatch"}
cfg={"WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE":"entrega_documento_clinico",
     "WHATSAPP_CLINICAL_VIDEO_TEMPLATE":"entrega_video_clinico",
     "WHATSAPP_CLINICAL_ACCESS_TOKEN":"DO_NOT_READ"}
ns["_clinical_settings"]=lambda:cfg
ns["_setup"]=lambda:{"clinical_delivery_enabled":False}
exec(compile(ast.Module(body=functions,type_ignores=[]),"isolated_worker_send","exec"),ns)

class Response:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*_):return json.dumps({"accepted_by_meta":True,"message_id":"synthetic-only"}).encode()

def fake_urlopen(req,timeout):
    requests.append(req)
    assert req.get_method()=="POST"
    assert req.full_url==ns["CLINICAL_WORKER_URL"]
    data=json.loads(req.data)
    assert data["mode"]=="test"
    assert data["body_params"][0]=="PACIENTE DE PRUEBA"
    assert data["body_params"][1]=="DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)"
    assert "WHATSAPP_ACCESS_TOKEN" not in data
    assert "WHATSAPP_CLINICAL_ACCESS_TOKEN" not in data
    assert data["token"]!="DO_NOT_READ"
    return Response()

with patch.object(urllib.request,"urlopen",side_effect=fake_urlopen):
    try:
        ns["_send_template"]("593999999999","PACIENTE DE PRUEBA","receta","7 dias",
            "https://example.invalid/fictitious",label_override="DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)")
    except HTTPException as exc:
        assert exc.status_code==503
    else:raise AssertionError("Patient-mode must remain disabled")
    assert ns["_send_template"]("593999999999","PACIENTE DE PRUEBA","receta",
        "7 dias","https://example.invalid/fictitious",
        label_override="DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)",test_mode=True)=="synthetic-only"

assert len(requests)==1 and len(rows)==1
assert rows[0]["mode"]=="test"
assert rows[0]["recipient_hash"]==hashlib.sha256(b"593999999999").hexdigest()
assert "core.whatsapp_send_template" not in source
assert "core.WHATSAPP_ACCESS_TOKEN" not in source
assert '"WHATSAPP_CLINICAL_ACCESS_TOKEN"]' not in source
assert "test_mode=True)" in source
assert "if not _setup()[\"ready_document\"]:" in source
assert "if not _setup()[\"ready_video\"]:" in source
assert 'if (u.pathname === "/clinical/dispatch") return serveClinicalDispatch(request,env);' in worker
print("RECEPTION_CLINICAL_UNIFIED_WORKER_SYNTHETIC_NO_PATIENTS_NO_LOCAL_META_OK")
