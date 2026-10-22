"""Fail-closed static regression checks for the 4.8.42 billing workspace.

No Neon credentials, real invoices, network calls or database writes.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def function(tree: ast.AST, name: str) -> ast.FunctionDef:
    nodes = [x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef) and x.name == name]
    assert len(nodes) == 1, (name, len(nodes))
    return nodes[0]


def main() -> None:
    manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))
    version = json.loads((APP / "recepcion-version.json").read_text(encoding="utf-8"))["version"]
    assert version == manifest["version"] == manifest["app_version"] == manifest["runtime_version"] in {"4.8.42","4.8.43","4.8.44","4.8.45","4.8.46","4.8.47","4.8.48","4.8.49","4.8.50","4.8.51","4.8.52","4.8.53","4.8.54","4.8.56","4.8.57"}
    for item in ("static/billing_advanced.css", "static/billing_advanced.js"):
        assert item in manifest["copy"], ("Not shipped by launcher", item)
        assert item in manifest["required_dependencies"], ("Not required", item)
        assert (APP / item).is_file()

    html = (APP / "static/index.html").read_text(encoding="utf-8")
    assert f'billing_advanced.css?v={version}' in html
    assert f'billing_advanced.js?v={version}' in html
    assert html.index('<script src="/static/app.js') < html.index('<script src="/static/billing_advanced.js')

    client = (APP / "static/billing_advanced.js").read_text(encoding="utf-8")
    for label in (
        "v4842-workspace", "v4842-detail", "rpBillingReview",
        "rpBillingConfirm", "rpBillingSelect", "rpBillingExportVisible",
        "azur/preview", "billing/approve", "checkAzurInvoiceStatus",
        "pre.unlocked", "if (!pre.unlocked)",
        "singleFlightMutation",
    ):
        assert label in client, ("Billing workspace feature absent", label)
    assert "api('/api/billing/azur/emit',{method:'POST'" not in client
    assert "setInterval(" not in client, "Do not introduce polling"

    core_text = (APP / "core_runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(core_text)
    preview = ast.get_source_segment(core_text, function(tree, "billing_azur_batch_preview"))
    batch = ast.get_source_segment(core_text, function(tree, "billing_azur_emit_all_pending"))
    assert preview and batch
    assert '"unlocked": _azur_mass_unlocked(db)' in preview
    assert 'if not _azur_mass_unlocked(db):' in batch
    assert 'raise HTTPException(409, "La emisión por lotes está bloqueada' in batch
    assert batch.index("if not _azur_mass_unlocked(db):") < batch.index("for patient_id, fecha, _ in grouped:")
    assert "AZUR_LIVE_EMISSION" in batch and "is_offline_db(db)" in batch

    vanilla = (APP / "static/app.js").read_text(encoding="utf-8")
    assert "function billingMissingFields(p={}){" in vanilla
    billing_fields = vanilla.split("function billingMissingFields(p={}){", 1)[1].split("}", 1)[0]
    assert "push('correo')" not in billing_fields, "Email must remain optional"
    assert "['cédula'].includes(x)" in vanilla
    assert "if (window.__rpBilling4842) return;" in client, "Billing workspace must boot only once"
    print("RECEPTION_BILLING_4842_SAFE_STATIC_OK")


if __name__ == "__main__":
    main()
