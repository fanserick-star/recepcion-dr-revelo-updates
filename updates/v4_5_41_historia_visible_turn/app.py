from __future__ import annotations

# v4.5.33 — FUENTE ÚNICA DE VERSIÓN DE RECEPCIÓN.
# El número vive solamente en recepcion-version.json. app.py, /api/version,
# la UI y el launcher derivan de esa fuente. No modifica funciones ni datos.

import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import app_patch_4525 as previous
import app_patch_4508 as bridge_v4508
import historia_bridge

core = previous.core
app = previous.app

_VERSION_PATH = Path(__file__).with_name("recepcion-version.json")
_VERSION_DOC = json.loads(_VERSION_PATH.read_text(encoding="utf-8"))
APP_VERSION = str(_VERSION_DOC["version"]).strip()
if not APP_VERSION:
    raise RuntimeError("recepcion-version.json no contiene una versión válida")

_mod = previous
_seen = set()
for _ in range(720):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)

core.APP_VERSION = APP_VERSION

# app_patch_4525 llevaba el número visual 4.5.25 fijado en CSS.
# Una regla posterior corrige únicamente la etiqueta visible.
V4533_VERSION_CSS = f"""
.v460-version::after,#currentVersionBadge::after{{
  content:"v{APP_VERSION}"!important;
}}
"""
core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4533_VERSION_CSS

# El comprobador viejo leía update_manifest.json y latest-v4.json, lo que
# permitía mostrar una "versión de paquete" distinta del backend real.
# Desde aquí, tanto la pantalla interna como el launcher consultan el MISMO
# canal y usan APP_VERSION, derivado de recepcion-version.json.
_LAUNCHER_APP_CHANNEL = (
    "https://raw.githubusercontent.com/fanserick-star/"
    "recepcion-dr-revelo-updates/main/launcher-v1/app-channel.json"
)

def _canonical_update_channel_status():
    started = time.perf_counter()
    req = urllib.request.Request(
        _LAUNCHER_APP_CHANNEL + f"?rp_ts={time.time_ns()}",
        headers={
            "User-Agent": f"Recepcion-Dr-Revelo/{APP_VERSION}",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        remote = json.loads(response.read(512_000).decode("utf-8-sig"))
    latest = str(remote.get("appVersion") or "").strip()
    if remote.get("product") != "recepcion-dr-revelo" or not latest:
        raise RuntimeError("El canal de Recepción respondió con un manifiesto no válido")

    def _vt(value):
        out = []
        for part in str(value or "0").split("."):
            digits = "".join(ch for ch in part if ch.isdigit())
            out.append(int(digits or 0))
        return tuple((out + [0, 0, 0, 0])[:4])

    return {
        "local": APP_VERSION,
        "latest": latest,
        "update_available": _vt(latest) > _vt(APP_VERSION),
        "latency_ms": (time.perf_counter() - started) * 1000,
    }

# Las funciones antiguas resuelven este nombre en el módulo core en tiempo
# de ejecución, por lo que al sustituirlo dejamos de leer la versión del
# manifest local como si fuera una versión independiente.
core._read_update_channel_status = _canonical_update_channel_status

# Sustituimos únicamente el endpoint de comprobación de actualización para
# eliminar el mensaje ambiguo "paquete X". No cambia ningún flujo clínico.
for _route in list(app.router.routes):
    if (
        getattr(_route, "path", None) == "/api/program/update-now"
        and "POST" in (getattr(_route, "methods", set()) or set())
    ):
        app.router.routes.remove(_route)

@app.post("/api/program/update-now")
def program_update_now_canonical():
    try:
        info = _canonical_update_channel_status()
        if info["update_available"]:
            return {
                "ok": True,
                "update": True,
                "mandatory": True,
                "current": APP_VERSION,
                "latest": info["latest"],
                "message": (
                    f"Actualización obligatoria {info['latest']} disponible. "
                    "Cierra y abre Recepción para instalarla antes de continuar."
                ),
            }
        return {
            "ok": True,
            "update": False,
            "mandatory": True,
            "current": APP_VERSION,
            "latest": info["latest"],
            "message": f"Recepción {APP_VERSION} está actualizada.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "update": False,
            "mandatory": True,
            "current": APP_VERSION,
            "message": f"No se pudo consultar el canal: {str(exc)[:200]}",
        }


# v4.5.39 — el turno mostrado en Historia debe venir de la misma fuente
# de verdad que usa Recepción para su lista y para el recibo térmico.
def _v4539_consultation_turn(db, visit):
    if visit is None or str(getattr(visit, "procedimiento", "") or "").strip():
        return None
    rows = list(db.scalars(
        core.select(core.Visit)
        .where(core.Visit.fecha == visit.fecha)
        .order_by(core.Visit.id)
    ))
    first_by_patient = {}
    for row in rows:
        if str(getattr(row, "procedimiento", "") or "").strip():
            continue
        first_by_patient.setdefault(int(row.patient_id), int(row.id))
    ordered = [
        pid for pid, _first_id in
        sorted(first_by_patient.items(), key=lambda item: item[1])
    ]
    try:
        return ordered.index(int(visit.patient_id)) + 1
    except ValueError:
        return None


# v4.5.35 — corrige exclusivamente el metadato enviado a Historia Clínica.
# N/S describe al paciente; Consulta/Procedimiento se determina por el servicio
# realmente seleccionado. No cambia cobros, facturación ni la UI de Recepción.
for _route in list(app.router.routes):
    if (
        getattr(_route, "path", None) == "/api/visits/batch-payment"
        and "POST" in set(getattr(_route, "methods", set()) or set())
    ):
        app.router.routes.remove(_route)

@app.post("/api/visits/batch-payment")
def v4535_create_visit_batch_payment(
    data: bridge_v4508.payment_core.V4504VisitBatchPaymentIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    result = bridge_v4508._old_batch(data, db, user)

    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            services = list(getattr(data, "services", None) or [])
            procedures = [
                str(getattr(x, "procedimiento", "") or "").strip()
                for x in services
            ]
            has_consultation = (not services) or any(not x for x in procedures)

            items = (
                list((result or {}).get("items") or [])
                if isinstance(result, dict) else []
            )
            visit_ids = [
                x.get("id") for x in items
                if isinstance(x, dict) and x.get("id") is not None
            ]

            type_code = str(getattr(data, "tipo", "") or "").strip().upper()
            if not type_code and items and isinstance(items[0], dict):
                type_code = str(items[0].get("tipo") or "").strip().upper()

            patient_status = {
                "N": "Nuevo",
                "S": "Subsecuente",
            }.get(type_code, "")
            attention_type = "Consulta" if has_consultation else "Procedimiento"

            reception_turn = None
            if has_consultation and visit_ids:
                created_visits = list(db.scalars(
                    core.select(core.Visit).where(core.Visit.id.in_([
                        int(x) for x in visit_ids if x is not None
                    ]))
                ))
                consultation_visit = next(
                    (
                        v for v in sorted(created_visits, key=lambda x: int(x.id))
                        if not str(getattr(v, "procedimiento", "") or "").strip()
                    ),
                    None,
                )
                reception_turn = _v4539_consultation_turn(db, consultation_visit)

            birth = getattr(patient, "fecha_nacimiento", None)
            historia_bridge.queue_attention(
                reception_patient_id=int(patient.id),
                display_name=str(getattr(patient, "nombre", "") or "Paciente"),
                identification=str(getattr(patient, "cedula", "") or ""),
                attention_type=attention_type,
                patient_status=patient_status,
                reception_turn=reception_turn,
                visit_ids=visit_ids,
                birth_date=str(birth or ""),
                phone=str(getattr(patient, "celular", "") or ""),
                email=str(getattr(patient, "correo", "") or ""),
                address=str(getattr(patient, "lugar", "") or ""),
            )
    except Exception as exc:
        try:
            core.audit(
                db, user, "historia_bridge_pending",
                f"Puente Historia Clínica pendiente: {type(exc).__name__}",
            )
            db.commit()
        except Exception:
            pass

    return result


@app.on_event("startup")
def _v4535_repair_recent_historia_handoffs():
    """Reetiqueta eventos de las últimas 48 h y los reenvía a Historia."""
    try:
        outbox = historia_bridge.OUTBOX_DB
        if not outbox.is_file():
            return
        cutoff = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        dbgen = core.get_db()
        db = next(dbgen)
        changed = 0
        try:
            with sqlite3.connect(outbox, timeout=8) as local:
                local.row_factory = sqlite3.Row
                rows = local.execute(
                    "SELECT event_id,payload_json FROM events "
                    "WHERE created_at>=? ORDER BY created_at",
                    (cutoff,),
                ).fetchall()
                for row in rows:
                    try:
                        payload = json.loads(row["payload_json"])
                    except Exception:
                        continue
                    if str(payload.get("action") or "handoff").lower() != "handoff":
                        continue
                    ids = []
                    for value in payload.get("visit_ids") or []:
                        try:
                            ids.append(int(value))
                        except Exception:
                            pass
                    if not ids:
                        continue
                    visits = list(db.scalars(
                        core.select(core.Visit).where(core.Visit.id.in_(ids))
                    ))
                    if not visits:
                        continue
                    has_consultation = any(
                        not str(getattr(v, "procedimiento", "") or "").strip()
                        for v in visits
                    )
                    first_type = str(getattr(visits[0], "tipo", "") or "").strip().upper()
                    wanted_status = {"N":"Nuevo","S":"Subsecuente"}.get(first_type, "")
                    wanted_type = "Consulta" if has_consultation else "Procedimiento"
                    consultation_visit = next(
                        (
                            v for v in sorted(visits, key=lambda x: int(x.id))
                            if not str(getattr(v, "procedimiento", "") or "").strip()
                        ),
                        None,
                    )
                    wanted_turn = (
                        _v4539_consultation_turn(db, consultation_visit)
                        if has_consultation else None
                    )
                    try:
                        current_turn = int(payload.get("reception_turn")) if payload.get("reception_turn") not in (None, "") else None
                    except Exception:
                        current_turn = None
                    if (
                        str(payload.get("attention_type") or "") == wanted_type
                        and str(payload.get("patient_status") or "") == wanted_status
                        and current_turn == wanted_turn
                    ):
                        continue
                    payload["attention_type"] = wanted_type
                    payload["patient_status"] = wanted_status
                    payload["reception_turn"] = wanted_turn
                    local.execute(
                        "UPDATE events SET payload_json=?,sent_at=NULL,attempts=0,"
                        "last_attempt_at=NULL,last_error='' WHERE event_id=?",
                        (
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            row["event_id"],
                        ),
                    )
                    changed += 1
                if changed:
                    local.commit()
        finally:
            try:
                dbgen.close()
            except Exception:
                pass
        if changed:
            historia_bridge.flush_pending(max_items=100, background=True)
    except Exception:
        # El puente jamás debe impedir que Recepción abra.
        pass


@app.get("/api/v4535/health")
def v4535_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_attention_kind_from_services": True,
        "historia_cloud_schema": "historia",
        "repairs_recent_handoffs": True,
        "database_schema_changes": False,
        "reception_ui_changes": False,
    }


@app.get("/api/v4533/health")
def v4533_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "version_chain_synced": True,
        "visual_version_synced": True,
        "database_schema_changes": False,
        "preserves_data_env_excel": True,
    }


# v4.5.36 — recuperación del puente Historia.
# Al iniciar, reintenta el outbox una vez. historia_bridge prepara de forma
# aditiva el índice UNIQUE que necesita el UPSERT remoto y luego el estado
# normal reduce los reintentos automáticos para no golpear Neon cada 10 s.
@app.on_event("startup")
def _v4536_flush_historia_backlog():
    try:
        historia_bridge.flush_pending(max_items=200, background=True)
    except Exception:
        pass



# v4.5.41 — sincroniza a Historia el MISMO número que Recepción dibuja en Inicio.
# Ya no intenta reconstruir el turno desde otra lógica del backend.
class _V4541TurnSyncIn(core.BaseModel):
    fecha: str
    patient_id: int
    turn: int
    visit_ids: list[int] = []


def _v4541_existing_handoff(patient_id: int, fecha: str):
    """Busca el handoff real ya creado para ese paciente/día y conserva su event_id."""
    try:
        outbox = historia_bridge.OUTBOX_DB
        if not outbox.is_file():
            return None
        with sqlite3.connect(outbox, timeout=5) as local:
            local.row_factory = sqlite3.Row
            rows = local.execute(
                "SELECT event_id,payload_json,created_at FROM events ORDER BY created_at DESC LIMIT 300"
            ).fetchall()
        wanted_pid = str(int(patient_id))
        wanted_day = str(fecha or "")[:10]
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                continue
            if str(payload.get("action") or "handoff").lower() != "handoff":
                continue
            if str(payload.get("reception_patient_id") or "") != wanted_pid:
                continue
            queued_day = str(payload.get("queued_at") or "")[:10]
            if wanted_day and queued_day and queued_day != wanted_day:
                continue
            payload["_event_id"] = str(row["event_id"])
            return payload
    except Exception:
        return None
    return None


@app.post("/api/historia-bridge/turn-sync")
def v4541_sync_exact_visible_turn(
    data: _V4541TurnSyncIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    turn = int(data.turn or 0)
    if turn < 1 or turn > 500:
        raise core.HTTPException(400, "Turno inválido")

    patient = db.get(core.Patient, int(data.patient_id))
    if not patient:
        raise core.HTTPException(404, "Paciente no encontrado")

    existing = _v4541_existing_handoff(int(data.patient_id), str(data.fecha))
    visit_ids = []
    if existing:
        for value in existing.get("visit_ids") or []:
            try:
                visit_ids.append(int(value))
            except Exception:
                pass
    if not visit_ids:
        visit_ids = [int(x) for x in (data.visit_ids or []) if x is not None]

    # Si no tenemos IDs no inventamos un evento distinto.
    if not visit_ids:
        return {"ok": False, "synced": False, "reason": "missing_visit_ids"}

    visits = list(db.scalars(
        core.select(core.Visit).where(core.Visit.id.in_(visit_ids))
    ))
    if not visits:
        return {"ok": False, "synced": False, "reason": "visits_not_found"}

    has_consultation = any(
        not str(getattr(v, "procedimiento", "") or "").strip()
        for v in visits
    )
    if not has_consultation:
        return {"ok": True, "synced": False, "procedure_only": True}

    first_type = str(getattr(sorted(visits, key=lambda x: int(x.id))[0], "tipo", "") or "").strip().upper()
    patient_status = {"N": "Nuevo", "S": "Subsecuente"}.get(first_type, "")

    birth = getattr(patient, "fecha_nacimiento", None)
    historia_bridge.queue_attention(
        reception_patient_id=patient.id,
        display_name=str(getattr(patient, "nombre", "") or "Paciente"),
        identification=str(getattr(patient, "cedula", "") or ""),
        attention_type="Consulta",
        patient_status=patient_status,
        reception_turn=turn,
        visit_ids=visit_ids,
        birth_date=str(birth or ""),
        phone=str(getattr(patient, "celular", "") or ""),
        email=str(getattr(patient, "correo", "") or ""),
        address=str(getattr(patient, "lugar", "") or ""),
    )
    return {
        "ok": True,
        "synced": True,
        "patient_id": int(data.patient_id),
        "turn": turn,
        "visit_ids": visit_ids,
    }


V4541_TURN_SYNC_JS = r"""
;(()=>{
  if(window.__v4541ExactTurnSync)return;
  window.__v4541ExactTurnSync=true;

  const sent=new Map();

  async function syncRows(iso,rows){
    if(!Array.isArray(rows)||!rows.length||typeof groupHomeVisits!=='function')return;
    const groups=groupHomeVisits(rows);
    let turn=0;

    for(const g of [...groups].reverse()){
      const visits=Array.isArray(g?.visits)?g.visits:[];
      const consultations=visits.filter(v=>!String(v?.procedimiento||'').trim());
      if(!consultations.length)continue;

      turn++;
      const patientId=Number(g?.patient?.id||consultations[0]?.patient?.id||consultations[0]?.patient_id||0);
      if(!patientId)continue;
      const visitIds=visits.map(v=>Number(v?.id||0)).filter(v=>Number.isFinite(v)&&v>0);
      if(!visitIds.length)continue;

      const cacheKey=String(iso)+'|'+patientId;
      const signature=turn+'|'+visitIds.slice().sort((a,b)=>a-b).join(',');
      if(sent.get(cacheKey)===signature)continue;
      sent.set(cacheKey,signature);

      try{
        const r=await fetch('/api/historia-bridge/turn-sync',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            fecha:String(iso||'').slice(0,10),
            patient_id:patientId,
            turn,
            visit_ids:visitIds
          })
        });
        if(!r.ok)sent.delete(cacheKey);
      }catch(_e){
        sent.delete(cacheKey);
      }
    }
  }

  const previousRender=window.renderHomeDayPayload;
  if(typeof previousRender==='function'){
    window.renderHomeDayPayload=function(iso,d){
      const result=previousRender.apply(this,arguments);
      Promise.resolve().then(()=>syncRows(String(iso||'').slice(0,10),d?.visits||[]));
      return result;
    };
  }

  async function syncToday(){
    try{
      const now=new Date();
      const iso=[
        now.getFullYear(),
        String(now.getMonth()+1).padStart(2,'0'),
        String(now.getDate()).padStart(2,'0')
      ].join('-');
      const r=await fetch('/api/today?fecha='+encodeURIComponent(iso),{cache:'no-store'});
      if(!r.ok)return;
      const d=await r.json();
      await syncRows(iso,d?.visits||[]);
    }catch(_e){}
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',()=>setTimeout(syncToday,900),{once:true});
  }else{
    setTimeout(syncToday,900);
  }
  window.addEventListener('focus',()=>setTimeout(syncToday,300));
})();
"""

core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4541_TURN_SYNC_JS


@app.get("/api/v4541/health")
def v4541_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_turn_source": "reception_visible_home_number",
        "syncs_visible_turn_to_historia": True,
        "procedures_consume_turn": False,
    }


@app.get("/api/v4539/health")
def v4539_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_turn_source": "reception_exact",
        "turn_matches_reception_daily_list": True,
        "procedures_consume_turn": False,
    }


@app.get("/api/v4537/health")
def v4537_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_service_kind_separated": True,
        "patient_status_separated": True,
        "consultations_consume_turn": True,
        "procedures_consume_turn": False,
        "database_schema_changes": False,
        "reception_data_changes": False,
    }


@app.get("/api/v4536/health")
def v4536_health(user=core.Depends(core.current_user)):
    status = historia_bridge.bridge_status()
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_bridge_recovery": True,
        "historia_remote_unique_event": True,
        "historia_pending": int(status.get("pending") or 0),
        "historia_last_error": str(status.get("last_error") or "")[:220],
        "status_retry_seconds": 60,
        "database_schema_changes": False,
        "reception_data_changes": False,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )
