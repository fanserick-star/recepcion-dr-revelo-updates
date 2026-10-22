"""POS-80C multi-format thermal geometry and safety regression.
No real printer, database, patient data, AZUR, or Neon is accessed.
"""
import ast
from pathlib import Path

root=Path(__file__).resolve().parents[1]/"recepcion"/"app"
def source(name):
    return (root/name).read_text(encoding="utf-8")

core=source("core_runtime.py")
receipt=source("reception_receipt_width.py")
proof=source("reception_payment_proof_layout.py")
queue=source("reception_printing_queue.py")
ast.parse(core)
ast.parse(receipt)
ast.parse(proof)
ast.parse(queue)

functions={fn.name:fn for fn in ast.parse(core).body if isinstance(fn,ast.FunctionDef)}
safe=functions["_safe_pos80_print_width"]
context={}
exec(compile(ast.Module(body=[safe],type_ignores=[]),"<safe width>","exec"),context)
width_for=context["_safe_pos80_print_width"]
for page_width,left,right,printable_right in [
    (315,11,13,284), (315,11,13,300), (315,11,13,265)]:
    w=width_for(page_width-left-right,printable_right,left)
    assert 145 <= w <= 255, (w,printable_right)
    assert left+w<=printable_right-16, (w,printable_right)
    assert w<=page_width-left-right-20

assert "doc.OriginAtMargins = True" in receipt
assert "Margins(11, 13, 8, 10)" in receipt
assert "target_w = core._safe_pos80_print_width(" in receipt
assert "e.PageSettings.PrintableArea.Right" in receipt
assert "RectangleF(0.0, 8.0, target_w, target_h)" in receipt
assert "target_h > float(e.MarginBounds.Height) - 16.0" in receipt
assert "target_w = 283.5" not in receipt

assert "Margins(11, 13, 8, 10)" in proof
assert "width = core._safe_pos80_print_width(" in proof
assert "safe_right = width" in proof
assert "name_h = max(24.0, float(measured.Height) + 6.0)" in proof
assert "item_h = max(18.0, float(size.Height) + 4.0)" in proof
assert "method_height = max(18.0," in proof
assert "y + 40.0 > float(e.MarginBounds.Height) - 10.0" in proof
assert "PaperSize('Comprobante 80 mm', 315, max(900, min(3200, int(estimated_h))))" in proof
assert "safe_right = max(210.0, width - 22.0)" not in proof

review=ast.get_source_segment(core,functions["_print_exam_review_ticket_windows"])
assert "w = _safe_pos80_print_width(" in review
assert "float(e.PageSettings.PrintableArea.Right)" in review
assert "RectangleF(0.0, float(y) + 3.0, w, float(height) + 5.0)" in review
assert 'g.MeasureString(turn_text, font_turn)' in review
assert "paper_center - w / 2.0 - 7.0" not in review
assert "is_exam_review_no_charge" not in review  # Ticket printer never alters patient or fiscal flow.
assert "db.commit(" not in review

assert "'delivery_stage': 'queued'" in queue
assert "'delivery_stage'] = 'submitted_to_windows'" in queue
assert "'physical_completion_verified': False" in queue
assert "core._print_receipt_windows = _print_receipt_windows_v4474" in queue
print("RECEPTION_POS80_RECEIPT_PAYMENT_PROOF_REVIEW_AND_SPOOLER_4857_OK")
