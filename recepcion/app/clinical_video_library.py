"""Private videocystoscopy library on the Reception PC; no cloud video storage.

Only Reception can attach an original MP4 to an already verified clinical
patient. Historia can catalogue/play via LAN with a separate shared HMAC,
without modifying patient links or copying video into Historia or Neon.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import core_runtime as core
from fastapi import Request
from fastapi.responses import FileResponse

app = core.app
BASE = Path(core.DATA_DIR).resolve() / "clinical_videos"
STORE = BASE / "objects"
INDEX = BASE / "library.sqlite3"
MAX_VIDEO = 2 * 1024 * 1024 * 1024
CHUNK = 1024 * 1024
_UUID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_FILENAME = re.compile(r"[^a-zA-Z0-9_. -]")

def _db():
    BASE.mkdir(parents=True, exist_ok=True)
    STORE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(INDEX), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=20000")
    db.execute("""CREATE TABLE IF NOT EXISTS videos(
        id TEXT PRIMARY KEY,
        reception_patient_id TEXT NOT NULL,
        clinical_patient_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        stored_name TEXT NOT NULL UNIQUE,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        recorded_at TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        archived_at TEXT,
        UNIQUE(clinical_patient_id,sha256)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS ix_videos_clinical ON videos(clinical_patient_id,recorded_at DESC)")
    db.commit()
    return db

def _safe_row(row):
    return {
        "id": str(row["id"]), "recorded_at": str(row["recorded_at"]),
        "size_bytes": int(row["size_bytes"]),
        "backup": _has_backup(row),
    }

def _local_file(row):
    stored = str(row["stored_name"])
    if not re.fullmatch(r"[0-9a-f]{32}\.mp4", stored):
        raise FileNotFoundError("Ruta del video inválida")
    file = (STORE / stored).resolve()
    if not file.is_relative_to(STORE.resolve()) or not file.is_file():
        raise FileNotFoundError("Video no disponible en la PC de Recepción")
    if file.stat().st_size != int(row["size_bytes"]):
        raise FileNotFoundError("El tamaño del original cambió")
    return file

def _backup_path(row):
    dest = str(os.getenv("CLINICAL_VIDEO_BACKUP_DIR", "")).strip()
    if not dest:
        return None
    folder = Path(dest).expanduser().resolve()
    if folder == BASE or folder.is_relative_to(BASE):
        return None
    return folder / str(row["stored_name"])

def _has_backup(row):
    path = _backup_path(row)
    try:
        return bool(path and path.is_file() and path.stat().st_size == int(row["size_bytes"])
                    and (path.parent / "library.sqlite3").is_file())
    except OSError:
        return False

def _backup_copy(row, source):
    dest = _backup_path(row)
    if dest is None:
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and dest.stat().st_size == int(row["size_bytes"]):
            return True
        temp = dest.with_name(dest.name + "." + secrets.token_hex(4) + ".part")
        try:
            with source.open("rb") as src, temp.open("xb") as target:
                shutil.copyfileobj(src, target, CHUNK)
                target.flush()
                os.fsync(target.fileno())
            with temp.open("rb") as check:
                backup_hash = hashlib.file_digest(check, "sha256").hexdigest()
            if backup_hash != row["sha256"]:
                raise OSError("Backup checksum mismatch")
            os.replace(temp, dest)
            # A backup without the patient-to-file index is not recoverable.
            # Use SQLite's online backup API; never copy an open WAL file.
            index_tmp = dest.parent / ("library.sqlite3." + secrets.token_hex(5) + ".part")
            try:
                with sqlite3.connect(str(INDEX), timeout=20) as original:
                    with sqlite3.connect(str(index_tmp), timeout=20) as copy:
                        original.backup(copy)
                os.replace(index_tmp, dest.parent / "library.sqlite3")
            finally:
                index_tmp.unlink(missing_ok=True)
            return True
        finally:
            temp.unlink(missing_ok=True)
    except (OSError, ValueError):
        return False

def _secret():
    # Reuse ONLY the independent clinical-delivery LAN secret; never turn-token
    # or appointment WhatsApp credentials.
    from clinical_delivery import _clinical_setting
    return _clinical_setting("CLINICAL_DELIVERY_LAN_SECRET")

def _verify_lan(request: Request, action, clinical_id, video_id):
    try:
        address = ipaddress.ip_address(str(request.client.host))
        if not (address.is_private or address.is_loopback):
            raise ValueError("not a private LAN client")
        stamp = str(request.query_params.get("ts") or "")
        proof = str(request.query_params.get("proof") or "")
        key = _secret()
        if not key or len(key) < 32 or not stamp.isascii() or not stamp.isdigit():
            raise ValueError("invalid authorization")
        if abs(int(time.time()) - int(stamp)) > 90:
            raise ValueError("expired authorization")
        if not _UUID.fullmatch(clinical_id) or (video_id != "-" and not _UUID.fullmatch(video_id)):
            raise ValueError("invalid identifier")
        payload = f"{action}|{clinical_id}|{video_id}|{stamp}"
        expected = hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, proof):
            raise ValueError("invalid authorization")
    except (ValueError, AttributeError, TypeError):
        raise core.HTTPException(403, "Acceso clínico LAN no autorizado") from None

def _records(clinical_id):
    with _db() as conn:
        rows = conn.execute("""SELECT * FROM videos
            WHERE clinical_patient_id=? AND archived_at IS NULL
            ORDER BY recorded_at DESC, imported_at DESC LIMIT 150""", (clinical_id,)).fetchall()
    results = []
    for row in rows:
        try:
            _local_file(row)
        except (FileNotFoundError, OSError):
            continue
        results.append(_safe_row(row))
    return results

def _row_by_id(video_id, clinical_id):
    with _db() as conn:
        row = conn.execute("""SELECT * FROM videos
            WHERE id=? AND clinical_patient_id=? AND archived_at IS NULL""",
            (video_id, clinical_id)).fetchone()
    if not row:
        raise core.HTTPException(404, "Videocistoscopía no encontrada en esta ficha")
    return row

@app.post("/api/clinical-videos/patients/{pid}/import")
async def import_video(pid: int, request: Request, filename: str = "Videocistoscopia.mp4",
                       recorded_at: str = "", db=core.Depends(core.get_db),
                       user=core.Depends(core.current_user)):
    from clinical_delivery import _linked_patient, _patient
    _patient(db, pid)
    clinical_id, reception_id, conn = _linked_patient(pid)
    conn.close()
    filename = _FILENAME.sub("_", Path(filename.replace("\\", "/")).name)[:120]
    if not filename.lower().endswith(".mp4"):
        raise core.HTTPException(415, "Solo se admiten archivos originales MP4")
    if "video/mp4" not in request.headers.get("content-type", "").lower():
        raise core.HTTPException(415, "El archivo debe ser MP4")
    if not recorded_at:
        recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    else:
        try:
            datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except ValueError:
            raise core.HTTPException(400, "Fecha de grabación inválida")
    STORE.mkdir(parents=True, exist_ok=True)
    fd, part_name = tempfile.mkstemp(prefix=".import-", suffix=".part", dir=STORE)
    total = 0
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out:
            async for piece in request.stream():
                if not piece:
                    continue
                total += len(piece)
                if total > MAX_VIDEO:
                    raise core.HTTPException(413, "El video supera el límite de 2 GB")
                digest.update(piece)
                out.write(piece)
            out.flush()
            os.fsync(out.fileno())
        with open(part_name, "rb") as probe:
            header = probe.read(32)
        if total < 1024 or header[4:8] != b"ftyp":
            raise core.HTTPException(415, "El archivo no tiene una cabecera MP4 válida")
        sha = digest.hexdigest()
        with _db() as index:
            existing = index.execute("""SELECT * FROM videos
                WHERE clinical_patient_id=? AND sha256=?""", (clinical_id, sha)).fetchone()
            if existing:
                # Never create duplicates; importing an archived duplicate does
                # not unarchive it without explicit operator decision.
                return {"ok": True, "duplicate": True, "video": _safe_row(existing)}
            video_id = secrets.token_hex(16)
            stored_name = secrets.token_hex(16) + ".mp4"
            path = STORE / stored_name
            os.replace(part_name, path)
            try:
                index.execute("""INSERT INTO videos
                    (id,reception_patient_id,clinical_patient_id,filename,stored_name,
                     sha256,size_bytes,recorded_at,imported_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (video_id, reception_id, clinical_id, filename, stored_name, sha,
                     total, recorded_at, datetime.now(timezone.utc).isoformat()))
                index.commit()
            except Exception:
                path.unlink(missing_ok=True)
                raise
            row = index.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        backup = _backup_copy(row, path)
        return {"ok": True, "duplicate": False, "video": _safe_row(row),
                "backup": backup,
                "message": "Video original archivado en Recepción sin subirlo a internet"}
    finally:
        Path(part_name).unlink(missing_ok=True)

@app.get("/api/clinical-videos/patients/{pid}")
def video_list(pid: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    from clinical_delivery import _linked_patient, _patient
    _patient(db, pid)
    clinical_id, _, conn = _linked_patient(pid)
    conn.close()
    return {"ok": True, "videos": _records(clinical_id)}

@app.get("/api/clinical-videos/lan/catalog")
def video_lan_catalog(request: Request, clinical_id: str):
    _verify_lan(request, "catalog", clinical_id, "-")
    return {"ok": True, "videos": _records(clinical_id)}

@app.get("/api/clinical-videos/lan/stream/{video_id}")
def video_lan_stream(video_id: str, clinical_id: str, request: Request):
    _verify_lan(request, "stream", clinical_id, video_id)
    row = _row_by_id(video_id, clinical_id)
    try:
        source = _local_file(row)
    except (FileNotFoundError, OSError):
        raise core.HTTPException(503, "El original no está disponible en Recepción")
    return FileResponse(source, media_type="video/mp4",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Accept-Ranges": "bytes"})
