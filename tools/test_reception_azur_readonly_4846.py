"""Regression contract for local-only AZUR v2 consultation. No network/DB calls."""
import ast
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "recepcion" / "app"
backend = (root / "reception_azur_readonly.py").read_text(encoding="utf-8")
tree = ast.parse(backend)
functions = {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
for name in ("_remote_get", "azur_read_status", "azur_read_save", "azur_read_test", "azur_read_verify_invoice"):
    assert name in functions, name

remote = ast.get_source_segment(backend, functions["_remote_get"])
assert "method=\"GET\"" in remote
assert '"--request", "GET"' in remote
assert "normalize_base_url(core.AZUR_BASE_URL)" in remote
assert '"--max-redirs", "0"' in remote
assert "build_opener(_NeverRedirect()).open" in remote
assert '"--config", "-"' in remote
assert 'capture_output=True' in remote
assert "subprocess.run" in remote
assert 'core._upsert_local_env({"AZUR_READ_API_KEY": key})' in backend
assert 'AZUR_API_KEY": key' not in backend
assert "return _config()" in backend
assert "core.AzurEmission" in backend
assert 'r.clave_acceso' in backend
assert "remote_key != expected_key" in backend
assert "No se imprimió" not in backend or "impresión" in backend
assert "db.commit(" not in backend and "db.add(" not in backend and "db.delete(" not in backend
assert ".Print(" not in backend and "azur_emit_invoice" not in backend

context={"re":re,"Any":object}
for name in ("_invoice_norm","_remote_rows","_field"):
    module=ast.Module(body=[functions[name]], type_ignores=[])
    exec(compile(module,"<isolated helpers>","exec"), context)
assert context["_invoice_norm"]("001-001-000000123")=="001001000000123"
assert context["_invoice_norm"]("123")=="" 
assert len(context["_remote_rows"]({"facturas":[{"numero":"001-001-000000123"}]}))==1
assert context["_field"]({"numero":"001-001-000000123"},"numero")=="001-001-000000123"

m=json.loads((root/"update_manifest.json").read_text())
v=json.loads((root/"recepcion-version.json").read_text())["version"]
assert m["version"] == m["app_version"] == m["runtime_version"] == v in {"4.8.46","4.8.47","4.8.48","4.8.49","4.8.50","4.8.51","4.8.52","4.8.53","4.8.54"}
for section in ("copy","required_dependencies"):
    assert "reception_azur_readonly.py" in m[section]
    assert "static/azur_readonly_config.js" in m[section]

html=(root/"static/index.html").read_text()
assert 'azur_readonly_config.js?v=4.8.46' in html
assert f'billing_advanced.js?v={v}' in html
assert f'billing_advanced.css?v={v}' in html
app=(root/"app.py").read_text()
assert "import reception_azur_readonly as _azur_readonly" in app
print("AZUR_V2_LOCAL_READONLY_STATIC_SAFE_4846_OK")
