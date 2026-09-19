from __future__ import annotations

# v4.5.22 — sincroniza borrado/restauración de atenciones con Historia.
# Una atención eliminada cancela su turno en Historia por LAN y por el
# outbox Neon. Una historia ya finalizada queda protegida y no se borra.

import app_patch_4521 as previous
import historia_bridge

core = previous.core
app = previous.app
APP_VERSION = "4.5.22"

_mod = previous
_seen = set()
for _ in range(560):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION


def _remove_route(path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in set(getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


_old_safe_delete_visit = _remove_route("/api/safety/visits/{visit_id}", "DELETE")
_old_direct_delete_visit = _remove_route("/api/visits/{visit_id}", "DELETE")
_old_restore_trash = _remove_route("/api/ops/trash/{trash_id}/restore", "POST")


def _cancel_historia_visit(visit_id, patient_id, db=None, user=None):
    try:
        historia_bridge.cancel_attention(
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
                    f"Atención {visit_id}: {type(exc).__name__}",
                )
                db.commit()
        except Exception:
            pass


def _restore_historia_visit(visit_id, patient_id, db=None, user=None):
    try:
        historia_bridge.restore_attention(
            visit_id=visit_id,
            reception_patient_id=patient_id,
        )
    except Exception as exc:
        try:
            if db is not None and user is not None:
                core.audit(
                    db,
                    user,
                    "historia_restore_pending",
                    f"Atención {visit_id}: {type(exc).__name__}",
                )
                db.commit()
        except Exception:
            pass


if _old_safe_delete_visit is not None:
    @app.delete("/api/safety/visits/{visit_id}")
    def v4522_safe_delete_visit(
        visit_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        result = _old_safe_delete_visit(visit_id, db, user)
        patient_id = (result or {}).get("patient_id") if isinstance(result, dict) else None
        _cancel_historia_visit(visit_id, patient_id or "", db, user)
        return result


if _old_direct_delete_visit is not None:
    @app.delete("/api/visits/{visit_id}")
    def v4522_direct_delete_visit(
        visit_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        result = _old_direct_delete_visit(visit_id, db, user)
        patient_id = (result or {}).get("patient_id") if isinstance(result, dict) else None
        _cancel_historia_visit(visit_id, patient_id or "", db, user)
        return result


if _old_restore_trash is not None:
    @app.post("/api/ops/trash/{trash_id}/restore")
    def v4522_restore_trash(
        trash_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        result = _old_restore_trash(trash_id, db, user)
        if isinstance(result, dict) and result.get("entity_type") == "visit":
            visit_id = result.get("entity_id")
            try:
                visit = db.get(core.Visit, int(visit_id))
            except Exception:
                visit = None
            patient_id = getattr(visit, "patient_id", "") if visit is not None else ""
            _restore_historia_visit(visit_id, patient_id, db, user)
        return result


@app.get("/api/v4522/health")
def v4522_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_delete_sync": True,
        "historia_restore_sync": True,
        "signed_history_protected": True,
        "transport": "lan-first-cloud-backup",
        "database_schema_changes": False,
    }


PATCH_BOOT_OK = True
