from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
for name in ("app.py", "app_patch_4524.py", "historia_bridge.py", "historia_lan_transport.py"):
    ast.parse((ROOT / name).read_text(encoding="utf-8"))

app = (ROOT / "app_patch_4524.py").read_text(encoding="utf-8")
bridge = (ROOT / "historia_bridge.py").read_text(encoding="utf-8")
lan = (ROOT / "historia_lan_transport.py").read_text(encoding="utf-8")

for token in (
    'APP_VERSION = "4.5.24"',
    "birth_date=str(birth or \"\")",
    'phone=str(getattr(patient, "celular", "") or "")',
    'email=str(getattr(patient, "correo", "") or "")',
    'address=str(getattr(patient, "lugar", "") or "")',
):
    if token not in app:
        raise AssertionError(f"Missing app contract: {token}")

for token in (
    '"birth_date": _clean(birth_date, 20)',
    '"phone": _clean(phone, 80)',
    '"email": _clean(email, 180)',
    '"address": _clean(address, 360)',
    "cloud_new_demographics",
):
    if token not in bridge:
        raise AssertionError(f"Missing cloud bridge contract: {token}")

for token in (
    "birth_date=birth_date",
    "phone=phone",
    "email=email",
    "address=address",
):
    if token not in lan:
        raise AssertionError(f"Missing LAN contract: {token}")

print("RECEPCION_4524_HISTORIA_DEMOGRAPHICS_OK")
