"""Read-only preflight for the DECEMBER return from emergency Neon to official.

Never changes either Neon. Do not run during live clinical writes.
Requires both direct connection URLs in process environment; nothing saved.
Prints counts and conflict categories only, never clinical data or identifiers.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "historia-clinica" / "app"))

SOURCE_ENDPOINT = "ep-noisy-paper-arf28291"
DESTINATION_ENDPOINT = "ep-sweet-mud-arlsk7qa"
# patient_links are Reception-owned; waiting_queue is transient.
# Audit and immutable revisions require separate deduplication checks.
TABLE_KEYS = {
    "patients": "id",
    "encounters": "id",
    "prescriptions": "id",
    "certificates": "id",
    "encounter_addenda": "id",
    "macros": "id",
    "clinic_settings": "setting_key",
    "waiting_queue": "id",
    "patient_links": "reception_patient_id",
    "audit_log": "id",
    "encounter_revisions": "id",
}
MANUAL_TABLES = {"patient_links", "waiting_queue", "audit_log", "encounter_revisions"}
CRITICAL_TABLES = {"patients", "encounters", "prescriptions", "certificates"}


def classify(source: dict, destination: dict) -> dict[str, int]:
    """Pure comparison of {row_key: (digest, is_deleted)}."""
    missing = changed = destination_only = tombstone_conflict = tombstone_change = 0
    for key, (digest, deleted) in source.items():
        if key not in destination:
            missing += 1
            continue
        old_digest, old_deleted = destination[key]
        if old_deleted and not deleted:
            tombstone_conflict += 1  # Never resurrect automatically.
        elif deleted != old_deleted:
            tombstone_change += 1  # Requires explicit deletion review.
        elif digest != old_digest:
            changed += 1
    destination_only = len(set(destination) - set(source))
    return dict(
        source_only=missing,
        destination_only=destination_only,
        changed=changed,
        source_deleted_diff=tombstone_change,
        reactivation_blockers=tombstone_conflict,
    )


def endpoint_url(env_key: str, expected_endpoint: str) -> str:
    url = os.environ.get(env_key, "").strip()
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme not in ("postgres", "postgresql")
        or not host.startswith(expected_endpoint + ".")
        or (parts.path or "").lstrip("/") != "neondb"
        or not parts.username
        or not parts.password
    ):
        raise ValueError("Conexión privada ausente o endpoint no autorizado: " + env_key)
    return url


def _columns(pg) -> dict[str, set[str]]:
    cursor = pg.cursor()
    quoted = ",".join("'" + t + "'" for t in TABLE_KEYS)
    cursor.execute(
        "SELECT table_name,column_name FROM information_schema.columns "
        f"WHERE table_schema='public' AND table_name IN ({quoted})"
    )
    columns = {t: set() for t in TABLE_KEYS}
    for table, col in cursor.fetchall():
        columns[table].add(col)
    return columns


def _expressions(table: str, pk: str, columns_common: set[str]) -> tuple[str, str]:
    # Hash ONLY common clinical columns: prevents schema drift between
    # original (timestamp tombstones) and emergency (text tombstones)
    # from pretending an unchanged clinical row was modified.
    excluded = {"cloud_updated_at", "deleted_at"}
    all_known_columns = columns_common
    # jsonb_build_object uses explicit, shared columns to ensure comparable
    # fingerprints in different versions of the schema.
    fields = sorted(all_known_columns - excluded)
    if not fields:
        raise ValueError("Sin columnas comparables en " + table)
    for col in fields:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", col):
            raise ValueError("Columna de esquema inesperada")
    obj = "jsonb_build_object(" + ",".join(
        "'" + c + "',t.\"" + c + "\"" for c in fields
    ) + ")"
    digest = "md5((" + obj + ")::text)"
    deleted = (
        "NULLIF(t.deleted_at::text,'') IS NOT NULL"
        if "deleted_at" in columns_common else "FALSE"
    )
    return digest, deleted


def _bucket_summary(pg, table: str, pk: str, digest: str, deleted: str) -> dict:
    cur = pg.cursor()
    q = (
        f'WITH h AS (SELECT left(md5(t."{pk}"::text),2) bucket,'
        f' t."{pk}"::text row_key,{digest} digest,({deleted}) gone '
        f'FROM public."{table}" t) '
        "SELECT bucket,COUNT(*) rows,"
        "md5(string_agg(row_key || ':' || digest || ':' || gone::text,"
        "E'\\n' ORDER BY row_key)) fp FROM h GROUP BY bucket ORDER BY bucket"
    )
    cur.execute(q)
    return {b: (int(n), fp) for b, n, fp in cur.fetchall()}


def _bucket_rows(pg, table: str, pk: str, digest: str, deleted: str,
                 buckets: list[str]) -> dict:
    if not buckets:
        return {}
    if any(not re.fullmatch(r"[0-9a-f]{2}", b) for b in buckets):
        raise ValueError("Invalid fingerprint bucket")
    cur = pg.cursor()
    allowed = ",".join("'" + b + "'" for b in buckets)
    q = (
        f'SELECT t."{pk}"::text,{digest},({deleted}) '
        f'FROM public."{table}" t WHERE left(md5(t."{pk}"::text),2) '
        f"IN ({allowed}) ORDER BY t.\"{pk}\"::text"
    )
    cur.execute(q)
    return {str(key): (str(fp), bool(gone)) for key, fp, gone in cur.fetchall()}


def preflight(source_pg, destination_pg) -> dict:
    src_cols = _columns(source_pg)
    dst_cols = _columns(destination_pg)
    result = {"mode": "READ_ONLY", "direction": "emergency_to_official",
              "tables": {}, "blocked": False}
    for table, pk in TABLE_KEYS.items():
        shared = src_cols[table] & dst_cols[table]
        if pk not in shared:
            result["tables"][table] = {"status": "missing_primary_key"}
            result["blocked"] = True
            continue
        # Missing destination clinical fields must never be silently omitted.
        source_extra = sorted(src_cols[table] - dst_cols[table] - {"cloud_updated_at"})
        src_fingerprint, src_deleted = _expressions(table, pk, shared)
        dst_fingerprint, dst_deleted = _expressions(table, pk, shared)
        sb = _bucket_summary(source_pg, table, pk, src_fingerprint, src_deleted)
        db = _bucket_summary(destination_pg, table, pk, dst_fingerprint, dst_deleted)
        mismatched = sorted(
            b for b in set(sb) | set(db) if sb.get(b) != db.get(b)
        )
        sr = _bucket_rows(source_pg, table, pk, src_fingerprint, src_deleted, mismatched)
        dr = _bucket_rows(destination_pg, table, pk, dst_fingerprint, dst_deleted, mismatched)
        delta = classify(sr, dr)
        manual = (table in MANUAL_TABLES) or bool(source_extra)
        blocked = (bool(delta["reactivation_blockers"])
                   or bool(delta["source_deleted_diff"])
                   or (bool(source_extra) and table in CRITICAL_TABLES))
        result["blocked"] |= blocked
        result["tables"][table] = {
            "source_count": sum(v[0] for v in sb.values()),
            "official_count": sum(v[0] for v in db.values()),
            "different_buckets": len(mismatched),
            **delta,
            "manual_review": manual,
            "source_only_columns": source_extra,
        }
    return result


def main() -> None:
    # Never accept URLs through CLI, logs, repository or output files.
    source_url = endpoint_url("HISTORIA_RETURN_EMERGENCY_URL", SOURCE_ENDPOINT)
    dest_url = endpoint_url("HISTORIA_RETURN_OFFICIAL_URL", DESTINATION_ENDPOINT)
    from cloud_sync import _pg_connect
    source = destination = None
    try:
        source = _pg_connect(source_url)
        destination = _pg_connect(dest_url)
        for pg in (source, destination):
            cur = pg.cursor()
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '30000ms'")
        report = preflight(source, destination)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        if source is not None:
            source.rollback()
            source.close()
        if destination is not None:
            destination.rollback()
            destination.close()


if __name__ == "__main__":
    main()
