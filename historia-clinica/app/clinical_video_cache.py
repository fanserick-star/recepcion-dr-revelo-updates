"""Private, bounded on-disk videocystoscopy cache for the doctor's localhost.

Only verified patient/video IDs from the HMAC-authenticated Reception catalog
are downloadable. A complete SHA256-verified MP4 becomes playable locally.
No originals are moved, signed or modified; never sent to cloud storage.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

MAX_VIDEO_BYTES = 2 * 1024 ** 3
MAX_CACHE_BYTES = 3 * 1024 ** 3
RESERVED_FREE_BYTES = 512 * 1024 ** 2
TTL_SECONDS = 2 * 60 * 60
TRANSFER_BYTES = 256 * 1024
CATALOG_LIMIT = 256 * 1024


class LocalVideoCache:
    def __init__(self, root, url_for, fetch):
        self.directory = Path(root) / "data" / "video_cache_local"
        self.url_for = url_for
        self.fetch = fetch
        self.lock = threading.RLock()
        self.jobs = {}
        self.active = None
        self.closing = threading.Event()

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.directory, 0o700)
        except OSError:
            pass
        # Per-instance cache: securely separate from Neon and never expose
        # stale videos after restarting Historia or changing Windows sessions.
        for path in self.directory.iterdir():
            if path.is_file() and (path.suffix in {".mp4", ".part"}):
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _key(patient_id, video_id):
        # No patient name or original filename ever appears in cache paths.
        return hashlib.sha256((patient_id + "|" + video_id).encode()).hexdigest()

    def _cleanup(self):
        now = time.monotonic()
        for key, job in list(self.jobs.items()):
            if job["state"] == "downloading":
                continue
            if now - job["accessed"] < TTL_SECONDS:
                continue
            path = self.directory / (key + ".mp4")
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            self.jobs.pop(key, None)

    def _catalog_item(self, patient_id, video_id):
        url = self.url_for("catalog", patient_id, "-", "/api/clinical-videos/lan/catalog")
        with self.fetch(url, timeout=10) as response:
            if response.status != 200:
                raise ValueError("Recepción rechazó el catálogo privado de videos")
            data = response.read(CATALOG_LIMIT + 1)
        if len(data) > CATALOG_LIMIT:
            raise ValueError("El catálogo de videos supera el límite")
        catalog = json.loads(data.decode("utf-8"))
        if not isinstance(catalog, dict) or not isinstance(catalog.get("videos"), list):
            raise ValueError("Respuesta de catálogo inválida")
        for item in catalog["videos"]:
            if isinstance(item, dict) and item.get("id") == video_id:
                size = int(item.get("size_bytes") or 0)
                fingerprint = str(item.get("sha256") or "").lower()
                if size < 1024 or size > MAX_VIDEO_BYTES:
                    raise ValueError("Tamaño original del video inválido")
                if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
                    raise ValueError("Actualiza Recepción para verificar la integridad del MP4 original")
                return size, fingerprint
        raise HTTPException(404, "El video no pertenece a esta ficha clínica")

    def begin(self, patient_id, video_id):
        key = self._key(patient_id, video_id)
        with self.lock:
            self._cleanup()
            job = self.jobs.get(key)
            if job and job["state"] in {"ready", "downloading"}:
                job["accessed"] = time.monotonic()
                return self.snapshot(patient_id, video_id)
            if self.active is not None:
                raise HTTPException(409, "Hay otra videocistoscopía descargándose. Termina esa primero.")
            self.directory.mkdir(parents=True, exist_ok=True)
            existing = sum(j["total"] for j in self.jobs.values() if j["state"] == "ready")
            # Do not accumulate multiple large temporary patient files forever.
            if existing > MAX_CACHE_BYTES:
                raise HTTPException(507, "Espacio de caché agotado; reinicia Historia para limpiarla.")
            # Resolve remote ownership and checksum BEFORE starting a worker.
            try:
                size, fingerprint = self._catalog_item(patient_id, video_id)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(503, "No se pudo verificar el video en Recepción por la red local") from None
            space = shutil.disk_usage(self.directory).free
            if space < size + RESERVED_FREE_BYTES or existing + size > MAX_CACHE_BYTES:
                raise HTTPException(
                    507, "Espacio insuficiente para la copia temporal. Libera espacio en la PC del doctor."
                )
            job = {
                "patient": patient_id, "video": video_id, "total": size,
                "sha256": fingerprint, "bytes": 0, "started": time.monotonic(),
                "accessed": time.monotonic(), "state": "downloading", "error": "",
            }
            self.jobs[key] = job
            self.active = key
            thread = threading.Thread(
                target=self._download, args=(key,), name="private-clinical-video-download", daemon=True
            )
            thread.start()
            return self.snapshot(patient_id, video_id)

    def _download(self, key):
        final = self.directory / (key + ".mp4")
        partial = self.directory / (key + ".part")
        job = self.jobs[key]
        try:
            url = self.url_for("stream", job["patient"], job["video"],
                               "/api/clinical-videos/lan/stream/" + job["video"])
            digest = hashlib.sha256()
            count = 0
            with self.fetch(url, timeout=35) as response:
                mime = str(response.headers.get("Content-Type") or "").split(";")[0]
                content_length = int(response.headers.get("Content-Length") or -1)
                if response.status != 200 or mime != "video/mp4" or content_length != job["total"]:
                    raise ValueError("Recepción no entregó el MP4 original completo")
                with partial.open("xb") as target:
                    try:
                        os.chmod(partial, 0o600)
                    except OSError:
                        pass
                    while not self.closing.is_set():
                        block = response.read(TRANSFER_BYTES)
                        if not block:
                            break
                        count += len(block)
                        if count > job["total"]:
                            raise ValueError("Video recibido supera el tamaño esperado")
                        digest.update(block)
                        target.write(block)
                        with self.lock:
                            job["bytes"] = count
                    target.flush()
                    os.fsync(target.fileno())
            if self.closing.is_set():
                raise ValueError("Historia se cerró antes de completar la descarga")
            if count != job["total"] or not hmac.compare_digest(digest.hexdigest(), job["sha256"]):
                raise ValueError("La descarga está incompleta o difiere del video original")
            # Never publish an unverified .part as a locally playable file.
            os.replace(partial, final)
            with self.lock:
                job["state"] = "ready"
                job["accessed"] = time.monotonic()
        except Exception:
            with self.lock:
                job["state"] = "error"
                job["error"] = ("No se pudo completar o verificar la copia temporal. "
                                "Comprueba la conexión de red local y pulsa Reintentar.")
        finally:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            with self.lock:
                if self.active == key:
                    self.active = None

    def snapshot(self, patient_id, video_id):
        key = self._key(patient_id, video_id)
        with self.lock:
            self._cleanup()
            job = self.jobs.get(key)
            if not job or job["patient"] != patient_id or job["video"] != video_id:
                return {"state": "not_started", "downloaded_bytes": 0, "total_bytes": 0}
            job["accessed"] = time.monotonic()
            elapsed = max(0.001, time.monotonic() - job["started"])
            return {
                "state": job["state"], "downloaded_bytes": job["bytes"],
                "total_bytes": job["total"],
                "speed_mbps": round(8 * job["bytes"] / (elapsed * 1_000_000), 2),
                "error": job["error"],
            }

    def playable(self, patient_id, video_id):
        key = self._key(patient_id, video_id)
        with self.lock:
            self._cleanup()
            job = self.jobs.get(key)
            if not job or job["patient"] != patient_id or job["video"] != video_id or job["state"] != "ready":
                raise HTTPException(409, "Primero descarga y verifica el video en Historia")
            path = self.directory / (key + ".mp4")
            if not path.is_file() or path.stat().st_size != job["total"]:
                raise HTTPException(503, "La copia temporal no está disponible")
            job["accessed"] = time.monotonic()
        return FileResponse(
            path, media_type="video/mp4", content_disposition_type="inline",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                     "Accept-Ranges": "bytes"}
        )

    def diagnostic(self):
        url = self.url_for("speed", "-", "-", "/api/clinical-videos/lan/speed")
        started = time.monotonic()
        with self.fetch(url, timeout=25) as response:
            if response.status != 200 or response.headers.get("Content-Type", "").split(";")[0] != "application/octet-stream":
                raise ValueError("Recepción no dispone de la prueba de velocidad privada")
            expected = 8 * 1024 * 1024
            if int(response.headers.get("Content-Length") or 0) != expected:
                raise ValueError("Tamaño inesperado de la prueba LAN")
            received = 0
            while received < expected:
                block = response.read(min(TRANSFER_BYTES, expected - received))
                if not block:
                    break
                received += len(block)
        seconds = max(time.monotonic() - started, 0.001)
        if received != expected:
            raise ValueError("La prueba LAN quedó incompleta")
        return {"ok": True, "megabits_per_second": round(received * 8 / (seconds * 1_000_000), 1),
                "megabytes_per_second": round(received / (seconds * 1024 * 1024), 2),
                "seconds": round(seconds, 2), "test_bytes": expected,
                "note": "Prueba LAN sintética, sin descargar ni compartir un video clínico."}

    def shutdown(self):
        self.closing.set()
        # Do not delete files actively being written; clean on next startup.
        with self.lock:
            if self.active is None:
                for file in self.directory.glob("*"):
                    if file.suffix in {".mp4", ".part"}:
                        try:
                            file.unlink()
                        except OSError:
                            pass


def install(app, root, url_for, fetch, local_only, existing_patient):
    cache = LocalVideoCache(root, url_for, fetch)

    @app.on_event("startup")
    def initialize_clinical_cache():
        cache.initialize()

    @app.on_event("shutdown")
    def close_clinical_cache():
        cache.shutdown()

    def guard(request, patient_id, video_id):
        local_only(request)
        existing_patient(patient_id)
        if not isinstance(video_id, str) or len(video_id) < 1 or len(video_id) > 100 or not all(
                c.isalnum() or c in "-_" for c in video_id):
            raise HTTPException(400, "Video inválido")
        # Other websites must not be able to submit download jobs to localhost.
        if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            raise HTTPException(403, "Origen no autorizado")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Origen no autorizado")

    @app.post("/api/clinical-videos/patient/{patient_id}/prepare/{video_id}")
    def prepare_video(patient_id: str, video_id: str, request: Request):
        guard(request, patient_id, video_id)
        return cache.begin(patient_id, video_id)

    @app.get("/api/clinical-videos/patient/{patient_id}/cache-status/{video_id}")
    def cache_status(patient_id: str, video_id: str, request: Request):
        guard(request, patient_id, video_id)
        return cache.snapshot(patient_id, video_id)

    @app.get("/api/clinical-videos/patient/{patient_id}/cached-play/{video_id}")
    def cache_play(patient_id: str, video_id: str, request: Request):
        guard(request, patient_id, video_id)
        return cache.playable(patient_id, video_id)

    @app.get("/api/clinical-videos/diagnostic")
    def clinical_wifi_diagnostic(request: Request):
        local_only(request)
        try:
            return cache.diagnostic()
        except (OSError, ValueError, HTTPException):
            return JSONResponse({"ok": False,
                "error": "No se pudo completar la prueba de red. Comprueba que Recepción y el puerto 8766 estén disponibles."},
                status_code=503)

    return cache
