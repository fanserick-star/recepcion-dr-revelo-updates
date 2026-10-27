from __future__ import annotations

"""Aviso sonoro local al llegar una consulta o revisión a Historia.

Lee exclusivamente la cola SQLite de esta PC cada 4 segundos. NO consulta
Neón, no escribe en las fichas, no llama al TV y no cambia el estado del turno.
En Windows usa winsound para funcionar aunque Historia esté en otra pantalla.
"""
import io
import json
import math
import os
import struct
import threading
import wave
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

_POLL_SECONDS = 4.0
_DAY_LIMIT = 1500
_ALLOWED_CONSULTATIONS = {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}
_ALLOWED_REVIEWS = {"REVISION DE EXAMENES"}


def _kind(value: object) -> str:
    import unicodedata
    raw = unicodedata.normalize("NFD", str(value or "").strip().upper())
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return " ".join(raw.split())


def _eligible(row, is_procedure) -> bool:
    """Lista cerrada: ni procedimientos ni valores desconocidos generan sonido."""
    if str(row["status"] or "") != "waiting":
        return False
    name = _kind(row["attention_type"])
    if name in _ALLOWED_REVIEWS:
        return True
    return name in _ALLOWED_CONSULTATIONS and not is_procedure(row)


def _gentle_chime() -> bytes:
    """Campanilla original y discreta de dos tonos, 16 bits / 22.05 kHz."""
    rate = 22050
    sound = bytearray()
    for freq, duration in ((660, 0.15), (880, 0.19)):
        total = int(rate * duration)
        fade = max(1, int(rate * 0.022))
        for i in range(total):
            envelope = min(1.0, i / fade, (total - 1 - i) / fade)
            sample = int(32767 * 0.105 * max(0.0, envelope)
                         * math.sin(2 * math.pi * freq * i / rate))
            sound.extend(struct.pack("<h", sample))
        sound.extend(b"\0\0" * int(rate * 0.042))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(sound)
    return buffer.getvalue()


_CHIME_WAV = _gentle_chime()


def _play_native_sound() -> None:
    """winsound es local a Windows. Fallos de audio no afectan la consulta."""
    if os.name != "nt":
        return
    try:
        import winsound
        winsound.PlaySound(_CHIME_WAV, winsound.SND_MEMORY)
    except (ImportError, OSError, RuntimeError, ValueError):
        pass


class QueueArrivalChime:
    def __init__(self, db_factory, root: Path, is_procedure, player=None):
        self._db_factory = db_factory
        self._is_procedure = is_procedure
        self._player = player if player is not None else _play_native_sound
        self._settings_path = Path(root) / "data" / "queue_arrival_chime.json"
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._started = False
        self._seen = set()
        self._day = ""
        self._enabled = self._read_enabled()

    def _read_enabled(self) -> bool:
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            return data.get("enabled") is not False
        except (OSError, ValueError, TypeError):
            return True  # Encendido por defecto; puede silenciarse desde Inicio.

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> bool:
        """Persistencia sólo local, no sincronizada con bases clínicas."""
        if not isinstance(enabled, bool):
            raise ValueError("La preferencia de sonido debe ser booleana.")
        with self._lock:
            # Escribir primero y cambiar la preferencia solo si se guardó.
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._settings_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"enabled": enabled}, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, self._settings_path)
            self._enabled = enabled
            return enabled

    def _active_today(self, day: str):
        # Lee la cola LOCAL, sin filtros de nombre ni datos sensibles.
        # Incluye estados ya atendiendo para marcarlos vistos sin reproducir.
        with self._db_factory() as conn:
            return conn.execute(
                """SELECT id, status, attention_type
                   FROM waiting_queue
                   WHERE status IN ('waiting','in_consultation')
                     AND COALESCE(deleted_at,'')=''
                     AND substr(COALESCE(queued_at,''),1,10)=?
                   ORDER BY queued_at ASC LIMIT ?""",
                (day, _DAY_LIMIT),
            ).fetchall()

    def check_once(self, *, now=None) -> bool:
        """True solamente cuando llega una consulta/revisión nueva y audible."""
        day = (now or datetime.now()).date().isoformat()
        rows = self._active_today(day)
        current = {str(r["id"]) for r in rows if str(r["id"] or "")}
        with self._lock:
            if not self._started or self._day != day:
                self._started = True
                self._day = day
                self._seen = current
                return False  # Nunca avisar por pacientes que ya estaban.
            newcomers = [r for r in rows if str(r["id"]) not in self._seen
                         and _eligible(r, self._is_procedure)]
            self._seen.update(current)
            # Sólo un sonido por grupo, y cada id se consume incluso silenciado.
            should_play = bool(newcomers) and self._enabled
        if should_play:
            self._player()
        return should_play

    def _run(self):
        # Primer chequeo fija la línea base sin sonar al iniciar/reiniciar.
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                # Reintento simple ante SQLite ocupado, nunca bloquear atención.
                pass
            if self._stop.wait(_POLL_SECONDS):
                return

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._started = False
            self._thread = threading.Thread(
                target=self._run, name="HistoriaQueueArrivalChime", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            self._stop.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)


def install(app, db_factory, root: Path, is_procedure) -> QueueArrivalChime:
    """Registra endpoints locales de preferencia y escucha en el ciclo servidor."""
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse

    monitor = QueueArrivalChime(db_factory, root, is_procedure)

    @app.on_event("startup")
    def start_chime():
        monitor.start()

    @app.on_event("shutdown")
    def stop_chime():
        monitor.stop()

    @app.get("/api/queue/chime")
    def chime_status():
        return JSONResponse({"enabled": monitor.enabled,
                             "available": os.name == "nt"})

    @app.post("/api/queue/chime")
    async def change_chime(request: Request):
        host = str(getattr(getattr(request, "client", None), "host", "") or "").lower()
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise HTTPException(403, "Solo desde la PC del doctor.")
        if request.headers.get("x-historia-queue-chime") != "1":
            raise HTTPException(403, "Acción local no autorizada.")
        if str(request.headers.get("sec-fetch-site") or "").lower() == "cross-site":
            raise HTTPException(403, "Origen externo no autorizado.")
        origin = str(request.headers.get("origin") or "")
        if origin:
            a, b = urlsplit(origin), urlsplit(str(request.base_url))
            if (a.scheme, a.netloc) != (b.scheme, b.netloc):
                raise HTTPException(403, "Origen externo no autorizado.")
        try:
            body = await request.json()
        except (ValueError, TypeError):
            raise HTTPException(400, "Preferencia inválida.")
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            raise HTTPException(400, "Se requiere enabled verdadero o falso.")
        try:
            enabled = monitor.set_enabled(body["enabled"])
        except OSError:
            raise HTTPException(500, "No se pudo guardar la preferencia local.")
        return JSONResponse({"ok": True, "enabled": enabled,
                             "available": os.name == "nt"})

    return monitor
