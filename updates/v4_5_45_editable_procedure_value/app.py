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



# v4.5.44 — menú Imprimir fuera de la tabla.
# El <details> original vive dentro de la tabla de Inicio y cualquier ancestro
# con overflow puede recortar una de las dos opciones. El menú visible se
# renderiza directamente en document.body con position:fixed, por lo que
# siempre muestra RECIBO + COMPROBANTE completos.
V4544_PRINT_PORTAL_CSS = r"""
.v4544-print-portal{
  position:fixed!important;
  z-index:2147483640!important;
  display:grid!important;
  gap:5px!important;
  min-width:190px!important;
  padding:7px!important;
  border:1px solid #d7e1ec!important;
  border-radius:11px!important;
  background:#fff!important;
  box-shadow:0 14px 34px rgba(35,55,80,.24)!important;
  box-sizing:border-box!important;
}
.v4544-print-portal button{
  width:100%!important;
  min-height:38px!important;
  display:flex!important;
  align-items:center!important;
  gap:8px!important;
  border:0!important;
  border-radius:9px!important;
  background:#fff!important;
  color:#344c69!important;
  padding:9px 10px!important;
  font-size:10px!important;
  font-weight:850!important;
  text-align:left!important;
  white-space:nowrap!important;
  cursor:pointer!important;
}
.v4544-print-portal button:hover{background:#f1f6fb!important}
.v4544-print-portal button:disabled{
  opacity:.42!important;
  cursor:not-allowed!important;
  background:#f7f8fa!important;
}
.v4544-print-portal .v488-home-action-svg{
  width:14px!important;height:14px!important;flex:0 0 14px!important;
}
"""

V4544_PRINT_PORTAL_JS = r"""
;(()=>{
  if(window.__v4544PrintPortal)return;
  window.__v4544PrintPortal=true;

  let portal=null;
  let anchor=null;

  function closePortal(){
    if(portal){try{portal.remove()}catch(_){}}
    portal=null;
    if(anchor){
      try{
        anchor.closest('.v4486-print-menu')?.removeAttribute('open');
        anchor.setAttribute('aria-expanded','false');
      }catch(_){}
    }
    anchor=null;
  }

  function place(){
    if(!portal||!anchor)return;
    const r=anchor.getBoundingClientRect();
    const w=Math.max(190,portal.offsetWidth||190);
    const h=Math.max(86,portal.offsetHeight||86);
    let left=r.right-w;
    left=Math.max(8,Math.min(left,window.innerWidth-w-8));
    let top;
    // Preferimos abrir arriba, pero solo si CABE COMPLETO.
    if(r.top>=h+10) top=r.top-h-6;
    else top=Math.min(window.innerHeight-h-8,r.bottom+6);
    portal.style.left=Math.round(left)+'px';
    portal.style.top=Math.max(8,Math.round(top))+'px';
  }

  function openPortal(summary){
    closePortal();
    const details=summary.closest('.v4486-print-menu');
    const source=details?.querySelector('.v4486-print-pop');
    if(!details||!source)return;

    details.removeAttribute('open');
    anchor=summary;
    anchor.setAttribute('aria-expanded','true');

    portal=document.createElement('div');
    portal.className='v4544-print-portal';
    portal.setAttribute('role','menu');

    [...source.querySelectorAll('button')].forEach(original=>{
      const clone=original.cloneNode(true);
      clone.removeAttribute('style');
      clone.addEventListener('click',()=>{
        setTimeout(closePortal,0);
      },{once:true});
      portal.appendChild(clone);
    });

    document.body.appendChild(portal);
    place();
  }

  document.addEventListener('click',e=>{
    const summary=e.target?.closest?.('.v4486-print-summary');
    if(summary){
      // Impide que <details> abra dentro de la tabla.
      e.preventDefault();
      e.stopPropagation();
      openPortal(summary);
      return;
    }
    if(portal&&!portal.contains(e.target))closePortal();
  },true);

  window.addEventListener('resize',closePortal,{passive:true});
  window.addEventListener('scroll',closePortal,true);
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape')closePortal();
  });
})();
"""

core.V460_OVERLAY_CSS = (
    (getattr(core, "V460_OVERLAY_CSS", "") or "")
    + "\n"
    + V4544_PRINT_PORTAL_CSS
)
core.V460_OVERLAY_JS = (
    (getattr(core, "V460_OVERLAY_JS", "") or "")
    + "\n"
    + V4544_PRINT_PORTAL_JS
)


# ---------------------------------------------------------------------------
# v4.5.45 — valores editables de procedimientos en Nueva atención
# ---------------------------------------------------------------------------
# FULGURACIÓN, CISTOSCOPIA, DILATACIÓN, CIRCUNCISIÓN y cualquier otro
# procedimiento sin valor fijo muestran un campo "Valor de ...". La capa de
# pagos v4.5.4 calculaba el total leyendo .service-price dentro de la tarjeta,
# pero ese campo editable vive FUERA de la tarjeta. Resultado: $100 visible
# en el campo, pero $0.00 en el resumen y Guardar rechazaba la atención.
#
# Esta reparación sincroniza el valor editable con la tarjeta antes de calcular
# el total/guardar y, como segunda defensa, corrige el valor enviado en el
# payload. No modifica base de datos, Neon, Historia Clínica ni facturación.

V4545_EDITABLE_PROCEDURE_JS = r"""
;(()=>{
  if(window.__v4545EditableProcedureFix)return;
  window.__v4545EditableProcedureFix=true;

  const q=(s,r=document)=>r?.querySelector?.(s)||null;
  const qa=(s,r=document)=>r?.querySelectorAll?[...r.querySelectorAll(s)]:[];
  const norm=v=>String(v||'')
    .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/\s+/g,' ').trim().toUpperCase();
  const number=v=>{
    const raw=String(v??'').trim().replace(/\s/g,'').replace(',','.')
      .replace(/[^0-9.\-]/g,'');
    const n=Number(raw||0);
    return Number.isFinite(n)?Math.round(n*100)/100:0;
  };
  const money=v=>'
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
+Number(v||0).toFixed(2);

  function box(){
    return q('.attention-form-modal')
      || [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')]
        .find(b=>[...b.querySelectorAll('h1,h2,h3')]
          .some(h=>norm(h.textContent)==='NUEVA ATENCION'))
      || null;
  }

  function isSelected(card){
    if(!card)return false;
    const check=q('input[type="checkbox"],input[type="radio"]',card);
    return card.classList.contains('selected')
      || card.classList.contains('is-selected')
      || card.getAttribute('aria-pressed')==='true'
      || !!check?.checked;
  }

  function serviceCards(root=box()){
    return root?qa('button.service-card[data-service]',root):[];
  }

  function selectedCards(root=box()){
    return serviceCards(root).filter(isSelected);
  }

  function ignoredValueInput(inp){
    return !!inp.closest(
      '#v4504Payment,#v4504Checkout,#v4525Bendo,'
      +'[data-mix-method],.v4504-mixed,.v4504-card-meta'
    );
  }

  function contextMatches(inp,service,root){
    const target=norm(service);
    let cur=inp.parentElement;
    for(let i=0;cur&&cur!==root&&i<7;i++,cur=cur.parentElement){
      const text=norm(cur.textContent);
      if(!text)continue;
      if(text.includes('VALOR DE '+target))return true;
      if(text.includes('VALOR')&&text.includes(target)&&text.length<260)return true;
    }
    return false;
  }

  function editableInputFor(service,root=box()){
    if(!root||!service)return null;
    const target=norm(service);
    const inputs=qa('input',root).filter(inp=>{
      const type=String(inp.type||'text').toLowerCase();
      if(['checkbox','radio','hidden','date','time','password'].includes(type))return false;
      if(ignoredValueInput(inp))return false;
      return true;
    });

    for(const inp of inputs){
      if(contextMatches(inp,target,root))return inp;
      const own=norm(
        inp.dataset?.service
        ||inp.dataset?.procedure
        ||inp.dataset?.procedimiento
        ||inp.name
        ||inp.id
        ||''
      );
      if(own&&own.includes(target)&&(
        own.includes('VALOR')||own.includes('VALUE')||own.includes('PRICE')
      ))return inp;
    }

    // Fallback deliberadamente conservador: solo si existe UN procedimiento
    // editable seleccionado y UN campo numérico operativo fuera de pagos.
    const editableSelected=selectedCards(root).filter(card=>{
      const price=q('.service-price',card);
      return number(price?.textContent||'')<=0
        ||norm(price?.textContent||'').includes('EDITABLE')
        ||price?.dataset?.v4545Editable==='1';
    });
    const numeric=inputs.filter(inp=>{
      const type=String(inp.type||'').toLowerCase();
      return type==='number'||String(inp.inputMode||'').toLowerCase()==='decimal';
    });
    if(editableSelected.length===1&&numeric.length===1
       &&norm(editableSelected[0].dataset.service)===target){
      return numeric[0];
    }
    return null;
  }

  function valueForCard(card,root=box()){
    if(!card)return 0;
    const service=String(card.dataset.service||'').trim();
    const price=q('.service-price',card);
    const markedEditable=price?.dataset?.v4545Editable==='1';
    const visible=number(price?.textContent||'');
    const editable=markedEditable
      ||visible<=0
      ||norm(price?.textContent||'').includes('EDITABLE');

    if(!editable&&visible>0)return visible;

    const input=editableInputFor(service,root);
    const entered=number(input?.value||0);
    if(price){
      if(!price.dataset.v4545Original)price.dataset.v4545Original=price.textContent||'Valor editable';
      price.dataset.v4545Editable='1';
      price.textContent=entered>0?money(entered):price.dataset.v4545Original;
    }
    card.dataset.v4545Value=entered>0?String(entered):'';
    if(entered>0){
      // Compatibilidad con capas antiguas que han usado distintos nombres.
      card.dataset.price=String(entered);
      card.dataset.value=String(entered);
      card.dataset.valor=String(entered);
    }
    return entered;
  }

  function syncEditableValues(){
    const root=box();
    if(!root)return {root:null,total:0,values:new Map()};
    const values=new Map();
    let total=0;
    for(const card of selectedCards(root)){
      const service=norm(card.dataset.service||'');
      const value=valueForCard(card,root);
      if(service)values.set(service,value);
      total+=Number(value||0);
    }
    total=Math.round(total*100)/100;
    repairVisibleSummary(root,values,total);
    return {root,total,values};
  }

  function repairVisibleSummary(root,values,total){
    const summary=q('#v4504Summary',root);
    if(summary){
      const headTotal=q('.v4504-summary-head strong',summary);
      if(headTotal)headTotal.textContent=money(total);
      const body=q('.v4504-summary-body',summary);
      if(body){
        const children=[...body.children];
        for(let i=0;i<children.length-1;i++){
          const label=children[i];
          const amount=children[i+1];
          if(label.tagName!=='SPAN'||amount.tagName!=='B')continue;
          const key=norm(label.textContent);
          if(values.has(key))amount.textContent=money(values.get(key));
        }
      }
    }
    const legacyTotal=q('#v4504Total',root);
    if(legacyTotal)legacyTotal.textContent=money(total);
  }

  function valueForService(service){
    const root=box();
    if(!root)return 0;
    const target=norm(service);
    const card=serviceCards(root).find(c=>norm(c.dataset.service||'')===target);
    if(!card)return 0;
    return valueForCard(card,root);
  }

  function patchRequestBody(body){
    if(!body||!Array.isArray(body.services))return body;
    for(const item of body.services){
      const procedure=norm(item?.procedimiento||'');
      if(!procedure)continue; // CONSULTA conserva su precio fijo/desc. pareja.
      const value=valueForService(procedure);
      if(value>0)item.valor=value;
    }
    return body;
  }

  // Esta capa se ejecuta después de v4.5.25. Antes de entrar a la cadena
  // histórica de saveAttention, hace visible el precio dentro de la tarjeta.
  // Así el payload() de v4.5.4 deja de interpretar "Valor editable" como $0.
  const stableSave=window.saveAttention;
  if(typeof stableSave==='function'&&!stableSave.__v4545EditableProcedure){
    const wrapped=async function(){
      const synced=syncEditableValues();

      // Si hay procedimiento editable seleccionado y su campo está vacío/0,
      // damos un mensaje concreto en vez del ambiguo "atención con valor".
      for(const card of selectedCards(synced.root)){
        const price=q('.service-price',card);
        const editable=price?.dataset?.v4545Editable==='1'
          ||norm(price?.dataset?.v4545Original||price?.textContent||'').includes('EDITABLE');
        if(editable&&valueForCard(card,synced.root)<=0){
          const name=String(card.dataset.service||'procedimiento').trim();
          alert('Ingresa un valor mayor a $0 para '+name+'.');
          editableInputFor(name,synced.root)?.focus?.();
          return;
        }
      }

      const previousWindowApi=window.api;
      let previousApi=null;
      try{previousApi=api}catch(_e){}
      const downstream=typeof previousWindowApi==='function'
        ?previousWindowApi
        :(typeof previousApi==='function'?previousApi:null);

      if(typeof downstream!=='function'){
        return await stableSave.apply(this,arguments);
      }

      const intercept=async function(url,opt={}){
        const path=String(url||'');
        if(path==='/api/visits/batch'||path==='/api/visits/batch-payment'){
          let body={};
          try{body=JSON.parse(opt?.body||'{}')}catch(_e){body={}}
          patchRequestBody(body);
          return downstream(url,{...opt,body:JSON.stringify(body)});
        }
        return downstream(url,opt);
      };

      try{
        window.api=intercept;
        try{api=intercept}catch(_e){}
        return await stableSave.apply(this,arguments);
      }finally{
        window.api=previousWindowApi;
        try{api=previousApi}catch(_e){}
      }
    };
    wrapped.__v4545EditableProcedure=true;
    window.saveAttention=wrapped;
  }

  function scheduleSync(){
    setTimeout(syncEditableValues,0);
    setTimeout(syncEditableValues,40);
    setTimeout(syncEditableValues,140);
  }

  document.addEventListener('click',event=>{
    if(event.target?.closest?.('.attention-form-modal .service-card')){
      scheduleSync();
    }
  },true);

  document.addEventListener('input',event=>{
    const root=event.target?.closest?.('.attention-form-modal');
    if(!root||ignoredValueInput(event.target))return;
    // Solo reacciona a campos que pertenezcan a una sección "Valor de ...".
    const relevant=selectedCards(root).some(card=>
      contextMatches(event.target,card.dataset.service||'',root)
    );
    if(relevant)scheduleSync();
  },true);

  document.addEventListener('change',event=>{
    if(event.target?.closest?.('.attention-form-modal'))scheduleSync();
  },true);

  // Si el modal ya estaba abierto durante la actualización, también lo repara.
  scheduleSync();

  window.__v4545EditableProcedureTest={
    sync:syncEditableValues,
    valueForService,
    patchRequestBody,
    total:()=>syncEditableValues().total
  };
})();
"""

core.V460_OVERLAY_JS = (
    (getattr(core, "V460_OVERLAY_JS", "") or "")
    + "\n"
    + V4545_EDITABLE_PROCEDURE_JS
)

@app.get("/api/v4545/health")
def v4545_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "editable_procedure_value_synced_to_service_card": True,
        "editable_procedure_payload_repaired": True,
        "zero_value_guard": True,
        "payment_summary_repaired": True,
        "database_schema_changes": False,
        "neon_changes": False,
        "historia_changes": False,
        "patient_data_changes": False,
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
