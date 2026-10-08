from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RECEPTION = ROOT / "recepcion" / "app"


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def fn_node(contents: str, name: str) -> ast.FunctionDef:
    found = [node for node in ast.parse(contents).body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(found) == 1, name
    return found[0]


class FakeHttpException(Exception):
    def __init__(self, code: int, message: str):
        self.status_code = code
        self.detail = message


def test_safe_auto_creation_returns_status_without_deleting_admin_patient() -> None:
    contents = text("recepcion/app/core_runtime.py")
    fn = fn_node(contents, "_auto_create_clinical_chart_for_new_reception_patient")
    calls = []
    fake_identity = types.ModuleType("reception_history_identity_consolidated")
    class FakeCreateInput:
        def __init__(self, reception_patient_id):
            self.reception_patient_id = reception_patient_id
    fake_identity._HistoryCreateFromReceptionIn = FakeCreateInput
    fake_identity.historia_identity_create_from_reception = lambda data, db, user: (
        calls.append((data.reception_patient_id, db, user)) or
        {"linked": True, "created": True, "clinical_patient": {"id": "clinic-101"}}
    )
    previous = sys.modules.get(fake_identity.__name__)
    sys.modules[fake_identity.__name__] = fake_identity
    try:
        scope = {
            "Session": object, "User": object,
            "HTTPException": FakeHttpException,
            "is_offline_db": lambda db: db.offline,
        }
        body = ast.FunctionDef(
            name=fn.name, args=fn.args, body=fn.body, decorator_list=[],
            returns=fn.returns, type_comment=None
        )
        exec(compile(ast.fix_missing_locations(ast.Module(body=[body], type_ignores=[])),
                     "core_runtime_auto_chart", "exec"), scope)
        run = scope[fn.name]
        online = SimpleNamespace(offline=False)
        admin = SimpleNamespace(username="recepcion")
        ok = run(online, 101, admin)
        assert ok == {
            "status": "linked", "linked": True,
            "created": True, "clinical_patient_id": "clinic-101",
        }
        assert calls == [(101, online, admin)]
        offline = run(SimpleNamespace(offline=True), 29, admin)
        assert offline["status"] == "pending_connection"
        assert not offline["linked"]
        assert len(calls) == 1

        def old_patient(data, db, user):
            raise FakeHttpException(409, "Ya existe una historia clínica")
        fake_identity.historia_identity_create_from_reception = old_patient
        blocked = run(online, 102, admin)
        assert blocked["status"] == "needs_link"
        assert not blocked["linked"]

        def neon_down(data, db, user):
            raise OSError("Neon fuera de servicio")
        fake_identity.historia_identity_create_from_reception = neon_down
        unavailable = run(online, 103, admin)
        assert unavailable["status"] == "pending_connection"
        assert not unavailable["linked"]
    finally:
        if previous is not None:
            sys.modules[fake_identity.__name__] = previous
        else:
            sys.modules.pop(fake_identity.__name__, None)


def test_new_patient_route_autocreates_at_registration() -> None:
    core = text("recepcion/app/core_runtime.py")
    create = core.split('@app.post("/api/patients")', 1)[1].split(
        '@app.put("/api/patients/{pid}")', 1
    )[0]
    assert 'db.commit()' in create
    assert 'mirror_patient_to_local(p)' in create
    assert create.count('_auto_create_clinical_chart_for_new_reception_patient(') == 2
    assert 'result["clinical_chart"] =' in create
    assert 'offline=True' in create
    assert create.index('mirror_patient_to_local(p)') < create.rindex(
        '_auto_create_clinical_chart_for_new_reception_patient('
    )
    sync = core.split("def process_offline_queue(", 1)[1].split(
        "V4425_AUTOBOOK_CSS", 1
    )[0]
    assert 'q.operation == "patient.create"' in sync
    assert 'set_id_map(ldb, "patient"' in sync
    assert 'patient_in_cloud.id' in sync
    assert sync.index('set_id_map(ldb, "patient"') < sync.index(
        '_auto_create_clinical_chart_for_new_reception_patient('
    )
    assert not "clinical_chart" in core.split('def update_patient(', 1)[1].split(
        '@app.post("/api/patients/{source_id}/link/', 1
    )[0]


def test_identity_autocreate_guards_and_idempotency() -> None:
    identity = text("recepcion/app/reception_history_identity_consolidated.py")
    create = identity.split('def historia_identity_create_from_reception(', 1)[1].split(
        '@app.post("/api/historia-identity/link")', 1
    )[0]
    assert 'current = _linked_patient(cur, patient.id)' in create
    assert '"created": False' in create
    assert '"verified"' in create
    assert 'national_id_search=%s AND deleted_at IS NULL' in create
    assert '_search_candidates(cur, demo, name, 20)' in create
    assert '"Hay fichas clínicas parecidas' in create
    assert "ON CONFLICT(reception_patient_id) DO NOTHING" in create
    assert "conn.rollback()" in create
    assert '"reception_created_verified"' in create
    assert 'DELETE FROM' not in create
    assert 'UPDATE public.encounters' not in create

    js = text("recepcion/app/static/app.js")
    registration = js.split('async function saveNewPatient(action=false){', 1)[1].split(
        'async function openHistoricalPatientProfile(', 1
    )[0]
    assert "p?.clinical_chart" in registration
    assert 'clinical.status===\'needs_link\'' in registration
    assert 'clinical.status===\'pending_connection\'' in registration
    assert "api('/api/patients',{method:'POST'" in registration
    assert "create-new" not in registration
    assert "Crear ficha clínica nueva" not in registration

    name_search = text("recepcion/app/reception_history_identity_name_search.py")
    assert "import re" in name_search
    assert "re.fullmatch" in name_search

    lan = text("recepcion/app/historia_lan_transport.py")
    lookup = lan.split("def _cloud_link_id(", 1)[1].split(
        "def _flush_lan_outbox(", 1
    )[0]
    assert 'get_id_map(ldb, "patient", int(reception_patient_id))' in lookup
    assert '(cloud_reception_id,)' in lookup


if __name__ == "__main__":
    test_safe_auto_creation_returns_status_without_deleting_admin_patient()
    test_new_patient_route_autocreates_at_registration()
    test_identity_autocreate_guards_and_idempotency()
    print("RECEPTION_AUTO_CLINICAL_CHART_OK")
