"""Read-only local Historia proxy for MP4 originals stored on Reception.

No MP4 in Historia SQLite/Neon, browser only communicates with local Historia.
Requests to Reception are HMAC authenticated and LAN IP restricted.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import queue
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_JSON_LIMIT = 256 * 1024

# Read ahead over the private LAN while the doctor's browser decodes prior
# chunks. 12 x 512 KiB = maximum 6 MiB of additional RAM per active stream.
# Unlike a full download, this leaves the original MP4 on Reception and
# supports byte Range seeks with their existing authenticated request.
_VIDEO_CHUNK_BYTES = 512 * 1024
_VIDEO_PREFETCH_CHUNKS = 12


def _buffered_video_body(upstream):
    pending = queue.Queue(maxsize=_VIDEO_PREFETCH_CHUNKS)
    cancelled = threading.Event()
    complete = object()

    def enqueue(value):
        while not cancelled.is_set():
            try:
                pending.put(value, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def read_ahead():
        try:
            while not cancelled.is_set():
                block = upstream.read(_VIDEO_CHUNK_BYTES)
                if not block:
                    break
                if not enqueue(block):
                    break
        except (OSError, ValueError):
            # An interrupted LAN transfer must not be disguised as success.
            # The browser can re-request remaining bytes using HTTP Range.
            logging.getLogger(__name__).warning(
                "Interrupción en la lectura LAN de un video clínico")
        finally:
            enqueue(complete)
            upstream.close()

    worker = threading.Thread(target=read_ahead, name="historia-video-lan-buffer", daemon=True)
    worker.start()
    try:
        while True:
            try:
                block = pending.get(timeout=0.5)
            except queue.Empty:
                if not worker.is_alive():
                    break
                continue
            if block is complete:
                break
            yield block
    finally:
        cancelled.set()
        # Don't block the History UI shutdown waiting for a network read.
        upstream.close()
        worker.join(timeout=0.1)


def install(app, root: Path, db_path: Path, lan_service):
    from cloud_sync import _load_env

    def _local_only(request):
        ip = str(getattr(request.client, "host", "") or "").lower()
        if ip not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(403, "Los videos clínicos se consultan solo desde esta PC")

    def _existing_patient(patient_id):
        """Read-only patient lookup compatible with older imported SQLite files.

        The base schema includes deleted_at, but migrated legacy databases may
        not. Never alter a clinical table merely to list reception-hosted MP4s.
        """
        if not _SAFE.fullmatch(patient_id):
            raise HTTPException(400, "Ficha inválida")
        try:
            with sqlite3.connect(db_path, timeout=5) as db:
                columns = {str(row[1]) for row in db.execute("PRAGMA table_info(patients)")}
                if "id" not in columns:
                    raise sqlite3.OperationalError("patients schema unavailable")
                clauses = ["id=?"]
                if "deleted_at" in columns:
                    clauses.append("COALESCE(deleted_at,'')=''")
                if "merged_into_patient_id" in columns:
                    clauses.append("COALESCE(merged_into_patient_id,'')=''")
                sql = "SELECT 1 FROM patients WHERE " + " AND ".join(clauses) + " LIMIT 1"
                row = db.execute(sql, (patient_id,)).fetchone()
        except sqlite3.Error:
            raise HTTPException(
                503, "Historia no pudo consultar su base local de pacientes. "
                     "Comprueba que la base de datos esté disponible."
            ) from None
        if not row:
            raise HTTPException(404, "La ficha clínica no existe o fue fusionada")
        return patient_id

    def _host():
        values = _load_env(root)
        # Explicit operator override wins; if missing, reuse the LAN source
        # observed by the existing Reception -> Historia waiting queue.
        candidate = str(values.get("RECEPTION_VIDEO_LAN_HOST") or
                        getattr(lan_service, "_last_reception_ip", "") or "").strip()
        try:
            ip = ipaddress.ip_address(candidate)
            if not ip.is_private and not ip.is_loopback:
                raise ValueError("Untrusted address")
        except ValueError:
            raise HTTPException(503, "Historia no conoce la IP de Recepción. Comprueba que los turnos LAN estén conectados y vuelve a abrir Documentos") from None
        port = str(values.get("RECEPTION_VIDEO_LAN_PORT") or "8766")
        if not port.isdigit() or not (1024 <= int(port) <= 65535):
            raise HTTPException(503, "Puerto LAN de Recepción inválido")
        host = f"[{candidate}]" if ":" in candidate else candidate
        return f"http://{host}:{port}"

    def _url(action, patient_id, video_id, path):
        values = _load_env(root)
        secret = str(values.get("CLINICAL_DELIVERY_LAN_SECRET") or "").strip()
        if len(secret) < 32:
            raise HTTPException(503, "Clave de entrega clínica LAN no configurada en Historia")
        stamp = str(int(time.time()))
        message = f"{action}|{patient_id}|{video_id}|{stamp}"
        mac = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        query = urllib.parse.urlencode({"clinical_id": patient_id, "ts": stamp, "proof": mac})
        return _host() + path + "?" + query

    def _fetch(url, headers=None, timeout=5):
        # Never send private HMAC requests through system HTTP proxies.
        req = urllib.request.Request(url, headers={
            "Accept-Encoding": "identity", "Cache-Control": "no-store",
            **(headers or {}),
        })
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)

    @app.get("/api/clinical-videos/patient/{patient_id}")
    def patient_videos(patient_id: str, request: Request):
        try:
            _local_only(request)
            _existing_patient(patient_id)
            url = _url("catalog", patient_id, "-", "/api/clinical-videos/lan/catalog")
            try:
                with _fetch(url, timeout=3) as resp:
                    data = resp.read(_JSON_LIMIT + 1)
                    if len(data) > _JSON_LIMIT:
                        raise ValueError("Catálogo excede límite")
                    payload = json.loads(data.decode("utf-8"))
                    if not isinstance(payload, dict) or not isinstance(payload.get("videos"), list):
                        raise ValueError("Catálogo inválido")
                    videos = []
                    for item in payload["videos"][:150]:
                        if not isinstance(item, dict):
                            continue
                        vid = str(item.get("id") or "")
                        if not _SAFE.fullmatch(vid):
                            continue
                        videos.append({
                            "id": vid,
                            "recorded_at": str(item.get("recorded_at") or "")[:32],
                            "size_bytes": max(0, int(item.get("size_bytes") or 0)),
                            "backup": bool(item.get("backup")),
                        })
                    return {"ok": True, "videos": videos}
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    message = ("Recepción respondió, pero rechazó la clave privada de videos. "
                               "Comprueba que CLINICAL_DELIVERY_LAN_SECRET coincida en ambas PC.")
                elif exc.code == 404:
                    message = ("Recepción respondió, pero el servicio privado de videos no está instalado. "
                               "Actualiza Recepción a la versión compatible y reiníciala.")
                elif exc.code == 503:
                    message = ("Recepción respondió, pero su archivo local de videos no está disponible. "
                               "Comprueba el almacenamiento y el servicio de videos.")
                else:
                    message = ("El servicio privado de videos de Recepción respondió con error HTTP "
                               + str(exc.code) + ".")
                return JSONResponse({"ok": False, "videos": [], "error": message},
                                    status_code=503)
            except (OSError, ValueError, TypeError, urllib.error.URLError, json.JSONDecodeError):
                return JSONResponse({"ok": False, "videos": [],
                    "error": "No se puede alcanzar el puerto privado 8766 de Recepción. "
                             "Abre Recepción y pulsa «Habilitar acceso de Historia» "
                             "en el archivo de videocistoscopías para autorizar Windows."},
                    status_code=503)
        except HTTPException:
            raise
        except Exception:
            # Never return FastAPI's plain-text 'Internal Server Error' to the
            # Javascript JSON viewer. Log the traceback locally without patient data.
            logging.getLogger(__name__).exception("Fallo interno del catálogo de videocistoscopías")
            return JSONResponse({"ok": False, "videos": [],
                "error": "Historia no pudo leer el catálogo de videos. "
                         "Reinicia Historia y vuelve a comprobar la conexión LAN."},
                status_code=503)

    @app.get("/api/clinical-videos/patient/{patient_id}/play/{video_id}")
    def play_video(patient_id: str, video_id: str, request: Request):
        _local_only(request)
        _existing_patient(patient_id)
        if not _SAFE.fullmatch(video_id):
            raise HTTPException(400, "Identificador de video inválido")
        url = _url("stream", patient_id, video_id,
                   "/api/clinical-videos/lan/stream/" + video_id)
        incoming_range = str(request.headers.get("range") or "").strip()
        if incoming_range and not re.fullmatch(r"bytes=(\d+-\d*|-\d+)", incoming_range):
            raise HTTPException(416, "Rango de video inválido")
        try:
            upstream = _fetch(url, headers={"Range": incoming_range} if incoming_range else {}, timeout=15)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise HTTPException(404, "Este video no pertenece a la ficha o el original no está disponible") from None
            if exc.code == 403:
                raise HTTPException(503, "Recepción rechazó la autorización privada de reproducción") from None
            raise HTTPException(503, "Recepción no pudo entregar el video original") from None
        except (OSError, urllib.error.URLError):
            raise HTTPException(503, "No se puede alcanzar el servidor privado de videos en Recepción") from None
        media = str(upstream.headers.get("Content-Type") or "").split(";")[0].strip()
        if media != "video/mp4":
            upstream.close()
            raise HTTPException(503, "Recepción no devolvió un video MP4")
        headers = {"Cache-Control": "private, no-store",
                   "X-Content-Type-Options": "nosniff",
                   "Accept-Ranges": "bytes"}
        for key in ("Content-Range", "Content-Length"):
            if upstream.headers.get(key):
                headers[key] = upstream.headers[key]
        return StreamingResponse(_buffered_video_body(upstream),
                                 status_code=upstream.status,
                                 media_type="video/mp4", headers=headers)
