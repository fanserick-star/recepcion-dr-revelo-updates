"""Offline regression tests for Neon settings UI and fail-closed switch (1.4.89)."""
from __future__ import annotations

import ast
from pathlib import Path
import sys
from unittest import mock

APP = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
sys.path.insert(0, str(APP))

import neon_return_settings as ui

SOURCE = (APP / "app.py").read_text(encoding="utf8")
PANEL = (APP / "neon_return_settings.py").read_text(encoding="utf8")

for file in (APP/"app.py",APP/"neon_return_settings.py"):
    ast.parse(file.read_text(encoding="utf8"))
assert "neon_return_settings.complete_scheduled_return(ROOT, DB_PATH)" in SOURCE
assert SOURCE.index("neon_return_settings.complete_scheduled_return") < SOURCE.index("SYNC_SERVICE = build_sync_service(")
assert "neon_return_settings.install(app, ROOT, DB_PATH, base)" in SOURCE
for endpoint in ("/configuracion/neon","/api/neon/return/check","/api/neon/return/authorize"):
    assert endpoint in PANEL
assert "Comprobar diferencias" in PANEL
assert "Confirmar regreso al Oficial" in PANEL
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

fixture = {
  "tables": {
    "patients": {
      "source_rows": 10, "official_rows": 10, "missing": 0, "changed": 0,
      "official_only": 0, "source_deleted_diff": 0, "reactivation_conflicts": 0,
      "manual_review": False, "unshared_source_columns": []
    },
    "patient_links": {
      "source_rows": 4, "official_rows": 3, "missing": 1, "changed": 0,
      "official_only": 0, "source_deleted_diff": 0, "reactivation_conflicts": 0,
      "manual_review": True, "unshared_source_columns": []
    }
  },
  "plan_sha256": "a"*64
}
s = ui._summary(fixture)
assert s["missing"]==1 and s["manual_review"]==1 and s["changed"]==0
assert s["source_rows"]==14 and s["official_rows"]==13
with mock.patch.object(ui, "_read_json", return_value={}):
    with mock.patch.object(ui, "_load_credentials", side_effect=RuntimeError("No credentials used")):
        with mock.patch.object(ui, "_current", side_effect=RuntimeError("Should not check without request")):
            assert ui.complete_scheduled_return(APP, APP/"data"/"not_there.db")=={"state":"not_scheduled"}
print("HISTORIA_NEON_SETTINGS_1489_OK")
