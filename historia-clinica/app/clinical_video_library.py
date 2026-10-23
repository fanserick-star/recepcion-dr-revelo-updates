"""Read-only local Historia proxy for MP4 originals stored on Reception.

No MP4 in Historia SQLite/Neon, browser only communicates with local Historia.
Requests to Reception are HMAC authenticated and LAN IP restricted.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_JSON_LIMIT = 256 * 1024

def install(app, root: Path, db_path: Path, lan_service):
    from cloud_sync import _load_env

    def _local_only(request):
        ip = str(getattr(request.client, "host", "") or "").lower()
        if ip not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(403, "Los videos clínicos se consultan solo desde esta PC")

    def _existing_patient(patient_id):
        if not _SAFE.fullmatch(patient_id):
            raise HTTPException(400, "Ficha inválida")
        with sqlite3.connect(db_path, timeout=5) as db:
            row = db.execute("""SELECT 1 FROM patients
                WHERE id=? AND COALESCE(deleted_at,'')='' LIMIT 1""", (patient_id,)).fetchone()
        if not row:
            raise HTTPException(404, "La ficha clínica no existe")
        return patient_id

    def _host():
        values = _load_env(root)
        candidate = str(getattr(lan_service, "_last_reception_ip", "") or
                        values.get("RECEPTION_VIDEO_LAN_HOST") or "").strip()
        try:
            ip = ipaddress.ip_address(candidate)
            if not ip.is_private and not ip.is_loopback:
                raise ValueError("Untrusted address")
        except ValueError:
            raise HTTPException(503, "Recepción desconectada: abre Recepción y comprueba la conexión LAN") from None
        port = str(values.get("RECEPTION_VIDEO_LAN_PORT") or "8000")
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
        _local_only(request)
        _existing_patient(patient_id)
        url = _url("catalog", patient_id, "-", "/api/clinical-videos/lan/catalog")
        try:
            with _fetch(url, timeout=3) as resp:
                data = resp.read(_JSON_LIMIT + 1)
                if len(data) > _JSON_LIMIT:
                    raise ValueError("Catálogo excede límite")
                payload = json.loads(data.decode("utf-8"))
                if not isinstance(payload.get("videos"), list):
                    raise ValueError("Catálogo inválido")
                videos = []
                for item in payload["videos"][:150]:
                    vid = str(item.get("id") or "")
                    if not _SAFE.fullmatch(vid):
                        continue
                    videos.append({
                        "id": vid,
                        "recorded_at": str(item.get("recorded_at") or "")[:32],
                        "size_bytes": int(item.get("size_bytes") or 0),
                        "backup": bool(item.get("backup")),
                    })
                return {"ok": True, "videos": videos}
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            return JSONResponse({"ok": False, "videos": [],
                "error": "PC de Recepción no disponible para consultar videos. Comprueba que esté encendida y conectada a la LAN."},
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
            raise HTTPException(404 if exc.code == 404 else 503,
                                "El video no está disponible en Recepción") from None
        except (OSError, urllib.error.URLError):
            raise HTTPException(503, "No hay conexión con Recepción para reproducir el video") from None
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
        def stream():
            try:
                while True:
                    block = upstream.read(256 * 1024)
                    if not block:
                        break
                    yield block
            finally:
                upstream.close()
        return StreamingResponse(stream(), status_code=upstream.status,
                                 media_type="video/mp4", headers=headers)
