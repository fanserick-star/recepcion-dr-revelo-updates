from __future__ import annotations

import json


def _remove_route(app, path: str, method: str) -> int:
    method = method.upper()
    kept = []
    removed = 0
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in (getattr(route, "methods", None) or set())}
        if getattr(route, "path", None) == path and method in methods:
            removed += 1
        else:
            kept.append(route)
    app.router.routes[:] = kept
    return removed


def apply(core, app, legacy):
    _remove_route(app, "/api/identity/phone-owner", "GET")

    @app.get("/api/identity/phone-owner")
    def phone_owner_shared(
        phone: str,
        exclude_id: int = 0,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        normalized = core.normalize_lookup_phone(phone)
        if not normalized or len(normalized) < 9:
            return {"duplicate": False, "patient": None, "shared": [], "sharing_allowed": True}
        variants = {normalized}
        if len(normalized) == 10 and normalized.startswith("0"):
            variants.add("593" + normalized[1:])
        rows = list(db.scalars(
            core.select(core.Patient)
            .where(core.Patient.celular.in_(sorted(variants)))
            .order_by(core.Patient.id)
        ))
        shared = []
        for p in rows:
            if int(exclude_id or 0) and int(p.id) == int(exclude_id):
                continue
            if core.normalize_lookup_phone(p.celular) != normalized:
                continue
            shared.append({"id": int(p.id), "nombre": p.nombre, "cedula": p.cedula, "celular": p.celular})
        return {
            "duplicate": False,
            "patient": None,
            "shared": shared[:8],
            "normalized": normalized,
            "sharing_allowed": True,
        }

    def same_week_conflict(db, patient, target_date):
        monday = target_date - core.timedelta(days=target_date.weekday())
        sunday = monday + core.timedelta(days=6)
        linked = db.execute(
            core.select(core.Appointment, core.Patient)
            .join(core.Patient, core.Patient.id == core.Appointment.patient_id)
            .where(
                core.Appointment.patient_id == int(patient.id),
                core.Appointment.fecha >= monday,
                core.Appointment.fecha <= sunday,
                core.Appointment.origen != core.CONFIRMAFY_ATTENDED_ORIGIN,
                ~core.func.upper(core.func.coalesce(core.Appointment.estado, "")).in_(
                    ["CANCELADA", "CANCELADO", "NO_ASISTIRA", "NO_ASISTIRÁ", "REAGENDADA"]
                ),
            )
            .order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id)
            .limit(1)
        ).first()
        if linked:
            a, owner = linked
            return {"source": "appointment", "date": a.fecha.isoformat(), "time": a.hora, "name": owner.nombre}

        phone = core.normalize_lookup_phone(getattr(patient, "celular", ""))
        if not phone:
            return None
        variants = {phone}
        if len(phone) == 10 and phone.startswith("0"):
            variants.add("593" + phone[1:])
        staged = list(db.scalars(
            core.select(core.ConfirmafyAgendaItem)
            .where(
                core.ConfirmafyAgendaItem.fecha >= monday,
                core.ConfirmafyAgendaItem.fecha <= sunday,
                core.ConfirmafyAgendaItem.celular.in_(sorted(variants)),
            )
            .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora)
            .limit(12)
        ))
        current_name = core.normalize_lookup_name(getattr(patient, "nombre", ""))
        for item in staged:
            item_name = core.normalize_lookup_name(getattr(item, "nombre", ""))
            if current_name and item_name and (
                current_name == item_name or core.strong_name_overlap(current_name, item_name)
            ):
                return {"source": "staged", "date": item.fecha.isoformat(), "time": item.hora, "name": item.nombre}
        return None

    if hasattr(legacy, "_v4444_same_week_conflict"):
        legacy._v4444_same_week_conflict = same_week_conflict

    stable_sync = core.sync_one_operation

    def sync_one_operation(q, ldb, cdb):
        if q.operation != "procedure.archive":
            return stable_sync(q, ldb, cdb)
        already = cdb.get(core.SyncOperation, q.token)
        if already:
            return already.result_id
        payload = json.loads(q.payload or "{}")
        proc_id = int(payload["procedure_id"])
        proc = cdb.get(core.Procedure, proc_id)
        result_id = proc_id
        if proc:
            proc.activo = 0
            result_id = int(proc.id)
            core.audit(cdb, q.username, "sincronizar_archivo_procedimiento_offline", proc.nombre)
        cdb.add(core.SyncOperation(token=q.token, operation=q.operation, result_id=result_id))
        return result_id

    core.sync_one_operation = sync_one_operation

    _remove_route(app, "/api/procedures/{procedure_id}", "DELETE")

    @app.delete("/api/procedures/{procedure_id}")
    def archive_procedure(
        procedure_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        proc = db.get(core.Procedure, int(procedure_id))
        if not proc:
            raise core.HTTPException(404, "Servicio no encontrado")
        used = int(db.scalar(
            core.select(core.func.count(core.Visit.id)).where(
                core.func.upper(core.func.coalesce(core.Visit.procedimiento, ""))
                == str(proc.nombre or "").upper()
            )
        ) or 0)
        proc.activo = 0
        name = str(proc.nombre or "SERVICIO")
        if core.is_offline_db(db):
            core.add_queue(
                db, "procedure.archive", "procedure",
                {"procedure_id": int(procedure_id)}, user.username, int(procedure_id),
            )
            core.audit(db, user, "archivar_procedimiento_offline", f"{name}; {used} histórica(s)")
            db.commit()
            return {"ok": True, "archived": True, "offline": True, "used": used,
                    "message": "Servicio eliminado de la lista. Se sincronizará cuando vuelva Internet."}
        core.audit(db, user, "archivar_procedimiento", f"{name}; {used} histórica(s)")
        db.commit()
        core.mirror_procedure_local(proc)
        return {"ok": True, "archived": True, "offline": False, "used": used,
                "message": "Servicio eliminado de nuevas atenciones. El historial anterior se conserva." if used
                           else "Servicio eliminado de la lista."}

    return {"shared_phone": True, "procedure_archive": True, "weekly_identity_fix": True}
