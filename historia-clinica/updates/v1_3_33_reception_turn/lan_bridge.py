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
        patient_status = _clean(payload.get("patient_status"), 40)
        try:
            reception_turn = int(payload.get("reception_turn")) if payload.get("reception_turn") not in (None, "") else None
        except Exception:
            reception_turn = None
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
            queue_columns = {
                str(r[1]) for r in conn.execute("PRAGMA table_info(waiting_queue)").fetchall()
            }
            has_patient_status = "patient_status" in queue_columns
            has_reception_turn = "reception_turn" in queue_columns
            if existing:
                if has_patient_status and has_reception_turn:
                    conn.execute(
                        """
                        UPDATE waiting_queue SET
                          reception_patient_id=?,
                          clinical_patient_id=COALESCE(clinical_patient_id,?),
                          display_name=?,
                          identification=?,
                          attention_type=?,
                          patient_status=?,
                          reception_turn=?,
                          updated_at=?
                        WHERE reception_event_id=?
                        """,
                        (
                            reception_patient_id,
                            clinical_id,
                            display_name,
                            identification or None,
                            attention_type,
                            patient_status or None,
                            reception_turn,
                            stamp,
                            event_id,
                        ),
                    )
                elif has_patient_status:
                    conn.execute(
                        """
                        UPDATE waiting_queue SET
                          reception_patient_id=?,
                          clinical_patient_id=COALESCE(clinical_patient_id,?),
                          display_name=?,
                          identification=?,
                          attention_type=?,
                          patient_status=?,
                          updated_at=?
                        WHERE reception_event_id=?
                        """,
                        (
                            reception_patient_id,
                            clinical_id,
                            display_name,
                            identification or None,
                            attention_type,
                            patient_status or None,
                            stamp,
                            event_id,
                        ),
                    )
                else:
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
                if has_patient_status and has_reception_turn:
                    conn.execute(
                        """
                        INSERT INTO waiting_queue(
                          id,reception_event_id,reception_patient_id,clinical_patient_id,
                          display_name,identification,attention_type,patient_status,reception_turn,queued_at,status,
                          source,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            queue_id,
                            event_id,
                            reception_patient_id,
                            clinical_id,
                            display_name,
                            identification or None,
                            attention_type,
                            patient_status or None,
                            reception_turn,
                            queued_at,
                            "waiting",
                            "reception",
                            stamp,
                            stamp,
                        ),
                    )
                elif has_patient_status:
                    conn.execute(
                        """
                        INSERT INTO waiting_queue(
                          id,reception_event_id,reception_patient_id,clinical_patient_id,
                          display_name,identification,attention_type,patient_status,queued_at,status,
                          source,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            queue_id,
                            event_id,
                            reception_patient_id,
                            clinical_id,
                            display_name,
                            identification or None,
                            attention_type,
                            patient_status or None,
                            queued_at,
                            "waiting",
                            "reception",
                            stamp,
                            stamp,
                        ),
                    )
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
        self._last_error = ""
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

    def accept_cancel(self, payload: dict, remote_ip: str) -> dict:
        event_id = _clean(payload.get("event_id") or payload.get("target_event_id"), 180)
        if not event_id:
            raise ValueError("Falta event_id del turno")
        stamp = _now()
        protected = False
        removed_drafts = 0
        queue_id = ""

        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            row = conn.execute(
                "SELECT id,status FROM waiting_queue WHERE reception_event_id=? LIMIT 1",
                (event_id,),
            ).fetchone()
            if row:
                queue_id = str(row["id"])
                signed = int(conn.execute(
                    """SELECT COUNT(*) FROM encounters
                       WHERE queue_id=? AND note_status IN ('signed','legacy')""",
                    (queue_id,),
                ).fetchone()[0])
                if row["status"] == "completed" or signed > 0:
                    protected = True
                else:
                    drafts = conn.execute(
                        "SELECT id FROM encounters WHERE queue_id=? AND note_status='draft'",
                        (queue_id,),
                    ).fetchall()
                    # v1.3.24: jamás borrar texto clínico por una cancelación
                    # administrativa. El borrador queda recuperable, solo se
                    # separa del turno cancelado.
                    for draft in drafts:
                        conn.execute(
                            "UPDATE encounters SET queue_id=NULL,updated_at=? "
                            "WHERE id=? AND note_status='draft'",
                            (stamp, draft["id"]),
                        )
                    removed_drafts = 0
                    conn.execute(
                        """UPDATE waiting_queue
                           SET status='cancelled',updated_at=?
                           WHERE id=? AND status IN ('waiting','in_consultation')""",
                        (stamp, queue_id),
                    )
                    try:
                        conn.execute(
                            """INSERT INTO audit_log(
                                 occurred_at,actor,action,entity_type,entity_id,details_json
                               ) VALUES(?,?,?,?,?,?)""",
                            (
                                stamp,
                                "Recepción",
                                "cancel_from_reception",
                                "waiting_queue",
                                queue_id,
                                json.dumps(
                                    {"event_id": event_id, "removed_drafts": removed_drafts},
                                    ensure_ascii=False,
                                ),
                            ),
                        )
                    except sqlite3.Error:
                        pass
                    conn.commit()

        self._last_error = ""
        self._touch_reception(remote_ip)
        try:
            if self.sync_service is not None:
                self.sync_service.mark_activity()
                self.sync_service.wake()
        except Exception:
            pass
        return {
            "ok": True,
            "event_id": event_id,
            "queue_id": queue_id,
            "cancelled": bool(queue_id and not protected),
            "protected_signed_history": protected,
            "removed_drafts": removed_drafts,
        }

    def accept_restore(self, payload: dict, remote_ip: str) -> dict:
        event_id = _clean(payload.get("event_id") or payload.get("target_event_id"), 180)
        if not event_id:
            raise ValueError("Falta event_id del turno")
        stamp = _now()
        queue_id = ""
        restored = False
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id,status FROM waiting_queue WHERE reception_event_id=? LIMIT 1",
                (event_id,),
            ).fetchone()
            if row:
                queue_id = str(row["id"])
                if row["status"] == "cancelled":
                    conn.execute(
                        "UPDATE waiting_queue SET status='waiting',updated_at=? WHERE id=?",
                        (stamp, queue_id),
                    )
                    conn.commit()
                    restored = True
        self._touch_reception(remote_ip)
        try:
            if self.sync_service is not None:
                self.sync_service.mark_activity()
                self.sync_service.wake()
        except Exception:
            pass
        return {"ok": True, "event_id": event_id, "queue_id": queue_id, "restored": restored}

    def status(self) -> dict:
        return {
            "ok": self._httpd is not None,
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
                if path not in {"/handoff", "/cancel", "/restore"}:
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
                    if path == "/cancel":
                        result = service.accept_cancel(payload, self.remote_ip)
                    elif path == "/restore":
                        result = service.accept_restore(payload, self.remote_ip)
                    else:
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


# v1.3.2 — enriquece pacientes NUEVOS con datos administrativos de Recepción.
_v132_accept_handoff_original = LanService.accept_handoff

def _v132_is_new_attention(value) -> bool:
    return str(value or "").strip().upper() in {"N", "NUEVO"}

def _v132_patient_id(reception_patient_id: str) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "historia-reception-patient:" + str(reception_patient_id or "").strip(),
    ))

def _v132_name_search(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())

def _v132_enrich_new_patient(self, payload: dict) -> str:
    reception_patient_id = _clean(payload.get("reception_patient_id"), 120)
    patient_status = _clean(payload.get("patient_status"), 40)
    is_new = _v132_is_new_attention(patient_status) if patient_status else _v132_is_new_attention(payload.get("attention_type"))
    if not reception_patient_id or not is_new:
        return ""

    name = re.sub(r"\s+", " ", _clean(payload.get("display_name"), 260)).strip().upper()
    if not name:
        return ""

    identification = _clean(payload.get("identification"), 120)
    ident_search = _normalize_id(identification)
    birth_date = _clean(payload.get("birth_date"), 20)
    phone = _clean(payload.get("phone"), 80)
    email = _clean(payload.get("email"), 180).lower()
    address = _clean(payload.get("address"), 360)
    event_id = _clean(payload.get("event_id"), 180)
    stamp = _now()

    with sqlite3.connect(self.db_path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        link = conn.execute(
            "SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id=? LIMIT 1",
            (reception_patient_id,),
        ).fetchone()
        patient_id = str(link["clinical_patient_id"] or "").strip() if link else ""

        if not patient_id and ident_search:
            exact = conn.execute(
                "SELECT id FROM patients WHERE national_id_search=? LIMIT 2",
                (ident_search,),
            ).fetchall()
            if len(exact) == 1:
                patient_id = str(exact[0]["id"])

        if not patient_id:
            patient_id = _v132_patient_id(reception_patient_id)

        source_hash = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "historia-reception-demographics:" + reception_patient_id,
        ).hex

        conn.execute(
            """INSERT OR IGNORE INTO patients(
                 id,legacy_patient_id,name,name_search,birth_date,address,phone,
                 national_id,national_id_search,email,source,source_record_hash,
                 created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                patient_id, None, name, _v132_name_search(name), birth_date or None,
                address or None, phone or None, identification or None,
                ident_search if identification else "", email or None,
                "reception_new", source_hash, stamp, stamp,
            ),
        )
        conn.execute(
            """UPDATE patients SET
                 name=CASE WHEN TRIM(COALESCE(name,''))='' THEN ? ELSE name END,
                 name_search=CASE WHEN TRIM(COALESCE(name_search,''))='' THEN ? ELSE name_search END,
                 birth_date=CASE WHEN TRIM(COALESCE(birth_date,''))='' THEN ? ELSE birth_date END,
                 address=CASE WHEN TRIM(COALESCE(address,''))='' THEN ? ELSE address END,
                 phone=CASE WHEN TRIM(COALESCE(phone,''))='' THEN ? ELSE phone END,
                 national_id=CASE WHEN TRIM(COALESCE(national_id,''))='' THEN ? ELSE national_id END,
                 national_id_search=CASE WHEN TRIM(COALESCE(national_id_search,''))='' THEN ? ELSE national_id_search END,
                 email=CASE WHEN TRIM(COALESCE(email,''))='' THEN ? ELSE email END,
                 updated_at=?
               WHERE id=?""",
            (
                name, _v132_name_search(name), birth_date or None, address or None,
                phone or None, identification or None,
                ident_search if identification else "", email or None,
                stamp, patient_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO patient_links(
              reception_patient_id,clinical_patient_id,matched_by,verified,
              verified_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(reception_patient_id) DO UPDATE SET
              clinical_patient_id=excluded.clinical_patient_id,
              matched_by=CASE
                WHEN patient_links.matched_by='doctor_confirmed_new'
                THEN patient_links.matched_by
                ELSE excluded.matched_by
              END,
              verified=1,
              verified_at=excluded.verified_at,
              updated_at=excluded.updated_at
            """,
            (
                reception_patient_id, patient_id, "lan_new_demographics", 1,
                stamp, stamp, stamp,
            ),
        )
        if event_id:
            conn.execute(
                """UPDATE waiting_queue
                   SET clinical_patient_id=?,display_name=?,identification=?,updated_at=?
                   WHERE reception_event_id=?""",
                (patient_id, name, identification or None, stamp, event_id),
            )
        conn.commit()

    try:
        if self.sync_service is not None:
            self.sync_service.mark_activity()
            self.sync_service.wake()
    except Exception:
        pass
    return patient_id

def _v132_accept_handoff(self, payload: dict, remote_ip: str) -> dict:
    result = _v132_accept_handoff_original(self, payload, remote_ip)
    try:
        patient_id = _v132_enrich_new_patient(self, payload)
        if patient_id:
            result["clinical_patient_id"] = patient_id
            result["demographics_received"] = True
    except Exception as exc:
        result["demographics_received"] = False
        result["demographics_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return result

LanService.accept_handoff = _v132_accept_handoff
