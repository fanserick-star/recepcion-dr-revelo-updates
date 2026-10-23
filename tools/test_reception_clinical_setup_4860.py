"""Synthetic contract for local setup; cannot touch real patient data or credentials."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"recepcion"/"app"
config=APP/"clinical_delivery_config.py"
wizard=APP/"clinical_delivery_setup.pyw"
for p in (config,wizard):
    ast.parse(p.read_text(encoding="utf-8"),filename=str(p))
spec=importlib.util.spec_from_file_location("clinical_delivery_config_4860",config)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix="rp_clinical_4860_") as d:
    p=Path(d)/".env"
    p.write_text("DATABASE_URL=private-not-touched\nWHATSAPP_AUTO_CITA_AGENDADA=1\n"
                 "CLINICAL_R2_ACCOUNT_ID=00000000000000000000000000000000\n",
                 encoding="utf-8")
    fake={
        "CLINICAL_R2_ACCOUNT_ID":"a"*32,
        "CLINICAL_R2_BUCKET":"dr-revelo-clinical-2026",
        "CLINICAL_R2_ACCESS_KEY_ID":"B"*32,
        "CLINICAL_R2_SECRET_ACCESS_KEY":"C"*64,
        "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED":"1",
        "CLINICAL_DELIVERY_LIVE_ENABLED":"0",
        "WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"0",
        "WHATSAPP_GRAPH_VERSION":"v26.0",
        "WHATSAPP_TEST_PHONE":"0999999999",
    }
    m.save_local_settings(fake,p)
    one=m.parse_existing(p)
    assert one["DATABASE_URL"]=="private-not-touched"
    assert one["WHATSAPP_AUTO_CITA_AGENDADA"]=="1"
    assert one["CLINICAL_R2_ACCOUNT_ID"]=="a"*32
    assert one["CLINICAL_R2_BUCKET"]=="dr-revelo-clinical-2026"
    assert one["CLINICAL_DELIVERY_LIVE_ENABLED"]=="0"
    assert one["WHATSAPP_CLINICAL_TEMPLATES_APPROVED"]=="0"
    m.save_local_settings({"WHATSAPP_TEST_PHONE":"593999999999"},p)
    assert len([s for s in p.read_text().splitlines() if s.startswith("WHATSAPP_TEST_PHONE=")])==1
    assert m.parse_existing(p)["CLINICAL_R2_SECRET_ACCESS_KEY"]=="C"*64
    for invalid in (
        {"DATABASE_URL":"another-database"},
        {"WHATSAPP_ACCESS_TOKEN":"abc\nWHATSAPP_ENABLED=1"},
        {"CLINICAL_R2_BUCKET":"a-different-bucket"},
        {"WHATSAPP_GRAPH_VERSION":"v26broken0"},
    ):
        try:
            m.save_local_settings(invalid,p)
        except ValueError:pass
        else:raise AssertionError("Unexpected acceptance of forbidden settings")
    assert m.parse_existing(p)["WHATSAPP_AUTO_CITA_AGENDADA"]=="1"
delivery=(APP/"clinical_delivery.py").read_text(encoding="utf-8")
assert 'live_enabled=cfg["CLINICAL_DELIVERY_LIVE_ENABLED"]=="1"' in delivery
assert 'approved=cfg["WHATSAPP_CLINICAL_TEMPLATES_APPROVED"]=="1"' in delivery
assert 'ready_test=bool(live_enabled and approved and ready_r2' in delivery
assert '"ready_document":bool(live_enabled and approved' in delivery
assert '"ready_video":bool(live_enabled and approved' in delivery
manifest=json.loads((APP/"update_manifest.json").read_text())
for filename in ("clinical_delivery_config.py","clinical_delivery_setup.pyw","Configurar_envios_clinicos.vbs"):
    assert filename in manifest["copy"] and (APP/filename).is_file()
assert manifest["version"]=="4.8.61"
assert 'pythonw.exe' in (APP/"Configurar_envios_clinicos.vbs").read_text()
print("CLINICAL_SETUP_4860_NO_PATIENTS_FAIL_CLOSED_OK")
