from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_top_function(text: str, name: str, replacement: str) -> str:
    tree = ast.parse(text)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise AssertionError(f"{name}: expected 1 top-level function, found {len(matches)}")
    node = matches[0]
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n"]
    return "".join(lines)


def remove_top_functions(text: str, names: set[str]) -> str:
    tree = ast.parse(text)
    spans = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            spans.append((node.lineno - 1, node.end_lineno))
            found.add(node.name)
    missing = names - found
    if missing:
        raise AssertionError(f"missing functions: {sorted(missing)}")
    lines = text.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    return "".join(lines)


def replace_method(text: str, class_name: str, method_name: str, replacement: str) -> str:
    tree = ast.parse(text)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    if cls is None:
        raise AssertionError(class_name)
    matches = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name]
    if len(matches) != 1:
        raise AssertionError(f"{class_name}.{method_name}: {len(matches)}")
    node = matches[0]
    lines = text.splitlines(keepends=True)
    indent = " " * 4
    rendered = "\n".join(indent + line if line else line for line in replacement.rstrip().splitlines()) + "\n"
    lines[node.lineno - 1:node.end_lineno] = [rendered]
    return "".join(lines)


# ---------------------------------------------------------------------------
# 1) historia_bridge becomes configuration/event identity only.
#    Waiting-room persistence is no longer allowed to touch Neon.
# ---------------------------------------------------------------------------
write("recepcion/app/historia_bridge.py", r'''from __future__ import annotations

import os
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_KEY = "HISTORIA_DATABASE_URL"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: object, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


def _read_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return {}
    return out


def _connection_identity(value: str) -> tuple[str, int, str, str] | None:
    raw = _clean(value, 4000)
    if not raw:
        return None
    try:
        parts = urllib.parse.urlsplit(raw)
        return (
            (parts.hostname or "").lower(),
            int(parts.port or 5432),
            urllib.parse.unquote((parts.path or "/neondb").lstrip("/")) or "neondb",
            urllib.parse.unquote(parts.username or ""),
        )
    except Exception:
        return None


def _database_url() -> str:
    """Return only Historia Neon; never fall back to Reception DATABASE_URL."""
    env = _read_env_file()
    historia_url = _clean(os.getenv(ENV_KEY) or env.get(ENV_KEY), 4000)
    if not historia_url:
        return ""
    reception_url = _clean(os.getenv("DATABASE_URL") or env.get("DATABASE_URL"), 4000)
    historia_id = _connection_identity(historia_url)
    reception_id = _connection_identity(reception_url)
    if historia_id and reception_id and historia_id == reception_id:
        raise RuntimeError(
            "Configuración bloqueada: Historia Clínica y Recepción apuntan a la misma base de datos"
        )
    return historia_url


def _parse_pg_url(url: str) -> dict:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower().split("+", 1)[0] not in {"postgres", "postgresql"}:
        raise RuntimeError("HISTORIA_DATABASE_URL no es PostgreSQL")
    return {
        "user": urllib.parse.unquote(parts.username or ""),
        "password": urllib.parse.unquote(parts.password or ""),
        "host": parts.hostname or "",
        "port": int(parts.port or 5432),
        "database": urllib.parse.unquote((parts.path or "/neondb").lstrip("/")) or "neondb",
    }


def _event_id(reception_patient_id: object, visit_ids: list[object] | None) -> str:
    ids = ",".join(str(x) for x in (visit_ids or []) if x is not None)
    raw = f"reception:{reception_patient_id}:{ids or _now()}"
    return "reception:" + str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


# These are interface placeholders. historia_lan_transport.install() replaces
# them at application startup. They intentionally perform no cloud queue I/O.
def queue_attention(**_kwargs) -> str:
    raise RuntimeError("El transporte LAN de Historia todavía no está instalado")


def cancel_attention(**_kwargs) -> list[str]:
    return []


def restore_attention(**_kwargs) -> list[str]:
    return []


def bridge_status() -> dict:
    return {
        "configured": False,
        "pending": 0,
        "sent": 0,
        "cloud_reachable": False,
        "doctor_online": False,
        "lan_online": False,
        "transport": "not-installed",
        "waiting_queue_transport": "lan_only",
    }
''')


# ---------------------------------------------------------------------------
# 2) One Reception handoff wrapper instead of three route-replacement layers.
# ---------------------------------------------------------------------------
write("recepcion/app/reception_history_bridge.py", r'''from __future__ import annotations

import reception_payment_terminal_manual as _dep_payment_terminal_manual
import reception_payment_terminal as payment_core
import historia_bridge

core = _dep_payment_terminal_manual.core
app = _dep_payment_terminal_manual.app
APP_VERSION = "4.6.25"
core.APP_VERSION = APP_VERSION

_old_batch = None
for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/visits/batch-payment" and "POST" in set(getattr(_route, "methods", set()) or set()):
        _old_batch = getattr(_route, "endpoint", None)
        app.router.routes.remove(_route)
        break
if _old_batch is None:
    raise RuntimeError("No se encontró /api/visits/batch-payment para activar Historia Clínica")

_TYPE_LABELS = {"N": "Nuevo", "S": "Subsecuente", "P": "Procedimiento", "X": "Procedimiento"}


def _patient_status(type_code: object) -> str:
    code = str(type_code or "").strip().upper()
    return "Nuevo" if code == "N" else "Subsecuente" if code == "S" else ""


def _procedure_attention_type(name: object) -> str:
    label = " ".join(str(name or "").strip().split())
    return f"Procedimiento - {label}" if label else "Procedimiento"


def _handoff_item(patient, item: dict, fallback_type: object = "") -> None:
    visit_id = item.get("id")
    if visit_id is None:
        return
    procedure = str(item.get("procedimiento") or "").strip()
    type_code = str(item.get("tipo") or fallback_type or "").strip().upper()
    if procedure:
        attention_type = _procedure_attention_type(procedure)
    else:
        attention_type = _TYPE_LABELS.get(type_code)
        if not attention_type:
            attention_type = "Subsecuente" if type_code == "S" else "Nuevo" if type_code == "N" else "Consulta"
    birth = getattr(patient, "fecha_nacimiento", None)
    historia_bridge.queue_attention(
        reception_patient_id=int(patient.id),
        display_name=str(getattr(patient, "nombre", "") or "Paciente"),
        identification=str(getattr(patient, "cedula", "") or ""),
        attention_type=attention_type,
        patient_status=_patient_status(type_code),
        reception_turn=None,
        visit_ids=[visit_id],
        birth_date=str(birth or ""),
        phone=str(getattr(patient, "celular", "") or ""),
        email=str(getattr(patient, "correo", "") or ""),
        address=str(getattr(patient, "lugar", "") or ""),
    )


@app.post("/api/visits/batch-payment")
def create_visit_batch_payment(
    data: payment_core.V4504VisitBatchPaymentIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result = _old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            items = [x for x in list((result or {}).get("items") or []) if isinstance(x, dict)] if isinstance(result, dict) else []
            for item in items:
                _handoff_item(patient, item, getattr(data, "tipo", ""))
    except Exception as exc:
        try:
            core.audit(db, user, "historia_bridge_pending", f"Puente Historia Clínica pendiente: {type(exc).__name__}")
            db.commit()
        except Exception:
            pass
    return result


@app.get("/api/historia-bridge/status")
def historia_bridge_status(user=core.Depends(core.current_user)):
    return historia_bridge.bridge_status()


@app.get("/api/history-handoff/health")
def history_handoff_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "single_handoff_wrapper": True,
        "waiting_queue_transport": "lan_only",
        "lan_online": bool(state.get("lan_online")),
        "pending": int(state.get("pending") or 0),
    }

PATCH_BOOT_OK = True
''')


# ---------------------------------------------------------------------------
# 3) LAN badge/status says what the architecture really does.
# ---------------------------------------------------------------------------
write("recepcion/app/reception_history_transport.py", r'''from __future__ import annotations

import reception_version_sidebar as _dep_version_sidebar
import historia_bridge
import historia_lan_transport

core = _dep_version_sidebar.core
app = _dep_version_sidebar.app
APP_VERSION = "4.6.25"
core.APP_VERSION = APP_VERSION
historia_lan_transport.install(historia_bridge)

V4520_CSS = r"""
#historiaDoctorBadge.lan{
  border-color:rgba(68,201,124,.58)!important;color:#e3faeb!important;
  background:rgba(27,116,68,.28)!important
}
#historiaDoctorBadge.lan:before{
  background:#35d174!important;box-shadow:0 0 0 3px rgba(53,209,116,.18)!important
}
"""

V4520_JS = r"""
;(()=>{
 if(window.__historyLanStatus)return;window.__historyLanStatus=true;
 const q=(s,r=document)=>r.querySelector(s);
 function ensureBadge(){const c=q('#connectionBadge');let b=q('#historiaDoctorBadge');if(!b&&c){b=document.createElement('span');b.id='historiaDoctorBadge';c.insertAdjacentElement('afterend',b)}return b}
 async function getStatus(){const r=await fetch('/api/historia-bridge/status?t='+Date.now(),{cache:'no-store',headers:{'Cache-Control':'no-cache'}});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
 async function refresh(){const b=ensureBadge();if(!b)return;try{const d=await getStatus();b.className='';const pending=Number(d.pending||0);if(d.lan_online){b.classList.add('lan');b.textContent='Historia: LAN conectada';const ms=Number(d.lan_latency_ms);b.title='PC del doctor accesible por red local'+(d.lan_host?' · '+d.lan_host:'')+(d.lan_version?' · v'+d.lan_version:'')+(Number.isFinite(ms)&&ms>=0?' · '+ms+' ms':'')+' · Pacientes en espera viajan por LAN';return}b.classList.add('error');if(pending>0){b.textContent='Historia: '+pending+' pendientes';b.title='La PC del doctor no responde todavía. Los turnos están protegidos en la cola local y se reintentarán por LAN.'}else{b.textContent='Historia: LAN sin conexión';b.title='La PC del doctor no responde en la red local. La vinculación de fichas por Neon es independiente.'}}catch(err){b.className='error';b.textContent='Historia: sin comprobar';b.title=String(err?.message||err||'')}}
 function boot(){refresh()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();window.addEventListener('focus',boot);document.addEventListener('visibilitychange',()=>{if(!document.hidden)boot()});setInterval(refresh,10000);
})();
"""
core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4520_CSS
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4520_JS

@app.get("/api/v4520/health")
def history_transport_health(user=core.Depends(core.current_user)):
    state = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "lan_online": bool(state.get("lan_online")),
        "local_outbox_pending": int(state.get("pending") or 0),
        "waiting_queue_transport": "lan_only",
        "cloud_queue_write": False,
        "database_schema_changes": False,
    }

PATCH_BOOT_OK = True
''')


# ---------------------------------------------------------------------------
# 4) Remove historical wrappers from the active import graph.
# ---------------------------------------------------------------------------
features_path = "recepcion/app/features_runtime.py"
features = read(features_path)
for name in (
    "reception_history_attention_type",
    "reception_history_patient_details",
    "reception_history_name_lookup",
    "reception_history_requeue_guard",
):
    features = features.replace(f"import {name}\n", "")
    features = features.replace(f"    {name},\n", "")
write(features_path, features)

cancel_path = "recepcion/app/reception_history_cancellation.py"
cancel = read(cancel_path)
cancel = cancel.replace(
    "import reception_history_attention_type as _dep_history_attention_type\n",
    "import reception_history_transport as _dep_history_transport\n",
    1,
)
cancel = cancel.replace("core = _dep_history_attention_type.core\napp = _dep_history_attention_type.app\n", "core = _dep_history_transport.core\napp = _dep_history_transport.app\n", 1)
cancel = cancel.replace("'transport': 'lan-first-cloud-backup'", "'transport': 'lan-only'")
write(cancel_path, cancel)

for rel in (
    "recepcion/app/reception_history_attention_type.py",
    "recepcion/app/reception_history_patient_details.py",
    "recepcion/app/reception_history_name_lookup.py",
    "recepcion/app/reception_history_requeue_guard.py",
):
    path = ROOT / rel
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# 5) Identity/link: no dead autolink path, no v4.6.18 route shadowing,
#    safer demographic synchronization and a clearer linked-state UI.
# ---------------------------------------------------------------------------
id_path = "recepcion/app/reception_history_identity_consolidated.py"
idtext = read(id_path)
if "import threading\n" not in idtext:
    idtext = idtext.replace("import ssl\n", "import ssl\nimport threading\n", 1)
idtext = idtext.replace(
    "_PLACEHOLDER_IDS = {",
    "_SCHEMA_LOCK = threading.Lock()\n_SCHEMA_VALIDATED = set()\n\n_PLACEHOLDER_IDS = {",
    1,
)

idtext = replace_top_function(idtext, "_connect_public", r'''def _connect_public():
    """Única conexión operativa de Recepción hacia Historia: public.*."""
    url = historia_bridge._database_url()
    if not url:
        raise RuntimeError("Historia Clínica no está configurada en esta PC")
    cfg = historia_bridge._parse_pg_url(url)
    if _endpoint_id(cfg.get("host")) != HISTORIA_ENDPOINT_ID:
        raise RuntimeError("Se bloqueó una conexión que no corresponde al Neon de Historia Clínica")
    from pg8000 import dbapi
    conn = dbapi.connect(
        user=cfg["user"], password=cfg["password"], host=cfg["host"],
        port=cfg["port"], database=cfg["database"],
        ssl_context=ssl.create_default_context(), timeout=12,
    )
    key = (str(cfg["host"]).lower(), int(cfg["port"]), str(cfg["database"]), str(cfg["user"]))
    try:
        cur = conn.cursor()
        cur.execute("SET search_path TO public")
        if key not in _SCHEMA_VALIDATED:
            with _SCHEMA_LOCK:
                if key not in _SCHEMA_VALIDATED:
                    cur.execute("""
                        SELECT table_name,column_name
                        FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name IN ('patients','encounters','patient_links')
                    """)
                    found = {}
                    for table, column in cur.fetchall() or []:
                        found.setdefault(str(table), set()).add(str(column))
                    required = {
                        "patients": {"id","name","name_search","birth_date","phone","national_id","national_id_search","email","deleted_at","cloud_updated_at"},
                        "encounters": {"id","patient_id","encounter_date","note_status","deleted_at","cloud_updated_at"},
                        "patient_links": {"reception_patient_id","clinical_patient_id","matched_by","verified","deleted_at","cloud_updated_at"},
                    }
                    missing = {table: sorted(cols-found.get(table,set())) for table, cols in required.items() if not cols.issubset(found.get(table,set()))}
                    if missing:
                        raise RuntimeError("El esquema canónico de Historia está incompleto: " + json.dumps(missing, ensure_ascii=False))
                    _SCHEMA_VALIDATED.add(key)
        conn.commit()
        return conn
    except Exception:
        try: conn.close()
        except Exception: pass
        raise
''')

idtext = remove_top_functions(idtext, {"_same_identity_signature", "_safe_exact_identification_match"})

idtext = replace_top_function(idtext, "_sync_demographics", r'''def _sync_demographics(cur, clinical_patient_id, demo):
    before = _patient_row(cur, clinical_patient_id)
    if not before:
        raise RuntimeError("La ficha vinculada ya no existe en Historia Clínica")
    changes = {}
    warnings = []

    wanted_id = _clean(demo.get("national_id"), 120)
    wanted_id_search = _usable_id(wanted_id)
    current_id = _usable_id(before.get("national_id_search") or before.get("national_id"))
    if wanted_id_search and wanted_id_search != current_id:
        cur.execute("""SELECT id,name,birth_date FROM public.patients
                       WHERE deleted_at IS NULL AND national_id_search=%s AND id<>%s LIMIT 8""",
                    (wanted_id_search, str(clinical_patient_id)))
        conflicts = [_dict_row(cur, r) for r in (cur.fetchall() or [])]
        if conflicts:
            warnings.append("La cédula/identificación no se actualizó porque ya pertenece a otra ficha de Historia.")
        elif current_id:
            warnings.append("La identificación de Recepción difiere de Historia; no se cambió automáticamente.")
        else:
            changes["national_id"] = wanted_id
            changes["national_id_search"] = wanted_id_search

    wanted_name = _clean(demo.get("name"), 260)
    current_name = _clean(before.get("name"), 260)
    if wanted_name and _norm_text(wanted_name) != _norm_text(current_name):
        if current_name:
            warnings.append("El nombre de Recepción difiere de Historia; se conservó el nombre clínico existente.")
        else:
            changes["name"] = wanted_name
            changes["name_search"] = _norm_text(wanted_name)

    wanted_birth = _iso_date(demo.get("birth_date"))
    current_birth = _iso_date(before.get("birth_date"))
    if wanted_birth and wanted_birth != current_birth:
        if current_birth:
            warnings.append("La fecha de nacimiento difiere; se conservó la registrada en Historia.")
        else:
            changes["birth_date"] = wanted_birth

    for field, column, limit in (("address","address",400),("phone","phone",120),("email","email",180)):
        wanted = _clean(demo.get(field), limit)
        current = _clean(before.get(column), limit)
        if wanted and wanted != current:
            changes[column] = wanted

    if changes:
        stamp = datetime.now().isoformat(timespec="seconds")
        assignments, values = [], []
        for column, value in changes.items():
            assignments.append(f'"{column}"=%s'); values.append(value)
        assignments.extend(["updated_at=%s", "cloud_updated_at=now()"])
        values.extend([stamp, str(clinical_patient_id)])
        cur.execute("UPDATE public.patients SET " + ",".join(assignments) + " WHERE id=%s AND deleted_at IS NULL", tuple(values))
    return changes, warnings
''')

idtext = replace_top_function(idtext, "_prepare_identity", r'''def _prepare_identity(db, reception_patient_id, *, sync=True):
    patient = _reception_patient(db, reception_patient_id)
    demo = _demographics(patient)
    conn = _connect_public()
    try:
        cur = conn.cursor()
        linked = _linked_patient(cur, patient.id)
        changed, warnings = {}, []
        if linked is not None and sync:
            _upsert_link(cur, patient.id, linked["id"], linked.get("matched_by") or "reception_verified")
            changed, warnings = _sync_demographics(cur, linked["id"], demo)
            conn.commit()
            linked = _linked_patient(cur, patient.id)
        return {
            "ok": True,
            "reachable": True,
            "reception_patient_id": int(patient.id),
            "reception_name": demo["name"],
            "reception_birth_date": demo["birth_date"],
            "linked": bool(linked),
            "auto_linked": False,
            "duplicate_exact_id_resolved": False,
            "clinical_patient": linked,
            "history_date_count": int((linked or {}).get("history_date_count") or 0),
            "last_history_date": _clean((linked or {}).get("last_history_date"), 20),
            "demographics_changed": changed,
            "warnings": warnings,
        }
    finally:
        try: conn.close()
        except Exception: pass
''')
idtext = idtext.replace("db, reception_patient_id, auto_link=False, sync=False", "db, reception_patient_id, sync=False")
idtext = idtext.replace("db, reception_patient_id, auto_link=False, sync=True", "db, reception_patient_id, sync=True")
idtext = idtext.replace("db, reception_patient_id, auto_link=True, sync=True", "db, reception_patient_id, sync=True")

marker = "# v4.6.18 — fallback de identidad por LAN sin credenciales clínicas en Recepción."
if marker in idtext:
    start = idtext.index(marker)
    end = idtext.index("V4613_CSS =", start)
    idtext = idtext[:start] + idtext[end:]

old_linked = """      if(linked){
        const linkedTitle=attentionModal?'✓ Vinculado con Historia Clínica':'Historia clínica vinculada';
        card.innerHTML=`<div class=\"v4613-history-copy\"><b>${linkedTitle}</b><small>${count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas'}${last?' · Última: '+esc(last):''}</small></div><div class=\"v4613-history-actions\"><span class=\"v4613-history-count\">${count}</span><button type=\"button\" class=\"v4613-btn secondary\">Revisar vínculo</button></div>`;
        card.querySelector('button').onclick=()=>searchDialog(pid,labelFrom(host));
      }else{"""
new_linked = """      if(linked){
        const linkedTitle=attentionModal?'✓ Vinculado con Historia Clínica':'Historia clínica vinculada';
        const cp=d?.clinical_patient||{};
        const identityLine=[text(cp.name||''),cp.national_id?'ID '+text(cp.national_id):''].filter(Boolean).join(' · ');
        const historyLine=(count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas')+(last?' · Última: '+last:'');
        const action=attentionModal?'':`<button type=\"button\" class=\"v4613-btn secondary\">Cambiar vínculo</button>`;
        card.innerHTML=`<div class=\"v4613-history-copy\"><b>${linkedTitle}</b><small>${identityLine?esc(identityLine)+' · ':''}${esc(historyLine)}</small></div><div class=\"v4613-history-actions\"><span class=\"v4613-history-count\">${count}</span>${action}</div>`;
        if(!attentionModal)card.querySelector('button')?.addEventListener('click',()=>searchDialog(pid,labelFrom(host)));
      }else{"""
if old_linked not in idtext:
    raise AssertionError("linked UI block not found")
idtext = idtext.replace(old_linked, new_linked, 1)

old_click = """          card.querySelector('button').onclick=async()=>{
            const btn=card.querySelector('button');btn.disabled=true;btn.textContent='Vinculando…';
            try{
              const linked=await call('/api/historia-identity/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reception_patient_id:Number(pid),clinical_patient_id:String(r.id)})});
              if(linked?.ok===false)throw Error(linked.error||'No se pudo vincular');
              clearPatientCache(pid);closeSearch();await renderAll(true);
              if(typeof window.rpAlert==='function')window.rpAlert('Ficha vinculada correctamente.','Historia Clínica'); else alert('Ficha vinculada correctamente.');
            }catch(err){btn.disabled=false;btn.textContent='Vincular esta ficha';alert(err.message||err)}
          };"""
new_click = """          card.querySelector('button').onclick=async()=>{
            const btn=card.querySelector('button');
            if(btn.dataset.confirm!=='1'){
              btn.dataset.confirm='1';btn.textContent='Confirmar vínculo';btn.style.background='#a96f18';
              const note=document.createElement('small');note.className='v4613-confirm-note';note.textContent='Confirma que esta es la ficha clínica correcta.';card.querySelector('div')?.appendChild(note);return;
            }
            btn.disabled=true;btn.textContent='Vinculando…';
            try{
              const linked=await call('/api/historia-identity/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reception_patient_id:Number(pid),clinical_patient_id:String(r.id)})});
              if(linked?.ok===false)throw Error(linked.error||'No se pudo vincular');
              statusCache.set(Number(pid),{at:Date.now(),data:linked});closeSearch();
              for(const host of modalRoots()){const c=host.querySelector(':scope > .v4613-history-card');if(c&&Number(c.dataset.pid||0)===Number(pid))c.dataset.settled='0'}
              renderAll(false);
              if(typeof window.rpAlert==='function')window.rpAlert('Ficha vinculada correctamente.','Historia Clínica');
            }catch(err){btn.disabled=false;btn.dataset.confirm='0';btn.textContent='Vincular esta ficha';btn.style.background='';results.insertAdjacentHTML('afterbegin',`<div class=\"v4613-empty\">${esc(err.message||'No se pudo vincular.')}</div>`)}
          };"""
if old_click not in idtext:
    raise AssertionError("link click block not found")
idtext = idtext.replace(old_click, new_click, 1)
write(id_path, idtext)


# ---------------------------------------------------------------------------
# 6) Historia LAN never creates a link itself; Reception is the authority.
# ---------------------------------------------------------------------------
lan_path = "historia-clinica/app/lan_bridge.py"
lan = read(lan_path)
lan = replace_method(lan, "LanService", "_resolve_patient", r'''def _resolve_patient(self, conn: sqlite3.Connection, reception_patient_id: str, identification: str) -> str | None:
    """Only consume a link already created by Reception/cloud sync."""
    try:
        row = conn.execute(
            "SELECT clinical_patient_id FROM patient_links WHERE reception_patient_id=? LIMIT 1",
            (reception_patient_id,),
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except sqlite3.Error:
        pass
    return None
''')
write(lan_path, lan)

hist_path = "historia-clinica/app/app.py"
hist = read(hist_path)
hist = replace_top_function(hist, "_queue_validated_link", r'''def _queue_validated_link(conn, row):
    """Trust the clinical id supplied by Reception, with conservative safety checks."""
    linked_id = str(row["clinical_patient_id"] or "").strip()
    if not linked_id:
        return ""
    linked = conn.execute(
        "SELECT id,name,name_search,national_id_search,merged_into_patient_id FROM patients WHERE id=? LIMIT 1",
        (linked_id,),
    ).fetchone()
    if not linked:
        return ""
    merged_to = str(linked["merged_into_patient_id"] or "").strip()
    if merged_to:
        canonical = conn.execute(
            "SELECT id,name,name_search,national_id_search,merged_into_patient_id FROM patients WHERE id=? LIMIT 1",
            (merged_to,),
        ).fetchone()
        if canonical:
            linked_id = str(canonical["id"])
            linked = canonical
            _link_queue_patient(conn, row, linked_id, "repair_merged_patient")
    identification = normalize_search(row["identification"] or "")
    linked_ident = normalize_search(linked["national_id_search"] or "")
    if identification and linked_ident and linked_ident != identification:
        return ""
    return linked_id
''')

auto_block = '''        candidates, reason = _queue_strong_candidates(conn, row)\n        if len(candidates) == 1:\n            patient_id = str(candidates[0]["id"])\n            _link_queue_patient(conn, row, patient_id, "auto_" + (reason or "search"))\n            return RedirectResponse(\n                f"/paciente/{patient_id}/nueva?queue_id={queue_id}",\n                status_code=303,\n            )\n\n'''
if auto_block not in hist:
    raise AssertionError("doctor silent auto-link block not found")
hist = hist.replace(auto_block, "        candidates, reason = _queue_strong_candidates(conn, row)\n        # Sin vínculo de Recepción no adivinamos automáticamente la ficha.\n        # Los candidatos se muestran sólo como fallback manual de emergencia.\n\n", 1)
write(hist_path, hist)


# ---------------------------------------------------------------------------
# 7) Versions/manifests.
# ---------------------------------------------------------------------------
def bump_version(path: str, version: str):
    doc = json.loads(read(path)); doc["version"] = version
    write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def bump_manifest(path: str, version: str, previous: str, purpose: str, notes: dict):
    doc = json.loads(read(path))
    for key in ("version","app_version","runtime_version"):
        if key in doc: doc[key] = version
    n = doc.setdefault("notes", {})
    n["purpose"] = purpose; n["previous_version"] = previous; n.update(notes)
    write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


bump_version("recepcion/app/recepcion-version.json", "4.6.25")
rmanifest_path = "recepcion/app/update_manifest.json"
rmanifest = json.loads(read(rmanifest_path))
removed_files = {
    "reception_history_attention_type.py",
    "reception_history_patient_details.py",
    "reception_history_name_lookup.py",
    "reception_history_requeue_guard.py",
}
for key in ("required_dependencies", "copy"):
    rmanifest[key] = [x for x in rmanifest.get(key, []) if str(x) not in removed_files]
for key in ("version","app_version","runtime_version"):
    if key in rmanifest: rmanifest[key] = "4.6.25"
rnotes = rmanifest.setdefault("notes", {})
rnotes.update({
    "purpose": "Consolida la vinculación Recepción-Historia: Neon sólo identidad/vínculos y LAN sólo Pacientes en espera; elimina capas obsoletas y reduce acciones redundantes.",
    "previous_version": "4.6.24",
    "history_identity_transport": "neon_only",
    "waiting_queue_transport": "lan_only",
    "waiting_queue_cloud_write": False,
    "legacy_cloud_waiting_outbox_removed": True,
    "history_handoff_single_wrapper": True,
    "history_attention_type_wrapper_removed": True,
    "history_patient_details_wrapper_removed": True,
    "history_requeue_guard_removed": True,
    "history_name_lookup_layer_removed": True,
    "history_manual_link_required": True,
    "history_auto_link_exact_identification": False,
    "linked_attention_change_button_removed": True,
    "profile_change_link_explicit": True,
    "manual_link_double_confirmation": True,
    "demographics_name_birth_conflict_guard": True,
    "history_schema_validation_cached": True,
    "procedure_recovery_temporary_layer_removed": True,
    "database_schema_changes": False,
    "patient_data_destructive_changes": False,
    "billing_logic_changes": False,
    "azur_logic_changes": False,
})
write(rmanifest_path, json.dumps(rmanifest, ensure_ascii=False, indent=2) + "\n")

bump_version("historia-clinica/app/historia-version.json", "1.3.88")
bump_manifest(
    "historia-clinica/app/update_manifest.json",
    "1.3.88",
    "1.3.87",
    "Recepción queda como autoridad exclusiva de vínculos; Historia consume el clinical_patient_id por LAN y elimina autovinculaciones silenciosas.",
    {
        "reception_identity_authority": True,
        "lan_identity_exact_id_autolink": False,
        "doctor_silent_auto_link": False,
        "doctor_manual_link_normal_flow": False,
        "doctor_manual_link_emergency_fallback": True,
        "waiting_queue_transport": "lan_only",
        "waiting_queue_accepts_verified_clinical_patient_id": True,
        "database_schema_changes": False,
        "clinical_data_changes": False,
        "patient_data_destructive_changes": False,
        "lan_logic_changes": True,
        "ui_only_release": False,
    },
)

print("PATCH_OK Reception 4.6.25 / Historia 1.3.88")
