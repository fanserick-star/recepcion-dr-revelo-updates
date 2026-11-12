"""No-dependency safety checks for the 1.4.89 Neon settings UI.

Canonical/publisher CI runs BEFORE FastAPI is installed, so parse the module
without importing runtime dependencies. Windows runtime validation separately
imports the actual application with its pinned packages installed.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
SOURCE = (APP/"app.py").read_text(encoding="utf8")
PANEL = (APP/"neon_return_settings.py").read_text(encoding="utf8")

for file in (APP/"app.py",APP/"neon_return_settings.py"):
    ast.parse(file.read_text(encoding="utf8"))

assert "neon_return_settings.complete_scheduled_return(ROOT, DB_PATH)" in SOURCE
assert SOURCE.index("neon_return_settings.complete_scheduled_return") < SOURCE.index("SYNC_SERVICE = build_sync_service(")
assert "neon_return_settings.install(app, ROOT, DB_PATH, base)" in SOURCE

for endpoint in ("/configuracion/neon","/api/neon/return/check","/api/neon/return/authorize"):
    assert endpoint in PANEL
assert "Sincronizar y cambiar al Neon Oficial" in PANEL
assert "neon-return-oneclick" in PANEL
assert "/api/neon/return/prepare" in PANEL
assert "check_automatic_return(report, private)" in PANEL
assert "transfer(" in PANEL
assert "neon_return_before_copy.sqlite" in PANEL
assert "SET TRANSACTION READ ONLY" in PANEL
assert "neon_return_before_switch.sqlite" in PANEL
assert "plan_sha256" in PANEL
assert "quick_check" in PANEL
assert "_verify_complete(report)" in PANEL
assert "_stop_if_unsafe(root, require_backups=True)" in PANEL
assert "input type='password'" not in PANEL
assert "cutover-url" not in PANEL
assert "clinical_note" not in PANEL
assert "patient_id" not in PANEL
assert "UPDATE public." not in PANEL

tree=ast.parse(PANEL)
names={node.name for node in tree.body if isinstance(node,ast.FunctionDef)}
assert {"_summary","_compare","_local","_current","_local_health",
        "_make_backup","complete_scheduled_return","install"}.issubset(names)
assert "return {\"state\": \"not_scheduled\"}" in PANEL
assert 'if report["plan_sha256"] != request["plan_sha256"]:' in PANEL
assert 'if health["pending"] != 0 or health["conflicts"] != 0:' in PANEL
assert "Neon Respaldo sigue activo." in PANEL
print("HISTORIA_NEON_SETTINGS_1489_OK")
