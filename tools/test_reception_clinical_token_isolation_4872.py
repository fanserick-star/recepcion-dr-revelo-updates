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

# Wizard no longer requests a local Meta token, while keeping older .env
# values intact to avoid impacting any legacy or appointment configuration.
assert "WHATSAPP_CLINICAL_ACCESS_TOKEN" not in wizard
assert "WHATSAPP_ACCESS_TOKEN" not in wizard
assert '"WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"0"' not in wizard
assert '"CLINICAL_DELIVERY_LIVE_ENABLED":"0"' in wizard

ast_tree = ast.parse(source)
functions = {node.name: node for node in ast_tree.body if isinstance(node, ast.FunctionDef)}
ns = {}
exec(compile(ast.Module(body=[functions["_setup"]],type_ignores=[]),"worker_readiness_test","exec"),ns)
cfg={key:"" for key in module.ALLOWED}
cfg.update({
    "CLINICAL_R2_ACCOUNT_ID":"a"*32,
    "CLINICAL_R2_BUCKET":"dr-revelo-clinical-2026",
    "CLINICAL_R2_ACCESS_KEY_ID":"b"*32,
    "CLINICAL_R2_SECRET_ACCESS_KEY":"c"*64,
    "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED":"1",
    "WHATSAPP_TEST_PHONE":"0999999999",
    "WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE":"entrega_documento_clinico",
    "WHATSAPP_CLINICAL_VIDEO_TEMPLATE":"entrega_video_clinico",
    "WHATSAPP_CLINICAL_TEMPLATES_APPROVED":"1",
    "CLINICAL_DELIVERY_LIVE_ENABLED":"0",
})
core=SimpleNamespace(WHATSAPP_TEST_PHONE="", CloudSessionLocal=None, FORCE_OFFLINE=False)
ns.update(core=core,re=re,_clinical_settings=lambda:cfg)
assert not ns["_setup"]()["ready_test"]
core.CloudSessionLocal=object()
assert ns["_setup"]()["ready_test"]
assert not ns["_setup"]()["ready_document"]
cfg["WHATSAPP_CLINICAL_ACCESS_TOKEN"]="intentionally-ignored"
assert ns["_setup"]()["ready_test"]
core.FORCE_OFFLINE=True
assert not ns["_setup"]()["ready_test"]
send_section=source.split("def _send_template(",1)[1].split("def _audit(",1)[0]
assert "core.whatsapp_send_template" not in send_section
assert "core.WHATSAPP_ACCESS_TOKEN" not in send_section
assert 'WHATSAPP_CLINICAL_ACCESS_TOKEN' not in send_section
assert "CLINICAL_WORKER_URL" in source
assert 'whatsapp_cloud.clinical_delivery_caps' in source
print("CLINICAL_WORKER_TOKEN_ISOLATION_SYNTHETIC_OK")
