from __future__ import annotations

import sqlite3

import cloud_sync


def _push_encounter_tombstones(service, pg) -> int:
    """Propaga a Neon los encounters borrados lógicamente.

    `encounters` conserva la fila local por trazabilidad y marca `deleted_at`.
    El sincronizador base trata una fila existente como activa y, por diseño
    histórico, fuerza `deleted_at=NULL`. Este filtro consume primero esos
    tombstones para que un borrador descartado no pueda resucitar desde Neon.
    """
    available = set(getattr(service, "_remote_available_tables", set()) or set())
    if "encounters" not in available:
        return 0

    conn = sqlite3.connect(service.db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    completed: list[tuple[str, str]] = []
    try:
        items = conn.execute(
            """SELECT row_key
               FROM sync_dirty
               WHERE table_name='encounters'
               ORDER BY changed_at,row_key
               LIMIT 750"""
        ).fetchall()
        if not items:
            return 0

        cur = pg.cursor()
        for item in items:
            key = str(item["row_key"] or "").strip()
            if not key:
                continue
            row = conn.execute(
                "SELECT id,deleted_at FROM encounters WHERE CAST(id AS TEXT)=? LIMIT 1",
                (key,),
            ).fetchone()
            if not row or not str(row["deleted_at"] or "").strip():
                continue

            deleted_at = str(row["deleted_at"])
            cur.execute(
                """UPDATE public.encounters
                   SET deleted_at=%s,cloud_updated_at=now()
                   WHERE CAST(id AS TEXT)=%s""",
                (deleted_at, key),
            )
            completed.append(("encounters", key))

        if not completed:
            return 0

        pg.commit()
        conn.executemany(
            "DELETE FROM sync_dirty WHERE table_name=? AND row_key=?",
            completed,
        )
        conn.commit()
        return len(completed)
    except Exception:
        try:
            pg.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _apply_remote_encounter_tombstones(service, pg, remote_now: str) -> int:
    """Aplica tombstones remotos sin borrar físicamente la historia local."""
    available = set(getattr(service, "_remote_available_tables", set()) or set())
    if "encounters" not in available:
        return 0

    conn = sqlite3.connect(service.db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    applied = 0
    try:
        last_pull = service._get_state(
            conn, "last_pull", "1970-01-01T00:00:00+00:00"
        )
        cur = pg.cursor()
        cur.execute(
            """SELECT id,deleted_at,cloud_updated_at
               FROM public.encounters
               WHERE deleted_at IS NOT NULL
                 AND cloud_updated_at>%s::timestamptz
                 AND cloud_updated_at<=%s::timestamptz
               ORDER BY cloud_updated_at,CAST(id AS TEXT)""",
            (last_pull, remote_now),
        )
        rows = cloud_sync._dict_rows(cur)
        if not rows:
            return 0

        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('sync_applying_remote','1')"
        )
        conn.commit()
        try:
            for remote in rows:
                key = str(remote.get("id") or "").strip()
                if not key:
                    continue

                dirty = conn.execute(
                    "SELECT 1 FROM sync_dirty WHERE table_name='encounters' AND row_key=? LIMIT 1",
                    (key,),
                ).fetchone()
                if dirty:
                    local_row = conn.execute(
                        "SELECT * FROM encounters WHERE CAST(id AS TEXT)=? LIMIT 1",
                        (key,),
                    ).fetchone()
                    service._record_conflict(
                        conn,
                        "encounters",
                        key,
                        local_row,
                        remote,
                        "remote_tombstone_skipped_local_dirty",
                    )
                    continue

                deleted_at = cloud_sync._normalize_remote_value(remote.get("deleted_at"))
                result = conn.execute(
                    """UPDATE encounters
                       SET deleted_at=?
                       WHERE CAST(id AS TEXT)=?""",
                    (deleted_at, key),
                )
                if int(result.rowcount or 0) > 0:
                    applied += 1
            conn.commit()
        finally:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('sync_applying_remote','0')"
            )
            conn.commit()
        return applied
    finally:
        conn.close()


def install() -> None:
    cls = cloud_sync.CloudSyncService
    if getattr(cls, "_v1376_tombstone_installed", False):
        return
    cls._v1376_tombstone_installed = True

    original_push = cls._push
    original_pull = cls._pull

    def push(self, pg):
        tombstones = _push_encounter_tombstones(self, pg)
        return tombstones + int(original_push(self, pg) or 0)

    def pull(self, pg, remote_now: str):
        _apply_remote_encounter_tombstones(self, pg, remote_now)
        return original_pull(self, pg, remote_now)

    cls._push = push
    cls._pull = pull
