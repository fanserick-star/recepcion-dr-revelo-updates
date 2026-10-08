from __future__ import annotations

import core_runtime as core
import historia_bridge
import historia_lan_transport

app = core.app

# Único vínculo de cancelación Recepción -> Historia.
# Desde 4.7.0 la atención nunca se borra físicamente: core.delete_visit cambia
# estado a CANCELADA y preserva BillingRecord/AzurEmission.
historia_lan_transport.install(historia_bridge)


def _remove_route(path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in set(getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def _capture_visit(db, visit_id: int) -> dict:
    try:
        visit = core.get_visit_any_state(db, int(visit_id))
    except Exception:
        visit = None
    if visit is None:
        return {"visit_id": int(visit_id), "patient_id": ""}
    return {
        "visit_id": int(getattr(visit, "id", visit_id) or visit_id),
        "patient_id": str(getattr(visit, "patient_id", "") or ""),
    }


def _cancel_historia_visit(visit_id, patient_id, db=None, user=None):
    if not patient_id:
        return []
    try:
        return historia_bridge.cancel_attention(
            visit_id=visit_id,
            reception_patient_id=patient_id,
        )
    except Exception as exc:
        try:
            if db is not None and user is not None:
                core.audit(
                    db,
                    user,
                    "historia_cancel_pending",
                    f"Atención {visit_id}, paciente {patient_id}: {type(exc).__name__}",
                )
                db.commit()
        except Exception:
            pass
        return []


_old_safe_cancel_visit = _remove_route("/api/safety/visits/{visit_id}", "DELETE")
_old_direct_cancel_visit = _remove_route("/api/visits/{visit_id}", "DELETE")

if _old_safe_cancel_visit is None or _old_direct_cancel_visit is None:
    raise RuntimeError("No se encontraron las rutas de atención necesarias para sincronizar Historia Clínica")


def _cancel_visit_source_aware(endpoint, visit_id: int, db, user):
    """Usa el ID visible/local sin convertirlo en un borrado físico.

    Si la UI trabaja sobre SQLite local-first, la cancelación queda en esa misma
    fila y se encola visit.cancel para Neon. Si el ID ya es el de nube, usa la
    sesión recibida.
    """
    local_db = None
    try:
        local_db = core.LocalSessionLocal()
        # This is explicitly a local SQLite session. Without this flag,
        # delete_visit() treats it as a cloud session and never queues visit.cancel.
        local_db.info["offline"] = True
        local_db.info["local_first"] = True
        local_visit = core.get_visit_any_state(local_db, int(visit_id))
        if local_visit is not None:
            # A previously cancelled local row might have missed cloud sync in
            # older versions. A repeated delete must repair its pending tombstone.
            was_cancelled = str(getattr(local_visit, "estado", "ACTIVA") or "").upper() == "CANCELADA"
            captured = _capture_visit(local_db, visit_id)
            result = endpoint(int(visit_id), local_db, user)
            if was_cancelled:
                queued = local_db.scalar(core.select(core.OfflineQueue.id).where(
                    core.OfflineQueue.operation.in_(("visit.cancel", "visit.delete")),
                    core.OfflineQueue.local_entity_id == int(visit_id),
                ).limit(1))
                if queued is None:
                    core.add_queue(
                        local_db, "visit.cancel", "visit",
                        {"visit_id": int(visit_id), "cloud_visit_id": core.get_id_map(local_db, "visit", int(visit_id))},
                        str(getattr(user, "username", "") or "admin"), int(visit_id),
                    )
                    local_db.commit()
            # Event-driven sync, never a polling loop. If offline, the durable
            # SQLite queue remains until connectivity resumes.
            try:
                core.threading.Thread(
                    target=core.process_offline_queue,
                    name="rp-visit-cancel-sync", daemon=True,
                ).start()
            except Exception:
                pass
            return result, captured, "local"
    finally:
        try:
            if local_db is not None:
                local_db.close()
        except Exception:
            pass

    captured = _capture_visit(db, visit_id)
    result = endpoint(int(visit_id), db, user)
    return result, captured, "request-db"


@app.delete("/api/safety/visits/{visit_id}")
def cancel_visit_and_cancel_historia_safe(
    visit_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result, captured, _source = _cancel_visit_source_aware(
        _old_safe_cancel_visit,
        visit_id,
        db,
        user,
    )
    patient_id = (
        str((result or {}).get("patient_id") or "")
        if isinstance(result, dict)
        else ""
    ) or captured["patient_id"]
    _cancel_historia_visit(visit_id, patient_id, db, user)
    return result


@app.delete("/api/visits/{visit_id}")
def cancel_visit_and_cancel_historia_direct(
    visit_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result, captured, _source = _cancel_visit_source_aware(
        _old_direct_cancel_visit,
        visit_id,
        db,
        user,
    )
    patient_id = (
        str((result or {}).get("patient_id") or "")
        if isinstance(result, dict)
        else ""
    ) or captured["patient_id"]
    _cancel_historia_visit(visit_id, patient_id, db, user)
    return result


@app.get("/api/history-cancel/health")
def history_cancel_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "attention_state_model": "ACTIVA/CANCELADA",
        "physical_visit_delete": False,
        "invoice_preserved": True,
        "startup_reconcile": False,
        "cancel_requires_patient_and_visit": True,
        "transport": "lan-only",
        "signed_history_protected": True,
        "database_schema_changes": True,
    }


# Compatibilidad con módulos que solo consultan estas banderas.
PATCH_DELETE_HISTORY_CANCEL_OK = True
PATCH_BOOT_OK = True
