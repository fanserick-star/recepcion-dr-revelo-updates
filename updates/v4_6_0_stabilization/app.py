from __future__ import annotations

# v4.6.0 — runtime histórico congelado.
# Toda la cadena 4.4.x/4.5.x vive dentro de un ZIP inmutable y verificado.
# El ZIP se coloca primero en sys.path para no depender de módulos app_patch_*
# sueltos que hayan quedado de instalaciones anteriores.
import os as _v460_boot_os
import sys as _v460_sys
from pathlib import Path as _V460Path

_V460_APP_ROOT = _V460Path(__file__).resolve().parent
_v460_boot_os.environ["RP_APP_ROOT"] = str(_V460_APP_ROOT)
_V460_RUNTIME_ZIP = _V460_APP_ROOT / "recepcion_legacy_runtime.zip"
if not _V460_RUNTIME_ZIP.is_file():
    raise RuntimeError(
        "Falta recepcion_legacy_runtime.zip. La instalación 4.6.0 está incompleta; "
        "el launcher debe repararla antes de abrir Recepción."
    )
_v460_sys.path.insert(0, str(_V460_RUNTIME_ZIP))


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


# ---------------------------------------------------------------------------
# v4.6.0 — estabilización posterior al runtime histórico
# ---------------------------------------------------------------------------
# Objetivos:
# - una sola implementación efectiva por ruta;
# - retirar superficies antiguas de Cloudflare Tunnel;
# - retirar el actualizador ZIP dentro del backend;
# - aislar la API experimental de datáfono;
# - reemplazar decenas de /api/vXXXX/health por un único diagnóstico;
# - auditar duplicados sin tocar ni fusionar pacientes automáticamente.
import os as _v460_os
import re as _v460_re
from collections import defaultdict as _v460_defaultdict

_V460_DATAPHONE_API_ENABLED = (
    (_v460_os.getenv("RP_DATAPHONE_API_ENABLED") or "0").strip() == "1"
)

def _v460_methods(route):
    return frozenset(
        str(x).upper()
        for x in (getattr(route, "methods", set()) or set())
        if str(x).upper() not in {"HEAD", "OPTIONS"}
    )

def _v460_remove_exact(path: str, methods=None) -> int:
    wanted = {str(x).upper() for x in (methods or [])}
    removed = 0
    for route in list(app.router.routes):
        if getattr(route, "path", None) != path:
            continue
        route_methods = set(_v460_methods(route))
        if wanted and not (wanted & route_methods):
            continue
        try:
            app.router.routes.remove(route)
            removed += 1
        except ValueError:
            pass
    return removed

def _v460_dedupe_routes_keep_last() -> int:
    """Conserva la implementación registrada más tarde de cada ruta/método."""
    seen = set()
    remove = []
    for route in reversed(list(app.router.routes)):
        path = getattr(route, "path", None)
        methods = _v460_methods(route)
        if not path or not methods:
            continue
        key = (str(path), methods)
        if key in seen:
            remove.append(route)
        else:
            seen.add(key)
    for route in remove:
        try:
            app.router.routes.remove(route)
        except ValueError:
            pass
    return len(remove)

# 1) Cloudflare Tunnel antiguo. La Agenda vigente es GitHub Pages + Neon.
_V460_REMOVED_CLOUDFLARE = sum(
    _v460_remove_exact(path)
    for path in (
        "/api/mobile/remote/status",
        "/api/mobile/remote/quick/start",
        "/api/mobile/remote/stable/restart",
        "/api/mobile/remote/stop",
    )
)

# 2) El actualizador ZIP interno queda retirado. El único escritor de programa
#    será Launcher v1 con SHA-256, staging, preflight y rollback.
_v460_remove_exact("/api/update/info")
_v460_remove_exact("/api/update/apply")

@app.get("/api/update/info")
def v460_update_info(user=core.Depends(core.current_user)):
    return {
        "version": APP_VERSION,
        "mode": "launcher-v1-only",
        "automatic": True,
        "message": (
            "Las actualizaciones se verifican y aplican exclusivamente desde "
            "RecepcionLauncher."
        ),
    }

@app.post("/api/update/apply")
def v460_update_apply_retired(user=core.Depends(core.current_user)):
    raise core.HTTPException(
        410,
        "El actualizador ZIP interno fue retirado. Cierra y vuelve a abrir "
        "Recepción para que el Launcher aplique la actualización segura.",
    )

# 3) API genérica/experimental del datáfono: no se expone mientras no exista
#    configuración explícita. El flujo manual Bendo v4.5.x se conserva.
_V460_REMOVED_DATAPHONE = 0
if not _V460_DATAPHONE_API_ENABLED:
    for _path in (
        "/api/v4506/dataphone/config",
        "/api/v4506/dataphone/validate",
        "/api/v4506/dataphone/test",
        "/api/v4506/dataphone/payment-preview",
    ):
        _V460_REMOVED_DATAPHONE += _v460_remove_exact(_path)

# 4) Health endpoints históricos: retiramos todos y dejamos una sola
#    implementación con alias compatible /api/v{numero}/health.
_V460_REMOVED_VERSION_HEALTH = 0
for _route in list(app.router.routes):
    _path = str(getattr(_route, "path", "") or "")
    if _v460_re.fullmatch(r"/api/v\d+/health", _path):
        try:
            app.router.routes.remove(_route)
            _V460_REMOVED_VERSION_HEALTH += 1
        except ValueError:
            pass

# 5) Guard extra de identidad. No añadimos UNIQUE a la tabla todavía: primero
#    impedimos nuevas colisiones normalizadas y auditamos las antiguas.
_V460_CREATE_PATIENT_ENDPOINT = None
for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/patients" and "POST" in _v460_methods(_route):
        _V460_CREATE_PATIENT_ENDPOINT = getattr(_route, "endpoint", None)
_v460_remove_exact("/api/patients", {"POST"})

def _v460_normalize_identification(value, *, foreign=False):
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    if not foreign:
        digits = _v460_re.sub(r"\D", "", raw)
        if digits:
            return digits
    return _v460_re.sub(r"\s+", "", raw)

@app.post("/api/patients")
def v460_create_patient_guarded(
    data: core.PatientIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    values = core.normalize_patient_payload(data)
    cedula = str(values.get("cedula") or "").strip()
    if cedula:
        normalized = _v460_normalize_identification(
            cedula, foreign=bool(getattr(data, "extranjero", False))
        )
        # La comparación se hace en Python únicamente al crear una ficha.
        # Son ~miles de pacientes, no un sondeo periódico de Neon.
        candidates = list(db.execute(
            core.select(core.Patient.id, core.Patient.cedula)
            .where(core.Patient.cedula.is_not(None))
        ).all())
        for patient_id, current in candidates:
            if _v460_normalize_identification(
                current, foreign=bool(getattr(data, "extranjero", False))
            ) == normalized:
                raise core.HTTPException(
                    409,
                    f"Ya existe un paciente con esa identificación (ficha {int(patient_id)}).",
                )
    if _V460_CREATE_PATIENT_ENDPOINT is None:
        raise core.HTTPException(500, "No se encontró el creador estable de pacientes")
    return _V460_CREATE_PATIENT_ENDPOINT(data, db, user)

# 6) Quitamos rutas exactamente duplicadas que sobrevivieron a parches antiguos.
_V460_REMOVED_DUPLICATE_ROUTES = _v460_dedupe_routes_keep_last()

def _v460_require_local(request):
    checker = getattr(core, "_is_loopback_client", None)
    if checker is not None and not checker(request):
        raise core.HTTPException(
            403, "Este diagnóstico solo está disponible en la PC de Recepción"
        )

def _v460_route_duplicates():
    groups = _v460_defaultdict(list)
    for route in app.router.routes:
        path = getattr(route, "path", None)
        methods = _v460_methods(route)
        if not path or not methods:
            continue
        groups[(str(path), tuple(sorted(methods)))].append(
            str(getattr(route, "name", "") or "")
        )
    return [
        {"path": key[0], "methods": list(key[1]), "handlers": names}
        for key, names in groups.items()
        if len(names) > 1
    ]

def _v460_data_audit(db, *, include_samples=False):
    patients = list(db.execute(
        core.select(
            core.Patient.id,
            core.Patient.cedula,
            core.Patient.nombre,
            core.Patient.celular,
            core.Patient.fecha_nacimiento,
        )
    ).all())

    ids = _v460_defaultdict(list)
    name_phone = _v460_defaultdict(list)
    for pid, cedula, nombre, celular, birth in patients:
        key = _v460_normalize_identification(cedula, foreign=False)
        if key:
            ids[key].append(int(pid))
        phone = _v460_re.sub(r"\D", "", str(celular or ""))
        name = " ".join(str(nombre or "").upper().split())
        if phone and name:
            name_phone[(name, phone)].append(int(pid))

    duplicate_identifications = {
        key: rows for key, rows in ids.items() if len(rows) > 1
    }
    duplicate_name_phone = {
        f"{key[0]}|{key[1]}": rows
        for key, rows in name_phone.items()
        if len(rows) > 1
    }

    orphan_visits = int(db.scalar(
        core.select(core.func.count(core.Visit.id))
        .select_from(core.Visit)
        .outerjoin(core.Patient, core.Visit.patient_id == core.Patient.id)
        .where(core.Patient.id.is_(None))
    ) or 0)

    orphan_billing = int(db.scalar(
        core.select(core.func.count(core.BillingRecord.id))
        .select_from(core.BillingRecord)
        .outerjoin(core.Visit, core.BillingRecord.visit_id == core.Visit.id)
        .where(core.Visit.id.is_(None))
    ) or 0)

    appointments = list(db.execute(
        core.select(
            core.Appointment.id,
            core.Appointment.patient_id,
            core.Appointment.fecha,
            core.Appointment.hora,
            core.Appointment.estado,
        )
    ).all())
    appointment_groups = _v460_defaultdict(list)
    for aid, pid, fecha, hora, estado in appointments:
        if str(estado or "").upper() == "CANCELADA":
            continue
        appointment_groups[(int(pid), str(fecha), str(hora))].append(int(aid))
    duplicate_appointments = {
        "|".join(map(str, key)): rows
        for key, rows in appointment_groups.items()
        if len(rows) > 1
    }

    local_orphan_links = 0
    try:
        with core.LocalSessionLocal() as ldb:
            active_ids = set(
                int(x) for x in ldb.scalars(core.select(core.Patient.id)).all()
            )
            links = list(ldb.scalars(core.select(core.HistoricalPatientLink)).all())
            local_orphan_links = sum(
                1 for link in links if int(link.patient_id) not in active_ids
            )
    except Exception:
        local_orphan_links = -1

    result = {
        "patients": len(patients),
        "duplicate_identification_groups": len(duplicate_identifications),
        "duplicate_name_phone_groups": len(duplicate_name_phone),
        "duplicate_appointment_groups": len(duplicate_appointments),
        "orphan_visits": orphan_visits,
        "orphan_billing_records": orphan_billing,
        "orphan_historical_links": local_orphan_links,
        "offline_pending": int(core.queue_count(force=True)),
        "safe_to_add_unique_identification": (
            not duplicate_identifications and orphan_visits == 0
        ),
    }
    if include_samples:
        # Solo IDs; no devolvemos nombres, teléfonos ni identificaciones.
        result["samples"] = {
            "duplicate_identification_patient_ids":
                list(duplicate_identifications.values())[:25],
            "duplicate_name_phone_patient_ids":
                list(duplicate_name_phone.values())[:25],
            "duplicate_appointment_ids":
                list(duplicate_appointments.values())[:25],
        }
    return result

@app.get("/api/system/data-audit")
def v460_data_audit(
    request: core.Request,
    include_samples: bool = False,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    _v460_require_local(request)
    return {
        "ok": True,
        "version": APP_VERSION,
        "read_only": True,
        "audit": _v460_data_audit(db, include_samples=bool(include_samples)),
    }

@app.get("/api/system/health")
def v460_system_health(
    request: core.Request,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    _v460_require_local(request)
    bridge = {}
    try:
        bridge = historia_bridge.bridge_status() or {}
    except Exception as exc:
        bridge = {"last_error": str(exc)[:180]}

    backups = 0
    try:
        backups = len(list(core.Path(core.BACKUP_DIR).glob("recepcion_backup_*.db")))
    except Exception:
        pass

    depth = 0
    seen = set()
    mod = previous
    while mod is not None and id(mod) not in seen and depth < 1000:
        seen.add(id(mod))
        depth += 1
        mod = getattr(mod, "previous", None)

    return {
        "ok": True,
        "version": APP_VERSION,
        "architecture": "v4.6.0-stabilized-runtime",
        "version_source": "recepcion-version.json",
        "runtime_bundle": _V460_RUNTIME_ZIP.name,
        "legacy_runtime_modules": depth,
        "route_duplicates": _v460_route_duplicates(),
        "routes_total": len(app.router.routes),
        "cleanup": {
            "duplicate_routes_removed": _V460_REMOVED_DUPLICATE_ROUTES,
            "version_health_routes_removed": _V460_REMOVED_VERSION_HEALTH,
            "cloudflare_routes_removed": _V460_REMOVED_CLOUDFLARE,
            "experimental_dataphone_routes_removed": _V460_REMOVED_DATAPHONE,
        },
        "updates": {
            "writer": "launcher-v1",
            "legacy_zip_upload_retired": True,
        },
        "agenda": {
            "architecture": "GitHub Pages + Neon Data API",
            "legacy_cloudflare_tunnel": False,
        },
        "bendo": {
            "manual_flow": True,
            "api_enabled": bool(_V460_DATAPHONE_API_ENABLED),
        },
        "whatsapp": {
            "cloud_mode": bool(getattr(core, "WHATSAPP_CLOUD_MODE", True)),
            "local_worker_enabled": bool(
                getattr(core, "WHATSAPP_ENABLED", False)
                and not getattr(core, "WHATSAPP_CLOUD_MODE", True)
            ),
        },
        "offline": {
            "pending": int(core.queue_count(force=True)),
            "backups": backups,
        },
        "historia_bridge": {
            "pending": int(bridge.get("pending") or 0),
            "last_error": str(bridge.get("last_error") or "")[:180],
        },
    }

@app.get("/api/v{legacy_version}/health", include_in_schema=False)
def v460_legacy_health_alias(
    legacy_version: str,
    request: core.Request,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    payload = v460_system_health(request, db, user)
    return {
        "ok": payload["ok"],
        "version": payload["version"],
        "legacy_alias": f"v{legacy_version}",
        "canonical_health": "/api/system/health",
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
