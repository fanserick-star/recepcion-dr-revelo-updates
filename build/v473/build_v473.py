from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "updates" / "v472"
OUT_DIR = ROOT / "updates" / "v473"
VERSION = "4.3.73"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_v472_app() -> str:
    parts = sorted(SRC_DIR.glob("app.part*"), key=lambda p: int(p.name.replace("app.part", "")))
    if len(parts) != 7:
        raise SystemExit(f"Se esperaban 7 partes de v4.3.72 y hay {len(parts)}")
    return "".join(p.read_text(encoding="utf-8") for p in parts)


DELETE_IMPL = '''@app.delete("/api/agenda/appointments/{appointment_id}")
def agenda_delete(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Elimina realmente la cita y libera el horario.

    v4.3.73 corrige el comportamiento heredado de v4.3.46: el botón
    "Eliminar cita" ya no convierte la cita en CANCELADA/"No asistirá".
    NO_ASISTIRA queda reservado exclusivamente para la respuesta real del
    paciente al mensaje de confirmación de WhatsApp.
    """
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    detail = f"Cita {appointment_id}, paciente {a.patient_id}, {a.fecha} {a.hora}"
    if is_offline_db(db):
        add_queue(db, "appointment.delete", "appointment", {"appointment_id": appointment_id}, user.username, appointment_id)
        audit(db, user, "eliminar_cita_offline", detail)
        db.delete(a)
        db.commit()
        _whatsapp_cancel_pending("appointment", appointment_id)
        return {"ok": True, "offline": True, "deleted": True}
    audit(db, user, "eliminar_cita", detail)
    db.delete(a)
    db.commit()
    mirror_delete_appointment_local(appointment_id)
    _whatsapp_cancel_pending("appointment", appointment_id)
    return {"ok": True, "offline": False, "deleted": True}


'''


HOTFIX_JS = r''';(()=>{
  if(window.__v473Hotfix)return;
  window.__v473Hotfix=true;

  // CANCELADA era el estado que dejaba el antiguo botón Eliminar. No debe
  // presentarse como si el paciente hubiese respondido "No" por WhatsApp.
  const baseAgendaStatusInfo=window.agendaStatusInfo;
  window.agendaStatusInfo=function(state){
    const s=String(state||'PENDIENTE').toUpperCase();
    if(['CANCELADA','CANCELADO'].includes(s))return {label:'Cancelada',cls:'cancelled'};
    return typeof baseAgendaStatusInfo==='function'?baseAgendaStatusInfo(state):{label:'Pendiente',cls:'pending'};
  };

  function confirmationDue(fecha){
    const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(fecha||'').slice(0,10));
    if(!m)return null;
    const due=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]),8,0,0,0);
    due.setDate(due.getDate()-1);
    return due;
  }
  function statusForDate(state,fecha){
    const s=String(state||'PENDIENTE').toUpperCase();
    if(['CONFIRMADA','CONFIRMADO'].includes(s))return {label:'Confirmada',cls:'confirmed'};
    if(s==='NO_ASISTIRA')return {label:'No asistirá',cls:'cancelled'};
    if(['CANCELADA','CANCELADO'].includes(s))return {label:'Cancelada',cls:'cancelled'};
    if(s==='REAGENDADA')return {label:'Reagendada',cls:'rescheduled'};
    const due=confirmationDue(fecha);
    if(due&&Date.now()<due.getTime())return {label:'Agendada',cls:'scheduled'};
    return {label:'Pendiente',cls:'pending'};
  }
  window.v473AgendaStatusForDate=statusForDate;

  // En la cuadrícula, "Pendiente" solo aparece desde la hora en que corresponde
  // enviar la confirmación. Una cita futura todavía no confirmada dice "Agendada".
  window.nativeAgendaRowCell=function(row,date,time){
    if(!row)return `<button class="native-slot free" onclick="openAgendaSlotPicker('${date}','${time}')"><b class="native-free-time">${esc(fmtTime(time))}</b><span>Disponible</span></button>`;
    const a=row.appointment||{},p=row.patient||{},staged=row.staged||{},source=String(row.source_type||''),unlinked=source==='MOBILE_UNLINKED'||source==='LEGACY_UNLINKED'||source==='CONFIRMAFY_STAGED'||source==='CONFIRMAFY_LEGACY';
    const name=staged.nombre||p.nombre||'PACIENTE',status=statusForDate(a.estado,date),sourceBadge=unlinked?'<small class="native-unlinked">SIN VINCULAR</small>':'';
    const action=unlinked?`openUnlinkedAgendaDetail(${Number(staged.id||0)},'${date}')`:`openLinkedAgendaDetail(${Number(a.id||0)},${Number(p.id||0)},'${date}')`;
    return `<button class="native-slot occupied ${status.cls}" onclick="${action}"><b>${esc(name)}</b><span>${esc(status.label)}</span>${sourceBadge}</button>`;
  };

  // El detalle usa la misma regla de fecha que la cuadrícula.
  const baseOpenLinked=window.openLinkedAgendaDetail;
  if(typeof baseOpenLinked==='function')window.openLinkedAgendaDetail=async function(appointmentId,patientId,fecha){
    await baseOpenLinked(appointmentId,patientId,fecha);
    try{
      const row=agendaAppointmentById.get(Number(appointmentId)),a=row?.appointment||{};
      const st=statusForDate(a.estado,a.fecha||fecha),el=document.querySelector('.native-appointment-detail .native-detail-status');
      if(el){el.className=`native-detail-status ${st.cls}`;el.textContent=st.label}
    }catch(_e){}
  };

  // Emisión masiva: confirmar una sola vez y ejecutar la llamada directamente.
  // No se vuelve a hacer click programáticamente sobre el botón, evitando el bucle.
  window.emitAllPendingInvoices=async function(){
    try{
      const pre=await api('/api/billing/azur/batch-preview');
      const c=pre.counts||{},ready=Number(c.ready||0),skipped=Number(c.skipped||0);
      if(!pre.unlocked){alert('🔒 Emisión masiva bloqueada por seguridad.\n\nPrimero emite UNA factura individual real y confirma que AZUR/SRI la marque AUTORIZADA.');return}
      if(!ready){alert(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`);return}
      const examples=(pre.skipped||[]).slice(0,5).map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      const text=`¿Emitir ${ready} factura${ready===1?'':'s'} aprobada${ready===1?'':'s'} en AZUR?\n\nSe enviarán una por una para evitar duplicados. Las enviadas quedarán EN PROCESO hasta consultar la autorización del SRI.`+(skipped?`\n\nSe omitirán ${skipped} por datos incompletos o estado.`:'')+(examples?`\n\nEjemplos omitidos:\n${examples}`:'');
      const ok=typeof window.rpConfirm==='function'?await window.rpConfirm(text,'Confirmar emisión en AZUR'):window.confirm(text);
      if(!ok)return;
      const result=await singleFlightMutation('billing:azur:emit-all',()=>api('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}'}),'Enviando facturas…');
      if(!result)return;
      const r=result.counts||{};let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
      const omit=(result.skipped||[]).slice(0,8);if(omit.length)detail+='\n\nOmitidas:\n'+omit.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      const failed=(result.failed||[]).slice(0,5);if(failed.length)detail+='\n\nFallidas:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      alert('Lote enviado. Las enviadas quedan EN PROCESO hasta confirmar autorización SRI.\n\n'+detail);
      await loadBilling();await refreshPendingBadges();
    }catch(e){alert(e.message||'No se pudo completar la emisión masiva.')}
  };
})();'''


def patch_app(app: str) -> str:
    old_version = 'APP_VERSION = "4.3.72"'
    if app.count(old_version) != 1:
        raise SystemExit("No se encontró exactamente APP_VERSION 4.3.72")
    app = app.replace(old_version, f'APP_VERSION = "{VERSION}"', 1)

    start_marker = '@app.delete("/api/agenda/appointments/{appointment_id}")\ndef agenda_delete('
    start = app.find(start_marker)
    if start < 0:
        raise SystemExit("No se encontró agenda_delete")
    end_marker = '\ndef _decode_confirmafy_csv('
    end = app.find(end_marker, start)
    if end < 0:
        raise SystemExit("No se encontró el final de agenda_delete")
    app = app[:start] + DELETE_IMPL + app[end + 1:]

    route_marker = '@app.get("/v460/overlay.css")'
    if app.count(route_marker) != 1:
        raise SystemExit("No se encontró el punto de inserción del overlay")
    injected = (
        'V473_HOTFIX_JS = r"""' + HOTFIX_JS + '"""\n'
        'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V473_HOTFIX_JS\n\n'
        + route_marker
    )
    app = app.replace(route_marker, injected, 1)
    return app


def write_parts(app: str) -> list[str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in OUT_DIR.glob("app.part*"):
        p.unlink()
    n = 7
    step = math.ceil(len(app) / n)
    names = []
    for i in range(n):
        chunk = app[i * step:(i + 1) * step]
        if not chunk and i == n - 1:
            chunk = ""
        name = f"app.part{i+1}"
        (OUT_DIR / name).write_text(chunk, encoding="utf-8", newline="")
        names.append(name)
    rebuilt = "".join((OUT_DIR / n).read_text(encoding="utf-8") for n in names)
    if rebuilt != app:
        raise SystemExit("Las partes no reconstruyen app.py exactamente")
    return names


def main() -> None:
    app = patch_app(read_v472_app())
    compile(app, "app.py", "exec")
    tree = ast.parse(app)
    found_hotfix = False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "V473_HOTFIX_JS" for t in node.targets):
            found_hotfix = True
            break
    if not found_hotfix:
        raise SystemExit("No quedó V473_HOTFIX_JS")
    if 'add_queue(db, "appointment.delete"' not in app or 'a.estado = "CANCELADA"' in app[app.find('@app.delete("/api/agenda/appointments/{appointment_id}")'):app.find('def _decode_confirmafy_csv')]:
        raise SystemExit("agenda_delete no quedó con borrado real")

    parts = write_parts(app)
    app_bytes = app.encode("utf-8")

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.57-standalone-1",
        "updater_version": "integrado-en-launcher",
        "copy": ["ABRIR_RECEPCION.py", "app.py", "update_manifest.json"],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (OUT_DIR / "update_manifest.json").write_bytes(manifest_bytes)

    current = json.loads((ROOT / "latest.json").read_text(encoding="utf-8"))
    launcher = next(x for x in current["files"] if x.get("path") == "ABRIR_RECEPCION.py")
    base = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v473/"
    latest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.3.73: corrige Emitir todas en AZUR, evita mostrar Pendiente antes de la confirmación y hace que Eliminar cita borre realmente la cita en vez de marcarla No asistirá.",
        "files": [
            launcher,
            {
                "path": "app.py",
                "parts": [base + name for name in parts],
                "sha256": sha(app_bytes),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": base + "update_manifest.json",
                "sha256": sha(manifest_bytes),
                "encoding": "utf-8",
            },
        ],
    }
    text = json.dumps(latest, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "latest.json").write_text(text, encoding="utf-8", newline="")
    (ROOT / "latest-v3.json").write_text(text, encoding="utf-8", newline="")

    print("OK", VERSION, sha(app_bytes), len(app_bytes))


if __name__ == "__main__":
    main()
