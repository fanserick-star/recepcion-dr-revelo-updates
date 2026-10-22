"""Recepción v4.8.55: no cropped header, improved usable width and compact
vertical spacing; static and deterministic tests without SRI or printer calls.
"""
import ast
from pathlib import Path

app=Path(__file__).resolve().parents[1]/"recepcion"/"app"
src=(app/"reception_azur_pos80.py").read_text(encoding="utf-8")
nodes={n.name:n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)}
for helper in ("_pos80_horizontal_origin","_pos80_text_line_box"):
    assert helper in nodes
sandbox={}
for helper in ("_pos80_horizontal_origin","_pos80_text_line_box"):
    exec(compile(ast.Module(body=[nodes[helper]],type_ignores=[]),
                 "<isolated geometry>", "exec"), sandbox)
origin=sandbox["_pos80_horizontal_origin"]
line=sandbox["_pos80_text_line_box"]
printer=ast.get_source_segment(src,nodes["_print_ticket_windows"])
assert printer

# Paper's nominal width is 315 printer points (80mm). Document keeps safe
# margins while moving ink 9.5pt left and making text 21pt wider.
bounds=315.0-11.0-13.0
width=min(279.0,bounds-8.0)
left=11.0+origin(bounds,width)
right=315.0-left-width
assert width==279.0
assert left==11.0 and right==25.0, (left,right,width)
old_left=14.0+origin(315.0-28.0,258.0)
assert left<old_left-8.0

for measured in (12.0,13.5,16.7,22.5):
    top,height,next_y=line(11.0,measured,12.0)
    assert top>=12.5
    assert height>=measured+2.5
    assert next_y>=top+height+0.49
    old_next=11.0+max(12.0,measured+3.0)+5.5
    assert next_y<old_next-3.0, (measured,next_y,old_next)

# The fiscal feed is unchanged; these are printing-only geometry changes.
for fragment in (
    "Margins(11, 13, 16, 10)",
    "width = min(279.0, bounds_width - 8.0)",
    "y = 11.0",
    "y += 13.0",
    "PointF(x + width / 2.0, y)",
    'write_access_identifier("Clave de acceso", ticket["clave"])',
    'write_detail_row(("Cant", "Descripción", "Subtotal"), True)',
    'write_detail_prices(item["unitario"], item["descuento"])',
    'write_amount("VALOR TOTAL", ticket["total"], True)',
    "if y > float(e.MarginBounds.Height) - 10:",
    "doc.Print()",
):
    assert fragment in printer, fragment

for forbidden in ("db.commit(", "db.delete(", "azur_emit_invoice"):
    assert forbidden not in src

print("POS_80MM_LEFT_GUTTER_TOP_MARGIN_AND_COMPACT_SPACING_4855_OK")
