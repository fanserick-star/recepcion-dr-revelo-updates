from pathlib import Path
import json
import shutil

root = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new)


# -----------------------------------------------------------------------------
# Historia 1.3.73
# -----------------------------------------------------------------------------
hsrc = root / "historia-clinica/updates/v1_3_72_waiting_opens_card"
hdst = root / "historia-clinica/updates/v1_3_73_waiting_room_remaster"
if hdst.exists():
    shutil.rmtree(hdst)
shutil.copytree(hsrc, hdst)
app_path = hdst / "app.py"
app = app_path.read_text(encoding="utf-8")

app = replace_once(
    app,
    '''        queue = conn.execute("""
            SELECT * FROM waiting_queue WHERE status IN ('waiting','in_consultation')
            ORDER BY CASE status WHEN 'in_consultation' THEN 0 ELSE 1 END, queued_at ASC LIMIT 20
        """).fetchall()''',
    '''        # v1.3.73: datos útiles para la sala de espera, sólo desde SQLite local.
        queue = conn.execute("""
            SELECT q.*,
                   p.birth_date AS patient_birth_date,
                   (SELECT e.encounter_date
                      FROM encounters e
                     WHERE e.patient_id=q.clinical_patient_id
                       AND e.note_status IN ('signed','legacy')
                       AND COALESCE(e.deleted_at,'')=''
                     ORDER BY e.encounter_date DESC,
                              COALESCE(e.encounter_time,'') DESC,
                              COALESCE(e.updated_at,'') DESC
                     LIMIT 1) AS last_encounter_date
            FROM waiting_queue q
            LEFT JOIN patients p ON p.id=q.clinical_patient_id
            WHERE q.status IN ('waiting','in_consultation')
            ORDER BY CASE q.status WHEN 'in_consultation' THEN 0 ELSE 1 END,
                     q.queued_at ASC
            LIMIT 20
        """).fetchall()''',
    "Historia queue query",
)

app = replace_once(
    app,
    '''    if raw in {"P", "X", "PROCEDIMIENTO"}:
        return True
    if raw in {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}:
        return False''',
    '''    if raw in {"P", "X", "PROCEDIMIENTO"} or raw.startswith("PROCEDIMIENTO "):
        return True
    if raw in {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE"}:
        return False''',
    "procedure detector",
)

anchor = '''    # Compatibilidad con el puente antiguo: enviaba el nombre real del
    # procedimiento (ECOGRAFÍA, CURACIÓN, etc.) en attention_type.'''
helper = '''def _v1373_procedure_label(row) -> str:
    raw = str(row["attention_type"] or "").strip()
    norm = normalize_search(raw).upper().strip()
    if norm in {"P", "X", "PROCEDIMIENTO"}:
        return "PROCEDIMIENTO"
    if norm.startswith("PROCEDIMIENTO "):
        for sep in ("·", ":", "-"):
            if sep in raw:
                tail = raw.split(sep, 1)[1].strip()
                if tail:
                    return tail.upper()
        tail = raw[len("Procedimiento"):].strip()
        return tail.upper() or "PROCEDIMIENTO"
    if _queue_is_procedure(row):
        return raw.upper() or "PROCEDIMIENTO"
    return ""


def _v1373_last_attention_label(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Sin atenciones anteriores"
    try:
        d = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        today = datetime.now().date()
        delta = (today - d).days
        if delta == 0:
            return "Última atención: Hoy"
        if delta == 1:
            return "Última atención: Ayer"
        return "Última atención: " + d.strftime("%d/%m/%Y")
    except Exception:
        return "Última atención: " + raw


def _v1373_queue_has_signed_encounter(conn, row, patient_id="") -> bool:
    qid = str(row["id"] or "").strip()
    pid = str(patient_id or row["clinical_patient_id"] or "").strip()
    if not qid or not pid:
        return False
    return bool(conn.execute(
        "SELECT 1 FROM encounters WHERE queue_id=? AND patient_id=? AND note_status='signed' LIMIT 1",
        (qid, pid),
    ).fetchone())


def _v1373_reconcile_signed_queue_items() -> int:
    """Cierra sólo turnos activos cuyo mismo queue_id ya produjo una historia firmada."""
    stamp = now_iso()
    fixed = 0
    with db() as conn:
        rows = conn.execute("""
            SELECT q.* FROM waiting_queue q
            WHERE q.status IN ('waiting','in_consultation')
              AND COALESCE(q.clinical_patient_id,'')<>''
              AND EXISTS(
                    SELECT 1 FROM encounters e
                    WHERE e.queue_id=q.id
                      AND e.patient_id=q.clinical_patient_id
                      AND e.note_status='signed'
              )
        """).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE waiting_queue SET status='completed', completed_at=COALESCE(completed_at,?), updated_at=? WHERE id=?",
                (stamp, stamp, row["id"]),
            )
            conn.execute("""
                UPDATE encounters SET queue_id=NULL,updated_at=?
                WHERE queue_id=? AND note_status='draft'
                  AND COALESCE(TRIM(clinical_note),'')=''
                  AND COALESCE(TRIM(diagnosis),'')=''
                  AND COALESCE(TRIM(treatment),'')=''
            """, (stamp, row["id"]))
            audit(conn, "reconcile_signed_queue", "waiting_queue", row["id"], {
                "patient_id": row["clinical_patient_id"],
                "reason": "signed_encounter_for_same_queue",
            })
            fixed += 1
        if fixed:
            conn.commit()
    if fixed:
        try:
            SYNC_SERVICE.mark_activity()
            SYNC_SERVICE.wake()
        except Exception:
            pass
    return fixed


'''
app = replace_once(app, anchor, helper + anchor, "v1373 helpers")

app = replace_once(
    app,
    '''    return bool(
        link
        and str(link["clinical_patient_id"] or "") == patient_id
        and str(link["matched_by"] or "") == "doctor_confirmed_new"
    )''',
    '''    if bool(
        link
        and str(link["clinical_patient_id"] or "") == patient_id
        and str(link["matched_by"] or "") == "doctor_confirmed_new"
    ):
        return True
    # Si el mismo turno ya produjo una consulta firmada, la ficha existe y no
    # se vuelve a ofrecer crearla, aunque matched_by sea lan_new_demographics.
    return _v1373_queue_has_signed_encounter(conn, row, patient_id)''',
    "new-patient signed guard",
)

app = replace_once(
    app,
    '''def home():
    today = datetime.now().strftime("%Y-%m-%d")''',
    '''def home():
    _v1373_reconcile_signed_queue_items()
    today = datetime.now().strftime("%Y-%m-%d")''',
    "home reconciliation",
)

app = replace_once(
    app,
    '''            service_tag = (
                "<span class='queue-type queue-type-procedimiento'>PROCEDIMIENTO</span>"
                if is_procedure else ""
            )
            queued = e((r["queued_at"] or "")[-8:-3])''',
    '''            procedure_name = _v1373_procedure_label(r) if is_procedure else ""
            service_tag = (
                f"<span class='queue-procedure-chip'><span>PROCEDIMIENTO</span><b>{e(procedure_name)}</b></span>"
                if is_procedure else ""
            )
            age = age_from_birth(r["patient_birth_date"]) if "patient_birth_date" in r.keys() else ""
            last_label = _v1373_last_attention_label(r["last_encounter_date"] if "last_encounter_date" in r.keys() else "")
            patient_meta = " · ".join(x for x in ((f"{age} años" if age else ""), last_label) if x)
            queued = e((r["queued_at"] or "")[-8:-3])''',
    "procedure label and patient metadata",
)

app = replace_once(
    app,
    '''                f"<div class='queue-row queue-row-clickable {'queue-row-new' if is_new else ''}'>"
                f"<a class='queue-row-main' href='{href}' title='{e(action_label)}'>"
                f"{turn_badge}"
                f"<div class='queue-avatar'>{e((r['display_name'] or '?')[:1])}</div>"
                f"<span class='queue-patient-copy'><b>{e(r['display_name'])}</b>"
                f"<span class='queue-tags'><span class='queue-type queue-type-{e(attention_key)}'>{'★ PACIENTE NUEVO' if is_new else e(attention_label)}</span>"
                f"{service_tag}<span class='queue-status'>{e(status_text)}</span></span></span>"
                f"<time>{queued}</time><span class='queue-row-action'>{e(action_label)} ›</span></a>"''',
    '''                f"<div class='queue-row queue-row-clickable {'queue-row-new' if is_new else ''} {'queue-row-procedure' if is_procedure else 'queue-row-consultation'}'>"
                f"<a class='queue-row-main' href='{href}' title='{e(action_label)}'>"
                f"{turn_badge}"
                f"<div class='queue-avatar'>{e((r['display_name'] or '?')[:1])}</div>"
                f"<span class='queue-patient-copy'><b>{e(r['display_name'])}</b>"
                f"<small class='queue-patient-meta'>{e(patient_meta)}</small>"
                f"<span class='queue-tags'><span class='queue-type queue-type-{e(attention_key)}'>{'★ PACIENTE NUEVO' if is_new else e(attention_label)}</span>"
                f"{service_tag}<span class='queue-status'>{e(status_text)}</span></span></span>"
                f"<time>{queued}</time><span class='queue-row-action'>{e(action_label)} ›</span></a>"''',
    "queue card markup",
)

app_path.write_text(app, encoding="utf-8")

css_path = hdst / "static/style.css"
css = css_path.read_text(encoding="utf-8")
css += '''

/* v1.3.73 · Sala de espera profesional */
.cp-remaster-app .queue-row{position:relative;border-left:4px solid transparent}
.cp-remaster-app .queue-row-consultation{border-left-color:#2d6f9f}
.cp-remaster-app .queue-row-procedure{border-left-color:#7a4ca5;background:linear-gradient(90deg,#fbf8ff 0,#fff 24%)}
.cp-remaster-app .queue-row-procedure:hover{background:#f8f3fc}
.cp-remaster-app .queue-row-procedure .queue-avatar{background:#f0e8f7;color:#6b3e91}
.cp-remaster-app .queue-row-procedure .queue-turn-number{background:#f0e8f7;color:#6b3e91;border-color:#dac7ea}
.cp-remaster-app .queue-patient-copy{min-width:0;flex:1}
.cp-remaster-app .queue-patient-meta{display:block!important;margin-top:4px!important;color:#6a7788!important;font-size:11.5px!important;font-weight:600}
.cp-remaster-app .queue-procedure-chip{display:inline-flex;align-items:center;gap:6px;max-width:360px;border:1px solid #d9c5e8;background:#f5effa;color:#603782;border-radius:999px;padding:5px 8px;font-size:10px;line-height:1}
.cp-remaster-app .queue-procedure-chip span{font-weight:800;letter-spacing:.055em}
.cp-remaster-app .queue-procedure-chip b{font-size:10.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cp-remaster-app .queue-dismiss-btn{opacity:.42;transition:.15s ease}
.cp-remaster-app .queue-row:hover .queue-dismiss-btn{opacity:1}
@media(max-width:760px){.cp-remaster-app .queue-procedure-chip{max-width:210px}.cp-remaster-app .queue-patient-meta{font-size:10.5px!important}}
'''
css_path.write_text(css, encoding="utf-8")

(hdst / "historia-version.json").write_text(json.dumps({"version": "1.3.73"}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
hm = json.loads((hdst / "update_manifest.json").read_text(encoding="utf-8"))
hm["version"] = hm["app_version"] = hm["runtime_version"] = "1.3.73"
hm.setdefault("notes", {}).update({
    "purpose": "Remaster profesional de Pacientes en espera: edad, última atención, procedimientos diferenciados con nombre real y protección de nuevos ya atendidos.",
    "previous_version": "1.3.72",
    "waiting_room_professional_remaster": True,
    "waiting_room_age": True,
    "waiting_room_last_attention": True,
    "procedure_visual_identity": True,
    "procedure_specific_name_supported": True,
    "signed_queue_reconciliation": True,
    "new_patient_duplicate_guard_by_signed_queue": True,
    "database_schema_changes": False,
    "patient_data_destructive_changes": False,
    "cloud_logic_unchanged_from_1_3_72": True,
    "lan_logic_unchanged_from_1_3_72": True,
})
(hdst / "update_manifest.json").write_text(json.dumps(hm, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

hs_path = root / "historia-clinica/launcher-v1/app-channel-source.json"
hs = json.loads(hs_path.read_text(encoding="utf-8"))
hs["appVersion"] = "1.3.73"
hs["notes"] = "Historia Clínica 1.3.73: sala de espera profesional con edad, última atención, procedimientos diferenciados y nombre específico; protege pacientes nuevos que ya tienen consulta firmada."
for item in hs["files"]:
    item["sourcePath"] = item["sourcePath"].replace("v1_3_72_waiting_opens_card", "v1_3_73_waiting_room_remaster")
hs_path.write_text(json.dumps(hs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# -----------------------------------------------------------------------------
# Recepción 4.6.5 — only enrich Historia handoff label
# -----------------------------------------------------------------------------
rsrc = root / "updates/v4_6_4_cleanup"
rdst = root / "updates/v4_6_5_historia_procedure_names"
if rdst.exists():
    shutil.rmtree(rdst)
shutil.copytree(rsrc, rdst)
rapp_path = rdst / "app.py"
rapp = rapp_path.read_text(encoding="utf-8")
rapp = replace_once(
    rapp,
    '''            patient_status = {
                "N": "Nuevo",
                "S": "Subsecuente",
            }.get(type_code, "")
            attention_type = "Consulta" if has_consultation else "Procedimiento"''',
    '''            patient_status = {
                "N": "Nuevo",
                "S": "Subsecuente",
            }.get(type_code, "")
            if has_consultation:
                attention_type = "Consulta"
            else:
                # v4.6.5: sólo enriquece la etiqueta administrativa enviada a Historia.
                _procedure_names = []
                for _procedure in procedures:
                    _name = " ".join(str(_procedure or "").split()).upper()
                    if _name and _name not in _procedure_names:
                        _procedure_names.append(_name)
                attention_type = "Procedimiento"
                if _procedure_names:
                    attention_type += " · " + " / ".join(_procedure_names)''',
    "Reception procedure handoff label",
)
rapp_path.write_text(rapp, encoding="utf-8")
(rdst / "recepcion-version.json").write_text(json.dumps({"version": "4.6.5"}, indent=2) + "\n", encoding="utf-8")
rm = json.loads((rdst / "update_manifest.json").read_text(encoding="utf-8"))
rm["version"] = rm["app_version"] = rm["runtime_version"] = "4.6.5"
rm.setdefault("notes", {}).update({
    "purpose": "Enriquece exclusivamente el handoff hacia Historia con el nombre real del procedimiento para la sala de espera.",
    "previous_version": "4.6.4",
    "billing_logic_changes": False,
    "azur_logic_changes": False,
    "whatsapp_logic_changes": False,
    "printing_changes": False,
    "procedure_pricing_logic_changes": False,
    "procedure_handoff_label_enriched": True,
    "database_schema_changes": False,
    "patient_data_changes": False,
    "patient_data_destructive_changes": False,
})
(rdst / "update_manifest.json").write_text(json.dumps(rm, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

rs_path = root / "launcher-v1/app-channel-source.json"
rs = json.loads(rs_path.read_text(encoding="utf-8"))
rs["appVersion"] = "4.6.5"
rs["notes"] = "Recepción 4.6.5: envía a Historia el nombre real del procedimiento en la etiqueta de handoff. No cambia facturación, AZUR, WhatsApp, precios, impresión ni datos."
for item in rs["files"]:
    item["sourcePath"] = item["sourcePath"].replace("v4_6_4_cleanup", "v4_6_5_historia_procedure_names")
rs_path.write_text(json.dumps(rs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Byte contracts for untouched files.
for name in ["historia_bridge.py", "historia_lan_transport.py", "static/runtime_keep.txt"]:
    if (rsrc / name).read_bytes() != (rdst / name).read_bytes():
        raise RuntimeError(f"unexpected Reception change: {name}")
for name in ["cloud_sync.py", "cloud_presence_patch.py", "lan_bridge.py", "documentos_clinicos.py", "requirements.txt", "static/doctor_icon.b64"]:
    if (hsrc / name).read_bytes() != (hdst / name).read_bytes():
        raise RuntimeError(f"unexpected Historia change: {name}")

compile(app_path.read_text(encoding="utf-8"), str(app_path), "exec")
compile(rapp_path.read_text(encoding="utf-8"), str(rapp_path), "exec")
print("GENERATED_OK")
