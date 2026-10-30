"""Real V2 prescription preview regression: paired medication rows stay aligned.

The real route is extracted from its AST with fake database data; no printer,
Neon, signatures, or patient database is touched.
"""
from __future__ import annotations

import ast
from datetime import date
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
source = (ROOT / "documentos_clinicos.py").read_text(encoding="utf-8")
tree = ast.parse(source)
node = next(n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "prescription_preview")
node.decorator_list = []
ast.fix_missing_locations(node)

row = {
    "name": "PACIENTE DE PRUEBA",
    "national_id": "0000000000",
    "sex": "F",
    "birth_date": "1980-01-01",
    "diagnosis": "",
    "cie10": "",
    "allergies": "NO",
    "allergies_detail": "",
    "issued_at": "2026-10-30",
    "series_no": "262",
    "instructions": "Tomar agua",
    "items_json": json.dumps([
        {"medication": "PRIMER MEDICAMENTO", "presentation_quantity": "CÁPSULAS #60",
         "indications": "TOMAR 1 CÁPSULA CADA 12 HORAS. " * 3},
        {"medication": "SEGUNDO MEDICAMENTO", "presentation_quantity": "TABLETAS #50",
         "indications": "TOMAR 1 TABLETA CADA 8 HORAS."},
    ], ensure_ascii=False),
}

class FakeDb:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, args):
        assert "FROM prescriptions" in sql
        return self
    def fetchone(self):
        return row

def render(items, signature_space=0):
    row["items_json"] = json.dumps(items, ensure_ascii=False)
    namespace = {
        "_connect": lambda path: FakeDb(),
        "db_path": "unused-test-database",
        "_settings": lambda conn: {"senescyt_registration": ""},
        "_e": lambda v: html.escape(str(v if v is not None else ""), quote=True),
        "_date_short": lambda value: "30/10/2026",
        "_age": lambda value: "46",
        "json": json,
        "date": date,
        "HTMLResponse": lambda value, status_code=200: value,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(ROOT / "documentos_clinicos.py"), "exec"), namespace)
    return namespace["prescription_preview"]("rx-test", signature_space=signature_space)

items = json.loads(row["items_json"])
preview = render(items)
assert "<main class='sheet'>" in preview
assert preview.count("<div class='rx-med-pair'>") == 2, "Una fila compartida por medicina"
pair_area = preview.split("<div class='rx-paired-medications",1)[1].split("</main>",1)[0]
first, second = pair_area.split("<div class='rx-med-pair'>")[1:3]

for content, number, medicine in [
    (first, "1.", "PRIMER MEDICAMENTO"),
    (second, "2.", "SEGUNDO MEDICAMENTO"),
]:
    assert content.count(f"{number} {medicine}") == 2, content
    assert content.index("rx-med-left") < content.index("rx-med-right")
    assert "class='med-name'" in content
assert "CÁPSULAS #60" in first
assert "TABLETAS #50" in second
assert "TOMAR 1 CÁPSULA CADA 12 HORAS" in first
assert "TOMAR 1 TABLETA CADA 8 HORAS" in second
assert preview.count("Tomar agua") == 1, "Indicaciones adicionales nunca duplicadas"
assert "class='rx-paired-extra'" in pair_area
# CSS Grid uses one common row for both halves: wrapping text is shared.
for rule in (
    ".rx-med-pair{",
    "display:grid;grid-template-columns:88mm 90mm;column-gap:9mm;",
    "align-items:start;flex:none;margin-bottom:14mm;",
    ".rx-paired-medications.rx-med-medium .rx-med-pair{margin-bottom:10mm}",
    ".rx-paired-medications.rx-med-many .rx-med-pair{margin-bottom:5mm}",
    ".rx-med-pair .med-item{min-width:0;margin:0}",
    "position:absolute;top:82mm;bottom:32mm;left:12.5mm;right:10.5mm;",
    "position:relative; /* ancla la cuadrícula compartida al A4",
):
    assert rule in preview, rule

signed = render(items, signature_space=1)
assert "<main class='sheet rx-signed-preview'>" in signed
assert ".rx-signed-preview .rx-paired-medications{bottom:64mm}" in signed
assert signed.count("<div class='rx-med-pair'>") == 2

# Historical recipes do not use paired overlays: both A4 copies unchanged.
old_items = [{"medication":"ANTIGUO","dose":"1 TABLETA", "frequency":"CADA 12H"}]
old = render(old_items)
assert "<div class='rx-paired-medications" not in old
assert old.count("1. ANTIGUO") == 2
assert "1 TABLETA CADA 12H" in old
assert "Sin medicamentos registrados." not in old

print("HISTORIA_1465_RECIPE_ROW_ALIGNMENT_SHARED_GRID_OK")
