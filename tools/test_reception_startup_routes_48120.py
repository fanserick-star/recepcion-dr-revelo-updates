"""Regresión: Uvicorn nunca debe arrancar antes de registrar endpoints."""
from pathlib import Path
import ast
import json

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/app.py").read_text(encoding="utf-8")
tree = ast.parse(source)
top = tree.body

main_blocks = [
    (i, n) for i, n in enumerate(top)
    if isinstance(n, ast.If)
    and isinstance(n.test, ast.Compare)
    and isinstance(n.test.left, ast.Name)
    and n.test.left.id == "__name__"
    and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in n.test.comparators)
]
assert len(main_blocks) == 1, "Debe existir un único arranque principal"
index, main = main_blocks[0]
assert index == len(top) - 1, "El arranque Uvicorn debe ser la última instrucción del archivo"
assert any(
    isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
    and isinstance(n.value.func, ast.Attribute)
    and n.value.func.attr == "run"
    for n in main.body
), "Se perdió el arranque Uvicorn"

routes = {}
for i, node in enumerate(top):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr not in {"get", "post", "middleware"}:
            continue
        if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            routes[(decorator.func.attr, str(decorator.args[0].value))] = i

for requirement in [
    ("get", "/api/ops/performance"),
    ("get", "/api/historia/visit-delivery-status"),
    ("post", "/api/visits/batch-payment"),
    ("middleware", "http"),
]:
    assert requirement in routes, f"Falta endpoint/interceptor {requirement}"
    assert routes[requirement] < index, f"Endpoint después del inicio: {requirement}"

version = json.loads((ROOT / "recepcion/app/recepcion-version.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "recepcion/app/update_manifest.json").read_text(encoding="utf-8"))
assert version["version"] == "4.8.120"
assert all(manifest[field] == version["version"] for field in ("version", "app_version", "runtime_version"))
print("RECEPTION SERVER STARTUP ROUTES ORDER OK")
