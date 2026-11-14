"""Read-only regression: 409 diagnostics are safe, actionable, and never bypass preflight."""
import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
app = (root / "recepcion/app/static/app.js").read_text(encoding="utf-8")
src = (root / "recepcion/app/reception_history_neon_selector.py").read_text(encoding="utf-8")
manifest = json.loads((root / "recepcion/app/update_manifest.json").read_text(encoding="utf-8"))

assert "data.detail||data.message||" in app
tree = ast.parse(src)
funcs = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_safe_check_error"]
assert len(funcs)==1
# Synthetic reasons only; no connections, patient records or secret paths.
namespace={}
exec(compile(ast.Module(body=funcs,type_ignores=[]),"safe_errors","exec"),namespace)
class SafeError(Exception): pass
check=namespace["_safe_check_error"]
assert check(SafeError("Neon Emergencia de Historia no configurado en Recepción"))["code"]=="private_connection_missing"
assert check(SafeError("conexión a un proyecto distinto"))["code"]=="private_connection_mismatch"
assert check(SafeError("Vinculaciones duplicadas"))["code"]=="links_need_review"
assert check(SafeError("cola offline"))["code"]=="pending_queue_unavailable"
assert check(SafeError("Comparación vencida"))["code"]=="check_expired"
assert check(SafeError("Diferencias pendientes"))["code"]=="links_or_queue_pending"
secret="postgresql://sensitive:password@private-host/db"
assert secret not in json.dumps(check(SafeError(secret)))
assert "status_code=409" in src
assert '_preflight(target)' in src and '_write_pending(target)' in src
assert tuple(map(int, manifest["version"].split("."))) >= (4, 8, 143)
print("RECEPTION_48143_SAFE_409_DIAGNOSTICS_NO_SECRET_NO_BYPASS_OK")
