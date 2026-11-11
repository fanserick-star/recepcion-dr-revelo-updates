"""Historia 1.4.77: opt-in emergency backup FROM THE DOCTOR'S LOCAL SQLITE.
Never connects to the original Neon project or changes the active synchronizer.
No database passwords, clinical records, or signed document contents are logged.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from cloud_sync import _pg_connect

PROJECT_ID = "winter-smoke-49748362"
ENDPOINT = "ep-noisy-paper-arf28291"
EXPECTED_HOST = ENDPOINT + ".c-4.us-west-2.aws.neon.tech"
CHUNK_SIZE = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 650 * 1024 * 1024  # Keep below Free branch 1 GiB limit.
COPY_TABLES = (
    ("patients", "id"), ("encounters", "id"), ("patient_links", "reception_patient_id"),
    ("waiting_queue", "id"), ("encounter_addenda", "id"), ("macros", "id"),
    ("prescriptions", "id"), ("certificates", "id"), ("clinic_settings", "setting_key"),
    ("audit_log", "id"), ("encounter_revisions", "id"),
)
_ID = re.compile(r"^[a-z_][a-z0-9_]*$")
_LOCK = threading.Lock()
_RUNNING = False


def _quoted(value: str) -> str:
    if not _ID.fullmatch(value):
        raise RuntimeError("Identificador de columna no permitido")
    return '"' + value + '"'


def _validate_destination(value: str) -> str:
    url = str(value or "").strip()
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        database = urllib.parse.unquote((parts.path or "").strip("/"))
        if (
            parts.scheme not in {"postgres", "postgresql"}
            or host not in {EXPECTED_HOST, ENDPOINT + "-pooler.c-4.us-west-2.aws.neon.tech"}
            or not parts.username or not parts.password
            or database != "neondb"
            or int(parts.port or 5432) != 5432
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeError(
            "Pega la cadena de conexión directa del proyecto 'Historia Clinica Emergencia' "
            "(neondb); no se aceptan conexiones al Neon oficial ni a Recepción."
        ) from None
    return url


def _status_path(root: Path) -> Path:
    return root / "data" / "neon_emergency_copy_status.json"


def _publish(root: Path, **values: object) -> dict:
    path = _status_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = {}
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    old.update(values)
    old["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
    return old


def _status(root: Path) -> dict:
    try:
        data = json.loads(_status_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {"state": "not_started", "message": "Todavía no se ha copiado la base local."}


def _is_local(request: Request) -> None:
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, detail="Solo disponible en la PC del doctor")


def _type_for(col: sqlite3.Row) -> str:
    raw = str(col[2] or "").upper()
    if "BLOB" in raw:
        return "BYTEA"
    if "INT" in raw:
        return "BIGINT"
    if any(t in raw for t in ("REAL", "FLOAT", "DOUBLE")):
        return "DOUBLE PRECISION"
    return "TEXT"


def _columns(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({_quoted(table)})").fetchall()


def _create_tables(source: sqlite3.Connection, pg) -> None:
    cursor = pg.cursor()
    cursor.execute("CREATE SCHEMA IF NOT EXISTS emergency_archive")
    cursor.execute("""CREATE TABLE IF NOT EXISTS emergency_archive.manifests(
        id TEXT PRIMARY KEY, archive_sha256 TEXT NOT NULL, archive_size BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        verified BOOLEAN NOT NULL DEFAULT FALSE,
        sqlite_summary TEXT NOT NULL DEFAULT '{}'
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS emergency_archive.chunks(
        backup_id TEXT NOT NULL, chunk_index INTEGER NOT NULL,
        content BYTEA NOT NULL, content_md5 TEXT NOT NULL,
        PRIMARY KEY (backup_id, chunk_index)
    )""")
    for table, key in COPY_TABLES:
        cols = _columns(source, table)
        if not cols:
            raise RuntimeError("Falta una tabla clínica local requerida: " + table)
        names = [str(c[1]) for c in cols]
        if key not in names:
            raise RuntimeError("Falta la clave clínica en: " + table)
        definitions = []
        for col in cols:
            name = str(col[1])
            if name == "cloud_updated_at":
                continue
            typ = "TEXT" if name == key else _type_for(col)
            definitions.append(_quoted(name) + " " + typ + (" PRIMARY KEY" if name == key and table != "encounter_revisions" else ""))
        if "deleted_at" not in names:
            definitions.append("deleted_at TEXT")
        definitions.append("cloud_updated_at TIMESTAMPTZ NOT NULL DEFAULT now()")
        if table == "encounter_revisions" and "source_key" not in names:
            definitions.append("source_key TEXT PRIMARY KEY")
        if table == "audit_log" and "device_id" not in names:
            definitions.append("device_id TEXT")
        cursor.execute("CREATE TABLE IF NOT EXISTS public." + _quoted(table) +
                       " (" + ",".join(definitions) + ")")
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s", (table,)
        )
        found = {str(r[0]) for r in cursor.fetchall()}
        required = set(names) - {"cloud_updated_at"}
        required |= {key, "deleted_at", "cloud_updated_at"}
        if table == "encounter_revisions":
            required.add("source_key")
        if not required.issubset(found):
            raise RuntimeError("Esquema parcial o incompatible en el respaldo: " + table)
    cursor.execute("""CREATE TABLE IF NOT EXISTS public.devices(
        id TEXT PRIMARY KEY, display_name TEXT,
        first_seen_at TEXT, last_seen_at TEXT, app_version TEXT
    )""")
    pg.commit()


def _table_digest_local(conn: sqlite3.Connection, table: str, pk: str) -> tuple[int, str]:
    cur = conn.execute(f"SELECT {_quoted(pk)} FROM {_quoted(table)} ORDER BY CAST({_quoted(pk)} AS TEXT)")
    digest = hashlib.md5()
    total = 0
    first = True
    for (key,) in cur:
        if not first:
            digest.update(b"\n")
        digest.update(str(key).encode("utf-8"))
        first = False
        total += 1
    return total, digest.hexdigest()


def _table_digest_remote(pg, table: str, pk: str) -> tuple[int, str]:
    cur = pg.cursor()
    cur.execute("SELECT count(*), md5(COALESCE(string_agg("
                "CAST(" + _quoted(pk) + " AS TEXT), E'\\n' ORDER BY "
                "CAST(" + _quoted(pk) + " AS TEXT)),'')) "
                "FROM public." + _quoted(table))
    n, md5 = cur.fetchone()
    return int(n), str(md5)


def _make_archive(root: Path, db_path: Path) -> tuple[Path, dict, Path]:
    backups = root / "data" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = backups / ("historia_emergencia_local_" + stamp + ".zip")
    with tempfile.TemporaryDirectory(prefix="historia_neon_snapshot_", dir=str(backups)) as td:
        snapshot = Path(td) / "historia_clinica.db"
        source = sqlite3.connect(db_path, timeout=30)
        target = sqlite3.connect(snapshot, timeout=30)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        check = sqlite3.connect(f"file:{snapshot.as_posix()}?mode=ro", uri=True)
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise RuntimeError("La copia local no pasó la verificación SQLite.")
            stats = {table: int(check.execute(
                f"SELECT COUNT(*) FROM {_quoted(table)}"
            ).fetchone()[0]) for table, _ in COPY_TABLES}
        finally:
            check.close()
        pdf_count = 0
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(snapshot, "historia_clinica.db")
            signed = root / "data" / "documentos_firmados"
            if signed.is_dir():
                for pdf in sorted(signed.rglob("*.pdf")):
                    if not pdf.is_file() or pdf.is_symlink():
                        continue
                    archive.write(pdf, "documentos_firmados/" + pdf.relative_to(signed).as_posix())
                    pdf_count += 1
        size = output.stat().st_size
        if size > MAX_ARCHIVE_BYTES:
            raise RuntimeError(
                "La copia local quedó guardada, pero excede el tamaño seguro para "
                "este proyecto Free. Se necesita dividir el respaldo antes de subirlo."
            )
    stats["pdf_signed_files"] = pdf_count
    stats["archive_bytes"] = size
    # Keep the backup locally; never publish it in GitHub.
    return output, stats, backups


def _copy_rows(snapshot: sqlite3.Connection, pg, root: Path) -> dict:
    report = {}
    for i, (table, pk) in enumerate(COPY_TABLES, 1):
        columns_info = _columns(snapshot, table)
        names = [str(col[1]) for col in columns_info if str(col[1]) != "cloud_updated_at"]
        query = "SELECT " + ",".join(_quoted(c) for c in names) + \
                " FROM " + _quoted(table) + " ORDER BY CAST(" + _quoted(pk) + " AS TEXT)"
        cur = snapshot.execute(query)
        remote = pg.cursor()
        revisions_need_source_key = table == "encounter_revisions" and "source_key" not in names
        remote_key = "source_key" if revisions_need_source_key else pk
        outbound_names = names + (["source_key"] if revisions_need_source_key else [])
        names_str = ",".join(_quoted(c) for c in outbound_names)
        columns_sql = names_str + ",cloud_updated_at"
        placeholders = "(" + ",".join(["%s"] * len(outbound_names)) + ",now())"
        updates = ",".join(_quoted(c) + "=EXCLUDED." + _quoted(c)
                           for c in outbound_names if c != remote_key)
        update_clause = "DO UPDATE SET " + updates + ",cloud_updated_at=now()" \
                        if updates else "DO NOTHING"
        rows_done = 0
        while True:
            batch = cur.fetchmany(40)
            if not batch:
                break
            rows = [tuple(row) for row in batch]
            if revisions_need_source_key:
                device_file = root / "data" / "device_id.txt"
                device_id = (device_file.read_text(encoding="utf-8").strip()
                             if device_file.is_file() else "historia-local")
                key_index = names.index(pk)
                rows = [r + (device_id + ":" + str(r[key_index]),) for r in rows]
            sql = "INSERT INTO public." + _quoted(table) + "(" + columns_sql + ") VALUES " + \
                  ",".join([placeholders] * len(rows)) + \
                  " ON CONFLICT (" + _quoted(remote_key) + ") " + update_clause
            params = [cell for row in rows for cell in row]
            remote.execute(sql, tuple(params))
            rows_done += len(rows)
        pg.commit()
        expected = _table_digest_local(snapshot, table, pk)
        got = _table_digest_remote(pg, table, pk)
        if expected != got:
            raise RuntimeError("La verificación de registros no coincide en: " + table)
        report[table] = rows_done
        _publish(root, state="copying", message="Verificados registros locales en " + table,
                 copied_tables=i, table_count=len(COPY_TABLES))
    return report


def _copy_archive(pg, path: Path, stats: dict, root: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as src:
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    sha = digest.hexdigest()
    backup_id = sha[:48]
    cur = pg.cursor()
    cur.execute("INSERT INTO emergency_archive.manifests"
                "(id,archive_sha256,archive_size,verified,sqlite_summary) "
                "VALUES(%s,%s,%s,FALSE,%s) ON CONFLICT (id) DO NOTHING",
                (backup_id, sha, path.stat().st_size, json.dumps(stats)))
    pg.commit()
    count = 0
    with path.open("rb") as src:
        while True:
            data = src.read(CHUNK_SIZE)
            if not data:
                break
            md5 = hashlib.md5(data).hexdigest()
            cur.execute("INSERT INTO emergency_archive.chunks"
                        "(backup_id,chunk_index,content,content_md5) "
                        "VALUES(%s,%s,%s,%s) ON CONFLICT (backup_id,chunk_index) DO NOTHING",
                        (backup_id, count, data, md5))
            pg.commit()
            count += 1
            _publish(root, state="copying", message="Guardando copia íntegra en Neon de emergencia",
                     archive_chunks_done=count)
    cur.execute("SELECT count(*),COALESCE(sum(octet_length(content)),0),"
                "sum(CASE WHEN md5(content)=content_md5 THEN 0 ELSE 1 END) "
                "FROM emergency_archive.chunks WHERE backup_id=%s", (backup_id,))
    n, size, invalid = cur.fetchone()
    if int(n) != count or int(size) != path.stat().st_size or int(invalid or 0) != 0:
        raise RuntimeError("La copia ZIP remota no coincide con el archivo local.")
    cur.execute("UPDATE emergency_archive.manifests SET verified=TRUE WHERE id=%s",
                (backup_id,))
    pg.commit()
    return backup_id


def _run(root: Path, db_path: Path, url: str) -> None:
    global _RUNNING
    pg = None
    try:
        _publish(root, state="copying", message="Creando copia SQLite consistente",
                 verified=False, copied_tables=0, archive_chunks_done=0)
        archive, stats, backups = _make_archive(root, db_path)
        _publish(root, state="copying", message="Copia local creada, conectando al respaldo",
                 local_archive=archive.name, local_counts=stats,
                 archive_size_bytes=stats["archive_bytes"])
        # A new connection is used ONLY for the emergency project.
        pg = _pg_connect(url)
        cur = pg.cursor()
        cur.execute("SELECT current_database()")
        db_name = str(cur.fetchone()[0])
        if db_name != "neondb":
            raise RuntimeError("La conexión no corresponde a neondb.")
        pg.commit()

        # Open the fresh local backup, never the live doctor's SQLite.
        with tempfile.TemporaryDirectory(prefix="historia_neon_import_", dir=str(backups)) as td:
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extract("historia_clinica.db", path=td)
            snapshot = sqlite3.connect(
                f"file:{(Path(td) / 'historia_clinica.db').as_posix()}?mode=ro", uri=True
            )
            snapshot.row_factory = sqlite3.Row
            try:
                _create_tables(snapshot, pg)
                table_report = _copy_rows(snapshot, pg, root)
            finally:
                snapshot.close()
        _publish(root, state="copying",
                 message="Verificando la copia comprimida y los PDF firmados")
        archive_id = _copy_archive(pg, archive, stats, root)
        _publish(root, state="verified",
                 message="Copia clínica local verificada en Neon de emergencia. "
                         "El Neon oficial sigue activo; NO se ha cambiado automáticamente.",
                 verified=True, backup_id=archive_id, copied_tables=len(COPY_TABLES),
                 local_counts=stats, remote_table_counts=table_report)
    except Exception as exc:
        # Do not persist database URLs, SQL parameters, patients, or credentials.
        _publish(root, state="error", verified=False,
                 message="No se completó la copia: " + type(exc).__name__ +
                         ". El Neon oficial sigue intacto. Revisa la conexión o reintenta.")
        try:
            if pg:
                pg.rollback()
        except Exception:
            pass
    finally:
        if pg:
            try:
                pg.close()
            except Exception:
                pass
        with _LOCK:
            _RUNNING = False


def install(app, root: Path, db_path: Path, base):
    @app.get("/configuracion/neon/copiar", response_class=HTMLResponse)
    def copy_page(request: Request):
        _is_local(request)
        body = """<section class='page-head'><span class='eyebrow'>RESPALDO DE EMERGENCIA</span>
        <h1>Copiar historias desde esta PC</h1>
        <p>Se copiarán todos los registros de SQLite y los PDF firmados locales
        al proyecto Neon de emergencia. El proyecto Oficial no se modifica.</p></section>
        <section class='panel' style='padding:22px'>
        <p><b>Destino fijo:</b> Historia Clinica Emergencia (winter-smoke-49748362).</p>
        <p><b>Origen:</b> copia consistente de la base local de la PC del doctor.</p>
        <p>1. Abre el proyecto de emergencia en Neon y copia su cadena de conexión
        directa (Connection string, base neondb).</p>
        <p>2. Pégala aquí. La contraseña no se guarda en el programa ni se envía
        a GitHub o a ChatGPT.</p>
        <label for='emergency-db-url'><b>Conexión del Neon de emergencia</b></label>
        <input id='emergency-db-url' type='password' spellcheck='false' autocomplete='off'
        placeholder='postgresql://...@ep-noisy-paper-arf28291.../neondb'
        style='width:100%;margin:10px 0;padding:12px' />
        <button id='emergency-copy-start' class='doc-primary' type='button'>
          Crear y subir copia de emergencia
        </button>
        <p id='emergency-copy-status' role='status' aria-live='polite'>
          Consultando el estado del respaldo…
        </p>
        <p><small>Mientras se copia, deja Historia Clínica abierta. La copia no
        cambiará el Neon activo; la conmutación requiere una verificación adicional.
        Si el respaldo se interrumpe, puedes repetirlo sin borrar el original.</small></p>
        <p><a href='/configuracion/neon'>Volver a Neon Oficial y Respaldo</a></p>
        </section>
        <script>
        (function(){
          const button=document.getElementById('emergency-copy-start');
          const field=document.getElementById('emergency-db-url');
          const status=document.getElementById('emergency-copy-status');
          let busy=false;
          async function refresh(){
            try{
              const resp=await fetch('/api/neon/emergency-copy/status',{cache:'no-store'});
              if(!resp.ok)return;
              const data=await resp.json();
              busy=data.state==='copying';
              button.disabled=busy;
              status.textContent=(data.message||'Sin copia')+
                (data.copied_tables?' · Tablas verificadas: '+data.copied_tables:'')+
                (data.local_counts?' · Pacientes: '+(data.local_counts.patients||0):'')+
                (data.state==='verified'?' ✓ Copia verificada':'');
            }catch(err){status.textContent='No se pudo consultar el estado local';}
          }
          button.addEventListener('click',async()=>{
            if(busy)return;
            const database_url=field.value.trim();
            if(!database_url){status.textContent='Falta pegar la conexión del Neon de emergencia.';return;}
            if(!confirm('¿Crear una copia desde esta PC y enviarla al Neon de emergencia? No se cambiará el Neon oficial.'))return;
            button.disabled=true;
            try{
              const resp=await fetch('/api/neon/emergency-copy/start',{
                method:'POST',cache:'no-store',
                headers:{'Content-Type':'application/json','X-Historia-Emergency-Copy':'1'},
                body:JSON.stringify({database_url})
              });
              const data=await resp.json();
              if(!resp.ok||!data.ok)throw new Error(data.message||'No fue posible iniciar la copia.');
              field.value='';
              status.textContent='Copia iniciada desde SQLite local.';
            }catch(err){status.textContent=err.message||'Error al iniciar la copia.';}
            finally{refresh();}
          });
          refresh();setInterval(refresh,2500);
        })();
        </script>"""
        return HTMLResponse(base("Copia de emergencia", body, "neon"))

    @app.get("/api/neon/emergency-copy/status")
    def copy_status(request: Request):
        _is_local(request)
        return JSONResponse(_status(root))

    @app.post("/api/neon/emergency-copy/start")
    async def copy_start(request: Request):
        global _RUNNING
        _is_local(request)
        if request.headers.get("x-historia-emergency-copy") != "1" or \
           "application/json" not in request.headers.get("content-type", ""):
            raise HTTPException(403, detail="Solicitud de copia no autorizada.")
        origin = request.headers.get("origin")
        if origin:
            try:
                o = urllib.parse.urlsplit(origin)
                if o.hostname not in {"127.0.0.1", "localhost"}:
                    raise HTTPException(403, detail="Origen no autorizado.")
            except ValueError:
                raise HTTPException(403, detail="Origen inválido.") from None
        try:
            payload = await request.json()
            url = _validate_destination(payload.get("database_url") if isinstance(payload, dict) else "")
        except RuntimeError as exc:
            return JSONResponse({"ok":False,"message":str(exc)}, status_code=400)
        with _LOCK:
            if _RUNNING:
                return JSONResponse({"ok":False,"message":"Ya existe una copia en ejecución."},status_code=409)
            _RUNNING = True
        thread = threading.Thread(target=_run, args=(root, db_path, url),
                                  daemon=True, name="historia-emergency-local-copy")
        thread.start()
        return JSONResponse({"ok":True, "message":"Copia iniciada desde SQLite. Neon oficial sin cambios."})
