"""Real SQLite regression of the issued-invoice read-only endpoint."""
from __future__ import annotations

import ast
from datetime import date, timedelta, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import (
    Column, Integer, Date, DateTime, ForeignKey, String, create_engine,
    select, func, or_,
)
from sqlalchemy.orm import declarative_base, Session

APP = Path(__file__).resolve().parents[1] / "recepcion/app"
Base = declarative_base()


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    nombre = Column(String)


class Visit(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer)
    fecha = Column(Date)
    estado = Column(String)


class BillingRecord(Base):
    __tablename__ = "billing_records"
    id = Column(Integer, primary_key=True)
    visit_id = Column(Integer)
    estado = Column(String)
    numero_factura = Column(String)


class AzurEmission(Base):
    __tablename__ = "azur_emissions"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer)
    fecha = Column(Date)
    estado = Column(String)
    numero_factura = Column(String)
    updated_at = Column(DateTime)


class BillingPreference(Base):
    __tablename__ = "billing_preferences"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer)
    enabled = Column(Integer)


class BadQuery(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


class FakeApp:
    def get(self, _path):
        return lambda function: function


def install_functions(archived):
    source = (APP / "reception_billing_history.py").read_text(encoding="utf-8")
    names = {
        "_issued_group_query", "_issued_count_groups", "_issued_archive_key",
        "_issued_page_keys", "billing_issued_page",
    }
    tree = ast.parse(source)
    definitions = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert len(definitions) == len(names), names
    core = SimpleNamespace(
        Patient=Patient, Visit=Visit, BillingRecord=BillingRecord,
        AzurEmission=AzurEmission, BillingPreference=BillingPreference,
        BILLING_QUEUE_START_DATE=date(2026, 8, 24),
        select=select, func=func, or_=or_,
        Depends=lambda value: None, get_db=None, current_user=None,
        HTTPException=BadQuery,
        billing_dict=lambda b: {"id": b.id, "estado": b.estado,
                                "numero_factura": b.numero_factura},
        v_dict=lambda v: {"id": v.id, "patient_id": v.patient_id,
                          "fecha": v.fecha.isoformat(), "estado": v.estado},
        p_dict=lambda p: {"id": p.id, "nombre": p.nombre},
        azur_emission_dict=lambda e: {"estado": e.estado,
                                      "numero_factura": e.numero_factura},
        billing_preference_dict=lambda p: {"patient_id": p.patient_id},
    )
    ns = dict(
        core=core, app=FakeApp(), _date=date, ISSUED_PAGE_SIZE=20,
        _active_trashed_patient_ids=lambda: {999},
        _archived_emitted_items=lambda db, desde=None: archived,
    )
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(APP), "exec"), ns)
    return ns["billing_issued_page"]


def main():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    today = date.today()
    yesterday = today - timedelta(days=1)
    archived = [
        {"patient": {"id": 999, "nombre": "PACIENTE ARCHIVADO"},
         "visit": {"id": 9001, "patient_id": 999, "fecha": today.isoformat()},
         "billing": {"id": 9001, "estado": "EMITIDA", "numero_factura": "F-ARCH-HOY"},
         "azur": {"estado": "AUTORIZADA"}, "archived_deleted_patient": True},
        {"patient": {"id": 999, "nombre": "PACIENTE ARCHIVADO"},
         "visit": {"id": 9002, "patient_id": 999, "fecha": yesterday.isoformat()},
         "billing": {"id": 9002, "estado": "EMITIDA", "numero_factura": "F-ARCH-AYER"},
         "azur": {"estado": "AUTORIZADA"}, "archived_deleted_patient": True},
    ]
    with Session(engine) as db:
        def add_invoice(pid, day, visit_id, *, estado="ACTIVA", bill="EMITIDA"):
            if db.get(Patient, pid) is None:
                db.add(Patient(id=pid, nombre="PACIENTE %s" % pid))
                db.flush()
            db.add(Visit(id=visit_id, patient_id=pid, fecha=day, estado=estado))
            db.add(BillingRecord(id=visit_id, visit_id=visit_id, estado=bill,
                                 numero_factura="F-%s" % visit_id if bill == "EMITIDA" else None))

        for i in range(1, 26):
            add_invoice(i, today, 100 + i, estado="CANCELADA" if i == 2 else "ACTIVA")
        add_invoice(1, today, 400)  # Multiple services, same fiscal group.
        for i in range(101, 136):
            add_invoice(i, yesterday, i + 400)
        add_invoice(999, yesterday, 700)  # Hidden, supplied only by archive.
        add_invoice(777, yesterday, 701, bill="PENDIENTE")
        add_invoice(778, today + timedelta(days=1), 702, bill="PENDIENTE")
        db.add(Visit(id=800, patient_id=8888, fecha=today, estado="ACTIVA"))
        db.add(BillingRecord(id=800, visit_id=800, estado="EMITIDA",
                             numero_factura="ORPHAN-EXCLUDED"))
        db.add(AzurEmission(
            id=1, patient_id=1, fecha=today, estado="AUTORIZADA",
            numero_factura="F-101", updated_at=datetime.now(),
        ))
        db.add(AzurEmission(
            id=2, patient_id=1, fecha=today, estado="RECHAZADA",
            numero_factura="DUPLICATE-ATTEMPT", updated_at=datetime.now(),
        ))
        db.commit()

        route = install_functions(archived)
        first = route(scope="today", page=1, db=db)
        second = route(scope="today", page=2, db=db)
        keys = lambda result: {(x["patient"]["id"], x["visit"]["fecha"]) for x in result["items"]}
        assert first["pagination"]["total"] == 26, first["pagination"]
        assert first["pagination"]["pages"] == 2
        assert len(keys(first)) == 20, keys(first)
        assert len(keys(second)) == 6, keys(second)
        assert keys(first).isdisjoint(keys(second))
        assert (999, today.isoformat()) in keys(first) | keys(second)
        assert (8888, today.isoformat()) not in keys(first) | keys(second)
        assert any(x["visit"]["estado"] == "CANCELADA" for x in first["items"] + second["items"])
        group1 = [x for x in first["items"] + second["items"] if x["patient"]["id"] == 1]
        assert len(group1) == 2, group1
        assert any(x.get("azur", {}).get("estado") == "AUTORIZADA"
                   for x in group1 if x.get("azur"))
        assert first["counts"]["EMITIDA"] == 62, first["counts"]
        assert first["counts"]["PENDIENTE"] == 2, first["counts"]
        assert first["counts"]["RECHAZADA"] == 1

        older1 = route(scope="previous", page=1, db=db)
        older2 = route(scope="previous", page=2, db=db)
        assert older1["pagination"]["total"] == 36
        assert len(keys(older1)) == 20 and len(keys(older2)) == 16
        assert keys(older1).isdisjoint(keys(older2))
        assert (999, yesterday.isoformat()) in keys(older1) | keys(older2)
        assert all(x["visit"]["fecha"] < today.isoformat()
                   for x in older1["items"] + older2["items"])
        assert route(scope="previous", page=3, db=db)["items"] == []

        assert db.get(BillingRecord, 101).numero_factura == "F-101"
        assert db.get(Visit, 102).estado == "CANCELADA"
        try:
            route(scope="invalid", page=1, db=db)
            raise AssertionError("Bad period accepted")
        except BadQuery as exc:
            assert exc.status_code == 400
    print("RECEPTION_BILLING_ISSUED_SQLITE_OK")


if __name__ == "__main__":
    main()
