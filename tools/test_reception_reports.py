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


# Billing history: verified read-only paging, today first, historical recovery.
history = (ROOT / "recepcion/app/reception_billing_history.py").read_text(encoding="utf-8")
history_ast = ast.parse(history)
function_names = {"_issued_page_keys", "_issued_archive_key"}
functions = [node for node in ast.walk(history_ast)
             if isinstance(node, ast.FunctionDef) and node.name in function_names]
assert len(functions) == 2
namespace = {}
exec(compile(ast.Module(body=functions, type_ignores=[]), "billing-paging-functions", "exec"), namespace)
page_keys = namespace["_issued_page_keys"]

today = "2026-10-08"
archive_today = [
    {"patient": {"id": 777}, "visit": {"id": 100, "fecha": today}},
    {"patient": {"id": 777}, "visit": {"id": 99, "fecha": today}},
]
regular_today = [(i, today, i) for i in range(1, 26)]
first = page_keys(regular_today[-20:], archive_today, 1, 20)
second = page_keys(regular_today, archive_today, 2, 20)
assert len(first) == 20 and len(second) == 6
assert len(set(first + second)) == 26
assert (777, today) in first
assert first[0] == (777, today)
assert first[-1] == (7, today)
assert second[-1] == (1, today)

older = [(i, "2026-09-15", i) for i in range(1, 36)]
assert len(page_keys(older[:20], [], 1, 20)) == 20
assert len(page_keys(older, [], 2, 20)) == 15

route = history.split("def billing_issued_page(", 1)[1].split(
    "    _stable_safe_delete_patient =", 1
)[0]
assert "@app.get('/api/billing/issued-page')" in history
assert "scope not in {'today', 'previous'}" in route
assert "_issued_group_query(hidden, scope)" in route
assert ".limit(page * ISSUED_PAGE_SIZE)" in route
assert "ISSUED_PAGE_SIZE = 20" in history
assert "include_cancelled_visits=True" in history
assert "_archived_emitted_items(db, desde=_date(1900, 1, 1))" in route
assert "'billing_preferences':" in route
assert "'read_only': True" in route
assert not any(call in route for call in ["db.commit(", "db.delete(", "db.add(", "emit_invoice(", "query_comprobante("])

assert "const issued=estado==='EMITIDA'" in front
assert "url='/api/billing/issued-page'" in front
assert "function issuedBillingToolbar(meta={})" in front
assert "billingIssuedScope='today';billingIssuedPage=1" in front
assert "setBillingIssuedScope" in front and "changeBillingIssuedPage" in front
assert 'if(issued){' in front and "groups.map(billingCardHtml)" in front
assert "const d=await api(url+'?'+params.toString())" in front
assert "issued-billing-toolbar" in (ROOT / "recepcion/app/static/style.css").read_text(encoding="utf-8")
print("RECEPTION_BILLING_ISSUED_PAGING_OK", version)
