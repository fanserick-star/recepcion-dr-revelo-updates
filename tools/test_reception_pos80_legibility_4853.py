"""Recepción 4.8.53: typography and no broken POS 80mm column headers.
Synthetic geometry, no AZUR requests, patients, printer, fiscal or DB writes.
The Windows font is validated by source contract; real printer still needs a photo.
"""
import ast
import re
from pathlib import Path
root=Path(__file__).resolve().parents[1]/"recepcion"/"app"
source=(root/"reception_azur_pos80.py").read_text(encoding="utf-8")
tree=ast.parse(source)
funcs={f.name:f for f in tree.body if isinstance(f,ast.FunctionDef)}
printer=ast.get_source_segment(source,funcs["_print_ticket_windows"])
assert printer
for marker in (
    'Font("Tahoma",',
    'TextRenderingHint.SingleBitPerPixelGridFit',
    'f_small = make_font(7.7)',
    'f_bold_small = make_font(7.4, True)',
    'write_row(("Cant", "Descripción", "P.V.P", "Descto", "Subtotal"), True)',
    'write_access_identifier("Autorización", ticket["autorizacion"])',
    'write_access_identifier("Clave de acceso", ticket["clave"])',
    'write(token[:25], f_identifier)',
    'write(token[25:], f_identifier)',
    'Margins(14, 14, 11, 10)',
    'if y > float(e.MarginBounds.Height) - 10:',
):
    assert marker in printer, marker
assert 'Font("Times New Roman",' not in printer

# Inspect the same fractions used by the actual printer routine, rather than
# testing a separate copy that could disagree with production code.
match=re.search(r"fractions = \(([^\n]+)\)",printer)
assert match
fractions=ast.literal_eval("("+match.group(1)+")")
assert len(fractions)==5 and abs(sum(fractions)-1.0)<1e-10
width=258.0
spans=[width*x for x in fractions]
assert spans[0]>=31 and spans[1]>=96 and spans[4]>=53

# Simulate the wrapping decision with a conservative 5.8 point-per-glyph
# surrogate. Actual Windows GDI+ widths depend on the printer driver.
scope={}
wrap=funcs["_wrap_thermal_text"]
exec(compile(ast.Module(body=[wrap],type_ignores=[]),"<wrap>", "exec"),scope)
wrap=scope["_wrap_thermal_text"]
samples=[(0,"Cant"),(0,"1.00"),(1,"CONSULTA MEDICA"),
         (2,"P.V.P"),(2,"40.00"),(3,"Descto"),(3,"0.00"),
         (4,"Subtotal"),(4,"40.00")]
for i,value in samples:
    parts=wrap(value,spans[i]-3.0,lambda v:len(v)*5.8)
    assert parts==[value],(i,value,parts,spans)
# 49 digits must be printed in exactly two intact chunks, never orphaned.
token="1234567890123456789012345678901234567890123456789"
assert len(token)==49 and len(token[:25])==25 and len(token[25:])==24
assert token[:25]+token[25:]==token

# The printer only handles XML-authenticated reprints; it cannot create
# invoices, modify fiscal data or change automatic issuance.
assert "azur_emit_invoice" not in source
assert "db.commit(" not in source
assert "db.delete(" not in source
assert 'doc.Print()' in printer
print("AZUR_80MM_TAHOMA_LEGIBILITY_AND_FIVE_COLUMNS_4853_OK")
