from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
PATCH = ROOT / "app_patch_4523.py"
APP = ROOT / "app.py"

source = PATCH.read_text(encoding="utf-8")
ast.parse(source)
ast.parse(APP.read_text(encoding="utf-8"))

required = [
    'APP_VERSION = "4.5.23"',
    "N.º de operación Bendo",
    "PAGO EXITOSO",
    "body.card_reference=referenceValue()",
    "delete body.voucher",
    "zero_amount_approval_blocked",
    "stores_pan",
    "stores_cvv",
]
for token in required:
    if token not in source:
        raise AssertionError(f"Missing v4.5.23 contract token: {token}")

if '"database_schema_changes": False' not in source:
    raise AssertionError("v4.5.23 must not change the database schema")

print("Recepcion v4.5.23 Bendo operation smoke: OK")
