from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path


def find_route(app_module, path: str, method: str):
    method = method.upper()
    matches = [
        r for r in app_module.app.router.routes
        if getattr(r, "path", None) == path
        and method in set(getattr(r, "methods", set()) or set())
    ]
    assert len(matches) == 1, (path, method, [getattr(x, "name", "") for x in matches])
    return matches[0].endpoint


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    candidate = root / "updates" / "v4_6_0_stabilization"
    data_dir = Path(tempfile.mkdtemp(prefix="recepcion_v460_smoke_"))

    os.environ["RP_DATA_DIR"] = str(data_dir)
    os.environ["RP_FORCE_OFFLINE"] = "1"
    os.environ["RP_DESKTOP_LAUNCH"] = "1"
    os.environ["WHATSAPP_ENABLED"] = "0"
    os.environ["WHATSAPP_CLOUD_MODE"] = "1"
    os.environ["DATABASE_URL"] = ""
    os.environ["NEON_DATABASE_URL"] = ""
    os.environ["HISTORIA_DATABASE_URL"] = ""
    os.environ["RP_DATAPHONE_API_ENABLED"] = "0"

    sys.path.insert(0, str(candidate))
    os.chdir(candidate)

    import app

    core = app.core
    user = core.User(
        id=999999,
        username="AUDITORIA_V460",
        password_hash="",
        role="admin",
    )

    # Nunca permitir impresión física durante un smoke test.
    core._print_receipt_windows = lambda *_args, **_kwargs: "IMPRESORA_PRUEBA"

    with core.LocalSessionLocal() as db:
        db.info["offline"] = True

        p = core.Patient(
            cedula="1203456783",
            nombre="PACIENTE HISTORICO PRUEBA",
            celular=None,
            correo=None,
            lugar=None,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        patient_id = int(p.id)

        # 1) Una cédula equivalente con guiones/espacios debe bloquearse.
        duplicate_input = core.PatientIn(
            cedula="120-345-6783",
            nombre="OTRA FICHA QUE NO DEBE CREARSE",
        )
        try:
            app.v460_create_patient_guarded(duplicate_input, db, user)
        except core.HTTPException as exc:
            assert int(exc.status_code) == 409, exc
        else:
            raise AssertionError("La protección normalizada permitió una ficha duplicada")

        # 2) Sembramos un histórico que corresponde a la ficha activa existente.
        historical = core.HistoricalPatient(
            source_key="audit-v460-history",
            nombre="PACIENTE HISTORICO PRUEBA",
            search_text="PACIENTE HISTORICO PRUEBA 1203456783 0999999999 QUEVEDO",
            cedula="1203456783",
            celular="0999999999",
            correo="audit@example.invalid",
            lugar="QUEVEDO",
            first_year=2022,
            last_year=2022,
            last_visit_date=date(2022, 5, 10),
            row_count=1,
            aliases="PACIENTE HISTORICO PRUEBA",
            phones="0999999999",
            emails="audit@example.invalid",
            cedulas="1203456783",
        )
        db.add(historical)
        db.commit()
        db.refresh(historical)

        before = int(db.scalar(core.select(core.func.count(core.Patient.id))) or 0)
        activated = app.v4543_activate_historical_patient(int(historical.id), db, user)
        after = int(db.scalar(core.select(core.func.count(core.Patient.id))) or 0)

        assert int(activated["id"]) == patient_id, activated
        assert activated["suggested_type"] == "S", activated
        assert activated["historical"] is False, activated
        assert activated["activated_from_historical"] is True, activated
        assert before == after, (before, after)

        db.expire_all()
        refreshed = db.get(core.Patient, patient_id)
        assert str(refreshed.celular or "") == "0999999999"
        assert str(refreshed.correo or "") == "audit@example.invalid"
        assert str(refreshed.lugar or "") == "QUEVEDO"

        # Activar por segunda vez debe apuntar a la misma ficha.
        activated_again = app.v4543_activate_historical_patient(
            int(historical.id), db, user
        )
        after_again = int(db.scalar(core.select(core.func.count(core.Patient.id))) or 0)
        assert int(activated_again["id"]) == patient_id
        assert after_again == after

        with core.LocalSessionLocal() as ldb:
            link = ldb.get(core.HistoricalPatientLink, "audit-v460-history")
            assert link is not None
            assert int(link.patient_id) == patient_id

        # 3) Aunque una pantalla antigua intente enviar N, histórico => S.
        batch_endpoint = find_route(app, "/api/visits/batch-payment", "POST")
        batch_model = app.bridge_v4508.payment_core.V4504VisitBatchPaymentIn
        batch = batch_model(
            patient_id=patient_id,
            fecha=date.today(),
            tipo="N",
            services=[
                core.VisitBatchServiceIn(
                    procedimiento=None,
                    valor=25.0,
                )
            ],
            observacion="SMOKE V460",
            payment_method="EFECTIVO",
        )
        batch_endpoint(batch, db, user)
        db.commit()

        visit = db.scalar(
            core.select(core.Visit)
            .where(core.Visit.patient_id == patient_id)
            .order_by(core.Visit.id.desc())
        )
        assert visit is not None
        assert str(visit.tipo or "").upper() == "S", visit.tipo

        # 4) El recibo automático debe respetar S => SUBSECUENTE.
        print_endpoint = find_route(app, "/api/v4470/print-visit/{visit_id}", "POST")
        result = print_endpoint(int(visit.id), app._V4544PrintVisitIn(), db, user)
        assert result["ok"] is True
        assert result["printed"] is True
        assert result["tipo"] == "S", result
        assert result["is_new"] is False, result

        # 5) Auditor sin anomalías artificiales.
        audit_before = app._v460_data_audit(db, include_samples=True)
        assert audit_before["orphan_visits"] == 0
        assert audit_before["orphan_billing_records"] == 0

        # 6) Simulamos un duplicado legado para asegurar que el auditor lo ve.
        legacy_duplicate = core.Patient(
            cedula="120-345-6783",
            nombre="PACIENTE HISTORICO PRUEBA",
            celular="0999999999",
        )
        db.add(legacy_duplicate)
        db.commit()
        db.refresh(legacy_duplicate)

        a1 = core.Appointment(
            patient_id=patient_id,
            fecha=date.today(),
            hora="10:00",
            estado="PENDIENTE",
            origen="AUDITORIA",
        )
        a2 = core.Appointment(
            patient_id=patient_id,
            fecha=date.today(),
            hora="10:00",
            estado="PENDIENTE",
            origen="AUDITORIA",
        )
        db.add_all([a1, a2])
        db.commit()

        audit_after = app._v460_data_audit(db, include_samples=True)
        assert audit_after["duplicate_identification_groups"] >= 1, audit_after
        assert audit_after["duplicate_name_phone_groups"] >= 1, audit_after
        assert audit_after["duplicate_appointment_groups"] >= 1, audit_after

    print({
        "ok": True,
        "patient_reused": True,
        "historical_link_persisted": True,
        "historical_forced_subsequent": True,
        "receipt_subsequent": True,
        "normalized_duplicate_blocked": True,
        "legacy_duplicate_detected": True,
    })


if __name__ == "__main__":
    main()
