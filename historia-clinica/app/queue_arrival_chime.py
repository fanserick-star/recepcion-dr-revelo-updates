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
from fastapi import Request  # Debe existir a nivel de módulo: anotaciones diferidas de FastAPI

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


def _gentle_chime(volume: int = 40, sound_type: str = "soft") -> bytes:
    """Dos sonidos originales, con volumen independiente del volumen de Windows."""
    rate = 22050
    sound = bytearray()
    tones = ((660, 0.15), (880, 0.19)) if sound_type == "soft" else (
        (784, 0.11), (1047, 0.14)
    )
    amplitude = 0.26 * max(0, min(100, volume)) / 100.0
    for freq, duration in tones:
        total = int(rate * duration)
        fade = max(1, int(rate * 0.022))
        for i in range(total):
            envelope = min(1.0, i / fade, (total - 1 - i) / fade)
            sample = int(32767 * amplitude * max(0.0, envelope)
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


def _play_native_diagnostic(volume: int = 40, sound_type: str = "soft") -> dict:
    """Prueba WAV en memoria y archivo local; devuelve diagnóstico legible.

    El audio no se envía a Neón, Recepción ni TV. No hay archivos clínicos.
    La llamada bloquea hasta acabar el sonido (menos de un segundo).
    """
    if os.name != "nt":
        return {"ok": False, "method": "", "message":
                "El aviso nativo necesita Windows en la PC del doctor."}
    if volume <= 0:
        return {"ok": False, "method": "", "message":
                "El volumen de la campanilla está al 0%. Súbalo en Configuración y vuelva a probar."}
    try:
        import winsound
        import tempfile
    except ImportError:
        return {"ok": False, "method": "", "message":
                "Windows no proporcionó el módulo de reproducción de sonidos."}

    data = _gentle_chime(volume, sound_type)
    try:
        flags = winsound.SND_MEMORY | getattr(winsound, "SND_NODEFAULT", 0)
        winsound.PlaySound(data, flags)
        return {"ok": True, "method": "memory", "message":
                "Campanilla enviada a la salida de audio de Windows."}
    except (OSError, RuntimeError, ValueError) as first_error:
        first_failure = str(first_error)[:120]

    # Segundo método: algunas instalaciones de Windows no aceptan WAV en
    # memoria pero sí reproducen correctamente un archivo WAV nativo.
    path = None
    try:
        fd, path = tempfile.mkstemp(prefix="historia-chime-", suffix=".wav")
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        flags = winsound.SND_FILENAME | getattr(winsound, "SND_NODEFAULT", 0)
        winsound.PlaySound(path, flags)
        return {"ok": True, "method": "wav", "message":
                "Campanilla enviada a Windows mediante audio WAV."}
    except (OSError, RuntimeError, ValueError) as second_error:
        detail = str(second_error)[:120]
        return {"ok": False, "method": "", "message":
                "Windows no pudo reproducir la campanilla. Comprueba los "
                "altavoces y el dispositivo de salida predeterminado. "
                "Detalle: " + (detail or first_failure or "falló la reproducción")}
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _play_native_sound(volume: int = 40, sound_type: str = "soft") -> bool:
    """El monitor automático nunca impide atender al paciente."""
    return bool(_play_native_diagnostic(volume, sound_type)["ok"])


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
        self._settings = self._read_settings()
        self._enabled = self._settings["enabled"]

    def _read_settings(self) -> dict:
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Configuración incorrecta")
            return {
                "enabled": data.get("enabled") is not False,
                "volume": self._clamp_volume(data.get("volume", 40)),
                "sound": data.get("sound") if data.get("sound") in {"soft", "short"} else "soft",
            }
        except (OSError, ValueError, TypeError):
            return {"enabled": True, "volume": 40, "sound": "soft"}

    @staticmethod
    def _clamp_volume(value) -> int:
        if isinstance(value, bool):
            raise ValueError("Volumen inválido.")
        try:
            return max(0, min(100, int(value)))
        except (ValueError, TypeError):
            return 40

    @property
    def settings(self) -> dict:
        with self._lock:
            return dict(self._settings)

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_settings(self, enabled: bool, volume: int, sound: str) -> dict:
        """Preferencias sólo de esta PC; no forman parte del sincronizador."""
        if not isinstance(enabled, bool) or not isinstance(volume, int) or isinstance(volume, bool):
            raise ValueError("Configuración de sonido inválida.")
        if volume < 0 or volume > 100 or not isinstance(sound, str) or sound not in {"soft", "short"}:
            raise ValueError("Volumen o tipo de sonido inválido.")
        settings = {"enabled": enabled, "volume": volume, "sound": sound}
        with self._lock:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._settings_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, self._settings_path)
            self._settings = dict(settings)
            self._enabled = enabled
            return dict(settings)

    def set_enabled(self, enabled: bool) -> bool:
        current = self.settings
        return self.set_settings(enabled, current["volume"], current["sound"])["enabled"]

    def preview_result(self) -> dict:
        """Respuesta diagnóstica de prueba, independiente del silencio."""
        with self._lock:
            current = dict(self._settings)
        if self._player is not _play_native_sound:
            self._player()
            return {"ok": True, "method": "test", "message": "Prueba ejecutada."}
        return _play_native_diagnostic(current["volume"], current["sound"])

    def preview(self) -> bool:
        return bool(self.preview_result()["ok"])

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
            if self._player is _play_native_sound:
                _play_native_sound(self.settings["volume"], self.settings["sound"])
            else:
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
    from fastapi import HTTPException
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
        return JSONResponse({**monitor.settings, "available": os.name == "nt"})

    def _authorize_local(request: Request) -> None:
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

    @app.post("/api/queue/chime")
    async def change_chime(request: Request):
        _authorize_local(request)
        try:
            body = await request.json()
        except (ValueError, TypeError):
            raise HTTPException(400, "Preferencia inválida.")
        if not isinstance(body, dict):
            raise HTTPException(400, "Preferencia inválida.")
        now = monitor.settings
        enabled = body.get("enabled", now["enabled"])
        volume = body.get("volume", now["volume"])
        sound = body.get("sound", now["sound"])
        try:
            settings = monitor.set_settings(enabled, volume, sound)
        except ValueError:
            raise HTTPException(400, "Tipo de sonido o volumen inválido.")
        except OSError:
            raise HTTPException(500, "No se pudo guardar la preferencia local.")
        return JSONResponse({"ok": True, **settings, "available": os.name == "nt"})

    @app.post("/api/queue/chime/test")
    def test_chime(request: Request):
        _authorize_local(request)
        result = monitor.preview_result()
        return JSONResponse({**result, "available": os.name == "nt"},
                            status_code=200 if result["ok"] else 503)

    return monitor
