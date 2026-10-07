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


def _delete_visit_source_aware(endpoint, visit_id: int, db, user):
    """Borra la atención que el usuario realmente ve en Recepción.

    Inicio y Pacientes leen desde la copia local para que la PC antigua sea rápida.
    Una atención creada local-first puede tener un ID local distinto del ID que
    recibió luego en Neon. Por eso un DELETE no debe interpretar ciegamente el ID
    visible como ID de Neon: primero se borra la fila local y la cola offline ya
    existente traduce ese ID mediante id_map antes de replicar el borrado a nube.

    Si la fila no existe localmente (por ejemplo una llamada API con un ID de nube),
    conservamos el comportamiento anterior usando la sesión recibida.
    """
    local_db = None
    try:
        local_db = core.LocalSessionLocal()
        local_visit = local_db.get(core.Visit, int(visit_id))
        if local_visit is not None:
            captured = _capture_visit(local_db, visit_id)
            result = endpoint(int(visit_id), local_db, user)
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
def delete_visit_and_cancel_historia_safe(
    visit_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result, captured, _source = _delete_visit_source_aware(
        _old_safe_delete_visit,
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
def delete_visit_and_cancel_historia_direct(
    visit_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result, captured, _source = _delete_visit_source_aware(
        _old_direct_delete_visit,
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


def _mapped_cloud_visit_ids(local_db, visit_ids: list[int]) -> list[int]:
    mapped = []
    for value in visit_ids:
        try:
            cloud_id = int(core.resolve_cloud_id(local_db, "visit", int(value)))
        except Exception:
            cloud_id = int(value)
        if cloud_id not in mapped:
            mapped.append(cloud_id)
    return mapped


def _recent_deleted_handoffs(days: int = 2) -> list[dict]:
    """Encuentra handoffs LAN recientes cuya atención ya no existe en Recepción.

    Los visit_ids del handoff corresponden al ID visible/local. Si Neon es la
    autoridad, cada ID se traduce primero con id_map antes de comprobar existencia.
    Esto evita cancelar por error una atención válida cuyo ID de nube es distinto.
    """
    path = historia_lan_transport.LAN_OUTBOX_DB
    if not path.is_file():
        return []

    authoritative_is_cloud = core.CloudSessionLocal is not None
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
    local_db = None
    out = []
    try:
        db = session_factory()
        local_db = core.LocalSessionLocal()
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

            # La atención visible/local es prueba suficiente de que NO fue borrada.
            # No consultamos Neon primero porque una atención local-first puede tardar
            # unos segundos/minutos en recibir su ID de nube.
            local_surviving = list(
                local_db.scalars(core.select(core.Visit.id).where(core.Visit.id.in_(visit_ids)))
            )
            if local_surviving:
                continue

            authoritative_ids = (
                _mapped_cloud_visit_ids(local_db, visit_ids)
                if authoritative_is_cloud
                else visit_ids
            )
            surviving = list(
                db.scalars(core.select(core.Visit.id).where(core.Visit.id.in_(authoritative_ids)))
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
        try:
            if local_db is not None:
                local_db.close()
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


def _recent_live_handoffs(days: int = 2) -> list[dict]:
    """Devuelve handoffs recientes cuya atención TODAVÍA existe localmente.

    El restore remoto es idempotente: solo cambia cancelled -> waiting. Por eso
    podemos comprobar todos los handoffs vivos y reparar también el caso en que
    un visit_id borrado fue reutilizado y el event_id determinista quedó pegado a
    un turno cancelado anterior.
    """
    path = historia_lan_transport.LAN_OUTBOX_DB
    if not path.is_file():
        return []

    cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            rows = conn.execute(
                """
                SELECT event_id,payload_json
                FROM events
                WHERE created_at>=?
                ORDER BY created_at DESC
                LIMIT 120
                """,
                (cutoff,),
            ).fetchall()
    except Exception:
        return []

    local_db = None
    out = []
    try:
        local_db = core.LocalSessionLocal()
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
                local_db.scalars(core.select(core.Visit.id).where(core.Visit.id.in_(visit_ids)))
            )
            if not surviving:
                continue

            out.append(
                {
                    "event_id": str(event_id),
                    "visit_id": visit_ids[0],
                    "patient_id": str(payload.get("reception_patient_id") or ""),
                }
            )
    except Exception:
        return []
    finally:
        try:
            if local_db is not None:
                local_db.close()
        except Exception:
            pass
    return out


def restore_recent_live_handoffs() -> int:
    restored = 0
    for item in _recent_live_handoffs():
        targets = _restore_historia_visit(item["visit_id"], item["patient_id"])
        if targets:
            restored += 1
    return restored


def _startup_reconcile_worker() -> None:
    # Da tiempo al monitor LAN para descubrir la PC del doctor. El evento local
    # queda marcado cancelado de todos modos y el transporte reintenta si hace falta.
    time.sleep(2.0)
    # Primero restaura de forma idempotente todo handoff reciente cuya visita
    # siga viva localmente. Esto incluye event_id reutilizados tras borrar/recrear.
    restore_recent_live_handoffs()
    # Después reconcilia únicamente handoffs realmente ausentes local + nube.
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
        "delete_uses_visible_local_id": True,
        "restore_sync_active": _old_restore_trash is not None,
        "transport": "lan-only",
        "startup_recent_delete_reconcile": True,
        "startup_reconcile_maps_local_to_cloud": True,
        "startup_reconcile_requires_local_absence": True,
        "startup_false_cancel_self_heal": True,
        "startup_live_handoff_idempotent_restore": True,
        "reused_event_id_cancel_recovery": True,
        "signed_history_protected": True,
        "database_schema_changes": False,
    }


PATCH_DELETE_HISTORY_CANCEL_OK = True
PATCH_BOOT_OK = True
