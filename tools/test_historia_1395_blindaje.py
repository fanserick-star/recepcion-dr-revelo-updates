from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _install_fastapi_stubs() -> None:
    fastapi = types.ModuleType("fastapi")

    class DummyFastAPI:
        def __init__(self, *args, **kwargs):
            self.state = types.SimpleNamespace()

        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def middleware(self, *_args, **_kwargs):
            return lambda fn: fn

    class DummyRequest:
        pass

    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = DummyRequest
    sys.modules["fastapi"] = fastapi

    responses = types.ModuleType("fastapi.responses")

    class DummyHTMLResponse:
        def __init__(self, content="", status_code=200, headers=None, **_kwargs):
            self.content = content
            self.status_code = status_code
            self.headers = headers or {}

    responses.HTMLResponse = DummyHTMLResponse
    sys.modules["fastapi.responses"] = responses


def _queue_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE waiting_queue(
              id TEXT PRIMARY KEY,
              status TEXT,
              clinical_patient_id TEXT,
              attention_type TEXT,
              reception_turn INTEGER,
              started_at TEXT,
              updated_at TEXT
            );
            CREATE TABLE audit_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              occurred_at TEXT,
              actor TEXT,
              action TEXT,
              entity_type TEXT,
              entity_id TEXT,
              details_json TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO waiting_queue(id,status,clinical_patient_id,attention_type,reception_turn,started_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            [
                ("q1", "in_consultation", "p1", "CONSULTA", 5, "2026-10-02T10:00:00", "2026-10-02T10:00:00"),
                ("q2", "waiting", "p2", "CONSULTA", 6, None, "2026-10-02T10:01:00"),
                ("q3", "waiting", "p3", "PROCEDIMIENTO", None, None, "2026-10-02T10:02:00"),
                ("q4", "waiting", "", "CONSULTA", 7, None, "2026-10-02T10:03:00"),
            ],
        )
        conn.commit()


def test_parallel_attention_guard() -> None:
    _install_fastapi_stubs()
    queue = _load_module("queue_open_attention_test", APP / "queue_open_attention.py")
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / "historia_clinica.db"
        _queue_db(db)
        queue.DB_PATH = db

        context = queue._confirmation_context("q2", link_selected=False)
        assert context is not None, "Una segunda consulta vinculada debe pedir confirmación"
        assert context["active"]["turn"] == "05"
        assert context["target"]["turn"] == "06"

        assert queue._confirmation_context("q4", link_selected=False) is None, (
            "Una ficha aún no vinculada debe conservar primero el flujo de selección"
        )
        assert queue._confirmation_context("q4", link_selected=True) is not None, (
            "Después de elegir la ficha, una segunda consulta debe pedir confirmación"
        )

        assert queue._start_attention("q2", allow_parallel=False) is False, (
            "No debe iniciar silenciosamente un segundo turno"
        )
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT status FROM waiting_queue WHERE id='q2'").fetchone()[0] == "waiting"

        assert queue._start_attention("q2", allow_parallel=True) is True, (
            "La confirmación explícita debe permitir iniciar el nuevo turno"
        )
        with sqlite3.connect(db) as conn:
            status, started = conn.execute(
                "SELECT status,started_at FROM waiting_queue WHERE id='q2'"
            ).fetchone()
        assert status == "in_consultation"
        assert started

        assert queue._start_attention("q2", allow_parallel=True) is False
        with sqlite3.connect(db) as conn:
            started_again = conn.execute(
                "SELECT started_at FROM waiting_queue WHERE id='q2'"
            ).fetchone()[0]
        assert started_again == started, "Reabrir la ficha no puede cambiar started_at"

        assert queue._start_attention("q3", allow_parallel=False) is True, (
            "Los procedimientos conservan el comportamiento previo y siguen fuera de TV"
        )


def test_sync_status_resilience() -> None:
    cloud = _load_module("cloud_sync", APP / "cloud_sync.py")
    resilience = _load_module("sync_status_resilience_test", APP / "sync_status_resilience.py")
    resilience.cloud_sync = cloud
    resilience.install()

    with tempfile.TemporaryDirectory() as temp:
        data = Path(temp)
        real_replace = os.replace
        attempts = {"count": 0}

        def flaky_replace(source, target):
            attempts["count"] += 1
            if attempts["count"] <= 2:
                raise PermissionError(5, "archivo ocupado temporalmente")
            real_replace(source, target)

        resilience._atomic_replace = flaky_replace
        result = cloud._write_status(data, state="ready", online=True, message="Nube lista")
        assert result["state"] == "ready"
        saved = json.loads((data / "sync_status.json").read_text(encoding="utf-8"))
        assert saved["state"] == "ready" and saved["online"] is True
        assert attempts["count"] >= 3, "Debe reintentar os.replace cuando Windows bloquea el archivo"

        def always_blocked(_source, _target):
            raise PermissionError(5, "bloqueo persistente")

        resilience._atomic_replace = always_blocked
        result = cloud._write_status(data, state="ready", online=False, message="Estado auxiliar")
        assert result["online"] is False
        saved = json.loads((data / "sync_status.json").read_text(encoding="utf-8"))
        assert saved["online"] is False, "El fallback directo debe mantener usable el estado auxiliar"
        assert not (data / "sync_status.tmp").exists(), "No debe reutilizar el antiguo temporal compartido"
        assert not list(data.glob("*.tmp")), "Los temporales únicos deben limpiarse"


def main() -> None:
    test_parallel_attention_guard()
    test_sync_status_resilience()
    print("HISTORIA_1_3_95_BLINDAJE_OK")


if __name__ == "__main__":
    main()
