from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_marker_and_no_billing() -> None:
    source = text("recepcion/app/core_runtime.py")
    tree = ast.parse(source)
    functions = {
        node.name: node for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "is_exam_review_no_charge" in functions
    fn = functions["is_exam_review_no_charge"]
    scope = {"EXAM_REVIEW_NO_CHARGE_SOURCE_ROW": -480210}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "core_runtime.py", "exec"), scope)
    is_free = scope["is_exam_review_no_charge"]
    assert is_free(SimpleNamespace(source_row=-480210, procedimiento=None, valor=0))
    assert not is_free(SimpleNamespace(source_row=-480210, procedimiento="ECOGRAFIA", valor=0))
    assert not is_free(SimpleNamespace(source_row=-480210, procedimiento=None, valor=40))
    assert not is_free(SimpleNamespace(source_row=-442901, procedimiento=None, valor=0))
    assert not is_free(SimpleNamespace(source_row=None, procedimiento=None, valor=0))

    free_route = source.split('@app.post("/api/visits/exam-review")', 1)[1].split(
        '@app.delete("/api/visits/{visit_id}")', 1
    )[0]
    assert "data.fecha != date.today()" in free_route
    assert 'Visit.source_row == EXAM_REVIEW_NO_CHARGE_SOURCE_ROW' in free_route
    assert 'Visit.procedimiento.is_(None)' in free_route
    assert '"Este paciente ya tiene una consulta o turno activo hoy.' in free_route
    assert 'valor=0.0' in free_route
    assert 'source_row=EXAM_REVIEW_NO_CHARGE_SOURCE_ROW' in free_route
    assert '"exam_review_no_charge": True' in free_route
    assert '"visit.create"' in free_route
    assert "BillingRecord(" not in free_route
    assert 'attention_type="Consulta"' in free_route
    assert 'historia_bridge.queue_attention(' in free_route
    assert '"billing_created": False' in free_route
    assert '"handoff_queued": not bool(handoff_error)' in free_route

    sync = source.split('elif q.operation == "visit.create":', 1)[1].split(
        'elif q.operation in {"visit.cancel", "visit.delete"}:', 1
    )[0]
    assert 'free_review = payload.get("exam_review_no_charge") is True' in sync
    assert 'if not free_review:' in sync
    assert 'cdb.add(BillingRecord(visit_id=v.id, estado="PENDIENTE"))' in sync
    assert 'source_row=EXAM_REVIEW_NO_CHARGE_SOURCE_ROW if free_review else None' in sync
    assert '"/api/visits/exam-review"' in source
    assert '"exam_review_no_charge": is_exam_review_no_charge(v)' in source


def test_separate_free_button_and_no_receipt() -> None:
    js = text("recepcion/app/static/app.js")
    assert 'onclick="saveExamReviewTurn(' in js
    assert "async function saveExamReviewTurn(id)" in js
    free_handler = js.split("async function saveExamReviewTurn(id){", 1)[1].split(
        "async function saveAttention(id){", 1
    )[0]
    assert "api('/api/visits/exam-review'" in free_handler
    assert "api('/api/visits/batch-payment'" not in free_handler
    assert "saveAttention(" not in free_handler
    assert "const fecha=" in free_handler
    assert "sin cobro ni factura" in free_handler.lower() or "no se cobrará ni se creará factura" in free_handler.lower()
    assert 'if(r?.exam_review_no_charge)' in js
    assert "&&!v.exam_review_no_charge" in js
    assert "&&!r?.exam_review_no_charge" in js
    assert "receiptDataFromHome" in js
    assert '.filter(v=>!String(v.procedimiento||\'\').trim()&&!v.exam_review_no_charge)' in js
    css = text("recepcion/app/static/style.css")
    assert ".exam-review-turn-btn" in css


def test_cross_system_and_fiscal_safety() -> None:
    app = text("recepcion/app/app.py")
    printer = app.split("def v466_print_visit_local_first(", 1)[1].split(
        "_V466_OLD_BUSY =", 1
    )[0]
    assert "core.is_exam_review_no_charge(visit)" in printer
    assert "raise core.HTTPException" in printer

    tv = text("historia-clinica/app/tv_turn_bridge.py")
    assert 'raw in {"P", "X", "PROCEDIMIENTO"}' in tv
    assert "raw.startswith(\"PROCEDIMIENTO \")" in tv
    assert "review" not in text("recepcion/app/reception_payment_terminal.py").split(
        "PAYMENT_SENTINELS =", 1
    )[1].split("\n", 1)[0].lower()


if __name__ == "__main__":
    test_marker_and_no_billing()
    test_separate_free_button_and_no_receipt()
    test_cross_system_and_fiscal_safety()
    print("RECEPTION_EXAM_REVIEW_TURN_OK")
