from pathlib import Path
import json
import re
import shutil
import py_compile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "historia-clinica/updates/v1_3_69_professional_ui"
DST = ROOT / "historia-clinica/updates/v1_3_70_linked_documents"


def rep(text, old, new, count=1, label="replacement"):
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} occurrence(s), found {found}")
    return text.replace(old, new, count)


def sub(text, pattern, replacement, count=1, label="regex", flags=0):
    out, n = re.subn(pattern, lambda m: replacement, text, count=count, flags=flags)
    if n != count:
        raise RuntimeError(f"{label}: expected {count} match(es), found {n}")
    return out


if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)

app_path = DST / "app.py"
docs_path = DST / "documentos_clinicos.py"
css_path = DST / "static/style.css"
app = app_path.read_text(encoding="utf-8")
docs = docs_path.read_text(encoding="utf-8")

# ------------------------------------------------------------------
# APP: documentos visibles dentro de cada consulta del historial.
# ------------------------------------------------------------------
helper = r'''
def _v1370_encounter_has_documents(conn, encounter_id: str) -> bool:
    """Una consulta también tiene actividad clínica cuando emitió documentos."""
    encounter_id = str(encounter_id or "").strip()
    if not encounter_id:
        return False
    try:
        row = conn.execute(
            """SELECT 1
               FROM prescriptions
               WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
               UNION ALL
               SELECT 1
               FROM certificates
               WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
               LIMIT 1""",
            (encounter_id, encounter_id),
        ).fetchone()
        return bool(row)
    except sqlite3.OperationalError:
        return False


def _v1370_encounter_documents(encounter_id: str) -> list[dict]:
    encounter_id = str(encounter_id or "").strip()
    if not encounter_id:
        return []
    try:
        with db() as conn:
            rows = conn.execute(
                """SELECT 'rx' AS kind,id,issued_at,COALESCE(series_no,'') AS ref,
                          COALESCE(diagnosis,'') AS diagnosis,'' AS certificate_type
                   FROM prescriptions
                   WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
                   UNION ALL
                   SELECT 'cert' AS kind,id,issued_at,COALESCE(certificate_no,'') AS ref,
                          COALESCE(diagnosis,'') AS diagnosis,COALESCE(certificate_type,'medical') AS certificate_type
                   FROM certificates
                   WHERE encounter_id=? AND COALESCE(deleted_at,'')=''
                   ORDER BY issued_at DESC""",
                (encounter_id, encounter_id),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _v1370_render_encounter_documents(encounter_id: str, compact: bool = False) -> str:
    docs = _v1370_encounter_documents(encounter_id)
    if not docs:
        return ""
    rows = []
    for item in docs:
        kind = str(item.get("kind") or "")
        doc_id = str(item.get("id") or "")
        issued = str(item.get("issued_at") or "")
        date_label = human_dt(issued) if issued else ""
        diagnosis = str(item.get("diagnosis") or "").strip()
        if kind == "rx":
            label = "Receta médica"
            ref = str(item.get("ref") or "").strip()
            detail = ("Serie " + ref) if ref else diagnosis
            url = f"/recetas/{e(doc_id)}/vista"
        else:
            cert_type = str(item.get("certificate_type") or "medical")
            label = "Certificado de reposo" if cert_type == "rest_isolation" else "Certificado médico"
            detail = diagnosis
            url = (
                f"/certificados/reposo/{e(doc_id)}/vista"
                if cert_type == "rest_isolation"
                else f"/certificados/{e(doc_id)}/vista"
            )
        meta = " · ".join(x for x in (date_label, detail) if x)
        rows.append(
            "<div class='encounter-document-row'>"
            f"<span class='encounter-document-icon'>{'RX' if kind == 'rx' else 'DOC'}</span>"
            f"<span class='encounter-document-copy'><b>{e(label)}</b><small>{e(meta)}</small></span>"
            f"<a href='{url}' target='_blank'>Ver</a>"
            f"<a href='{url}{'&' if '?' in url else '?'}print_now=1' target='_blank'>Imprimir</a>"
            "</div>"
        )
    cls = " encounter-documents-compact" if compact else ""
    return (
        f"<section class='encounter-documents{cls}'>"
        "<div class='encounter-documents-title'><span>DOCUMENTOS DE ESTA CONSULTA</span>"
        f"<strong>{len(rows)}</strong></div>"
        + "".join(rows)
        + "</section>"
    )


'''
app = rep(
    app,
    "def render_history_card(h, addenda, open_by_default=False):\n",
    helper + "def render_history_card(h, addenda, open_by_default=False):\n",
    label="insert document history helpers",
)
app = rep(
    app,
    "    actions = f\"<a class='text-btn' href='/encuentro/{e(h['id'])}/imprimir?print_now=1' target='_blank'>Imprimir</a>\"\n",
    "    documents_html = _v1370_render_encounter_documents(h[\"id\"])\n"
    "    actions = f\"<a class='text-btn' href='/encuentro/{e(h['id'])}/imprimir?print_now=1' target='_blank'>Imprimir</a>\"\n",
    label="history documents variable",
)
app = rep(
    app,
    "    {add_html}\n  </div>\n</article>\n",
    "    {documents_html}\n    {add_html}\n  </div>\n</article>\n",
    label="history documents block",
)
app = rep(
    app,
    "                record_body += _continuation_html\n\n            date_label = human_date(h[\"encounter_date\"])",
    "                record_body += _continuation_html\n\n            record_body += _v1370_render_encounter_documents(h[\"id\"], compact=True)\n\n            date_label = human_date(h[\"encounter_date\"])",
    label="compact previous documents",
)

# Pending/active draft must include document-only consultations.
alias_condition = """              AND (\n                TRIM(COALESCE(e.clinical_note,''))<>''\n                OR TRIM(COALESCE(e.diagnosis,''))<>''\n                OR TRIM(COALESCE(e.treatment,''))<>''\n              )"""
alias_replacement = """              AND (\n                TRIM(COALESCE(e.clinical_note,''))<>''\n                OR TRIM(COALESCE(e.diagnosis,''))<>''\n                OR TRIM(COALESCE(e.treatment,''))<>''\n                OR EXISTS (SELECT 1 FROM prescriptions r WHERE r.encounter_id=e.id AND COALESCE(r.deleted_at,'')='')\n                OR EXISTS (SELECT 1 FROM certificates c WHERE c.encounter_id=e.id AND COALESCE(c.deleted_at,'')='')\n              )"""
app = rep(app, alias_condition, alias_replacement, label="home pending document-aware")
plain_condition = """              AND (\n                TRIM(COALESCE(clinical_note,''))<>''\n                OR TRIM(COALESCE(diagnosis,''))<>''\n                OR TRIM(COALESCE(treatment,''))<>''\n              )"""
plain_replacement = """              AND (\n                TRIM(COALESCE(clinical_note,''))<>''\n                OR TRIM(COALESCE(diagnosis,''))<>''\n                OR TRIM(COALESCE(treatment,''))<>''\n                OR EXISTS (SELECT 1 FROM prescriptions r WHERE r.encounter_id=encounters.id AND COALESCE(r.deleted_at,'')='')\n                OR EXISTS (SELECT 1 FROM certificates c WHERE c.encounter_id=encounters.id AND COALESCE(c.deleted_at,'')='')\n              )"""
found_plain = app.count(plain_condition)
if found_plain != 2:
    raise RuntimeError(f"plain draft conditions: expected 2, found {found_plain}")
app = app.replace(plain_condition, plain_replacement)

# Existing document-only draft must not be discarded by an empty text save.
app = rep(
    app,
    "            if not _v1368_has_clinical_content(note, diagnosis, treatment):\n",
    "            if (\n                not _v1368_has_clinical_content(note, diagnosis, treatment)\n                and not (existing and _v1370_encounter_has_documents(conn, enc_id))\n            ):\n",
    label="preserve document-only draft",
)

# Empty-complete: sign document-only encounters instead of discarding them.
app = rep(
    app,
    "    discarded = []\n    with db() as conn:\n",
    "    discarded = []\n    signed_document_only = []\n    with db() as conn:\n",
    label="empty complete counters",
)
old_empty_loop = '''            if _v1368_has_clinical_content(\n                row["clinical_note"], row["diagnosis"], row["treatment"]\n            ):\n                raise HTTPException(\n                    409,\n                    "La consulta contiene información clínica y debe finalizarse normalmente.",\n                )\n            conn.execute(\n                """UPDATE encounters\n                   SET queue_id=NULL,deleted_at=?,updated_at=?\n                   WHERE id=? AND note_status='draft'""",\n                (stamp, stamp, row["id"]),\n            )\n            discarded.append(str(row["id"]))\n'''
new_empty_loop = '''            if _v1368_has_clinical_content(\n                row["clinical_note"], row["diagnosis"], row["treatment"]\n            ):\n                raise HTTPException(\n                    409,\n                    "La consulta contiene información clínica y debe finalizarse normalmente.",\n                )\n            if _v1370_encounter_has_documents(conn, row["id"]):\n                conn.execute(\n                    """UPDATE encounters\n                       SET note_status='signed',signed_at=?,signed_by=?,deleted_at=NULL,updated_at=?\n                       WHERE id=? AND note_status='draft'""",\n                    (stamp, DOCTOR_NAME, stamp, row["id"]),\n                )\n                signed_document_only.append(str(row["id"]))\n            else:\n                conn.execute(\n                    """UPDATE encounters\n                       SET queue_id=NULL,deleted_at=?,updated_at=?\n                       WHERE id=? AND note_status='draft'""",\n                    (stamp, stamp, row["id"]),\n                )\n                discarded.append(str(row["id"]))\n'''
app = rep(app, old_empty_loop, new_empty_loop, label="empty complete document-only sign")
app = rep(
    app,
    '{"patient_id": patient_id, "discarded_empty_drafts": discarded},\n',
    '{"patient_id": patient_id, "discarded_empty_drafts": discarded, "signed_document_only": signed_document_only},\n',
    label="empty complete audit",
)
app = rep(
    app,
    '    return JSONResponse({"ok": True, "empty": True, "discarded": len(discarded)})\n',
    '    return JSONResponse({"ok": True, "empty": not bool(signed_document_only), "discarded": len(discarded), "signed_document_only": len(signed_document_only)})\n',
    label="empty complete response",
)

# Signing a no-text consultation is valid if it contains a linked document.
old_sign_empty = '''            if (\n                not (h["clinical_note"] or "").strip()\n                and not (h["diagnosis"] or "").strip()\n                and not (h["treatment"] or "").strip()\n            ):\n                raise HTTPException(400, "La consulta está vacía.")\n'''
new_sign_empty = '''            if (\n                not (h["clinical_note"] or "").strip()\n                and not (h["diagnosis"] or "").strip()\n                and not (h["treatment"] or "").strip()\n                and not _v1370_encounter_has_documents(conn, encounter_id)\n            ):\n                raise HTTPException(400, "La consulta está vacía.")\n'''
app = rep(app, old_sign_empty, new_sign_empty, label="sign document-only encounter")

# Editor knows when its draft already has documents.
app = rep(
    app,
    '        macros = conn.execute("SELECT * FROM macros ORDER BY label COLLATE NOCASE").fetchall()\n',
    '        macros = conn.execute("SELECT * FROM macros ORDER BY label COLLATE NOCASE").fetchall()\n'
    '        working_has_documents = bool(working and _v1370_encounter_has_documents(conn, working["id"]))\n',
    label="working document state",
)
app = rep(
    app,
    'let encounterId=__WORKING_ID__ || null, timer=null, dirty=false, leavingAfterFinalize=false;\n',
    'let encounterId=__WORKING_ID__ || null, timer=null, dirty=false, leavingAfterFinalize=false, documentActivity=__HAS_DOCUMENTS__;\n',
    label="editor document state js",
)
app = rep(
    app,
    'let lastFocused=noteEl;\n',
    '''let lastFocused=noteEl;\nwindow.addEventListener('message',ev=>{\n  if(ev.origin!==location.origin)return;\n  const data=ev.data||{};\n  if(data.type!=='clinical-document-saved')return;\n  if(data.encounter_id)encounterId=String(data.encounter_id);\n  documentActivity=true;\n  state.textContent='Documento guardado en esta consulta';\n  state.className='save-state saved';\n});\n''',
    label="editor document postMessage",
)
app = rep(
    app,
    'async function save(manual=false){\n  if(!dirty && encounterId){\n',
    '''async function save(manual=false){\n  if(documentActivity && encounterId && !String(noteEl.value||'').trim()){\n    dirty=false;\n    if(manual){state.textContent='Documento guardado · sin texto adicional';state.className='save-state saved'}\n    return encounterId;\n  }\n  if(!dirty && encounterId){\n''',
    label="document-only save guard",
)
app = rep(
    app,
    '  return Boolean(String(noteEl.value||\'\').trim() || dirty);\n',
    '  return Boolean(String(noteEl.value||\'\').trim() || dirty || documentActivity);\n',
    label="has open consultation documents",
)

finalize_pattern = r"async function finalizeAndHome\(button\)\{.*?\n\}\n\nsignBtn\.addEventListener\('click',\(\)=>\{"
finalize_replacement = r'''async function finalizeAndHome(button){
  const original=button?.textContent||'Finalizar consulta';
  if(button){button.disabled=true;button.textContent='Finalizando…'}
  signBtn.disabled=true;
  try{
    upperClinical(noteEl);
    const hasText=Boolean(String(noteEl.value||'').trim());
    if(!hasText && !documentActivity){
      const r=await fetch('/api/encounters/empty/complete',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({encounter_id:encounterId,patient_id:PATIENT_ID,queue_id:QUEUE_ID})
      });
      if(!r.ok){
        let msg='No se pudo cerrar la atención vacía.';
        try{const j=await r.json();if(j.detail)msg+=' '+j.detail}catch(_e){}
        throw new Error(msg);
      }
      encounterId=null;dirty=false;leavingAfterFinalize=true;location.href='/';return;
    }

    let id=encounterId;
    if(hasText){
      dirty=true;
      id=await save(true);
    }
    if(!id)throw new Error('No se pudo identificar la consulta para finalizarla.');
    const r=await fetch('/api/encounters/'+encodeURIComponent(id)+'/sign',{method:'POST'});
    if(!r.ok){
      let msg='No se pudo finalizar la consulta.';
      try{const j=await r.json();if(j.detail)msg+=' '+j.detail}catch(_e){}
      throw new Error(msg);
    }
    dirty=false;leavingAfterFinalize=true;location.href='/';
  }catch(err){
    if(button){button.disabled=false;button.textContent=original}
    signBtn.disabled=false;finalizeModal.hidden=true;leaveModal.hidden=true;
    showAppToast(err && err.message ? err.message : 'No se pudo finalizar la consulta.','error');
  }
}

signBtn.addEventListener('click',()=>{'''
app = sub(app, finalize_pattern, finalize_replacement, label="finalize document-only flow", flags=re.S)
app = rep(
    app,
    "  const blank=!String(noteEl.value||'').trim();\n  const title=finalizeModal.querySelector('h3');\n",
    "  const blank=!String(noteEl.value||'').trim() && !documentActivity;\n  const title=finalizeModal.querySelector('h3');\n",
    label="finalize modal documents",
)
app = rep(
    app,
    '.replace("__WORKING_ID__", json.dumps(working["id"] if working else ""))\n',
    '.replace("__WORKING_ID__", json.dumps(working["id"] if working else ""))\n        .replace("__HAS_DOCUMENTS__", "true" if working_has_documents else "false")\n',
    label="replace document state placeholder",
)

# Document launch passes consultation context even when note is still blank.
app = rep(
    app,
    "      const qs=new URLSearchParams({patient_id:PATIENT_ID});\n      if(id)qs.set('encounter_id',id);\n      window.open(route+'?'+qs.toString(),'_blank');\n",
    "      const qs=new URLSearchParams({patient_id:PATIENT_ID});\n"
    "      if(id)qs.set('encounter_id',id);\n"
    "      qs.set('from_consultation','1');\n"
    "      if(QUEUE_ID)qs.set('queue_id',QUEUE_ID);\n"
    "      qs.set('encounter_date',document.getElementById('enc-date')?.value||'');\n"
    "      qs.set('encounter_time',document.getElementById('enc-time')?.value||'');\n"
    "      window.open(route+'?'+qs.toString(),'_blank');\n",
    label="document launch context",
)

# ------------------------------------------------------------------
# DOCUMENTOS: context linkage + idempotent saves + clean button roles.
# ------------------------------------------------------------------
docs = rep(
    docs,
    "            CREATE INDEX IF NOT EXISTS idx_prescriptions_patient\n              ON prescriptions(patient_id, issued_at DESC);\n",
    "            CREATE INDEX IF NOT EXISTS idx_prescriptions_patient\n              ON prescriptions(patient_id, issued_at DESC);\n"
    "            CREATE INDEX IF NOT EXISTS idx_prescriptions_encounter\n              ON prescriptions(encounter_id);\n",
    label="prescription encounter index",
)
docs = rep(
    docs,
    "            CREATE INDEX IF NOT EXISTS idx_certificates_patient\n              ON certificates(patient_id, issued_at DESC);\n",
    "            CREATE INDEX IF NOT EXISTS idx_certificates_patient\n              ON certificates(patient_id, issued_at DESC);\n"
    "            CREATE INDEX IF NOT EXISTS idx_certificates_encounter\n              ON certificates(encounter_id);\n",
    label="certificate encounter index",
)

install_marker = '    _ensure_official_doctor_logo(Path(context["ROOT"]))\n\n'
install_helpers = r'''    _ensure_official_doctor_logo(Path(context["ROOT"]))
    doctor_name = str(context.get("DOCTOR_NAME") or "Dr. Armando Revelo")

    def ensure_document_encounter(conn, patient_id: str, encounter_id: str = "", queue_id: str = "",
                                  encounter_date: str = "", encounter_time: str = "",
                                  from_consultation: bool = False):
        enc_id = str(encounter_id or "").strip()
        qid = str(queue_id or "").strip()
        if enc_id:
            row = conn.execute(
                "SELECT id,patient_id,queue_id,note_status FROM encounters WHERE id=? LIMIT 1",
                (enc_id,),
            ).fetchone()
            if not row or str(row["patient_id"] or "") != str(patient_id):
                raise ValueError("La consulta indicada no pertenece a este paciente.")
            return enc_id, (str(row["queue_id"] or "").strip() or qid)
        if not from_consultation:
            return None, qid

        if qid:
            row = conn.execute(
                """SELECT id FROM encounters
                   WHERE patient_id=? AND queue_id=? AND note_status='draft'
                     AND COALESCE(deleted_at,'')=''
                   ORDER BY updated_at DESC LIMIT 1""",
                (patient_id, qid),
            ).fetchone()
            if row:
                return str(row["id"]), qid

        stamp = _now()
        enc_id = _id()
        enc_date = str(encounter_date or date.today().isoformat())
        enc_time = str(encounter_time or datetime.now().strftime("%H:%M"))
        conn.execute(
            """INSERT INTO encounters(
               id,patient_id,encounter_date,encounter_time,clinical_note,diagnosis,treatment,
               source,source_record_hash,is_legacy_locked,created_at,updated_at,deleted_at,
               note_status,signed_at,signed_by,copied_from_encounter_id,queue_id,created_by
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                enc_id,patient_id,enc_date,enc_time,"","","",
                "historia_clinica","document:"+enc_id,0,stamp,stamp,None,
                "draft",None,None,None,qid or None,doctor_name,
            ),
        )
        return enc_id, qid

    def mark_document_activity(conn, queue_id: str, patient_id: str, stamp: str):
        qid = str(queue_id or "").strip()
        if not qid:
            return
        try:
            conn.execute(
                """UPDATE waiting_queue
                   SET status='in_consultation',started_at=COALESCE(started_at,?),
                       clinical_patient_id=COALESCE(clinical_patient_id,?),updated_at=?
                   WHERE id=? AND status IN ('waiting','in_consultation')""",
                (stamp, patient_id, stamp, qid),
            )
        except sqlite3.OperationalError:
            pass

'''
docs = rep(docs, install_marker, install_helpers, label="document context helpers")

# Route signatures carry context.
docs = rep(
    docs,
    '    def prescription_new(patient_id: str, encounter_id: str = ""):\n',
    '    def prescription_new(patient_id: str, encounter_id: str = "", queue_id: str = "", encounter_date: str = "", encounter_time: str = "", from_consultation: int = 0):\n',
    label="prescription context signature",
)
docs = rep(
    docs,
    '    def certificate_new(patient_id: str, encounter_id: str = ""):\n',
    '    def certificate_new(patient_id: str, encounter_id: str = "", queue_id: str = "", encounter_date: str = "", encounter_time: str = "", from_consultation: int = 0):\n',
    label="certificate context signature",
)
docs = rep(
    docs,
    '    def rest_certificate_new(patient_id: str, encounter_id: str = ""):\n',
    '    def rest_certificate_new(patient_id: str, encounter_id: str = "", queue_id: str = "", encounter_date: str = "", encounter_time: str = "", from_consultation: int = 0):\n',
    label="rest context signature",
)

# Standard certificate links preserve consultation context.
docs = rep(
    docs,
    "<div class='doc-actions'><a class='doc-light' href='/certificados/reposo/nuevo?patient_id={_e(patient_id)}&encounter_id={_e(encounter_id)}'>Usar certificado de reposo / aislamiento</a></div>",
    "<div class='doc-actions'><a class='doc-light' href='/certificados/reposo/nuevo?patient_id={_e(patient_id)}&encounter_id={_e(encounter_id)}&queue_id={_e(queue_id)}&encounter_date={_e(encounter_date)}&encounter_time={_e(encounter_time)}&from_consultation={1 if from_consultation else 0}'>Usar certificado de reposo / aislamiento</a></div>",
    label="standard to rest context link",
)
docs = rep(
    docs,
    "<div class='doc-actions'><a class='doc-light' href='/certificados/nuevo?patient_id={_e(patient_id)}&encounter_id={_e(encounter_id)}'>Usar certificado médico normal</a></div>",
    "<div class='doc-actions'><a class='doc-light' href='/certificados/nuevo?patient_id={_e(patient_id)}&encounter_id={_e(encounter_id)}&queue_id={_e(queue_id)}&encounter_date={_e(encounter_date)}&encounter_time={_e(encounter_time)}&from_consultation={1 if from_consultation else 0}'>Usar certificado médico normal</a></div>",
    label="rest to standard context link",
)

# Recipe editor: real Save + reusable ID + parent notification.
docs = rep(
    docs,
    "            <button class='doc-primary' id='rx-preview'>Vista previa</button>\n            <button class='doc-primary' id='rx-print'>Imprimir</button>\n            <button class='doc-primary' id='rx-pdf'>Guardar PDF</button>\n",
    "            <button class='doc-primary' id='rx-save'>Guardar</button>\n"
    "            <button class='doc-light' id='rx-preview'>Vista previa</button>\n"
    "            <button class='doc-primary' id='rx-print'>Imprimir</button>\n"
    "            <button class='doc-light' id='rx-pdf'>Guardar PDF</button>\n"
    "            <span class='doc-save-state' id='rx-state'>Sin guardar</span>\n",
    label="recipe buttons",
)
docs = rep(
    docs,
    '        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};\n',
    '        const patientId={json.dumps(patient_id)}, queueId={json.dumps(queue_id)}, encounterDate={json.dumps(encounter_date)}, encounterTime={json.dumps(encounter_time)}, fromConsultation={"true" if from_consultation else "false"};\n        let encounterId={json.dumps(encounter_id)}, prescriptionId=null;\n',
    label="recipe context js",
)
old_rx_js = r'''        async function saveRx(){{
          const r=await fetch('/api/recetas',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{
            patient_id:patientId,encounter_id:encounterId,issued_date:document.getElementById('rx-date').value,
            series_no:document.getElementById('rx-series').value,diagnosis:document.getElementById('rx-dx').value,
            cie10:document.getElementById('rx-cie').value,allergies:document.getElementById('rx-allergy').value,
            allergies_detail:document.getElementById('rx-allergy-detail').value,items:items(),
            instructions:document.getElementById('rx-instructions').value
          }})}});
          if(!r.ok)throw new Error('No se pudo guardar la receta');
          return await r.json();
        }}
        async function openPreview(printNow=false){{
          try{{
            const j=await saveRx();
            const url=j.preview_url+(printNow?(j.preview_url.includes('?')?'&print_now=1':'?print_now=1'):'');
            window.open(url,'_blank');
          }}catch(e){{alert(e.message)}}
        }}
        document.getElementById('rx-preview').onclick=()=>openPreview(false);
        document.getElementById('rx-print').onclick=()=>openPreview(true);
        document.getElementById('rx-pdf').onclick=()=>openPreview(true);
'''
new_rx_js = r'''        function notifyParent(encId){{
          try{{if(window.opener&&!window.opener.closed)window.opener.postMessage({{type:'clinical-document-saved',encounter_id:encId||''}},location.origin)}}catch(_e){{}}
        }}
        async function saveRx(showNotice=false){{
          const payload={{
            prescription_id:prescriptionId,patient_id:patientId,encounter_id:encounterId,
            queue_id:queueId,encounter_date:encounterDate,encounter_time:encounterTime,from_consultation:fromConsultation,
            issued_date:document.getElementById('rx-date').value,
            series_no:document.getElementById('rx-series').value,diagnosis:document.getElementById('rx-dx').value,
            cie10:document.getElementById('rx-cie').value,allergies:document.getElementById('rx-allergy').value,
            allergies_detail:document.getElementById('rx-allergy-detail').value,items:items(),
            instructions:document.getElementById('rx-instructions').value
          }};
          const r=await fetch('/api/recetas',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
          const j=await r.json().catch(()=>({{}}));
          if(!r.ok||!j.ok)throw new Error(j.error||'No se pudo guardar la receta');
          prescriptionId=j.id||prescriptionId;
          if(j.encounter_id)encounterId=j.encounter_id;
          notifyParent(encounterId);
          const state=document.getElementById('rx-state');
          if(state)state.textContent='Guardada';
          if(showNotice&&window.showAppToast)showAppToast('Receta guardada correctamente.','success');
          return j;
        }}
        async function openPreview(mode='preview'){{
          const popup=window.open('about:blank','_blank');
          try{{
            const j=await saveRx(false);
            let url=j.preview_url;
            if(mode==='print')url+=(url.includes('?')?'&':'?')+'print_now=1';
            if(popup)popup.location.replace(url);else window.open(url,'_blank');
          }}catch(e){{if(popup)popup.close();alert(e.message)}}
        }}
        document.getElementById('rx-save').onclick=()=>saveRx(true).catch(e=>alert(e.message));
        document.getElementById('rx-preview').onclick=()=>openPreview('preview');
        document.getElementById('rx-print').onclick=()=>openPreview('print');
        document.getElementById('rx-pdf').onclick=()=>openPreview('pdf');
'''
docs = rep(docs, old_rx_js, new_rx_js, label="recipe save print js")

# Replace prescription API with idempotent upsert + encounter creation on actual save.
rx_api_pattern = r'    @app\.post\("/api/recetas"\)\n    async def prescription_save\(request: Request\):.*?\n    @app\.get\("/recetas/\{rx_id\}/vista", response_class=HTMLResponse\)'
rx_api_new = r'''    @app.post("/api/recetas")
    async def prescription_save(request: Request):
        payload = await request.json()
        patient_id = str(payload.get("patient_id") or "").strip()
        if not patient_id:
            return JSONResponse({"ok": False, "error": "patient_id requerido"}, status_code=400)
        stamp = _now()
        issued_date = str(payload.get("issued_date") or date.today().isoformat())
        issued_at = issued_date + "T" + datetime.now().strftime("%H:%M:%S")
        rid = str(payload.get("prescription_id") or "").strip() or _id()
        with _connect(db_path) as conn:
            patient_id = _canonical_patient_id(conn, patient_id)
            if not _patient(conn, patient_id):
                return JSONResponse({"ok": False, "error": "Paciente no encontrado"}, status_code=404)
            try:
                enc_id, qid = ensure_document_encounter(
                    conn, patient_id, str(payload.get("encounter_id") or ""),
                    str(payload.get("queue_id") or ""), str(payload.get("encounter_date") or ""),
                    str(payload.get("encounter_time") or ""), bool(payload.get("from_consultation")),
                )
            except ValueError as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
            current = conn.execute(
                "SELECT id,patient_id FROM prescriptions WHERE id=? AND COALESCE(deleted_at,'')=''",
                (rid,),
            ).fetchone()
            values = (
                patient_id, enc_id, issued_at, str(payload.get("series_no") or ""),
                str(payload.get("diagnosis") or "").upper(), str(payload.get("cie10") or "").upper(),
                str(payload.get("allergies") or "NO").upper(), str(payload.get("allergies_detail") or "").upper(),
                json.dumps(payload.get("items") or [], ensure_ascii=False),
                str(payload.get("instructions") or "").upper(), stamp,
            )
            if current:
                if str(current["patient_id"] or "") != patient_id:
                    return JSONResponse({"ok": False, "error": "La receta pertenece a otro paciente"}, status_code=409)
                conn.execute(
                    """UPDATE prescriptions SET patient_id=?,encounter_id=?,issued_at=?,series_no=?,diagnosis=?,cie10=?,
                       allergies=?,allergies_detail=?,items_json=?,instructions=?,updated_at=? WHERE id=?""",
                    values + (rid,),
                )
            else:
                conn.execute(
                    """INSERT INTO prescriptions(
                       id,patient_id,encounter_id,issued_at,series_no,diagnosis,cie10,allergies,
                       allergies_detail,items_json,instructions,created_at,updated_at,deleted_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (rid,) + values[:-1] + (stamp, stamp),
                )
            mark_document_activity(conn, qid, patient_id, stamp)
            conn.commit()
        return JSONResponse({"ok": True, "id": rid, "encounter_id": enc_id, "preview_url": f"/recetas/{rid}/vista"})

    @app.get("/recetas/{rx_id}/vista", response_class=HTMLResponse)'''
docs = sub(docs, rx_api_pattern, rx_api_new, label="prescription upsert api", flags=re.S)

# Standard certificate: context, save-only button, reusable ID.
docs = rep(
    docs,
    "        <div class='doc-actions'><button class='doc-primary' id='cert-preview'>Vista previa</button><button class='doc-primary' id='cert-print'>Imprimir</button><button class='doc-primary' id='cert-pdf'>Guardar PDF</button><button class='doc-muted' onclick='window.close()'>Cancelar</button></div>\n",
    "        <div class='doc-actions'><button class='doc-primary' id='cert-save'>Guardar</button><button class='doc-light' id='cert-preview'>Vista previa</button><button class='doc-primary' id='cert-print'>Imprimir</button><button class='doc-light' id='cert-pdf'>Guardar PDF</button><span class='doc-save-state' id='cert-state'>Sin guardar</span><button class='doc-muted' onclick='window.close()'>Cancelar</button></div>\n",
    label="certificate buttons",
)
# This is the second patientId/encounterId JS occurrence after recipe was already changed.
docs = rep(
    docs,
    '        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};\n        const certBody=',
    '        const patientId={json.dumps(patient_id)}, queueId={json.dumps(queue_id)}, encounterDate={json.dumps(encounter_date)}, encounterTime={json.dumps(encounter_time)}, fromConsultation={"true" if from_consultation else "false"};\n        let encounterId={json.dumps(encounter_id)}, certificateId=null;\n        const certBody=',
    label="certificate context js",
)
docs = rep(
    docs,
    '            patient_id:patientId,encounter_id:encounterId,issued_date:document.getElementById(\'cert-date\').value,\n',
    '            certificate_id:certificateId,patient_id:patientId,encounter_id:encounterId,queue_id:queueId,encounter_date:encounterDate,encounter_time:encounterTime,from_consultation:fromConsultation,issued_date:document.getElementById(\'cert-date\').value,\n',
    label="certificate payload context",
)
old_cert_save_js = r'''        async function saveCert(){{
          const payload=certPayload();
          payload.body_text=certBody.value;
          const r=await fetch('/api/certificados',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
          if(!r.ok)throw new Error('No se pudo guardar el certificado');return await r.json();
        }}
        async function openCert(printNow=false){{try{{const j=await saveCert();const url=j.preview_url+(printNow?(j.preview_url.includes('?')?'&print_now=1':'?print_now=1'):'');window.open(url,'_blank')}}catch(e){{alert(e.message)}}}}
        document.getElementById('cert-preview').onclick=()=>openCert(false);
        document.getElementById('cert-print').onclick=()=>openCert(true);
        document.getElementById('cert-pdf').onclick=()=>openCert(true);
'''
new_cert_save_js = r'''        function notifyCertParent(encId){{try{{if(window.opener&&!window.opener.closed)window.opener.postMessage({{type:'clinical-document-saved',encounter_id:encId||''}},location.origin)}}catch(_e){{}}}}
        async function saveCert(showNotice=false){{
          const payload=certPayload();payload.body_text=certBody.value;
          const r=await fetch('/api/certificados',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
          const j=await r.json().catch(()=>({{}}));
          if(!r.ok||!j.ok)throw new Error(j.error||'No se pudo guardar el certificado');
          certificateId=j.id||certificateId;if(j.encounter_id)encounterId=j.encounter_id;notifyCertParent(encounterId);
          const s=document.getElementById('cert-state');if(s)s.textContent='Guardado';
          if(showNotice&&window.showAppToast)showAppToast('Certificado guardado correctamente.','success');
          return j;
        }}
        async function openCert(mode='preview'){{const popup=window.open('about:blank','_blank');try{{const j=await saveCert(false);let url=j.preview_url;if(mode==='print')url+=(url.includes('?')?'&':'?')+'print_now=1';if(popup)popup.location.replace(url);else window.open(url,'_blank')}}catch(e){{if(popup)popup.close();alert(e.message)}}}}
        document.getElementById('cert-save').onclick=()=>saveCert(true).catch(e=>alert(e.message));
        document.getElementById('cert-preview').onclick=()=>openCert('preview');
        document.getElementById('cert-print').onclick=()=>openCert('print');
        document.getElementById('cert-pdf').onclick=()=>openCert('pdf');
'''
docs = rep(docs, old_cert_save_js, new_cert_save_js, label="certificate save print js")

cert_api_pattern = r'    @app\.post\("/api/certificados"\)\n    async def certificate_save\(request: Request\):.*?\n    @app\.get\("/certificados/\{cert_id\}/vista", response_class=HTMLResponse\)'
cert_api_new = r'''    @app.post("/api/certificados")
    async def certificate_save(request: Request):
        p = await request.json()
        patient_id = str(p.get("patient_id") or "").strip()
        stamp = _now()
        cid = str(p.get("certificate_id") or "").strip() or _id()
        with _connect(db_path) as conn:
            patient_id = _canonical_patient_id(conn, patient_id)
            patient = _patient(conn, patient_id)
            if not patient:
                return JSONResponse({"ok": False, "error": "Paciente no encontrado"}, status_code=404)
            try:
                enc_id, qid = ensure_document_encounter(
                    conn, patient_id, str(p.get("encounter_id") or ""), str(p.get("queue_id") or ""),
                    str(p.get("encounter_date") or ""), str(p.get("encounter_time") or ""), bool(p.get("from_consultation")),
                )
            except ValueError as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
            settings = _settings(conn)
            enc = _encounter(conn, enc_id)
            rest_days = max(0, int(p.get("rest_days") or 0))
            body_text = str(p.get("body_text") or "").strip()
            extras = p.get("additional_diagnoses")
            if not isinstance(extras, list):
                extras = []
                legacy_dx = str(p.get("additional_diagnosis") or "").strip()
                legacy_cie = str(p.get("additional_cie10") or "").strip()
                if legacy_dx or legacy_cie:
                    extras.append({"diagnosis": legacy_dx, "cie10": legacy_cie})
            if not body_text:
                body_text = _certificate_body(
                    patient, enc, str(p.get("diagnosis") or ""), str(p.get("cie10") or ""), extras, "",
                    str(p.get("procedure_text") or ""), rest_days,
                    str(p.get("rest_from") or date.today().isoformat()), str(p.get("rest_to") or date.today().isoformat()), settings,
                )
            stored_extra_dx = " | ".join(str(x.get("diagnosis") or "").strip().upper() for x in extras if isinstance(x, dict) and str(x.get("diagnosis") or "").strip())
            stored_extra_cie = " | ".join(str(x.get("cie10") or "").strip().upper() for x in extras if isinstance(x, dict) and str(x.get("cie10") or "").strip())
            issued_at = str(p.get("issued_date") or date.today().isoformat()) + "T" + datetime.now().strftime("%H:%M:%S")
            values = (
                patient_id,enc_id,issued_at,str(p.get("diagnosis") or "").upper(),str(p.get("cie10") or "").upper(),
                stored_extra_dx,stored_extra_cie,str(p.get("procedure_text") or "").upper(),rest_days,
                str(p.get("rest_from") or ""),str(p.get("rest_to") or ""),body_text.upper(),stamp,
            )
            current = conn.execute("SELECT id,patient_id FROM certificates WHERE id=? AND COALESCE(deleted_at,'')=''",(cid,)).fetchone()
            if current:
                if str(current["patient_id"] or "") != patient_id:
                    return JSONResponse({"ok": False, "error": "El certificado pertenece a otro paciente"}, status_code=409)
                conn.execute(
                    """UPDATE certificates SET patient_id=?,encounter_id=?,issued_at=?,diagnosis=?,cie10=?,additional_diagnosis=?,
                       additional_cie10=?,procedure_text=?,rest_days=?,rest_from=?,rest_to=?,body_text=?,updated_at=? WHERE id=?""",
                    values + (cid,),
                )
            else:
                conn.execute(
                    """INSERT INTO certificates(id,patient_id,encounter_id,issued_at,diagnosis,cie10,additional_diagnosis,
                       additional_cie10,procedure_text,rest_days,rest_from,rest_to,body_text,created_at,updated_at,deleted_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (cid,) + values[:-1] + (stamp,stamp),
                )
            mark_document_activity(conn,qid,patient_id,stamp)
            conn.commit()
        return JSONResponse({"ok": True, "id": cid, "encounter_id": enc_id, "preview_url": f"/certificados/{cid}/vista"})

    @app.get("/certificados/{cert_id}/vista", response_class=HTMLResponse)'''
docs = sub(docs, cert_api_pattern, cert_api_new, label="certificate upsert api", flags=re.S)

# Rest certificate context + save-only + reusable ID.
docs = rep(
    docs,
    "            <button class='doc-primary' id='rest-preview'>Vista previa</button>\n            <button class='doc-primary' id='rest-print'>Imprimir</button>\n            <button class='doc-primary' id='rest-pdf'>Guardar PDF</button>\n",
    "            <button class='doc-primary' id='rest-save'>Guardar</button>\n"
    "            <button class='doc-light' id='rest-preview'>Vista previa</button>\n"
    "            <button class='doc-primary' id='rest-print'>Imprimir</button>\n"
    "            <button class='doc-light' id='rest-pdf'>Guardar PDF</button>\n"
    "            <span class='doc-save-state' id='rest-state'>Sin guardar</span>\n",
    label="rest buttons",
)
docs = rep(
    docs,
    '        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};\n        function localIso',
    '        const patientId={json.dumps(patient_id)}, queueId={json.dumps(queue_id)}, encounterDate={json.dumps(encounter_date)}, encounterTime={json.dumps(encounter_time)}, fromConsultation={"true" if from_consultation else "false"};\n        let encounterId={json.dumps(encounter_id)}, certificateId=null;\n        function localIso',
    label="rest context js",
)
docs = rep(
    docs,
    '            patient_id:patientId,encounter_id:encounterId,\n            issued_date:',
    '            certificate_id:certificateId,patient_id:patientId,encounter_id:encounterId,queue_id:queueId,encounter_date:encounterDate,encounter_time:encounterTime,from_consultation:fromConsultation,\n            issued_date:',
    label="rest payload context",
)
old_rest_js = r'''        async function saveRest(){{
          const data=payload();
          if(!data.contingency)throw new Error('Seleccione si existe contingencia.');
          if(!data.symptoms)throw new Error('Seleccione si el paciente presenta síntomas.');
          const r=await fetch('/api/certificados/reposo',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
          const j=await r.json();
          if(!r.ok||!j.ok)throw new Error(j.error||'No se pudo guardar el certificado');
          return j;
        }}
        async function openRest(printNow=false){{
          try{{
            const j=await saveRest();
            const url=j.preview_url+(printNow?(j.preview_url.includes('?')?'&print_now=1':'?print_now=1'):'');
            window.open(url,'_blank');
          }}catch(e){{alert(e.message)}}
        }}
        document.getElementById('rest-preview').onclick=()=>openRest(false);
        document.getElementById('rest-print').onclick=()=>openRest(true);
        document.getElementById('rest-pdf').onclick=()=>openRest(true);
'''
new_rest_js = r'''        function notifyRestParent(encId){{try{{if(window.opener&&!window.opener.closed)window.opener.postMessage({{type:'clinical-document-saved',encounter_id:encId||''}},location.origin)}}catch(_e){{}}}}
        async function saveRest(showNotice=false){{
          const data=payload();if(!data.contingency)throw new Error('Seleccione si existe contingencia.');if(!data.symptoms)throw new Error('Seleccione si el paciente presenta síntomas.');
          const r=await fetch('/api/certificados/reposo',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});
          const j=await r.json().catch(()=>({{}}));if(!r.ok||!j.ok)throw new Error(j.error||'No se pudo guardar el certificado');
          certificateId=j.id||certificateId;if(j.encounter_id)encounterId=j.encounter_id;notifyRestParent(encounterId);
          const s=document.getElementById('rest-state');if(s)s.textContent='Guardado';
          if(showNotice&&window.showAppToast)showAppToast('Certificado guardado correctamente.','success');return j;
        }}
        async function openRest(mode='preview'){{const popup=window.open('about:blank','_blank');try{{const j=await saveRest(false);let url=j.preview_url;if(mode==='print')url+=(url.includes('?')?'&':'?')+'print_now=1';if(popup)popup.location.replace(url);else window.open(url,'_blank')}}catch(e){{if(popup)popup.close();alert(e.message)}}}}
        document.getElementById('rest-save').onclick=()=>saveRest(true).catch(e=>alert(e.message));
        document.getElementById('rest-preview').onclick=()=>openRest('preview');
        document.getElementById('rest-print').onclick=()=>openRest('print');
        document.getElementById('rest-pdf').onclick=()=>openRest('pdf');
'''
docs = rep(docs, old_rest_js, new_rest_js, label="rest save print js")

rest_api_pattern = r'    @app\.post\("/api/certificados/reposo"\)\n    async def rest_certificate_save\(request: Request\):.*?\n    @app\.get\("/certificados/reposo/\{cert_id\}/vista", response_class=HTMLResponse\)'
rest_api_new = r'''    @app.post("/api/certificados/reposo")
    async def rest_certificate_save(request: Request):
        p = await request.json()
        patient_id = str(p.get("patient_id") or "").strip()
        stamp = _now()
        cid = str(p.get("certificate_id") or "").strip() or _id()
        with _connect(db_path) as conn:
            patient_id = _canonical_patient_id(conn, patient_id)
            patient = _patient(conn, patient_id)
            if not patient:
                return JSONResponse({"ok": False, "error": "Paciente no encontrado"}, status_code=404)
            try:
                enc_id,qid=ensure_document_encounter(conn,patient_id,str(p.get("encounter_id") or ""),str(p.get("queue_id") or ""),str(p.get("encounter_date") or ""),str(p.get("encounter_time") or ""),bool(p.get("from_consultation")))
            except ValueError as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)
            rest_days=max(1,int(p.get("rest_days") or 1));contingency=str(p.get("contingency") or "").strip().upper();symptoms=str(p.get("symptoms") or "").strip().upper()
            if contingency not in {"SI","NO"}:return JSONResponse({"ok":False,"error":"Seleccione si existe contingencia."},status_code=400)
            if symptoms not in {"SI","NO"}:return JSONResponse({"ok":False,"error":"Seleccione si el paciente presenta síntomas."},status_code=400)
            extras=p.get("additional_diagnoses");extras=extras if isinstance(extras,list) else []
            extras=[{"diagnosis":str(x.get("diagnosis") or "").strip().upper(),"cie10":str(x.get("cie10") or "").strip().upper()} for x in extras if isinstance(x,dict) and (str(x.get("diagnosis") or "").strip() or str(x.get("cie10") or "").strip())]
            issued_at=str(p.get("issued_date") or date.today().isoformat())+"T"+datetime.now().strftime("%H:%M:%S")
            extra={"establishment":str(p.get("establishment") or ""),"place":str(p.get("place") or "Quevedo"),"institution":str(p.get("institution") or ""),"job_title":str(p.get("job_title") or ""),"history_no":str(p.get("history_no") or ""),"address":str(p.get("address") or ""),"phone":str(p.get("phone") or ""),"email":str(p.get("email") or ""),"rest_reason":str(p.get("rest_reason") or ""),"contingency":contingency,"symptoms":symptoms,"disease_text":str(p.get("disease_text") or ""),"additional_diagnoses":extras}
            body_text=str(extra["disease_text"] or p.get("diagnosis") or "").strip().upper();stored_extra_dx=" | ".join(x["diagnosis"] for x in extras if x["diagnosis"]);stored_extra_cie=" | ".join(x["cie10"] for x in extras if x["cie10"])
            values=(patient_id,enc_id,issued_at,str(p.get("diagnosis") or "").upper(),str(p.get("cie10") or "").upper(),stored_extra_dx,stored_extra_cie,str(extra["rest_reason"] or "").upper(),rest_days,str(p.get("rest_from") or ""),str(p.get("rest_to") or ""),body_text,"rest_isolation",json.dumps(extra,ensure_ascii=False),stamp)
            current=conn.execute("SELECT id,patient_id FROM certificates WHERE id=? AND COALESCE(deleted_at,'')=''",(cid,)).fetchone()
            if current:
                if str(current["patient_id"] or "")!=patient_id:return JSONResponse({"ok":False,"error":"El certificado pertenece a otro paciente"},status_code=409)
                conn.execute("""UPDATE certificates SET patient_id=?,encounter_id=?,issued_at=?,diagnosis=?,cie10=?,additional_diagnosis=?,additional_cie10=?,procedure_text=?,rest_days=?,rest_from=?,rest_to=?,body_text=?,certificate_type=?,extra_json=?,updated_at=? WHERE id=?""",values+(cid,))
            else:
                conn.execute("""INSERT INTO certificates(id,patient_id,encounter_id,issued_at,diagnosis,cie10,additional_diagnosis,additional_cie10,procedure_text,rest_days,rest_from,rest_to,body_text,certificate_type,extra_json,created_at,updated_at,deleted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",(cid,)+values[:-1]+(stamp,stamp))
            mark_document_activity(conn,qid,patient_id,stamp);conn.commit()
        return JSONResponse({"ok":True,"id":cid,"encounter_id":enc_id,"preview_url":f"/certificados/reposo/{cid}/vista"})

    @app.get("/certificados/reposo/{cert_id}/vista", response_class=HTMLResponse)'''
docs = sub(docs, rest_api_pattern, rest_api_new, label="rest certificate upsert api", flags=re.S)

# Robust auto-print: user clicks Imprimir, print dialog must fire on loaded document.
docs = docs.replace(
    "window.addEventListener('load',()=>setTimeout(()=>window.print(),250));",
    "(()=>{let fired=false;const go=()=>{if(fired)return;fired=true;try{window.focus()}catch(_e){};setTimeout(()=>{try{window.print()}catch(_e){}},450)};if(document.readyState==='complete')go();else window.addEventListener('load',go,{once:true});window.addEventListener('pageshow',go,{once:true});})();"
)
if "setTimeout(()=>window.print(),250)" in docs:
    raise RuntimeError("old auto-print hook still present")

app_path.write_text(app, encoding="utf-8")
docs_path.write_text(docs, encoding="utf-8")

# UI for linked document cards and save state.
with css_path.open("a", encoding="utf-8") as fh:
    fh.write(r'''

/* ======================================================================
   v1.3.70 · Documentos ligados a consulta + acciones de documento
   ====================================================================== */
.encounter-documents{margin:13px 0 3px;border:1px solid #d9e4ee;border-radius:12px;background:#f8fbfe;overflow:hidden}
.encounter-documents-title{display:flex;align-items:center;justify-content:space-between;padding:9px 11px;border-bottom:1px solid #e1e9f0;background:#f1f6fa;color:#49647c}
.encounter-documents-title span{font-size:10px;font-weight:950;letter-spacing:.08em}
.encounter-documents-title strong{min-width:24px;height:24px;display:grid;place-items:center;border-radius:999px;background:#dfeaf4;color:#214c72;font-size:11px}
.encounter-document-row{display:flex;align-items:center;gap:9px;padding:10px 11px;border-bottom:1px solid #e7edf3}
.encounter-document-row:last-child{border-bottom:0}
.encounter-document-icon{width:34px;height:28px;display:grid;place-items:center;border-radius:7px;background:#e7f1f8;color:#225a86;font-size:9px;font-weight:950}
.encounter-document-copy{min-width:0;flex:1;display:flex;flex-direction:column;gap:2px}.encounter-document-copy b{font-size:12px;color:#183b56}.encounter-document-copy small{font-size:10px;color:#718394}
.encounter-document-row>a{font-size:10.5px;font-weight:850;color:#245f94;text-decoration:none;padding:5px 7px;border-radius:6px}.encounter-document-row>a:hover{background:#e8f1f8}
.encounter-documents-compact{margin-top:10px}.encounter-documents-compact .encounter-document-row{padding:8px 9px}.encounter-documents-compact .encounter-document-copy b{font-size:11px}
.doc-save-state{display:inline-flex;align-items:center;min-height:38px;padding:0 10px;color:#5d7083;font-size:11px;font-weight:800}
''')

# Version files.
(DST / "historia-version.json").write_text(json.dumps({"version":"1.3.70"}, indent=2) + "\n", encoding="utf-8")
manifest_path = DST / "update_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = manifest["app_version"] = manifest["runtime_version"] = "1.3.70"
manifest["notes"]["purpose"] = "Ligar recetas/certificados a la consulta clínica y corregir Guardar/Imprimir sin duplicados."
manifest["notes"]["previous_version"] = "1.3.69"
manifest["notes"]["functional_changes"] = True
manifest["notes"]["database_schema_changes"] = True
manifest["notes"]["ui_only_release"] = False
manifest["notes"]["clinical_logic_unchanged_from_1_3_68"] = False
manifest["notes"]["printing_logic_unchanged_from_1_3_68"] = False
manifest["notes"].update({
    "documents_linked_to_encounter": True,
    "document_only_encounter_supported": True,
    "prescription_save_does_not_print": True,
    "prescription_reprint_no_duplicate": True,
    "certificate_reprint_no_duplicate": True,
    "auto_print_hardened": True,
    "encounter_document_indexes": True,
})
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

channel_path = ROOT / "historia-clinica/launcher-v1/app-channel-source.json"
channel = json.loads(channel_path.read_text(encoding="utf-8"))
channel["appVersion"] = "1.3.70"
channel["notes"] = "Historia Clínica 1.3.70: recetas y certificados ligados a la consulta clínica; Guardar ya no abre impresión; Imprimir dispara el diálogo automáticamente y reimprimir no duplica documentos."
for item in channel["files"]:
    item["sourcePath"] = item["sourcePath"].replace("v1_3_69_professional_ui", "v1_3_70_linked_documents")
channel_path.write_text(json.dumps(channel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Static contract checks.
assert "appVersion\": \"1.3.70" in channel_path.read_text(encoding="utf-8")
assert "id='rx-save'" in docs
assert "prescription_id:prescriptionId" in docs
assert "clinical-document-saved" in docs and "clinical-document-saved" in app
assert "DOCUMENTOS DE ESTA CONSULTA" in app
assert "_v1370_encounter_has_documents" in app
assert "print_now=1" in docs
assert "openPreview('print')" in docs
assert "openPreview('pdf')" in docs
assert "rx-pdf').onclick=()=>openPreview('pdf')" in docs
assert "rx-print').onclick=()=>openPreview('print')" in docs
assert "idx_prescriptions_encounter" in docs and "idx_certificates_encounter" in docs

py_compile.compile(str(app_path), doraise=True)
py_compile.compile(str(docs_path), doraise=True)
print("Historia 1.3.70 candidate generated and compiled successfully")
