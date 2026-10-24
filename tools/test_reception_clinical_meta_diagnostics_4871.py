"""No-network checks for safe clinical Meta failure diagnostics."""
import ast
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

root = Path(__file__).resolve().parents[1]
clinical = (root / "recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
client_path = root / "recepcion/app/whatsapp_client.py"

# Execute only the pure diagnostic helper: no core/Neon/R2/Meta connections.
tree = ast.parse(clinical)
helper = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "_clinical_test_meta_failure")
namespace = {}
exec(compile(ast.Module(body=[helper], type_ignores=[]), "clinical_meta_helper", "exec"), namespace)
safe = namespace["_clinical_test_meta_failure"]

spec = importlib.util.spec_from_file_location("clinical_wa_test_client", client_path)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
original = client.urllib.request.urlopen

def failed_meta(_request, timeout=15):
    payload = {"error": {"message": "SECRET_TOKEN_123 +593912345678 https://signed.example/path?signature=veryprivate",
                         "code": 132001, "error_subcode": 2593006}}
    raise urllib.error.HTTPError("https://graph.facebook.com", 400, "Bad Request", {},
                                  io.BytesIO(json.dumps(payload).encode()))

try:
    client.urllib.request.urlopen = failed_meta
    try:
        client.send_template(graph_version="v26.0", phone_number_id="1234567890",
                             access_token="super-secret-value",
                             payload={"type": "template"})
        assert False, "Expected Meta rejection"
    except client.WhatsAppError as exc:
        assert exc.meta_http_status == 400
        assert exc.meta_error_code == 132001
        assert exc.meta_error_subcode == 2593006
        hint = safe(exc)
        assert "HTTP 400" in hint and "código 132001" in hint
        assert "subcódigo" not in hint  # Suppress unexpected/unbounded Meta values.
        assert "plantilla" in hint.lower()
        for forbidden in ("SECRET_TOKEN", "+5939", "signed.example", "veryprivate", "super-secret-value"):
            assert forbidden not in hint
finally:
    client.urllib.request.urlopen = original

unknown = client.WhatsAppError("TOKEN_SECRET and phone 593912345678")
assert "TOKEN_SECRET" not in safe(unknown)
assert "no se pudo confirmar" in safe(unknown).lower()

assert 'except core.WhatsAppError as exc:' in clinical
assert 'raise core.HTTPException(502, _clinical_test_meta_failure(exc)) from exc' in clinical
assert 'CLINICAL_DELIVERY_LIVE_ENABLED' in clinical
assert 'WHATSAPP_TEST_PHONE' in clinical
assert 'time.monotonic() - _LAST_TEST_SEND < 300' in clinical
print("CLINICAL_META_DIAGNOSTICS_NO_NETWORK_OK")
