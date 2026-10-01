from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import core_runtime as core
import historia_bridge
import historia_lan_transport

app = core.app

# La cancelación debe viajar por el mismo transporte LAN que los handoffs.
# Se instala aquí de forma explícita para que borrar una atención nunca dependa
# de que otro módulo histórico haya sido importado antes.
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
        visit = db.get(core.Visit, int(visit_id))
    except Exception:
        visit = None
    if visit is None:
        return {"visit_id": int(visit_id), "patient_id": ""}
    return {
        "visit_id": int(getattr(visit, "id", visit_id) or visit_id),
        "patient_id": str(getattr(visit, "patient_id", "") or ""),
    }


def _cancel_historia_visit(visit_id, patient_id, db=None, user=None):
    try:
        return historia_bridge.cancel_attention(
            visit_id=visit_id,
            reception_patient_id=patient_id or "",
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
        return []


def _restore_historia_visit(visit_id, patient_id, db=None, user=None):
    try:
        return historia_bridge.restore_attention(
            visit_id=visit_id,
            reception_patient_id=patient_id or "",
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
        return []


_old_safe_delete_visit = _remove_route("/api/safety/visits/{visit_id}", "DELETE")
_old_direct_delete_visit = _remove_route("/api/visits/{visit_id}", "DELETE")
_old_restore_trash = _remove_route("/api/ops/trash/{trash_id}/restore", "POST")

if _old_safe_delete_visit is None or _old_direct_delete_visit is None:
    raise RuntimeError("No se encontraron las rutas de borrado necesarias para sincronizar Historia Clínica")


@app.delete("/api/safety/visits/{visit_id}")
def delete_visit_and_cancel_historia_safe(
    visit_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    captured = _capture_visit(db, visit_id)
    result = _old_safe_delete_visit(visit_id, db, user)
    patient_id = (
        str((result or {}).get("patient_id") or "")
        if isinstance(result, dict)
        else ""
    ) or captured["patient_id"]
    _cancel_historia_visit(visit_id, patient_id, db, user)
    return result


@app.delete("/api/visits/{visit_id}")
def delete_visit_and_cancel_historia_direct(
    visit_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    captured = _capture_visit(db, visit_id)
    result = _old_direct_delete_visit(visit_id, db, user)
    patient_id = (
        str((result or {}).get("patient_id") or "")
        if isinstance(result, dict)
        else ""
    ) or captured["patient_id"]
    _cancel_historia_visit(visit_id, patient_id, db, user)
    return result


if _old_restore_trash is not None:

    @app.post("/api/ops/trash/{trash_id}/restore")
    def restore_visit_and_restore_historia(
        trash_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        result = _old_restore_trash(trash_id, db, user)
        if isinstance(result, dict) and result.get("entity_type") == "visit":
            visit_id = result.get("entity_id")
            visit = None
            try:
                visit = db.get(core.Visit, int(visit_id))
            except Exception:
                pass
            patient_id = str(getattr(visit, "patient_id", "") or "") if visit is not None else ""
            _restore_historia_visit(visit_id, patient_id, db, user)
        return result


def _recent_deleted_handoffs(days: int = 2) -> list[dict]:
    """Encuentra handoffs LAN recientes cuya atención ya no existe en Recepción.

    Solo repara automáticamente si podemos consultar la base autoritativa. Si
    Recepción usa Neon y Neon no responde, no inferimos una eliminación desde
    una cache potencialmente incompleta.
    """
    path = historia_lan_transport.LAN_OUTBOX_DB
    if not path.is_file():
        return []

    session_factory = core.CloudSessionLocal or core.LocalSessionLocal
    cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT event_id,payload_json
                FROM events
                WHERE created_at>=? AND cancelled=0
                ORDER BY created_at DESC
                LIMIT 120
                """,
                (cutoff,),
            ).fetchall()
    except Exception:
        return []

    db = None
    out = []
    try:
        db = session_factory()
        # Fuerza la conexión antes de tomar cualquier decisión destructiva.
        db.execute(core.select(core.Visit.id).limit(1)).all()
        for event_id, payload_json in rows:
            try:
                payload = json.loads(payload_json)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            visit_ids = []
            for value in payload.get("visit_ids") or []:
                try:
                    visit_ids.append(int(value))
                except Exception:
                    pass
            if not visit_ids:
                continue
            surviving = list(
                db.scalars(core.select(core.Visit.id).where(core.Visit.id.in_(visit_ids)))
            )
            if surviving:
                continue
            out.append(
                {
                    "event_id": str(event_id),
                    "visit_id": visit_ids[0],
                    "patient_id": str(payload.get("reception_patient_id") or ""),
                }
            )
    except Exception:
        # Si Neon estaba configurado pero no disponible, no caemos a la cache.
        return []
    finally:
        try:
            if db is not None:
                db.close()
        except Exception:
            pass
    return out


def reconcile_recent_deleted_handoffs() -> int:
    repaired = 0
    for item in _recent_deleted_handoffs():
        targets = _cancel_historia_visit(item["visit_id"], item["patient_id"])
        if targets:
            repaired += 1
    return repaired


def _startup_reconcile_worker() -> None:
    # Da tiempo al monitor LAN para descubrir la PC del doctor. El evento local
    # queda marcado cancelado de todos modos y el transporte reintenta si hace falta.
    time.sleep(2.0)
    reconcile_recent_deleted_handoffs()


@app.on_event("startup")
def _reconcile_historia_deletions_on_startup():
    threading.Thread(
        target=_startup_reconcile_worker,
        daemon=True,
        name="historia-delete-reconcile",
    ).start()


@app.get("/api/history-cancel/health")
def history_cancel_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "delete_sync_active": True,
        "restore_sync_active": _old_restore_trash is not None,
        "transport": "lan-only",
        "startup_recent_delete_reconcile": True,
        "signed_history_protected": True,
        "database_schema_changes": False,
    }


PATCH_DELETE_HISTORY_CANCEL_OK = True
PATCH_BOOT_OK = True
