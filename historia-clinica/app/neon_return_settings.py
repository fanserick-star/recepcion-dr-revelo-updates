"""Safe local settings panel for switching Historia Neon after clinical parity.

No URLs, secrets, patient names, or record contents are shown in the UI.
Comparison is read-only. Activation is scheduled only after a second explicit
confirmation, and finalized OFFLINE on the next clean app startup.
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
    _verify_complete, _pg_connect, build_plan, switch, _atomic_save
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


def _compare(root):
    """Use read-only transactions on BOTH Neons, never transfer clinical rows."""
    source_url, dest_url, _ = _load_credentials(Path(root))
    src = dst = None
    try:
        src = _pg_connect(source_url)
        dst = _pg_connect(dest_url)
        for pg in (src, dst):
            cur = pg.cursor()
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout='60000ms'")
        report, _ = build_plan(src, dst)
        blocked = False
        try:
            _verify_complete(report)
        except RuntimeError:
            blocked = True
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


def _make_backup(root, db_path):
    """Verified local SQLite snapshot before switching connection settings."""
    path = _file(root, "neon_return_before_switch.sqlite")
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
        # The file is a local approval ticket, created only after a complete
        # read-only parity check, with a verified SQLite backup.
        os.environ["HISTORIA_RETURN_MAINTENANCE_CONFIRMED"] = "1"
        os.environ["HISTORIA_RETURN_BACKUPS_VERIFIED"] = "1"
        lock = _stop_if_unsafe(root, require_backups=True)
        source_url, dest_url, _ = _load_credentials(root)
        source = _pg_connect(source_url)
        official = _pg_connect(dest_url)
        for pg in (source, official):
            cur = pg.cursor()
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout='60000ms'")
        report, _ = build_plan(source, official)
        if report["plan_sha256"] != request["plan_sha256"]:
            raise RuntimeError("Los datos cambiaron: se requiere nueva comparación.")
        _verify_complete(report)
        result = switch(root, lock, source_url, dest_url, report["plan_sha256"], official)
        lock.close(); lock = None
        _file(root, REQUEST_NAME).unlink(missing_ok=True)
        _save_json(root, STATUS_NAME, {
            "state": "official", "message": "Neon Oficial activado tras verificación completa.",
            "at": datetime.now(timezone.utc).isoformat(),
        })
        return result
    except Exception:
        # Fail closed: leave emergency selected and all clinical records intact.
        _save_json(root, STATUS_NAME, {
            "state": "blocked",
            "message": "No se realizó el cambio. La nube de emergencia sigue protegida. Vuelve a comprobar desde Configuración.",
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
<p>Primero se comparan los datos. Si falta algo o hay conflictos, no se activa el cambio.</p>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:15px 0">
<button class="doc-primary" type="button" id="neon-check" {'disabled' if not emergency_active else ''}>Comprobar diferencias</button>
<button class="secondary" type="button" id="neon-authorize" disabled>Confirmar regreso al Oficial</button>
</div>
<p id="neon-return-state" role="status" aria-live="polite">{esc(last_message) if last_message else ('Ya está usando Neon Oficial.' if official_active else 'Sin comprobación reciente.')}</p>
<div id="neon-return-results" style="display:none;margin-top:12px;padding:14px;border-radius:10px;background:var(--surface, #f5f7f9)"></div>
<p style="font-size:13px;color:var(--muted, #667085)">El regreso no afecta las consultas en curso. Si se autoriza, se aplicará al cerrar y abrir nuevamente Historia, únicamente si todo sigue coincidiendo.</p>
</section>
<script>
(function(){{
const check=document.getElementById('neon-check');
const authorize=document.getElementById('neon-authorize');
const msg=document.getElementById('neon-return-state');
const summary=document.getElementById('neon-return-results');
let authorizedPlan='';
function show(s){{msg.textContent=s;}}
async function post(url,data){{
  const response=await fetch(url,{{method:'POST',headers:{{'Content-Type':'application/json','X-Historia-Neon-Control':'1'}},body:JSON.stringify(data||{{}}),cache:'no-store'}});
  const result=await response.json();
  if(!response.ok||!result.ok)throw new Error(result.message||'No se pudo completar la comprobación');
  return result;
}}
if(check)check.addEventListener('click',async()=>{{
  check.disabled=true;authorize.disabled=true;authorizedPlan='';summary.style.display='none';
  show('Comparando Neon de emergencia y Oficial. No se moverán historias…');
  try{{
    const d=await post('/api/neon/return/check',{{}});
    let s=d.summary;
    summary.style.display='block';
    summary.textContent='Registros nuevos por copiar: '+s.missing+' · Registros modificados: '+s.changed+
     ' · Exclusivos del Oficial: '+s.official_only+' · Eliminaciones por revisar: '+s.deletion_conflicts+
     ' · Tablas administrativas pendientes: '+s.manual_review;
    if(d.ready){{authorizedPlan=d.plan_sha256;authorize.disabled=false;show('Todo coincide. Puedes confirmar el regreso al Oficial.');}}
    else show('Cambio protegido: hay diferencias o pendientes que deben revisarse antes de regresar.');
  }}catch(e){{show(e.message||'No se pudo comparar.');}}
  finally{{check.disabled=false;}}
}});
if(authorize)authorize.addEventListener('click',async()=>{{
  if(!authorizedPlan)return;
  if(!confirm('¿Autorizar el regreso al Neon Oficial al cerrar y volver a abrir Historia? Se hará solo si ambos servidores siguen idénticos y el respaldo local se verifica.'))return;
  authorize.disabled=true;check.disabled=true;
  show('Verificando datos y preparando un respaldo local seguro…');
  try{{
    const d=await post('/api/neon/return/authorize',{{plan_sha256:authorizedPlan}});
    show(d.message);
  }}catch(e){{show(e.message||'No fue posible autorizar el regreso.');check.disabled=false;}}
}});
}})();
</script>"""
        return HTMLResponse(base("Servidores Neon", content, "configuracion"))

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
