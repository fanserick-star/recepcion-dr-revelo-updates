"""Regressions: local cancel -> Neon, mapped replay, stable exam-review ticket."""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def source(name):
    return (APP / name).read_text(encoding="utf-8-sig")


def executable_function(module, function_name, scope):
    tree = ast.parse(source(module))
    found = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    exec(compile(ast.Module(body=[found], type_ignores=[]), module, "exec"), scope)
    return scope[function_name]


def test_local_cancellation_and_replay():
    cancellation = source("reception_history_cancellation.py")
    core = source("core_runtime.py")
    ui = source("static/app.js")

    cancel_fn = cancellation.split("def _cancel_visit_source_aware(", 1)[1].split(
        '@app.delete("/api/safety/visits/{visit_id}")', 1
    )[0]
    assert 'local_db.info["offline"] = True' in cancel_fn
    assert '"visit.cancel"' in cancel_fn
    assert 'core.get_id_map(local_db, "visit", int(visit_id))' in cancel_fn
    assert 'core.process_offline_queue' in cancel_fn
    assert 'target=core.process_offline_queue' in cancel_fn
    assert 'endpoint(int(visit_id), local_db, user)' in cancel_fn

    replay = core.split('elif q.operation == "visit.create":', 1)[1].split(
        'elif q.operation in {"visit.cancel", "visit.delete"}:', 1
    )[0]
    assert 'get_id_map(ldb, "visit", local_visit_id)' in replay
    assert 'get_visit_any_state(cdb, int(previous_cloud_id))' in replay
    assert '_visit_cloud_matches_local(existing_cloud_visit, payload, cloud_patient_id)' in replay
    assert 'result_id = int(existing_cloud_visit.id)' in replay
    assert 'else:\n            v = Visit(' in replay
    assert 'if not free_review:' in replay
    assert 'BillingRecord(visit_id=v.id, estado="PENDIENTE")' in replay
    assert '"source_row"' in replay
    assert 'v.estado = "CANCELADA"' in core
    assert 'db.delete(v)' not in core.split('@app.delete("/api/visits/{visit_id}")', 1)[1].split(
        '@app.get("/api/dashboard")', 1
    )[0]

    # Papelera is retired from the UI only. Stored backup snapshots and
    # issued invoices remain intact for forensic/fiscal safety.
    assert '<button id="opsTrashTab"' not in core
    assert '<div id="opsTrashPane"' not in core
    assert "showUndoToast(d)" not in core
    assert "BillingRecord" in core
    assert '"fiscal_preserved": True' in core
    assert "loadWeek(" in ui


def test_cloud_replay_matches_exact_local_row():
    match = executable_function(
        "core_runtime.py",
        "_visit_cloud_matches_local",
        {"date": date},
    )
    old = SimpleNamespace(patient_id=429, fecha=date(2026, 10, 8),
                          procedimiento="CISTOSCOPIA", valor=140.0)
    payload = {"fecha": "2026-10-08", "procedimiento": "cistoscopia",
               "valor": 140}
    assert match(old, payload, 429)
    assert not match(old, payload, 430)
    assert not match(old, {**payload, "fecha": "2026-10-07"}, 429)
    assert not match(old, {**payload, "procedimiento": ""}, 429)
    assert not match(old, {**payload, "valor": 40}, 429)
    assert not match(old, {"fecha": "error"}, 429)


def test_exam_review_turn_number_does_not_change_after_refresh():
    class Field:
        def __eq__(self, _value):
            return True

        def asc(self):
            return self

    class Visit:
        fecha = Field()
        id = Field()

        def __init__(self, id, patient_id, source_row=None):
            self.id, self.patient_id = id, patient_id
            self.fecha = date(2026, 10, 8)
            self.procedimiento = None
            self.source_row = source_row
            self.valor = 0

    class Query:
        def where(self, *_):
            return self

        def order_by(self, *_):
            return self

    store = {}
    review = Visit(606, 70, -480210)
    rows = [Visit(598, 431), review]
    class DB:
        def get(self, _model, id):
            return review if id == review.id else None

        def scalars(self, _query):
            return rows

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            pass

    def cache_get(_db, key):
        val = store.get(key)
        return SimpleNamespace(value=val) if val is not None else None

    def cache_set(_db, key, value):
        store[key] = value

    core = SimpleNamespace(
        Visit=Visit,
        CacheMeta=object,
        select=lambda _model: Query(),
        is_exam_review_no_charge=lambda v: v.source_row == -480210,
        LocalSessionLocal=lambda: local,
        cache_meta_set=cache_set,
    )
    local = DB()
    local.get = cache_get
    calculate = executable_function(
        "reception_history_bridge.py",
        "_reception_turn_for_visit",
        {"core": core},
    )
    db = DB()
    initial = calculate(db, 606)
    assert initial == 2
    # An unrelated row reappears between creation and the printer request.
    rows[:] = [Visit(598, 431), Visit(599, 429), review]
    assert calculate(db, 606) == 2
    assert store["exam_review_turn:20261008:70"] == "2"

    source_js = source("static/app.js")
    source_core = source("core_runtime.py")
    assert "examReviewPrintingIds.has(key)" in source_js
    assert "result?.printed||result?.duplicate_suppressed" in source_js
    assert "_EXAM_REVIEW_PRINT_LOCK = threading.Lock()" in source_core
    assert '"duplicate_suppressed": True' in source_core


if __name__ == "__main__":
    test_local_cancellation_and_replay()
    test_cloud_replay_matches_exact_local_row()
    test_exam_review_turn_number_does_not_change_after_refresh()
    print("RECEPTION_CANCEL_SYNC_TICKET_4811_OK")
