"""Historia 1.4.78: secure user-confirmed switch to VERIFIED emergency Neon.

The HTTPS/UI credentials never leave the doctor's PC. The official connection
remains recoverable locally, not in GitHub. The app must restart to use the new
synchronizer; on first start the local database is fully re-queued for parity.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from cloud_sync import _pg_connect, _endpoint_id_from_url
from neon_emergency_copy import (
    _is_local, _validate_destination, _status, COPY_TABLES, _quoted
)

EXPECTED_ID = "winter-smoke-49748362"
EXPECTED_ENDPOINT = "ep-noisy-paper-arf28291"


def _target_in_env(root: Path) -> bool:
    path = root / ".env"
    if not path.is_file():
        return False
    found = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            found[k.strip()] = v.strip().strip('"').strip("'")
    return found.get("HISTORIA_NEON_TARGET") == "emergency" and (
        _endpoint_id_from_url(found.get("HISTORIA_DATABASE_URL", ""))
        == EXPECTED_ENDPOINT
    )


def _verify_before_cutover(root: Path, db_path: Path, url: str) -> dict:
    _validate_destination(url)
    # The local verifier must have completed its ZIP upload with checksums.
    local_copy = _status(root)
    if local_copy.get("state") != "verified" or local_copy.get("verified") is not True:
        raise RuntimeError("El respaldo no figura como verificado en esta PC.")
    backup_id = str(local_copy.get("backup_id") or "")
    if not backup_id or len(backup_id) < 32:
        raise RuntimeError("No se encuentra la identificación del respaldo verificado.")
    pg = _pg_connect(url)
    try:
        cur = pg.cursor()
        cur.execute("SELECT current_database()")
        if str(cur.fetchone()[0]) != "neondb":
            raise RuntimeError("La conexión no pertenece al respaldo neondb.")
        cur.execute(
            "SELECT archive_size,verified,sqlite_summary FROM emergency_archive.manifests "
            "WHERE id=%s",
            (backup_id,),
        )
        row = cur.fetchone()
        if not row or row[1] is not True:
            raise RuntimeError("Neon todavía no confirma la copia íntegra.")
        saved_size = int(row[0])
        summary = json.loads(row[2])
        cur.execute(
            "SELECT count(*),COALESCE(sum(octet_length(content)),0),"
            "COUNT(*) FILTER (WHERE md5(content)<>content_md5) "
            "FROM emergency_archive.chunks WHERE backup_id=%s",
            (backup_id,),
        )
        chunks, chunk_size, bad_chunks = cur.fetchone()
        if not chunks or int(chunk_size) != saved_size or int(bad_chunks or 0) != 0:
            raise RuntimeError("Los fragmentos de respaldo no pasaron integridad.")
        local = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            counts = {}
            for table, pk in COPY_TABLES:
                cur.execute("SELECT COUNT(*) FROM public." + _quoted(table))
                remote_count = int(cur.fetchone()[0])
                snapshot_count = int(summary.get(table, -1))
                local_count = int(local.execute(
                    "SELECT COUNT(*) FROM " + _quoted(table)
                ).fetchone()[0])
                # New consultations may have arrived since the SQLite snapshot.
                # A local count smaller than the verified copy is a red flag.
                if snapshot_count < 0 or remote_count != snapshot_count:
                    raise RuntimeError("El respaldo tiene registros incompletos en " + table)
                if local_count < snapshot_count and table not in {"waiting_queue", "clinic_settings"}:
                    raise RuntimeError("La PC tiene menos registros que la copia: " + table)
                counts[table] = local_count
        finally:
            local.close()
        if counts.get("patients", 0) < 10000 or counts.get("encounters", 0) < 10000:
            raise RuntimeError("No se encontró el histórico clínico esperado.")
        pg.commit()
        return counts
    finally:
        pg.close()


def _save_cutover(root: Path, url: str, counts: dict) -> None:
    env_path = root / ".env"
    if not env_path.is_file():
        raise RuntimeError("No se encuentra la configuración privada de Historia.")
    old_content = env_path.read_text(encoding="utf-8-sig")
    parsed = {}
    for raw in old_content.splitlines():
        if "=" not in raw or raw.lstrip().startswith("#"):
            continue
        k, v = raw.split("=", 1)
        parsed[k.strip()] = v.strip().strip('"').strip("'")
    official_url = parsed.get("HISTORIA_DATABASE_URL", "")
    if _endpoint_id_from_url(official_url) != "ep-sweet-mud-arlsk7qa":
        raise RuntimeError("La conexión anterior no coincide con Neon Oficial. Sin cambios.")
    if "\n" in url or "\r" in url or '"' in url or "'" in url:
        raise RuntimeError("La cadena de conexión contiene caracteres inválidos.")
    # Before touching .env, preserve its exact original bytes in private data.
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    original = data / "neon_oficial_antes_de_cambio.env"
    if not original.exists():
        tmp_old = original.with_suffix(".tmp")
        tmp_old.write_text(old_content, encoding="utf-8")
        os.replace(tmp_old, original)
    lines = []
    found = set()
    for raw in old_content.splitlines():
        k = raw.split("=", 1)[0].strip() if "=" in raw else ""
        if k == "HISTORIA_DATABASE_URL":
            lines.append("HISTORIA_DATABASE_URL=" + url)
            found.add(k)
        elif k == "HISTORIA_NEON_TARGET":
            lines.append("HISTORIA_NEON_TARGET=emergency")
            found.add(k)
        elif k == "HISTORIA_OFFICIAL_DATABASE_URL":
            lines.append("HISTORIA_OFFICIAL_DATABASE_URL=" + official_url)
            found.add(k)
        else:
            lines.append(raw)
    if "HISTORIA_DATABASE_URL" not in found:
        raise RuntimeError("Falta HISTORIA_DATABASE_URL; no se modificó nada.")
    if "HISTORIA_NEON_TARGET" not in found:
        lines.append("HISTORIA_NEON_TARGET=emergency")
    if "HISTORIA_OFFICIAL_DATABASE_URL" not in found:
        lines.append("HISTORIA_OFFICIAL_DATABASE_URL=" + official_url)
    tmp = env_path.with_name(env_path.name + ".neon-next")
    try:
        tmp.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
        os.replace(tmp, env_path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    # No credentials in the UI status file.
    status = {
        "target": "emergency", "restart_required": True,
        "verified": True, "copied_counts_at_switch": counts,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = data / "neon_cutover_status.tmp"
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, data / "neon_cutover_status.json")


def install(app, root: Path, db_path: Path, base) -> None:
    @app.get("/configuracion/neon/activar", response_class=HTMLResponse)
    def cutover_page(request: Request):
        _is_local(request)
        selected = _target_in_env(root)
        state = _status(root)
        verified = state.get("state") == "verified" and state.get("verified") is True
        state_label = (
            "Neon de emergencia ya seleccionado: reinicia Historia para conectar."
            if selected else
            ("Respaldo local verificado. Puedes preparar el cambio." if verified
             else "No hay una copia verificada; no se permite cambiar.")
        )
        body = """<section class='page-head'>
        <span class='eyebrow'>CAMBIO SEGURO DE NUBE</span>
        <h1>Activar Neon de emergencia</h1>
        <p>El doctor puede seguir atendiendo mientras compruebas el respaldo.
        Para pasar realmente a la nueva nube debes guardar lo actual, cerrar
        Historia y abrirla otra vez DESPUÉS de preparar el cambio.</p></section>
        <section class='panel' style='padding:22px'>
        <p><b>Estado:</b> """ + state_label + """</p>
        <p>Este procedimiento comprueba los 11 conjuntos clínicos, el ZIP y sus
        fragmentos, conserva el Neon oficial para recuperación y prepara la
        resincronización de todo SQLite, incluidas consultas recientes.</p>
        <p><b>Pega de nuevo la cadena de conexión DIRECTA del Neon de emergencia.</b>
        La contraseña no queda publicada en internet ni en ChatGPT.</p>
        <input type='password' id='cutover-url' autocomplete='off'
         spellcheck='false' style='width:100%;padding:12px;margin:10px 0'
         placeholder='postgresql://...@ep-noisy-paper-arf28291.../neondb'/>
        <button class='doc-primary' type='button' id='cutover-activate'>Verificar y preparar cambio</button>
        <p id='cutover-status' role='status' aria-live='polite'>""" + state_label + """</p>
        <p><small>Si la comprobación falla, se conserva Neon Oficial.
        Si funciona, cierra Historia únicamente después de terminar la
        atención actual y ábrela desde el launcher.</small></p>
        <p><a href='/configuracion/neon'>Volver</a></p></section>
        <script>
        document.getElementById('cutover-activate').addEventListener('click',async()=>{
          const button=document.getElementById('cutover-activate');
          const field=document.getElementById('cutover-url');
          const status=document.getElementById('cutover-status');
          const url=field.value.trim();
          if(!url){status.textContent='Pega la conexión directa del respaldo';return;}
          if(!confirm('¿Confirmas cambiar Historia Clínica al respaldo tras comprobar todos los registros? Se aplicará cuando reinicies Historia.'))return;
          button.disabled=true;
          status.textContent='Verificando registros y copia de emergencia…';
          try{
            const response=await fetch('/api/neon/emergency-cutover/activate',{
              method:'POST',headers:{'Content-Type':'application/json','X-Historia-Emergency-Cutover':'1'},
              body:JSON.stringify({database_url:url}),cache:'no-store'
            });
            const data=await response.json();
            if(!response.ok||!data.ok)throw new Error(data.message||'No se activó el respaldo');
            field.value='';
            status.textContent=data.message;
          }catch(error){status.textContent=error.message||'Error de verificación';}
          finally{button.disabled=false;}
        });
        </script>"""
        return HTMLResponse(base("Activar Neon emergencia", body, "neon"))

    @app.post("/api/neon/emergency-cutover/activate")
    async def activate(request: Request):
        _is_local(request)
        if request.headers.get("x-historia-emergency-cutover") != "1":
            raise HTTPException(403, detail="Acción no autorizada")
        if "application/json" not in request.headers.get("content-type", ""):
            raise HTTPException(403, detail="Contenido no autorizado")
        origin = request.headers.get("origin")
        if origin:
            try:
                if urllib.parse.urlsplit(origin).hostname not in {"127.0.0.1", "localhost"}:
                    raise HTTPException(403, detail="Origen no autorizado")
            except ValueError:
                raise HTTPException(403, detail="Origen no autorizado") from None
        try:
            payload = await request.json()
            url = _validate_destination(payload.get("database_url") if isinstance(payload, dict) else "")
            if _target_in_env(root):
                return JSONResponse({"ok": True, "message": "Neon de emergencia ya seleccionado. Reinicia Historia cuando el doctor termine su consulta."})
            counts = _verify_before_cutover(root, db_path, url)
            _save_cutover(root, url, counts)
            return JSONResponse({
                "ok": True,
                "message": "¡Neon de emergencia verificado y seleccionado! "
                           "El doctor puede terminar su consulta. Guarda, cierra Historia "
                           "y vuelve a abrirla desde el launcher para conectar al respaldo "
                           "y subir los cambios locales recientes.",
            })
        except Exception as exc:
            # Never persist credentials or clinical rows in error messages.
            return JSONResponse({
                "ok": False,
                "message": "No se cambió el Neon: " + type(exc).__name__ +
                           ". Revisa la conexión y la copia verificada.",
            }, status_code=400)
