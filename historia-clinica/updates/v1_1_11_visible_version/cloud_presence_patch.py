from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime

import cloud_sync

HEARTBEAT_SECONDS = 240
APP_VERSION = "1.1.11"


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
    if getattr(cls, "_v111_presence_installed", False):
        return
    cls._v118_presence_installed = True

    # Corrige también el número de versión que registra cada sincronización normal.
    cls._register_device = _register_device

    original_start = cls.start

    def start(self):
        result = original_start(self)
        thread = getattr(self, "_v111_presence_thread", None)
        if getattr(self, "enabled", False) and getattr(self, "url", "") and not (thread and thread.is_alive()):
            thread = threading.Thread(
                target=_heartbeat_loop,
                args=(self,),
                daemon=True,
                name="historia-presence-heartbeat",
            )
            self._v118_presence_thread = thread
            thread.start()
        return result

    cls.start = start
