"""Regression 4.8.51: AZUR visual-only RIDE 80 mm.

Checks canonical printer layout, signed XML values, and preview surface.
No AZUR calls, printers, patient data, Neon writes, fiscal operations.
"""
import ast
import json
import re
from pathlib import Path
from decimal import Decimal

base = Path(__file__).resolve().parents[1] / "recepcion" / "app"
src = (base / "reception_azur_pos80.py").read_text(encoding="utf-8")
preview = (base / "static" / "azur_pos80_ui.js").read_text(encoding="utf-8")
css = (base / "static" / "billing_advanced.css").read_text(encoding="utf-8")
html = (base / "static" / "index.html").read_text(encoding="utf-8")
manifest = json.loads((base / "update_manifest.json").read_text(encoding="utf-8"))
version = json.loads((base / "recepcion-version.json").read_text(encoding="utf-8"))["version"]
assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == version in {"4.8.51","4.8.52","4.8.53","4.8.54","4.8.55","4.8.56","4.8.57"}
assert "reception_azur_pos80.py" in manifest["copy"]
assert "static/azur_pos80_ui.js" in manifest["copy"]
assert "static/billing_advanced.css" in manifest["copy"]

module = ast.parse(src)
funcs = {n.name:n for n in module.body if isinstance(n, ast.FunctionDef)}
printer = funcs["_print_ticket_windows"]
code = ast.get_source_segment(src, printer)
assert code
# Keep the existing thermal printer safety envelope intact.
for marker in (
    'PaperSize("Factura RIDE 80 mm", 315, est)',
    "Margins(11, 13, 16, 10)",
    "_pos80_horizontal_origin(bounds_width, width)",
    "_pos80_text_line_box(",
    "_wrap_thermal_text(content, width - 12.0",
    "RectangleF(x, draw_top, width, rect_height)",
    "g.DrawLine(pen, x, y, x + width, y)",
    "if y > float(e.MarginBounds.Height) - 10:",
    "doc.Print()",
):
    assert marker in code, marker

# AZUR style, not another full-border boxed receipt.
for marker in (
    'write_title()',
    'write("RUC: " + ticket["ruc"]',
    'write("No. " + ticket["numero"]',
    'write("Ambiente: PRODUCCION"',
    'write_access_identifier("Autorización", ticket["autorizacion"])',
    '_format_authorization_datetime(ticket["fecha_autorizacion"])',
    'write_access_identifier("Clave de acceso", ticket["clave"])',
    'write("Razón social / nombres: " + ticket["cliente"]',
    'write_detail_row(("Cant", "Descripción", "Subtotal"), True)',
    'write_amount("Total sin impuestos", ticket["subtotal"])',
    'write_amount("Descuento", ticket["total_descuento"])',
    'write_amount("Valor ICE", _money(ice))',
    'write_amount("VALOR TOTAL", ticket["total"], True)',
    '_payment_method_label(pago["tipo"])',
):
    assert marker in code, marker

# Only two horizontal rules remain, both within the printable width.
print_node = next(n for n in ast.walk(printer) if isinstance(n,ast.FunctionDef) and n.name=="print_page")
calls = [n for n in ast.walk(print_node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="line"]
assert len(calls) == 2, len(calls)

# All taxable values originate from verified signed XML; no recomputation of
# actual invoice total from the local order or on-the-fly billing.
xml = ast.get_source_segment(src,funcs["_authorized_xml_to_ticket"])
assert '_text(info, "importeTotal")' in xml
assert '"autorizacion": auth_key' in xml
assert '"clave": expected_key' in xml
assert '"total_descuento":' in xml
assert '"impuestos": taxes' in xml
assert '"servicios": lines' in xml
for prohibited in ("azur_emit_invoice", "db.commit(", "db.delete(", "POST /factura/emision"):
    assert prohibited not in src

# Preview has the same sections, escaping source data and no extra fiscal API.
for marker in ("v4851-azur-head", "v4851-azur-client", "v4851-azur-detail",
               "v4851-azur-totals", "v4851-azur-add", "XML AUTORIZADO",
               "Cerrar sin imprimir", "Imprimir 80 mm"):
    assert marker in preview
assert "/api/azur/readonly/pos80-preview" in preview
assert "/api/azur/readonly/pos80-print" in preview
assert "/api/billing/emit" not in preview
assert "v4851-azur-paper" in css
assert 'azur_pos80_ui.js?v=4.8.57' in html
assert 'billing_advanced.css?v=4.8.57' in html
print("AZUR_RIDE_COMPACT_80MM_XML_AUTHORIZED_FISCAL_UNCHANGED_4851_OK")
