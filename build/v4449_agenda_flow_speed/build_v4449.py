from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_48_dependency_recovery"
OUT = ROOT / "updates" / "v4_4_49_agenda_flow_speed"
VERSION = "4.4.49"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.49 — Agenda local inmediata + paciente existente + hora WA correcta.
    # -----------------------------------------------------------------------
    # 1) La v4.4.45 esperaba a Neon ANTES de responder /api/agenda/week. Eso
    #    hacía lenta la Agenda en la PC antigua. Conservamos exactamente el
    #    mismo espejo Cloud->SQLite, pero lo lanzamos en segundo plano: la UI
    #    dibuja primero la copia local y se refresca después sin bloquear.
    _v4449_cloud_sync_blocking = _v4445_sync_cloud_agenda_for_dates
    _v4449_cloud_bg_guard = core.threading.Lock()
    _v4449_cloud_bg_keys: set[str] = set()

    def _v4449_cloud_sync_background(dates, min_interval: float = 5.0) -> int:
        normalized = []
        for value in dates or []:
            try:
                d = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
            except Exception:
                continue
            if d not in normalized:
                normalized.append(d)
        if not normalized:
            return 0
        key = "|".join(sorted(d.isoformat() for d in normalized))
        with _v4449_cloud_bg_guard:
            if key in _v4449_cloud_bg_keys:
                return 0
            _v4449_cloud_bg_keys.add(key)

        def worker():
            try:
                _v4449_cloud_sync_blocking(normalized, min_interval=min_interval)
            finally:
                with _v4449_cloud_bg_guard:
                    _v4449_cloud_bg_keys.discard(key)

        core.threading.Thread(
            target=worker,
            daemon=True,
            name="rp-agenda-cloud-catchup",
        ).start()
        return 0

    # El middleware v4.4.45 resuelve este nombre global en cada petición.
    # Reasignarlo cambia la espera síncrona por un disparo no bloqueante sin
    # duplicar rutas ni tocar SQLite/Neon.
    _v4445_sync_cloud_agenda_for_dates = _v4449_cloud_sync_background

    # 2) Cita agendada debe ser inmediata. Appointment.created_at se guarda en
    #    UTC naive; usarlo como hora local hacía que Ecuador (-05:00) mostrara
    #    falsamente una hora cinco horas adelante (ej. 10:45 -> 15:45).
    #    El worker Cloud sigue siendo la autoridad de envío; aquí corregimos la
    #    línea de tiempo para que diga "Al guardar la cita" y quede esperando al
    #    worker hasta que exista un evento SENT/DELIVERED/READ.
    _v4449_timeline_defs_stable = core._wa_timeline_defs

    def _v4449_timeline_defs(fecha, hora, created_at=None):
        rows = _v4449_timeline_defs_stable(fecha, hora, created_at)
        for row in rows:
            if str(row.get("key") or "") == "cita_agendada":
                row["due_at"] = (core.datetime.now() - core.timedelta(seconds=1)).isoformat()
                row["planned"] = "Al guardar la cita"
        return rows

    core._wa_timeline_defs = _v4449_timeline_defs

    V4449_AGENDA_FLOW_JS = r"""
;(()=>{
  if(window.__v4449AgendaFlowSpeed)return;
  window.__v4449AgendaFlowSpeed=true;

  const wait=(ms,fn)=>setTimeout(()=>{try{fn()}catch(_e){}},ms);

  // Nueva atención: primera pintura 100% local. Después de que el espejo Cloud
  // tuvo tiempo de terminar, una lectura LOCAL muy barata actualiza la lista.
  const stableLoadAttentionWeek=window.loadAttentionWeek;
  if(typeof stableLoadAttentionWeek==='function'){
    let seq=0;
    window.loadAttentionWeek=async function(force=false,anchorValue=null){
      const token=++seq;
      const effective=anchorValue||(typeof attentionWeekAnchor!=='undefined'?attentionWeekAnchor:null);
      const result=await stableLoadAttentionWeek.call(this,force,effective);
      if(!force){
        [1600,4800].forEach(delay=>wait(delay,()=>{
          if(token!==seq||!document.querySelector('#attentionWeekCalendar'))return;
          try{if(typeof invalidateAttentionWeekCache==='function')invalidateAttentionWeekCache()}catch(_e){}
          Promise.resolve(stableLoadAttentionWeek.call(window,true,effective)).catch(()=>{});
        }));
      }
      return result;
    };
  }

  // Agenda principal: una sola segunda lectura local. La primera ya no espera a
  // Neon gracias al backend v4.4.49.
  const stableLoadAgenda=window.loadAgenda;
  if(typeof stableLoadAgenda==='function'){
    let agendaSeq=0;
    window.loadAgenda=async function(){
      const token=++agendaSeq,args=arguments;
      const result=await stableLoadAgenda.apply(this,args);
      wait(2600,()=>{
        if(token!==agendaSeq)return;
        const sec=document.querySelector('#agenda');
        if(sec?.classList?.contains('hidden'))return;
        Promise.resolve(stableLoadAgenda.apply(window,args)).catch(()=>{});
      });
      return result;
    };
  }

  // Las citas legacy que YA tienen patient_id no son pacientes nuevos. Solo
  // los registros realmente staged/sin ficha siguen usando el flujo WhatsApp.
  const stableAttentionWeekRow=window.attentionWeekRow;
  if(typeof stableAttentionWeekRow==='function')window.attentionWeekRow=function(row){
    if(String(row?.source_type||'')==='CONFIRMAFY_LEGACY'&&Number(row?.patient?.id||0)>0){
      return stableAttentionWeekRow.call(this,{...row,source_type:'PATIENT_APPOINTMENT'});
    }
    return stableAttentionWeekRow.apply(this,arguments);
  };
  const stableNativeAgendaRowCell=window.nativeAgendaRowCell;
  if(typeof stableNativeAgendaRowCell==='function')window.nativeAgendaRowCell=function(row,date,time){
    if(String(row?.source_type||'')==='CONFIRMAFY_LEGACY'&&Number(row?.patient?.id||0)>0){
      return stableNativeAgendaRowCell.call(this,{...row,source_type:'PATIENT_APPOINTMENT'},date,time);
    }
    return stableNativeAgendaRowCell.apply(this,arguments);
  };

  const stableAttendFromAgenda=window.attendFromAgenda;
  async function openExistingUpdateAndAttend(patientId,fecha){
    const id=Number(patientId||0),today=toISO(new Date()),target=String(fecha||today).slice(0,10);
    if(!id)return stableAttendFromAgenda?.apply(window,arguments);
    if(target!==today&&!confirm(`Esta cita corresponde al ${fmtDate(target)}. ¿Registrar la atención con esa fecha?`))return;
    try{
      const p=await api('/api/patients/'+id);
      const missing=typeof missingPatientFields==='function'?missingPatientFields(p):[];
      if(!missing.length){
        return attentionFor(id,{fecha:target});
      }
      const missingText=missing.join(', ');
      openModal(`<div class="patient-form-modal v4449-existing-attend"><div class="modal-form-heading"><h2>Actualizar datos y atender</h2><p>Esta cita ya pertenece a <b>${esc(p.nombre||'este paciente')}</b>. Actualizaremos la misma ficha; no se creará otra.</p></div><div class="v4449-existing-note">Falta completar: <b>${esc(missingText)}</b></div>${patientForm(p)}<div class="actions form-actions"><button class="cancel-btn" onclick="newAttention()">Volver</button><button class="primary" onclick="v4449SaveExistingAndAttend(${id},'${target}')">Guardar cambios y atender</button></div></div>`);
      wait(35,()=>{
        try{window.__v4446PhoneGuardTest?.installWatcher?.(id,null)}catch(_e){}
        const first=missing.includes('cédula')?$('#fCedula'):(missing.includes('celular')?$('#fCel'):(missing.includes('correo')?$('#fMail'):$('#fNombre')));
        first?.focus?.();
      });
    }catch(e){alert(e.message||e)}
  }
  if(typeof stableAttendFromAgenda==='function')window.attendFromAgenda=openExistingUpdateAndAttend;

  window.v4449SaveExistingAndAttend=async function(patientId,fecha){
    const id=Number(patientId||0),target=String(fecha||toISO(new Date())).slice(0,10);
    try{
      const guard=window.__v4446PhoneGuardTest;
      if(guard?.checkVisiblePhone){
        const owner=await guard.checkVisiblePhone(id,false);
        if(owner){
          alert(`⚠ Este celular ya pertenece a otra ficha\n\n${owner.nombre||'Paciente existente'}\n\nNo se cambió esta ficha. Revisa el paciente correcto.`);
          return;
        }
      }
      const data=getPatientForm();
      await api('/api/patients/'+id,{method:'PUT',body:JSON.stringify(data)});
      try{if(typeof invalidateAttentionWeekCache==='function')invalidateAttentionWeekCache()}catch(_e){}
      await attentionFor(id,{fecha:target});
    }catch(e){alert(e.message||e)}
  };

  // Compatibilidad con citas antiguas importadas: si conservan patient_id,
  // nunca las convertimos a staged ni mostramos "Nueva ficha".
  const stableAttendLegacy=window.attendLegacyConfirmafy;
  if(typeof stableAttendLegacy==='function')window.attendLegacyConfirmafy=async function(appointmentId,fecha){
    try{
      const row=await api(`/api/agenda/appointments/${Number(appointmentId)}`);
      const patientId=Number(row?.patient?.id||row?.appointment?.patient_id||0);
      if(patientId)return window.attendFromAgenda(patientId,String(fecha||row?.appointment?.fecha||'').slice(0,10));
    }catch(_e){}
    return stableAttendLegacy.apply(this,arguments);
  };

  window.__v4449AgendaTest={openExistingUpdateAndAttend};
})();
"""

    V4449_AGENDA_FLOW_CSS = r"""
.v4449-existing-note{margin:10px 0 14px;padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d6e6f5;color:#536d86;font-size:10px;line-height:1.4}
.v4449-existing-note b{color:#274d70}
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4449_AGENDA_FLOW_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4449_AGENDA_FLOW_CSS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.48"' in app_text, "La base app no es 4.4.48")
    require("FEATURE_BOOT_OK = True" in app_text, "No se encontró punto de inserción seguro")
    app_text = app_text.replace('APP_VERSION = "4.4.48"', 'APP_VERSION = "4.4.49"', 1)
    app_text = app_text.replace("const VERSION='4.4.48';", "const VERSION='4.4.49';")
    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
    app_base = (SOURCE / "app_base_4428.py").read_bytes()
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
    compile(app_base.decode("utf-8-sig"), "app_base_4428.py", "exec")
    compile(launcher.decode("utf-8-sig"), "ABRIR_RECEPCION.py", "exec")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app)
    (OUT / "app_base_4428.py").write_bytes(app_base)
    for i, data in enumerate(launcher_parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.4.48-update-before-focus-dependency-safe-1",
        "updater_version": "integrado-en-launcher-update-before-focus",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_49_agenda_flow_speed/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.49: Agenda abre desde SQLite sin esperar a Neon y actualiza Cloud en segundo plano; "
            "las citas con patient_id actualizan la ficha existente antes de atender en vez de crear otra; "
            "y Cita agendada deja de mostrar una hora UTC falsa. Conserva protección semanal, identidad por celular y todos los arreglos 4.4.48."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4449_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()
