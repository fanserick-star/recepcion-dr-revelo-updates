from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import ssl
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

BIDIRECTIONAL_TABLES = {
    "patients": "id",
    "encounters": "id",
    "patient_links": "reception_patient_id",
    "waiting_queue": "id",
    "encounter_addenda": "id",
    "macros": "id",
    "prescriptions": "id",
    "certificates": "id",
    "clinic_settings": "setting_key",
}
PUSH_ONLY_TABLES = {
    "audit_log": "id",
    "encounter_revisions": "id",
}
ALL_SYNC_TABLES = {**BIDIRECTIONAL_TABLES, **PUSH_ONLY_TABLES}
CLOUD_SCHEMA = "public"
HISTORIA_CLOUD_IDENTITY = "historia-clinica-dr-revelo"
HISTORIA_NEON_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"

_STATUS_LOCK = threading.Lock()
_SERVICE = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _load_env(root: Path) -> dict[str, str]:
    """Load Historia's private configuration only.

    v1.3.40 deliberately stops inheriting DATABASE_URL from Reception.
    Historia Clínica and Recepción are separate Neon projects.
    """
    values = dict(os.environ)
    path = Path(root) / ".env"
    if path.is_file():
        try:
            for raw in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    # The Historia-local file is authoritative.
                    values[key] = value
        except Exception:
            pass
    return values


def _endpoint_id_from_url(url: str) -> str:
    """Return ep-... endpoint id without exposing credentials."""
    try:
        host = (urllib.parse.urlsplit(str(url or "")).hostname or "").strip().lower()
        label = host.split(".", 1)[0]
        if label.endswith("-pooler"):
            label = label[:-7]
        return label
    except Exception:
        return ""


def _resolve_database_url(env: dict[str, str]) -> tuple[str, str]:
    """Historia only accepts its dedicated key; DATABASE_URL is Reception-only."""
    dedicated = str(env.get("HISTORIA_DATABASE_URL") or "").strip()
    if dedicated:
        return dedicated, "HISTORIA_DATABASE_URL"
    return "", ""


def _database_url_candidates(root: Path, env: dict[str, str]) -> list[tuple[str, str]]:
    """Return only dedicated Historia candidates.

    Never import C:\\Recepcion Dr Revelo\\.env and never fall back to DATABASE_URL.
    This prevents a fresh Historia installation from silently attaching to
    the Recepción Pacientes Neon project.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(value: object, source: str) -> None:
        url = str(value or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        out.append((url, source))

    local = {}
    path = Path(root) / ".env"
    if path.is_file():
        try:
            for raw in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                local[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            local = {}

    add(local.get("HISTORIA_DATABASE_URL"), "Historia .env · HISTORIA_DATABASE_URL")
    add(os.environ.get("HISTORIA_DATABASE_URL"), "Windows · HISTORIA_DATABASE_URL")

    resolved, source = _resolve_database_url(env)
    add(resolved, source or "Historia dedicada")
    return out

def _status_path(data_dir: Path) -> Path:
    return data_dir / "sync_status.json"


def _write_status(data_dir: Path, **values) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = _status_path(data_dir)
    with _STATUS_LOCK:
        old = {}
        if path.is_file():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        old.update(values)
        old["updated_at"] = _now_iso()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return old


def get_sync_status(data_dir: Path) -> dict:
    path = _status_path(data_dir)
    if not path.is_file():
        return {
            "state": "pending",
            "online": False,
            "configured": False,
            "message": "Preparando sincronización",
            "last_sync": "",
            "last_backup": "",
            "pending": 0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"state": "error", "online": False, "configured": False, "message": "Estado de nube no disponible"}


def _device_id(data_dir: Path) -> str:
    path = data_dir / "device_id.txt"
    if path.is_file():
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        except Exception:
            pass
    value = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    return value


def ensure_local_sync_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path, timeout=20)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("CREATE TABLE IF NOT EXISTS sync_dirty(table_name TEXT NOT NULL,row_key TEXT NOT NULL,changed_at TEXT NOT NULL,PRIMARY KEY(table_name,row_key))")
        conn.execute("CREATE TABLE IF NOT EXISTS sync_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('sync_applying_remote','0')")
        for table, key in ALL_SYNC_TABLES.items():
            qtable = table.replace('"','')
            qkey = key.replace('"','')
            for op, suffix in (("INSERT", "ai"), ("UPDATE", "au"), ("DELETE", "ad")):
                trig = f"sync_{qtable}_{suffix}"
                ref = "OLD" if op == "DELETE" else "NEW"
                conn.execute(f"DROP TRIGGER IF EXISTS {trig}")
                conn.execute(f"""
                    CREATE TRIGGER {trig} AFTER {op} ON {qtable}
                    WHEN COALESCE((SELECT value FROM meta WHERE key='sync_applying_remote'),'0')!='1'
                    BEGIN
                      INSERT INTO sync_dirty(table_name,row_key,changed_at)
                      VALUES('{qtable}',CAST({ref}.{qkey} AS TEXT),datetime('now'))
                      ON CONFLICT(table_name,row_key) DO UPDATE SET changed_at=excluded.changed_at;
                    END
                """)
        seeded = conn.execute("SELECT value FROM sync_state WHERE key='initial_seeded'").fetchone()
        if not seeded:
            for table, key in ALL_SYNC_TABLES.items():
                conn.execute(
                    f"INSERT OR IGNORE INTO sync_dirty(table_name,row_key,changed_at) SELECT ?,CAST({key} AS TEXT),datetime('now') FROM {table}",
                    (table,),
                )
            conn.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES('initial_seeded','1')")
        conn.commit()
    finally:
        conn.close()


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _backup_database(db_path: Path, data_dir: Path) -> str:
    backups = data_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    target = backups / f"historia_clinica_{stamp}.db"
    if target.is_file() and target.stat().st_size > 0:
        return str(target)
    tmp = target.with_suffix(".tmp")
    src = sqlite3.connect(db_path, timeout=20)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    os.replace(tmp, target)
    old = sorted(backups.glob("historia_clinica_*.db"), key=lambda p: p.name, reverse=True)
    for path in old[14:]:
        try: path.unlink()
        except Exception: pass
    return str(target)


def _pg_connect(url: str):
    try:
        from pg8000 import dbapi as pg
    except Exception as exc:
        raise RuntimeError("Falta pg8000. Cierra y vuelve a abrir para completar la instalación.") from exc
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("La URL de PostgreSQL/Neon de Historia Clínica es inválida")
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    timeout = int(query.get("connect_timeout") or 12)
    return pg.connect(
        user=urllib.parse.unquote(parts.username or ""),
        password=urllib.parse.unquote(parts.password or ""),
        host=parts.hostname or "",
        port=int(parts.port or 5432),
        database=urllib.parse.unquote((parts.path or "/neondb").lstrip("/")) or "neondb",
        ssl_context=ssl.create_default_context(),
        timeout=timeout,
    )


def _dict_rows(cursor):
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _remote_now(cur) -> str:
    cur.execute("SELECT now()::text")
    return str(cur.fetchone()[0])


def _normalize_remote_value(value):
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


class CloudSyncService:
    def __init__(self, root: Path, db_path: Path):
        self.root = Path(root)
        self.db_path = Path(db_path)
        self.data_dir = self.root / "data"
        self.env = _load_env(self.root)
        self.url_candidates = _database_url_candidates(self.root, self.env)
        self.url, self.url_source = self.url_candidates[0] if self.url_candidates else ("", "")
        self.enabled = str(self.env.get("HISTORIA_SYNC_ENABLED", "1")).strip().lower() not in {"0","false","no","off"}
        self.device_id = _device_id(self.data_dir)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._last_activity = time.monotonic()
        self._last_pull_monotonic = 0.0
        try:
            _c = sqlite3.connect(self.db_path, timeout=10)
            try:
                _initial_pending = int(_c.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0])
            finally:
                _c.close()
        except Exception:
            _initial_pending = 0
        _existing_status = get_sync_status(self.data_dir)
        _initial_total = max(int(_existing_status.get("initial_total") or 0), _initial_pending)
        _write_status(
            self.data_dir,
            configured=bool(self.url and self.enabled), online=False,
            config_source=self.url_source if self.url else "",
            cloud_schema=CLOUD_SCHEMA,
            state="pending" if self.url and self.enabled else "disabled",
            message=(f"Subiendo respaldo… {_initial_pending} pendientes" if self.url and self.enabled and _initial_pending else ("Nube preparada" if self.url and self.enabled else "Nube no configurada")),
            pending=_initial_pending, initial_total=_initial_total, device_id=self.device_id,
            connection_candidate_count=len(self.url_candidates),
        )

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="historia-cloud-sync", daemon=True)
        self._thread.start()
        self._wake.set()

    def stop(self):
        self._stop.set(); self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def wake(self):
        self._wake.set()

    def mark_activity(self):
        self._last_activity = time.monotonic()
        self._wake.set()

    def _pending(self, conn: sqlite3.Connection) -> int:
        missing = set(getattr(self, "_remote_missing_tables", set()) or set())
        if not missing:
            return int(conn.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0])
        marks = ",".join(["?"] * len(missing))
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM sync_dirty WHERE table_name NOT IN ({marks})",
                tuple(sorted(missing)),
            ).fetchone()[0]
        )

    def _get_state(self, conn: sqlite3.Connection, key: str, default=""):
        row = conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set_state(self, conn: sqlite3.Connection, key: str, value: str):
        conn.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)", (key, str(value)))

    def _run(self):
        try:
            backup = _backup_database(self.db_path, self.data_dir)
            _write_status(self.data_dir, last_backup=backup, backup_ok=True)
        except Exception as exc:
            _write_status(self.data_dir, backup_ok=False, backup_error=type(exc).__name__)
        if not self.enabled or not self.url:
            return
        while not self._stop.is_set():
            try:
                self._cycle()
            except Exception as exc:
                detail = f"{type(exc).__name__}: {str(exc)[:140]}"
                _write_status(
                    self.data_dir, state="offline", online=False,
                    message=f"Trabajando localmente; reintento automático · {detail}",
                    last_error=detail, cloud_schema=CLOUD_SCHEMA,
                )
            self._wake.wait(timeout=30)
            self._wake.clear()

    def _remote_columns(self, pg, schema: str, table: str) -> set[str]:
        cur = pg.cursor()
        cur.execute(
            """SELECT column_name
               FROM information_schema.columns
               WHERE table_schema=%s AND table_name=%s""",
            (schema, table),
        )
        return {str(row[0]) for row in (cur.fetchall() or [])}

    def _remote_count(self, pg, schema: str, table: str) -> int:
        cols = self._remote_columns(pg, schema, table)
        if not cols:
            return 0
        cur = pg.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        return int(cur.fetchone()[0] or 0)

    def _probe_historia_data(self, pg) -> dict:
        """Inspect the verified dedicated clinical dataset in public.*."""
        historia_patients = self._remote_count(pg, CLOUD_SCHEMA, "patients")
        historia_encounters = self._remote_count(pg, CLOUD_SCHEMA, "encounters")

        public_patient_cols = self._remote_columns(pg, "public", "patients")
        public_encounter_cols = self._remote_columns(pg, "public", "encounters")
        public_clinical_signature = {
            "id", "legacy_patient_id", "name", "name_search"
        }.issubset(public_patient_cols) and {
            "id", "patient_id", "legacy_history_id", "clinical_note"
        }.issubset(public_encounter_cols)

        public_patients = (
            self._remote_count(pg, "public", "patients")
            if public_clinical_signature else 0
        )
        public_encounters = (
            self._remote_count(pg, "public", "encounters")
            if public_clinical_signature else 0
        )
        return {
            "historia_patients": historia_patients,
            "historia_encounters": historia_encounters,
            "public_clinical_signature": bool(public_clinical_signature),
            "public_patients": public_patients,
            "public_encounters": public_encounters,
        }

    def _connect_cloud(self):
        """Connect only to the dedicated Historia Clinica Dr Revelo Neon project."""
        errors: list[str] = []

        for url, source in self.url_candidates:
            endpoint_id = _endpoint_id_from_url(url)
            if endpoint_id != HISTORIA_NEON_ENDPOINT_ID:
                errors.append(f"{source}: proyecto Neon incorrecto")
                continue

            pg = None
            try:
                pg = _pg_connect(url)
                cur = pg.cursor()
                cur.execute("SELECT current_database(), current_user")
                db_name, db_user = cur.fetchone()
                try:
                    pg.commit()
                except Exception:
                    pass

                profile = self._probe_historia_data(pg)
                self.url = url
                self.url_source = source
                self.remote_profile = profile

                _write_status(
                    self.data_dir,
                    configured=True,
                    config_source=source,
                    cloud_identity=HISTORIA_CLOUD_IDENTITY,
                    cloud_identity_verified=True,
                    cloud_endpoint_id=endpoint_id,
                    cloud_database=str(db_name or ""),
                    cloud_role=str(db_user or ""),
                    cloud_patients_seen=profile["historia_patients"],
                    cloud_encounters_seen=profile["historia_encounters"],
                    legacy_public_clinical=profile["public_clinical_signature"],
                    legacy_public_patients_seen=profile["public_patients"],
                    legacy_public_encounters_seen=profile["public_encounters"],
                    connection_candidate_count=len(self.url_candidates),
                    connection_fallback_used=False,
                )
                chosen = pg
                pg = None
                return chosen
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}")
            finally:
                if pg is not None:
                    try:
                        pg.close()
                    except Exception:
                        pass

        summary = " · ".join(errors[:4]) or "falta HISTORIA_DATABASE_URL"
        raise RuntimeError(
            "Historia Clínica no está conectada a su Neon dedicado "
            f"({summary})"
        )

    def _migrate_legacy_public_to_historia(self, pg) -> dict:
        """v1.3.41: public.* is canonical on the dedicated Historia Neon.

        The verified clinical endpoint already contains the complete historical
        dataset in public.*. Do not copy it to a second schema and do not require
        CREATE/ALTER privileges.
        """
        return {"copied": 0, "tables": 0, "mode": "public_canonical"}

    def _queue_missing_local_rows(self, pg) -> int:
        """Queue only local rows whose primary key is truly absent from Neon.

        This repairs an interrupted initial upload without overwriting rows that
        already exist in the cloud.
        """
        tables = (
            "patients",
            "encounters",
            "encounter_addenda",
            "macros",
            "prescriptions",
            "certificates",
            "clinic_settings",
        )
        queued = 0
        sconn = sqlite3.connect(self.db_path, timeout=20)
        try:
            for table in tables:
                pk = BIDIRECTIONAL_TABLES.get(table)
                if not pk:
                    continue
                try:
                    local_rows = sconn.execute(
                        f"SELECT CAST({pk} AS TEXT) FROM {table}"
                    ).fetchall()
                except sqlite3.Error:
                    continue
                if not local_rows:
                    continue

                remote_cols = self._remote_columns(pg, CLOUD_SCHEMA, table)
                if pk not in remote_cols:
                    continue
                cur = pg.cursor()
                cur.execute(
                    f'SELECT CAST("{pk}" AS TEXT) '
                    f'FROM "{CLOUD_SCHEMA}"."{table}"'
                )
                remote_ids = {str(row[0]) for row in (cur.fetchall() or [])}
                missing = [
                    str(row[0]) for row in local_rows
                    if str(row[0]) not in remote_ids
                ]
                if not missing:
                    continue

                stamp = _now_iso()
                sconn.executemany(
                    """INSERT OR IGNORE INTO sync_dirty(table_name,row_key,changed_at)
                       VALUES(?,?,?)""",
                    [(table, key, stamp) for key in missing],
                )
                queued += len(missing)
            sconn.commit()
        finally:
            sconn.close()
        return queued

    def _cycle(self):
        sconn = sqlite3.connect(self.db_path, timeout=20)
        sconn.row_factory = sqlite3.Row
        try:
            pending = self._pending(sconn)
            active = (time.monotonic() - self._last_activity) < 300
            bootstrap_done = (
                self._get_state(sconn, "cloud_bootstrap_complete", "0") == "1"
            )
            pull_due = (
                not bootstrap_done
                or (active and (time.monotonic() - self._last_pull_monotonic >= 90))
            )
            if pending == 0 and not pull_due:
                _write_status(self.data_dir, pending=0)
                return
        finally:
            sconn.close()

        pg = self._connect_cloud()
        try:
            pg.autocommit = False
            endpoint_id = _endpoint_id_from_url(self.url)

            # If this PC previously synchronized against the wrong project,
            # invalidate its cursor before reading the real Historia project.
            sconn = sqlite3.connect(self.db_path, timeout=20)
            try:
                previous_endpoint = self._get_state(
                    sconn, "cloud_endpoint_id", ""
                )
                endpoint_changed = previous_endpoint != endpoint_id
                if endpoint_changed:
                    self._set_state(
                        sconn, "last_pull", "1970-01-01T00:00:00+00:00"
                    )
                    self._set_state(sconn, "cloud_bootstrap_complete", "0")
                    self._set_state(sconn, "cloud_endpoint_id", endpoint_id)
                    self._set_state(
                        sconn, "cloud_identity", HISTORIA_CLOUD_IDENTITY
                    )
                    sconn.commit()
                    pull_due = True
            finally:
                sconn.close()

            self._ensure_remote_extension_schema(pg)

            # Recover the original public.* cloud dataset into historia.*.
            migration = self._migrate_legacy_public_to_historia(pg)
            profile = self._probe_historia_data(pg)
            remote_patients = int(profile["historia_patients"] or 0)
            remote_encounters = int(profile["historia_encounters"] or 0)

            sconn = sqlite3.connect(self.db_path, timeout=20)
            try:
                local_patients = int(
                    sconn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                )
                local_encounters = int(
                    sconn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
                )
            finally:
                sconn.close()

            # On the doctor's full PC, repair an upload that stopped part-way.
            # Only truly absent keys are queued; existing cloud rows are untouched.
            missing_queued = 0
            if (
                local_patients > remote_patients
                or local_encounters > remote_encounters
            ):
                missing_queued = self._queue_missing_local_rows(pg)

            bootstrap_recovery = (
                endpoint_changed
                or (local_patients == 0 and remote_patients > 0)
            )
            if bootstrap_recovery:
                sconn = sqlite3.connect(self.db_path, timeout=20)
                try:
                    self._set_state(
                        sconn, "last_pull", "1970-01-01T00:00:00+00:00"
                    )
                    self._set_state(sconn, "cloud_bootstrap_complete", "0")
                    self._set_state(
                        sconn, "bootstrap_recovery_version", "1.3.43"
                    )
                    sconn.commit()
                    pull_due = True
                finally:
                    sconn.close()

            _write_status(
                self.data_dir,
                cloud_identity=HISTORIA_CLOUD_IDENTITY,
                cloud_identity_verified=True,
                cloud_endpoint_id=endpoint_id,
                cloud_patients_seen=remote_patients,
                cloud_encounters_seen=remote_encounters,
                legacy_public_clinical=profile["public_clinical_signature"],
                legacy_public_patients_seen=profile["public_patients"],
                legacy_public_encounters_seen=profile["public_encounters"],
                legacy_rows_copied=int(migration.get("copied") or 0),
                missing_local_rows_queued=missing_queued,
                remote_missing_optional_tables=sorted(
                    getattr(self, "_remote_missing_tables", set()) or set()
                ),
                local_patients_before_pull=local_patients,
                local_encounters_before_pull=local_encounters,
                endpoint_changed=endpoint_changed,
                bootstrap_recovery=bootstrap_recovery,
                bootstrap_recovery_reason=(
                    "cambio_al_neon_clinico_correcto"
                    if endpoint_changed
                    else (
                        "base_local_vacia_con_pacientes_en_neon"
                        if bootstrap_recovery else ""
                    )
                ),
            )

            cur = pg.cursor()
            remote_now = _remote_now(cur)
            pg.commit()

            pulled = self._pull(pg, remote_now) if pull_due else 0
            pushed = self._push(pg)
            self._register_device(pg)
            pg.commit()
            if pull_due:
                self._last_pull_monotonic = time.monotonic()

            sconn = sqlite3.connect(self.db_path, timeout=20)
            try:
                pending_after = self._pending(sconn)
                local_patients_after = int(
                    sconn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
                )
                local_encounters_after = int(
                    sconn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
                )
            finally:
                sconn.close()

            recovery_incomplete = (
                remote_patients > 0 and local_patients_after == 0
            )
            state = (
                "syncing"
                if recovery_incomplete or pending_after > 0
                else "synced"
            )
            missing_optional = sorted(
                getattr(self, "_remote_missing_tables", set()) or set()
            )
            if recovery_incomplete:
                message = "Recuperando pacientes desde Neon de Historia…"
            elif pending_after > 0:
                message = f"Completando respaldo clínico… {pending_after} pendientes"
            elif missing_optional:
                message = (
                    "Nube clínica sincronizada · auxiliares solo locales: "
                    + ", ".join(missing_optional)
                )
            else:
                message = "Nube de Historia sincronizada"

            _write_status(
                self.data_dir,
                state=state,
                online=True,
                configured=True,
                message=message,
                last_sync=_now_iso(),
                pending=pending_after,
                last_pushed=pushed,
                last_pulled=pulled,
                local_patients_after_pull=local_patients_after,
                local_encounters_after_pull=local_encounters_after,
                bootstrap_recovery_incomplete=recovery_incomplete,
                last_error="",
            )

            if recovery_incomplete:
                sconn = sqlite3.connect(self.db_path, timeout=20)
                try:
                    self._set_state(
                        sconn, "last_pull", "1970-01-01T00:00:00+00:00"
                    )
                    self._set_state(sconn, "cloud_bootstrap_complete", "0")
                    sconn.commit()
                finally:
                    sconn.close()
                self._wake.set()
            elif pending_after > 0:
                self._wake.set()
        finally:
            try:
                pg.close()
            except Exception:
                pass

    def _register_device(self, pg):
        # v1.3.41: device telemetry is optional and must never block sync.
        try:
            cur = pg.cursor()
            cur.execute("SELECT to_regclass('public.devices')")
            row = cur.fetchone()
            if not row or not row[0]:
                return
            stamp = _now_iso()
            cur.execute("SAVEPOINT historia_device_optional")
            try:
                cur.execute(
                    """INSERT INTO public.devices(id,display_name,first_seen_at,last_seen_at,app_version)
                       VALUES(%s,%s,%s,%s,%s)
                       ON CONFLICT(id) DO UPDATE SET
                         last_seen_at=EXCLUDED.last_seen_at,
                         app_version=EXCLUDED.app_version""",
                    (
                        self.device_id,
                        os.getenv("COMPUTERNAME") or "PC Historia Clínica",
                        stamp,
                        stamp,
                        os.getenv("HISTORIA_APP_VERSION") or "1.3.43",
                    ),
                )
                cur.execute("RELEASE SAVEPOINT historia_device_optional")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT historia_device_optional")
                cur.execute("RELEASE SAVEPOINT historia_device_optional")
        except Exception:
            return

    def _ensure_remote_extension_schema(self, pg) -> None:
        """Validate the legacy public clinical schema without remote DDL.

        patients and encounters are mandatory. Auxiliary tables are optional:
        if an older Neon does not have one, v1.3.42 keeps its local dirty rows
        and skips that table instead of aborting the whole synchronization.
        """
        cur = pg.cursor()
        cur.execute("SET search_path TO public")

        available = set()
        missing = set()

        for table, pk in BIDIRECTIONAL_TABLES.items():
            cols = self._remote_columns(pg, "public", table)
            required = {pk, "cloud_updated_at", "deleted_at"}
            if required.issubset(cols):
                available.add(table)
            else:
                missing.add(table)

        for table, pk in PUSH_ONLY_TABLES.items():
            cols = self._remote_columns(pg, "public", table)
            if pk in cols:
                available.add(table)
            else:
                missing.add(table)

        for required_table in ("patients", "encounters"):
            if required_table not in available:
                raise RuntimeError(
                    "Neon clínico incompleto: falta public."
                    + required_table
                    + " o sus columnas de sincronización"
                )

        self._remote_available_tables = available
        self._remote_missing_tables = missing
        pg.commit()

    def _push(self, pg) -> int:
        sconn = sqlite3.connect(self.db_path, timeout=20)
        sconn.row_factory = sqlite3.Row
        pushed = 0
        completed = []
        try:
            items = sconn.execute("""
                SELECT table_name,row_key FROM sync_dirty
                ORDER BY CASE table_name
                  WHEN 'patients' THEN 1 WHEN 'encounters' THEN 2 WHEN 'patient_links' THEN 3
                  WHEN 'waiting_queue' THEN 4 WHEN 'encounter_addenda' THEN 5 WHEN 'macros' THEN 6
                  WHEN 'prescriptions' THEN 7 WHEN 'certificates' THEN 8 WHEN 'clinic_settings' THEN 9
                  WHEN 'audit_log' THEN 10 WHEN 'encounter_revisions' THEN 11 ELSE 99 END,
                  changed_at, row_key
                LIMIT 750
            """).fetchall()
            for item in items:
                table, key = item["table_name"], item["row_key"]
                if table not in ALL_SYNC_TABLES:
                    completed.append((table,key)); continue
                if table not in set(
                    getattr(self, "_remote_available_tables", set()) or set()
                ):
                    # Keep the dirty row locally. If the remote schema gains this
                    # table later, it can still be uploaded safely.
                    continue
                pk = ALL_SYNC_TABLES[table]
                row = sconn.execute(f"SELECT * FROM {table} WHERE CAST({pk} AS TEXT)=?", (key,)).fetchone()
                cur = pg.cursor()
                if row is None:
                    if table in BIDIRECTIONAL_TABLES:
                        cur.execute(f"UPDATE {table} SET deleted_at=%s,cloud_updated_at=now() WHERE CAST({pk} AS TEXT)=%s", (_now_iso(), key))
                    completed.append((table,key)); pushed += 1
                    continue
                data = dict(row)
                if table == "audit_log":
                    data["id"] = f"{self.device_id}:{row['id']}"
                    data["device_id"] = self.device_id
                    columns = ["id","occurred_at","actor","action","entity_type","entity_id","details_json","device_id"]
                    vals = [data.get(c) for c in columns]
                    cur.execute(
                        "INSERT INTO audit_log("+",".join(columns)+") VALUES("+",".join(["%s"]*len(columns))+") ON CONFLICT(id) DO NOTHING",
                        vals,
                    )
                elif table == "encounter_revisions":
                    source_key = f"{self.device_id}:{row['id']}"
                    columns = ["source_key","encounter_id","revision_no","saved_at","actor","clinical_note","diagnosis","treatment","reason"]
                    vals = [source_key] + [data.get(c) for c in columns[1:]]
                    # v1.3.65: las revisiones son inmutables y el Neon clínico
                    # también puede tener UNIQUE(encounter_id, revision_no). Si una
                    # revisión ya llegó desde otra instalación/dispositivo, no debe
                    # tumbar toda la sincronización ni repetirse para siempre.
                    # ON CONFLICT sin target protege tanto source_key como cualquier
                    # restricción única equivalente de la revisión.
                    cur.execute(
                        "INSERT INTO encounter_revisions("+",".join(columns)+") VALUES("+",".join(["%s"]*len(columns))+") ON CONFLICT DO NOTHING",
                        vals,
                    )
                else:
                    # v1.3.43: the dedicated clinical Neon is an older schema.
                    # Only send columns that actually exist remotely. Newer local
                    # fields remain preserved in SQLite and do not break sync.
                    remote_cols = self._remote_columns(pg, CLOUD_SCHEMA, table)
                    columns = [
                        c for c in data.keys()
                        if c in remote_cols
                        and c not in {"cloud_updated_at", "deleted_at"}
                    ]
                    if pk not in columns:
                        # This table cannot be safely synchronized with this
                        # legacy schema. Keep its dirty row locally.
                        continue
                    vals = [data.get(c) for c in columns]
                    updates = [f"{c}=EXCLUDED.{c}" for c in columns if c != pk]
                    if updates:
                        conflict_sql = (
                            "DO UPDATE SET "
                            + ",".join(updates)
                            + ",cloud_updated_at=now(),deleted_at=NULL"
                        )
                    else:
                        conflict_sql = "DO NOTHING"
                    sql = (
                        f"INSERT INTO {table}({','.join(columns)},cloud_updated_at,deleted_at) "
                        f"VALUES({','.join(['%s']*len(columns))},now(),NULL) "
                        f"ON CONFLICT({pk}) {conflict_sql}"
                    )
                    cur.execute(sql, vals)
                completed.append((table,key)); pushed += 1
            pg.commit()
            if completed:
                sconn.executemany("DELETE FROM sync_dirty WHERE table_name=? AND row_key=?", completed)
                sconn.commit()
            return pushed
        except Exception:
            try: pg.rollback()
            except Exception: pass
            raise
        finally:
            sconn.close()

    def _remote_columns_for(self, table: str, data: dict) -> list[str]:
        # Cloud schema mirrors the local columns plus cloud_updated_at/deleted_at.
        return list(data.keys())

    def _pull(self, pg, remote_now: str) -> int:
        sconn = sqlite3.connect(self.db_path, timeout=20)
        sconn.row_factory = sqlite3.Row
        pulled = 0
        try:
            last_pull = self._get_state(
                sconn, "last_pull", "1970-01-01T00:00:00+00:00"
            )
            sconn.execute(
                "UPDATE meta SET value='1' WHERE key='sync_applying_remote'"
            )
            sconn.commit()

            for table, pk in BIDIRECTIONAL_TABLES.items():
                if table not in set(
                    getattr(self, "_remote_available_tables", set()) or set()
                ):
                    continue
                cursor_time = last_pull
                cursor_key = ""
                while True:
                    cur = pg.cursor()
                    cur.execute(
                        f"""
                        SELECT * FROM {table}
                        WHERE cloud_updated_at>%s::timestamptz
                          AND cloud_updated_at<=%s::timestamptz
                          AND (
                            cloud_updated_at>%s::timestamptz
                            OR (
                              cloud_updated_at=%s::timestamptz
                              AND CAST({pk} AS TEXT)>%s
                            )
                          )
                        ORDER BY cloud_updated_at,CAST({pk} AS TEXT)
                        LIMIT 1000
                        """,
                        (
                            last_pull,
                            remote_now,
                            cursor_time,
                            cursor_time,
                            cursor_key,
                        ),
                    )
                    rows = _dict_rows(cur)
                    if not rows:
                        break

                    local_cols = set(_sqlite_columns(sconn, table))
                    for remote in rows:
                        key = remote.get(pk)
                        if key is None:
                            continue

                        stamp = remote.get("cloud_updated_at")
                        if stamp is not None:
                            cursor_time = (
                                stamp.isoformat()
                                if isinstance(stamp, datetime)
                                else str(stamp)
                            )
                            cursor_key = str(key)

                        if remote.get("deleted_at"):
                            if table in {
                                "macros",
                                "waiting_queue",
                                "patient_links",
                                "encounter_addenda",
                                "prescriptions",
                                "certificates",
                                "clinic_settings",
                            }:
                                sconn.execute(
                                    f"DELETE FROM {table} WHERE CAST({pk} AS TEXT)=?",
                                    (str(key),),
                                )
                            continue

                        data = {
                            k: _normalize_remote_value(v)
                            for k, v in remote.items()
                            if k in local_cols
                        }
                        cols = list(data.keys())
                        if not cols:
                            continue
                        placeholders = ",".join(["?"] * len(cols))
                        updates = ",".join(
                            [f"{c}=excluded.{c}" for c in cols if c != pk]
                        )
                        if updates:
                            sql = (
                                f"INSERT INTO {table}({','.join(cols)}) "
                                f"VALUES({placeholders}) "
                                f"ON CONFLICT({pk}) DO UPDATE SET {updates}"
                            )
                        else:
                            sql = (
                                f"INSERT OR IGNORE INTO {table}({','.join(cols)}) "
                                f"VALUES({placeholders})"
                            )
                        sconn.execute(sql, [data[c] for c in cols])
                        pulled += 1

                    sconn.commit()
                    if len(rows) < 1000:
                        break

            self._set_state(sconn, "last_pull", remote_now)
            self._set_state(sconn, "cloud_bootstrap_complete", "1")
            sconn.execute(
                "UPDATE meta SET value='0' WHERE key='sync_applying_remote'"
            )
            sconn.commit()
            return pulled
        except Exception:
            try:
                sconn.execute(
                    "UPDATE meta SET value='0' WHERE key='sync_applying_remote'"
                )
                sconn.commit()
            except Exception:
                pass
            raise
        finally:
            sconn.close()


def build_sync_service(root: Path, db_path: Path) -> CloudSyncService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = CloudSyncService(root, db_path)
    return _SERVICE


def get_sync_service() -> CloudSyncService | None:
    return _SERVICE