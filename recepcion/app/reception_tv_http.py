from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

from reception_tv_common import (
    CONTROL_PATH,
    DISPLAY_PATH,
    LOGO_FULL,
    LOGO_ICON,
    VIDEOS_DIR,
    _DING,
    _allowed_lan,
    _clean_name,
    _is_loopback,
    _is_video_name,
)
from reception_tv_voice_selector import inject_control, inject_display


def build_handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DrReveloTV/1.2"

        def log_message(self, _format, *_args):
            return

        def _remote_ip(self) -> str:
            return str(self.client_address[0] if self.client_address else "")

        def _require_lan(self) -> bool:
            if _allowed_lan(self._remote_ip()):
                return True
            self._send_text(403, "Acceso disponible solo desde la red local")
            return False

        def _require_control(self) -> bool:
            if _is_loopback(self._remote_ip()):
                return True
            self._send_text(403, "El panel de control solo está disponible en la PC de Recepción")
            return False

        def _send(self, status: int, data: bytes, ctype: str, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send(status, data, "application/json; charset=utf-8")

        def _send_text(self, status: int, text: str) -> None:
            self._send(status, str(text).encode("utf-8"), "text/plain; charset=utf-8")

        def _json_body(self) -> dict:
            length = max(0, min(2_000_000, int(self.headers.get("Content-Length") or 0)))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                value = json.loads(raw.decode("utf-8"))
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}

        def do_GET(self):
            if not self._require_lan():
                return
            parts = urllib.parse.urlsplit(self.path)
            path = parts.path
            query = urllib.parse.parse_qs(parts.query)
            if path in {"/", "/control"}:
                if not self._require_control():
                    return
                if not CONTROL_PATH.is_file():
                    return self._send_text(503, "Panel TV no instalado")
                return self._send(200, inject_control(CONTROL_PATH.read_bytes()), "text/html; charset=utf-8")
            if path in {"/TV", "/TV-PRUEBAS"}:
                if not DISPLAY_PATH.is_file():
                    return self._send_text(503, "Pantalla TV no instalada")
                return self._send(200, inject_display(DISPLAY_PATH.read_bytes()), "text/html; charset=utf-8")
            if path == "/api/display-state":
                return self._send_json(200, service.display_snapshot(touch_tv=query.get("tv") == ["1"]))
            if path == "/api/live-state":
                return self._send_json(200, service.live_snapshot())
            if path == "/api/test-state":
                return self._send_json(200, service.test_snapshot())
            if path == "/api/voice-settings":
                if not self._require_control():
                    return
                return self._send_json(200, service.voice_settings())
            if path == "/api/videos":
                return self._send_json(200, service.video_config())
            if path == "/api/status":
                return self._send_json(200, service.status())
            if path == "/ding.wav":
                return self._send(200, _DING, "audio/wav", "public, max-age=3600")
            if path == "/assets/logo-full.png":
                if LOGO_FULL.is_file():
                    return self._send(200, LOGO_FULL.read_bytes(), "image/png", "public, max-age=3600")
                return self._send_text(404, "Logo no encontrado")
            if path == "/assets/logo-icon.png":
                if LOGO_ICON.is_file():
                    return self._send(200, LOGO_ICON.read_bytes(), "image/png", "public, max-age=3600")
                return self._send_text(404, "Icono no encontrado")
            if path.startswith("/media/"):
                return service._serve_media(self, path[len("/media/"):])
            return self._send_text(404, "No encontrado")

        def do_POST(self):
            if not self._require_lan():
                return
            parts = urllib.parse.urlsplit(self.path)
            path = parts.path
            query = urllib.parse.parse_qs(parts.query)

            # Única escritura permitida desde la TV: informar las voces que su navegador ofrece.
            # No modifica turnos, pacientes ni estados clínicos.
            if path == "/api/tv/voices":
                try:
                    return self._send_json(200, service.report_tv_voices(self._json_body()))
                except Exception as exc:
                    return self._send_json(400, {"ok": False, "error": str(exc)[:180]})

            if not self._require_control():
                return
            try:
                if path == "/api/display-mode":
                    data = self._json_body()
                    return self._send_json(200, service.set_display_mode(data.get("mode")))
                if path == "/api/test/set":
                    data = self._json_body()
                    if str(data.get("action") or "") == "finish":
                        return self._send_json(200, service.finish_test())
                    return self._send_json(200, service.set_test(data))
                if path == "/api/live/recall":
                    return self._send_json(200, service.recall_live())
                if path == "/api/live/test-sound":
                    return self._send_json(200, service.test_sound_live())
                if path == "/api/voice/settings":
                    return self._send_json(200, service.set_voice_settings(self._json_body()))
                if path == "/api/voice/test":
                    return self._send_json(200, service.trigger_voice_test(self._json_body()))
                if path == "/api/videos/settings":
                    data = self._json_body()
                    with service.lock:
                        if "enabled" in data:
                            service.config["videos_enabled"] = bool(data.get("enabled"))
                        if "volume" in data:
                            service.config["video_volume"] = max(
                                0.0, min(1.0, float(data.get("volume") or 0))
                            )
                        service._save_config()
                    return self._send_json(200, {"ok": True, **service.video_config()})
                if path == "/api/videos/upload":
                    name = urllib.parse.unquote((query.get("filename") or [""])[0])
                    return self._send_json(200, service._save_upload(self, name))
                if path == "/api/videos/delete":
                    name = _clean_name(urllib.parse.unquote((query.get("filename") or [""])[0]))
                    target = VIDEOS_DIR / name
                    if target.is_file() and _is_video_name(name):
                        target.unlink()
                    with service.lock:
                        service.config["video_order"] = [
                            x for x in service.config.get("video_order", []) if x != name
                        ]
                        service._save_config()
                    return self._send_json(200, {"ok": True})
                if path == "/api/videos/move":
                    data = self._json_body()
                    name = _clean_name(data.get("name"))
                    direction = -1 if int(data.get("direction") or 0) < 0 else 1
                    with service.lock:
                        order = [x["name"] for x in service.video_items()]
                        if name in order:
                            idx = order.index(name)
                            new = idx + direction
                            if 0 <= new < len(order):
                                order[idx], order[new] = order[new], order[idx]
                                service.config["video_order"] = order
                                service._save_config()
                    return self._send_json(200, {"ok": True})
                if path == "/api/firewall/repair":
                    return self._send_json(200, service.firewall_repair())
            except ValueError as exc:
                return self._send_json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                return self._send_json(
                    500,
                    {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"},
                )
            return self._send_text(404, "No encontrado")

    return Handler
