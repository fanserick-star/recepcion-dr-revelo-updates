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
if not (root / "app.py").is_file():
    raise SystemExit("HISTORIA_APP_MISSING")

# Refuse to overwrite a clinical database that contains any patient data.
# A nonempty database is protected, even if it has an incomplete cloud cursor.
if db_path.is_file():
    with sqlite3.connect(db_path) as local:
        try:
            current = [int(local.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])
                       for table in ("patients", "encounters")]
        except sqlite3.DatabaseError:
            raise SystemExit("CLINICAL_DATABASE_PRESENT_UNREADABLE")
    if any(current):
        raise SystemExit("CLINICAL_DATABASE_ALREADY_EXISTS_NO_AUTO_OVERWRITE")

os.chdir(root)
sys.path.insert(0, str(root))
import app as clinical_app  # creates only missing local SQLite schema
import cloud_sync

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
    cur.execute("SELECT now()::text")
    remote_now = str(cur.fetchone()[0])
    restored = service._pull(pg, remote_now)  # PostgreSQL SELECT; only local SQLite UPSERT
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

print("HISTORIA_FIRST_BOOT_RESTORE_OK")
print("HISTORIA_CLOUD_ROWS_RETRIEVED", restored)
print("HISTORIA_LOCAL_PATIENTS", patients)
print("HISTORIA_LOCAL_ENCOUNTERS", encounters)
