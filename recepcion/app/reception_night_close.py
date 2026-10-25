"""Cierre fiscal nocturno: opt-in, una sola oportunidad, sin reintentos ciegos.

Los envíos al SRI son irreversibles. Este módulo NO activa automáticamente la
emisión al instalar la actualización. Hay que armarla desde Facturación.
La PC debe seguir encendida y Recepción ejecutándose a la hora programada.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core_runtime as core

app = core.app
ECUADOR = timezone(timedelta(hours=-5))
SETTINGS_PATH = Path(core.DATA_DIR) / "night_closing_4888.json"
LOCK = threading.Lock()
_STARTED = False
MAX_GROUPS = 25
CONFIRMATION = "FACTURAR AUTOMATICAMENTE"
# Política del consultorio: el descanso nocturno NUNCA cierra Recepción,
# Historia Clínica, WebView2, Windows ni el servidor LAN. Solo reduce
# consultas a Neon y (si está habilitado) procesa la cola fiscal aprobada.
# Esta regla también forma parte del contrato de regresión en CI.
NIGHT_REST_AUTO_CLOSE_PROGRAMS = False


def _now():
    return datetime.now(ECUADOR)


def _load():
    defaults = {"enabled": False, "hour": 19, "last_date": "", "last_result": {}}
    try:
        obj = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            defaults.update({k: obj[k] for k in defaults if k in obj})
    except (OSError, ValueError, TypeError):
        pass
    defaults["hour"] = 19  # horario estable, modificable solo en nueva versión auditada
    return defaults


def _save(obj):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)
    finally:
        if tmp.exists():
            tmp.unlink()


class ConfigIn(core.BaseModel):
    enabled: bool
    confirmation: str = ""


def _local_summary():
    """Solo SQLite, NUNCA Neon desde la pantalla informativa."""
    today = _now().date()
    with core.LocalSessionLocal() as db:
        grouped = db.execute(
            core.select(core.Visit.patient_id, core.Visit.fecha)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.fecha == today,
                core.BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]),
            )
            .group_by(core.Visit.patient_id, core.Visit.fecha)
        ).all()
        return len(grouped)


@app.get("/api/night-close/status")
def night_close_status(user=core.Depends(core.current_user)):
    cfg = _load()
    return {
        "enabled": bool(cfg["enabled"]),
        "hour": 19,
        "time_zone": "America/Guayaquil",
        "local_groups_to_review": _local_summary(),
        "pending_local_sync": int(core.queue_count()),
        "last_date": str(cfg.get("last_date") or ""),
        "last_result": cfg.get("last_result") or {},
        "requires_pc_on": True,
        "emits_only_current_day": True,
        "auto_close_programs": NIGHT_REST_AUTO_CLOSE_PROGRAMS,
        "programs_remain_open": True,
    }


@app.post("/api/night-close/config")
def night_close_config(data: ConfigIn, user=core.Depends(core.current_user)):
    if str(user.role or "").lower() != "admin":
        raise core.HTTPException(403, "Solo el administrador puede activar facturación automática")
    if data.enabled and str(data.confirmation or "").strip().upper() != CONFIRMATION:
        raise core.HTTPException(
            409, "Debes confirmar expresamente la emisión automática real a AZUR/SRI"
        )
    with LOCK:
        cfg = _load()
        cfg["enabled"] = bool(data.enabled)
        _save(cfg)
    return {
        "ok": True, "enabled": bool(data.enabled), "hour": 19,
        "auto_close_programs": NIGHT_REST_AUTO_CLOSE_PROGRAMS,
        "programs_remain_open": True,
    }


def _candidate_groups(db, today):
    grouped = db.execute(
        core.select(core.Visit.patient_id, core.Visit.fecha, core.func.min(core.Visit.id))
        .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
        .where(
            core.Visit.fecha == today,
            core.Visit.estado == "ACTIVA",
            core.BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]),
        )
        .group_by(core.Visit.patient_id, core.Visit.fecha)
        .order_by(core.func.min(core.Visit.id).asc())
        .limit(MAX_GROUPS + 1)
    ).all()
    if len(grouped) > MAX_GROUPS:
        raise RuntimeError("Más facturas que el máximo automático; requiere revisión manual")
    return grouped


def _prepare(db, patient_id, date_value):
    p = db.get(core.Patient, int(patient_id))
    if p is None:
        return None, "Paciente no encontrado"
    rows = core.billing_group_records(db, int(patient_id), date_value)
    if not rows:
        return None, "Sin líneas pendientes"
    if any(
        str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"}
        or str(v.estado or "").upper() != "ACTIVA"
        or float(v.valor or 0) <= 0
        or v.cancelled_at is not None
        for b, v in rows
    ):
        return None, "Grupo mixto, gratuito, cancelado o incompleto"

    # Un envío anterior (incluso de otras líneas del mismo día) necesita
    # verificación humana; no arriesgar una segunda factura por confusión.
    any_sent = db.scalar(
        core.select(core.AzurEmission.id)
        .where(
            core.AzurEmission.patient_id == int(patient_id),
            core.AzurEmission.fecha == date_value,
        ).limit(1)
    )
    if any_sent:
        return None, "Existe intento previo de AZUR; no duplicar"

    data = core._apply_billing_preference(
        core.BillingGroupIn(patient_id=int(patient_id), fecha=date_value), db
    )
    try:
        core.validate_billing_recipient(data, p)
        payload = core._azur_payload_for_group(data, p, rows)
    except core.HTTPException as exc:
        return None, str(exc.detail)[:130]
    return (p, rows, payload), ""


def _run_one(db, pid, fecha):
    prepared, reason = _prepare(db, pid, fecha)
    if prepared is None:
        return {"patient_id": int(pid), "status": "skipped", "reason": reason}, False
    p, rows, payload = prepared
    group_key = core._azur_group_key_for_rows(int(pid), fecha, rows)
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")).hexdigest()

    # Reservar EN NEON ANTES del POST irrepetible a AZUR.
    record = core.AzurEmission(
        group_key=group_key, patient_id=int(pid), fecha=fecha,
        estado="AUTO_RESERVADA", request_hash=digest,
        response_json=core._azur_pack_response({"auto": True}, rows),
    )
    db.add(record)
    try:
        core.audit(db, "robot_cierre_nocturno", "factura_auto_reservada",
                   f"Grupo {group_key}; {len(rows)} líneas")
        db.commit()
        core.mirror_azur_emission_to_local(record)
    except Exception as exc:
        db.rollback()
        return {"patient_id": int(pid), "status": "blocked",
                "reason": "No se pudo reservar emisión sin duplicados"}, True

    # Una sola llamada; si el resultado es ambiguo jamás volver a enviar.
    try:
        response_raw = core.azur_emit_invoice(
            core.AZUR_BASE_URL, core.AZUR_API_KEY, payload, timeout=25
        )
        response = response_raw.get("data") if isinstance(response_raw, dict) else {}
        response = response if isinstance(response, dict) else {}
        key = str(response.get("claveacceso") or response.get("clave_acceso") or "").strip()
        if response.get("creado") is not True or not key:
            raise RuntimeError("Respuesta de AZUR sin clave confirmada")
        number = core._azur_invoice_number_from_access_key(key) or str(
            response.get("numero_factura") or response.get("numero") or ""
        ).strip()
        record.estado = "EN_PROCESO"
        record.clave_acceso = key
        record.numero_factura = number or None
        record.response_json = core._azur_pack_response(response, rows)
        record.updated_at = datetime.utcnow()
        core.audit(db, "robot_cierre_nocturno", "factura_auto_enviada",
                   f"Grupo {group_key}; autorización SRI pendiente")
        db.commit()
        core.mirror_azur_emission_to_local(record)
        # No marcar BillingRecord EMITIDA antes de AUTORIZADA del SRI.
        return {"patient_id": int(pid), "status": "sent",
                "reason": "Recibida por AZUR; falta autorización SRI"}, False
    except Exception:
        db.rollback()
        try:
            with core.CloudSessionLocal() as recovery:
                current = recovery.scalar(core.select(core.AzurEmission).where(
                    core.AzurEmission.group_key == group_key))
                if current and not current.clave_acceso:
                    current.estado = "AUTO_INCIERTA"
                    recovery.commit()
                    core.mirror_azur_emission_to_local(current)
        except Exception:
            pass  # La reserva ya confirmada sigue bloqueando futuros intentos.
        return {"patient_id": int(pid), "status": "uncertain",
                "reason": "AZUR no confirmó resultado; comprobar manualmente, NO reenviar"}, True


def _execute(today):
    summary = {"date": today.isoformat(), "sent": 0, "skipped": 0,
               "uncertain": 0, "details": [], "status": "complete"}
    if core.queue_count() > 0:
        return {**summary, "status": "deferred", "reason": "Hay cambios pendientes de sincronizar"}
    if _local_summary() == 0:
        # Ninguna factura pendiente en la copia local: no despertar Neon de
        # noche ni abrir una conexión fiscal inútil.
        return {**summary, "status": "complete", "reason": "No hay facturas del día"}
    if not core.cloud_configured() or not core.AZUR_LIVE_EMISSION:
        return {**summary, "status": "deferred", "reason": "Neon o emisión AZUR desactivados"}
    if not core.AZUR_BASE_URL or not core.AZUR_API_KEY:
        return {**summary, "status": "deferred", "reason": "Credenciales AZUR no configuradas"}
    if not core.CloudSessionLocal or not core.check_cloud(force=True):
        return {**summary, "status": "deferred", "reason": "Sin conexión Neon"}
    try:
        with core.CloudSessionLocal() as db:
            if not core._azur_mass_unlocked(db):
                return {**summary, "status": "deferred",
                        "reason": "Falta primera factura SRI autorizada de comprobación"}
            for pid, fecha, _ in _candidate_groups(db, today):
                # Se puede desactivar durante el lote; nunca emitir el siguiente
                # comprobante si el personal reanudó su trabajo.
                with core._state_lock:
                    idle_still = bool(core._state.get("client_idle"))
                if not _load()["enabled"] or not idle_still or core.queue_count() > 0:
                    summary["status"] = "deferred"
                    summary["reason"] = "Cierre interrumpido: actividad, cambios pendientes o modo desactivado"
                    break
                result, stop = _run_one(db, pid, fecha)
                summary["details"].append(result)
                if result["status"] == "sent":
                    summary["sent"] += 1
                elif result["status"] in {"uncertain", "blocked"}:
                    summary["uncertain"] += 1
                else:
                    summary["skipped"] += 1
                if stop:
                    summary["status"] = "needs_review"
                    break
    except Exception:
        summary["status"] = "needs_review"
        summary["reason"] = "Error de facturación automática; revisar sin reenviar"
    return summary


def _tick():
    today_local = _now()
    if today_local.hour < 19 or today_local.hour > 23:
        return
    with LOCK:
        cfg = _load()
        if not cfg["enabled"] or cfg.get("last_date") == today_local.date().isoformat():
            return
        # No emitir mientras Recepción se usa activamente. Evitar procesar
        # formularios o cobrar pacientes a mitad de jornada.
        with core._state_lock:
            app_is_idle = bool(core._state.get("client_idle"))
            idle_secs = time.time() - float(core._state.get("idle_since") or time.time())
        if not app_is_idle or idle_secs < 15 * 60:
            return
        if int(core.queue_count()) > 0:
            return
        # Guardar la ejecución como consumida ANTES del primer POST;
        # tras un corte jamás habrá un segundo lote accidental.
        cfg["last_date"] = today_local.date().isoformat()
        cfg["last_result"] = {"date": cfg["last_date"], "status": "started"}
        _save(cfg)
    try:
        result = _execute(today_local.date())
    finally:
        # La facturación nocturna NO debe dejar conexiones SQL en el pool:
        # de lo contrario Neon permanecería despierto después del cierre.
        with core._state_lock:
            still_idle = bool(core._state.get("client_idle"))
        if still_idle and core.cloud_engine is not None:
            try:
                core.cloud_engine.dispose()
            except Exception:
                pass
    with LOCK:
        cfg = _load()
        cfg["last_result"] = result
        _save(cfg)


def _watch():
    # El vigilante nocturno permanece dentro del proceso actual: nunca intenta
    # terminar procesos ni ventanas. Los usuarios los cierran manualmente.
    while True:
        try:
            _tick()
        except Exception:
            pass
        time.sleep(75)  # Solo reloj/local; no consultas periódicas a Neon.


def install():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_watch, name="reception-night-close", daemon=True).start()
