"""One-action, locally authorized differential return to the Official Neon.

Clinical transfers run OFFLINE at the next restart, never during an appointment.
No credentials, patient records, or names appear in the UI or its status logs.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import socket
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from cloud_sync import _endpoint_id_from_url
from neon_official_return import (
    SOURCE, DESTINATION, _load_credentials, _stop_if_unsafe,
    _verify_complete, _pg_connect, build_plan, switch, _atomic_save,
    check_automatic_return, transfer
)

REQUEST_NAME = "neon_return_request.json"
STATUS_NAME = "neon_return_result.json"
_CACHE = {}  # Read-only summary from this local app process, never credentials.
_CACHE_SECONDS = 600


def _local(request: Request, *, write: bool = False):
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Solo desde la PC del doctor.")
    if write:
        origin = request.headers.get("origin", "")
        if origin:
            parsed = urllib.parse.urlsplit(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                raise HTTPException(403, "Origen no autorizado.")
        if request.headers.get("x-historia-neon-control") != "1":
            raise HTTPException(403, "Confirmación local requerida.")


def _file(root, name):
    return Path(root) / "data" / name


def _save_json(root, name, obj):
    data = json.dumps(obj, ensure_ascii=False, indent=2)
    _atomic_save(_file(root, name), data + "\n")


def _read_json(root, name):
    path = _file(root, name)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def _local_health(db_path):
    # Read-only snapshot of the local SQLite. No reset, no writes.
    con = sqlite3.connect(
        "file:" + Path(db_path).resolve().as_posix() + "?mode=ro",
        uri=True, timeout=4,
    )
    try:
        pending = int(con.execute("SELECT COUNT(*) FROM sync_dirty").fetchone()[0])
        try:
            conflicts = int(con.execute(
                "SELECT COUNT(*) FROM sync_conflicts WHERE resolved_at IS NULL"
            ).fetchone()[0])
        except sqlite3.OperationalError:
            conflicts = 0
        return {"pending": pending, "conflicts": conflicts}
    finally:
        con.close()


def _current(root, db_path):
    """Public, secret-free server status; no DB connections."""
    from cloud_sync import _load_env
    config = _load_env(Path(root))
    current_url = config.get("HISTORIA_DATABASE_URL", "")
    endpoint = _endpoint_id_from_url(current_url)
    if endpoint == SOURCE and config.get("HISTORIA_NEON_TARGET") == "emergency":
        target = "emergency"
    elif endpoint == DESTINATION and config.get("HISTORIA_NEON_TARGET") in ("official", ""):
        target = "official"
    else:
        target = "unknown"
    official_url = config.get("HISTORIA_OFFICIAL_DATABASE_URL", "")
    official_saved = _endpoint_id_from_url(official_url) == DESTINATION
    try:
        health = _local_health(db_path)
    except Exception:
        health = {"pending": -1, "conflicts": -1}
    return {
        "target": target,
        "official_saved": official_saved,
        "pending": health["pending"],
        "conflicts": health["conflicts"],
        "queued_return": bool(_read_json(root, REQUEST_NAME)),
        "last_result": _read_json(root, STATUS_NAME),
    }


def _compare(root, *, include_private=False):
    """Read-only comparison, including the guarded one-action eligibility check."""
    source_url, dest_url, _ = _load_credentials(Path(root))
    src = dst = None
    try:
        src = _pg_connect(source_url)
        dst = _pg_connect(dest_url)
        for pg in (src, dst):
            cur = pg.cursor()
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout='60000ms'")
        report, private = build_plan(src, dst)
        blocked = False
        try:
            _verify_complete(report)
        except RuntimeError:
            blocked = True
        if include_private:
            return report, not blocked, private
        return report, not blocked
    finally:
        for pg in (src, dst):
            if pg is not None:
                with contextlib.suppress(Exception):
                    pg.rollback()
                with contextlib.suppress(Exception):
                    pg.close()


def _summary(report):
    t = report["tables"]
    return {
        "source_rows": sum(x["source_rows"] for x in t.values()),
        "official_rows": sum(x["official_rows"] for x in t.values()),
        "missing": sum(x["missing"] for x in t.values()),
        "changed": sum(x["changed"] for x in t.values()),
        "official_only": sum(x["official_only"] for x in t.values()),
        "deletion_conflicts": sum(
            x["source_deleted_diff"] + x["reactivation_conflicts"]
            for x in t.values()
        ),
        "manual_review": sum(
            1 for x in t.values()
            if x["manual_review"] and (
                x["missing"] or x["changed"] or x["official_only"]
                or x["source_deleted_diff"] or x["reactivation_conflicts"]
            )
        ),
        "schema_issues": sum(
            1 for x in t.values() if x["unshared_source_columns"]
        ),
    }


def _make_backup(root, db_path, *, name="neon_return_before_switch.sqlite"):
    """Verified local SQLite snapshot before switching connection settings."""
    path = _file(root, name)
    src = sqlite3.connect(
        "file:" + Path(db_path).resolve().as_posix() + "?mode=ro", uri=True, timeout=10
    )
    try:
        dest = sqlite3.connect(str(path), timeout=10)
        try:
            src.backup(dest)
            if dest.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("La copia SQLite no pasó la verificación.")
            dest.commit()
        finally:
            dest.close()
    finally:
        src.close()
    if path.stat().st_size < 1024:
        raise RuntimeError("Copia SQLite incompleta.")
    return {"verified": True, "bytes": path.stat().st_size}


def complete_scheduled_return(root, db_path):
    """Called before cloud sync starts, never while History is serving patients."""
    root, db_path = Path(root), Path(db_path)
    request = _read_json(root, REQUEST_NAME)
    if not request:
        return {"state": "not_scheduled"}
    if request.get("target") != "official" or not request.get("plan_sha256"):
        return {"state": "invalid_request"}
    auto_sync = request.get("mode") == "auto_sync"

    # Never run automatically in isolated launcher trial copies.
    if (root / "data" / "neon_return_before_switch.sqlite").is_file() is False:
        return {"state": "backup_missing"}

    lock = source = official = None
    old_env = {k: os.environ.get(k) for k in (
        "HISTORIA_RETURN_MAINTENANCE_CONFIRMED",
        "HISTORIA_RETURN_BACKUPS_VERIFIED",
    )}
    try:
        config = _current(root, db_path)
        if config["target"] == "official":
            _file(root, REQUEST_NAME).unlink(missing_ok=True)
            _save_json(root, STATUS_NAME, {"state": "official", "message": "Neon Oficial ya está activo."})
            return {"state": "official"}
        if config["target"] != "emergency":
            raise RuntimeError("La configuración de nube cambió.")
        # Re-snapshot after the final appointment, including edits made after
        # the button click. Never use the earlier snapshot as the only backup.
        if auto_sync:
            if not _make_backup(root, db_path,
                                name="neon_return_before_copy.sqlite")["verified"]:
                raise RuntimeError("La copia final local no pudo verificarse")
        os.environ["HISTORIA_RETURN_MAINTENANCE_CONFIRMED"] = "1"
        os.environ["HISTORIA_RETURN_BACKUPS_VERIFIED"] = "1"
        lock = _stop_if_unsafe(root, require_backups=True)
        source_url, dest_url, _ = _load_credentials(root)
        source = _pg_connect(source_url)
        official = _pg_connect(dest_url)
        # Source stays read-only. Official must remain writable for the
        # differential copy; the current legacy parity-only path writes none.
        source.cursor().execute("SET TRANSACTION READ ONLY")
        source.cursor().execute("SET LOCAL statement_timeout='60000ms'")
        report, private = build_plan(source, official)
        transferred = {}
        if auto_sync:
            check_automatic_return(report, private)
            cutover = _read_json(root, "neon_cutover_status.json").get("updated_at")
            transferred = transfer(
                source, official, report, private, report["plan_sha256"],
                allow_updates=True, cutover_at=cutover,
            )
            # Never switch unless a fresh, independent parity scan passes.
            report, _ = build_plan(source, official)
            _verify_complete(report)
        else:
            if report["plan_sha256"] != request["plan_sha256"]:
                raise RuntimeError("Los datos cambiaron: se requiere nueva comparación.")
            _verify_complete(report)
        result = switch(root, lock, source_url, dest_url, report["plan_sha256"], official)
        lock.close(); lock = None
        _file(root, REQUEST_NAME).unlink(missing_ok=True)
        _save_json(root, STATUS_NAME, {
            "state": "official",
            "message": "Neon Oficial activado tras sincronizar y verificar las diferencias.",
            "inserted": sum(item["inserted"] for item in transferred.values()),
            "updated": sum(item["updated"] for item in transferred.values()),
            "at": datetime.now(timezone.utc).isoformat(),
        })
        return result
    except Exception:
        # A transfer may have committed verified batches to Official; source
        # remains intact and the next plan skips rows already synchronized.
        _save_json(root, STATUS_NAME, {
            "state": "blocked",
            "message": "No se realizó el cambio. Neon Respaldo sigue activo. Hay diferencias que requieren revisión antes de regresar al Oficial.",
        })
        _file(root, REQUEST_NAME).unlink(missing_ok=True)
        return {"state": "blocked"}
    finally:
        if lock is not None:
            with contextlib.suppress(Exception):
                lock.rollback(); lock.close()
        for pg in (source, official):
            if pg is not None:
                with contextlib.suppress(Exception):
                    pg.rollback(); pg.close()
        for key, previous in old_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def install(app, root, db_path, base):
    root, db_path = Path(root), Path(db_path)

    @app.get("/configuracion/neon", response_class=HTMLResponse)
    def neon_page(request: Request):
        _local(request)
        current = _current(root, db_path)
        emergency_active = current["target"] == "emergency"
        official_active = current["target"] == "official"
        em_style = "border:2px solid #278b78;" if emergency_active else ""
        off_style = "border:2px solid #278b78;" if official_active else ""
        pending_label = (str(current["pending"]) if current["pending"] >= 0 else "Por verificar")
        conflict_label = (str(current["conflicts"]) if current["conflicts"] >= 0 else "Por verificar")
        last_message = str(current["last_result"].get("message") or "")
        # All strings are HTML escaped. Never send credentials or patient data.
        from html import escape as esc
        content = f"""
<section class="page-head"><span class="eyebrow">CONFIGURACIÓN DE NUBE</span>
<h1>Servidores Neon</h1>
<p>Elige tu servidor con seguridad. Sin enlaces, claves ni ajustes técnicos.</p></section>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px">
<section class="panel" style="padding:22px;{em_style}">
<div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
<strong>Neon de emergencia</strong><span style="font-size:12px;font-weight:700">{'● ACTIVO' if emergency_active else 'EN RESERVA'}</span></div>
<p style="margin:10px 0 0;color:var(--muted, #667085)">Respaldo clínico utilizado desde noviembre.</p>
</section>
<section class="panel" style="padding:22px;{off_style}">
<div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
<strong>Neon Oficial</strong><span style="font-size:12px;font-weight:700">{'● ACTIVO' if official_active else 'EN RESERVA'}</span></div>
<p style="margin:10px 0 0;color:var(--muted, #667085)">Servidor principal para el regreso en diciembre.</p>
</section>
</div>
<section class="panel" style="padding:22px;margin-top:16px">
<h2>Regreso seguro al Neon Oficial</h2>
<p>En esta PC: <b>{esc(pending_label)} pendientes</b> · <b>{esc(conflict_label)} conflictos por revisar</b>.</p>
<p>Un solo paso: el programa compara ahora y, al reiniciarse después de la atención, copia únicamente los cambios seguros, los verifica y activa el Oficial.</p>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:15px 0">
<button class="doc-primary" type="button" id="neon-return-oneclick" {'disabled' if not emergency_active else ''}>Sincronizar y cambiar al Neon Oficial</button>
</div>
<p id="neon-return-state" role="status" aria-live="polite">{esc(last_message) if last_message else ('Ya está usando Neon Oficial.' if official_active else 'Sin comprobación reciente.')}</p>
<div id="neon-return-results" style="display:none;margin-top:12px;padding:14px;border-radius:10px;background:var(--surface, #f5f7f9)"></div>
<p style="font-size:13px;color:var(--muted, #667085)">No interrumpe consultas. Termina las atenciones y reinicia Historia desde el launcher. Si hay datos sin subir, vínculos de Recepción distintos, eliminaciones o conflictos con documentos firmados, seguirá activo el Respaldo.</p>
</section>
<script>
(function(){{
const button=document.getElementById('neon-return-oneclick');
const msg=document.getElementById('neon-return-state');
const summary=document.getElementById('neon-return-results');
function show(s){{msg.textContent=s;}}
if(button)button.addEventListener('click',async()=>{{
  if(!confirm('¿Preparar la sincronización de cambios y el regreso al Neon Oficial? El traslado se ejecutará cuando termines de atender, cierres Historia y la vuelvas a abrir. Si detecta conflictos no cambiará de servidor.'))return;
  button.disabled=true;
  show('Comparando servidores y verificando pendientes locales…');
  try{{
    const response=await fetch('/api/neon/return/prepare',{{method:'POST',
      headers:{{'Content-Type':'application/json','X-Historia-Neon-Control':'1'}},
      body:JSON.stringify({{confirm:'SINCRONIZAR_Y_CAMBIAR'}}),cache:'no-store'}});
    const d=await response.json();
    if(!response.ok||!d.ok)throw new Error(d.message||'No se pudo preparar el cambio');
    const x=d.summary;
    summary.style.display='block';
    summary.textContent='Se revisarán '+x.missing+' registros nuevos y '+x.changed+
      ' modificados. Datos exclusivos del Oficial: '+x.official_only+
      '. Conflictos por eliminación: '+x.deletion_conflicts+'.';
    show(d.message);
  }}catch(e){{show(e.message||'El Neon Respaldo continúa activo.');button.disabled=false;}}
}});
}})();
</script>"""
        return HTMLResponse(base("Servidores Neon", content, "configuracion"))

    @app.post("/api/neon/return/prepare")
    async def neon_prepare(request: Request):
        _local(request, write=True)
        try:
            body = await request.json()
            if not isinstance(body, dict) or body.get("confirm") != "SINCRONIZAR_Y_CAMBIAR":
                raise RuntimeError("Confirmacion explicita requerida.")
            status = _current(root, db_path)
            if status["target"] != "emergency" or not status["official_saved"]:
                raise RuntimeError("Las dos conexiones privadas de Neon no estan listas.")
            health = _local_health(db_path)
            if health["pending"] != 0 or health["conflicts"] != 0:
                raise RuntimeError("Termina la sincronizacion local y resuelve sus conflictos primero.")
            report, _, private = _compare(root, include_private=True)
            check_automatic_return(report, private)
            backup = _make_backup(root, db_path)
            if not backup["verified"]:
                raise RuntimeError("No se verifico el respaldo SQLite.")
            _save_json(root, REQUEST_NAME, {
                "target": "official",
                "mode": "auto_sync",
                "plan_sha256": report["plan_sha256"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            _save_json(root, STATUS_NAME, {
                "state": "scheduled",
                "message": "Regreso preparado. Termina de atender, cierra Historia y abre de nuevo desde el launcher. Solo se cambiara tras sincronizar y verificar.",
            })
            return {"ok": True, "summary": _summary(report),
                    "message": "Preparado. Al reiniciar, Historia sincronizara las diferencias seguras y activara Neon Oficial. Si encuentra un conflicto, conservara Neon Respaldo."}
        except Exception:
            return JSONResponse({"ok": False,
                "message": "No se preparo el regreso: hay datos pendientes, vinculos de Recepcion distintos o conflictos que requieren revision. Neon Respaldo sigue activo."}, status_code=409)

    @app.post("/api/neon/return/check")
    def neon_check(request: Request):
        _local(request, write=True)
        try:
            status = _current(root, db_path)
            if status["target"] != "emergency":
                return JSONResponse({"ok": False, "message": "Historia ya no utiliza Neon de emergencia."}, status_code=409)
            if not status["official_saved"]:
                return JSONResponse({"ok": False, "message": "Falta la conexión privada del Neon Oficial. No se cambió nada."}, status_code=409)
            report, parity = _compare(root)
            health = _local_health(db_path)
            ready = bool(parity and health["pending"] == 0 and health["conflicts"] == 0)
            _CACHE[str(root)] = {
                "at": time.monotonic(), "sha": report["plan_sha256"],
                "ready": ready,
            }
            return {"ok": True, "ready": ready, "plan_sha256": report["plan_sha256"],
                    "summary": _summary(report), "pending": health["pending"],
                    "conflicts": health["conflicts"]}
        except Exception:
            return JSONResponse({"ok": False,
                "message": "No se pudo completar la comparación. El Neon activo no cambió."}, status_code=409)

    @app.post("/api/neon/return/authorize")
    async def neon_authorize(request: Request):
        _local(request, write=True)
        try:
            body = await request.json()
            approved = str(body.get("plan_sha256") or "") if isinstance(body, dict) else ""
            cached = _CACHE.get(str(root), {})
            if (not approved or len(approved) != 64
                    or cached.get("sha") != approved or not cached.get("ready")
                    or time.monotonic() - cached.get("at", 0) > _CACHE_SECONDS):
                raise RuntimeError("Debes comprobar las diferencias nuevamente.")
            if _current(root, db_path)["target"] != "emergency":
                raise RuntimeError("El servidor activo cambió.")
            health = _local_health(db_path)
            if health["pending"] != 0 or health["conflicts"] != 0:
                raise RuntimeError("Existen pendientes o conflictos sin resolver.")
            fresh, parity = _compare(root)
            if not parity or fresh["plan_sha256"] != approved:
                raise RuntimeError("La nube cambió; debes comparar nuevamente.")
            # Preserve SQLite before the switch; original cloud is unchanged.
            backup = _make_backup(root, db_path)
            if not backup["verified"]:
                raise RuntimeError("No se pudo validar el respaldo local.")
            _save_json(root, REQUEST_NAME, {
                "target": "official",
                "plan_sha256": approved,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            _save_json(root, STATUS_NAME, {
                "state": "scheduled",
                "message": "Regreso autorizado. Termina la atención, cierra Historia y ábrela desde el launcher. Solo cambiará si todo sigue correcto.",
            })
            _CACHE.pop(str(root), None)
            return {"ok": True,
                    "message": "Preparado. Termina la atención y reinicia Historia desde el launcher. El cambio solo se hará si se verifican todos los datos."}
        except Exception:
            return JSONResponse({"ok": False,
                "message": "No se programó el cambio: hay verificaciones pendientes. Repite la comparación cuando todo esté listo."}, status_code=409)
