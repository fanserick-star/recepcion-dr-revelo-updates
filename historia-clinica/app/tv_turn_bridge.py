from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from urllib.parse import urlsplit

import lan_bridge

_INSTALLED = False
_ORIGINAL_HANDLER_FACTORY = None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_procedure(value: object) -> bool:
    raw = " ".join(str(value or "").strip().upper().split())
    return bool(
        raw in {"P", "X", "PROCEDIMIENTO"}
        or raw.startswith("PROCEDIMIENTO ")
    )


def _safe_turn(value: object):
    try:
        turn = int(value)
        return turn if turn > 0 else None
    except Exception:
        return None


def _snapshot(db_path) -> dict:
    current = None
    waiting = []
    recent = []
    with sqlite3.connect(db_path, timeout=3) as conn:
        conn.row_factory = sqlite3.Row
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(waiting_queue)").fetchall()}
        turn_expr = "reception_turn" if "reception_turn" in cols else "NULL AS reception_turn"
        started_expr = "started_at" if "started_at" in cols else "NULL AS started_at"
        completed_expr = "completed_at" if "completed_at" in cols else "NULL AS completed_at"
        rows = conn.execute(
            f"""
            SELECT id,status,attention_type,queued_at,updated_at,
                   {turn_expr},{started_expr},{completed_expr}
            FROM waiting_queue
            WHERE status IN ('waiting','in_consultation','completed','cancelled')
            ORDER BY COALESCE(updated_at,queued_at,'') DESC, id DESC
            LIMIT 120
            """
        ).fetchall()

    consultations = [row for row in rows if not _is_procedure(row["attention_type"])]
    in_consultation = [row for row in consultations if str(row["status"] or "") == "in_consultation"]
    if in_consultation:
        in_consultation.sort(
            key=lambda row: (
                str(row["started_at"] or row["updated_at"] or row["queued_at"] or ""),
                str(row["id"]),
            ),
            reverse=True,
        )
        row = in_consultation[0]
        current = {
            "queue_id": str(row["id"]),
            "turn": _safe_turn(row["reception_turn"]),
            "status": "in_consultation",
            "started_at": str(row["started_at"] or row["updated_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    waiting_rows = [row for row in consultations if str(row["status"] or "") == "waiting"]
    waiting_rows.sort(
        key=lambda row: (
            _safe_turn(row["reception_turn"]) is None,
            _safe_turn(row["reception_turn"]) or 999999,
            str(row["queued_at"] or row["updated_at"] or ""),
            str(row["id"]),
        )
    )
    for row in waiting_rows:
        waiting.append(
            {
                "queue_id": str(row["id"]),
                "turn": _safe_turn(row["reception_turn"]),
                "status": "waiting",
                "queued_at": str(row["queued_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
        )

    for row in consultations[:40]:
        recent.append(
            {
                "queue_id": str(row["id"]),
                "turn": _safe_turn(row["reception_turn"]),
                "status": str(row["status"] or ""),
                "updated_at": str(row["updated_at"] or ""),
                "completed_at": str(row["completed_at"] or ""),
            }
        )

    return {
        "ok": True,
        "product": "historia-clinica-dr-revelo",
        "generated_at": _now(),
        "current": current,
        "waiting": waiting,
        "waiting_count": len(waiting),
        "recent": recent,
        "procedures_excluded": True,
    }


def install() -> None:
    global _INSTALLED, _ORIGINAL_HANDLER_FACTORY
    if _INSTALLED:
        return
    _INSTALLED = True

    original = lan_bridge.LanService._handler_class
    _ORIGINAL_HANDLER_FACTORY = original

    def _handler_class_with_tv(self):
        base_handler = original(self)
        service = self

        class Handler(base_handler):
            def _tv_send_json(self, status: int, payload: dict) -> None:
                raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except Exception:
                    pass

            def do_GET(self):
                path = urlsplit(self.path).path
                if path != "/tv-state":
                    return super().do_GET()

                remote_ip = str(self.client_address[0] if self.client_address else "")
                token = str(self.headers.get("X-Historia-LAN-Token") or "")
                if not service._valid_token(remote_ip, token):
                    self._tv_send_json(403, {"ok": False, "error": "token_invalid"})
                    return

                try:
                    service._touch_reception(remote_ip)
                    payload = _snapshot(service.db_path)
                    payload["version"] = str(service.app_version)
                    self._tv_send_json(200, payload)
                except Exception as exc:
                    self._tv_send_json(
                        500,
                        {"ok": False, "error": type(exc).__name__, "generated_at": _now()},
                    )

        return Handler

    lan_bridge.LanService._handler_class = _handler_class_with_tv
