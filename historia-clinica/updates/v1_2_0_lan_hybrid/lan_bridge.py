from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

LAN_HTTP_PORT = 8765
LAN_DISCOVERY_PORT = 8766
DISCOVERY_MAGIC = b"HISTORIA_REVELO_DISCOVER_V1"
PRODUCT = "historia-clinica-dr-revelo"
RULE_TCP = "Historia Clinica Dr Revelo LAN TCP"
RULE_UDP = "Historia Clinica Dr Revelo LAN UDP"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _normalize_id(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _clean(value, 160).upper())


class LanService:
    def __init__(self, root: Path, db_path: Path, app_version: str, sync_service=None):
        self.root = Path(root)
        self.db_path = Path(db_path)
        self.app_version = str(app_version)
        self.sync_service = sync_service
        self._secret = os.urandom(32)
        self._httpd = None
        self._http_thread = None
        self._udp_thread = None
        self._stop = threading.Event()
        self._last_reception_seen = ""
        self._last_reception_ip = ""
        self._last_handoff_at = ""
        self._last_error = ""
        self._started_at = _now()

    def _token(self, ip: str, bucket: int | None = None) -> str:
        bucket = int(time.time() // 60) if bucket is None else int(bucket)
        msg = f"{ip}|{bucket}|{LAN_HTTP_PORT}".encode("utf-8")
        raw = hmac.new(self._secret, msg, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _valid_token(self, ip: str, token: str) -> bool:
        token = str(token or "")
        now_bucket = int(time.time() // 60)
        for bucket in (now_bucket, now_bucket - 1):
            if hmac.compare_digest(token, self._token(ip, bucket)):
                return True
        return False

    def _touch_reception(self, ip: str) -> None:
        self._last_reception_seen = _now()
        self._last_reception_ip = ip

    def _resolve_patient(self, conn: sqlite3.Connection, reception_patient_id: str, identification: str) -> str | None:
        try:
            row = conn.execute(
                "SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id=? LIMIT 1",
                (reception_patient_id,),
            ).fetchone()
            if row and row[0]:
                return str(row[0])
        except sqlite3.Error:
            pass

        ident = _normalize_id(identification)
        if not ident:
            return None

        rows = conn.execute(
            "SELECT id FROM patients WHERE national_id_search=? LIMIT 2",
            (ident,),
        ).fetchall()
        if len(rows) != 1:
            return None

        clinical_id = str(rows[0][0])
        stamp = _now()
        try:
            conn.execute(
                """
                INSERT INTO patient_links(
                  reception_patient_id,clinical_patient_id,matched_by,verified,
                  verified_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(reception_patient_id) DO UPDATE SET
                  clinical_patient_id=excluded.clinical_patient_id,
                  matched_by=excluded.matched_by,
                  verified=1,
                  verified_at=excluded.verified_at,
                  updated_at=excluded.updated_at
                """,
                (reception_patient_id, clinical_id, "lan_identification", 1, stamp, stamp, stamp),
            )
        except sqlite3.Error:
            pass
        return clinical_id

    def accept_handoff(self, payload: dict, remote_ip: str) -> dict:
        event_id = _clean(payload.get("event_id"), 180)
        reception_patient_id = _clean(payload.get("reception_patient_id"), 120)
        display_name = _clean(payload.get("display_name"), 260) or "Paciente"
        identification = _clean(payload.get("identification"), 120)
        attention_type = _clean(payload.get("attention_type"), 180) or "Consulta"
        queued_at = _clean(payload.get("queued_at"), 40) or _now()
        if not event_id or not reception_patient_id:
            raise ValueError("Faltan identificadores del turno")

        queue_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "historia-queue:" + event_id))
        stamp = _now()

        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            existing = conn.execute(
                "SELECT id,status,clinical_patient_id FROM waiting_queue WHERE reception_event_id=? LIMIT 1",
                (event_id,),
            ).fetchone()

            clinical_id = self._resolve_patient(conn, reception_patient_id, identification)
            if existing:
                conn.execute(
                    """
                    UPDATE waiting_queue SET
                      reception_patient_id=?,
                      clinical_patient_id=COALESCE(clinical_patient_id,?),
                      display_name=?,
                      identification=?,
                      attention_type=?,
                      updated_at=?
                    WHERE reception_event_id=?
                    """,
                    (
                        reception_patient_id,
                        clinical_id,
                        display_name,
                        identification or None,
                        attention_type,
                        stamp,
                        event_id,
                    ),
                )
                queue_id = str(existing["id"])
                duplicate = True
            else:
                conn.execute(
                    """
                    INSERT INTO waiting_queue(
                      id,reception_event_id,reception_patient_id,clinical_patient_id,
                      display_name,identification,attention_type,queued_at,status,
                      source,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        queue_id,
                        event_id,
                        reception_patient_id,
                        clinical_id,
                        display_name,
                        identification or None,
                        attention_type,
                        queued_at,
                        "waiting",
                        "reception",
                        stamp,
                        stamp,
                    ),
                )
                duplicate = False
            conn.commit()

        self._last_handoff_at = stamp
        self._touch_reception(remote_ip)
        try:
            if self.sync_service is not None:
                self.sync_service.mark_activity()
                self.sync_service.wake()
        except Exception:
            pass
        return {
            "ok": True,
            "queue_id": queue_id,
            "event_id": event_id,
            "duplicate": duplicate,
            "clinical_patient_id": clinical_id or "",
        }

    def status(self) -> dict:
        return {
            "ok": self._httpd is not None and not bool(self._last_error),
            "product": PRODUCT,
            "version": self.app_version,
            "port": LAN_HTTP_PORT,
            "discovery_port": LAN_DISCOVERY_PORT,
            "started_at": self._started_at,
            "last_reception_seen": self._last_reception_seen,
            "last_reception_ip": self._last_reception_ip,
            "last_handoff_at": self._last_handoff_at,
            "last_error": self._last_error,
            "firewall_rule": self.firewall_rule_present(),
        }

    def firewall_rule_present(self) -> bool | None:
        if os.name != "nt":
            return None
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.run(
                ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_TCP}"],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=5,
                creationflags=flags,
            )
            text = (out.stdout or "") + (out.stderr or "")
            return out.returncode == 0 and RULE_TCP.lower() in text.lower()
        except Exception:
            return None

    def request_firewall_repair(self) -> dict:
        if os.name != "nt":
            return {"ok": False, "message": "Disponible solo en Windows."}

        helper = self.root / "data" / "REPARAR_LAN_HISTORIA.cmd"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            "@echo off\r\n"
            f'netsh advfirewall firewall delete rule name="{RULE_TCP}" >nul 2>&1\r\n'
            f'netsh advfirewall firewall add rule name="{RULE_TCP}" dir=in action=allow protocol=TCP localport={LAN_HTTP_PORT} profile=private remoteip=localsubnet\r\n'
            f'netsh advfirewall firewall delete rule name="{RULE_UDP}" >nul 2>&1\r\n'
            f'netsh advfirewall firewall add rule name="{RULE_UDP}" dir=in action=allow protocol=UDP localport={LAN_DISCOVERY_PORT} profile=private remoteip=localsubnet\r\n',
            encoding="utf-8",
        )
        escaped = str(helper).replace("'", "''")
        command = f"Start-Process -FilePath '{escaped}' -Verb RunAs -Wait"
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                cwd=str(self.root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return {
                "ok": True,
                "message": "Windows pedirá permiso para habilitar Historia Clínica en la red privada.",
            }
        except Exception as exc:
            return {"ok": False, "message": f"No se pudo abrir el permiso de Windows: {type(exc).__name__}"}

    def _handler_class(self):
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "HistoriaReveloLAN/1"

            def log_message(self, *_args):
                return

            def _send(self, status: int, data: dict):
                raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)

            @property
            def remote_ip(self) -> str:
                return str(self.client_address[0] or "")

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == "/challenge":
                    service._touch_reception(self.remote_ip)
                    self._send(200, {
                        "ok": True,
                        "product": PRODUCT,
                        "version": service.app_version,
                        "token": service._token(self.remote_ip),
                        "port": LAN_HTTP_PORT,
                    })
                    return
                if path == "/health":
                    service._touch_reception(self.remote_ip)
                    self._send(200, {
                        "ok": True,
                        "product": PRODUCT,
                        "version": service.app_version,
                        "ready": True,
                    })
                    return
                self._send(404, {"ok": False})

            def do_POST(self):
                path = urlsplit(self.path).path
                if path != "/handoff":
                    self._send(404, {"ok": False})
                    return
                token = self.headers.get("X-Historia-LAN-Token", "")
                if not service._valid_token(self.remote_ip, token):
                    self._send(403, {"ok": False, "error": "token"})
                    return
                try:
                    length = min(32768, max(0, int(self.headers.get("Content-Length", "0") or "0")))
                    raw = self.rfile.read(length)
                    payload = json.loads(raw.decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("JSON inválido")
                    result = service.accept_handoff(payload, self.remote_ip)
                    self._send(200, result)
                except Exception as exc:
                    service._last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
                    self._send(400, {"ok": False, "error": str(exc)[:180]})

        return Handler

    def _udp_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", LAN_DISCOVERY_PORT))
            sock.settimeout(1.0)
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if data.strip() != DISCOVERY_MAGIC:
                    continue
                ip = str(addr[0] or "")
                self._touch_reception(ip)
                reply = json.dumps({
                    "product": PRODUCT,
                    "version": self.app_version,
                    "port": LAN_HTTP_PORT,
                    "token": self._token(ip),
                }, separators=(",", ":")).encode("utf-8")
                try:
                    sock.sendto(reply, addr)
                except OSError:
                    pass
        finally:
            try:
                sock.close()
            except Exception:
                pass

    def start(self):
        if self._http_thread and self._http_thread.is_alive():
            return
        self._stop.clear()
        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", LAN_HTTP_PORT), self._handler_class())
            self._httpd.daemon_threads = True
            self._last_error = ""
        except Exception as exc:
            self._httpd = None
            self._last_error = f"{type(exc).__name__}: {str(exc)[:180]}"
            return

        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.5},
            daemon=True,
            name="historia-lan-http",
        )
        self._udp_thread = threading.Thread(
            target=self._udp_loop,
            daemon=True,
            name="historia-lan-discovery",
        )
        self._http_thread.start()
        self._udp_thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self._httpd is not None:
                self._httpd.shutdown()
                self._httpd.server_close()
        except Exception:
            pass
        self._httpd = None


def install(app, root: Path, db_path: Path, app_version: str, sync_service=None):
    service = LanService(root, db_path, app_version, sync_service)

    @app.on_event("startup")
    def _start_lan_service():
        service.start()

    @app.on_event("shutdown")
    def _stop_lan_service():
        service.stop()

    @app.get("/api/lan/status")
    def api_lan_status():
        return service.status()

    @app.post("/api/system/lan-firewall")
    def api_lan_firewall():
        return service.request_firewall_repair()

    return service
