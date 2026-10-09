from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import core_runtime as core

app = core.app
APP_VERSION = "4.6.39"
_INSTALLED = False


def _iso(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        return str(value)
    except Exception:
        return ""


def _template_label(template_name: object) -> str:
    name = str(template_name or "").strip()
    if name == str(getattr(core, "WHATSAPP_TEMPLATE_CITA_AGENDADA", "") or ""):
        return "Cita agendada"
    if name == str(getattr(core, "WHATSAPP_TEMPLATE_RECORDATORIO_CITA", "") or ""):
        return "Confirmación de cita"
    try:
        if name == str(core.whatsapp_recordatorio_template_name() or ""):
            return "Confirmación de cita"
    except Exception:
        pass
    if name == str(getattr(core, "WHATSAPP_TEMPLATE_RECORDATORIO_HOY", "") or ""):
        return "Recordatorio del día"
    return name.replace("_", " ").strip().title() or "Mensaje de WhatsApp"


def _delivery_status(status: object, *, sent_at=None, delivered_at=None, read_at=None) -> tuple[str, str]:
    raw = str(status or "").strip().upper()
    if read_at or raw == "READ":
        return "Leído", "read"
    if delivered_at or raw == "DELIVERED":
        return "Entregado", "delivered"
    if sent_at or raw == "SENT":
        return "Enviado", "sent"
    if raw in {"ERROR", "FAILED"}:
        return "Error", "error"
    if raw in {"SENDING", "PROCESSING"}:
        return "Enviando", "sending"
    if raw in {"PENDING", "QUEUED", "SCHEDULED"}:
        return "Programado", "planned"
    if raw in {"CANCELLED", "CANCELED", "EXPIRED"}:
        return "Cancelado", "muted"
    return (raw.replace("_", " ").title() or "Programado"), "muted"


def _response_status(interpretation: object, resolved_at: object) -> tuple[str, str]:
    raw = str(interpretation or "REVISAR").strip().upper()
    if raw == "CONFIRMADO":
        return "Confirmado", "confirmed"
    if raw == "NO_ASISTIRA":
        return "No asistirá", "no-show"
    if raw == "REVISAR" and not resolved_at:
        return "Por revisar", "review"
    if resolved_at:
        return "Revisado", "resolved"
    return raw.replace("_", " ").title(), "muted"


def _cloud_history(source_type: str, source_id: int) -> tuple[list[dict], list[dict], str]:
    outbound: list[dict] = []
    inbound: list[dict] = []
    if not core.cloud_configured() or not core.CloudSessionLocal or core.FORCE_OFFLINE:
        return outbound, inbound, "Neon no está disponible"

    try:
        with core.CloudSessionLocal() as db:
            rows = db.execute(core.text("""
                SELECT id,message_id,template_name,status,created_at,due_at,
                       sent_at,delivered_at,read_at,error_text,
                       appointment_date,appointment_time,patient_name
                FROM whatsapp_cloud.events
                WHERE source_type=:source_type AND source_id=:source_id
                ORDER BY created_at ASC,id ASC
            """), {"source_type": str(source_type), "source_id": int(source_id)}).mappings().all()
            for row in rows:
                status_label, tone = _delivery_status(
                    row.get("status"),
                    sent_at=row.get("sent_at"),
                    delivered_at=row.get("delivered_at"),
                    read_at=row.get("read_at"),
                )
                outbound.append({
                    "id": f"cloud:{row.get('id')}",
                    "direction": "outbound",
                    "kind": "template",
                    "message_id": str(row.get("message_id") or ""),
                    "template": str(row.get("template_name") or ""),
                    "label": _template_label(row.get("template_name")),
                    "status": str(row.get("status") or ""),
                    "status_label": status_label,
                    "tone": tone,
                    "created_at": _iso(row.get("created_at")),
                    "due_at": _iso(row.get("due_at")),
                    "sent_at": _iso(row.get("sent_at")),
                    "delivered_at": _iso(row.get("delivered_at")),
                    "read_at": _iso(row.get("read_at")),
                    "timestamp": _iso(row.get("sent_at") or row.get("created_at") or row.get("due_at")),
                    "error": str(row.get("error_text") or "")[:300],
                    "appointment_date": _iso(row.get("appointment_date"))[:10],
                    "appointment_time": str(row.get("appointment_time") or "")[:5],
                    "patient_name": str(row.get("patient_name") or ""),
                })

            if core._wa_inbound_table_ready(db):
                rows = db.execute(core.text("""
                    SELECT id,message_id,message_type,raw_text,transcription,
                           interpretation,confidence,received_at,resolved_at,
                           resolution,apply_result,media_id,media_mime_type,
                           appointment_date,appointment_time,patient_name
                    FROM whatsapp_cloud.inbound_responses
                    WHERE source_type=:source_type AND source_id=:source_id
                    ORDER BY received_at ASC,id ASC
                """), {"source_type": str(source_type), "source_id": int(source_id)}).mappings().all()
                for row in rows:
                    audio = str(row.get("message_type") or "").lower() == "audio"
                    body = str((row.get("transcription") if audio else row.get("raw_text")) or "").strip()
                    status_label, tone = _response_status(row.get("interpretation"), row.get("resolved_at"))
                    inbound.append({
                        "id": f"inbound:{row.get('id')}",
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
                        "media_id": str(row.get("media_id") or ""),
                        "media_mime_type": str(row.get("media_mime_type") or ""),
                        "appointment_date": _iso(row.get("appointment_date"))[:10],
                        "appointment_time": str(row.get("appointment_time") or "")[:5],
                        "patient_name": str(row.get("patient_name") or ""),
                    })
        return outbound, inbound, ""
    except Exception as exc:
        return [], [], f"{type(exc).__name__}: {str(exc)[:220]}"


def _local_outbox_history(source_type: str, source_id: int) -> list[dict]:
    """Estado local administrativo; NO es prueba de envío por Meta.

    SQLite guarda created_at/sent_at como UTC sin tz y due_at en hora local.
    Normalizamos ambas para no mostrar 18:05 en una cita creada a las 13:05 EC.
    """
    utc = timezone.utc
    ecuador = timezone(timedelta(hours=-5))
    def stamp(value, tz):
        if value is None:
            return ""
        if isinstance(value, datetime):
            return (value if value.tzinfo else value.replace(tzinfo=tz)).isoformat()
        return _iso(value)

    rows: list[dict] = []
    try:
        with core.LocalSessionLocal() as db:
            items = list(db.scalars(
                core.select(core.WhatsAppOutbox)
                .where(
                    core.WhatsAppOutbox.source_type == str(source_type),
                    core.WhatsAppOutbox.source_id == int(source_id),
                )
                .order_by(core.WhatsAppOutbox.id.asc())
            ))
            for item in items:
                status_label, tone = _delivery_status(item.status, sent_at=item.sent_at)
                rows.append({
                    "id": f"local:{item.id}",
                    "direction": "outbound",
                    "kind": "template",
                    "message_id": "",
                    "template": str(item.template_name or ""),
                    "label": _template_label(item.template_name),
                    "status": str(item.status or ""),
                    "status_label": status_label,
                    "tone": tone,
                    "created_at": stamp(item.created_at, utc),
                    "due_at": stamp(item.due_at, ecuador),
                    "sent_at": stamp(item.sent_at, utc),
                    "delivered_at": "",
                    "read_at": "",
                    "timestamp": (stamp(item.sent_at, utc) if item.sent_at else stamp(item.due_at, ecuador)),
                    "error": str(item.last_error or "")[:300],
                    "appointment_date": "",
                    "appointment_time": "",
                    "patient_name": "",
                    "local_fallback": True,
                })
    except Exception:
        return []
    return rows


def _sort_key(item: dict) -> str:
    return str(item.get("timestamp") or item.get("due_at") or "9999-12-31T23:59:59")


def _message_history(*, source_type: str, source_id: int, patient_name: str = "") -> dict:
    outbound, inbound, cloud_error = _cloud_history(source_type, source_id)
    if not outbound:
        outbound = _local_outbox_history(source_type, source_id)

    events = sorted([*outbound, *inbound], key=_sort_key)
    return {
        "available": not bool(cloud_error) or bool(events),
        "cloud_available": not bool(cloud_error),
        "cloud_error": cloud_error,
        "source_type": source_type,
        "source_id": int(source_id),
        "patient_name": patient_name,
        "outbound_count": len(outbound),
        "inbound_count": len(inbound),
        "events": events,
    }


def _remove_route(path: str, method: str) -> None:
    wanted = str(method).upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) != path:
            continue
        methods = {str(x).upper() for x in (getattr(route, "methods", set()) or set())}
        if wanted in methods:
            app.router.routes.remove(route)


def _retire_confirmafy_import_export() -> None:
    retired = (
        ("/api/agenda/import-confirmafy/preview", "POST"),
        ("/api/agenda/import-confirmafy", "POST"),
        ("/api/agenda/export.csv", "POST"),
    )
    for path, method in retired:
        _remove_route(path, method)

    @app.post("/api/agenda/import-confirmafy/preview")
    def _retired_import_preview(user=core.Depends(core.current_user)):
        raise core.HTTPException(410, "La importación externa fue retirada. Usa la Agenda propia de Recepción.")

    @app.post("/api/agenda/import-confirmafy")
    def _retired_import(user=core.Depends(core.current_user)):
        raise core.HTTPException(410, "La importación externa fue retirada. Usa la Agenda propia de Recepción.")

    @app.post("/api/agenda/export.csv")
    def _retired_export(user=core.Depends(core.current_user)):
        raise core.HTTPException(410, "La exportación para la agenda antigua fue retirada. La Agenda propia trabaja directamente en Recepción.")


def _install_routes() -> None:
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
        return _message_history(
            source_type="appointment",
            source_id=int(appointment.id),
            patient_name=str(patient.nombre or ""),
        )

    @app.get("/api/agenda/unlinked/{item_id}")
    def unlinked_detail(
        item_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        item = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if not item or str(item.source_hash or "").startswith(str(core.WHATSAPP_CLOUD_TEST_PREFIX)):
            raise core.HTTPException(404, "La cita ya no existe")
        return {"staged": core.confirmafy_agenda_dict(item)}

    @app.get("/api/messaging/unlinked/{item_id}")
    def unlinked_message_history(
        item_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        item = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if not item or str(item.source_hash or "").startswith(str(core.WHATSAPP_CLOUD_TEST_PREFIX)):
            raise core.HTTPException(404, "La cita ya no existe")
        return _message_history(
            source_type="staged",
            source_id=int(item.id),
            patient_name=str(item.nombre or ""),
        )

    @app.get("/api/messaging/health")
    def messaging_health(user=core.Depends(core.current_user)):
        return {
            "ok": True,
            "version": APP_VERSION,
            "agenda_mode": "native",
            "confirmafy_ui": False,
            "confirmafy_import_export": False,
            "legacy_unlinked_compatibility": True,
            "whatsapp_history": "outbound_and_inbound",
            "cloud_mode": bool(getattr(core, "WHATSAPP_CLOUD_MODE", False)),
        }


RUNTIME_CSS = r'''
/* Semantic messaging runtime: native Agenda + complete WhatsApp history. */
.rp-msg-history{margin:10px 0 5px;border:1px solid #dce6ef;border-radius:13px;background:#fbfdff;overflow:hidden}
.rp-msg-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border-bottom:1px solid #e4ebf2}
.rp-msg-head h3{margin:0;font-size:14px;color:#203a57}.rp-msg-head span{font-size:9px;font-weight:900;color:#52718f;background:#edf5ff;border-radius:999px;padding:4px 7px}
.rp-msg-list{display:grid;padding:4px 11px 8px}.rp-msg-row{display:grid;grid-template-columns:30px minmax(0,1fr) auto;gap:9px;align-items:start;padding:9px 0;border-bottom:1px solid #edf1f5}.rp-msg-row:last-child{border-bottom:0}
.rp-msg-icon{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#eef4fa;color:#41698d;font-size:14px}.rp-msg-row.inbound .rp-msg-icon{background:#eaf7ef;color:#2f7650}.rp-msg-row.error .rp-msg-icon{background:#fff0ef;color:#a54c45}
.rp-msg-copy{min-width:0}.rp-msg-title{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.rp-msg-title b{font-size:12px;color:#263d56}.rp-msg-status{font-size:8px;font-weight:900;border-radius:999px;padding:3px 6px;background:#eef2f6;color:#647487}.rp-msg-status.read,.rp-msg-status.delivered,.rp-msg-status.sent,.rp-msg-status.confirmed{background:#e8f7ee;color:#2c7049}.rp-msg-status.review,.rp-msg-status.planned,.rp-msg-status.sending{background:#fff5d8;color:#806313}.rp-msg-status.error,.rp-msg-status.no-show{background:#fff0ef;color:#954c46}
.rp-msg-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:3px;color:#7b8b9c;font-size:9px}.rp-msg-body{margin:6px 0 0;padding:7px 9px;border-radius:9px;background:#f5f8fb;color:#31465d;font-size:11px;line-height:1.42;white-space:pre-wrap}.rp-msg-row.inbound .rp-msg-body{background:#f1f9f4}
.rp-msg-empty{padding:18px 12px;text-align:center;color:#73859a;font-size:11px}.rp-msg-error{padding:8px 11px;background:#fff9e8;color:#806313;font-size:9px;border-top:1px solid #f0dfaa}
.rp-msg-audio{margin-top:7px}.rp-msg-audio audio{width:100%;height:34px}.rp-msg-review-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}.rp-msg-review-actions button{font-size:9px;padding:6px 8px;border-radius:8px}
[onclick*="chooseConfirmafyImport"],[onclick*="openExternalApp('confirmafy')"],[onclick*='openExternalApp("confirmafy")']{display:none!important}
.confirmafy-import-modal,.patient-origin-badge{display:none!important}
@media(max-width:700px){.rp-msg-row{grid-template-columns:28px minmax(0,1fr)}.rp-msg-row>time{grid-column:2}.rp-msg-head{align-items:flex-start}}
'''


RUNTIME_JS = r'''
(()=>{
'use strict';
const cache=new Map(),CACHE_MS=30000;
const q=(s,r=document)=>r.querySelector(s);
const eh=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const call=async(url,opt={})=>{if(typeof window.api==='function')return window.api(url,opt);const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.message||'No se pudo completar la operación');return d};
const fmtStamp=v=>{if(!v)return'';try{return new Date(v).toLocaleString('es-EC',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})}catch{return String(v)}};
const fmtShort=v=>{if(!v)return'';try{return new Date(v).toLocaleString('es-EC',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}catch{return String(v)}};
function statusTimes(x){const out=[];if(x.due_at&&!x.sent_at)out.push('Programado: '+fmtStamp(x.due_at));if(x.sent_at)out.push('Enviado: '+fmtShort(x.sent_at));if(x.delivered_at)out.push('Entregado: '+fmtShort(x.delivered_at));if(x.read_at)out.push('Leído: '+fmtShort(x.read_at));if(x.received_at)out.push('Recibido: '+fmtStamp(x.received_at));return out.join(' · ')}
function actions(x,ctx){if(x.direction!=='inbound'||x.resolved_at||String(x.status||'').toUpperCase()!=='REVISAR')return'';const id=Number(x.response_id||0);if(!id)return'';if(ctx.kind==='appointment')return `<div class="rp-msg-review-actions"><button class="primary" onclick="rpResolveMessage(${id},'CONFIRMAR',${Number(ctx.appointmentId)},${Number(ctx.patientId)},'${eh(ctx.fecha)}')">✓ Confirmar</button><button onclick="rpResolveMessage(${id},'CANCELAR',${Number(ctx.appointmentId)},${Number(ctx.patientId)},'${eh(ctx.fecha)}')">× No asistirá</button><button onclick="rpResolveMessage(${id},'RESUELTO',${Number(ctx.appointmentId)},${Number(ctx.patientId)},'${eh(ctx.fecha)}')">Marcar resuelto</button></div>`;return `<div class="rp-msg-review-actions"><button onclick="rpResolveMessage(${id},'RESUELTO',0,0,'')">Marcar resuelto</button></div>`}
function eventHtml(x,ctx){const inbound=x.direction==='inbound',audio=x.kind==='audio',icon=inbound?(audio?'🎙':'↙'):'↗',tone=eh(x.tone||'muted'),body=inbound?(x.body||'Sin texto'):(x.error?'Error: '+x.error:''),meta=statusTimes(x),audioHtml=audio&&Number(x.response_id)?`<div class="rp-msg-audio"><audio id="waAudioPlayer${Number(x.response_id)}" controls preload="none"></audio><small id="waAudioStatus${Number(x.response_id)}" class="wa-audio-error">Cargando audio…</small></div>`:'';return `<div class="rp-msg-row ${inbound?'inbound':'outbound'} ${tone==='error'?'error':''}"><span class="rp-msg-icon">${icon}</span><div class="rp-msg-copy"><div class="rp-msg-title"><b>${eh(x.label||'WhatsApp')}</b><span class="rp-msg-status ${tone}">${eh(x.status_label||'')}</span></div>${meta?`<div class="rp-msg-meta">${eh(meta)}</div>`:''}${body?`<div class="rp-msg-body">${eh(body)}</div>`:''}${audioHtml}${actions(x,ctx)}</div><time class="rp-msg-meta">${eh(fmtShort(x.timestamp))}</time></div>`}
function render(data,ctx){const events=Array.isArray(data?.events)?data.events:[];let html='<div class="rp-msg-head"><h3>Mensajería WhatsApp</h3><span>Cloud 24/7</span></div>';if(!events.length)html+='<div class="rp-msg-empty">Aún no se han enviado ni recibido mensajes para esta cita.</div>';else html+='<div class="rp-msg-list">'+events.map(x=>eventHtml(x,ctx)).join('')+'</div>';if(data?.cloud_error&&events.length)html+=`<div class="rp-msg-error">La nube no respondió completamente: ${eh(data.cloud_error)}</div>`;return html}
async function getHistory(kind,id,force=false){const key=kind+':'+Number(id),old=cache.get(key);if(!force&&old&&Date.now()-old.at<CACHE_MS)return old.data;const url=kind==='appointment'?`/api/messaging/appointments/${Number(id)}`:`/api/messaging/unlinked/${Number(id)}`;const data=await call(url);cache.set(key,{at:Date.now(),data});return data}
async function loadHistory(host,ctx,force=false){if(!host)return;host.innerHTML='<div class="rp-msg-empty">Cargando historial de mensajes…</div>';try{const d=await getHistory(ctx.kind,ctx.kind==='appointment'?ctx.appointmentId:ctx.itemId,force);if(!host.isConnected)return;host.innerHTML=render(d,ctx);for(const x of d.events||[])if(x.kind==='audio'&&Number(x.response_id)&&typeof window.loadWhatsappAudioBlob==='function')setTimeout(()=>window.loadWhatsappAudioBlob(Number(x.response_id)),0)}catch(e){host.innerHTML=`<div class="rp-msg-empty">No se pudo cargar la mensajería: ${eh(e.message||e)}</div>`}}
window.rpResolveMessage=async function(id,action,appointmentId,patientId,fecha){const labels={CONFIRMAR:'Confirmar asistencia',CANCELAR:'Marcar que no asistirá',RESUELTO:'Marcar como resuelto'};if(action!=='RESUELTO'&&!confirm(`${labels[action]} para esta cita?`))return;try{await call(`/api/whatsapp-responses/${Number(id)}/resolve`,{method:'POST',body:JSON.stringify({action})});cache.clear();if(appointmentId){const host=q('#rpMessageHistory');await loadHistory(host,{kind:'appointment',appointmentId,patientId,fecha},true);try{if(typeof window.loadAgenda==='function')await window.loadAgenda()}catch{}}else if(typeof window.loadWhatsappResponses==='function'){try{await window.loadWhatsappResponses()}catch{}}}catch(e){if(typeof window.rpNotice==='function')window.rpNotice(e.message||e);else alert(e.message||e)}};
window.openExternalApp=async function(target){const key=String(target||'').toLowerCase();if(key!=='facturero'){if(typeof window.rpNotice==='function')window.rpNotice('La integración antigua de agenda fue retirada. Usa la Agenda propia de Recepción.');return}try{await call('/api/open-external/facturero',{method:'POST'})}catch{window.open('https://app.factureromovil.com/documentos/facturas','_blank','noopener')}};
window.nativeAgendaRowCell=function(row,date,time){if(!row)return `<button class="native-slot free" onclick="openAgendaSlotPicker('${date}','${time}')"><b class="native-free-time">${eh(typeof window.fmtTime==='function'?window.fmtTime(time):time)}</b><span>Disponible</span></button>`;const a=row.appointment||{},p=row.patient||{},staged=row.staged||{},linked=Number(a.id)>0&&Number(p.id)>0,name=(linked?p.nombre:staged.nombre)||p.nombre||'PACIENTE',state=String(a.estado||'PENDIENTE').toUpperCase();let label='Pendiente',cls='pending';if(['CONFIRMADA','CONFIRMADO'].includes(state)){label='Confirmada';cls='confirmed'}else if(['NO_ASISTIRA','CANCELADA','CANCELADO'].includes(state)){label='No asistirá';cls='cancelled'}else if(state==='REAGENDADA'){label='Reagendada';cls='rescheduled'}const action=linked?`openLinkedAgendaDetail(${Number(a.id)},${Number(p.id)},'${date}')`:`openUnlinkedAgendaDetail(${Number(staged.id||0)},'${date}')`;return `<button class="native-slot occupied ${cls}" onclick="${action}"><b>${eh(name)}</b><span>${eh(label)}</span>${linked?'':'<small class="native-unlinked">SIN VINCULAR</small>'}</button>`};
window.openLinkedAgendaDetail=async function(appointmentId,patientId,fecha){try{let row=window.agendaAppointmentById?.get?.(Number(appointmentId));if(!row)row=await call(`/api/agenda/appointments/${Number(appointmentId)}`);const a=row.appointment||{},p=row.patient||await call('/api/patients/'+Number(patientId)),state=String(a.estado||'PENDIENTE').toUpperCase();let label='Pendiente',cls='pending';if(['CONFIRMADA','CONFIRMADO'].includes(state)){label='Confirmada';cls='confirmed'}else if(['NO_ASISTIRA','CANCELADA','CANCELADO'].includes(state)){label='No asistirá';cls='cancelled'}else if(state==='REAGENDADA'){label='Reagendada';cls='rescheduled'}const d=typeof window.fmtDate==='function'?window.fmtDate(a.fecha):String(a.fecha||''),t=typeof window.fmtTime==='function'?window.fmtTime(a.hora):String(a.hora||'');window.openModal(`<div class="native-appointment-detail"><div class="modal-form-heading"><h2>${eh(p.nombre||'Paciente')}</h2><p>${eh(d)} · ${eh(t)}</p></div><div class="native-detail-status ${cls}">${eh(label)}</div>${a.nota?`<div class="native-detail-note">${eh(a.nota)}</div>`:''}<section id="rpMessageHistory" class="rp-msg-history"><div class="rp-msg-empty">Cargando historial de mensajes…</div></section><div class="actions wrap-actions"><button onclick="openPatient(${Number(p.id)},'patients')">Ver paciente</button><button onclick="attendFromAgenda(${Number(p.id)},'${String(fecha||a.fecha).slice(0,10)}')">✓ Atender</button><button onclick="openAgendaPatient(${Number(p.id)},${Number(a.id)})">✎ Editar cita</button><button class="danger ghost" onclick="deleteAgendaAppointment(${Number(a.id)})">Eliminar cita</button></div></div>`);const host=q('#rpMessageHistory');if(host)loadHistory(host,{kind:'appointment',appointmentId:Number(a.id),patientId:Number(p.id),fecha:String(fecha||a.fecha).slice(0,10)})}catch(e){if(typeof window.rpNotice==='function')window.rpNotice(e.message||e);else alert(e.message||e)}};
window.openUnlinkedAgendaDetail=async function(itemId,fecha){if(!Number(itemId)){if(typeof window.rpNotice==='function')window.rpNotice('Esta cita antigua ya tiene ficha vinculada. Actualiza la agenda e inténtalo nuevamente.');return}try{const d=await call(`/api/agenda/unlinked/${Number(itemId)}`),st=d.staged||{},fd=typeof window.fmtDate==='function'?window.fmtDate(st.fecha):String(st.fecha||''),ft=typeof window.fmtTime==='function'?window.fmtTime(st.hora):String(st.hora||'');window.openModal(`<div class="native-appointment-detail"><div class="modal-form-heading"><h2>${eh(st.nombre||'Paciente')}</h2><p>${eh(fd)} · ${eh(ft)}</p></div><div class="native-detail-status pending">Pendiente · sin ficha vinculada</div><p class="muted">La identidad se resolverá cuando el paciente sea atendido.</p><section id="rpMessageHistory" class="rp-msg-history"><div class="rp-msg-empty">Cargando historial de mensajes…</div></section><div class="actions wrap-actions"><button class="primary" onclick="attendConfirmafyStaged(${Number(itemId)},'${String(fecha||st.fecha).slice(0,10)}')">✓ Atender</button><button class="danger ghost" onclick="deleteUnlinkedAppointment(${Number(itemId)})">Eliminar cita</button></div></div>`);const host=q('#rpMessageHistory');if(host)loadHistory(host,{kind:'unlinked',itemId:Number(itemId),fecha:String(fecha||st.fecha).slice(0,10)})}catch(e){if(typeof window.rpNotice==='function')window.rpNotice(e.message||e);else alert(e.message||e)}};
window.loadAgendaWhatsappAppointmentPanel=async function(appointmentId,patientId,fecha){const host=q('#agendaWhatsappDetail'+Number(appointmentId))||q('#rpMessageHistory');if(host)await loadHistory(host,{kind:'appointment',appointmentId:Number(appointmentId),patientId:Number(patientId),fecha:String(fecha||'').slice(0,10)},true)};
const scrub=()=>{document.querySelectorAll('[onclick*="chooseConfirmafyImport"],[onclick*="openExternalApp(\'confirmafy\')"],[onclick*="deleteConfirmafyImportedPatient"]').forEach(x=>x.remove());document.querySelectorAll('.patient-origin-badge').forEach(x=>x.remove())};
new MutationObserver(scrub).observe(document.documentElement,{childList:true,subtree:true});scrub();
})();
'''


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _retire_confirmafy_import_export()
    _install_routes()
    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + RUNTIME_CSS
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + RUNTIME_JS


PATCH_BOOT_OK = True
