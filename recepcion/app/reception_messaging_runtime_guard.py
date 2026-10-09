from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import time

import core_runtime as core
import reception_messaging_runtime as messaging

app = core.app
APP_VERSION = "4.6.40"
_INSTALLED = False
_ORIGINAL_INSTALL = messaging.install
_STAGED_STATE_CACHE: dict[int, tuple[float, str]] = {}
_STAGED_STATE_TTL = 30.0


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _remove_route(path: str, method: str = "GET") -> None:
    wanted = str(method).upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) != path:
            continue
        methods = {str(x).upper() for x in (getattr(route, "methods", set()) or set())}
        if wanted in methods:
            app.router.routes.remove(route)


def _event_status(row) -> tuple[str, str]:
    raw = str(row.get("status") or "").upper()
    if row.get("read_at") or raw == "READ":
        return "Leído", "read"
    if row.get("delivered_at") or raw == "DELIVERED":
        return "Entregado", "delivered"
    if row.get("sent_at") or raw == "SENT":
        return "Enviado", "sent"
    if raw in {"FAILED", "ERROR"}:
        return "Error", "error"
    if raw in {"SENDING", "PROCESSING"}:
        return "Enviando", "sending"
    if raw in {"CANCELLED", "CANCELED", "EXPIRED"}:
        return "Cancelado", "muted"
    return "Programado", "planned"


def _response_status(row) -> tuple[str, str]:
    raw = str(row.get("interpretation") or "REVISAR").upper()
    if raw == "CONFIRMADO":
        return "Confirmado", "confirmed"
    if raw == "NO_ASISTIRA":
        return "No asistirá", "no-show"
    if raw == "REVISAR" and not row.get("resolved_at"):
        return "Por revisar", "review"
    if row.get("resolved_at"):
        return "Revisado", "resolved"
    return raw.replace("_", " ").title(), "muted"


def _source_where(source_type: str, source_id: int, fecha: date | None, hora: str) -> tuple[str, dict]:
    params = {"source_type": str(source_type), "source_id": int(source_id)}
    direct = "(source_type=:source_type AND source_id=:source_id)"
    if not fecha or not hora:
        return direct, params
    params["appointment_date"] = fecha.isoformat()
    params["appointment_time"] = str(hora)[:5]
    # El segundo criterio recupera mensajes de citas heredadas cuyo source_id
    # todavía pertenece al registro externo antiguo. El horario es único dentro
    # de la agenda, por lo que no mezcla dos pacientes del mismo bloque.
    return (
        direct
        + " OR (appointment_date=:appointment_date "
          "AND left(appointment_time::text,5)=:appointment_time)",
        params,
    )


def _cloud_history(*, source_type: str, source_id: int, fecha: date | None, hora: str) -> tuple[list[dict], str]:
    if not core.cloud_configured() or not core.CloudSessionLocal or core.FORCE_OFFLINE:
        return [], "Neon no está disponible"
    where, params = _source_where(source_type, source_id, fecha, hora)
    events: list[dict] = []
    seen: set[str] = set()
    try:
        with core.CloudSessionLocal() as db:
            outbound = db.execute(core.text(f"""
                SELECT message_id,template_name,status,created_at,due_at,
                       sent_at,delivered_at,read_at,error_text,
                       appointment_date,appointment_time,patient_name,
                       source_type,source_id
                FROM whatsapp_cloud.events
                WHERE {where}
                ORDER BY created_at ASC,message_id ASC
            """), params).mappings().all()
            for index, row in enumerate(outbound, 1):
                key = str(row.get("message_id") or "") or "|".join((
                    str(row.get("template_name") or ""),
                    _iso(row.get("created_at")),
                    _iso(row.get("due_at")),
                ))
                if key in seen:
                    continue
                seen.add(key)
                status_label, tone = _event_status(row)
                sent = row.get("sent_at")
                timestamp = sent or row.get("due_at") or row.get("created_at")
                events.append({
                    "id": f"cloud:{index}:{key[:80]}",
                    "direction": "outbound",
                    "kind": "template",
                    "message_id": str(row.get("message_id") or ""),
                    "template": str(row.get("template_name") or ""),
                    "label": messaging._template_label(row.get("template_name")),
                    "status": str(row.get("status") or ""),
                    "status_label": status_label,
                    "tone": tone,
                    "created_at": _iso(row.get("created_at")),
                    "due_at": _iso(row.get("due_at")),
                    "sent_at": _iso(row.get("sent_at")),
                    "delivered_at": _iso(row.get("delivered_at")),
                    "read_at": _iso(row.get("read_at")),
                    "timestamp": _iso(timestamp),
                    "error": str(row.get("error_text") or "")[:300],
                })

            if core._wa_inbound_table_ready(db):
                inbound = db.execute(core.text(f"""
                    SELECT id,message_id,message_type,raw_text,transcription,
                           interpretation,confidence,received_at,resolved_at,
                           resolution,apply_result,media_id,media_mime_type,
                           appointment_date,appointment_time,patient_name,
                           source_type,source_id
                    FROM whatsapp_cloud.inbound_responses
                    WHERE {where}
                    ORDER BY received_at ASC,id ASC
                """), params).mappings().all()
                for row in inbound:
                    key = "inbound:" + str(row.get("id") or row.get("message_id") or "")
                    if key in seen:
                        continue
                    seen.add(key)
                    audio = str(row.get("message_type") or "").lower() == "audio"
                    body = str((row.get("transcription") if audio else row.get("raw_text")) or "").strip()
                    status_label, tone = _response_status(row)
                    events.append({
                        "id": key,
                        "response_id": int(row.get("id") or 0),
                        "direction": "inbound",
                        "kind": "audio" if audio else "text",
                        "message_id": str(row.get("message_id") or ""),
                        "label": "Audio del paciente" if audio else "Respuesta del paciente",
                        "body": body[:1200],
                        "status": str(row.get("interpretation") or "REVISAR"),
                        "status_label": status_label,
                        "tone": tone,
                        "confidence": int(row.get("confidence") or 0),
                        "received_at": _iso(row.get("received_at")),
                        "resolved_at": _iso(row.get("resolved_at")),
                        "resolution": str(row.get("resolution") or ""),
                        "apply_result": str(row.get("apply_result") or ""),
                        "timestamp": _iso(row.get("received_at")),
                    })
        events.sort(key=lambda item: str(item.get("timestamp") or "9999-12-31T23:59:59"))
        return events, ""
    except Exception as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:220]}"


def _local_intention_state(item: dict, *, cloud_available: bool) -> dict:
    """La cola SQLite es intención de envío, nunca aceptación de Meta.

    Cloud disponible + hora vencida + ausencia de evento = SIN CONSTANCIA.
    Cloud desconectado = NO VERIFICABLE. No ejecutar alarmas ni reenviar.
    """
    event = dict(item)
    event["source"] = "local_schedule_only"
    raw = str(event.get("status") or "").upper()
    if raw in {"CANCELLED", "CANCELED", "EXPIRED"}:
        return event
    if raw in {"FAILED", "ERROR"}:
        event["status_label"], event["tone"] = "Error local", "error"
        return event
    if raw in {"SENT", "DELIVERED", "READ"}:
        # Un estado local tampoco garantiza confirmación en Meta.
        event["status_label"], event["tone"] = "Enviado local · Meta sin comprobar", "planned"
        return event
    if not cloud_available:
        event.update(status="UNVERIFIED", status_label="No verificable",
                     tone="muted", error="No se pudo consultar WhatsApp Cloud.")
        return event
    try:
        due = datetime.fromisoformat(str(event.get("due_at") or "").replace("Z", "+00:00"))
        ec = timezone(timedelta(hours=-5))
        if due.tzinfo is None:
            due = due.replace(tzinfo=ec)
        lag_seconds = (datetime.now(ec) - due.astimezone(ec)).total_seconds()
    except (ValueError, TypeError):
        lag_seconds = 0
    if lag_seconds > 180:
        planned_at = str(event.get("due_at") or "")[:16].replace("T", " ")
        event.update(status="NO_CLOUD_EVENT", status_label="Sin constancia de envío",
                     tone="error", due_at="",
                     error="Previsto para " + planned_at + " (hora Ecuador), pero no existe registro de envío en Meta Cloud. No se reenvía.")
    elif lag_seconds >= 0:
        event.update(status="AWAITING", status_label="Pendiente de envío",
                     tone="planned", error="Todavía no existe un envío confirmado por Meta.")
    else:
        event.update(status="SCHEDULED_LOCAL", status_label="Programado",
                     tone="planned", error="")
    return event


def _pending_signal_safe() -> bool:
    try:
        return bool(core._wa_alarm_signal_state().get("pending"))
    except Exception:
        return False


def _history_payload(*, source_type: str, source_id: int, fecha: date | None, hora: str, patient_name: str) -> dict:
    events, cloud_error = _cloud_history(
        source_type=source_type,
        source_id=source_id,
        fecha=fecha,
        hora=hora,
    )
    # El panel real utiliza /api/messaging/*, NO /whatsapp-timeline.
    # Completar cada plantilla SIN evento Cloud con el plan administrativo,
    # pero nunca presentar PENDING local como estado de entrega.
    cloud_templates = {
        str(item.get("template") or "") for item in events
        if item.get("direction") == "outbound" and not item.get("local_fallback")
    }
    for local in messaging._local_outbox_history(source_type, source_id):
        if str(local.get("template") or "") in cloud_templates:
            continue
        events.append(_local_intention_state(local, cloud_available=not bool(cloud_error)))
    events.sort(key=lambda item: str(item.get("timestamp") or item.get("due_at") or "9999"))
    return {
        "available": not bool(cloud_error) or bool(events),
        "cloud_available": not bool(cloud_error),
        "cloud_error": cloud_error,
        "source_type": str(source_type),
        "source_id": int(source_id),
        "patient_name": str(patient_name or ""),
        "outbound_count": sum(1 for item in events if item.get("direction") == "outbound"),
        "inbound_count": sum(1 for item in events if item.get("direction") == "inbound"),
        "events": events,
        "message_source": "whatsapp_cloud.events_and_local_intentions",
        "active_messaging_panel": "4.8.22",
        "alarm_signal_pending": _pending_signal_safe(),
    }


def _latest_staged_states(item_ids) -> dict[int, str]:
    """Estado visual de citas sin ficha derivado de la última respuesta decisiva.

    ConfirmafyAgendaItem no tiene columna ``estado``: las confirmaciones 24/7 se
    guardan en whatsapp_cloud.inbound_responses. Consultamos todos los bloques
    visibles en una sola consulta y cacheamos 30 s para no convertir Agenda en
    un N+1 contra Neon. Un fallo de nube conserva el último estado conocido.
    """
    ids = sorted({int(x) for x in (item_ids or []) if int(x or 0) > 0})
    if not ids:
        return {}
    now = time.time()
    result: dict[int, str] = {}
    missing: list[int] = []
    for item_id in ids:
        cached = _STAGED_STATE_CACHE.get(item_id)
        if cached and now - cached[0] <= _STAGED_STATE_TTL:
            result[item_id] = cached[1]
        else:
            missing.append(item_id)
    if not missing:
        return result

    stale_fallback = {
        item_id: _STAGED_STATE_CACHE[item_id][1]
        for item_id in missing
        if item_id in _STAGED_STATE_CACHE
    }
    if not core.cloud_configured() or not core.CloudSessionLocal or core.FORCE_OFFLINE:
        result.update(stale_fallback)
        return result

    params = {f"id{i}": item_id for i, item_id in enumerate(missing)}
    placeholders = ",".join(f":id{i}" for i in range(len(missing)))
    try:
        with core.CloudSessionLocal() as db:
            if not core._wa_inbound_table_ready(db):
                result.update(stale_fallback)
                return result
            rows = db.execute(core.text(f"""
                SELECT DISTINCT ON (source_id)
                       source_id, upper(coalesce(interpretation,'')) AS interpretation
                FROM whatsapp_cloud.inbound_responses
                WHERE source_type='staged'
                  AND source_id IN ({placeholders})
                  AND upper(coalesce(interpretation,'')) IN ('CONFIRMADO','NO_ASISTIRA')
                ORDER BY source_id, received_at DESC, id DESC
            """), params).mappings().all()
        decisive = {
            int(row.get("source_id")): (
                "CONFIRMADA"
                if str(row.get("interpretation") or "").upper() == "CONFIRMADO"
                else "NO_ASISTIRA"
            )
            for row in rows
            if int(row.get("source_id") or 0) > 0
        }
        for item_id in missing:
            state = decisive.get(item_id, "PENDIENTE")
            _STAGED_STATE_CACHE[item_id] = (now, state)
            result[item_id] = state
        return result
    except Exception:
        result.update(stale_fallback)
        return result


def _enrich_week_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    rows = []
    ids = []
    for day in payload.get("days") or []:
        for row in day.get("appointments") or []:
            staged = (row or {}).get("staged") or {}
            item_id = int(staged.get("id") or 0)
            if item_id > 0:
                rows.append((row, staged, item_id))
                ids.append(item_id)
    states = _latest_staged_states(ids)
    for row, staged, item_id in rows:
        state = states.get(item_id, "PENDIENTE")
        staged["estado"] = state
        appointment = row.get("appointment") or {}
        appointment["estado"] = state
        row["appointment"] = appointment
    return payload


def _install_agenda_state_bridge() -> None:
    base_week = core.agenda_week
    if getattr(base_week, "__unlinked_whatsapp_state__", False):
        return

    def patched_agenda_week(
        anchor: date,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        return _enrich_week_payload(base_week(anchor=anchor, db=db, user=user))

    patched_agenda_week.__unlinked_whatsapp_state__ = True
    core.agenda_week = patched_agenda_week
    _remove_route("/api/agenda/week", "GET")
    app.get("/api/agenda/week")(patched_agenda_week)

    _remove_route("/api/agenda/unlinked/{item_id}", "GET")

    @app.get("/api/agenda/unlinked/{item_id}")
    def unlinked_detail(
        item_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        item = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if not item or str(item.source_hash or "").startswith(str(core.WHATSAPP_CLOUD_TEST_PREFIX)):
            raise core.HTTPException(404, "La cita ya no existe")
        staged = core.confirmafy_agenda_dict(item)
        staged["estado"] = _latest_staged_states([int(item.id)]).get(int(item.id), "PENDIENTE")
        return {"staged": staged}


GUARD_JS = r'''
(()=>{
'use strict';
const eh=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const phone=v=>typeof window.formatPhoneValue==='function'?window.formatPhoneValue(v):String(v||'');
// Los nombres internos antiguos se conservan únicamente como compatibilidad de
// datos. La interfaz usa vocabulario neutral y la Agenda propia.
window.getConfirmafyStagedRow=async function(itemId){
  const cached=window.confirmafyStagedById?.get?.(Number(itemId));
  if(cached?.staged)return cached.staged;
  const d=await (typeof window.api==='function'?window.api(`/api/agenda/unlinked/${Number(itemId)}`):fetch(`/api/agenda/unlinked/${Number(itemId)}`).then(r=>r.json()));
  return d.staged;
};
window.attentionWeekRow=function(row={}){
  const a=row.appointment||{},p=row.patient||{},staged=row.staged||null;
  const linked=Number(a.id)>0&&Number(p.id)>0;
  const fecha=String((staged?.fecha??a.fecha)||'').slice(0,10);
  const shownName=(linked?p.nombre:staged?.nombre)||p.nombre||'Paciente';
  const shownPhone=phone((linked?p.celular:staged?.celular)||p.celular||'');
  const click=linked
    ?`attendFromAgenda(${Number(p.id)},'${fecha}')`
    :`attendConfirmafyStaged(${Number(staged?.id||0)},'${fecha}')`;
  const title=linked?`Atender a ${shownName}`:`Atender y confirmar identidad de ${shownName}`;
  return `<div class="attention-week-row ${row.conflict?'has-conflict':''} ${linked?'':'confirmafy-unlinked'}" role="button" tabindex="0" title="${eh(title)}" onclick="${click}" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();${click}}"><div class="attention-week-time">${eh(typeof window.fmtTimeCompact==='function'?window.fmtTimeCompact(staged?.hora??a.hora):(staged?.hora??a.hora??''))}</div><div class="attention-week-person"><b>${eh(shownName)}</b><small>${eh(shownPhone||(linked?'SIN CELULAR':'IDENTIDAD PENDIENTE'))}</small></div>${row.conflict?'<div class="attention-week-conflict">⚠ Horario duplicado</div>':''}</div>`;
};
const previousOpenUnlinked=window.openUnlinkedAgendaDetail;
if(typeof previousOpenUnlinked==='function'){
  window.openUnlinkedAgendaDetail=async function(itemId,fecha){
    const result=await previousOpenUnlinked.apply(this,arguments);
    try{
      const d=await (typeof window.api==='function'?window.api(`/api/agenda/unlinked/${Number(itemId)}`):fetch(`/api/agenda/unlinked/${Number(itemId)}`).then(r=>r.json()));
      const state=String(d?.staged?.estado||'PENDIENTE').toUpperCase();
      const node=document.querySelector('.native-appointment-detail .native-detail-status');
      if(node){
        node.classList.remove('pending','confirmed','cancelled','rescheduled');
        if(['CONFIRMADA','CONFIRMADO'].includes(state)){
          node.classList.add('confirmed');node.textContent='Confirmada · sin ficha vinculada';
        }else if(['NO_ASISTIRA','CANCELADA','CANCELADO'].includes(state)){
          node.classList.add('cancelled');node.textContent='No asistirá · sin ficha vinculada';
        }else{
          node.classList.add('pending');node.textContent='Pendiente · sin ficha vinculada';
        }
      }
    }catch(_e){}
    return result;
  };
}
})();
'''


def install_guard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    for path in (
        "/api/messaging/appointments/{appointment_id}",
        "/api/messaging/unlinked/{item_id}",
    ):
        _remove_route(path, "GET")

    @app.get("/api/messaging/appointments/{appointment_id}")
    def appointment_message_history(
        appointment_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        row = db.execute(
            core.select(core.Appointment, core.Patient)
            .join(core.Patient)
            .where(core.Appointment.id == int(appointment_id))
        ).first()
        if not row:
            raise core.HTTPException(404, "Cita no encontrada")
        appointment, patient = row
        return _history_payload(
            source_type="appointment",
            source_id=int(appointment.id),
            fecha=appointment.fecha,
            hora=str(appointment.hora or "")[:5],
            patient_name=str(patient.nombre or ""),
        )

    @app.get("/api/messaging/unlinked/{item_id}")
    def unlinked_message_history(
        item_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        item = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if not item or str(item.source_hash or "").startswith(str(core.WHATSAPP_CLOUD_TEST_PREFIX)):
            raise core.HTTPException(404, "La cita ya no existe")
        return _history_payload(
            source_type="staged",
            source_id=int(item.id),
            fecha=item.fecha,
            hora=str(item.hora or "")[:5],
            patient_name=str(item.nombre or ""),
        )

    _install_agenda_state_bridge()
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + GUARD_JS


def install() -> None:
    _ORIGINAL_INSTALL()
    install_guard()


messaging.install = install
PATCH_BOOT_OK = True
