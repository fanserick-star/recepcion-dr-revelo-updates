from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"
SOURCE_REF = "5789f783702ce69769e139b63ecfeacdd0849605"
SOURCE_PREFIX = "updates/v4_4_43_daily_emitted_whatsapp_schedule"
VERSION = "4.4.44"
SOURCE_SHA256 = {
    "ABRIR_RECEPCION.py": "39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e",
    "app_base_4428.py": "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
    "app.py": "5bebead7606bfaea8cf04f83b657f8511a167a16506ae4c0d096df606786ec19",
    "static/app.js": "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
    "static/index.html": "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


FEATURE_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.44 — guardia semanal contra citas duplicadas por paciente.
    # -----------------------------------------------------------------------
    # No cambia tablas ni reemplaza agenda_create. El endpoint nuevo hace la
    # advertencia y luego delega el guardado real en la función estable 4.4.43.
    class AgendaGuardedAppointmentIn(core.BaseModel):
        patient_id: int
        fecha: _date
        hora: str
        nota: str | None = None
        allow_same_week: bool = False

    def _v4444_phone_variants(value: object) -> list[str]:
        raw = str(value or "").strip()
        clean = core.normalize_lookup_phone(raw)
        values = {x for x in (raw, clean) if x}
        if len(clean) == 10 and clean.startswith("0"):
            values.add("593" + clean[1:])
        return sorted(values)

    def _v4444_same_week_conflict(db, patient, target_date: _date):
        monday = target_date - core.timedelta(days=target_date.weekday())
        sunday = monday + core.timedelta(days=6)
        variants = _v4444_phone_variants(getattr(patient, "celular", ""))

        identity = [core.Appointment.patient_id == int(patient.id)]
        if variants:
            identity.append(core.Patient.celular.in_(variants))

        linked = db.execute(
            core.select(core.Appointment, core.Patient)
            .join(core.Patient, core.Patient.id == core.Appointment.patient_id)
            .where(
                core.Appointment.fecha >= monday,
                core.Appointment.fecha <= sunday,
                core.Appointment.origen != core.CONFIRMAFY_ATTENDED_ORIGIN,
                ~core.func.upper(core.func.coalesce(core.Appointment.estado, "")).in_(
                    ["CANCELADA", "CANCELADO", "NO_ASISTIRA", "NO_ASISTIRÁ", "REAGENDADA"]
                ),
                core.or_(*identity),
            )
            .order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id)
            .limit(1)
        ).first()
        if linked:
            appointment, owner = linked
            return {
                "source": "appointment",
                "date": appointment.fecha.isoformat(),
                "time": appointment.hora,
                "name": owner.nombre,
            }

        if variants:
            staged = db.scalar(
                core.select(core.ConfirmafyAgendaItem)
                .where(
                    core.ConfirmafyAgendaItem.fecha >= monday,
                    core.ConfirmafyAgendaItem.fecha <= sunday,
                    core.ConfirmafyAgendaItem.celular.in_(variants),
                )
                .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)
                .limit(1)
            )
            if staged:
                return {
                    "source": "staged",
                    "date": staged.fecha.isoformat(),
                    "time": staged.hora,
                    "name": staged.nombre,
                }
        return None

    @app.get("/api/agenda/week-conflict")
    def agenda_week_conflict_v4444(
        patient_id: int,
        fecha: _date,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        patient = db.get(core.Patient, int(patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        conflict = _v4444_same_week_conflict(db, patient, fecha)
        monday = fecha - core.timedelta(days=fecha.weekday())
        return {
            "conflict": conflict,
            "week_start": monday.isoformat(),
            "week_end": (monday + core.timedelta(days=6)).isoformat(),
        }

    @app.post("/api/agenda/appointments/guarded")
    def agenda_create_guarded_v4444(
        data: AgendaGuardedAppointmentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        if not core.confirmafy_phone(patient.celular):
            raise core.HTTPException(400, "Completa el celular del paciente antes de reagendar")

        stable_data = core.AppointmentIn(
            patient_id=int(data.patient_id), fecha=data.fecha, hora=data.hora, nota=data.nota
        )
        values = core.normalize_appointment_payload(stable_data)

        # La ocupación del bloque continúa siendo un bloqueo duro y se evalúa
        # ANTES de cualquier posibilidad de saltar la advertencia semanal.
        slot_conflicts = core.appointment_conflicts(db, values["fecha"], values["hora"], 20)
        if slot_conflicts:
            raise core.HTTPException(
                409,
                core.occupied_message(values["fecha"], values["hora"], slot_conflicts),
            )

        conflict = _v4444_same_week_conflict(db, patient, values["fecha"])
        if conflict and not bool(data.allow_same_week):
            return {"created": False, "same_week_conflict": conflict}

        # Reutiliza el guardado estable. Este vuelve a comprobar el horario,
        # conserva auditoría, offline/local-first, mirrors y WhatsApp existentes.
        result = core.agenda_create(stable_data, db, user)
        return {"created": True, "appointment": result}

    V4444_WEEK_GUARD_CSS = r"""
.v4444-week-guard-backdrop{position:fixed;inset:0;z-index:100000;display:grid;place-items:center;padding:18px;background:rgba(20,34,49,.48);backdrop-filter:blur(2px)}
.v4444-week-guard-card{width:min(470px,94vw);padding:20px;border-radius:18px;background:#fff;box-shadow:0 20px 60px rgba(19,38,58,.28);border:1px solid #dbe5ef}
.v4444-week-guard-card h3{margin:0 0 7px;font-size:18px;color:#263d55}.v4444-week-guard-card p{margin:0;color:#60748a;font-size:12px;line-height:1.45}
.v4444-week-guard-existing{margin:14px 0;padding:12px;border-radius:12px;background:#fff8e9;border:1px solid #ecd9a9;display:grid;gap:3px}
.v4444-week-guard-existing span{font-size:9px;font-weight:900;letter-spacing:.07em;color:#85652c}.v4444-week-guard-existing b{font-size:13px;color:#5f4b27}.v4444-week-guard-existing small{font-size:11px;color:#75664a}
.v4444-week-guard-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}.v4444-week-guard-actions button{min-height:38px;padding:8px 13px;border-radius:10px;border:1px solid #cfdbe6;background:#fff;font-weight:850;cursor:pointer}.v4444-week-guard-actions .proceed{background:#2f6698;color:#fff;border-color:#2f6698}
@media(max-width:560px){.v4444-week-guard-actions{flex-direction:column-reverse}.v4444-week-guard-actions button{width:100%}}
"""

    V4444_WEEK_GUARD_JS = r"""
;(()=>{
  if(window.__v4444WeeklyAppointmentGuard)return;
  window.__v4444WeeklyAppointmentGuard=true;

  function weeklyGuardAsk(conflict){
    return new Promise(resolve=>{
      document.querySelector('.v4444-week-guard-backdrop')?.remove();
      const root=document.createElement('div');root.className='v4444-week-guard-backdrop';
      const d=String(conflict?.date||''),t=String(conflict?.time||''),n=String(conflict?.name||'Paciente');
      root.innerHTML=`<div class="v4444-week-guard-card" role="dialog" aria-modal="true"><h3>Este paciente ya tiene una cita esta semana</h3><p>Revisa la cita existente antes de crear otra. Si realmente necesita dos citas en la misma semana, puedes continuar manualmente.</p><div class="v4444-week-guard-existing"><span>CITA YA REGISTRADA ESA SEMANA</span><b>${esc(n)}</b><small>${fmtDate(d)} · ${fmtTime(t)}</small></div><div class="v4444-week-guard-actions"><button type="button" data-action="cancel">Cancelar</button><button type="button" class="proceed" data-action="proceed">Agendar de todas formas</button></div></div>`;
      const done=value=>{root.remove();resolve(value)};
      root.querySelector('[data-action="cancel"]')?.addEventListener('click',()=>done(false));
      root.querySelector('[data-action="proceed"]')?.addEventListener('click',()=>done(true));
      root.addEventListener('click',e=>{if(e.target===root)done(false)});
      document.body.appendChild(root);
    });
  }

  window.saveAgendaAppointment=async function(appointmentId=null){
    // Editar una cita existente conserva exactamente el flujo estable 4.4.43.
    if(appointmentId){
      try{
        const p=agendaPatientCache;if(!p)throw Error('No se encontró el paciente.');
        const fecha=$('#agendaDate')?.value,hora=$('#agendaTime')?.value,nota=($('#agendaNote')?.value||'').trim();
        if(!fecha||!hora)throw Error('Selecciona fecha y hora.');
        const body={fecha,hora,nota};
        await singleFlightMutation(`appointment:${appointmentId}:${p.id}`,async()=>{await api(`/api/agenda/appointments/${appointmentId}`,{method:'PUT',body:JSON.stringify(body)});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda()},'Guardando cita…');
      }catch(e){alert(e.message)}
      return;
    }

    try{
      const p=agendaPatientCache;if(!p)throw Error('No se encontró el paciente.');
      const fecha=$('#agendaDate')?.value,hora=$('#agendaTime')?.value,nota=($('#agendaNote')?.value||'').trim();
      if(!fecha||!hora)throw Error('Selecciona fecha y hora.');
      const key=`appointment:new:${p.id}`;
      await singleFlightMutation(key,async()=>{
        const submit=async allow=>api('/api/agenda/appointments/guarded',{method:'POST',body:JSON.stringify({patient_id:p.id,fecha,hora,nota,allow_same_week:!!allow})});
        let result=await submit(false);
        if(result?.same_week_conflict){
          const proceed=await weeklyGuardAsk(result.same_week_conflict);
          if(!proceed)return;
          result=await submit(true);
        }
        if(!result?.created)throw Error('No se pudo confirmar el guardado de la cita. No se creó ninguna cita.');
        invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();agendaNativeAnchor=fecha;await loadAgenda();
      },'Guardando cita…');
    }catch(e){alert(e.message)}
  };

  window.__v4444WeeklyGuardTest={weeklyGuardAsk};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4444_WEEK_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4444_WEEK_GUARD_JS
'''


def build() -> None:
    parts = [git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5)]
    launcher = b"".join(parts)
    require(sha(launcher) == SOURCE_SHA256["ABRIR_RECEPCION.py"], "Launcher 4.4.43 cambió")

    fixed = {
        "app_base_4428.py": git_bytes("app_base_4428.py"),
        "app.py": git_bytes("app.py"),
        "static/app.js": git_bytes("static/app.js"),
        "static/index.html": git_bytes("static/index.html"),
    }
    for rel in fixed:
        require(sha(fixed[rel]) == SOURCE_SHA256[rel], f"Fuente 4.4.43 cambió: {rel}")

    app_text = fixed["app.py"].decode("utf-8-sig")
    require(app_text.count('APP_VERSION = "4.4.43"') == 1, "APP_VERSION 4.4.43 ambiguo")
    app_text = app_text.replace('APP_VERSION = "4.4.43"', 'APP_VERSION = "4.4.44"', 1)
    app_text = app_text.replace("const VERSION='4.4.43';", "const VERSION='4.4.44';")
    app_text = app_text.replace('"const VERSION=\'4.4.43\';"', '"const VERSION=\'4.4.44\';"')
    anchor = "\n    FEATURE_BOOT_OK = True\n"
    require(app_text.count(anchor) == 1, "Ancla FEATURE_BOOT_OK cambió")
    app_text = app_text.replace(anchor, FEATURE_BLOCK + anchor, 1)
    compile(app_text, "app.py", "exec")
    app_bytes = app_text.encode("utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "static").mkdir(exist_ok=True)
    for i, part in enumerate(parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(part)
    (OUT / "app_base_4428.py").write_bytes(fixed["app_base_4428.py"])
    (OUT / "app.py").write_bytes(app_bytes)
    (OUT / "static/app.js").write_bytes(fixed["static/app.js"])
    (OUT / "static/index.html").write_bytes(fixed["static/index.html"])

    paths = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    manifest = {
        "product": "recepcion-pacientes", "version": VERSION, "app_version": VERSION, "runtime_version": VERSION,
        "launcher_version": "4.4.42-dynamic-port-file-python-dependency-guard-1", "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": paths,
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_44_weekly_appointment_guard/"
    files = [
        {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
        {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(fixed["app_base_4428.py"]), "encoding": "utf-8"},
        {"path": "app.py", "url": raw + "app.py", "sha256": sha(app_bytes), "encoding": "utf-8"},
        {"path": "static/app.js", "url": raw + "static/app.js", "sha256": sha(fixed["static/app.js"]), "encoding": "utf-8"},
        {"path": "static/index.html", "url": raw + "static/index.html", "sha256": sha(fixed["static/index.html"]), "encoding": "utf-8"},
        {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
    ]
    candidate = {
        "product": "recepcion-pacientes", "version": VERSION, "app_version": VERSION, "runtime_version": VERSION,
        "mandatory": True, "channel": "files-v3",
        "message": "v4.4.44: Nueva cita advierte si el mismo paciente ya tiene una cita entre lunes y domingo y permite Agendar de todas formas solo con confirmación manual. Los horarios ocupados siguen siendo bloqueo duro. No cambia tablas, .env, data ni bases; conserva íntegra la 4.4.43 y su launcher.",
        "files": files,
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))

    require(sha((OUT / "app_base_4428.py").read_bytes()) == SOURCE_SHA256["app_base_4428.py"], "Base estable fue modificada")
    require(sha((OUT / "static/app.js").read_bytes()) == SOURCE_SHA256["static/app.js"], "JS base fue modificado")
    require("/api/agenda/appointments/guarded" in app_text, "Falta endpoint guarded")
    require("Agendar de todas formas" in app_text, "Falta override explícito")
    require("core.agenda_create(stable_data, db, user)" in app_text, "No delega al guardado estable")
    print("BUILD_V4444_OK")
    print("APP_SHA", sha(app_bytes))


if __name__ == "__main__":
    build()
