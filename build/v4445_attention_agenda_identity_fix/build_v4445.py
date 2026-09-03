from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V4444_BUILDER = ROOT / "build" / "v4444_weekly_appointment_guard" / "build_v4444.py"
V4444_OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"
OUT = ROOT / "updates" / "v4_4_45_attention_agenda_identity_fix"
VERSION = "4.4.45"

STABLE_HASHES = {
    "ABRIR_RECEPCION.py": "39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e",
    "app_base_4428.py": "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
    "static/app.js": "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
    "static/index.html": "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


FEATURE_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.45 — Agenda Cloud completa en Nueva atención + identidad segura.
    # -----------------------------------------------------------------------
    # La PC continúa siendo local-first. Únicamente al abrir /api/agenda/week,
    # y solo si no hay cambios offline pendientes, se copian a SQLite las citas
    # de esa semana que ya existen en Neon. No hay migraciones ni tablas nuevas.
    _v4445_cloud_agenda_lock = core.threading.Lock()
    _v4445_cloud_agenda_at = {}

    def _v4445_sync_cloud_agenda_for_dates(dates, min_interval: float = 5.0) -> int:
        normalized = []
        for value in dates or []:
            try:
                item_date = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
            except Exception:
                continue
            if item_date not in normalized:
                normalized.append(item_date)
        normalized.sort()
        if not normalized:
            return 0
        if not core.cloud_configured() or core.FORCE_OFFLINE or not core.CloudSessionLocal:
            return 0
        # Nunca mezclamos una descarga de nube con escrituras locales todavía
        # pendientes de subir. La cola offline conserva prioridad absoluta.
        if core.queue_count() > 0:
            return 0

        key = "|".join(x.isoformat() for x in normalized)
        now = core.time.time()
        if not _v4445_cloud_agenda_lock.acquire(blocking=False):
            return 0
        try:
            last = float(_v4445_cloud_agenda_at.get(key) or 0.0)
            if last and now - last < max(1.0, float(min_interval or 5.0)):
                return 0
            if not core.check_cloud(force=False):
                return 0

            # Leemos solamente los días visibles. Las citas vinculadas traen su
            # Patient para que la FK local exista; las citas WhatsApp/sin vincular
            # se conservan como ConfirmafyAgendaItem y NO crean fichas Patient.
            with core.CloudSessionLocal() as cdb:
                linked = list(cdb.execute(
                    core.select(core.Appointment, core.Patient)
                    .join(core.Patient, core.Patient.id == core.Appointment.patient_id)
                    .where(core.Appointment.fecha.in_(normalized))
                    .order_by(core.Appointment.fecha, core.Appointment.hora, core.Appointment.id)
                ).all())
                staged = list(cdb.scalars(
                    core.select(core.ConfirmafyAgendaItem)
                    .where(core.ConfirmafyAgendaItem.fecha.in_(normalized))
                    .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)
                ))

            mirrored = 0
            for appointment, patient in linked:
                # Las funciones estables hacen UPSERT local y commit. Si hubiera
                # cualquier problema aislado, ellas fallan de forma segura sin
                # tumbar la Agenda.
                core.mirror_patient_to_local(patient)
                core.mirror_appointment_to_local(appointment)
                mirrored += 1

            with core.LocalSessionLocal() as ldb:
                changed = False
                for row in staged:
                    source_hash = str(getattr(row, "source_hash", "") or "").strip()
                    if not source_hash or source_hash.startswith("mobile:whatsapp-cloud-test:"):
                        continue
                    existing = ldb.scalar(
                        core.select(core.ConfirmafyAgendaItem)
                        .where(core.ConfirmafyAgendaItem.source_hash == source_hash)
                        .limit(1)
                    )
                    values = {
                        "nombre": row.nombre,
                        "celular": row.celular,
                        "fecha": row.fecha,
                        "hora": row.hora,
                        "duracion": int(row.duracion or 20),
                        "created_at": row.created_at,
                    }
                    if existing is not None:
                        dirty = False
                        for attr, value in values.items():
                            if getattr(existing, attr, None) != value:
                                setattr(existing, attr, value)
                                dirty = True
                        if dirty:
                            changed = True
                            mirrored += 1
                        continue

                    cloud_id = int(row.id)
                    # Preservar el ID de Neon es importante porque al marcar una
                    # cita staged como atendida el POST se resuelve en la nube.
                    # Si existiera una colisión local excepcional, no pisamos nada.
                    if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:
                        continue
                    ldb.add(core.ConfirmafyAgendaItem(
                        id=cloud_id,
                        source_hash=source_hash,
                        **values,
                    ))
                    changed = True
                    mirrored += 1
                if changed:
                    ldb.commit()

            _v4445_cloud_agenda_at[key] = core.time.time()
            return mirrored
        except Exception as exc:
            # Fail-open: si Neon está lento o cae, Nueva atención sigue abriendo
            # con la copia SQLite que ya tenía la PC.
            try:
                with core._state_lock:
                    core._state["last_error"] = f"No se pudo actualizar Agenda Cloud: {core._cloud_error_hint(exc)}"[:300]
            except Exception:
                pass
            return 0
        finally:
            _v4445_cloud_agenda_lock.release()

    @app.middleware("http")
    async def v4445_cloud_agenda_catchup(request, call_next):
        if request.url.path == "/api/agenda/week":
            try:
                raw_anchor = str(request.query_params.get("anchor") or "").strip()
                anchor_date = _date.fromisoformat(raw_anchor[:10])
                monday = anchor_date - core.timedelta(days=anchor_date.weekday())
                week_dates = [monday + core.timedelta(days=i) for i in range(7)]
                # Es intencionalmente síncrono antes de dibujar: así una cita que
                # acaba de entrar por WhatsApp no aparece como hueco libre.
                _v4445_sync_cloud_agenda_for_dates(week_dates)
            except Exception:
                pass
        return await call_next(request)

    V4445_STAGED_IDENTITY_CSS = r"""
.v4445-phone-match-list{display:grid;gap:9px;margin:14px 0}
.v4445-phone-match-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border:1px solid #d7e2ec;border-radius:12px;background:#f9fbfd}
.v4445-phone-match-row>div{display:grid;gap:3px;min-width:0}.v4445-phone-match-row b{font-size:12px;color:#263f59}.v4445-phone-match-row small{font-size:10px;color:#687d92}
.v4445-phone-match-row button{flex:0 0 auto;min-height:35px;padding:7px 11px;border-radius:9px;border:1px solid #2f6698;background:#2f6698;color:#fff;font-weight:850;cursor:pointer}
.v4445-phone-note{padding:10px 12px;border-radius:11px;background:#eef6ff;border:1px solid #d3e4f5;color:#526d88;font-size:10.5px;line-height:1.4}
@media(max-width:560px){.v4445-phone-match-row{align-items:stretch;flex-direction:column}.v4445-phone-match-row button{width:100%}}
"""

    V4445_STAGED_IDENTITY_JS = r"""
;(()=>{
  if(window.__v4445StagedIdentityFix)return;
  window.__v4445StagedIdentityFix=true;

  const stableAttend=window.attendConfirmafyStaged;
  const stableNewPatient=window.newPatientFromStaged;
  if(typeof stableAttend!=='function'||typeof stableNewPatient!=='function')return;

  function phoneKey(value){
    let d=String(value||'').replace(/\D/g,'');
    if(d.startsWith('593')&&d.length>=12)d='0'+d.slice(3);
    return d;
  }
  function phoneQueries(value){
    const local=phoneKey(value),out=[];
    if(local)out.push(local);
    if(local.length===10&&local.startsWith('0'))out.push('593'+local.slice(1));
    return [...new Set(out)];
  }
  async function exactCurrentPhoneMatches(staged){
    const wanted=phoneKey(staged?.celular);
    if(!wanted)return [];
    const batches=await Promise.all(phoneQueries(staged.celular).map(q=>
      api('/api/patients?q='+encodeURIComponent(q)+'&limit=24').catch(()=>[])
    ));
    const found=new Map();
    for(const p of batches.flat()){
      if(!p||Number(p.id||0)<=0)continue;
      if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p))continue;
      if(phoneKey(p.celular)===wanted)found.set(Number(p.id),p);
    }
    return [...found.values()];
  }
  function showPhoneMatches(itemId,fecha,staged,rows){
    const target=String(fecha||staged?.fecha||toISO(new Date())).slice(0,10);
    currentStagedResolve=staged;
    const title=rows.length===1?'Encontramos una ficha con este celular':'Encontramos fichas con este celular';
    const list=rows.map(p=>`<article class="v4445-phone-match-row"><div><b>${esc(p.nombre||'Paciente')}</b><small>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</small></div><button type="button" onclick="usePatientForStaged(${Number(itemId)},${Number(p.id)},'${target}')">Usar esta ficha</button></article>`).join('');
    openModal(`<div class="staged-attend-modal v4445-phone-match"><div class="modal-form-heading"><h2>${esc(title)}</h2><p>La cita trae un celular que ya está asociado a una ficha. Revísala antes de crear otro paciente.</p></div><div class="v4445-phone-note">Si corresponde a este paciente, usa su ficha existente y podrás completar los datos que falten dentro de la atención. No se creará un duplicado.</div><div class="v4445-phone-match-list">${list}</div><div class="actions wrap-actions"><button type="button" onclick="openSubsequentStagedSearch(${Number(itemId)},'${target}')">Buscar otra ficha</button><button type="button" onclick="v4445CreateDifferentStaged(${Number(itemId)},'${target}')">Es otra persona</button><button type="button" class="cancel-btn" onclick="closeModal()">Cancelar</button></div></div>`);
  }

  window.v4445CreateDifferentStaged=function(itemId,fecha){
    return stableNewPatient(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));
  };

  window.attendConfirmafyStaged=async function(itemId,fecha){
    try{
      const staged=await getConfirmafyStagedRow(Number(itemId));
      const rows=await exactCurrentPhoneMatches(staged);
      if(rows.length){
        showPhoneMatches(Number(itemId),fecha,staged,rows);
        return;
      }
    }catch(e){
      console.warn('v4445_staged_identity_lookup_failed',e);
    }
    return stableAttend(Number(itemId),fecha);
  };

  window.__v4445IdentityTest={phoneKey,phoneQueries};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4445_STAGED_IDENTITY_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4445_STAGED_IDENTITY_JS
'''


def build() -> None:
    # Parte exactamente de la candidata 4.4.44 que ya contiene la guardia semanal,
    # pero NO de su antiguo parche de sync parcial. La 4.4.45 instala el puente
    # completo de citas vinculadas + staged en un solo lugar.
    subprocess.run([sys.executable, str(V4444_BUILDER)], cwd=ROOT, check=True)

    app_src = (V4444_OUT / "app.py").read_bytes()
    app_text = app_src.decode("utf-8-sig")
    require('APP_VERSION = "4.4.44"' in app_text, "La base candidata no es 4.4.44")
    require('/api/agenda/appointments/guarded' in app_text, "Se perdió la guardia semanal")
    require('_v4444_sync_cloud_staged_for_dates' not in app_text, "La base ya trae un sync parcial duplicado")

    app_text = app_text.replace('APP_VERSION = "4.4.44"', 'APP_VERSION = "4.4.45"', 1)
    app_text = app_text.replace("const VERSION='4.4.44';", "const VERSION='4.4.45';")
    app_text = app_text.replace('"const VERSION=\\\'4.4.44\\\';"', '"const VERSION=\\\'4.4.45\\\';"')
    anchor = "\n    FEATURE_BOOT_OK = True\n"
    require(app_text.count(anchor) == 1, "Ancla FEATURE_BOOT_OK ambigua")
    app_text = app_text.replace(anchor, FEATURE_BLOCK + anchor, 1)
    compile(app_text, "app.py", "exec")
    app_bytes = app_text.encode("utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app_bytes)

    # Actualización deliberadamente mínima: el launcher/base/static de 4.4.43 no
    # se reemplazan porque sus bytes ya son los estables correctos.
    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.4.42-dynamic-port-file-python-dependency-guard-1",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_45_attention_agenda_identity_fix/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.45: Nueva atención actualiza al abrir las citas de la semana desde Agenda Cloud/WhatsApp para que no falte ningún paciente. "
            "Al atender una cita sin vincular, si su celular ya corresponde a una ficha existente, la muestra primero para reutilizarla y completar sus datos sin crear duplicados. "
            "Incluye la protección semanal de citas de v4.4.44. No cambia tablas, .env, data, launcher ni bases locales y conserva el funcionamiento offline."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app_bytes), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))

    for marker in (
        'APP_VERSION = "4.4.45"',
        '/api/agenda/appointments/guarded',
        '_v4445_sync_cloud_agenda_for_dates',
        'core.mirror_patient_to_local(patient)',
        'core.mirror_appointment_to_local(appointment)',
        'window.__v4445StagedIdentityFix',
        'Encontramos una ficha con este celular',
        'usePatientForStaged',
        'v4445CreateDifferentStaged',
    ):
        require(marker in app_text, f"Falta contrato 4.4.45: {marker}")
    require("CREATE TABLE" not in FEATURE_BLOCK, "v4.4.45 no debe migrar tablas")
    print("BUILD_V4445_OK")
    print("APP_SHA", sha(app_bytes))


if __name__ == "__main__":
    build()
