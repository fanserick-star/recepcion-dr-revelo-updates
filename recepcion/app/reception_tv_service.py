from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

import historia_lan_transport
from reception_tv_common import APP_VERSION, DATA_DIR, PORT, VIDEOS_DIR, _epoch, _lan_ip, _now_iso
from reception_tv_media import TVMediaMixin


class TVTurnService(TVMediaMixin):
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.httpd = None
        self.http_thread = None
        self.poll_thread = None
        self.stop_event = threading.Event()
        self.started_at = ""
        self.start_error = ""
        self.history_error = ""
        self.last_history_seen_epoch = 0.0
        self.last_tv_seen_epoch = 0.0
        self.last_test_tv_seen_epoch = 0.0
        self.config = self._load_config()
        self.live = {
            "mode": "idle",
            "turn": None,
            "waiting_count": 0,
            "event_id": 0,
            "sound": True,
            "sound_test": False,
            "current_queue_id": "",
            "called_queue_id": "",
            "history_online": False,
            "history_host": "",
            "history_last_seen": "",
            "attention_started_epoch": 0.0,
            "calling_started_epoch": 0.0,
            "last_change": _now_iso(),
        }
        self.test = {
            "mode": "idle",
            "turn": 1,
            "waiting_count": 0,
            "event_id": 0,
            "sound": True,
            "sound_test": False,
            "attention_started_epoch": 0.0,
            "last_change": _now_iso(),
        }

    def live_snapshot(self, *, touch_tv: bool = False) -> dict:
        if touch_tv:
            self.last_tv_seen_epoch = _epoch()
        with self.lock:
            out = dict(self.live)
            out["history_online"] = bool(
                out.get("history_online") and (_epoch() - self.last_history_seen_epoch) < 12
            )
            out["history_age_seconds"] = (
                max(0.0, _epoch() - self.last_history_seen_epoch)
                if self.last_history_seen_epoch
                else None
            )
            out["tv_online"] = bool(self.last_tv_seen_epoch and _epoch() - self.last_tv_seen_epoch < 8)
            out["advertising"] = self._advertising_allowed(out)
            out["video_count"] = len(self.video_items())
            out["server_port"] = PORT
            out["tv_url"] = f"http://{_lan_ip()}:{PORT}/TV"
            out["control_url"] = f"http://127.0.0.1:{PORT}/control"
            out["version"] = APP_VERSION
            out["procedures_excluded"] = True
            return out

    def test_snapshot(self, *, touch_tv: bool = False) -> dict:
        if touch_tv:
            self.last_test_tv_seen_epoch = _epoch()
        with self.lock:
            out = dict(self.test)
            out["advertising"] = self._advertising_allowed(out)
            out["tv_online"] = bool(self.last_test_tv_seen_epoch and _epoch() - self.last_test_tv_seen_epoch < 8)
            out["video_count"] = len(self.video_items())
            out["server_port"] = PORT
            out["tv_url"] = f"http://{_lan_ip()}:{PORT}/TV-PRUEBAS"
            out["version"] = APP_VERSION
            return out

    def _history_state(self) -> dict:
        state = historia_lan_transport._snapshot()
        if not state.get("lan_online") or not state.get("lan_host") or not state.get("token"):
            state = historia_lan_transport.probe_once()
        host = str(state.get("lan_host") or "")
        token = str(state.get("token") or "")
        if not host or not token:
            raise RuntimeError("Historia no respondió en la red local")
        try:
            result = historia_lan_transport._http_json(
                host,
                "/tv-state",
                token=token,
                timeout=1.15,
            )
        except Exception:
            state = historia_lan_transport.probe_once()
            host = str(state.get("lan_host") or "")
            token = str(state.get("token") or "")
            if not host or not token:
                raise
            result = historia_lan_transport._http_json(
                host,
                "/tv-state",
                token=token,
                timeout=1.15,
            )
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or "Historia rechazó el estado de TV"))
        result["host"] = host
        return result

    def _recent_status(self, payload: dict, queue_id: str) -> str:
        if not queue_id:
            return ""
        for item in payload.get("recent") or []:
            if str(item.get("queue_id") or "") == str(queue_id):
                return str(item.get("status") or "")
        return ""

    def apply_history(self, payload: dict) -> None:
        now = _epoch()
        current = payload.get("current") if isinstance(payload.get("current"), dict) else None
        waiting = [x for x in (payload.get("waiting") or []) if isinstance(x, dict)]
        waiting = [x for x in waiting if x.get("turn") not in (None, "")]
        waiting_count = len(waiting)
        with self.lock:
            prev_current_id = str(self.live.get("current_queue_id") or "")
            called_id = str(self.live.get("called_queue_id") or "")
            self.live["history_online"] = True
            self.live["history_host"] = str(payload.get("host") or "")
            self.live["history_last_seen"] = _now_iso()
            self.live["waiting_count"] = waiting_count
            self.last_history_seen_epoch = now
            self.history_error = ""

            if current and current.get("turn") not in (None, ""):
                current_id = str(current.get("queue_id") or "")
                turn = int(current.get("turn"))
                changed = (
                    self.live.get("mode") != "attending"
                    or prev_current_id != current_id
                    or int(self.live.get("turn") or 0) != turn
                )
                self.live["mode"] = "attending"
                self.live["turn"] = turn
                self.live["current_queue_id"] = current_id
                self.live["called_queue_id"] = ""
                if changed:
                    self.live["sound_test"] = False
                    self.live["event_id"] = int(self.live.get("event_id") or 0) + 1
                    self.live["attention_started_epoch"] = now
                    self.live["last_change"] = _now_iso()
                elif not self.live.get("attention_started_epoch"):
                    self.live["attention_started_epoch"] = now
                return

            if prev_current_id:
                finished_status = self._recent_status(payload, prev_current_id)
                self.live["current_queue_id"] = ""
                self.live["attention_started_epoch"] = 0.0
                if finished_status == "completed" and waiting:
                    nxt = waiting[0]
                    self.live["mode"] = "calling"
                    self.live["turn"] = int(nxt["turn"])
                    self.live["called_queue_id"] = str(nxt.get("queue_id") or "")
                    self.live["event_id"] = int(self.live.get("event_id") or 0) + 1
                    self.live["calling_started_epoch"] = now
                    self.live["sound_test"] = False
                    self.live["last_change"] = _now_iso()
                else:
                    self.live["mode"] = "idle"
                    self.live["turn"] = None
                    self.live["called_queue_id"] = ""
                    self.live["calling_started_epoch"] = 0.0
                    self.live["sound_test"] = False
                    self.live["last_change"] = _now_iso()
                return

            if called_id:
                still_waiting = next(
                    (x for x in waiting if str(x.get("queue_id") or "") == called_id),
                    None,
                )
                if still_waiting:
                    self.live["mode"] = "calling"
                    self.live["turn"] = int(still_waiting["turn"])
                    return
                self.live["called_queue_id"] = ""
                self.live["mode"] = "idle"
                self.live["turn"] = None
                self.live["calling_started_epoch"] = 0.0
                self.live["last_change"] = _now_iso()
                return

            self.live["mode"] = "idle"
            self.live["turn"] = None

    def mark_history_offline(self, exc: Exception) -> None:
        with self.lock:
            self.live["history_online"] = False
            self.history_error = f"{type(exc).__name__}: {str(exc)[:160]}"

    def poll_loop(self) -> None:
        while not self.stop_event.wait(0.9):
            try:
                self.apply_history(self._history_state())
            except Exception as exc:
                self.mark_history_offline(exc)

    def set_test(self, data: dict) -> dict:
        with self.lock:
            mode = str(data.get("mode") or self.test.get("mode") or "idle")
            if mode not in {"idle", "calling", "attending"}:
                mode = "idle"
            turn = max(1, min(999, int(data.get("turn") or self.test.get("turn") or 1)))
            waiting = max(
                0,
                min(
                    99,
                    int(
                        data.get("waiting_count")
                        if data.get("waiting_count") is not None
                        else self.test.get("waiting_count") or 0
                    ),
                ),
            )
            changed = mode != self.test.get("mode") or turn != self.test.get("turn")
            self.test["mode"] = mode
            self.test["turn"] = turn
            self.test["waiting_count"] = waiting
            self.test["sound"] = bool(data.get("sound", self.test.get("sound", True)))
            self.test["sound_test"] = bool(data.get("sound_test", False))
            if changed or mode == "calling" or self.test["sound_test"]:
                self.test["event_id"] = int(self.test.get("event_id") or 0) + 1
                self.test["last_change"] = _now_iso()
            if mode == "attending" and (changed or not self.test.get("attention_started_epoch")):
                self.test["attention_started_epoch"] = _epoch()
            elif mode != "attending":
                self.test["attention_started_epoch"] = 0.0
            return self.test_snapshot()

    def finish_test(self) -> dict:
        with self.lock:
            turn = int(self.test.get("turn") or 1)
            waiting = int(self.test.get("waiting_count") or 0)
        if waiting > 0:
            return self.set_test(
                {"mode": "calling", "turn": turn + 1, "waiting_count": waiting - 1, "sound": True}
            )
        return self.set_test({"mode": "idle", "turn": turn, "waiting_count": 0, "sound": True})

    def recall_live(self) -> dict:
        with self.lock:
            turn = self.live.get("turn")
            if turn in (None, ""):
                raise ValueError("No hay un turno actual para volver a llamar")
            self.live["mode"] = "calling"
            self.live["event_id"] = int(self.live.get("event_id") or 0) + 1
            self.live["sound_test"] = False
            self.live["calling_started_epoch"] = _epoch()
            self.live["last_change"] = _now_iso()
            return self.live_snapshot()

    def test_sound_live(self) -> dict:
        with self.lock:
            self.live["event_id"] = int(self.live.get("event_id") or 0) + 1
            self.live["sound_test"] = True
            self.live["sound"] = True
            self.live["last_change"] = _now_iso()
            return self.live_snapshot()

    def start(self) -> None:
        with self.lock:
            if self.httpd is not None:
                return
            try:
                from reception_tv_http import build_handler

                server = ThreadingHTTPServer(("0.0.0.0", PORT), build_handler(self))
                server.daemon_threads = True
                server.allow_reuse_address = True
                self.httpd = server
                self.started_at = _now_iso()
                self.start_error = ""
            except OSError as exc:
                self.start_error = f"Puerto {PORT} ocupado o no disponible: {exc}"
                self.httpd = None
                return
            except Exception as exc:
                self.start_error = f"{type(exc).__name__}: {str(exc)[:180]}"
                self.httpd = None
                return

        self.http_thread = threading.Thread(
            target=self.httpd.serve_forever,
            daemon=True,
            name="reception-tv-http",
        )
        self.http_thread.start()
        self.poll_thread = threading.Thread(
            target=self.poll_loop,
            daemon=True,
            name="reception-tv-history-poll",
        )
        self.poll_thread.start()

    def status(self) -> dict:
        live = self.live_snapshot()
        return {
            "ok": self.httpd is not None,
            "started_at": self.started_at,
            "error": self.start_error,
            "port": PORT,
            "tv_url": live["tv_url"],
            "control_url": live["control_url"],
            "history_online": live["history_online"],
            "history_host": live.get("history_host") or "",
            "history_error": self.history_error,
            "tv_online": live["tv_online"],
            "mode": live.get("mode"),
            "turn": live.get("turn"),
            "waiting_count": live.get("waiting_count"),
            "advertising": live.get("advertising"),
            "version": APP_VERSION,
        }
