from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "historia_clinica.db"
PATCH_VERSION = "1.3.94"

_OPEN_RE = re.compile(r"^/cola/([^/]+)/atender/?$")
_LINK_RE = re.compile(r"^/cola/([^/]+)/vincular/[^/]+/?$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def _start_attention(queue_id: str) -> bool:
    """Mark one waiting item as in consultation exactly once.

    Idempotent by design: reopening the same chart does not change started_at,
    so the TV does not receive a second call for the same opening.
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
                            '{"source":"queue_chart_open","version":"1.3.94"}',
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

    @app.get("/api/v1394/queue-open-attention/health")
    def queue_open_attention_health():
        return {
            "ok": True,
            "version": PATCH_VERSION,
            "open_chart_starts_attention": True,
            "link_then_open_starts_attention": True,
            "idempotent": True,
            "search_patient_open_unchanged": True,
            "procedures_tv_excluded": True,
        }

    @app.middleware("http")
    async def _queue_open_attention_middleware(request: Request, call_next):
        path = request.url.path
        match = _OPEN_RE.fullmatch(path) or _LINK_RE.fullmatch(path)
        response = await call_next(request)
        if not match:
            return response

        # We only start attention after the existing route successfully resolves
        # to a real patient chart. If the route returns the manual-link page,
        # nothing changes until the doctor selects the correct ficha.
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = str(response.headers.get("location") or "")
        if not location.startswith("/paciente/"):
            return response

        try:
            _start_attention(match.group(1))
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
