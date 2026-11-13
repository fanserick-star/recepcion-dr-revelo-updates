"""Locally approved Reception selector for the *clinical* Neon, never billing.

No clinical records, database URIs, credentials, or patient identifiers are
returned to a browser. A change is stored as a pending startup selection and
takes effect in a fresh Reception process only after a safe parity preflight.
"""
from __future__ import annotations

import json
import os
import sqlite3
import ssl
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import core_runtime as core
import historia_bridge as bridge

app = core.app
PENDING_PATH = bridge.ROOT / "data" / "historia_neon_pending.json"
_LAST_SCAN = {}
_VALID_FOR_SECONDS = 180


def _local(request: Request):
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Solo disponible en esta PC de Recepción.")
    origin = request.headers.get("origin", "")
    if origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(403, "Origen de configuración no autorizado.")


def _json_read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or obj.get("schema") != 1:
            raise ValueError("Registro de selección inválido")
        return obj
    except (ValueError, OSError, TypeError) as exc:
        raise RuntimeError("Configuración pendiente inválida; no se cambió el Neon") from exc


def _write_pending(target: str) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": 1, "target": target, "created_at": int(time.time())}
    fd, temp = tempfile.mkstemp(prefix=".historia-neon-", suffix=".tmp",
                                dir=PENDING_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, PENDING_PATH)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def apply_pending_at_startup():
    """Revalidate at restart; never break Reception if pending switch is unsafe."""
    if not PENDING_PATH.exists():
        return {"state": "not_scheduled"}
    try:
        req = _json_read(PENDING_PATH)
        target = bridge._validated_target(req.get("target") or "")
        if target == bridge._history_target():
            PENDING_PATH.unlink(missing_ok=True)
            return {"state": "already_active"}
        # Data and queue may have changed since the operator clicked.
        # Refuse switching if any safety condition is no longer true.
        report = _preflight(target)
        if not report["ok"]:
            return {"state": "blocked", "reason": "Vinculaciones o envíos pendientes"}
        active = bridge.ACTIVE_NEON_SELECTION
        active.parent.mkdir(parents=True, exist_ok=True)
        os.replace(PENDING_PATH, active)
        # The process is not serving HTTP or workers yet. All future calls,
        # including LAN handoff and document verification, use this one target.
        bridge._PROCESS_HISTORY_TARGET = target
        return {"state": "activated", "target": target}
    except Exception:
        # No fallback hidden switch, no risk of taking the admin app offline.
        # Keep the pending request to show the operator a blocked state.
        return {"state": "blocked", "reason": "Revisión o conexión privada pendiente"}


def _connected(target: str):
    import pg8000.dbapi as pg
    url = bridge._database_url_for_target(target)
    if not url:
        raise RuntimeError("Falta la conexión privada del Neon seleccionado")
    cfg = bridge._parse_pg_url(url)
    conn = pg.connect(user=cfg["user"], password=cfg["password"],
                      host=cfg["host"], port=cfg["port"],
                      database=cfg["database"], ssl_context=ssl.create_default_context(),
                      timeout=7)
    conn.cursor().execute("SET TRANSACTION READ ONLY")
    return conn


def _link_snapshot(conn) -> dict:
    cur = conn.cursor()
    cur.execute("""
        SELECT l.reception_patient_id::text,l.clinical_patient_id::text,
               p.id IS NOT NULL AND p.deleted_at IS NULL
                 AND p.merged_into_patient_id IS NULL AS patient_valid
        FROM public.patient_links l
        LEFT JOIN public.patients p ON p.id=l.clinical_patient_id
        WHERE l.verified=1 AND l.deleted_at IS NULL
    """)
    out = {}
    for rid, cid, valid in cur.fetchall():
        rid, cid = str(rid), str(cid or "")
        if not rid or not cid or rid in out:
            raise RuntimeError("Vinculaciones duplicadas o incompletas: revisión necesaria")
        out[rid] = (cid, bool(valid))
    return out


def _pending_work() -> tuple[int, int]:
    try:
        reception_pending = int(core.queue_count())
    except Exception as exc:
        raise RuntimeError("No se pudo verificar la cola offline de Recepción") from exc
    lan_path = bridge.ROOT / "data" / "historia_lan_outbox.db"
    if not lan_path.is_file():
        return reception_pending, 0
    try:
        db = sqlite3.connect("file:" + lan_path.resolve().as_posix() + "?mode=ro",
                             uri=True, timeout=4)
        try:
            remaining = int(db.execute(
                "SELECT COUNT(*) FROM events WHERE cancelled=0 AND "
                "((sent_at IS NULL AND date(created_at) >= date('now','localtime')) "
                "OR control_pending=1)"
            ).fetchone()[0])
        finally:
            db.close()
    except Exception as exc:
        raise RuntimeError("No se pudo verificar la cola LAN del doctor") from exc
    return reception_pending, remaining


def _preflight(target: str) -> dict:
    selected = bridge._validated_target(target)
    current = bridge._history_target()
    if selected == current:
        return {"ok": True, "same_target": True, "target": selected,
                "missing": 0, "different": 0, "destination_only": 0,
                "pending": 0, "pending_lan": 0}
    # This selector does NOT reconcile identities. A missing link must be
    # reviewed via Reception, never inferred from a matching name.
    official = emergency = None
    try:
        official = _connected("official")
        emergency = _connected("emergency")
        from_rows = _link_snapshot(official if current == "official" else emergency)
        to_rows = _link_snapshot(emergency if selected == "emergency" else official)
        missing = [rid for rid in from_rows if rid not in to_rows]
        different = [rid for rid in from_rows if rid in to_rows
                     and (from_rows[rid][0] != to_rows[rid][0]
                          or not from_rows[rid][1] or not to_rows[rid][1])]
        destination_only = [rid for rid in to_rows if rid not in from_rows]
        invalid = sum(1 for _,v in to_rows.items() if not v[1])
        # The destination might contain newer legitimate Reception links.
        # Do not switch while either side has unmatched links.
        pending, pending_lan = _pending_work()
        blockers = []
        if missing or destination_only or different or invalid:
            blockers.append("Diferencias de vinculación: revisa las fichas antes de cambiar.")
        if pending or pending_lan:
            blockers.append("Hay sincronizaciones o turnos LAN pendientes.")
        # A Reception operator can create new links on the original while
        # scanning. The second preflight before scheduling catches changes.
        return {
            "ok": not blockers, "same_target": False, "target": selected,
            "source_links": len(from_rows), "destination_links": len(to_rows),
            "missing": len(missing), "different": len(different),
            "destination_only": len(destination_only), "invalid": invalid,
            "pending": pending, "pending_lan": pending_lan,
            "message": ("Listo para programar el cambio al reiniciar."
                        if not blockers else " ".join(blockers)),
        }
    finally:
        for conn in (official, emergency):
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
                try: conn.close()
                except Exception: pass


def _status():
    active = bridge._history_target()
    pending = _json_read(PENDING_PATH).get("target") or ""
    available = {}
    for target in ("official", "emergency"):
        try:
            available[target] = bool(bridge._database_url_for_target(target))
        except Exception:
            available[target] = False
    return {"ok": True, "active": active, "pending_restart": pending,
            "credential_ready": available,
            "clinical_only": True, "reception_finances_unchanged": True,
            "switch_changes_only_after_restart": True}


def _request_ok(request: Request):
    _local(request)
    if request.headers.get("x-reception-neon-control") != "1":
        raise HTTPException(403, "Confirmación local requerida.")


@app.get("/api/config/historia-neon", dependencies=[core.Depends(core.current_user)])
def historia_neon_status(request: Request):
    _local(request)
    try:
        return _status()
    except Exception:
        return JSONResponse({"ok": False, "message": "Error en la configuración local de Neon."}, status_code=409)


@app.post("/api/config/historia-neon/check", dependencies=[core.Depends(core.current_user)])
async def historia_neon_check(request: Request):
    _request_ok(request)
    try:
        body = await request.json()
        target = bridge._validated_target(str(body.get("target") or ""))
        report = _preflight(target)
        if report["ok"] and not report["same_target"]:
            _LAST_SCAN["target"], _LAST_SCAN["at"] = target, time.monotonic()
        else:
            _LAST_SCAN.clear()
        return report
    except Exception:
        _LAST_SCAN.clear()
        return JSONResponse({"ok": False,
            "message": "No se pudo comparar ambos servidores de forma segura. "
                       "Revisa su conexión privada y las vinculaciones."}, status_code=409)


@app.post("/api/config/historia-neon/select", dependencies=[core.Depends(core.current_user)])
async def historia_neon_select(request: Request):
    _request_ok(request)
    try:
        body = await request.json()
        target = bridge._validated_target(str(body.get("target") or ""))
        if body.get("confirm") != "CAMBIAR_HISTORIA_AL_REINICIAR":
            raise RuntimeError("Confirmación explícita requerida")
        if (_LAST_SCAN.get("target") != target
                or time.monotonic() - float(_LAST_SCAN.get("at") or 0) > _VALID_FOR_SECONDS):
            raise RuntimeError("Comparación vencida")
        report = _preflight(target)
        if not report["ok"] or report["same_target"]:
            raise RuntimeError("Diferencias pendientes")
        _write_pending(target)
        _LAST_SCAN.clear()
        return {"ok": True, "pending_restart": target,
                "message": "Cambio preparado. Cierra Recepción después de atender "
                           "y ábrela desde el launcher. Si no se reinicia, "
                           "todas las consultas siguen usando el Neon anterior."}
    except Exception:
        _LAST_SCAN.clear()
        return JSONResponse({"ok": False,
            "message": "No se activó el cambio. Hay diferencias, trabajo pendiente "
                       "o la conexión privada no está lista. El Neon actual continúa activo."},
            status_code=409)
