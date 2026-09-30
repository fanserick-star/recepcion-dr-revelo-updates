from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"
CORE = APP / "core_runtime.py"
FRONT = APP / "static" / "app.js"
VERSION = APP / "recepcion-version.json"
MANIFEST = APP / "update_manifest.json"
WORKFLOW = ROOT / ".github" / "workflows" / "publish-reception-app-channel.yml"
TEST = ROOT / "tools" / "test_reception_reports.py"
OLD = "4.6.26"
NEW = "4.6.27"


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


core = CORE.read_text(encoding="utf-8")
core = once(
    core,
    "from datetime import date, datetime, timedelta\nfrom typing import Optional",
    "from datetime import date, datetime, timedelta\nfrom decimal import Decimal, ROUND_HALF_UP\nfrom typing import Optional",
    "decimal import",
)
core = once(
    core,
    "from xml.sax.saxutils import escape as xml_escape",
    "from xml.sax.saxutils import escape as xml_escape\nfrom xml.etree import ElementTree as ET",
    "ElementTree import",
)

helpers = '''\n_REPORT_CENT = Decimal("0.01")\n\ndef _report_money(value) -> Decimal:\n    """Convierte cualquier valor monetario del reporte a centavos exactos."""\n    if value is None:\n        return Decimal("0.00")\n    amount = value if isinstance(value, Decimal) else Decimal(str(value))\n    return amount.quantize(_REPORT_CENT, rounding=ROUND_HALF_UP)\n\ndef _report_money_float(value) -> float:\n    return float(_report_money(value))\n\n'''
core = once(core, "\ndef build_report_data(rows):\n", helpers + "\ndef build_report_data(rows):\n", "report money helpers")

start = core.index("def build_report_data(rows):")
end = core.index("\ndef _xlsx_col_name", start)
body = core[start:end]

body = once(
    body,
    "    turns = _v4457_consultation_turns(patient_days)\n",
    "    turns = _v4457_consultation_turns(patient_days)\n    unique_patient_count = len({int(p.id) for _v, p in rows})\n",
    "unique patients",
)
body = once(
    body,
    '            "consultations": 0, "procedures": 0, "total": 0.0,',
    '            "consultations": 0, "procedures": 0, "total": Decimal("0.00"),',
    "daily decimal",
)
body = once(body, "            value = float(v.valor or 0)", "            value = _report_money(v.valor)", "visit decimal")
body = once(
    body,
    '            st = service_totals.setdefault(service, {"service": service, "count": 0, "total": 0.0})',
    '            st = service_totals.setdefault(service, {"service": service, "count": 0, "total": Decimal("0.00")})',
    "service decimal",
)
body = once(body, '                "value": value,', '                "value": _report_money_float(value),', "detail decimal output")
body = once(
    body,
    "    days = [daily[d] for d in sorted(daily)]\n",
    "    for item in daily.values():\n        item[\"total\"] = _report_money_float(item[\"total\"])\n    for item in service_totals.values():\n        item[\"total\"] = _report_money_float(item[\"total\"])\n\n    days = [daily[d] for d in sorted(daily)]\n",
    "decimal output conversion",
)
body = once(
    body,
    "    total = sum(float(v.valor or 0) for v, _ in rows)\n",
    "    total_decimal = sum((_report_money(v.valor) for v, _ in rows), Decimal(\"0.00\"))\n    total = _report_money_float(total_decimal)\n    detail_total_decimal = sum((_report_money(item.get(\"value\")) for item in detail_rows), Decimal(\"0.00\"))\n    service_total_decimal = sum((_report_money(item.get(\"total\")) for item in services), Decimal(\"0.00\"))\n    day_total_decimal = sum((_report_money(item.get(\"total\")) for item in days), Decimal(\"0.00\"))\n    integrity_ok = total_decimal == detail_total_decimal == service_total_decimal == day_total_decimal\n",
    "report integrity totals",
)
body = once(
    body,
    '        "patients": patient_count,\n',
    '        "patients": patient_count,\n        "unique_patients": unique_patient_count,\n',
    "unique patients response",
)
body = once(
    body,
    '        "days": days,\n        "details": detail_rows,',
    '        "days": days,\n        "integrity": {\n            "ok": integrity_ok,\n            "detail_total": _report_money_float(detail_total_decimal),\n            "service_total": _report_money_float(service_total_decimal),\n            "day_total": _report_money_float(day_total_decimal),\n            "overall_total": total,\n        },\n        "details": detail_rows,',
    "integrity response",
)
core = core[:start] + body + core[end:]

# Keep monthly comparison compatible while exposing the new unique-person metric.
core = once(
    core,
    '                "patients": prev["patients"], "N": prev["N"], "S": prev["S"],',
    '                "patients": prev["patients"], "unique_patients": prev.get("unique_patients", prev["patients"]), "N": prev["N"], "S": prev["S"],',
    "comparison unique patients",
)

# SpreadsheetML requires autoFilter before mergeCells in worksheet child order.
core = once(
    core,
    '        f\'<sheetData>{"".join(row_xml)}</sheetData>{merge_xml}{filter_xml}\'\n',
    '        f\'<sheetData>{"".join(row_xml)}</sheetData>{filter_xml}{merge_xml}\'\n',
    "xlsx worksheet element order",
)

validator = '''\ndef _validate_report_xlsx_bytes(content: bytes) -> None:\n    """Fail closed before saving/sending an XLSX whose package is malformed."""\n    required = {\n        "[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",\n        "xl/_rels/workbook.xml.rels", "xl/styles.xml",\n        "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml",\n    }\n    try:\n        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:\n            names = set(zf.namelist())\n            missing = sorted(required - names)\n            if missing:\n                raise ValueError("faltan partes XLSX: " + ", ".join(missing))\n            for name in required:\n                if name.endswith(".xml") or name.endswith(".rels"):\n                    ET.fromstring(zf.read(name))\n            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"\n            for name in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):\n                root = ET.fromstring(zf.read(name))\n                tags = [child.tag.removeprefix(ns) for child in list(root)]\n                if "autoFilter" in tags and "mergeCells" in tags:\n                    if tags.index("autoFilter") > tags.index("mergeCells"):\n                        raise ValueError(f"orden SpreadsheetML inválido en {name}")\n    except Exception as exc:\n        raise RuntimeError(f"No se pudo generar un Excel compatible: {exc}") from exc\n\n'''
core = once(core, "\ndef build_report_xlsx(data: dict, desde: date, hasta: date) -> bytes:\n", validator + "\ndef build_report_xlsx(data: dict, desde: date, hasta: date) -> bytes:\n", "xlsx validator")
core = once(
    core,
    '    period = f"Período: {desde.strftime(\'%d/%m/%Y\')} al {hasta.strftime(\'%d/%m/%Y\')}"\n',
    '    integrity_label = "Totales verificados" if (data.get("integrity") or {}).get("ok") else "REVISAR TOTALES"\n    period = f"Período: {desde.strftime(\'%d/%m/%Y\')} al {hasta.strftime(\'%d/%m/%Y\')} · Pacientes únicos: {data.get(\'unique_patients\', data.get(\'patients\', 0))} · {integrity_label}"\n',
    "xlsx report header",
)
core = once(
    core,
    "        z.writestr('xl/worksheets/sheet2.xml', detail_xml)\n    return out.getvalue()\n",
    "        z.writestr('xl/worksheets/sheet2.xml', detail_xml)\n    content = out.getvalue()\n    _validate_report_xlsx_bytes(content)\n    return content\n",
    "xlsx validate before return",
)
CORE.write_text(core, encoding="utf-8")

front = FRONT.read_text(encoding="utf-8")
front = once(
    front,
    "  const current={patients:d.patients,consultations:d.consultations,P:d.P,total:d.total};\n  const cards=[\n    ['Pacientes',current.patients,prev.patients,false],",
    "  const current={patients:d.patients,unique_patients:d.unique_patients??d.patients,consultations:d.consultations,P:d.P,total:d.total};\n  const cards=[\n    ['Atenciones paciente/día',current.patients,prev.patients,false],\n    ['Pacientes únicos',current.unique_patients,prev.unique_patients??prev.patients,false],",
    "report comparison unique patients",
)
front = once(
    front,
    '      <div class="report-kpi"><span>Pacientes atendidos</span><b>${d.patients}</b></div>\n      <div class="report-kpi"><span>Nuevos</span><b>${d.N}</b></div>',
    '      <div class="report-kpi"><span>Atenciones paciente/día</span><b>${d.patients}</b></div>\n      <div class="report-kpi"><span>Pacientes únicos</span><b>${d.unique_patients??d.patients}</b></div>\n      <div class="report-kpi"><span>Nuevos</span><b>${d.N}</b></div>',
    "report unique patient KPI",
)
front = once(
    front,
    '      <div class="report-kpi money"><span>Total del período</span><b>${money(d.total)}</b></div>`;',
    '      <div class="report-kpi money"><span>Total del período</span><b>${money(d.total)}</b></div>\n      <div class="report-kpi"><span>Control de totales</span><b>${d.integrity?.ok?\'✓ Verificado\':\'⚠ Revisar\'}</b></div>`;',
    "report integrity KPI",
)
FRONT.write_text(front, encoding="utf-8")

VERSION.write_text(json.dumps({"version": NEW}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
for key in ("version", "app_version", "runtime_version"):
    manifest[key] = NEW
notes = manifest.setdefault("notes", {})
notes.update({
    "purpose": "Audita y blinda Reportes: dinero exacto por centavos, pacientes únicos, control cruzado de totales, eliminación sin saldos fantasma y XLSX compatible/autovalidado.",
    "previous_version": OLD,
    "reports_decimal_money": True,
    "reports_unique_patients": True,
    "reports_cross_total_integrity": True,
    "reports_deleted_visits_recalculated": True,
    "xlsx_spreadsheetml_order_fixed": True,
    "xlsx_runtime_package_validation": True,
    "xlsx_no_new_runtime_dependency": True,
    "database_schema_changes": False,
    "patient_data_changes": False,
    "patient_data_destructive_changes": False,
    "billing_logic_changes": False,
    "azur_logic_changes": False,
    "whatsapp_logic_changes": False,
    "procedure_logic_changes": False,
    "printing_changes": False,
    "production_status": "stable",
    "rollback_safe": True,
})
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

TEST.write_text(r'''from pathlib import Path
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
''', encoding="utf-8")

workflow = WORKFLOW.read_text(encoding="utf-8")
needle = "      - name: Validate runtime layout\n        run: python tools/validate_reception_runtime_layout.py recepcion/app\n"
if "Validate report invariants" not in workflow:
    if needle not in workflow:
        raise SystemExit("publisher workflow anchor not found")
    workflow = workflow.replace(
        needle,
        needle + "\n      - name: Validate report invariants\n        run: python tools/test_reception_reports.py\n",
        1,
    )
WORKFLOW.write_text(workflow, encoding="utf-8")

print("PATCH_RECEPTION_REPORTS_OK", NEW)
