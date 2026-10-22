"""Regression for actual top-glyph clipping and off-center 80mm paper.

Runs no Windows printer, invoice, AZUR, network, or fiscal mutations.
"""
import ast
from pathlib import Path

root=Path(__file__).resolve().parents[1]/"recepcion"/"app"
source=(root/"reception_azur_pos80.py").read_text(encoding="utf-8")
tree=ast.parse(source)
fns={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
required=("_pos80_horizontal_origin","_pos80_text_line_box","_print_ticket_windows")
assert all(k in fns for k in required), required
helpers={}
for name in required[:2]:
    exec(compile(ast.Module(body=[fns[name]],type_ignores=[]),"<isolated thermal geometry>","exec"),helpers)
origin=helpers["_pos80_horizontal_origin"]
line=helpers["_pos80_text_line_box"]

# Representative 80mm driver: 315pt paper, 14pt margins on either side.
# The old layout was centered by the driver, but visibly right-shifted on paper.
bounds=315.0-14.0-14.0
width=min(258.0,bounds-12.0)
old=(bounds-width)/2.0
x=origin(bounds,width)
assert old - x == 8.0, (old,x)
assert x >= 0.0
assert x+width <= bounds, (x,width,bounds)
assert origin(266,258) == 0.0, "Narrow driver must not print outside left margin"

# Ascenders no longer start at the top edge of their PrintDocument rectangle.
# Consecutive text boxes are disjoint even for long headers or bold totals.
y=7.0
for measured in (13.5,16.7,22.5,11.3,18.0,26.0):
    top,h,next_y=line(y,measured,14)
    assert top >= y+2.0
    assert h >= measured+2.0
    assert next_y >= top+h+0.5
    y=next_y

printer=ast.get_source_segment(source,fns["_print_ticket_windows"])
assert "_pos80_horizontal_origin(bounds_width, width)" in printer
assert "_pos80_text_line_box(" in printer
assert "RectangleF(x, draw_top, width, rect_height)" in printer
assert "y = next_y" in printer
assert "Margins(14, 14, 11, 10)" in printer
assert "_wrap_thermal_text(content, width - 12.0" in printer
assert "g.DrawLine(pen, x, y, x + width, y)" in printer
assert "doc.Print()" in printer

# Deliberately no alteration of authorized SRI fiscal data.
assert "azur_emit_invoice" not in source
assert "db.commit(" not in source
assert "db.delete(" not in source
manifest=__import__("json").loads((root/"update_manifest.json").read_text(encoding="utf-8"))
version=__import__("json").loads((root/"recepcion-version.json").read_text(encoding="utf-8"))["version"]
assert manifest["version"]==version and version in ("4.8.50","4.8.51","4.8.52","4.8.53")
print("RECEPTION_AZUR_POS80_TOP_GLYPHS_AND_LEFT_CALIBRATION_4850_OK")
