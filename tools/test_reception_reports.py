from pathlib import Path
import ast
import json

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
front = (ROOT / "recepcion/app/static/app.js").read_text(encoding="utf-8")
version = json.loads((ROOT / "recepcion/app/recepcion-version.json").read_text(encoding="utf-8"))["version"]
manifest = json.loads((ROOT / "recepcion/app/update_manifest.json").read_text(encoding="utf-8"))

ast.parse(core)
assert version == manifest["version"] == manifest["app_version"] == manifest["runtime_version"]
assert "from decimal import Decimal, ROUND_HALF_UP" in core
assert '"unique_patients": unique_patient_count' in core
assert '"integrity": {' in core and '"ok": integrity_ok' in core
assert "_validate_report_xlsx_bytes(content)" in core
assert '<sheetData>{"".join(row_xml)}</sheetData>{filter_xml}{merge_xml}' in core
assert '<sheetData>{"".join(row_xml)}</sheetData>{merge_xml}{filter_xml}' not in core
assert "Pacientes únicos" in front and "Control de totales" in front
assert "d.integrity?.ok" in front
print("RECEPTION_REPORTS_STATIC_OK", version)
