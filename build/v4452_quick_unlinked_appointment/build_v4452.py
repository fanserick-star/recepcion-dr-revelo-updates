from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_51_payment_source_of_truth"
OUT = ROOT / "updates" / "v4_4_52_quick_unlinked_appointment"
VERSION = "4.4.52"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.52 — Nueva cita rápida SIN crear ficha de paciente.
    # -----------------------------------------------------------------------
    # La agenda no debe obligar a inventar/completar una ficha clínica para
    # reservar un horario. Si recepción solo conoce nombre + celular, guardamos
    # una cita staged (sin patient_id), igual que las citas que llegan por
    # WhatsApp. La identidad se resuelve recién al atender.

    class V4452QuickAppointmentIn(core.BaseModel):
        nombre: str
        celular: str
        fecha: _date
        hora: str
        allow_same_week: bool = False

    def _v4452_quick_source_hash(nombre: str, celular: str, fecha, hora: str) -> str:
        clean_name = core.normalize_lookup_name(nombre or "PACIENTE")
        clean_phone = core.normalize_lookup_phone(celular or "")
        seed = core.uuid.uuid4().hex
        return "pc:quick:" + core.hashlib.sha1(
            f"{clean_name}|{clean_phone}|{fecha.isoformat()}|{hora}|{seed}".encode("utf-8")
        ).hexdigest()

    @app.post("/api/agenda/unlinked/guarded")
    def v4452_create_quick_unlinked_appointment(
        data: V4452QuickAppointmentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        name = " ".join(str(data.nombre or "").split()).upper()
        phone = core.re.sub(r"\D", "", str(data.celular or ""))
        if len(name) < 3:
            raise core.HTTPException(400, "Escribe el nombre del paciente")
        if len(phone) < 8 or len(phone) > 15:
            raise core.HTTPException(400, "Escribe un celular válido")

        values = core.normalize_appointment_payload(data)
        slot_conflicts = core.appointment_conflicts(
            db, values["fecha"], values["hora"], 20
        )
        if slot_conflicts:
            raise core.HTTPException(
                409,
                core.occupied_message(values["fecha"], values["hora"], slot_conflicts),
            )

        # Reutilizamos la guardia semanal ya probada, pero la identidad aquí es
        # el celular porque todavía NO existe una ficha de paciente.
        phone_identity = type(
            "V4452PhoneIdentity", (), {"id": -4452, "celular": phone}
        )()
        conflict = _v4444_same_week_conflict(db, phone_identity, values["fecha"])
        if conflict and not bool(data.allow_same_week):
            return {"created": False, "same_week_conflict": conflict}

        source_hash = _v4452_quick_source_hash(
            name, phone, values["fecha"], values["hora"]
        )
        item = core.ConfirmafyAgendaItem(
            nombre=name,
            celular=phone,
            fecha=values["fecha"],
            hora=values["hora"],
            duracion=20,
            source_hash=source_hash,
        )
        db.add(item)
        db.flush()
        offline = core.is_offline_db(db)
        if offline:
            core.add_queue(
                db,
                "confirmafy_staged.create",
                "confirmafy_staged",
                {
                    "nombre": item.nombre,
                    "celular": item.celular,
                    "fecha": item.fecha.isoformat(),
                    "hora": item.hora,
                    "source_hash": item.source_hash,
                },
                user.username,
                item.id,
            )
        core.audit(
            db,
            user,
            "crear_cita_rapida_sin_ficha",
            f"{name} · {values['fecha']} {values['hora']}",
        )
        db.commit()

        if not offline:
            try:
                db.refresh(item)
            except Exception:
                pass
            try:
                core.mirror_confirmafy_agenda_local(item)
            except Exception:
                pass
            try:
                core.schedule_whatsapp_for_contact(
                    source_type="staged",
                    source_id=item.id,
                    name=item.nombre,
                    phone=item.celular or "",
                    fecha=item.fecha,
                    hora=item.hora,
                )
            except Exception:
                pass

        return {
            "created": True,
            "staged": core.confirmafy_agenda_dict(item),
            "offline": bool(offline),
            "unlinked": True,
        }

    V4452_QUICK_APPOINTMENT_JS = r"""
;(()=>{
  if(window.__v4452QuickUnlinkedAppointment)return;
  window.__v4452QuickUnlinkedAppointment=true;

  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  const esc2=v=>typeof esc==='function'?esc(String(v??'')):String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function newAppointmentModal(){
    return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(box=>
      [...box.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva cita')
    )||null;
  }

  function parseSlotText(text){
    const raw=String(text||'').replace(/\s+/g,' ').trim();
    const dm=/(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(raw);
    const tm=/(\d{1,2}):(\d{2})\s*(a\.?\s*m\.?|p\.?\s*m\.?|am|pm)?/i.exec(raw);
    if(!dm||!tm)return null;
    const dd=Number(dm[1]),mm=Number(dm[2]),yy=Number(dm[3]);
    let hh=Number(tm[1]),mi=Number(tm[2]);
    const ap=norm(tm[3]||'').replace(/\./g,'').replace(/\s/g,'');
    if(ap==='pm'&&hh<12)hh+=12;
    if(ap==='am'&&hh===12)hh=0;
    if(!(dd>=1&&dd<=31&&mm>=1&&mm<=12&&hh>=0&&hh<=23&&mi>=0&&mi<=59))return null;
    return {fecha:`${String(yy).padStart(4,'0')}-${String(mm).padStart(2,'0')}-${String(dd).padStart(2,'0')}`,hora:`${String(hh).padStart(2,'0')}:${String(mi).padStart(2,'0')}`};
  }

  function slotFromModal(box){
    const dateInput=box?.querySelector('#agendaDate,input[type="date"]');
    const timeInput=box?.querySelector('#agendaTime,input[type="time"]');
    const fecha=String(dateInput?.value||'').slice(0,10),hora=String(timeInput?.value||'').slice(0,5);
    if(/^\d{4}-\d{2}-\d{2}$/.test(fecha)&&/^\d{2}:\d{2}$/.test(hora))return {fecha,hora};
    const candidates=[...box.querySelectorAll('span,button,div')]
      .map(el=>String(el.textContent||'').trim())
      .filter(t=>t.length>5&&t.length<90&&/\d{1,2}\/\d{1,2}\/\d{4}/.test(t)&&/\d{1,2}:\d{2}/.test(t))
      .sort((a,b)=>a.length-b.length);
    for(const text of candidates){const parsed=parseSlotText(text);if(parsed)return parsed}
    return parseSlotText(box?.textContent||'');
  }

  function fmtSlot(slot){
    try{return `${typeof fmtDate==='function'?fmtDate(slot.fecha):slot.fecha} · ${typeof fmtTime==='function'?fmtTime(slot.hora):slot.hora}`}
    catch(_e){return `${slot.fecha} · ${slot.hora}`}
  }

  window.v4452OpenQuickAppointment=function(){
    const source=newAppointmentModal();
    const slot=slotFromModal(source);
    if(!slot){alert('No pude identificar la fecha y hora seleccionadas. Cierra esta ventana y vuelve a tocar el horario.');return}
    openModal(`<div class="v4452-quick-modal"><div class="modal-form-heading"><h2>Crear cita nueva</h2><p>Reserva el horario solo con nombre y celular. La ficha del paciente se completará o vinculará cuando sea atendido.</p></div><div class="v4452-slot"><span>Horario seleccionado</span><b>${esc2(fmtSlot(slot))}</b></div><div class="v4452-fields"><label>Apellidos y nombres<input id="v4452QuickName" maxlength="220" autocomplete="off" placeholder="APELLIDOS Y NOMBRES" oninput="this.value=this.value.toUpperCase()"></label><label>Celular<input id="v4452QuickPhone" inputmode="numeric" maxlength="15" autocomplete="tel" placeholder="09XXXXXXXX" oninput="this.value=this.value.replace(/[^0-9]/g,'')"></label></div><div class="v4452-note">Esta acción <b>no crea una ficha de paciente</b>. La cita quedará como “sin ficha vinculada”.</div><div class="actions form-actions"><button class="cancel-btn" onclick="closeModal()">Cancelar</button><button id="v4452QuickSave" class="primary" onclick="v4452SaveQuickAppointment('${slot.fecha}','${slot.hora}',false)">Guardar cita</button></div></div>`);
    setTimeout(()=>document.querySelector('#v4452QuickName')?.focus(),30);
  };

  window.v4452SaveQuickAppointment=async function(fecha,hora,allowSameWeek=false){
    const name=String(document.querySelector('#v4452QuickName')?.value||'').trim().replace(/\s+/g,' ').toUpperCase();
    const phone=String(document.querySelector('#v4452QuickPhone')?.value||'').replace(/[^0-9]/g,'');
    if(name.length<3){alert('Escribe el nombre del paciente.');document.querySelector('#v4452QuickName')?.focus();return}
    if(phone.length<8||phone.length>15){alert('Escribe un celular válido.');document.querySelector('#v4452QuickPhone')?.focus();return}
    const btn=document.querySelector('#v4452QuickSave');if(btn){btn.disabled=true;btn.textContent='Guardando…'}
    try{
      const result=await api('/api/agenda/unlinked/guarded',{method:'POST',body:JSON.stringify({nombre:name,celular:phone,fecha,hora,allow_same_week:!!allowSameWeek})});
      if(result?.same_week_conflict&&!allowSameWeek){
        const c=result.same_week_conflict||{};
        const when=`${typeof fmtDate==='function'?fmtDate(c.date):String(c.date||'')} · ${typeof fmtTime==='function'?fmtTime(c.time):String(c.time||'')}`;
        const proceed=confirm(`Este paciente ya tiene una cita esta semana:\n\n${String(c.name||name)}\n${when}\n\n¿Agendar de todas formas?`);
        if(proceed)return v4452SaveQuickAppointment(fecha,hora,true);
        return;
      }
      if(!result?.created)throw Error('No se pudo crear la cita.');
      try{invalidateAgendaSlotCache()}catch(_e){}
      try{invalidateAttentionWeekCache()}catch(_e){}
      closeModal();
      try{agendaNativeAnchor=fecha}catch(_e){}
      if(typeof loadAgenda==='function')await loadAgenda();
      if(typeof rpNotice==='function')rpNotice('Cita creada sin ficha de paciente.');
    }catch(e){alert(e.message||e)}
    finally{const b=document.querySelector('#v4452QuickSave');if(b){b.disabled=false;b.textContent='Guardar cita'}}
  };

  function decorate(){
    const box=newAppointmentModal();if(!box)return;
    const buttons=[...box.querySelectorAll('button')];
    const old=buttons.find(b=>norm(b.textContent).includes('nuevo paciente'));
    if(old&&!old.dataset.v4452Quick){
      old.dataset.v4452Quick='1';
      old.textContent='＋ Crear cita nueva';
      old.removeAttribute('onclick');
      old.onclick=e=>{e?.preventDefault?.();e?.stopPropagation?.();window.v4452OpenQuickAppointment()};
      old.title='Agendar solo con nombre y celular, sin crear ficha de paciente';
    }
    const heading=[...box.querySelectorAll('.modal-form-heading p,p')].find(p=>norm(p.textContent).includes('selecciona primero'));
    if(heading&&!heading.dataset.v4452Copy){heading.dataset.v4452Copy='1';heading.textContent='Selecciona un paciente existente o crea una cita nueva solo con nombre y celular.'}
  }

  const obs=new MutationObserver(()=>{setTimeout(decorate,0);setTimeout(decorate,80)});
  const start=()=>{obs.observe(document.body,{childList:true,subtree:true});decorate()};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  document.addEventListener('click',()=>setTimeout(decorate,20),true);

  window.__v4452QuickTest={parseSlotText,slotFromModal,decorate};
})();
"""

    V4452_QUICK_APPOINTMENT_CSS = r"""
.v4452-quick-modal{width:min(600px,92vw);display:grid;gap:13px}.v4452-slot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;border:1px solid #cce0d3;border-radius:12px;background:#f1faf4}.v4452-slot span{font-size:8px;font-weight:900;color:#688176;text-transform:uppercase;letter-spacing:.04em}.v4452-slot b{font-size:11px;color:#285a3c}.v4452-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.v4452-fields label{display:grid;gap:5px;font-size:9px;font-weight:900;color:#455f75}.v4452-fields input{width:100%;min-height:43px;border:1px solid #cad8e5;border-radius:10px;padding:9px 11px;font-size:11px;font-weight:800;box-sizing:border-box;background:#fff;color:#233e57}.v4452-fields input:focus{outline:0;border-color:#5d91c7;box-shadow:0 0 0 3px rgba(70,126,181,.10)}.v4452-note{padding:9px 11px;border-radius:10px;background:#f7f9fb;color:#65798b;font-size:8.5px;line-height:1.35}.v4452-note b{color:#415c72}@media(max-width:650px){.v4452-fields{grid-template-columns:1fr}.v4452-slot{align-items:flex-start;flex-direction:column}}
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4452_QUICK_APPOINTMENT_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4452_QUICK_APPOINTMENT_CSS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.51"' in app_text, "La base app no es 4.4.51")
    require("FEATURE_BOOT_OK = True" in app_text, "No se encontró punto de inserción seguro")

    app_text = app_text.replace('APP_VERSION = "4.4.51"', 'APP_VERSION = "4.4.52"', 1)
    app_text = app_text.replace("const VERSION='4.4.51';", "const VERSION='4.4.52';")
    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
    app_base = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
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

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_52_quick_unlinked_appointment/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.52: Nueva cita ya no crea fichas de paciente. El botón pasa a Crear cita nueva y permite "
            "reservar solo con apellidos/nombres y celular; la cita queda sin ficha vinculada y la identidad se "
            "resuelve al atender. Conserva protección de horario y guardia semanal por celular, además de todos "
            "los arreglos de v4.4.51."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4452_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()
