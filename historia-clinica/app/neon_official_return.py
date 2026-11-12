"""Controlled, differential return from emergency Neon to the original clinical Neon.

Local OFFLINE maintenance tool. Never runs at app startup. No cloud credentials
or patient-level data are written to logs or source control.

Phases: plan (read-only), copy (user-approved, guarded), verify (read-only),
switch (separate explicit approval after clinical parity and local checkpoint).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import socket
import sqlite3
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from cloud_sync import _pg_connect, _endpoint_id_from_url

ROOT = Path(__file__).resolve().parent
SOURCE = "ep-noisy-paper-arf28291"
DESTINATION = "ep-sweet-mud-arlsk7qa"
PRIMARY = {
    "patients": "id",
    "encounters": "id",
    "prescriptions": "id",
    "certificates": "id",
    "encounter_addenda": "id",
    "macros": "id",
    "audit_log": "id",
    "encounter_revisions": "id",
}
MANUAL = {
    "patient_links": "reception_patient_id",  # Reception-owned
    "waiting_queue": "id",                       # Live turn status
    "clinic_settings": "setting_key",            # Server-specific settings
}
TABLE_KEYS = {**PRIMARY, **MANUAL}
IMMUTABLE = {"audit_log", "encounter_revisions"}
SIGNED = {"encounters", "prescriptions", "certificates"}
BATCH = 25


def _ident(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise ValueError("Unexpected SQL identifier")
    return '"' + value + '"'


def classify(src, dst):
    """Row summaries: {key: (content_hash, deleted_flag)}."""
    missing, changed, source_deleted, resurrection, extra = [], [], [], [], []
    for key, (digest, deleted) in src.items():
        if key not in dst:
            missing.append(key)
        else:
            previous, was_deleted = dst[key]
            if was_deleted and not deleted:
                resurrection.append(key)
            elif was_deleted != deleted:
                source_deleted.append(key)
            elif digest != previous:
                changed.append(key)
    extra = sorted(set(dst) - set(src))
    return {"missing": sorted(missing), "changed": sorted(changed),
            "tombstone_mismatch": sorted(source_deleted),
            "resurrection_conflict": sorted(resurrection),
            "destination_only": extra}


def _load_credentials(root):
    p = root / ".env"
    if not p.is_file():
        raise RuntimeError("Missing protected local configuration")
    values = {}
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    if values.get("HISTORIA_NEON_TARGET") != "emergency":
        raise RuntimeError("Historia is not configured for the emergency Neon")
    src = values.get("HISTORIA_DATABASE_URL", "")
    dst = values.get("HISTORIA_OFFICIAL_DATABASE_URL", "")
    for url, expected in ((src, SOURCE), (dst, DESTINATION)):
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme not in ("postgres", "postgresql")
                or _endpoint_id_from_url(url) != expected
                or (parts.path or "").lstrip("/") != "neondb"
                or not parts.username or not parts.password):
            raise RuntimeError("Missing or invalid dedicated clinical Neon endpoint")
    return src, dst, values


def _columns(pg, table):
    cur = pg.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (table,))
    return {row[0] for row in cur.fetchall()}


def _row_hash(columns):
    fields = sorted(columns - {"cloud_updated_at", "deleted_at"})
    if not fields:
        raise ValueError("No comparable columns")
    pairs = []
    for c in fields:
        pairs.extend(["'" + c + "'", "t." + _ident(c)])
    return "md5(jsonb_build_object(" + ",".join(pairs) + ")::text)"


def _tombstone(columns):
    return "NULLIF(t.deleted_at::text,'') IS NOT NULL" if "deleted_at" in columns else "FALSE"


def _buckets(pg, table, pk, fp, deleted):
    cur = pg.cursor()
    cur.execute(
        "WITH h AS (SELECT left(md5(t." + _ident(pk) + "::text),2) AS bucket,"
        "t." + _ident(pk) + "::text AS row_key," + fp + " AS digest,"
        "(" + deleted + ") AS gone FROM public." + _ident(table) + " t) "
        "SELECT bucket,count(*),md5(string_agg("
        "row_key || ':' || digest || ':' || gone::text,E'\\n' ORDER BY row_key)) "
        "FROM h GROUP BY bucket ORDER BY bucket"
    )
    return {str(b): (int(n), str(fp)) for b, n, fp in cur.fetchall()}


def _bucket_rows(pg, table, pk, fp, deleted, buckets):
    if not buckets:
        return {}
    if any(not re.fullmatch(r"[0-9a-f]{2}", b) for b in buckets):
        raise RuntimeError("Unexpected bucket")
    cur = pg.cursor()
    sql = (
        "SELECT t." + _ident(pk) + "::text," + fp + ",(" + deleted + ") "
        "FROM public." + _ident(table) + " t WHERE "
        "left(md5(t." + _ident(pk) + "::text),2) IN ("
        + ",".join(["%s"] * len(buckets)) + ")"
    )
    cur.execute(sql, tuple(buckets))
    return {str(k): (str(digest), bool(gone)) for k, digest, gone in cur.fetchall()}


def build_plan(src, dst):
    """Compute fingerprints on-server, transfer only changed bucket IDs/digests."""
    tables, private = {}, {}
    for table, pk in TABLE_KEYS.items():
        sc, dc = _columns(src, table), _columns(dst, table)
        shared = sc & dc
        if pk not in shared:
            raise RuntimeError("Missing key in " + table)
        extra = sorted(sc - dc - {"cloud_updated_at"})
        # The emergency-only deleted_at on immutable tables is always a
        # consistency marker; never silently drop other clinical fields.
        unshared = sorted(c for c in extra
                          if not (table in IMMUTABLE and c == "deleted_at"))
        fp = _row_hash(shared)
        gone = _tombstone(shared)
        sb = _buckets(src, table, pk, fp, gone)
        db = _buckets(dst, table, pk, fp, gone)
        diffs = sorted(k for k in set(sb) | set(db) if sb.get(k) != db.get(k))
        sr = _bucket_rows(src, table, pk, fp, gone, diffs)
        dr = _bucket_rows(dst, table, pk, fp, gone, diffs)
        d = classify(sr, dr)
        # Keep row-level hashes only inside this process, not reports or logs.
        private[table] = {"source": sr, "dest": dr, "delta": d,
                          "shared": shared, "source_columns": sc,
                          "dest_columns": dc, "hash_sql": fp,
                          "deleted_sql": gone, "pk": pk}
        tables[table] = {
            "source_rows": sum(n for n, _ in sb.values()),
            "official_rows": sum(n for n, _ in db.values()),
            "different_buckets": len(diffs),
            "missing": len(d["missing"]),
            "changed": len(d["changed"]),
            "source_deleted_diff": len(d["tombstone_mismatch"]),
            "reactivation_conflicts": len(d["resurrection_conflict"]),
            "official_only": len(d["destination_only"]),
            "manual_review": table in MANUAL or bool(unshared),
            "unshared_source_columns": unshared,
        }
    canonical = json.dumps(
        {t: {"source": sorted((k, *v) for k,v in p["source"].items()),
             "official": sorted((k, *v) for k,v in p["dest"].items()),
             "columns": sorted(p["shared"])} for t,p in private.items()},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    token = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {"direction": "emergency_to_official", "plan_sha256": token,
            "tables": tables}, private


def _stop_if_unsafe(root, *, require_backups=False):
    """Fail closed when live app still open or pending local SQLite writes."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.8)
        if s.connect_ex(("127.0.0.1", 8787)) == 0:
            raise RuntimeError("Close Historia Clínica before maintenance")
    if os.environ.get("HISTORIA_RETURN_MAINTENANCE_CONFIRMED") != "1":
        raise RuntimeError("Explicit offline-maintenance confirmation required")
    if require_backups and os.environ.get("HISTORIA_RETURN_BACKUPS_VERIFIED") != "1":
        raise RuntimeError("Verified backups are required before writing")
    path = root / "data" / "historia_clinica.db"
    if not path.is_file():
        raise RuntimeError("Local SQLite is missing")
    db = sqlite3.connect(path, timeout=3)
    db.execute("BEGIN IMMEDIATE")
    try:
        pending = int(db.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0])
        if pending:
            raise RuntimeError("Finish emergency sync before return: pending local rows")
        try:
            conflicts = int(db.execute(
                "SELECT COUNT(*) FROM sync_conflicts WHERE resolved_at IS NULL"
            ).fetchone()[0])
        except sqlite3.OperationalError:
            conflicts = 0
        if conflicts:
            raise RuntimeError("Unresolved clinical sync conflicts require review")
    except Exception:
        db.rollback()
        db.close()
        raise
    return db


def _check_plan(plan, private, approved, *, allow_updates=False):
    if plan["plan_sha256"] != approved:
        raise RuntimeError("Plan changed since approval; run plan again")
    for table, item in private.items():
        d = item["delta"]
        if d["resurrection_conflict"] or d["tombstone_mismatch"]:
            raise RuntimeError("Conflicting deletion states require review in " + table)
        if plan["tables"][table]["unshared_source_columns"]:
            raise RuntimeError("Incompatible schema needs review in " + table)
        if table in MANUAL:
            continue
        if d["changed"] and (table in IMMUTABLE or not allow_updates):
            raise RuntimeError("Existing changed records require explicit review in " + table)


def _row(pg, table, pk, key, columns):
    cur = pg.cursor()
    names = sorted(columns)
    cur.execute("SELECT " + ",".join(_ident(c) for c in names)
                + " FROM public." + _ident(table)
                + " WHERE " + _ident(pk) + "::text=%s LIMIT 1", (key,))
    data = cur.fetchone()
    return dict(zip(names, data)) if data else None


def _fingerprint(pg, table, pk, key, fp, deleted):
    cur = pg.cursor()
    cur.execute("SELECT " + fp + ",(" + deleted + ") FROM public."
                + _ident(table) + " t WHERE t." + _ident(pk)
                + "::text=%s LIMIT 1", (key,))
    got = cur.fetchone()
    return (str(got[0]), bool(got[1])) if got else None


def _apply_one(src, dst, table, item, key, action):
    pk = item["pk"]
    expected_src = item["source"][key]
    current = _fingerprint(src, table, pk, key,
                           item["hash_sql"], item["deleted_sql"])
    if current != expected_src:
        raise RuntimeError("Source changed during transfer")
    expected_dest = item["dest"].get(key)
    current_dest = _fingerprint(dst, table, pk, key,
                                item["hash_sql"], item["deleted_sql"])
    if current_dest != expected_dest:
        raise RuntimeError("Official data changed during transfer")
    data = _row(src, table, pk, key, item["shared"] - {"cloud_updated_at"})
    if data is None:
        raise RuntimeError("Source row disappeared during transfer")
    names = sorted(item["shared"] - {"cloud_updated_at"})
    if "deleted_at" in data and not str(data["deleted_at"] or "").strip():
        data["deleted_at"] = None
    values = [data[c] for c in names]
    cur = dst.cursor()
    if action == "insert":
        cur.execute(
            "INSERT INTO public." + _ident(table) + " ("
            + ",".join(_ident(c) for c in names) + ",cloud_updated_at)"
            + " VALUES (" + ",".join(["%s"] * len(names)) + ",now())"
            + " ON CONFLICT DO NOTHING",
            tuple(values),
        )
    elif action == "update":
        if table in IMMUTABLE:
            raise RuntimeError("Immutable records cannot be updated automatically")
        if expected_src[1] or expected_dest[1]:
            raise RuntimeError("Tombstone changes cannot be updated automatically")
        if table == "encounters":
            old = _row(dst, table, pk, key,
                       {"id", "signed_at", "note_status"})
            if (str(data.get("signed_at") or "") != str(old.get("signed_at") or "")
                    or data.get("note_status") != old.get("note_status")):
                raise RuntimeError("Signed consultation mismatch; manual review")
        assignments = [(_ident(c) + "=%s") for c in names if c != pk]
        assignments.append("cloud_updated_at=now()")
        # Optimistic guard against an intervening clinical write. All
        # comparisons are rechecked immediately within this transaction.
        cur.execute("UPDATE public." + _ident(table) + " AS t SET "
                    + ",".join(assignments) + " WHERE " + _ident(pk)
                    + "::text=%s AND " + item["hash_sql"] + "=%s"
                    + " AND NOT (" + item["deleted_sql"] + ")",
                    tuple(data[c] for c in names if c != pk)
                    + (key, expected_dest[0]),
                    )
    else:
        raise RuntimeError("Invalid operation")
    if int(cur.rowcount or 0) != 1:
        raise RuntimeError("Clinical row changed or conflicted; rolled back")
    latest = _fingerprint(dst, table, pk, key,
                          item["hash_sql"], item["deleted_sql"])
    if latest != expected_src:
        raise RuntimeError("Written row content was not verified")


def transfer(src, dst, plan, private, approved, *, allow_updates=False):
    _check_plan(plan, private, approved, allow_updates=allow_updates)
    result = {}
    for table in PRIMARY:
        item = private[table]
        delta = item["delta"]
        operations = [(k, "insert") for k in delta["missing"]]
        if allow_updates:
            operations += [(k, "update") for k in delta["changed"]]
        inserted = updated = 0
        try:
            for i in range(0, len(operations), BATCH):
                for key, action in operations[i:i+BATCH]:
                    _apply_one(src, dst, table, item, key, action)
                    inserted += int(action == "insert")
                    updated += int(action == "update")
                dst.commit()
            result[table] = {"inserted": inserted, "updated": updated}
        except Exception:
            dst.rollback()
            raise
    return result


def _verify_complete(plan):
    for table in PRIMARY:
        row = plan["tables"][table]
        if (row["missing"] or row["changed"] or row["official_only"] or row["source_deleted_diff"]
                or row["reactivation_conflicts"] or row["unshared_source_columns"]):
            raise RuntimeError("Clinical parity not verified in " + table)
    for table in MANUAL:
        row = plan["tables"][table]
        if (row["missing"] or row["changed"] or row["source_deleted_diff"]
                or row["reactivation_conflicts"] or row["official_only"]):
            raise RuntimeError("Manual review pending in " + table)


def _atomic_save(path, value):
    # Temporary file is created beside destination; atomic os.replace.
    fd, temp_name = tempfile.mkstemp(prefix=".neon-official-", dir=path.parent)
    try:
        os.chmod(temp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)


def switch(root, local_db, source_url, official_url, plan_sha, official_pg):
    # This is deliberately separate from copy and requires another approval.
    path = root / ".env"
    previous = path.read_text(encoding="utf-8-sig")
    if _load_credentials(root)[0] != source_url:
        raise RuntimeError("Current emergency configuration changed")
    remote = official_pg.cursor()
    remote.execute("SELECT now()::text")
    official_now = str(remote.fetchone()[0])
    official_pg.commit()
    lines = []
    found = set()
    for line in previous.splitlines():
        if line.startswith("HISTORIA_DATABASE_URL="):
            lines.append("HISTORIA_DATABASE_URL=" + official_url); found.add("url")
        elif line.startswith("HISTORIA_NEON_TARGET="):
            lines.append("HISTORIA_NEON_TARGET=official"); found.add("target")
        elif line.startswith("HISTORIA_EMERGENCY_DATABASE_URL="):
            lines.append("HISTORIA_EMERGENCY_DATABASE_URL=" + source_url)
            found.add("emergency")
        else:
            lines.append(line)
    if "url" not in found or "target" not in found:
        raise RuntimeError("Missing private connection keys; switch refused")
    if "emergency" not in found:
        lines.append("HISTORIA_EMERGENCY_DATABASE_URL=" + source_url)
    backup = root / "data" / "neon_before_return_private.env"
    if not backup.exists():
        _atomic_save(backup, previous)
    # The SQLite marker is written before the .env switch; if an error occurs,
    # restore the previous local state so restarting Historia remains safe.
    keys = ["cloud_endpoint_id", "last_pull", "cloud_bootstrap_complete",
            "official_return_verified_sha"]
    old = {k: local_db.execute(
        "SELECT value FROM sync_state WHERE key=?", (k,)
    ).fetchone() for k in keys}
    try:
        for k,v in (("cloud_endpoint_id", DESTINATION),
                    ("last_pull", official_now),
                    ("cloud_bootstrap_complete", "1"),
                    ("official_return_verified_sha", plan_sha)):
            local_db.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)", (k,v))
        local_db.commit()
        local_db.execute("BEGIN IMMEDIATE")
        _atomic_save(path, "\n".join(lines).rstrip("\n") + "\n")
    except Exception:
        local_db.execute("BEGIN IMMEDIATE")
        for k, row in old.items():
            if row:
                local_db.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)",
                                 (k,row[0]))
            else:
                local_db.execute("DELETE FROM sync_state WHERE key=?", (k,))
        local_db.commit()
        with contextlib.suppress(Exception):
            _atomic_save(path, previous)
        raise
    local_db.commit()
    return {"connection": "official", "rollback_file_preserved": True,
            "verification_sha": plan_sha, "restart_required": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Controlled return to official clinical Neon")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--phase", choices=("plan","copy","verify","switch"), required=True)
    parser.add_argument("--approved-plan", default="")
    parser.add_argument("--allow-reviewed-updates", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    source_url, official_url, _ = _load_credentials(root)
    if args.phase in ("copy", "switch"):
        if args.confirm != ("COPIAR_DIFERENCIAS" if args.phase == "copy"
                            else "ACTIVAR_NEON_OFICIAL"):
            raise RuntimeError("Missing explicit action authorization")
    lock = _stop_if_unsafe(root, require_backups=args.phase in ("copy", "switch"))
    source = official = None
    try:
        source = _pg_connect(source_url)
        official = _pg_connect(official_url)
        # Same-session read-only source. The original is read-only until copy.
        source.cursor().execute("SET TRANSACTION READ ONLY")
        source.cursor().execute("SET LOCAL statement_timeout='60000ms'")
        report, private = build_plan(source, official)
        if args.phase == "copy":
            result = transfer(source, official, report, private, args.approved_plan,
                              allow_updates=args.allow_reviewed_updates)
            print(json.dumps({"applied": True, "changes": result,
                              "rerun_plan_and_verify": True}))
        elif args.phase in ("verify", "switch"):
            if args.phase == "switch" and report["plan_sha256"] != args.approved_plan:
                raise RuntimeError("Verification plan no longer matches approved plan")
            _verify_complete(report)
            if args.phase == "verify":
                print(json.dumps({"verified": True,
                                  "plan_sha256": report["plan_sha256"]}))
            else:
                result = switch(root, lock, source_url, official_url,
                                report["plan_sha256"], official)
                print(json.dumps(result))
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        if source is not None:
            source.rollback(); source.close()
        if official is not None:
            official.rollback(); official.close()
        lock.rollback(); lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Errors must not include patient records or DB connection strings.
        print("NEON_RETURN_BLOCKED: " + type(error).__name__)
        raise SystemExit(2)
