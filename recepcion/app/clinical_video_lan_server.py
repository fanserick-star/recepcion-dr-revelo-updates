"""Isolated, HMAC-only video LAN server on Reception's private network.

Never expose the entire Reception web application to the doctor's PC: only
the two authenticated GET video routes are served on a dedicated port.
Patient identity and archived MP4 bytes remain solely in Reception.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import clinical_video_library as videos

_RULE = "DrRevelo-Video-Privado-Recepcion"
_RANGE = re.compile(r"bytes=(\d+)-(\d*)|bytes=-(\d+)")
_MAX_BYTES = 512 * 1024
DEFAULT_PORT = 8766


def _port():
    raw = str(os.getenv("RP_VIDEO_PORT") or str(DEFAULT_PORT)).strip()
    try:
        parsed = int(raw)
        if parsed < 1024 or parsed > 65535:
            raise ValueError()
        return parsed
    except ValueError:
        return DEFAULT_PORT


class PrivateVideoLanServer:
    def __init__(self):
        self.port = _port()
        self.httpd = None
        self.thread = None
        self.error = ""
        self._lock = threading.Lock()
        self._clients = threading.BoundedSemaphore(5)

    def start(self):
        with self._lock:
            if self.httpd is not None:
                return
            parent = self

            class Handler(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"
                server_version = "ReveloPrivateVideo/1"

                def log_message(self, _format, *_args):
                    # Never log the HMAC query, patient ID or MP4 filename.
                    return

                def _headers(self, code, length, mime="application/json", extra=None):
                    self.send_response(code)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(length))
                    self.send_header("Cache-Control", "private, no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Connection", "close")
                    for key, val in (extra or {}).items():
                        self.send_header(key, str(val))
                    self.end_headers()
                    self.close_connection = True

                def _json(self, status, info):
                    data = json.dumps(info, ensure_ascii=False,
                                      separators=(",", ":")).encode("utf-8")
                    self._headers(status, len(data))
                    self.wfile.write(data)

                def do_GET(self):
                    if not parent._clients.acquire(blocking=False):
                        self._json(503, {"ok": False, "error": "Reproductor ocupado"})
                        return
                    try:
                        self._serve_video_request()
                    finally:
                        parent._clients.release()

                def do_POST(self):
                    self._json(405, {"ok": False, "error": "Método no permitido"})

                def do_HEAD(self):
                    self._json(405, {"ok": False, "error": "Método no permitido"})

                def _serve_video_request(self):
                    try:
                        if len(self.path) > 650:
                            self._json(414, {"ok": False, "error": "Petición inválida"})
                            return
                        parts = urlsplit(self.path)
                        query = parse_qs(parts.query, strict_parsing=False)
                        clinical_id = str(query.get("clinical_id", [""])[0])
                        v_id = "-"
                        action = ""
                        if parts.path == "/api/clinical-videos/lan/catalog":
                            action = "catalog"
                        elif re.fullmatch(r"/api/clinical-videos/lan/stream/[A-Za-z0-9_-]{1,100}", parts.path):
                            action = "stream"
                            v_id = parts.path.rsplit("/", 1)[-1]
                        else:
                            # No access to any other Reception or patient routes.
                            self._json(404, {"ok": False, "error": "No encontrado"})
                            return
                        request = SimpleNamespace(
                            client=SimpleNamespace(host=self.client_address[0]),
                            query_params={k: v[0] for k, v in query.items()})
                        try:
                            videos._verify_lan(request, action, clinical_id, v_id)
                        except Exception:
                            self._json(403, {"ok": False, "error": "Autorización LAN clínica inválida"})
                            return
                        if action == "catalog":
                            records = videos._records(clinical_id)
                            self._json(200, {"ok": True, "videos": records})
                            return
                        record = videos._row_by_id(v_id, clinical_id)
                        source = videos._local_file(record)
                        self._stream(source)
                    except (OSError, ValueError, FileNotFoundError):
                        self._json(503, {"ok": False, "error": "El archivo original no está disponible"})
                    except Exception as exc:
                        # Do not leak SQLite, file paths, secrets or clinical IDs.
                        status = int(getattr(exc, "status_code", 503) or 503)
                        if status not in (403, 404, 416, 503):
                            status = 503
                        self._json(status, {"ok": False, "error":
                            "Archivo no encontrado" if status == 404 else "No se pudo consultar el video"})

                def _stream(self, source: Path):
                    total = source.stat().st_size
                    if total < 1:
                        self._json(503, {"ok": False, "error": "Archivo vacío"})
                        return
                    raw = str(self.headers.get("Range") or "").strip()
                    start, end, code = 0, total - 1, 200
                    if raw:
                        match = _RANGE.fullmatch(raw)
                        if not match:
                            self._headers(416, 0, "text/plain", {"Content-Range": f"bytes */{total}"})
                            return
                        if match.group(3):
                            last = int(match.group(3))
                            if last <= 0:
                                self._headers(416, 0, "text/plain", {"Content-Range": f"bytes */{total}"})
                                return
                            start = max(0, total - last)
                        else:
                            start = int(match.group(1))
                            if match.group(2):
                                end = min(total - 1, int(match.group(2)))
                        if start >= total or start > end:
                            self._headers(416, 0, "text/plain", {"Content-Range": f"bytes */{total}"})
                            return
                        code = 206
                    length = end - start + 1
                    extras = {"Accept-Ranges": "bytes"}
                    if code == 206:
                        extras["Content-Range"] = f"bytes {start}-{end}/{total}"
                    self._headers(code, length, "video/mp4", extras)
                    with source.open("rb") as stream:
                        stream.seek(start)
                        left = length
                        while left:
                            chunk = stream.read(min(left, _MAX_BYTES))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            left -= len(chunk)

            try:
                server = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
                server.daemon_threads = True
                self.httpd = server
                self.thread = threading.Thread(target=server.serve_forever,
                                               name="clinical-video-private-lan", daemon=True)
                self.thread.start()
                self.error = ""
            except OSError as exc:
                self.error = type(exc).__name__
                self.httpd = None

    def stop(self):
        with self._lock:
            if self.httpd:
                self.httpd.shutdown()
                self.httpd.server_close()
            self.httpd = None

    def firewall_present(self):
        if os.name != "nt":
            return None
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={_RULE}"],
                capture_output=True, text=True, errors="ignore", timeout=5,
                creationflags=flags)
            return result.returncode == 0 and _RULE.lower() in (result.stdout or "").lower()
        except Exception:
            return None

    def status(self):
        return {
            "ready": self.httpd is not None,
            "port": self.port,
            "firewall_rule": self.firewall_present(),
            "error": self.error or "",
            "isolated_video_only": True,
        }

    def request_firewall_repair(self):
        if os.name != "nt":
            return {"ok": False, "message": "El permiso de Windows solo se configura en Windows."}
        # Only explicit click in Reception UI. Requires Windows UAC approval.
        # Restricted to PRIVATE network / local subnet; never port 8000.
        path = videos.BASE / "REPARAR_LAN_VIDEOS_RECEPCION.cmd"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "@echo off\r\n"
                f'netsh advfirewall firewall show rule name="{_RULE}" >nul 2>&1\r\n'
                "if errorlevel 1 (\r\n"
                f' netsh advfirewall firewall add rule name="{_RULE}" dir=in action=allow '
                f'protocol=TCP localport={self.port} profile=private remoteip=localsubnet\r\n'
                ")\r\n", encoding="utf-8")
            escaped = str(path).replace("'", "''")
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-Command", f"Start-Process -FilePath '{escaped}' -Verb RunAs -Wait"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, cwd=str(path.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"ok": True,
                    "message": "Windows solicitará permiso para habilitar exclusivamente el puerto privado de videos. Después vuelve a comprobar."}
        except Exception:
            return {"ok": False, "message": "No se pudo solicitar el permiso de red privada a Windows."}


service = PrivateVideoLanServer()


def install(app):
    from fastapi import Request
    import core_runtime as core

    @app.on_event("startup")
    def start_private_video_server():
        service.start()

    @app.on_event("shutdown")
    def stop_private_video_server():
        service.stop()

    @app.get("/api/clinical-videos/lan-status")
    def video_lan_status(request: Request, user=core.Depends(core.current_user)):
        if str(request.client.host) not in ("127.0.0.1", "::1"):
            raise core.HTTPException(403, "Solo desde Recepción")
        return service.status()

    @app.post("/api/clinical-videos/lan-firewall")
    def video_lan_firewall(request: Request, user=core.Depends(core.current_user)):
        if str(request.client.host) not in ("127.0.0.1", "::1"):
            raise core.HTTPException(403, "Solo desde Recepción")
        return service.request_firewall_repair()
