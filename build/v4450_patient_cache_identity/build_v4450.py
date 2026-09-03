from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_49_agenda_flow_speed"
OUT = ROOT / "updates" / "v4_4_50_patient_cache_identity"
VERSION = "4.4.50"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.50 — cache de pacientes coherente + histórico staged sin duplicar.
    # -----------------------------------------------------------------------
    # El buscador habitual es SQLite local-first. Si un borrado en Neon se
    # reflejaba mal en SQLite, la función antigua tragaba la excepción y podían
    # quedar fichas fantasma. Blindamos create/update/delete del espejo local y
    # reparamos en segundo plano borrados recientes confirmados por Neon.
    _v4450_stable_mirror_patient = core.mirror_patient_to_local
    _v4450_stable_mirror_delete_patient = core.mirror_delete_patient_local

    def _v4450_mirror_patient_to_local(patient) -> bool:
        try:
            _v4450_stable_mirror_patient(patient)
        except Exception:
            pass
        try:
            with core.LocalSessionLocal() as ldb:
                lp = ldb.get(core.Patient, int(patient.id))
                values = dict(
                    cedula=patient.cedula,
                    nombre=patient.nombre,
                    fecha_nacimiento=patient.fecha_nacimiento,
                    celular=patient.celular,
                    correo=patient.correo,
                    lugar=patient.lugar,
                    notas=patient.notas,
                    created_at=patient.created_at,
                )
                if lp is None:
                    ldb.add(core.Patient(id=int(patient.id), **values))
                else:
                    for key, value in values.items():
                        setattr(lp, key, value)
                ldb.commit()
            return True
        except Exception as exc:
            try:
                with core._state_lock:
                    core._state["last_error"] = f"No se pudo reflejar paciente {getattr(patient, 'id', '?')} en SQLite: {exc}"[:300]
            except Exception:
                pass
            return False

    def _v4450_force_delete_patient_local(pid: int) -> bool:
        patient_id = int(pid)
        try:
            _v4450_stable_mirror_delete_patient(patient_id)
        except Exception:
            pass
        try:
            with core.LocalSessionLocal() as ldb:
                if ldb.get(core.Patient, patient_id) is None:
                    return True
                visit_ids = [int(x) for x in ldb.scalars(
                    core.select(core.Visit.id).where(core.Visit.patient_id == patient_id)
                )]
                if visit_ids:
                    ldb.execute(core.delete(core.BillingRecord).where(core.BillingRecord.visit_id.in_(visit_ids)))
                if hasattr(core, "BillingPreference"):
                    ldb.execute(core.delete(core.BillingPreference).where(core.BillingPreference.patient_id == patient_id))
                ldb.execute(core.delete(core.Appointment).where(core.Appointment.patient_id == patient_id))
                ldb.execute(core.delete(core.Visit).where(core.Visit.patient_id == patient_id))
                ldb.execute(core.delete(core.Patient).where(core.Patient.id == patient_id))
                ldb.commit()
            with core.LocalSessionLocal() as verify:
                return verify.get(core.Patient, patient_id) is None
        except Exception as exc:
            try:
                with core._state_lock:
                    core._state["last_error"] = f"No se pudo purgar paciente {patient_id} de SQLite: {exc}"[:300]
            except Exception:
                pass
            return False

    core.mirror_patient_to_local = _v4450_mirror_patient_to_local
    core.mirror_delete_patient_local = _v4450_force_delete_patient_local

    _v4450_reconcile_lock = core.threading.Lock()

    def _v4450_reconcile_recent_deleted_patients() -> dict:
        if not _v4450_reconcile_lock.acquire(blocking=False):
            return {"ok": True, "busy": True, "purged": 0}
        try:
            if core.queue_count() > 0:
                return {"ok": True, "skipped": "offline_queue", "purged": 0}
            if not core.cloud_configured() or not core.CloudSessionLocal or not core.check_cloud(force=False):
                return {"ok": True, "skipped": "cloud_unavailable", "purged": 0}
            ids = set()
            with core.LocalSessionLocal() as ldb:
                rows = list(ldb.scalars(
                    core.select(core.Audit)
                    .where(core.Audit.action.in_(("borrar_paciente", "borrar_paciente_importado_confirmafy")))
                    .order_by(core.Audit.id.desc())
                    .limit(180)
                ))
                for row in rows:
                    match = core.re.search(r"Paciente\s+(\d+)", str(row.detail or ""), flags=core.re.I)
                    if match:
                        ids.add(int(match.group(1)))
            if not ids:
                return {"ok": True, "purged": 0}
            with core.CloudSessionLocal() as cdb:
                alive = {int(x) for x in cdb.scalars(
                    core.select(core.Patient.id).where(core.Patient.id.in_(sorted(ids)))
                )}
            purged = 0
            for pid in sorted(ids - alive):
                purged += int(_v4450_force_delete_patient_local(pid))
            return {"ok": True, "purged": purged, "checked": len(ids)}
        except Exception as exc:
            return {"ok": False, "purged": 0, "error": str(exc)[:220]}
        finally:
            _v4450_reconcile_lock.release()

    @app.post("/api/local-cache/reconcile-patients")
    def v4450_reconcile_patients(user=core.Depends(core.current_user)):
        return _v4450_reconcile_recent_deleted_patients()

    def _v4450_repair_worker():
        try:
            core.time.sleep(1.5)
            _v4450_reconcile_recent_deleted_patients()
        except Exception:
            pass

    core.threading.Thread(target=_v4450_repair_worker, daemon=True, name="rp-patient-cache-repair").start()

    # Al activar un histórico DESDE una cita staged, el celular actual de la
    # cita es la identidad operativa más fuerte. Si ya pertenece a una ficha,
    # se reutiliza y el histórico se vincula a ella. Si no, se activa una sola
    # ficha y se le guarda ese celular para que un segundo histórico no cree
    # otro paciente con el mismo número.
    @app.post("/api/historical/{hid}/activate-for-staged/{item_id}")
    def v4450_activate_historical_for_staged(
        hid: int,
        item_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        staged = db.get(core.ConfirmafyAgendaItem, int(item_id))
        if staged is None:
            raise core.HTTPException(404, "La cita ya no está disponible")
        staged_phone = core.normalize_lookup_phone(staged.celular)
        source_key = None
        try:
            with core.LocalSessionLocal() as ldb:
                historical = ldb.get(core.HistoricalPatient, int(hid))
                if historical is not None:
                    source_key = str(historical.source_key)
        except Exception:
            source_key = None

        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, 0, db, user)
            if owner_info.get("duplicate") and owner_info.get("patient"):
                owner_id = int(owner_info["patient"]["id"])
                owner = db.get(core.Patient, owner_id)
                if owner is not None:
                    if source_key:
                        try:
                            core._historical_link_patient(source_key, owner_id)
                        except Exception:
                            pass
                    _v4450_mirror_patient_to_local(owner)
                    out = core.p_dict(owner)
                    out.update({"created": False, "reused_by_staged_phone": True})
                    return out

        result = core.activate_historical_patient(int(hid), db, user)
        patient_id = int(result.get("id") or 0)
        patient = db.get(core.Patient, patient_id) if patient_id else None
        if patient is None:
            return result

        if staged_phone:
            owner_info = v4446_phone_owner(staged_phone, int(patient.id), db, user)
            if owner_info.get("duplicate") and owner_info.get("patient"):
                target_id = int(owner_info["patient"]["id"])
                if target_id != int(patient.id):
                    linked = core.link_duplicate_patient(int(patient.id), target_id, db, user)
                    out = dict(linked.get("patient") or {})
                    out.update({"created": False, "reused_by_staged_phone": True})
                    return out
            if core.normalize_lookup_phone(patient.celular) != staged_phone:
                patient.celular = staged_phone
                core.audit(db, user, "vincular_celular_cita_historico", f"Paciente {patient.id} · cita staged {item_id}")
                db.commit()
                _v4450_mirror_patient_to_local(patient)
        out = core.p_dict(patient)
        out.update({
            "created": bool(result.get("created")),
            "historical": result.get("historical"),
            "staged_phone_linked": bool(staged_phone),
        })
        return out

    V4450_PATIENT_CACHE_JS = r"""
;(()=>{
  if(window.__v4450PatientCacheIdentity)return;
  window.__v4450PatientCacheIdentity=true;

  const currentRows=rows=>(Array.isArray(rows)?rows:[]).filter(p=>!(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)));

  // El buscador normal muestra fichas ACTUALES. El histórico sigue disponible
  // en su filtro dedicado y en el flujo explícito de subsecuente de una cita.
  const stableRenderPatientResults=renderPatientResults;
  renderPatientResults=function(rows=[],title=''){
    const keepHistorical=String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='historical' || String(typeof activePatientFilter==='undefined'?'':activePatientFilter||'')==='review';
    return stableRenderPatientResults.call(this,keepHistorical?rows:currentRows(rows),title);
  };

  const stableGlobalResult=globalSearchResultHtml;
  globalSearchResultHtml=function(p){
    if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p))return '';
    return stableGlobalResult.call(this,p);
  };

  function clearPatientCaches(id=0){
    try{globalSearchCache=[]}catch(_e){}
    try{if(Number(id||0)>0)agendaPatientById.delete(Number(id));else agendaPatientById.clear()}catch(_e){}
    try{if(Number(id||0)>0&&Number(agendaPatientCache?.id||0)===Number(id))agendaPatientCache=null}catch(_e){}
  }
  window.__v4450ClearPatientCaches=clearPatientCaches;

  async function reconcileLocalPatients(){
    try{return await api('/api/local-cache/reconcile-patients',{method:'POST'})}catch(_e){return null}
  }

  // Borrar pasa por Papelera recuperable y luego limpia caches/UI. Así una ficha
  // buena no se pierde de forma irreversible por un clic de limpieza.
  deletePatient=async function(id,visitCount){
    const extra=visitCount?` También se moverán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'} a la Papelera.`:'';
    if(!confirmDeletion(`¿Mover este paciente a la Papelera?${extra}\n\nPodrás restaurarlo durante 7 días.`))return;
    try{
      await singleFlightMutation(`patient:safe-delete:${id}`,async()=>{
        const result=await api('/api/safety/patients/'+Number(id),{method:'DELETE'});
        clearPatientCaches(Number(id));
        await reconcileLocalPatients();
        closeModal();show('pacientes');
        try{await searchPatients()}catch(_e){}
        try{await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()])}catch(_e){}
        const msg=result?.trash_id?'Paciente movido a Papelera. Puedes restaurarlo desde Actividad → Papelera.':'Paciente eliminado.';
        if(typeof rpNotice==='function')rpNotice(msg);
      },'Moviendo…');
    }catch(e){alert(e.message||e)}
  };

  // Histórico elegido desde WhatsApp/staged: operación atómica en backend con
  // el celular de la cita, para que dos históricos no creen dos pacientes.
  useHistoricalForStaged=async function(itemId,hid,fecha){
    try{
      const p=await api(`/api/historical/${Number(hid)}/activate-for-staged/${Number(itemId)}`,{method:'POST'});
      clearPatientCaches(Number(p?.id||0));
      try{invalidateAttentionWeekCache()}catch(_e){}
      await usePatientForStaged(Number(itemId),Number(p.id),fecha);
    }catch(e){alert(e.message||e)}
  };

  // Después de cualquier edición desde atención, limpiar caches para que el
  // nombre recién completado aparezca inmediatamente en ambos buscadores.
  const stableSaveExistingAndAttend=window.v4449SaveExistingAndAttend;
  if(typeof stableSaveExistingAndAttend==='function')window.v4449SaveExistingAndAttend=async function(patientId,fecha){
    const out=await stableSaveExistingAndAttend.apply(this,arguments);
    clearPatientCaches(Number(patientId||0));
    return out;
  };
  const stableSavePatient=savePatient;
  savePatient=async function(id,source){
    const out=await stableSavePatient.apply(this,arguments);
    clearPatientCaches(Number(id||0));
    return out;
  };
  const stableSaveAndReturn=savePatientAndReturnToAttention;
  savePatientAndReturnToAttention=async function(id){
    const out=await stableSaveAndReturn.apply(this,arguments);
    clearPatientCaches(Number(id||0));
    return out;
  };

  // Reparación no bloqueante para instalaciones que ya traían fantasmas de
  // versiones anteriores. Luego vuelve a consultar solo si hay una búsqueda visible.
  setTimeout(async()=>{
    const r=await reconcileLocalPatients();
    if(!r?.purged)return;
    clearPatientCaches();
    try{const g=document.querySelector('#globalSearch');if(g&&String(g.value||'').trim().length>=2)globalSearchPatients(true)}catch(_e){}
    try{const p=document.querySelector('#search');if(p&&String(p.value||'').trim().length>=2)searchPatients()}catch(_e){}
  },1800);

  window.__v4450PatientTest={currentRows,reconcileLocalPatients,clearPatientCaches};
})();
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4450_PATIENT_CACHE_JS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.49"' in app_text, "La base app no es 4.4.49")
    require("FEATURE_BOOT_OK = True" in app_text, "No se encontró punto de inserción seguro")
    app_text = app_text.replace('APP_VERSION = "4.4.49"', 'APP_VERSION = "4.4.50"', 1)
    app_text = app_text.replace("const VERSION='4.4.49';", "const VERSION='4.4.50';")
    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
    # Normalizar LF para que Windows checkout y Raw GitHub tengan el mismo SHA.
    app_base = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").encode("utf-8")
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
    compile(app_base.decode("utf-8"), "app_base_4428.py", "exec")
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

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_50_patient_cache_identity/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.50: elimina fichas fantasma del cache local tras borrados confirmados en Neon; "
            "el buscador normal muestra solo pacientes actuales; históricos siguen en su filtro; "
            "al usar un histórico desde WhatsApp se reutiliza el celular/ficha actual para evitar duplicados; "
            "y Borrar paciente pasa por Papelera recuperable. Conserva todos los arreglos 4.4.49."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4450_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()
