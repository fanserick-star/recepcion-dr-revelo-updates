"""Measure-width wrapping regression for long AZUR fiscal headers.
No live invoices, printer, network, database or tax writes.
"""
import ast
from pathlib import Path

base=Path(__file__).resolve().parents[1]/"recepcion"/"app"
source=(base/"reception_azur_pos80.py").read_text(encoding="utf-8")
tree=ast.parse(source)
matches=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_wrap_thermal_text"]
assert len(matches)==1
scope={}
exec(compile(ast.Module(body=matches,type_ignores=[]),"<thermal word wrap>","exec"),scope)
wrap=scope["_wrap_thermal_text"]

# All text must be preserved, never ellipsized, and must fit the printer width.
cases=[
    "REVELO CASTILLO ARMANDO ARTURO",
    "CONSULTORIO DE ESPECIALIDADES EN UROLOGIA",
    "ATENCION MEDICA SUBSECUENTE COMPLEJA A DOMICILIO",
    "LARGOTOKENDEIDENTIFICACIONSINSEPARADORES1234567890",
]
width=23.0
measure=lambda v: float(len(v))
for content in cases:
    lines=wrap(content,width,measure)
    assert len(lines)>1,content
    assert all(measure(x)<=width for x in lines),lines
    assert "".join(lines).replace(" ","") == content.replace(" ",""),(content,lines)
assert wrap("TOTAL: $40.00",31,measure)==["TOTAL: $40.00"]
assert wrap("",31,measure)==[]

draw=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_print_ticket_windows"]
assert len(draw)==1
paint=ast.get_source_segment(source,draw[0])
assert "Margins(14, 14, 11, 10)" in paint, "Physical margins must protect paper edges"
assert "min(258.0, bounds_width - 12.0)" in paint, "Use conservative printable-width cap"
assert "_wrap_thermal_text(content, width - 12.0" in paint
assert "RectangleF(x, draw_top, width, rect_height)" in paint
assert "y = next_y" in paint, "Advance one row per wrapped line"
assert "g.DrawLine(pen, x, y, x + width, y)" in paint, "Rules must also respect width"
assert 'doc.Print()' in paint
assert 'azur_emit_invoice' not in source
assert 'db.commit(' not in source
print("AZUR_POS80_HEADER_WRAP_NO_CLIPPING_4848_OK")
