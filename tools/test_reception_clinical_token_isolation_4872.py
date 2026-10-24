"""Clinical Meta credentials are isolated; all checks offline and synthetic."""
import ast
import importlib.util
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "recepcion" / "app"
config_path = ROOT / "clinical_delivery_config.py"
clinical_path = ROOT / "clinical_delivery.py"
wizard_path = ROOT / "clinical_delivery_setup.pyw"

source = clinical_path.read_text(encoding="utf-8")
wizard = wizard_path.read_text(encoding="utf-8")
ast.parse(wizard, filename=str(wizard_path))
spec = importlib.util.spec_from_file_location("clinical_token_cfg", config_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert "WHATSAPP_CLINICAL_ACCESS_TOKEN" in module.ALLOWED
assert "WHATSAPP_ACCESS_TOKEN" not in module.ALLOWED

# Existing appointment/worker secrets and existing approval must remain untouched.
with tempfile.TemporaryDirectory(prefix="clinical_token_test_") as directory:
    path = Path(directory) / ".env"
    legacy = "legacy-same-scope-token-98765432101234567890"
    clinical = "new-independent-clinical-token-98765432101234567890"
    path.write_text(
        "WHATSAPP_ACCESS_TOKEN=" + legacy + "\n"
        "WHATSAPP_ENABLED=1\n"
        "WHATSAPP_CLINICAL_TEMPLATES_APPROVED=1\n"
        "CLINICAL_DELIVERY_LIVE_ENABLED=0\n"
        "DATABASE_URL=not-real\n",
        encoding="utf-8",
    )
    module.save_local_settings({"WHATSAPP_CLINICAL_ACCESS_TOKEN": clinical}, path)
    values = module.parse_existing(path)
    assert values["WHATSAPP_CLINICAL_ACCESS_TOKEN"] == clinical
    assert values["WHATSAPP_ACCESS_TOKEN"] == legacy
    assert values["WHATSAPP_ENABLED"] == "1"
    assert values["WHATSAPP_CLINICAL_TEMPLATES_APPROVED"] == "1"
    assert values["CLINICAL_DELIVERY_LIVE_ENABLED"] == "0"
    assert values["DATABASE_URL"] == "not-real"
    assert len([x for x in path.read_text().splitlines() if x.startswith("WHATSAPP_CLINICAL_ACCESS_TOKEN=")]) == 1
    try:
        module.save_local_settings({"WHATSAPP_ACCESS_TOKEN": clinical}, path)
    except ValueError:
        pass
    else:
        raise AssertionError("Clinical wizard must not change appointment token")

# In the wizard, importing previously-saved token is manual, explicit, and non-destructive.
assert 'def save_clinical_token_only():' in wizard
assert 'def copy_existing_token_to_clinical():' in wizard
assert 'existing.get("WHATSAPP_ACCESS_TOKEN"' in wizard
assert 'save_local_settings({"WHATSAPP_CLINICAL_ACCESS_TOKEN":old_token})' in wizard
assert 'save_local_settings({"WHATSAPP_CLINICAL_ACCESS_TOKEN":token})' in wizard
assert '"WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"0"' not in wizard

ast_tree = ast.parse(source)
functions = {node.name: node for node in ast_tree.body if isinstance(node, ast.FunctionDef)}
target_functions = [functions["_setup"], functions["_send_template"]]
ns = {}
exec(compile(ast.Module(body=target_functions, type_ignores=[]), "clinical_token_runtime_test", "exec"), ns)
captured = {}
core = SimpleNamespace(
    WHATSAPP_GRAPH_VERSION="v26.0",
    WHATSAPP_PHONE_NUMBER_ID="1234567890",
    WHATSAPP_TEST_PHONE="",
    whatsapp_build_template_payload=lambda **kw: kw,
    whatsapp_send_template=lambda **kw: captured.setdefault("send", kw) or {"messages":[{"id":"synthetic"}]},
)
# Use stub response with Meta-shaped ID, not real network.
def fake_send(**kw):
    captured["send"] = kw
    return {"messages": [{"id": "synthetic-test-only"}]}
core.whatsapp_send_template = fake_send
ns.update(core=core, re=re, LABELS={"receta":"Receta médica"})
cfg = {key:"" for key in module.ALLOWED}
cfg.update({
    "CLINICAL_R2_ACCOUNT_ID":"a"*32,
    "CLINICAL_R2_BUCKET":"dr-revelo-clinical-2026",
    "CLINICAL_R2_ACCESS_KEY_ID":"b"*32,
    "CLINICAL_R2_SECRET_ACCESS_KEY":"c"*64,
    "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED":"1",
    "WHATSAPP_PHONE_NUMBER_ID":"1234567890",
    "WHATSAPP_GRAPH_VERSION":"v26.0",
    "WHATSAPP_TEST_PHONE":"0999999999",
    "WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE":"entrega_documento_clinico",
    "WHATSAPP_CLINICAL_VIDEO_TEMPLATE":"entrega_video_clinico",
    "WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"1",
    "CLINICAL_DELIVERY_LIVE_ENABLED":"0",
    "WHATSAPP_CLINICAL_LANGUAGE":"es_EC",
})
ns["_clinical_settings"] = lambda: cfg
# Legacy appointment token never grants clinical readiness.
assert not ns["_setup"]()["ready_test"]
assert not ns["_setup"]()["ready_document"]
cfg["WHATSAPP_CLINICAL_ACCESS_TOKEN"] = "dedicated-clinical-token-12345678901234567890"
status = ns["_setup"]()
assert status["ready_test"] and status["ready_whatsapp"]
assert not status["ready_document"] and not status["ready_video"]
assert status["clinical_delivery_enabled"] is False
message_id = ns["_send_template"]("593999999999", "PRUEBA", "receta", "7 dias", "https://example.invalid/test")
assert message_id == "synthetic-test-only"
assert captured["send"]["access_token"] == cfg["WHATSAPP_CLINICAL_ACCESS_TOKEN"]
assert captured["send"]["payload"]["body_params"] == ["PRUEBA", "Receta médica", "7 dias", "https://example.invalid/test"]
assert 'core.WHATSAPP_ACCESS_TOKEN' not in source
assert 'cfg["WHATSAPP_ACCESS_TOKEN"]' not in source
print("CLINICAL_META_TOKEN_ISOLATION_SYNTHETIC_OK")
