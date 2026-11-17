"""Regression: new Reception charts must never block Historia's SQLite pull.

No clinical data, external services or live databases are used.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEPTION = ROOT / "recepcion/app/reception_history_identity_consolidated.py"
HISTORY = ROOT / "historia-clinica/app/cloud_sync.py"


def check_reception_insert() -> None:
    tree = ast.parse(RECEPTION.read_text(encoding="utf-8"), filename=str(RECEPTION))
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) != 2:
            continue
        sql_node, params_node = node.args
        if not isinstance(sql_node, ast.Constant) or not isinstance(sql_node.value, str):
            continue
        if "INSERT INTO public.patients(" not in sql_node.value:
            continue
        candidates.append((sql_node.value, params_node))

    assert len(candidates) == 1, "Expected one canonical patient INSERT"
    sql, params = candidates[0]
    match = re.search(r"INSERT INTO public\.patients\s*\((.*?)\)\s*VALUES\s*\((.*)\)\s*$", sql, re.S)
    assert match, "Cannot inspect clinical patient INSERT"
    cols = [c.strip() for c in match.group(1).split(",")]
    exprs = [v.strip() for v in match.group(2).split(",")]
    assert len(cols) == len(exprs), "SQL column/value mismatch"
    assert isinstance(params, ast.Tuple), "Clinical INSERT must bind a tuple"
    assert len(params.elts) == exprs.count("%s"), "Incorrect bind argument count"
    index = cols.index("legacy_no_depurable")
    assert exprs[index] == "%s", "Legacy flag must be explicitly bound"
    placeholder_index = exprs[:index + 1].count("%s") - 1
    assert isinstance(params.elts[placeholder_index], ast.Constant)
    assert params.elts[placeholder_index].value == 0, "Reception-created charts need flag 0"


def check_historia_import() -> None:
    spec = importlib.util.spec_from_file_location("clinical_cloud_sync_regression", HISTORY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    mapper = module._map_remote_row_to_local
    cols = {"id", "source", "legacy_no_depurable"}
    original = {"id": "new", "source": "reception_new", "legacy_no_depurable": None}
    mapped = mapper("patients", original, cols)
    assert mapped["legacy_no_depurable"] == 0
    assert original["legacy_no_depurable"] is None, "Must not modify remote input"

    missing = mapper("patients", {"id": "new2", "source": "reception_new"}, cols)
    assert missing["legacy_no_depurable"] == 0
    protected = mapper("patients", {"id": "legacy", "source": "legacy_consulta_practica", "legacy_no_depurable": 1}, cols)
    assert protected["legacy_no_depurable"] == 1, "Never weaken protected legacy charts"
    unclassified = mapper("patients", {"id": "unknown", "source": "legacy_consulta_practica", "legacy_no_depurable": None}, cols)
    assert unclassified["legacy_no_depurable"] is None, "Do not guess legacy flags"
    other = mapper("encounters", original, cols)
    assert other["legacy_no_depurable"] is None

    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE patients(id TEXT PRIMARY KEY, legacy_no_depurable INTEGER NOT NULL DEFAULT 0)")
        conn.execute("INSERT INTO patients(id, legacy_no_depurable) VALUES (?,?)", (mapped["id"], mapped["legacy_no_depurable"]))
        assert conn.execute("SELECT legacy_no_depurable FROM patients WHERE id='new'").fetchone()[0] == 0

    source = HISTORY.read_text(encoding="utf-8")
    assert "data = _map_remote_row_to_local(table, remote, local_cols)" in source


if __name__ == "__main__":
    check_reception_insert()
    check_historia_import()
    print("OK new Reception patient legacy flag, safe Historia SQLite pull")
