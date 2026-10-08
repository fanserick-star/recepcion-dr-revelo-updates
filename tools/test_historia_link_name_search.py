from __future__ import annotations

import ast
import importlib
import re
import sqlite3
import sys
import tempfile
import types
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app"


def install_fastapi_stubs():
    fastapi = types.ModuleType("fastapi")
    class FastAPI:
        pass
    class Request:
        pass
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    fastapi.Query = lambda default=None, **kwargs: default
    responses = types.ModuleType("fastapi.responses")
    class Response:
        def __init__(self, content=None, status_code=200, headers=None):
            self.content, self.status_code, self.headers = content, status_code, headers
    responses.HTMLResponse = Response
    responses.JSONResponse = Response
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses


def fixture(path: Path):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE patients(
          id TEXT PRIMARY KEY, name TEXT, name_search TEXT, national_id TEXT,
          national_id_search TEXT, birth_date TEXT, sex TEXT,
          merged_into_patient_id TEXT, updated_at TEXT, created_at TEXT,
          phone TEXT
        );
        CREATE TABLE waiting_queue(
          id TEXT PRIMARY KEY, display_name TEXT, identification TEXT,
          clinical_patient_id TEXT, status TEXT
        );
        CREATE TABLE encounters(
          id TEXT PRIMARY KEY, patient_id TEXT, note_status TEXT,
          deleted_at TEXT, encounter_date TEXT
        );
        """)
        distractors = [
            (str(i), f"PICO PERSONA DIFERENTE {i}", f"PICO PERSONA DIFERENTE {i}",
             "", "", "", "", "", "2026-10-07", "2026-10-07", "")
            for i in range(1, 370)
        ]
        db.executemany(
            "INSERT INTO patients VALUES(?,?,?,?,?,?,?,?,?,?,?)", distractors
        )
        real = [
            ("target", "VELIZ PICO SAUL AARON", "", "0912345678", "0912345678",
             "", "M", "", "2022-02-01", "2022-02-01", ""),
            ("other", "VELIZ PICO MARIA ANA", "VELIZ PICO MARIA ANA", "",
             "", "", "F", "", "2022-02-02", "2022-02-02", ""),
            ("near", "VELIZ RIVERA SAUL AARON", "VELIZ RIVERA SAUL AARON",
             "", "", "", "M", "", "2022-02-03", "2022-02-03", ""),
            ("merge", "VELIZ PICO PACIENTE FUSIONADO", "VELIZ PICO PACIENTE FUSIONADO",
             "", "", "", "M", "target", "2022-02-04", "2022-02-04", ""),
            ("badname", "0912345678", "0912345678", "", "", "", "M", "",
             "2022-02-05", "2022-02-05", ""),
        ]
        db.executemany("INSERT INTO patients VALUES(?,?,?,?,?,?,?,?,?,?,?)", real)
        db.executemany(
            "INSERT INTO waiting_queue VALUES(?,?,?,?,?)",
            [
                ("q1", "0912345678", "0912345678", "target", "waiting"),
                ("q2", "0912345678", "0912345678", "", "waiting"),
                ("q3", "0977777777", "0977777777", "", "waiting"),
                ("q4", "VELIZ PICO SAUL AARON", "", "", "waiting"),
            ],
        )
        db.execute(
            "INSERT INTO encounters VALUES(?,?,?,?,?)",
            ("enc1", "target", "signed", None, "2025-03-04"),
        )
        db.commit()


def isolated_search_functions():
    """Exercise the *actual* Inicio functions without starting Historia or Neon."""
    src = (APP / "app.py").read_text(encoding="utf-8-sig")
    names = {"normalize_search", "_birth_from_query", "_name_rank", "search_patients"}
    parsed = ast.parse(src)
    nodes = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    namespace = {"re": re, "unicodedata": unicodedata, "datetime": datetime}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP / "app.py"), "exec"), namespace)
    return namespace["search_patients"]


def main() -> None:
    install_fastapi_stubs()
    sys.path.insert(0, str(APP))
    import historia_link_helper as helper
    import historia_link_name_search as search

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "historia.db"
        fixture(db_path)
        helper.DB_PATH = db_path
        # This must never be used as text in the visible link-search field.
        assert search._queue_initial_name_first("q1") == "VELIZ PICO SAUL AARON"
        assert search._queue_initial_name_first("q2") == "VELIZ PICO SAUL AARON"
        assert search._queue_initial_name_first("q3") == ""
        assert search._queue_initial_name_first("q4") == "VELIZ PICO SAUL AARON"

        first = search._candidate_rows_name_first("q1", "PICO VELIZ")
        names = [row["name"] for row in first["results"]]
        assert names[:2] == ["VELIZ PICO SAUL AARON", "VELIZ PICO MARIA ANA"], names
        assert all("VELIZ" in n and "PICO" in n for n in names), names
        assert first["initial_query"] == "VELIZ PICO SAUL AARON"
        assert first["results"][0]["history_count"] == 1
        assert first["results"][0]["id_conflict"] is False
        assert "VELIZ PICO PACIENTE FUSIONADO" not in names

        reversed_query = search._candidate_rows_name_first("q4", "VELIZ PICO")
        reversed_names = [r["name"] for r in reversed_query["results"]]
        assert reversed_names == ["VELIZ PICO SAUL AARON", "VELIZ PICO MARIA ANA"], reversed_names

        id_results = search._candidate_rows_name_first("q3", "0912345678")
        assert id_results["results"] and id_results["results"][0]["name"] == "VELIZ PICO SAUL AARON"

        html = search._inject_link_name(
            "<section class='page-head'><h1>0912345678</h1></section><p>Vincular ficha</p></body>",
            "q1", search._queue_initial_name_first("q1"),
        )
        assert "<h1>VELIZ PICO SAUL AARON</h1>" in html
        assert '<h1>0912345678</h1>' not in html
        assert "Vincular esta ficha" in search._helper_markup_name_first("q1", "VELIZ PICO SAUL AARON")

        general = isolated_search_functions()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            found = general(conn, "PICO VELIZ", limit=20)
            assert [r["id"] for r in found][:2] == ["target", "other"], [r["name"] for r in found]
            assert all("VELIZ" in r["name"] and "PICO" in r["name"] for r in found)
            # A missing name_search must not hide real legacy patient names.
            assert any(r["id"] == "target" for r in found)
    print("HISTORIA_LINK_NAME_SEARCH_REGRESSION_OK")


if __name__ == "__main__":
    main()
