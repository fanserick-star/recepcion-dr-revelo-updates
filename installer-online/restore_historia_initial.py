#!/usr/bin/env python3
"""First-boot Historia restoration: PostgreSQL SELECT-only, SQLite LOCAL writes only.

Never use this script on a machine with an existing clinical database.
Never publish or print a DATABASE_URL, token or patient-identifiable row.
"""
import os
import sqlite3
import sys
from pathlib import Path

root = Path(os.environ.get("DR_REVELO_HISTORIA_ROOT", r"C:\Historia Clinica Dr Revelo"))
db_path = root / "data" / "historia_clinica.db"
resume_marker = root / "data" / ".instalador_restauracion_pendiente"
if not (root / "app.py").is_file():
    raise SystemExit("HISTORIA_APP_MISSING")

# Existing clinical data is never modified by this initializer.
existing_rows = False
if db_path.is_file():
    with sqlite3.connect(db_path) as local:
        try:
            current = [int(local.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])
                       for table in ("patients", "encounters")]
        except sqlite3.DatabaseError:
            raise SystemExit("CLINICAL_DATABASE_PRESENT_UNREADABLE")
    existing_rows = any(current)

# Installer marker is created ONLY when no old clinical SQLite exists.
# Failed imports can be safely resumed without overwriting doctor-entered data.
resume_allowed = resume_marker.is_file()
if existing_rows and resume_allowed:
    with sqlite3.connect(db_path) as check:
        pending_local = int(check.execute(
            "SELECT COUNT(*) FROM sync_dirty "
            "WHERE table_name IN ('patients','encounters','encounter_revisions')"
        ).fetchone()[0])
    if pending_local:
        raise SystemExit("LOCAL_CLINICAL_EDITS_DETECTED_RESTORE_ABORTED")
if not db_path.exists():
    resume_marker.parent.mkdir(parents=True, exist_ok=True)
    resume_marker.write_text("restauracion-segura-v1\n", encoding="utf-8")
    resume_allowed = True

os.chdir(root)
sys.path.insert(0, str(root))
import cloud_sync

if existing_rows or (db_path.is_file() and resume_allowed):
    # Existing data: no app.py import to avoid destructive startup side effects.
    # Verification only. Never import app.py over a doctor's existing database.
    service = cloud_sync.CloudSyncService(root, db_path)
else:
    import app as clinical_app  # creates only missing local SQLite schema
    service = clinical_app.SYNC_SERVICE
if not service.enabled:
    raise SystemExit("HISTORIA_CLOUD_SYNC_DISABLED")
if cloud_sync._endpoint_id_from_url(service.url) != cloud_sync.HISTORIA_NEON_ENDPOINT_ID:
    raise SystemExit("HISTORIA_NEON_WRONG_ENDPOINT")

pg = service._connect_cloud()  # SELECT-only endpoint / clinical identity verification
try:
    pg.commit()
    cur = pg.cursor()
    cur.execute("BEGIN READ ONLY")
    cur.execute("SET LOCAL search_path TO public")
    profile = service._probe_historia_data(pg)
    expected_patients = int(profile["historia_patients"])
    expected_encounters = int(profile["historia_encounters"])
    if not profile["public_clinical_signature"] or expected_patients < 1000 or expected_encounters < 1000:
        raise SystemExit("HISTORIA_CLOUD_HAS_NO_VERIFIED_HISTORIC_DATASET")

    found = set()
    for table, pk in cloud_sync.BIDIRECTIONAL_TABLES.items():
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        cols = {row[0] for row in cur.fetchall()}
        if not cols:
            continue
        if pk not in cols or "cloud_updated_at" not in cols:
            raise SystemExit("HISTORIA_CLOUD_SCHEMA_INVALID")
        found.add(table)
    if not {"patients", "encounters"}.issubset(found):
        raise SystemExit("HISTORIA_CLOUD_CORE_TABLES_MISSING")

    service._remote_available_tables = found
    if existing_rows and not resume_allowed:
        with sqlite3.connect(db_path) as existing:
            try:
                local_patients = int(existing.execute("SELECT COUNT(*) FROM patients").fetchone()[0])
                local_encounters = int(existing.execute("SELECT COUNT(*) FROM encounters").fetchone()[0])
                row = existing.execute("SELECT value FROM sync_state WHERE key='cloud_bootstrap_complete'").fetchone()
                endpoint_row = existing.execute("SELECT value FROM sync_state WHERE key='cloud_endpoint_id'").fetchone()
            except sqlite3.DatabaseError:
                raise SystemExit("CLINICAL_DATABASE_EXISTS_INCOMPLETE")
        if (local_patients < expected_patients or
            local_encounters < expected_encounters - 100 or not row or
            row[0] != "1" or not endpoint_row or
            endpoint_row[0] != cloud_sync.HISTORIA_NEON_ENDPOINT_ID):
            raise SystemExit("EXISTING_CLINICAL_DATA_NOT_VERIFIED_NO_AUTO_OVERWRITE")
        print("HISTORIA_EXISTING_DB_VERIFIED_NO_CHANGES")
        raise SystemExit(0)
    if resume_allowed:
        with sqlite3.connect(db_path) as pending:
            pending.execute(
                "INSERT OR REPLACE INTO sync_state(key,value) "
                "VALUES('last_pull','1970-01-01T00:00:00+00:00')"
            )
            pending.execute(
                "INSERT OR REPLACE INTO sync_state(key,value) "
                "VALUES('cloud_bootstrap_complete','0')"
            )
            pending.commit()
    cur.execute("SELECT now()::text")
    remote_now = str(cur.fetchone()[0])
    restored = service._pull(pg, remote_now)  # PostgreSQL SELECT; only local SQLite UPSERT

    # Audit and clinical encounter revisions are PUSH-ONLY in the normal sync.
    # A fresh PC still needs their historic records. Restore from PostgreSQL
    # using SELECT ONLY and disable local change triggers during the import.
    restored_aux = {}
    with sqlite3.connect(db_path) as local:
        local.execute("UPDATE meta SET value='1' WHERE key='sync_applying_remote'")
        local.commit()
        try:
            for table in ("encounter_revisions", "audit_log"):
                cur.execute("SELECT COUNT(*) FROM public." + table)
                expected = int(cur.fetchone()[0])
                cols = {row[1] for row in local.execute("PRAGMA table_info(" + table + ")")}
                count = 0
                for offset in range(0, expected, 500):
                    cur.execute("SELECT * FROM public." + table +
                                " ORDER BY id LIMIT 500 OFFSET %s", (offset,))
                    cloud_cols = [col[0] for col in cur.description]
                    chosen = [(idx, col) for idx, col in enumerate(cloud_cols)
                              if col in cols]
                    if "id" not in [name for _, name in chosen]:
                        raise SystemExit("HISTORIA_AUXILIARY_SCHEMA_INVALID")
                    insert_cols = [name for _, name in chosen]
                    sql = ("INSERT OR IGNORE INTO " + table + "(" +
                           ",".join(insert_cols) + ") VALUES (" +
                           ",".join("?" for _ in insert_cols) + ")")
                    for row in cur.fetchall():
                        values = [cloud_sync._normalize_remote_value(row[idx])
                                  for idx, _ in chosen]
                        local.execute(sql, values)
                        count += 1
                    local.commit()
                local_count = int(local.execute(
                    "SELECT COUNT(*) FROM " + table
                ).fetchone()[0])
                if local_count < expected:
                    raise SystemExit("HISTORIA_AUXILIARY_RESTORE_INCOMPLETE")
                restored_aux[table] = count
        finally:
            local.execute("UPDATE meta SET value='0' WHERE key='sync_applying_remote'")
            local.commit()
    pg.commit()
finally:
    pg.close()

with sqlite3.connect(db_path) as local:
    patients = int(local.execute("SELECT COUNT(*) FROM patients").fetchone()[0])
    encounters = int(local.execute("SELECT COUNT(*) FROM encounters").fetchone()[0])
    dirty = int(local.execute(
        "SELECT COUNT(*) FROM sync_dirty "
        "WHERE table_name IN ('patients', 'encounters')"
    ).fetchone()[0])
    cursor = local.execute(
        "SELECT value FROM sync_state WHERE key='cloud_bootstrap_complete'"
    ).fetchone()
    if not cursor or cursor[0] != "1":
        raise SystemExit("HISTORIA_LOCAL_CLOUD_CURSOR_NOT_COMPLETE")
    if patients < expected_patients or encounters < expected_encounters - 100 or dirty:
        raise SystemExit("HISTORIA_REMOTE_RESTORE_INCOMPLETE")
    local.execute(
        "INSERT OR REPLACE INTO sync_state(key,value) "
        "VALUES('cloud_endpoint_id',?)",
        (cloud_sync.HISTORIA_NEON_ENDPOINT_ID,),
    )
    local.execute(
        "INSERT OR REPLACE INTO sync_state(key,value) "
        "VALUES('cloud_identity',?)",
        (cloud_sync.HISTORIA_CLOUD_IDENTITY,),
    )
    local.commit()

if resume_allowed:
    resume_marker.unlink(missing_ok=True)

print("HISTORIA_FIRST_BOOT_RESTORE_OK")
print("HISTORIA_CLOUD_ROWS_RETRIEVED", restored)
print("HISTORIA_AUXILIARY_ROWS_RETRIEVED", sum(restored_aux.values()))
print("HISTORIA_LOCAL_PATIENTS", patients)
print("HISTORIA_LOCAL_ENCOUNTERS", encounters)
