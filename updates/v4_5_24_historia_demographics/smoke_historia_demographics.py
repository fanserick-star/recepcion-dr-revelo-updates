from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent
for name in ("app.py", "app_patch_4505.py", "app_patch_4507.py", "app_patch_4523.py", "app_patch_4524.py", "historia_bridge.py", "historia_lan_transport.py"):
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


legacy = (ROOT / "app_patch_4505.py").read_text(encoding="utf-8")
manual = (ROOT / "app_patch_4507.py").read_text(encoding="utf-8")
operation = (ROOT / "app_patch_4523.py").read_text(encoding="utf-8")

if "if(window.__v4507BendoManual||window.__v4523BendoOperation)return;" not in legacy:
    raise AssertionError("Legacy v4.5.5 dataphone blocker is not inert under Bendo")
if "const observer=new MutationObserver" in operation:
    raise AssertionError("Global Bendo MutationObserver must not ship in v4.5.24")
if "setTimeout(patchPayment,550)" in manual or "setTimeout(boot,1100)" in manual:
    raise AssertionError("Legacy Bendo repaint timers were not reduced")
if "setTimeout(()=>{patchFlow();patchConfig()},70)" not in operation:
    raise AssertionError("Targeted Bendo refresh missing")
print("BENDO_PERFORMANCE_OK")
