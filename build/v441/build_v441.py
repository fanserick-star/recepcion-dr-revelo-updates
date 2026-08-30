from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v440'
OUT = ROOT / 'updates' / 'v441'
VERSION = '4.4.1'
LAUNCHER_VERSION = '4.3.100-standalone-7'


def joined(prefix: str, n: int) -> str:
    parts = sorted(SRC.glob(prefix + '*'), key=lambda p: int(p.name.replace(prefix, '')))
    if len(parts) != n:
        raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(parts)}')
    return ''.join(p.read_text(encoding='utf-8') for p in parts)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_parts(text: str, prefix: str, n: int) -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob(prefix + '*'):
        p.unlink()
    step = math.ceil(len(text) / n)
    names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step], encoding='utf-8', newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names) != text:
        raise SystemExit('reconstrucción inválida '+prefix)
    return names


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontró {count}')
    return text.replace(old,new,1)


def replace_between(text: str, start: str, end: str, new: str, label: str) -> str:
    a=text.find(start)
    if a < 0: raise SystemExit(label+': inicio no encontrado')
    b=text.find(end,a+len(start))
    if b < 0: raise SystemExit(label+': fin no encontrado')
    return text[:a]+new+text[b:]


AUDIT_LOCAL = r'''def _workstation_label() -> str:
    raw = (os.getenv("RP_WORKSTATION_NAME") or os.getenv("COMPUTERNAME") or socket.gethostname() or "PC RECEPCION").strip()
    raw = re.sub(r"[^A-Za-z0-9 _.-]+", "", raw)[:60].strip()
    return raw.upper() or "PC RECEPCION"


def audit(db: Session, username_or_user, action: str, detail: str = ""):
    """Registra la acción en la base de trabajo y refleja la misma línea en SQLite.

    La copia local se hace DESPUÉS de que la transacción principal confirme, así
    abrir Actividad nunca necesita consultar Neon. No añade ninguna lectura a la nube.
    """
    username = getattr(username_or_user, "username", None) or str(username_or_user or "admin")
    clean = str(detail or "").strip()
    tagged = f"[PC:{_workstation_label()}] {clean}".strip()
    stamp = datetime.utcnow()
    db.add(Audit(ts=stamp, username=username, action=action, detail=tagged))
    try:
        if db.get_bind() is not local_engine:
            db.info.setdefault("rp_audit_local_mirror", []).append({
                "ts": stamp, "username": username, "action": action, "detail": tagged,
            })
    except Exception:
        pass


@event.listens_for(Session, "after_commit")
def _audit_after_commit_local_mirror(session):
    try:
        if session.get_bind() is local_engine:
            session.info.pop("rp_audit_local_mirror", None)
            return
    except Exception:
        return
    pending = session.info.pop("rp_audit_local_mirror", [])
    if not pending:
        return
    try:
        with LocalSessionLocal() as ldb:
            for row in pending:
                ldb.add(Audit(ts=row["ts"], username=row["username"], action=row["action"], detail=row["detail"]))
            ldb.commit()
    except Exception:
        pass


@event.listens_for(Session, "after_rollback")
def _audit_after_rollback_clear_local_mirror(session):
    session.info.pop("rp_audit_local_mirror", None)
'''


CAPTURE_LOCAL = r'''def _ops_capture_trash(db: Session, user, entity_type: str, entity_id: int, patient_id: Optional[int], label: str, snapshot: dict) -> TrashItem:
    """Guarda la Papelera únicamente en SQLite local.

    La eliminación clínica sigue usando la base principal como siempre, pero la
    red de seguridad no añade INSERTs ni lecturas a Neon.
    """
    username = getattr(user, "username", None) or "admin"
    with LocalSessionLocal() as ldb:
        _ops_ensure_trash_table(ldb)
        item = TrashItem(
            entity_type=str(entity_type), entity_id=int(entity_id),
            patient_id=int(patient_id) if patient_id else None,
            label=str(label or entity_type)[:240],
            snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=_ops_json_value),
            deleted_by=username, origin=_workstation_label(),
        )
        ldb.add(item)
        ldb.commit(); ldb.refresh(item)
        return item


def _ops_discard_local_trash(trash_id: int) -> None:
    try:
        with LocalSessionLocal() as ldb:
            item=ldb.get(TrashItem, int(trash_id))
            if item:
                ldb.delete(item); ldb.commit()
    except Exception:
        pass


'''


SAFE_DELETE = r'''@app.delete("/api/safety/patients/{pid}")
def ops_safe_delete_patient(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    item = _ops_capture_patient(db, user, p)
    try:
        result = delete_patient(pid, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/visits/{visit_id}")
def ops_safe_delete_visit(visit_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Visit, visit_id)
    if not v:
        raise HTTPException(404, "Atención no encontrada")
    item = _ops_capture_visit(db, user, v)
    try:
        result = delete_visit(visit_id, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/appointments/{appointment_id}")
def ops_safe_delete_appointment(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    item = _ops_capture_appointment(db, user, a)
    try:
        result = agenda_delete(appointment_id, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/unlinked/{item_id}")
def ops_safe_delete_unlinked(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    staged = db.get(ConfirmafyAgendaItem, item_id)
    if not staged:
        raise HTTPException(404, "La cita ya no existe")
    item = _ops_capture_staged(db, user, staged)
    try:
        result = agenda_delete_unlinked(item_id, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


'''


TRASH_LIST = r'''@app.get("/api/ops/trash")
def ops_trash(include_restored: bool = False, limit: int = 100, user: User = Depends(current_user)):
    """Lectura estrictamente local: abrir Papelera jamás despierta Neon."""
    with LocalSessionLocal() as db:
        _ops_ensure_trash_table(db)
        cutoff = datetime.utcnow() - timedelta(days=TRASH_RETENTION_DAYS)
        try:
            old = list(db.scalars(select(TrashItem).where(TrashItem.deleted_at < cutoff)))
            for item in old:
                db.delete(item)
            if old:
                db.commit()
        except Exception:
            db.rollback()
        stmt = select(TrashItem)
        if not include_restored:
            stmt = stmt.where(TrashItem.restored_at.is_(None))
        stmt = stmt.order_by(TrashItem.deleted_at.desc(), TrashItem.id.desc()).limit(min(max(int(limit or 100),1),250))
        return [_ops_trash_dict(x) for x in db.scalars(stmt)]


'''


RESTORE_LOCAL = r'''@app.post("/api/ops/trash/{trash_id}/restore")
def ops_restore_trash(trash_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Lee el snapshot de SQLite y solo toca Neon si realmente se pide Restaurar."""
    with LocalSessionLocal() as ldb:
        _ops_ensure_trash_table(ldb)
        item = ldb.get(TrashItem, trash_id)
        if not item:
            raise HTTPException(404, "Ese elemento ya no está en la Papelera")
        if item.restored_at:
            return {"ok": True, "already_restored": True, "item": _ops_trash_dict(item)}
        try:
            snapshot = json.loads(item.snapshot_json or "{}")
        except Exception:
            raise HTTPException(500, "La copia de recuperación está dañada")
        entity_type=item.entity_type; entity_id=int(item.entity_id); label=item.label

    restored = None
    if entity_type == "patient":
        restored = _ops_restore_patient(db, snapshot)
    elif entity_type == "visit":
        restored = _ops_restore_visit(db, snapshot.get("visit") or {})
    elif entity_type == "appointment":
        restored = _ops_restore_appointment(db, snapshot.get("appointment") or {})
    elif entity_type == "staged_appointment":
        snap = snapshot.get("staged") or {}
        sid = int(snap["id"])
        restored = db.get(ConfirmafyAgendaItem, sid)
        if not restored:
            restored = ConfirmafyAgendaItem(
                id=sid, nombre=snap.get("nombre") or "PACIENTE", celular=snap.get("celular"),
                fecha=_ops_parse_date(snap.get("fecha")), hora=str(snap.get("hora") or "")[:5],
                duracion=int(snap.get("duracion") or 20), source_hash=snap.get("source_hash") or f"restored:{sid}",
                created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
            )
            db.add(restored); db.flush()
    else:
        raise HTTPException(400, "Tipo de elemento no recuperable")

    audit(db, user, "restaurar_desde_papelera", f"{entity_type} {entity_id}: {label}; papelera local {trash_id}")
    db.commit()
    try:
        if entity_type == "patient" and isinstance(restored, Patient):
            mirror_patient_to_local(restored)
            for v in db.scalars(select(Visit).where(Visit.patient_id == restored.id)):
                mirror_visit_to_local(v)
            for a in db.scalars(select(Appointment).where(Appointment.patient_id == restored.id)):
                mirror_appointment_to_local(a)
        elif entity_type == "visit" and isinstance(restored, Visit):
            mirror_visit_to_local(restored)
            billing=db.scalar(select(BillingRecord).where(BillingRecord.visit_id == restored.id))
            if billing: mirror_billing_to_local(billing)
        elif entity_type == "appointment" and isinstance(restored, Appointment):
            mirror_appointment_to_local(restored)
        elif entity_type == "staged_appointment" and isinstance(restored, ConfirmafyAgendaItem):
            mirror_confirmafy_agenda_local(restored)
    except Exception:
        pass
    with LocalSessionLocal() as ldb:
        local_item=ldb.get(TrashItem, trash_id)
        if local_item:
            local_item.restored_at=datetime.utcnow(); local_item.restored_by=getattr(user,"username",None) or "admin"
            ldb.commit(); result_item=_ops_trash_dict(local_item)
        else:
            result_item={"id":trash_id,"entity_type":entity_type,"entity_id":entity_id,"label":label}
    return {"ok": True, "item": result_item, "entity_type": entity_type, "entity_id": entity_id}


@app.delete("/api/ops/trash/{trash_id}")
def ops_delete_trash_forever(trash_id: int, user: User = Depends(current_user)):
    """Vaciar Papelera es una operación SQLite; no consulta ni escribe Neon."""
    with LocalSessionLocal() as db:
        _ops_ensure_trash_table(db)
        item = db.get(TrashItem, trash_id)
        if not item:
            raise HTTPException(404, "Ese elemento ya no está en la Papelera")
        db.delete(item); db.commit()
    return {"ok": True}


'''


ACTIVITY_LOCAL = r'''@app.get("/api/ops/activity")
def ops_activity(limit: int = 120, q: str = "", user: User = Depends(current_user)):
    """Actividad local-first estricta: esta pantalla nunca consulta Neon."""
    lim = min(max(int(limit or 120), 1), 300)
    with LocalSessionLocal() as db:
        stmt = select(Audit)
        raw = str(q or "").strip()
        if raw:
            pattern = f"%{raw}%"
            stmt = stmt.where(or_(Audit.action.ilike(pattern), Audit.detail.ilike(pattern), Audit.username.ilike(pattern)))
        stmt = stmt.order_by(Audit.ts.desc(), Audit.id.desc()).limit(lim)
        out=[]
        for row in db.scalars(stmt):
            detail = str(row.detail or "")
            origin = "PC NO REGISTRADA"
            match = re.match(r"^\[PC:([^\]]+)\]\s*(.*)$", detail, flags=re.S)
            if match:
                origin = match.group(1).strip() or origin
                detail = match.group(2).strip()
            out.append({"id": row.id, "ts": row.ts, "username": row.username, "action": row.action, "detail": detail, "origin": origin})
        return out


'''


FIX_CSS = r'''/* v4.4.1 — correcciones operativas y lectura local estricta */
.patient-name-button{appearance:none!important;background:transparent!important;border:0!important;padding:0!important;margin:0!important;color:inherit!important;font:inherit!important;font-weight:inherit!important;text-align:left!important;cursor:pointer!important;box-shadow:none!important;min-height:0!important;line-height:inherit!important}
.patient-name-button:hover{text-decoration:underline!important;color:#245f98!important}
.patient-quick-drawer{left:auto!important;right:0!important;bottom:auto!important;max-width:94vw!important;margin:0!important;padding:0!important}
.ops-diagnostic-panel{display:none!important}
.ops-diagnostic-integrated{margin-top:12px!important;padding-top:12px!important;border-top:1px solid #e1e8ef!important}
.ops-diagnostic-integrated .diag-actions{display:flex!important;gap:9px!important;align-items:center!important;margin-top:0!important}
.ops-diagnostic-integrated .diag-actions button{min-height:42px!important;padding:10px 16px!important;font-size:12px!important;font-weight:900!important;border-radius:10px!important}
.ops-diagnostic-integrated .ops-diagnostic-grid{margin-top:11px!important}
.ops-diagnostic-integrated .diag-item{padding:11px 12px!important}
.ops-diagnostic-integrated .diag-copy b{font-size:11px!important}.ops-diagnostic-integrated .diag-copy span{font-size:10px!important;line-height:1.35!important}
'''


def patch_static_app(js: str) -> str:
    old="""  return `<div class=\"patient-name-line\"><a href=\"#\" onclick=\"openPatient(${p.id},'home');return false\">${esc(p.nombre||'')}</a>${home?n:''}${home?'':dataWarning(p,true)}</div>`;"""
    new="""  return `<div class=\"patient-name-line\"><button type=\"button\" class=\"patient-name-button\" onclick=\"openPatient(${p.id},'home')\">${esc(p.nombre||'')}</button>${home?n:''}${home?'':dataWarning(p,true)}</div>`;"""
    js=replace_once(js,old,new,'nombre paciente sin href')
    return js


def patch_app(s: str) -> str:
    s=replace_once(s,'APP_VERSION = "4.4.0"','APP_VERSION = "4.4.1"','versión backend')
    s=replace_once(s,"const VERSION=\\'4.4.0\\';","const VERSION=\\'4.4.1\\';",'versión visual')
    s=replace_once(s,'TRASH_RETENTION_DAYS = 30','TRASH_RETENTION_DAYS = 7','retención papelera')

    old_audit='''def _workstation_label() -> str:\n    raw = (os.getenv("RP_WORKSTATION_NAME") or os.getenv("COMPUTERNAME") or socket.gethostname() or "PC RECEPCION").strip()\n    raw = re.sub(r"[^A-Za-z0-9 _.-]+", "", raw)[:60].strip()\n    return raw.upper() or "PC RECEPCION"\n\n\ndef audit(db: Session, username_or_user, action: str, detail: str = ""):\n    username = getattr(username_or_user, "username", None) or str(username_or_user or "admin")\n    clean = str(detail or "").strip()\n    tagged = f"[PC:{_workstation_label()}] {clean}".strip()\n    db.add(Audit(username=username, action=action, detail=tagged))\n'''
    s=replace_once(s,old_audit,AUDIT_LOCAL,'audit local mirror')

    s=replace_between(s,'def _ops_capture_trash(db: Session, user, entity_type: str, entity_id: int, patient_id: Optional[int], label: str, snapshot: dict) -> TrashItem:',
                      'def _ops_capture_patient(db: Session, user, p: Patient) -> TrashItem:',CAPTURE_LOCAL+'def _ops_capture_patient(db: Session, user, p: Patient) -> TrashItem:','papelera local')
    s=replace_between(s,'@app.delete("/api/safety/patients/{pid}")','@app.get("/api/ops/trash")',SAFE_DELETE+'@app.get("/api/ops/trash")','borrado seguro')
    s=replace_between(s,'@app.get("/api/ops/trash")','@app.post("/api/ops/trash/{trash_id}/restore")',TRASH_LIST+'@app.post("/api/ops/trash/{trash_id}/restore")','listado papelera local')
    s=replace_between(s,'@app.post("/api/ops/trash/{trash_id}/restore")','@app.get("/api/ops/activity")',RESTORE_LOCAL+'@app.get("/api/ops/activity")','restauración local')
    s=replace_between(s,'@app.get("/api/ops/activity")','@app.get("/api/patients/{pid}/quick")',ACTIVITY_LOCAL+'@app.get("/api/patients/{pid}/quick")','actividad local')

    # v4.4.1: retirar por completo la Agenda inteligente de la interfaz y del arranque.
    s=s.replace('}ensurePatientDrawer();ensureSmartAgendaHost();ensureDiagnosticsCard()}','}ensurePatientDrawer();ensureDiagnosticsCard()}',1)
    smart_tail="window.loadSmartAgenda=loadSmartAgenda;const oldLoadAgenda=window.loadAgenda;if(typeof oldLoadAgenda==='function')window.loadAgenda=async function(...args){const r=await oldLoadAgenda(...args);setTimeout(loadSmartAgenda,0);return r};"
    s=replace_once(s,smart_tail,"window.loadSmartAgenda=async()=>{};",'desactivar agenda inteligente')
    s=replace_once(s,"if(id==='agenda')setTimeout(loadSmartAgenda,0);",'', 'show sin agenda inteligente')
    s=replace_once(s,'function init(){ensureOpsUI();maybeDailyBrief()}','function init(){ensureOpsUI()}', 'sin resumen diario')

    # Papelera de una semana también en todos los textos visibles.
    s=s.replace('30 días','7 días')

    # Evitar que el panel lateral herede las reglas globales del <aside> principal.
    s=replace_once(s,"<aside id=\"patientQuickDrawer\" class=\"patient-quick-drawer\" aria-hidden=\"true\"><div id=\"patientQuickContent\"></div></aside>",
                      "<div id=\"patientQuickDrawer\" class=\"patient-quick-drawer\" aria-hidden=\"true\"><div id=\"patientQuickContent\"></div></div>",'drawer div')

    # Integrar Revisar sistema dentro del Resumen de datos existente, sin duplicar tarjetas.
    diag_start=' function ensureDiagnosticsCard(){'
    diag_end="let lastSafeDiagnostic='';"
    new_diag=r''' function ensureDiagnosticsCard(){const sys=document.querySelector('[data-config-section="sistema"]'),panel=sys?.querySelector('.system-status-panel');if(!panel||panel.querySelector('#opsDiagnosticControls'))return;panel.querySelector('#opsDiagnosticPanel')?.remove();const head=panel.querySelector('.config-panel-head h3');if(head)head.textContent='Resumen de datos y servicios';const grid=panel.querySelector('#systemStatusGrid');const wrap=document.createElement('div');wrap.id='opsDiagnosticControls';wrap.className='ops-diagnostic-integrated';wrap.innerHTML='<div class="diag-actions"><button class="primary-soft" onclick="runOpsDiagnostics()">🔧 Revisar sistema</button><button id="copyOpsDiagnosticsBtn" class="hidden" onclick="copyOpsDiagnostics()">Copiar diagnóstico</button></div><div id="opsDiagnosticGrid" class="ops-diagnostic-grid hidden"></div>';if(grid)grid.insertAdjacentElement('afterend',wrap);else panel.appendChild(wrap)}'''
    s=replace_between(s,diag_start,diag_end,new_diag+diag_end,'diagnóstico integrado')
    s=replace_once(s,"async function runOpsDiagnostics(){const box=$('#opsDiagnosticGrid');if(!box)return;box.innerHTML='<div class=\"muted\">Comprobando servicios…</div>';",
                      "async function runOpsDiagnostics(){const box=$('#opsDiagnosticGrid');if(!box)return;box.classList.remove('hidden');box.innerHTML='<div class=\"muted\">Comprobando servicios…</div>';",'mostrar diagnóstico')

    overlay_marker='@app.get("/v460/overlay.css")'
    inject='V441_FIX_CSS = r"""'+FIX_CSS+'"""\nV460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V441_FIX_CSS\n\n'+overlay_marker
    s=replace_once(s,overlay_marker,inject,'css v441')

    compile(s,'app.py','exec')
    required=['APP_VERSION = "4.4.1"','TRASH_RETENTION_DAYS = 7','Actividad local-first estricta','Lectura estrictamente local','Guarda la Papelera únicamente en SQLite local','rp_audit_local_mirror','Resumen de datos y servicios','patient-quick-drawer','V441_FIX_CSS','/api/ops/diagnostics','V43104_ALERT_JS','Procedimientos y servicios',"price.textContent='$40.00'",'Emitir por lotes']
    for token in required:
        if token not in s: raise SystemExit('app falta '+token)
    forbidden=['setTimeout(loadSmartAgenda,0)','function init(){ensureOpsUI();maybeDailyBrief()}','durante 30 días','TRASH_RETENTION_DAYS = 30']
    for token in forbidden:
        if token in s: raise SystemExit('app conserva '+token)
    return s


def main() -> None:
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    (OUT/'static').mkdir(parents=True,exist_ok=True)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8')
    static_app=patch_static_app((SRC/'static'/'app.js').read_text(encoding='utf-8'))
    (OUT/'static'/'index.html').write_text(index,encoding='utf-8',newline='')
    (OUT/'static'/'app.js').write_text(static_app,encoding='utf-8',newline='')
    ab,lb,ib,jb=app.encode(),launcher.encode(),index.encode(),static_app.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','static/app.js','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v441/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.4.1: corrige ficha rápida, elimina Agenda inteligente, integra Revisar sistema, reduce Papelera a 7 días y fuerza Actividad/Papelera/Ficha rápida a SQLite local para no consultar Neon.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'static/app.js','url':base+'static/app.js','sha256':sha(jb),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb),sha(jb))

if __name__=='__main__': main()
