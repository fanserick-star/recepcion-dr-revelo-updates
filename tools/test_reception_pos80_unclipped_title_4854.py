"""Regresión AZUR RIDE 80 mm 4.8.54: evita recorte de título y precios partidos.
Sin realizar impresión, cambios fiscales, conexión al SRI ni escribir pacientes.
"""
import ast
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/"recepcion"/"app"
src=(root/"reception_azur_pos80.py").read_text(encoding="utf-8")
preview=(root/"static"/"azur_pos80_ui.js").read_text(encoding="utf-8")
css=(root/"static"/"billing_advanced.css").read_text(encoding="utf-8")
html=(root/"static"/"index.html").read_text(encoding="utf-8")
manifest=json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
version=json.loads((root/"recepcion-version.json").read_text(encoding="utf-8"))["version"]
assert manifest["version"]==manifest["app_version"]==manifest["runtime_version"]==version in {"4.8.54","4.8.55","4.8.56","4.8.57","4.8.58"}

nodes={n.name:n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)}
body=ast.get_source_segment(src,nodes["_print_ticket_windows"])
assert body
for marker in (
 'StringFormatFlags.NoClip', # prevent clipping upper glyph strokes
 'g.DrawString(text, f_title, Brushes.Black,',
 'RectangleF(x, top, width, box_height + 10.0)',
 'write_title()',
 'write_detail_row(("Cant", "Descripción", "Subtotal"), True)',
 'write_detail_row((item["cantidad"], item["descripcion"], item["total"]))',
 'write_detail_prices(item["unitario"], item["descuento"])',
 'fractions = (0.15, 0.58, 0.27)',
 '"P.V.P: " + str(unit_price)',
 '"    Descto: "',
 'if y > float(e.MarginBounds.Height) - 10:',
 'doc.Print()',
):
 assert marker in body,marker
assert 'write_row((' not in body
assert 'from System.Drawing import Font, FontStyle, Brushes, RectangleF,' in body
assert body.count('        line()')==2
# Fiscal content is emitted from SRI signed XML; we did not introduce writes.
assert "azur_emit_invoice" not in src
assert "db.commit(" not in src
assert "db.delete(" not in src
# Preview must show the same layout as paper; all values remain present.
for needle in ('class="v4854-azur-prices"', 'colspan="2"', 'v4854-azur-detail',
               "esc(x.cantidad)","esc(x.descripcion)","esc(x.total)",
               "esc(x.unitario)","esc(x.descuento||'0.00')"):
 assert needle in preview,needle
assert ".v4854-azur-detail" in css
for token in ('azur_pos80_ui.js?v=4.8.58',
              'billing_advanced.css?v=4.8.58',
              'billing_advanced.js?v=4.8.58'):
 assert token in html,token
print("AZUR_80MM_UNCLIPPED_TITLE_LEGIBLE_THREE_COLUMNS_AND_FULL_XML_4854_OK")
