"""Offline contract: read local clinical config without mutating patient, WhatsApp or global settings."""
import ast
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
source = (root / "recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
tree = ast.parse(source)
functions = {"_clinical_settings", "_clinical_setting", "_setup"}
isolated = ast.fix_missing_locations(ast.Module(
    body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions],
    type_ignores=[],
))
saved = {
    "CLINICAL_R2_ACCOUNT_ID": "a" * 32,
    "CLINICAL_R2_BUCKET": "dr-revelo-clinical-2026",
    "CLINICAL_R2_ACCESS_KEY_ID": "B" * 32,
    "CLINICAL_R2_SECRET_ACCESS_KEY": "C" * 64,
    "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED": "1",
    "WHATSAPP_GRAPH_VERSION": "v26.0",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789012345",
    "WHATSAPP_ACCESS_TOKEN": "E" * 80,
    "WHATSAPP_TEST_PHONE": "0999999999",
    "CLINICAL_DELIVERY_LAN_SECRET": "f" * 64,
    "CLINICAL_DELIVERY_LIVE_ENABLED": "0",
    "WHATSAPP_CLINICAL_TEMPLATES_APPROVED": "0",
}
config = SimpleNamespace(ALLOWED=set(saved) | {
    "WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE", "WHATSAPP_CLINICAL_VIDEO_TEMPLATE",
    "WHATSAPP_CLINICAL_LANGUAGE",
}, parse_existing=lambda: dict(saved))
core = SimpleNamespace(
    WHATSAPP_GRAPH_VERSION="", WHATSAPP_PHONE_NUMBER_ID="",
    WHATSAPP_ACCESS_TOKEN="", WHATSAPP_TEST_PHONE="",
)
ns = {"clinical_config": config, "os": os, "re": re, "core": core}
exec(compile(isolated, "clinical_config_offline_4861", "exec"), ns)
with patch.dict(os.environ, {
    "CLINICAL_R2_ACCOUNT_ID": "stale-account-value",
    "CLINICAL_DELIVERY_LIVE_ENABLED": "0",
    "WHATSAPP_ACCESS_TOKEN": "stale-wrong-token",
    "DATABASE_URL": "do-not-touch",
    "WHATSAPP_CLOUD_MODE": "1",
}, clear=True):
    original_env = dict(os.environ)
    loaded = ns["_clinical_settings"]()
    assert loaded["CLINICAL_R2_ACCOUNT_ID"] == "a" * 32
    assert loaded["WHATSAPP_ACCESS_TOKEN"] == "E" * 80
    assert loaded["CLINICAL_DELIVERY_LAN_SECRET"] == "f" * 64
    assert dict(os.environ) == original_env, "Clinical read changed global application credentials"
    status = ns["_setup"]()
    assert status["ready_r2"] is True
    assert status["ready_whatsapp"] is True
    assert status["ready_document"] is False
    assert status["ready_video"] is False
    assert status["ready_test"] is False
    assert status["clinical_templates_approved"] is False
    assert status["clinical_delivery_enabled"] is False
    assert dict(os.environ) == original_env
    saved["WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE"] = "entrega_documento_clinico"
    saved["WHATSAPP_CLINICAL_VIDEO_TEMPLATE"] = "entrega_video_clinico"
    status = ns["_setup"]()
    assert status["ready_document"] is False
    assert status["ready_test"] is False, "Template names alone cannot enable sending"
    saved["WHATSAPP_CLINICAL_TEMPLATES_APPROVED"] = "1"
    status = ns["_setup"]()
    assert status["ready_document"] is False, "Explicit live opt-in is mandatory"
    assert status["ready_test"] is True, "Synthetic self-test must be available before patient delivery"
    assert status["ready_video"] is False, "Patient delivery must remain blocked until separate activation"
    saved["CLINICAL_DELIVERY_LIVE_ENABLED"] = "1"
    status = ns["_setup"]()
    assert status["ready_document"] is True
    assert status["ready_video"] is True
    assert status["ready_test"] is True
    assert dict(os.environ) == original_env

assert 'certificate_type=\'rest_isolation\'' in source
assert 'WHEN certificate_type IN (\'report_cystoscopy\',\'report_ultrasound\')' in source
assert "def _linked_patient(pid):" in source
assert "l.verified=1" in source
print("CLINICAL_CONFIG_4861_LOCAL_VALUES_FAIL_CLOSED_NO_GLOBAL_MUTATION_OK")
