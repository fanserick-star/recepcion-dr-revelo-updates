"""Safe regression for 1.4.43 prescription spacing, signature QR and reports UI.

Uses source checks and geometry only; no clinical files, printer, LAN, or Neon.
"""
from pathlib import Path
import ast
import json

root=Path(__file__).resolve().parents[1]/"historia-clinica/app"
doc=(root/"documentos_clinicos.py").read_text(encoding="utf-8")
sign=(root/"firma_electronica.py").read_text(encoding="utf-8")
reports=(root/"informes_clinicos.py").read_text(encoding="utf-8")
app=(root/"app.py").read_text(encoding="utf-8")
version=json.loads((root/"historia-version.json").read_text(encoding="utf-8"))["version"]
manifest=json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
assert version==manifest["version"]==manifest["app_version"]==manifest["runtime_version"]in {"1.4.43","1.4.44"}
assert manifest["mandatory"] and not manifest["notes"]["database_schema_changes"]
assert not manifest["notes"]["patient_data_destructive_changes"]
for source in (doc,sign,reports,app):
    ast.parse(source)

# V2 recipes only: consistent space between separate medications on both halves.
assert ".rx-copy-v2 .med-item{{margin-bottom:14mm}}" in doc
assert ".rx-copy-v2.rx-med-medium .med-item{{margin-bottom:10mm}}" in doc
assert ".rx-copy-v2.rx-med-many .med-item{{margin-bottom:5mm}}" in doc
assert ".med-line{{margin:.7mm 0 0 2mm;font-size:9.1pt}}" in doc
assert ".med-presentation{{font-weight:900}}" in doc
assert "new_medication_rows(\"left\")" in doc and "new_medication_rows(\"right\")" in doc
assert "if split_prescription:" in doc
assert "left_copy = left_copy.replace(" in doc and "right_copy = right_copy.replace(" in doc
# The previous two-identical-halves historical prescription remains supported.
assert 'split_prescription = any(' in doc

# The *signed* PDF gets its own empty QR/stamp area, ordinary print unchanged.
assert "def prescription_preview(rx_id: str, print_now: int = 0, signature_space: int = 0):" in doc
assert 'sheet_class = "sheet rx-signed-preview" if signature_space else "sheet"' in doc
assert ".rx-signed-preview .rx-copy:first-child .rp{{bottom:59mm}}" in doc
assert "<main class='{sheet_class}'>{left_copy}{right_copy}</main>" in doc
assert 'preview_path = f"/recetas/{quote(doc_id)}/vista?signature_space=1"' in sign

node=next(n for n in ast.parse(sign).body if isinstance(n,ast.FunctionDef) and n.name=="_signature_stamp_box")
ns={}
exec(compile(ast.Module(body=[node],type_ignores=[]),"signature_box","exec"),ns)
box=ns["_signature_stamp_box"]("receta")
assert box==(30,81,273,151)
# 595 pt A4 page; 105mm (~298pt) defines the left-hand copy.
x1,y1,x2,y2=box
assert 22<x1<x2<297 and 70<y1<y2<172
# Preserve the certified PDF and verification QR (no broad database change).
assert 'SigSeedSubFilter.PADES' in sign
assert 'stamp.QRStampStyle(' in sign
assert 'on_page=-1' in sign
assert '"receta": "R"' in sign
assert 'relative_path,pdf_sha256' in sign

# Reports list must use the standalone editor shell, just like a report editor.
assert 'return HTMLResponse(_document_editor_shell(base, "Informes médicos", body, "informes"))' in reports
assert 'return HTMLResponse(base("Informes médicos", body, "informes"))' not in reports
assert 'body.clinical-document-editor > header.topbar,' in doc
assert 'body.clinical-document-editor > footer{display:none!important}' in doc
assert 'body.clinical-document-editor > main{width:100%' in doc
assert "window.open(route+'?'+qs.toString(),'_blank')" in app
print("HISTORIA_1443_RECETAS_AMBAS_COLUMNAS_FIRMA_QR_INFORMES_VENTANA_OK")
