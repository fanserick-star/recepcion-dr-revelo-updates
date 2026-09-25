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


# v4.5.41 — FUENTE ÚNICA DEL TURNO.
# La pantalla Inicio de Recepción lee SIEMPRE del cache SQLite local. Antes el
# puente calculaba el turno sobre la sesión de escritura (que podía ser Neon),
# por eso Inicio podía mostrar #6 mientras Historia recibía #10.
#
# Esta función reproduce exactamente la lógica visible de Inicio:
# - agrupa todas las atenciones del día por paciente;
# - el orden del paciente se fija por su PRIMERA atención del día;
# - sólo los grupos que contienen CONSULTA consumen número;
# - los procedimientos aislados muestran "—" y no alteran la secuencia.
def _v4541_consultation_turn(visit):
    if visit is None or str(getattr(visit, "procedimiento", "") or "").strip():
        return None
    fecha = getattr(visit, "fecha", None)
    patient_id = int(getattr(visit, "patient_id", 0) or 0)
    if not fecha or not patient_id:
        return None

    with core.LocalSessionLocal() as local_db:
        rows = list(local_db.scalars(
            core.select(core.Visit)
            .where(core.Visit.fecha == fecha)
            .order_by(core.Visit.id.desc())
        ))

    groups = {}
    order = []
    for row in rows:
        pid = int(getattr(row, "patient_id", 0) or 0)
        if pid not in groups:
            groups[pid] = {
                "first_visit_id": int(getattr(row, "id", 0) or 0),
                "has_consultation": False,
            }
            order.append(pid)
        item = groups[pid]
        rid = int(getattr(row, "id", 0) or 0)
        if not item["first_visit_id"] or (rid and rid < item["first_visit_id"]):
            item["first_visit_id"] = rid
        if not str(getattr(row, "procedimiento", "") or "").strip():
            item["has_consultation"] = True

    ordered_groups = sorted(
        groups.items(),
        key=lambda pair: int(pair[1]["first_visit_id"] or 0),
    )
    turn = 0
    for pid, item in ordered_groups:
        if not item["has_consultation"]:
            continue
        turn += 1
        if int(pid) == patient_id:
            return turn
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
    # v4.5.43: una ficha activada desde el histórico SIEMPRE es subsecuente.
    # historical_summary_for_patient reconoce el vínculo local persistido.
    try:
        _hist_patient = db.get(core.Patient, int(data.patient_id))
        if _hist_patient and core.historical_summary_for_patient(_hist_patient):
            try:
                data.tipo = "S"
            except Exception:
                object.__setattr__(data, "tipo", "S")
    except Exception:
        pass

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
                reception_turn = _v4541_consultation_turn(consultation_visit)

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
def _v4541_repair_recent_historia_handoffs():
    """Repara y reenvía por LAN + nube los handoffs recientes con el turno EXACTO de Inicio."""
    try:
        outbox = historia_bridge.OUTBOX_DB
        if not outbox.is_file():
            return
        cutoff = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
        resend = []

        # IMPORTANTE: Inicio lee SQLite local; la reparación debe leer esa misma
        # fuente. No usar core.get_db() aquí: requiere Request y además podría
        # escoger Neon, que fue precisamente la causa del #10.
        with core.LocalSessionLocal() as db:
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
                        _v4541_consultation_turn(consultation_visit)
                        if has_consultation else None
                    )

                    try:
                        current_turn = (
                            int(payload.get("reception_turn"))
                            if payload.get("reception_turn") not in (None, "")
                            else None
                        )
                    except Exception:
                        current_turn = None

                    needs_repair = (
                        str(payload.get("attention_type") or "") != wanted_type
                        or str(payload.get("patient_status") or "") != wanted_status
                        or current_turn != wanted_turn
                    )
                    if not needs_repair:
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
                    resend.append(payload)

                if resend:
                    local.commit()

        # Ya cerramos el SQLite del outbox para evitar locks. Reencolamos cada
        # evento usando el bridge híbrido: actualiza Neon y además lo manda por
        # LAN inmediatamente a la PC del doctor.
        for payload in resend:
            try:
                historia_bridge.queue_attention(
                    reception_patient_id=payload.get("reception_patient_id"),
                    display_name=payload.get("display_name") or "Paciente",
                    identification=payload.get("identification") or "",
                    attention_type=payload.get("attention_type") or "Consulta",
                    patient_status=payload.get("patient_status") or "",
                    reception_turn=payload.get("reception_turn"),
                    visit_ids=list(payload.get("visit_ids") or []),
                    birth_date=payload.get("birth_date") or "",
                    phone=payload.get("phone") or "",
                    email=payload.get("email") or "",
                    address=payload.get("address") or "",
                )
            except Exception:
                pass

        if resend:
            try:
                historia_bridge.flush_pending(max_items=100, background=True)
            except Exception:
                pass
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


@app.get("/api/v4541/health")
def v4541_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "historia_turn_source": "reception_local_visible_list",
        "startup_repair_uses_local_cache": True,
        "startup_repair_resends_lan_and_cloud": True,
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



# v4.5.43 — activación histórica directa + menú Imprimir visible.
#
# Esta versión se reconstruye desde 4.5.41. NO hereda el parche general de 4.5.42.
# Flujo histórico:
#   clic en ficha histórica -> activar/reutilizar ficha activa -> completar huecos
#   -> guardar vínculo histórico -> tratar la atención como SUBSECUENTE.
# No se cambia ningún esquema ni se fusionan fichas ambiguas automáticamente.

_V4543_BASE_ACTIVATE_HISTORICAL = core.activate_historical_patient

for _route in list(app.router.routes):
    if (
        getattr(_route, "path", None) == "/api/historical/{hid}/activate"
        and "POST" in set(getattr(_route, "methods", set()) or set())
    ):
        app.router.routes.remove(_route)


@app.post("/api/historical/{hid}/activate")
def v4543_activate_historical_patient(
    hid: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    source_key = ""
    try:
        with core.LocalSessionLocal() as ldb:
            historical = ldb.get(core.HistoricalPatient, int(hid))
            if historical is None:
                raise core.HTTPException(404, "Paciente histórico no encontrado")
            source_key = str(historical.source_key or "")
    except core.HTTPException:
        raise
    except Exception:
        source_key = ""

    # La función estable ya sabe:
    # - reutilizar una ficha activa si hay coincidencia segura;
    # - completar cédula/celular/correo/lugar que estén vacíos;
    # - crear una ficha activa solo cuando no existe coincidencia segura.
    result = _V4543_BASE_ACTIVATE_HISTORICAL(int(hid), db, user)

    patient_id = int((result or {}).get("id") or 0)
    if patient_id and source_key:
        core._historical_link_patient(source_key, patient_id)

    # Desde este punto el navegador debe verla como ACTIVA, no como otra
    # ficha histórica seleccionable.
    if isinstance(result, dict):
        historical_summary = result.get("historical")
        result["historical_summary"] = historical_summary
        result["historical"] = False
        result["activated_from_historical"] = True
        result["suggested_type"] = "S"
    return result


V4543_PRINT_MENU_CSS = r"""
/* v4.5.43 — el desplegable Imprimir no puede salir por debajo del cuadro.
   La tabla de Inicio tiene overflow para conservarse usable en la PC antigua;
   por eso el menú abre hacia ARRIBA del botón, donde sí hay espacio visible. */
#inicio .v4486-print-menu{
  position:relative!important;
}
#inicio .v4486-print-menu[open]{
  z-index:2147483000!important;
}
#inicio .v4486-print-pop{
  top:auto!important;
  bottom:calc(100% + 6px)!important;
  right:0!important;
  z-index:2147483001!important;
  margin:0!important;
}
#inicio .v4486-print-pop button{
  position:relative!important;
  z-index:2147483002!important;
}
"""

core.V460_OVERLAY_CSS = (
    (getattr(core, "V460_OVERLAY_CSS", "") or "")
    + "\n"
    + V4543_PRINT_MENU_CSS
)


@app.get("/api/v4543/health")
def v4543_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "rebuilt_from": "4.5.41",
        "inherits_v4542_logic": False,
        "historical_click_activates": True,
        "historical_link_persisted": True,
        "historical_data_completes_empty_fields": True,
        "historical_attention_subsequent": True,
        "print_menu_opens_upward": True,
        "database_schema_changes": False,
        "historia_clinica_changes": False,
    }


# v4.5.44 — el recibo automático respeta exactamente Visit.tipo.
#
# La ruta heredada v4.4.70 intentaba deducir "PRIMERO/SUBSECUENTE" contando
# consultas previas de la ficha activa. Eso falla para un paciente histórico:
# su primera visita en la BD activa puede ser S aunque no haya Visit anterior.
# Desde aquí la fuente de verdad es el tipo YA GUARDADO en la atención:
#   N -> PRIMERO
#   S -> SUBSECUENTE
# La reimpresión desde Inicio ya funcionaba así y queda sin cambios.

for _route in list(app.router.routes):
    if (
        getattr(_route, "path", None) == "/api/v4470/print-visit/{visit_id}"
        and "POST" in set(getattr(_route, "methods", set()) or set())
    ):
        app.router.routes.remove(_route)


class _V4544PrintVisitIn(core.BaseModel):
    pass


@app.post("/api/v4470/print-visit/{visit_id}")
def v4544_print_visit_exact_status(
    visit_id: int,
    data: _V4544PrintVisitIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    visit = db.get(core.Visit, int(visit_id))
    if not visit:
        return {
            "ok": True,
            "printed": False,
            "reason": "visit_not_found",
            "message": "Atención guardada, pero no se encontró el registro para imprimir.",
        }

    if str(getattr(visit, "procedimiento", "") or "").strip():
        return {
            "ok": True,
            "printed": False,
            "reason": "procedure_only",
            "message": "Atención guardada. Los procedimientos no generan recibo.",
        }

    patient = db.get(core.Patient, int(visit.patient_id))
    if not patient:
        return {
            "ok": True,
            "printed": False,
            "reason": "patient_not_found",
            "message": "Atención guardada, pero no se encontró el paciente para imprimir.",
        }

    tipo = str(getattr(visit, "tipo", "") or "").strip().upper()
    # Los registros válidos son N/S. Ante un registro legado raro, S es el
    # valor conservador: nunca inventamos "PRIMERO" por ausencia de filas.
    is_new = tipo == "N"

    turn = _v4541_consultation_turn(visit)

    birth = None
    if getattr(patient, "fecha_nacimiento", None):
        try:
            birth = patient.fecha_nacimiento.strftime("%d/%m/%Y")
        except Exception:
            birth = str(patient.fecha_nacimiento)

    payload = core.ReceiptPrintIn(
        fecha=visit.fecha.strftime("%d/%m/%Y"),
        nombre=str(patient.nombre or "").strip().upper(),
        fecha_nacimiento=birth,
        celular=str(patient.celular or "").strip() or None,
        turno=turn,
        is_new=is_new,
    )

    prefs = core._app_preferences()
    printer = str(prefs.get("printer") or "").strip()
    try:
        used = core._print_receipt_windows(
            payload,
            printer,
            bool(prefs.get("show_blood_pressure", True)),
        )
        return {
            "ok": True,
            "printed": True,
            "printer": used,
            "turno": turn,
            "tipo": tipo,
            "is_new": is_new,
            "message": "Atención guardada. Recibo enviado a la impresora.",
        }
    except Exception as exc:
        try:
            core.logging.getLogger(__name__).warning(
                "v4.5.44: atención %s guardada, impresión falló: %s",
                visit_id, exc,
            )
        except Exception:
            pass
        return {
            "ok": True,
            "printed": False,
            "reason": "printer_error",
            "turno": turn,
            "tipo": tipo,
            "is_new": is_new,
            "error": str(exc)[:240],
            "message": "Atención guardada. No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.",
        }


@app.get("/api/v4544/health")
def v4544_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "automatic_receipt_status_source": "visit.tipo",
        "N_prints_as": "PRIMERO",
        "S_prints_as": "SUBSECUENTE",
        "automatic_receipt_turn_source": "reception_local_visible_list",
        "reprint_status_source": "visit.tipo",
        "database_schema_changes": False,
        "patient_data_changes": False,
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
