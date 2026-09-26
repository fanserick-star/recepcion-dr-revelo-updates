from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "historia-clinica/updates/v1_3_67_cloud_optional_backfill"
DST = ROOT / "historia-clinica/updates/v1_3_68_empty_draft_fix"
CHANNEL = ROOT / "historia-clinica/launcher-v1/app-channel-source.json"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: se esperó 1 coincidencia y hubo {count}")
    return text.replace(old, new, 1)


if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)

app_path = DST / "app.py"
app = app_path.read_text(encoding="utf-8")

# 1) Los avisos de Inicio sólo representan borradores con contenido clínico real.
old = '''        pending_draft = conn.execute("""
            SELECT e.id AS encounter_id,e.patient_id,e.updated_at,p.name
            FROM encounters e
            JOIN patients p ON p.id=e.patient_id
            WHERE e.note_status='draft'
            ORDER BY e.updated_at DESC
            LIMIT 1
        """).fetchone()
        pending_draft_count = int(conn.execute(
            "SELECT COUNT(*) FROM encounters WHERE note_status='draft'"
        ).fetchone()[0])'''
new = '''        pending_draft = conn.execute("""
            SELECT e.id AS encounter_id,e.patient_id,e.updated_at,p.name
            FROM encounters e
            JOIN patients p ON p.id=e.patient_id
            WHERE e.note_status='draft'
              AND COALESCE(e.deleted_at,'')=''
              AND (
                TRIM(COALESCE(e.clinical_note,''))<>''
                OR TRIM(COALESCE(e.diagnosis,''))<>''
                OR TRIM(COALESCE(e.treatment,''))<>''
              )
            ORDER BY e.updated_at DESC
            LIMIT 1
        """).fetchone()
        pending_draft_count = int(conn.execute("""
            SELECT COUNT(*) FROM encounters
            WHERE note_status='draft'
              AND COALESCE(deleted_at,'')=''
              AND (
                TRIM(COALESCE(clinical_note,''))<>''
                OR TRIM(COALESCE(diagnosis,''))<>''
                OR TRIM(COALESCE(treatment,''))<>''
              )
        """).fetchone()[0])'''
app = replace_once(app, old, new, "home_pending_only_with_content")

# 2) La ficha no ofrece Continuar consulta por un draft vacío/descartado.
old = '''        active_edit = conn.execute("SELECT id,updated_at FROM encounters WHERE patient_id=? AND note_status='draft' ORDER BY updated_at DESC LIMIT 1", (patient_id,)).fetchone()'''
new = '''        active_edit = conn.execute("""
            SELECT id,updated_at FROM encounters
            WHERE patient_id=? AND note_status='draft'
              AND COALESCE(deleted_at,'')=''
              AND (
                TRIM(COALESCE(clinical_note,''))<>''
                OR TRIM(COALESCE(diagnosis,''))<>''
                OR TRIM(COALESCE(treatment,''))<>''
              )
            ORDER BY updated_at DESC LIMIT 1
        """, (patient_id,)).fetchone()'''
app = replace_once(app, old, new, "patient_active_edit_only_with_content")

# 3) Helper único para decidir si existe contenido clínico pendiente.
anchor = '''def _v1364_queue_best_effort(queue_id, patient_id, status, stamp):
    """La cola nunca debe impedir guardar o firmar la historia clínica."""'''
insert = '''def _v1368_has_clinical_content(note="", diagnosis="", treatment="") -> bool:
    """Una atención vacía no es una historia clínica pendiente."""
    return bool(
        str(note or "").strip()
        or str(diagnosis or "").strip()
        or str(treatment or "").strip()
    )


def _v1368_reset_queue_after_empty_save(queue_id, stamp):
    """Un guardado vacío no debe dejar artificialmente el turno 'En consulta'."""
    if not queue_id:
        return
    try:
        with db() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(waiting_queue)")}
            if "status" not in cols or "id" not in cols:
                return
            sets = ["status='waiting'"]
            params = []
            if "completed_at" in cols:
                sets.append("completed_at=NULL")
            if "updated_at" in cols:
                sets.append("updated_at=?")
                params.append(stamp)
            params.append(queue_id)
            conn.execute(
                f"UPDATE waiting_queue SET {','.join(sets)} "
                "WHERE id=? AND status='in_consultation'",
                params,
            )
            conn.commit()
    except Exception as exc:
        _v1364_log_save_error("empty_queue_reset", exc)


def _v1364_queue_best_effort(queue_id, patient_id, status, stamp):
    """La cola nunca debe impedir guardar o firmar la historia clínica."""'''
app = replace_once(app, anchor, insert, "central_clinical_content_helper")

# 4) Guardar vacío no crea una historia. Si ya existía un draft vacío, lo deja
# soft-deleted y retira el estado artificial 'En consulta'.
start = app.index('@app.post("/api/encounters/save")')
end = app.index('\n\n@app.post("/api/encounters/{encounter_id}/sign")', start)
new_save = r'''@app.post("/api/encounters/save")
async def save_encounter(request: Request):
    try:
        data = await request.json()
        patient_id = (data.get("patient_id") or "").strip()
        if not patient_id:
            raise HTTPException(400, "Falta el paciente.")
        enc_id = (data.get("encounter_id") or "").strip() or new_id()
        enc_date = data.get("encounter_date") or datetime.now().strftime("%Y-%m-%d")
        enc_time = data.get("encounter_time") or datetime.now().strftime("%H:%M")
        note = str(data.get("clinical_note") or "").upper()
        diagnosis = (str(data.get("diagnosis") or "").upper() if "diagnosis" in data else None)
        treatment = (str(data.get("treatment") or "").upper() if "treatment" in data else None)
        copied = data.get("copied_from_encounter_id") or None
        queue_id = data.get("queue_id") or None
        manual = bool(data.get("manual_snapshot"))
        stamp = now_iso()
        created = False
        empty_queue_id = queue_id
        empty_result = False

        # El núcleo clínico se guarda y confirma PRIMERO.
        with db() as conn:
            _v1364_ensure_encounter_schema(conn)
            if not conn.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
                raise HTTPException(404, "La ficha del paciente no existe en esta base local.")

            existing = conn.execute("SELECT * FROM encounters WHERE id=?", (enc_id,)).fetchone()
            if existing and existing["note_status"] != "draft":
                raise HTTPException(409, "La consulta ya está finalizada.")

            if diagnosis is None:
                diagnosis = (existing["diagnosis"] or "") if existing else ""
            if treatment is None:
                treatment = (existing["treatment"] or "") if existing else ""

            if not _v1368_has_clinical_content(note, diagnosis, treatment):
                # Nunca firmamos ni conservamos como pendiente una historia vacía.
                # Si venía de una versión anterior, la soft-delete mantiene trazabilidad
                # sin mostrarla como historia ni como consulta pendiente.
                if existing:
                    empty_queue_id = queue_id or existing["queue_id"]
                    conn.execute(
                        """UPDATE encounters
                           SET queue_id=NULL,deleted_at=?,updated_at=?
                           WHERE id=? AND note_status='draft'""",
                        (stamp, stamp, enc_id),
                    )
                    audit(
                        conn,
                        "discard_empty_draft",
                        "encounter",
                        enc_id,
                        {"patient_id": patient_id, "reason": "empty_save"},
                    )
                conn.commit()
                empty_result = True
            elif existing:
                conn.execute(
                    """UPDATE encounters
                       SET encounter_date=?,encounter_time=?,clinical_note=?,diagnosis=?,treatment=?,
                           copied_from_encounter_id=?,queue_id=COALESCE(?,queue_id),deleted_at=NULL,updated_at=?
                       WHERE id=?""",
                    (enc_date, enc_time, note, diagnosis, treatment, copied, queue_id, stamp, enc_id),
                )
                conn.commit()
            else:
                created = True
                digest = hashlib.sha256((enc_id + stamp).encode()).hexdigest()
                conn.execute(
                    """INSERT INTO encounters(
                        id,patient_id,encounter_date,encounter_time,clinical_note,diagnosis,treatment,
                        source,source_record_hash,is_legacy_locked,created_at,updated_at,deleted_at,
                        note_status,signed_at,signed_by,copied_from_encounter_id,queue_id,created_by
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        enc_id, patient_id, enc_date, enc_time, note, diagnosis, treatment,
                        "historia_clinica", digest, 0, stamp, stamp, None,
                        "draft", None, None, copied, queue_id, DOCTOR_NAME,
                    ),
                )
                conn.commit()

        if empty_result:
            _v1368_reset_queue_after_empty_save(empty_queue_id, stamp)
            SYNC_SERVICE.mark_activity()
            SYNC_SERVICE.wake()
            return JSONResponse({"ok": True, "encounter_id": None, "empty": True})

        # Acciones secundarias: importantes, pero nunca ponen en riesgo el texto.
        if created:
            _v1364_audit_best_effort(
                "start_encounter", "encounter", enc_id, {"patient_id": patient_id}
            )
        if manual:
            _v1364_save_revision_best_effort(
                enc_id, stamp, note, diagnosis or "", treatment or "", "guardado_manual"
            )
        _v1364_queue_best_effort(queue_id, patient_id, "in_consultation", stamp)

        return JSONResponse({"ok": True, "encounter_id": enc_id, "empty": False})
    except HTTPException:
        raise
    except Exception as exc:
        _v1364_log_save_error("save_core", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
            },
        )


@app.post("/api/encounters/empty/complete")
async def complete_empty_attention(request: Request):
    """Cierra una atención sin crear una historia clínica vacía."""
    data = await request.json()
    patient_id = str(data.get("patient_id") or "").strip()
    queue_id = str(data.get("queue_id") or "").strip() or None
    encounter_id = str(data.get("encounter_id") or "").strip() or None
    if not patient_id:
        raise HTTPException(400, "Falta el paciente.")

    stamp = now_iso()
    discarded = []
    with db() as conn:
        _v1364_ensure_encounter_schema(conn)
        if not conn.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone():
            raise HTTPException(404, "La ficha del paciente no existe en esta base local.")

        if encounter_id:
            rows = conn.execute(
                "SELECT * FROM encounters WHERE id=? AND patient_id=? LIMIT 1",
                (encounter_id, patient_id),
            ).fetchall()
        elif queue_id:
            rows = conn.execute(
                """SELECT * FROM encounters
                   WHERE patient_id=? AND queue_id=? AND note_status='draft'
                     AND COALESCE(deleted_at,'')=''""",
                (patient_id, queue_id),
            ).fetchall()
        else:
            rows = []

        for row in rows:
            if row["note_status"] != "draft":
                raise HTTPException(409, "La consulta ya está finalizada.")
            if _v1368_has_clinical_content(
                row["clinical_note"], row["diagnosis"], row["treatment"]
            ):
                raise HTTPException(
                    409,
                    "La consulta contiene información clínica y debe finalizarse normalmente.",
                )
            conn.execute(
                """UPDATE encounters
                   SET queue_id=NULL,deleted_at=?,updated_at=?
                   WHERE id=? AND note_status='draft'""",
                (stamp, stamp, row["id"]),
            )
            discarded.append(str(row["id"]))

        audit(
            conn,
            "complete_empty_attention",
            "waiting_queue" if queue_id else "patient",
            queue_id or patient_id,
            {"patient_id": patient_id, "discarded_empty_drafts": discarded},
        )
        conn.commit()

    if queue_id:
        _v1364_queue_best_effort(queue_id, patient_id, "completed", stamp)
    SYNC_SERVICE.mark_activity()
    SYNC_SERVICE.wake()
    return JSONResponse({"ok": True, "empty": True, "discarded": len(discarded)})
'''
app = app[:start] + new_save + app[end:]

# 5) El navegador entiende la respuesta vacía y no conserva encounterId falso.
old = '''    const j=await r.json();
    encounterId=j.encounter_id;
    dirty=false;
    state.textContent='Guardado '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    state.className='save-state saved';
    return encounterId;'''
new = '''    const j=await r.json();
    if(j.empty){
      encounterId=null;
      dirty=false;
      state.textContent='Sin contenido clínico que guardar';
      state.className='save-state saved';
      return null;
    }
    encounterId=j.encounter_id;
    dirty=false;
    state.textContent='Guardado '+new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    state.className='save-state saved';
    return encounterId;'''
app = replace_once(app, old, new, "js_save_empty_response")

# 6) Finalizar vacío cierra la atención sin crear/firmar una historia vacía.
start = app.index('async function finalizeAndHome(button){')
end = app.index('\nsignBtn.addEventListener', start)
new_finalize = r'''async function finalizeAndHome(button){
  const original=button?.textContent||'Finalizar consulta';
  if(button){button.disabled=true;button.textContent='Finalizando…'}
  signBtn.disabled=true;
  try{
    upperClinical(noteEl);
    const blank=!String(noteEl.value||'').trim();
    if(blank){
      const r=await fetch('/api/encounters/empty/complete',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          encounter_id:encounterId,
          patient_id:PATIENT_ID,
          queue_id:QUEUE_ID
        })
      });
      if(!r.ok){
        let msg='No se pudo cerrar la atención vacía.';
        try{const j=await r.json();if(j.detail)msg+=' '+j.detail}catch(_e){}
        throw new Error(msg);
      }
      encounterId=null;
      dirty=false;
      leavingAfterFinalize=true;
      location.href='/';
      return;
    }

    dirty=true;
    const id=await save(true);
    if(!id)throw new Error('No se pudo guardar la consulta.');
    const r=await fetch('/api/encounters/'+encodeURIComponent(id)+'/sign',{method:'POST'});
    if(!r.ok){
      let msg='No se pudo finalizar la consulta.';
      try{const j=await r.json();if(j.detail)msg+=' '+j.detail}catch(_e){}
      throw new Error(msg);
    }
    dirty=false;
    leavingAfterFinalize=true;
    location.href='/';
  }catch(err){
    if(button){button.disabled=false;button.textContent=original}
    signBtn.disabled=false;
    finalizeModal.hidden=true;
    leaveModal.hidden=true;
    showAppToast(err && err.message ? err.message : 'No se pudo finalizar la consulta.','error');
  }
}
'''
app = app[:start] + new_finalize + app[end:]

old = '''signBtn.addEventListener('click',()=>{
  if(!String(noteEl.value||'').trim()){
    showAppToast('Escriba la consulta antes de finalizarla.','warning');
    noteEl.focus();
    return;
  }
  finalizeModal.hidden=false;
});'''
new = '''signBtn.addEventListener('click',()=>{
  const blank=!String(noteEl.value||'').trim();
  const title=finalizeModal.querySelector('h3');
  const text=finalizeModal.querySelector('p');
  if(blank){
    if(title)title.textContent='¿Finalizar esta atención sin historia?';
    if(text)text.textContent='No se creará una historia clínica vacía. La atención se cerrará y dejará de aparecer como pendiente.';
  }else{
    if(title)title.textContent='¿Finalizar esta consulta?';
    if(text)text.innerHTML='La consulta quedará cerrada. Si después necesita agregar algo, podrá usar <b>Seguir editando historia</b> sin alterar el registro original.';
  }
  finalizeModal.hidden=false;
});'''
app = replace_once(app, old, new, "js_allow_empty_finalize")

old = '''finishAndHome.addEventListener('click',()=>{
  if(!String(noteEl.value||'').trim()){
    // Si no hay contenido clínico, no hay nada que finalizar ni proteger.
    // Permitimos volver al Inicio inmediatamente.
    dirty=false;
    leavingAfterFinalize=true;
    leaveModal.hidden=true;
    location.href='/';
    return;
  }
  finalizeAndHome(finishAndHome);
});'''
new = '''finishAndHome.addEventListener('click',()=>{
  finalizeAndHome(finishAndHome);
});'''
app = replace_once(app, old, new, "js_empty_leave_must_close_queue")

# 7) Marcador de salud para que CI pueda verificar el fix.
old = '''        "consultation_only_turn_numbers": True,
    })'''
new = '''        "consultation_only_turn_numbers": True,
        "empty_draft_pending_fix": True,
        "empty_attention_closes_without_signed_history": True,
    })'''
app = replace_once(app, old, new, "health_flags")

app_path.write_text(app, encoding="utf-8")

# Versión y manifiesto.
(DST / "historia-version.json").write_text(
    json.dumps({"version": "1.3.68"}, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
manifest_path = DST / "update_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = manifest["app_version"] = manifest["runtime_version"] = "1.3.68"
notes = manifest.setdefault("notes", {})
notes.update({
    "purpose": "Corregir consultas vacías que quedaban como pendientes sin debilitar el autosave.",
    "previous_version": "1.3.67",
    "functional_changes": True,
    "database_schema_changes": False,
    "patient_data_destructive_changes": False,
    "signed_history_protected": True,
    "empty_save_creates_no_history": True,
    "empty_draft_hidden_from_pending": True,
    "empty_finalize_completes_queue": True,
    "empty_finalize_creates_no_signed_history": True,
    "nonempty_draft_recovery_preserved": True,
    "emergency_local_draft_backup_preserved": True,
})
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Canal fuente candidato. El publicador de main generará SHA/URLs finales.
channel = json.loads(CHANNEL.read_text(encoding="utf-8"))
channel["appVersion"] = "1.3.68"
channel["notes"] = (
    "Historia Clínica 1.3.68: corrige el caso de atención con historia completamente vacía. "
    "Guardar vacío no crea un borrador; Finalizar vacío cierra la atención sin crear una historia firmada; "
    "los borradores con contenido siguen protegidos por autosave, SQLite, respaldo local y Neon."
)
for item in channel["files"]:
    item["sourcePath"] = item["sourcePath"].replace(
        "v1_3_67_cloud_optional_backfill", "v1_3_68_empty_draft_fix"
    )
CHANNEL.write_text(json.dumps(channel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Barreras estáticas mínimas.
compile(app, str(app_path), "exec")
assert '"empty_draft_pending_fix": True' in app
assert '/api/encounters/empty/complete' in app
assert "La atención se cerrará y dejará de aparecer como pendiente" in app
assert "TRIM(COALESCE(e.clinical_note,''))<>''" in app
print("Historia 1.3.68 generada correctamente")
