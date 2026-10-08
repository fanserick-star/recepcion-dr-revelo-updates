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


def test_conservative_name_duplicate_guard() -> None:
    import re
    import unicodedata
    from datetime import date
    def norm(text):
        raw = unicodedata.normalize("NFD", str(text or ""))
        raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", raw).strip().upper().replace("Z", "S")
    def ident(text):
        raw = re.sub(r"[^A-Z0-9]", "", norm(text))
        return raw if len(raw) >= 6 else ""
    def phone(text):
        return re.sub(r"\D", "", str(text or ""))
    def birth(text):
        return str(text or "")[:10]

    src = text("recepcion/app/reception_history_identity_consolidated.py")
    fn = fn_node(src, "_auto_creation_maybe_existing_chart")
    scope = {"_fuzzy_text": norm, "_usable_id": ident,
             "_norm_phone": phone, "_iso_date": birth}
    exec(compile(ast.Module(body=[fn], type_ignores=[]),
                 "reception_identity_duplicate_guard", "exec"), scope)
    might = scope[fn.name]
    demo = {"name": "GARCIA PEREZ ANA MARIA", "national_id": "0911111111",
            "phone": "", "birth_date": ""}
    assert not might(demo, {"name": "GARCIA RUIZ CARLOS MIGUEL",
                            "national_id": "0922222222"})
    assert might(demo, {"name": "PEREZ GARCIA ANA", "national_id": "0922222222"})
    assert might(demo, {"name": "PEREZ GARCIA LUIS", "national_id": "0922222222"})
    assert might(demo, {"name": "OTROS APELLIDOS", "national_id": "0911111111"})
    assert not might(demo, {"name": "PEREZ RUIZ JORGE", "national_id": "0922222222"})
    demo["phone"] = "0987654321"
    assert might(demo, {"name": "PEREZ RUIZ JORGE",
                        "national_id": "", "phone": "0987654321"})


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
    assert '"Hay una ficha clínica con identidad o apellidos coincidentes' in create
    assert '"Encontré una ficha con los dos apellidos del paciente' in create
    assert "_auto_creation_maybe_existing_chart(demo, r)" in create
    assert "LIMIT 1" in create
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


def test_retry_marker_is_durable_idempotent_and_nonblocking() -> None:
    from typing import Optional
    core = text("recepcion/app/core_runtime.py")
    fn = fn_node(core, "_remember_clinical_chart_retry")
    marker_state = {}
    sessions = []

    class FakeMeta:
        def __init__(self, key, value):
            self.key, self.value = key, value

    class FakeLocalSession:
        def __init__(self):
            self.commits = 0
            self.closed = False
            sessions.append(self)
        def get(self, klass, key):
            return marker_state.get(key)
        def add(self, record):
            marker_state[record.key] = record
        def commit(self):
            self.commits += 1
        def close(self):
            self.closed = True

    scope = {
        "Optional": Optional, "Session": object, "CacheMeta": FakeMeta,
        "LocalSessionLocal": FakeLocalSession,
        "CLINICAL_CHART_RETRY_PREFIX": "clinical_chart_retry:",
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])),
                 "clinical_chart_retry_marker", "exec"), scope)
    remember = scope[fn.name]
    remember(901)
    remember(901)
    assert list(marker_state) == ["clinical_chart_retry:901"]
    assert marker_state["clinical_chart_retry:901"].value == "pending"
    assert len(sessions) == 2 and all(x.commits == 1 and x.closed for x in sessions)

    local_db = FakeLocalSession()
    remember(902, local_db)
    assert local_db.commits == 0 and not local_db.closed
    assert marker_state["clinical_chart_retry:902"].value == "pending"

    sync = core.split("def process_offline_queue(", 1)[1].split("V4425_AUTOBOOK_CSS", 1)[0]
    assert 'clinical.get("status") == "pending_connection"' in sync
    assert "_remember_clinical_chart_retry(patient_in_cloud.id, ldb)" in sync
    assert sync.index("_remember_clinical_chart_retry(patient_in_cloud.id, ldb)") < sync.index("ldb.delete(q)")
    assert "_schedule_clinical_chart_retry()" in sync

    create = core.split('@app.post("/api/patients")', 1)[1].split(
        '@app.put("/api/patients/{pid}")', 1
    )[0]
    assert 'result["clinical_chart"].get("status") == "pending_connection"' in create
    assert "_remember_clinical_chart_retry(p.id)" in create

    retry = core.split("def _retry_pending_clinical_charts(", 1)[1].split(
        "def _schedule_clinical_chart_retry(", 1
    )[0]
    assert 'CacheMeta.value == "pending"' in retry
    assert 'status in {"linked", "needs_link", "missing"}' in retry
    assert 'marker.value = "needs_link"' in retry
    assert "ldb.delete(marker)" in retry
    assert "cdb.delete(" not in retry and "UPDATE public." not in retry
    assert "CloudSessionLocal()" in retry
    assert "User(username=\"admin\")" in retry
    assert "_clinical_chart_retry_lock.acquire(blocking=False)" in core
    assert "if online:" in core.split('def leave_power_idle(', 1)[1].split(
        'def ', 1
    )[0]


if __name__ == "__main__":
    test_safe_auto_creation_returns_status_without_deleting_admin_patient()
    test_conservative_name_duplicate_guard()
    test_new_patient_route_autocreates_at_registration()
    test_identity_autocreate_guards_and_idempotency()
    test_retry_marker_is_durable_idempotent_and_nonblocking()
    print("RECEPTION_AUTO_CLINICAL_CHART_OK")
