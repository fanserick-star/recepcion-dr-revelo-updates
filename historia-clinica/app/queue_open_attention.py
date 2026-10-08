from __future__ import annotations

import html
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "historia_clinica.db"
PATCH_VERSION = "1.3.95"
_CONFIRM_PARAM = "v1395_confirm"

_OPEN_RE = re.compile(r"^/cola/([^/]+)/atender/?$")
_LINK_RE = re.compile(r"^/cola/([^/]+)/vincular/[^/]+/?$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_procedure(value: object) -> bool:
    raw = " ".join(str(value or "").strip().upper().split())
    if raw in {"REVISIÓN DE EXÁMENES", "REVISION DE EXAMENES"}:
        return False
    return bool(raw in {"P", "X", "PROCEDIMIENTO"} or raw.startswith("PROCEDIMIENTO "))


def _safe_turn(value: object) -> str:
    try:
        number = int(value)
        if number > 0:
            return f"{number:02d}"
    except Exception:
        pass
    return "--"


def _wake_sync() -> None:
    try:
        import cloud_sync

        service = getattr(cloud_sync, "_SERVICE", None)
        if service is not None:
            try:
                service.mark_activity()
            except Exception:
                pass
            try:
                service.wake()
            except Exception:
                pass
    except Exception:
        pass


def _queue_context(queue_id: str) -> dict | None:
    if not queue_id or not DB_PATH.is_file():
        return None
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(waiting_queue)").fetchall()}
            turn_expr = "reception_turn" if "reception_turn" in cols else "NULL AS reception_turn"
            clinical_expr = "clinical_patient_id" if "clinical_patient_id" in cols else "NULL AS clinical_patient_id"
            row = conn.execute(
                f"""SELECT id,status,attention_type,{turn_expr},{clinical_expr}
                    FROM waiting_queue WHERE id=? LIMIT 1""",
                (str(queue_id),),
            ).fetchone()
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "status": str(row["status"] or ""),
                "attention_type": str(row["attention_type"] or ""),
                "turn": _safe_turn(row["reception_turn"]),
                "clinical_patient_id": str(row["clinical_patient_id"] or ""),
            }
    except Exception:
        return None


def _other_active_consultation(queue_id: str) -> dict | None:
    """Return another active consultation, ignoring procedures for TV safety."""
    if not queue_id or not DB_PATH.is_file():
        return None
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(waiting_queue)").fetchall()}
            turn_expr = "reception_turn" if "reception_turn" in cols else "NULL AS reception_turn"
            started_expr = "started_at" if "started_at" in cols else "NULL AS started_at"
            updated_expr = "updated_at" if "updated_at" in cols else "NULL AS updated_at"
            rows = conn.execute(
                f"""SELECT id,status,attention_type,{turn_expr},{started_expr},{updated_expr}
                    FROM waiting_queue
                    WHERE status='in_consultation' AND id<>?
                    ORDER BY COALESCE({started_expr.split(' AS ')[0] if ' AS ' in started_expr else 'started_at'},
                                      {updated_expr.split(' AS ')[0] if ' AS ' in updated_expr else 'updated_at'},'') DESC,
                             id DESC
                    LIMIT 12""",
                (str(queue_id),),
            ).fetchall()
            for row in rows:
                if _is_procedure(row["attention_type"]):
                    continue
                return {
                    "id": str(row["id"]),
                    "turn": _safe_turn(row["reception_turn"]),
                    "started_at": str(row["started_at"] or row["updated_at"] or ""),
                }
    except Exception:
        return None
    return None


def _confirmation_context(queue_id: str, *, link_selected: bool) -> dict | None:
    target = _queue_context(queue_id)
    if not target or target["status"] != "waiting" or _is_procedure(target["attention_type"]):
        return None

    # Si todavía no está vinculada y apenas se abrió la tarjeta, primero se
    # conserva el flujo normal de selección de ficha. La confirmación aparece
    # únicamente cuando ya existe una ficha resuelta o el doctor acaba de elegirla.
    if not link_selected and not target["clinical_patient_id"]:
        return None

    active = _other_active_consultation(queue_id)
    if not active:
        return None
    return {"target": target, "active": active}


def _render_confirmation(request: Request, context: dict) -> HTMLResponse:
    target_turn = html.escape(str(context["target"].get("turn") or "--"))
    active_turn = html.escape(str(context["active"].get("turn") or "--"))
    confirm_url = str(request.url.include_query_params(**{_CONFIRM_PARAM: "1"}))
    confirm_url = html.escape(confirm_url, quote=True)
    body = f"""<!doctype html>
<html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Confirmar inicio de atención</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef4f8;font-family:Arial,Helvetica,sans-serif;color:#173b66}}
.wrap{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:28px}}
.card{{width:min(620px,96vw);background:#fff;border:1px solid #d7e3ec;border-radius:20px;box-shadow:0 18px 45px #173b661c;padding:28px}}
.badge{{display:inline-block;background:#fff4d6;color:#805500;border:1px solid #efd48d;border-radius:999px;padding:7px 11px;font-size:12px;font-weight:900;letter-spacing:.04em}}
h1{{font-size:25px;margin:16px 0 10px}}p{{font-size:16px;line-height:1.5;color:#50677a;margin:8px 0}}
.turns{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:20px 0}}
.turn{{border:1px solid #d7e3ec;border-radius:14px;padding:15px;background:#f8fbfd}}.turn span{{display:block;font-size:11px;font-weight:900;color:#6d8292;letter-spacing:.08em}}.turn b{{font-size:32px;color:#173b66}}
.actions{{display:flex;gap:10px;justify-content:flex-end;margin-top:22px;flex-wrap:wrap}}a{{text-decoration:none;border-radius:11px;padding:11px 15px;font-weight:900}}.back{{background:#edf2f6;color:#29465b}}.go{{background:#246fae;color:#fff}}
.note{{font-size:13px;color:#6d8292;margin-top:13px}}
</style></head><body><div class='wrap'><section class='card'>
<div class='badge'>ATENCIÓN ACTIVA</div><h1>Ya hay otra consulta en atención</h1>
<p>El doctor todavía tiene un turno marcado como <b>En atención</b>. Para evitar cambiar la TV por accidente, el siguiente turno no se iniciará sin confirmación.</p>
<div class='turns'><div class='turn'><span>ATENCIÓN ACTUAL</span><b>{active_turn}</b></div><div class='turn'><span>NUEVO TURNO</span><b>{target_turn}</b></div></div>
<p class='note'>Si continúas, la atención anterior no se finalizará, no se borrará y no se modificará. Solo el nuevo turno pasará a En atención.</p>
<div class='actions'><a class='back' href='/'>Mantener atención actual</a><a class='go' href='{confirm_url}'>Sí, iniciar turno {target_turn}</a></div>
</section></div></body></html>"""
    return HTMLResponse(body, status_code=409, headers={"Cache-Control": "no-store"})


def _start_attention(queue_id: str, *, allow_parallel: bool = False) -> bool:
    """Mark one waiting item as in consultation exactly once.

    Reopening the same chart never changes started_at. A second simultaneous
    consultation is blocked unless the doctor explicitly confirmed it. Procedures
    keep their existing behavior and remain outside TV turn logic.
    """
    if not queue_id or not DB_PATH.is_file():
        return False

    stamp = _now()
    for attempt in range(4):
        try:
            with sqlite3.connect(DB_PATH, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(waiting_queue)").fetchall()}
                if "started_at" not in cols:
                    conn.execute("ALTER TABLE waiting_queue ADD COLUMN started_at TEXT")
                if "updated_at" not in cols:
                    conn.execute("ALTER TABLE waiting_queue ADD COLUMN updated_at TEXT")

                row = conn.execute(
                    "SELECT id,status,clinical_patient_id,attention_type FROM waiting_queue WHERE id=? LIMIT 1",
                    (str(queue_id),),
                ).fetchone()
                if not row or str(row["status"] or "") != "waiting":
                    return False

                if not allow_parallel and not _is_procedure(row["attention_type"]):
                    active_rows = conn.execute(
                        "SELECT id,attention_type FROM waiting_queue WHERE status='in_consultation' AND id<>? LIMIT 16",
                        (str(queue_id),),
                    ).fetchall()
                    if any(not _is_procedure(item["attention_type"]) for item in active_rows):
                        return False

                cur = conn.execute(
                    """UPDATE waiting_queue
                       SET status='in_consultation',
                           started_at=COALESCE(NULLIF(started_at,''),?),
                           updated_at=?
                       WHERE id=? AND status='waiting'""",
                    (stamp, stamp, str(queue_id)),
                )
                if not cur.rowcount:
                    return False

                try:
                    conn.execute(
                        """INSERT INTO audit_log(
                             occurred_at,actor,action,entity_type,entity_id,details_json
                           ) VALUES(?,?,?,?,?,?)""",
                        (
                            stamp,
                            "Dr. Armando Revelo",
                            "start_attention_on_open_chart",
                            "waiting_queue",
                            str(queue_id),
                            '{"source":"queue_chart_open","version":"1.3.95"}',
                        ),
                    )
                except sqlite3.Error:
                    pass
                conn.commit()
            _wake_sync()
            return True
        except sqlite3.OperationalError:
            if attempt >= 3:
                return False
            time.sleep(0.08 * (attempt + 1))
        except Exception:
            return False
    return False


def _install_on_app(app: FastAPI) -> None:
    if getattr(app.state, "queue_open_attention_installed", False):
        return
    app.state.queue_open_attention_installed = True

    @app.get("/api/v1395/queue-open-attention/health")
    def queue_open_attention_health():
        return {
            "ok": True,
            "version": PATCH_VERSION,
            "open_chart_starts_attention": True,
            "link_then_open_starts_attention": True,
            "idempotent": True,
            "search_patient_open_unchanged": True,
            "parallel_consultation_confirmation": True,
            "previous_attention_never_auto_completed": True,
            "procedures_tv_excluded": True,
        }

    @app.middleware("http")
    async def _queue_open_attention_middleware(request: Request, call_next):
        path = request.url.path
        open_match = _OPEN_RE.fullmatch(path)
        link_match = _LINK_RE.fullmatch(path)
        match = open_match or link_match
        if not match:
            return await call_next(request)

        queue_id = match.group(1)
        confirmed = str(request.query_params.get(_CONFIRM_PARAM) or "").strip() == "1"

        if not confirmed:
            context = _confirmation_context(queue_id, link_selected=bool(link_match))
            if context:
                return _render_confirmation(request, context)

        response = await call_next(request)

        # Start only after the existing route successfully resolves to a real
        # patient chart. Manual-link pages still do nothing until a ficha is chosen.
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = str(response.headers.get("location") or "")
        if not location.startswith("/paciente/"):
            return response

        try:
            started = _start_attention(queue_id, allow_parallel=confirmed)
            # Defensive race guard: if another consultation started between the
            # pre-check and this redirect, keep the target waiting and ask before
            # changing the TV instead of silently creating two active consults.
            if not started and not confirmed:
                target = _queue_context(queue_id)
                context = _confirmation_context(queue_id, link_selected=bool(link_match))
                if target and target.get("status") == "waiting" and context:
                    return _render_confirmation(request, context)
        except Exception:
            pass
        return response


def install_fastapi_hook() -> None:
    if getattr(FastAPI, "_queue_open_attention_hook", False):
        return
    FastAPI._queue_open_attention_hook = True
    original_init = FastAPI.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _install_on_app(self)
        except Exception:
            pass

    FastAPI.__init__ = patched_init
