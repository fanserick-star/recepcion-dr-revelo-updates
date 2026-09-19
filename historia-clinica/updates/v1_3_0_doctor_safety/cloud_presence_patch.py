from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime

import cloud_sync

AFK_SECONDS = 300
HEARTBEAT_SECONDS = 240
APP_VERSION = "1.3.0"


def _current_app_version(service) -> str:
    try:
        conn = sqlite3.connect(service.db_path, timeout=5)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='app_version' LIMIT 1").fetchone()
            value = str(row[0] or "").strip() if row else ""
            return value or APP_VERSION
        finally:
            conn.close()
    except Exception:
        return APP_VERSION


def _pending_count(service) -> int:
    try:
        conn = sqlite3.connect(service.db_path, timeout=5)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return 0


def _idle_seconds(service) -> int:
    try:
        return max(0, int(time.monotonic() - float(service._last_activity)))
    except Exception:
        return 0


def _is_afk(service) -> bool:
    return _pending_count(service) == 0 and _idle_seconds(service) >= AFK_SECONDS


def _register_device(self, pg):
    cur = pg.cursor()
    stamp = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """INSERT INTO devices(id,display_name,first_seen_at,last_seen_at,app_version)
           VALUES(%s,%s,%s,%s,%s)
           ON CONFLICT(id) DO UPDATE SET
             last_seen_at=EXCLUDED.last_seen_at,
             app_version=EXCLUDED.app_version""",
        (
            self.device_id,
            os.getenv("COMPUTERNAME") or "PC Historia Clínica",
            stamp,
            stamp,
            _current_app_version(self),
        ),
    )


def _heartbeat_once(service) -> None:
    if not getattr(service, "enabled", False) or not getattr(service, "url", ""):
        return

    pending = _pending_count(service)
    idle = _idle_seconds(service)

    # AFK real: con la cola limpia no se abre ninguna conexión a Neon.
    if pending == 0 and idle >= AFK_SECONDS:
        try:
            cloud_sync._write_status(
                service.data_dir,
                configured=True,
                online=False,
                state="afk",
                message="En reposo (AFK)",
                pending=0,
                afk=True,
                idle_seconds=idle,
            )
        except Exception:
            pass
        return

    # Si hay cambios pendientes, el ciclo principal ya usa Neon y registra el
    # dispositivo durante ese mismo push; no duplicamos conexiones.
    if pending > 0:
        return

    pg = None
    try:
        pg = cloud_sync._pg_connect(service.url)
        pg.autocommit = False
        service._register_device(pg)
        pg.commit()
    except Exception:
        try:
            if pg is not None:
                pg.rollback()
        except Exception:
            pass
    finally:
        try:
            if pg is not None:
                pg.close()
        except Exception:
            pass


def _heartbeat_loop(service) -> None:
    while not service._stop.wait(HEARTBEAT_SECONDS):
        _heartbeat_once(service)


def install() -> None:
    cls = cloud_sync.CloudSyncService
    if getattr(cls, "_v130_afk_installed", False):
        return
    cls._v130_afk_installed = True

    cls._register_device = _register_device

    original_start = cls.start
    original_mark_activity = cls.mark_activity

    def mark_activity(self):
        result = original_mark_activity(self)
        try:
            status = cloud_sync.get_sync_status(self.data_dir)
            if status.get("state") == "afk":
                cloud_sync._write_status(
                    self.data_dir,
                    configured=bool(self.url and self.enabled),
                    online=False,
                    state="ready",
                    message="Nube lista · actividad detectada",
                    afk=False,
                    idle_seconds=0,
                )
        except Exception:
            pass
        return result

    def start(self):
        result = original_start(self)
        thread = getattr(self, "_v130_presence_thread", None)
        if getattr(self, "enabled", False) and getattr(self, "url", "") and not (thread and thread.is_alive()):
            thread = threading.Thread(
                target=_heartbeat_loop,
                args=(self,),
                daemon=True,
                name="historia-presence-heartbeat",
            )
            self._v130_presence_thread = thread
            thread.start()
        return result

    cls.mark_activity = mark_activity
    cls.start = start
