from pathlib import Path
import ast
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent

for name in ("app.py", "app_patch_4525.py"):
    ast.parse((ROOT / name).read_text(encoding="utf-8"))

source = (ROOT / "app_patch_4525.py").read_text(encoding="utf-8")
tree = ast.parse(source)
values = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                values[target.id] = node.value.value

js = values.get("V4525_JS", "")
css = values.get("V4525_CSS", "")
if not js or not css:
    raise AssertionError("Missing v4.5.25 JS/CSS overlay")

required = [
    "document.addEventListener('click'",
    '[data-mode="TARJETA"]',
    '[data-v4507-card="1"]',
    "event.stopImmediatePropagation()",
    "state.active=true",
    "render();",
    "Confirmar PAGO EXITOSO",
    "N.º de operación Bendo",
    "Bendo Smart · manual",
    "/api/visits/batch-payment",
]
for token in required:
    if token not in js:
        raise AssertionError(f"Missing direct-click contract: {token}")

if "MutationObserver" in js:
    raise AssertionError("v4.5.25 must not use MutationObserver")
if "setTimeout(" in js:
    raise AssertionError("v4.5.25 direct card flow must not depend on timers")

with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as fh:
    fh.write(js)
    js_path = fh.name

subprocess.run(["node", "--check", js_path], check=True)
print("BENDO_4525_DIRECT_CLICK_OK")
