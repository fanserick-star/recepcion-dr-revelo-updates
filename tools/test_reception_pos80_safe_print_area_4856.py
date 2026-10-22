"""POS-80C thermal regression: physical 72.1mm printable width and full FACTURA.
Pure synthetic geometry: no printer, patients, AZUR, Neon or fiscal writes.
"""
import ast
from pathlib import Path

src=(Path(__file__).resolve().parents[1]/"recepcion"/"app"/"reception_azur_pos80.py").read_text(encoding="utf-8")
fns={f.name:f for f in ast.parse(src).body if isinstance(f, ast.FunctionDef)}
assert {"_pos80_safe_content_width","_pos80_horizontal_origin","_print_ticket_windows"} <= fns.keys()
scope={}
for name in ("_pos80_safe_content_width","_pos80_horizontal_origin"):
    exec(compile(ast.Module(body=[fns[name]],type_ignores=[]),"<safe POS80 geometry>","exec"),scope)

safe=scope["_pos80_safe_content_width"]
origin=scope["_pos80_horizontal_origin"]
for paper_width,margin_left,margin_right,printable_right in (
    (315.0,11.0,13.0,284.0), # POS-80C 80(72.1)
    (315.0,11.0,13.0,300.0), # wider driver
    (315.0,11.0,13.0,265.0), # narrow driver: adapt
):
    bounds=paper_width-margin_left-margin_right
    width=safe(bounds,printable_right,margin_left)
    x=origin(bounds,width)
    assert 145.0 <= width <= 255.0
    assert x>=0.0
    assert x+width<=bounds-20.0
    assert margin_left+x+width<=printable_right-16.0

printer=ast.get_source_segment(src,fns["_print_ticket_windows"])
for marker in (
    "e.PageSettings.PrintableArea",
    "float(printable.Right)",
    "float(e.MarginBounds.Left)",
    "width = _pos80_safe_content_width(",
    "StringFormatFlags.NoClip",
    "RectangleF(x, top, width, box_height + 10.0)",
    "title_format.Dispose()",
    'write_detail_row(("Cant", "Descripción", "Subtotal"), True)',
    'write_amount("VALOR TOTAL", ticket["total"], True)',
):
    assert marker in printer,marker
assert "PointF(x + width / 2.0, y)" not in printer
for forbidden in ("db.commit(", "db.delete(", "azur_emit_invoice"):
    assert forbidden not in src
print("POS80_RIGHT_EDGE_AND_FACTURA_TOP_GLYPH_4856_OK")
