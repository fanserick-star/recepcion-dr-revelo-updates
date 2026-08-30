from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v43104'
OUT = ROOT / 'updates' / 'v440'
VERSION = '4.4.0'
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


TRASH_MODEL = r'''

class TrashItem(Base):
    """Papelera recuperable para acciones borradas desde la interfaz.

    El snapshot se guarda como JSON de texto para funcionar igual en SQLite y
    PostgreSQL. No contiene claves, tokens ni configuración del programa.
    """
    __tablename__ = "trash_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    label: Mapped[str] = mapped_column(String(240))
    snapshot_json: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    deleted_by: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(120), default="PC RECEPCION")
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    restored_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

'''

AUDIT_REPLACEMENT = r'''def _workstation_label() -> str:
    raw = (os.getenv("RP_WORKSTATION_NAME") or os.getenv("COMPUTERNAME") or socket.gethostname() or "PC RECEPCION").strip()
    raw = re.sub(r"[^A-Za-z0-9 _.-]+", "", raw)[:60].strip()
    return raw.upper() or "PC RECEPCION"


def audit(db: Session, username_or_user, action: str, detail: str = ""):
    username = getattr(username_or_user, "username", None) or str(username_or_user or "admin")
    clean = str(detail or "").strip()
    tagged = f"[PC:{_workstation_label()}] {clean}".strip()
    db.add(Audit(username=username, action=action, detail=tagged))
'''

BACKEND_OPS = r'''

# ---------------------------------------------------------------------------
# v4.4.0 — Centro operativo: Papelera, Actividad, ficha rápida y Agenda inteligente
# ---------------------------------------------------------------------------

TRASH_RETENTION_DAYS = 30


def _ops_json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _ops_parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _ops_parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _ops_ensure_trash_table(db: Session) -> None:
    try:
        TrashItem.__table__.create(bind=db.get_bind(), checkfirst=True)
    except Exception:
        pass


def _ops_patient_snapshot(p: Patient) -> dict:
    return {
        "id": int(p.id), "cedula": p.cedula, "nombre": p.nombre,
        "fecha_nacimiento": _ops_json_value(p.fecha_nacimiento), "celular": p.celular,
        "correo": p.correo, "lugar": p.lugar, "notas": p.notas,
        "created_at": _ops_json_value(p.created_at),
    }


def _ops_visit_snapshot(db: Session, v: Visit) -> dict:
    billing = db.scalar(select(BillingRecord).where(BillingRecord.visit_id == v.id))
    out = {
        "id": int(v.id), "patient_id": int(v.patient_id), "fecha": _ops_json_value(v.fecha),
        "tipo": v.tipo, "procedimiento": v.procedimiento, "valor": float(v.valor or 0),
        "observacion": v.observacion, "source_row": v.source_row,
        "created_at": _ops_json_value(v.created_at),
    }
    if billing:
        out["billing"] = {
            "id": int(billing.id), "visit_id": int(billing.visit_id), "estado": billing.estado,
            "numero_factura": billing.numero_factura,
            "approved_at": _ops_json_value(billing.approved_at),
            "emitted_at": _ops_json_value(billing.emitted_at),
            "created_at": _ops_json_value(billing.created_at),
        }
    return out


def _ops_appointment_snapshot(a: Appointment) -> dict:
    return {
        "id": int(a.id), "patient_id": int(a.patient_id), "fecha": _ops_json_value(a.fecha),
        "hora": a.hora, "duracion": int(a.duracion or 20), "nota": a.nota,
        "estado": a.estado, "origen": a.origen,
        "exported_at": _ops_json_value(a.exported_at), "loaded_at": _ops_json_value(a.loaded_at),
        "created_at": _ops_json_value(a.created_at), "updated_at": _ops_json_value(a.updated_at),
    }


def _ops_staged_snapshot(a: ConfirmafyAgendaItem) -> dict:
    return {
        "id": int(a.id), "nombre": a.nombre, "celular": a.celular,
        "fecha": _ops_json_value(a.fecha), "hora": a.hora, "duracion": int(a.duracion or 20),
        "source_hash": a.source_hash, "created_at": _ops_json_value(a.created_at),
    }


def _ops_capture_trash(db: Session, user, entity_type: str, entity_id: int, patient_id: Optional[int], label: str, snapshot: dict) -> TrashItem:
    _ops_ensure_trash_table(db)
    username = getattr(user, "username", None) or "admin"
    item = TrashItem(
        entity_type=str(entity_type), entity_id=int(entity_id), patient_id=int(patient_id) if patient_id else None,
        label=str(label or entity_type)[:240], snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=_ops_json_value),
        deleted_by=username, origin=_workstation_label(),
    )
    db.add(item)
    db.flush()
    audit(db, user, "guardar_en_papelera", f"{entity_type} {entity_id}: {label}; papelera {item.id}")
    return item


def _ops_capture_patient(db: Session, user, p: Patient) -> TrashItem:
    visits = list(db.scalars(select(Visit).where(Visit.patient_id == p.id).order_by(Visit.id)))
    appointments = list(db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.id)))
    pref = db.scalar(select(BillingPreference).where(BillingPreference.patient_id == p.id))
    snapshot = {
        "patient": _ops_patient_snapshot(p),
        "visits": [_ops_visit_snapshot(db, v) for v in visits],
        "appointments": [_ops_appointment_snapshot(a) for a in appointments],
        "billing_preference": ({
            "id": int(pref.id), "patient_id": int(pref.patient_id), "enabled": int(pref.enabled or 0),
            "identificacion": pref.identificacion, "nombre": pref.nombre, "direccion": pref.direccion,
            "telefono": pref.telefono, "correo": pref.correo, "updated_at": _ops_json_value(pref.updated_at),
        } if pref else None),
    }
    return _ops_capture_trash(db, user, "patient", p.id, p.id, p.nombre, snapshot)


def _ops_capture_visit(db: Session, user, v: Visit) -> TrashItem:
    p = db.get(Patient, v.patient_id)
    service = str(v.procedimiento or "CONSULTA")
    label = f"{p.nombre if p else 'Paciente'} · {service} · {v.fecha.isoformat()}"
    return _ops_capture_trash(db, user, "visit", v.id, v.patient_id, label, {"visit": _ops_visit_snapshot(db, v)})


def _ops_capture_appointment(db: Session, user, a: Appointment) -> TrashItem:
    p = db.get(Patient, a.patient_id)
    label = f"{p.nombre if p else 'Paciente'} · {a.fecha.isoformat()} {a.hora}"
    return _ops_capture_trash(db, user, "appointment", a.id, a.patient_id, label, {"appointment": _ops_appointment_snapshot(a)})


def _ops_capture_staged(db: Session, user, a: ConfirmafyAgendaItem) -> TrashItem:
    label = f"{a.nombre} · {a.fecha.isoformat()} {a.hora}"
    return _ops_capture_trash(db, user, "staged_appointment", a.id, None, label, {"staged": _ops_staged_snapshot(a)})


def _ops_trash_dict(item: TrashItem) -> dict:
    now = datetime.utcnow()
    age = max(0, (now - item.deleted_at).days) if item.deleted_at else 0
    return {
        "id": item.id, "entity_type": item.entity_type, "entity_id": item.entity_id,
        "patient_id": item.patient_id, "label": item.label,
        "deleted_at": item.deleted_at, "deleted_by": item.deleted_by, "origin": item.origin,
        "restored_at": item.restored_at, "restored_by": item.restored_by,
        "days_left": max(0, TRASH_RETENTION_DAYS - age),
    }


def _ops_restore_visit(db: Session, snap: dict) -> Visit:
    vid = int(snap["id"])
    existing = db.get(Visit, vid)
    if existing:
        return existing
    if not db.get(Patient, int(snap["patient_id"])):
        raise HTTPException(409, "Primero restaura la ficha del paciente asociada.")
    v = Visit(
        id=vid, patient_id=int(snap["patient_id"]), fecha=_ops_parse_date(snap.get("fecha")),
        tipo=str(snap.get("tipo") or "S")[:1], procedimiento=snap.get("procedimiento"),
        valor=snap.get("valor") or 0, observacion=snap.get("observacion"),
        source_row=snap.get("source_row"), created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
    )
    db.add(v); db.flush()
    billing = snap.get("billing") or None
    if billing and not db.scalar(select(BillingRecord).where(BillingRecord.visit_id == vid)):
        db.add(BillingRecord(
            id=int(billing["id"]), visit_id=vid, estado=billing.get("estado") or "PENDIENTE",
            numero_factura=billing.get("numero_factura"), approved_at=_ops_parse_datetime(billing.get("approved_at")),
            emitted_at=_ops_parse_datetime(billing.get("emitted_at")),
            created_at=_ops_parse_datetime(billing.get("created_at")) or datetime.utcnow(),
        ))
    return v


def _ops_restore_appointment(db: Session, snap: dict) -> Appointment:
    aid = int(snap["id"])
    existing = db.get(Appointment, aid)
    if existing:
        return existing
    if not db.get(Patient, int(snap["patient_id"])):
        raise HTTPException(409, "Primero restaura la ficha del paciente asociada.")
    a = Appointment(
        id=aid, patient_id=int(snap["patient_id"]), fecha=_ops_parse_date(snap.get("fecha")),
        hora=str(snap.get("hora") or "")[:5], duracion=int(snap.get("duracion") or 20),
        nota=snap.get("nota"), estado=snap.get("estado") or "PENDIENTE", origen=snap.get("origen") or "RECEPCION",
        exported_at=_ops_parse_datetime(snap.get("exported_at")), loaded_at=_ops_parse_datetime(snap.get("loaded_at")),
        created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
        updated_at=_ops_parse_datetime(snap.get("updated_at")) or datetime.utcnow(),
    )
    db.add(a); db.flush()
    return a


def _ops_restore_patient(db: Session, snapshot: dict) -> Patient:
    snap = snapshot.get("patient") or {}
    pid = int(snap["id"])
    if db.get(Patient, pid):
        raise HTTPException(409, "La ficha del paciente ya existe. No se duplicó nada.")
    p = Patient(
        id=pid, cedula=snap.get("cedula"), nombre=snap.get("nombre") or "PACIENTE RESTAURADO",
        fecha_nacimiento=_ops_parse_date(snap.get("fecha_nacimiento")), celular=snap.get("celular"),
        correo=snap.get("correo"), lugar=snap.get("lugar"), notas=snap.get("notas"),
        created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
    )
    db.add(p); db.flush()
    restored_visits=[]; restored_apps=[]
    for v in snapshot.get("visits") or []:
        restored_visits.append(_ops_restore_visit(db, v))
    for a in snapshot.get("appointments") or []:
        restored_apps.append(_ops_restore_appointment(db, a))
    pref = snapshot.get("billing_preference") or None
    if pref and not db.scalar(select(BillingPreference).where(BillingPreference.patient_id == pid)):
        db.add(BillingPreference(
            id=int(pref["id"]), patient_id=pid, enabled=int(pref.get("enabled") or 0),
            identificacion=pref.get("identificacion"), nombre=pref.get("nombre"), direccion=pref.get("direccion"),
            telefono=pref.get("telefono"), correo=pref.get("correo") or "",
            updated_at=_ops_parse_datetime(pref.get("updated_at")) or datetime.utcnow(),
        ))
    return p


@app.delete("/api/safety/patients/{pid}")
def ops_safe_delete_patient(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    item = _ops_capture_patient(db, user, p)
    result = delete_patient(pid, db, user)
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/visits/{visit_id}")
def ops_safe_delete_visit(visit_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Visit, visit_id)
    if not v:
        raise HTTPException(404, "Atención no encontrada")
    item = _ops_capture_visit(db, user, v)
    result = delete_visit(visit_id, db, user)
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/appointments/{appointment_id}")
def ops_safe_delete_appointment(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    item = _ops_capture_appointment(db, user, a)
    result = agenda_delete(appointment_id, db, user)
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/unlinked/{item_id}")
def ops_safe_delete_unlinked(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    staged = db.get(ConfirmafyAgendaItem, item_id)
    if not staged:
        raise HTTPException(404, "La cita ya no existe")
    item = _ops_capture_staged(db, user, staged)
    result = agenda_delete_unlinked(item_id, db, user)
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.get("/api/ops/trash")
def ops_trash(include_restored: bool = False, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
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


@app.post("/api/ops/trash/{trash_id}/restore")
def ops_restore_trash(trash_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _ops_ensure_trash_table(db)
    item = db.get(TrashItem, trash_id)
    if not item:
        raise HTTPException(404, "Ese elemento ya no está en la Papelera")
    if item.restored_at:
        return {"ok": True, "already_restored": True, "item": _ops_trash_dict(item)}
    try:
        snapshot = json.loads(item.snapshot_json or "{}")
    except Exception:
        raise HTTPException(500, "La copia de recuperación está dañada")
    restored = None
    if item.entity_type == "patient":
        restored = _ops_restore_patient(db, snapshot)
    elif item.entity_type == "visit":
        restored = _ops_restore_visit(db, snapshot.get("visit") or {})
    elif item.entity_type == "appointment":
        restored = _ops_restore_appointment(db, snapshot.get("appointment") or {})
    elif item.entity_type == "staged_appointment":
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
    item.restored_at = datetime.utcnow(); item.restored_by = getattr(user, "username", None) or "admin"
    audit(db, user, "restaurar_desde_papelera", f"{item.entity_type} {item.entity_id}: {item.label}; papelera {item.id}")
    db.commit()
    try:
        if item.entity_type == "patient" and isinstance(restored, Patient):
            mirror_patient_to_local(restored)
            for v in db.scalars(select(Visit).where(Visit.patient_id == restored.id)):
                mirror_visit_to_local(v)
            for a in db.scalars(select(Appointment).where(Appointment.patient_id == restored.id)):
                mirror_appointment_to_local(a)
        elif item.entity_type == "visit" and isinstance(restored, Visit):
            mirror_visit_to_local(restored)
        elif item.entity_type == "appointment" and isinstance(restored, Appointment):
            mirror_appointment_to_local(restored)
        elif item.entity_type == "staged_appointment" and isinstance(restored, ConfirmafyAgendaItem):
            mirror_confirmafy_agenda_local(restored)
    except Exception:
        pass
    return {"ok": True, "item": _ops_trash_dict(item), "entity_type": item.entity_type, "entity_id": item.entity_id}


@app.delete("/api/ops/trash/{trash_id}")
def ops_delete_trash_forever(trash_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _ops_ensure_trash_table(db)
    item = db.get(TrashItem, trash_id)
    if not item:
        raise HTTPException(404, "Ese elemento ya no está en la Papelera")
    label = item.label
    audit(db, user, "vaciar_elemento_papelera", f"Papelera {trash_id}: {label}")
    db.delete(item); db.commit()
    return {"ok": True}


@app.get("/api/ops/activity")
def ops_activity(limit: int = 120, q: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    lim = min(max(int(limit or 120), 1), 300)
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


@app.get("/api/patients/{pid}/quick")
def ops_patient_quick(pid: int, user: User = Depends(current_user)):
    with LocalSessionLocal() as db:
        p = db.get(Patient, pid)
        if not p:
            raise HTTPException(404, "Paciente no encontrado")
        visits = list(db.scalars(select(Visit).where(Visit.patient_id == pid).order_by(Visit.fecha.desc(), Visit.id.desc()).limit(5)))
        visit_count = int(db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == pid)) or 0)
        total_value = float(db.scalar(select(func.coalesce(func.sum(Visit.valor), 0)).where(Visit.patient_id == pid)) or 0)
        next_app = db.scalar(select(Appointment).where(Appointment.patient_id == pid, Appointment.fecha >= date.today(), Appointment.estado != "NO_ASISTIRA").order_by(Appointment.fecha.asc(), Appointment.hora.asc(), Appointment.id.asc()).limit(1))
        missing=[]
        if not str(p.cedula or "").strip(): missing.append("cédula")
        if not str(p.celular or "").strip(): missing.append("celular")
        if not str(p.correo or "").strip(): missing.append("correo")
        if patient_name_word_count(p.nombre) < 4: missing.append("nombre incompleto")
        return {"patient": p_dict(p), "visit_count": visit_count, "total_value": total_value, "last_visit": v_dict(visits[0]) if visits else None, "recent_visits": [v_dict(v) for v in visits], "next_appointment": appointment_dict(next_app) if next_app else None, "missing": missing}


def _ops_smart_target(value: Optional[date]) -> date:
    d = value or date.today()
    if d.weekday() in {3,4,5}:
        return d
    for step in range(1,8):
        n = d + timedelta(days=step)
        if n.weekday() in {3,4,5}:
            return n
    return d


@app.get("/api/ops/agenda-smart")
def ops_agenda_smart(fecha: Optional[date] = None, user: User = Depends(current_user)):
    target = _ops_smart_target(fecha)
    with LocalSessionLocal() as db:
        linked = db.execute(select(Appointment, Patient).join(Patient).where(Appointment.fecha == target, Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN).order_by(Appointment.hora.asc(), Appointment.id.asc())).all()
        staged = [x for x in db.scalars(select(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.fecha == target).order_by(ConfirmafyAgendaItem.hora.asc(), ConfirmafyAgendaItem.id.asc())) if not str(x.source_hash or "").startswith("mobile:whatsapp-cloud-test:")]
        attended_ids = {int(x) for x in db.scalars(select(Visit.patient_id).where(Visit.fecha == target)).all()}
        current_minutes = datetime.now().hour*60 + datetime.now().minute
        is_today = target == date.today()
        pending=[]; new_count=0; subsequent_count=0; incomplete_today=0
        for a,p in linked:
            prior = int(db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == p.id, Visit.fecha < target)) or 0)
            if prior: subsequent_count += 1
            else: new_count += 1
            if not p.cedula or not p.celular or not p.correo or patient_name_word_count(p.nombre) < 4:
                incomplete_today += 1
            if int(p.id) in attended_ids or str(a.estado or "").upper() == "NO_ASISTIRA":
                continue
            try:
                hh,mm=[int(x) for x in str(a.hora)[:5].split(':')]; minutes=hh*60+mm
            except Exception:
                minutes=9999
            pending.append({"id":a.id,"patient_id":p.id,"name":p.nombre,"time":a.hora,"minutes":minutes,"state":a.estado})
        next_row = next((x for x in pending if (not is_today or x["minutes"] >= current_minutes)), None)
        late = [x for x in pending if is_today and x["minutes"] + 20 < current_minutes]
        try:
            slot_data = agenda_slots(fecha=target, exclude_id=None, user=user)
            free_slots = [str(x.get("time") or "")[:5] for x in (slot_data.get("slots") or []) if x.get("available")][:8]
        except Exception:
            free_slots = []
        actual_visits = list(db.scalars(select(Visit).where(Visit.fecha == target)))
        procedures_done = sum(1 for v in actual_visits if is_procedure(v))
        return {"date": target, "is_today": is_today, "total": len(linked)+len(staged), "linked": len(linked), "unlinked": len(staged), "new": new_count, "subsequent": subsequent_count, "procedures_done": procedures_done, "attended": len(attended_ids), "late_count": len(late), "late": late[:4], "next": next_row, "free_slots": free_slots, "incomplete_today": incomplete_today}


@app.get("/api/ops/diagnostics")
def ops_diagnostics(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta comprobación solo puede ejecutarse desde la PC de Recepción")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    probes = {"local": _probe_local_service, "neon": _probe_neon_service, "azur": _probe_azur_service, "whatsapp": _probe_whatsapp_service, "mensajes": _probe_messages_service, "agenda": _probe_agenda_service, "updates": _probe_updates_service}
    services={}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="rp-diagnostico") as pool:
        futures={pool.submit(fn):key for key,fn in probes.items()}
        for future in as_completed(futures):
            key=futures[future]
            try: services[key]=future.result()
            except Exception as exc: services[key]={"name":key,"status":"ERROR","detail":str(exc)[:180]}
    safe_lines=[]
    for key in ("local","neon","azur","whatsapp","mensajes","agenda","updates"):
        item=services.get(key) or {}
        safe_lines.append(f"{item.get('name') or key}: {item.get('status') or item.get('state') or 'SIN DATOS'}")
    return {"version":APP_VERSION,"workstation":_workstation_label(),"services":services,"safe_text":f"Recepción v{APP_VERSION} | "+" | ".join(safe_lines)}

'''

OPS_CSS = r'''/* v4.4.0 — Centro operativo */
.ops-nav-icon{font-size:16px!important}.ops-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-bottom:14px}.ops-page-head h1{margin:0 0 3px}.ops-page-head p{margin:0}.ops-tabs{display:flex;gap:7px;margin-bottom:12px}.ops-tabs button{min-height:34px;border-radius:10px;padding:7px 13px}.ops-tabs button.active{background:#203f60;color:#fff;border-color:#203f60}.ops-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:10px}.ops-toolbar input{min-width:260px;max-width:420px}.ops-list{display:grid;gap:8px}.ops-card{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:11px;padding:11px 12px;border:1px solid #dfe7ef;border-radius:13px;background:#fff}.ops-card-icon{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:#edf3f9;color:#3d6388;font-size:18px}.ops-card-copy{min-width:0;display:grid;gap:2px}.ops-card-copy b{font-size:12px;color:#263e58}.ops-card-copy span{font-size:10px;color:#607287}.ops-card-copy small{font-size:8.5px;color:#8794a3}.ops-card-actions{display:flex;gap:6px;align-items:center}.ops-card-actions button{min-height:32px;font-size:9px;padding:6px 9px;border-radius:9px}.ops-empty{padding:28px;text-align:center;border:1px dashed #ccd8e4;border-radius:14px;color:#78889a;background:#fbfcfe}.ops-origin{font-weight:850;color:#526d88}.ops-toast{position:fixed;right:20px;bottom:20px;z-index:10050;display:flex;align-items:center;gap:12px;max-width:min(520px,calc(100vw - 32px));padding:12px 13px;border-radius:13px;background:#18324b;color:#fff;box-shadow:0 12px 34px rgba(14,35,55,.28)}.ops-toast-copy{display:grid;gap:2px;min-width:0}.ops-toast-copy b{font-size:11px}.ops-toast-copy small{font-size:8.5px;color:#d8e4ef}.ops-toast button{background:#fff;color:#18324b;border:0;font-weight:900;white-space:nowrap}.ops-toast .ops-toast-close{background:transparent;color:#fff;padding:4px 6px;font-size:16px}.patient-quick-drawer-backdrop{position:fixed;inset:0;background:rgba(18,34,49,.25);z-index:10020;opacity:0;pointer-events:none;transition:opacity .16s}.patient-quick-drawer-backdrop.open{opacity:1;pointer-events:auto}.patient-quick-drawer{position:fixed;top:0;right:0;height:100vh;width:min(430px,94vw);z-index:10030;background:#f8fafc;border-left:1px solid #dce5ed;box-shadow:-14px 0 40px rgba(24,45,64,.18);transform:translateX(105%);transition:transform .2s ease;display:flex;flex-direction:column}.patient-quick-drawer.open{transform:translateX(0)}.pq-head{padding:18px 18px 14px;background:#fff;border-bottom:1px solid #e2e8ef;display:grid;grid-template-columns:1fr auto;gap:10px}.pq-head h2{margin:0 0 4px;font-size:19px;line-height:1.12;color:#243c55}.pq-head p{margin:0;font-size:9px;color:#708093}.pq-close{width:34px;height:34px;padding:0;border-radius:10px;font-size:18px}.pq-body{padding:14px 16px 18px;overflow:auto;display:grid;gap:11px}.pq-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.pq-kpi{padding:9px;border:1px solid #dfe7ef;border-radius:11px;background:#fff;display:grid;gap:2px}.pq-kpi b{font-size:14px;color:#284561}.pq-kpi span{font-size:7.5px;color:#798a9b;text-transform:uppercase;font-weight:850}.pq-card{padding:11px 12px;border:1px solid #dfe7ef;border-radius:12px;background:#fff}.pq-card h3{margin:0 0 8px;font-size:11px;color:#304a64}.pq-contact{display:grid;gap:5px;font-size:9.5px;color:#50667c}.pq-next{border-color:#c9dff4;background:#f2f7fd}.pq-warning{border-color:#e7bd52;background:#fff8dc}.pq-history{display:grid;gap:6px}.pq-history-row{display:grid;grid-template-columns:74px minmax(0,1fr) auto;gap:7px;align-items:center;padding:7px 0;border-bottom:1px solid #eef2f6;font-size:9px}.pq-history-row:last-child{border-bottom:0}.pq-actions{display:flex;gap:7px;position:sticky;bottom:-18px;background:linear-gradient(180deg,rgba(248,250,252,0),#f8fafc 28%);padding-top:18px}.pq-actions button{flex:1;min-height:38px}.smart-agenda-card{margin:0 0 12px;padding:11px 12px;border:1px solid #d7e3ef;border-radius:14px;background:linear-gradient(135deg,#fff 0%,#f6f9fc 100%);display:grid;gap:9px}.smart-agenda-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.smart-agenda-title{display:grid;gap:2px}.smart-agenda-title b{font-size:11px;color:#29445f}.smart-agenda-title span{font-size:8.5px;color:#758697}.smart-agenda-chips{display:flex;flex-wrap:wrap;gap:6px}.smart-chip{padding:5px 8px;border-radius:999px;background:#edf3f8;color:#46627d;font-size:8px;font-weight:850}.smart-chip.warn{background:#fff1c6;color:#815c0a}.smart-chip.good{background:#e9f6ef;color:#3d7557}.smart-agenda-bottom{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}.smart-mini{padding:8px 9px;border-radius:10px;background:#fff;border:1px solid #e4ebf2;display:grid;gap:2px}.smart-mini b{font-size:9px;color:#3c5268}.smart-mini span{font-size:9px;color:#6e7f90}.smart-free-slots{display:flex;gap:4px;flex-wrap:wrap}.smart-free-slots i{font-style:normal;padding:3px 6px;border-radius:7px;background:#eef6fd;color:#3a6f9f;font-size:8px;font-weight:850}.ops-diagnostic-panel{margin-bottom:12px}.ops-diagnostic-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:10px}.diag-item{padding:9px 10px;border:1px solid #dfe7ef;border-radius:11px;background:#fff;display:grid;grid-template-columns:10px minmax(0,1fr);gap:7px;align-items:start}.diag-dot{width:9px;height:9px;border-radius:50%;margin-top:3px;background:#9aa7b5}.diag-item.ok .diag-dot{background:#3d9b67}.diag-item.warn .diag-dot{background:#d49a22}.diag-item.bad .diag-dot{background:#ca5656}.diag-copy{display:grid;gap:2px;min-width:0}.diag-copy b{font-size:9px;color:#334c65}.diag-copy span{font-size:8px;color:#718193;line-height:1.25}.diag-actions{display:flex;gap:7px;margin-top:10px}@media(max-width:720px){.ops-card{grid-template-columns:38px 1fr}.ops-card-actions{grid-column:1/-1;justify-content:flex-end}.smart-agenda-bottom,.ops-diagnostic-grid{grid-template-columns:1fr}.pq-kpis{grid-template-columns:1fr 1fr 1fr}}
'''

OPS_JS = r''';(()=>{
 if(window.__v440Ops)return;window.__v440Ops=true;
 const opsEsc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
 const opsDateTime=v=>{if(!v)return '';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`};
 const actionLabels={crear_paciente:'Paciente creado',crear_paciente_offline:'Paciente creado',editar_paciente:'Paciente editado',editar_paciente_offline:'Paciente editado',borrar_paciente:'Paciente eliminado',borrar_paciente_offline:'Paciente eliminado',crear_atencion:'Atención registrada',crear_atencion_offline:'Atención registrada',borrar_atencion:'Atención eliminada',borrar_atencion_offline:'Atención eliminada',eliminar_cita:'Cita eliminada',crear_cita:'Cita creada',editar_cita:'Cita editada',reagendar_cita:'Cita reagendada',restaurar_desde_papelera:'Elemento restaurado',guardar_en_papelera:'Guardado en Papelera',vaciar_elemento_papelera:'Eliminado definitivamente',aprobar_factura:'Factura aprobada',emitir_factura:'Factura emitida',marcar_factura_emitida:'Factura emitida'};
 function actionLabel(a){return actionLabels[a]||String(a||'Actividad').replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase())} function actionIcon(a){const x=String(a||'');if(x.includes('paciente'))return '👤';if(x.includes('atencion'))return '✚';if(x.includes('cita')||x.includes('agenda'))return '▣';if(x.includes('factura')||x.includes('azur'))return '$';if(x.includes('papelera')||x.includes('restaur'))return '↶';return '•'}
 function ensureOpsUI(){const nav=document.querySelector('.side-nav');const configBtn=nav?.querySelector('[data-section="config"]');if(nav&&configBtn&&!nav.querySelector('[data-section="actividad"]'))configBtn.insertAdjacentHTML('beforebegin','<button class="nav-btn" data-section="actividad" onclick="show(\'actividad\')"><span class="nav-icon ops-nav-icon">◷</span><span>Actividad</span></button>');const config=document.querySelector('#config');if(config&&!document.querySelector('#actividad')){const section=document.createElement('section');section.id='actividad';section.className='hidden';section.innerHTML=`<div class="ops-page-head"><div><h1>Actividad</h1><p class="muted">Cambios importantes del consultorio y elementos recuperables.</p></div></div><div class="ops-tabs"><button id="opsActivityTab" class="active" onclick="switchOpsTab('activity')">Actividad</button><button id="opsTrashTab" onclick="switchOpsTab('trash')">Papelera</button></div><div id="opsActivityPane"><div class="ops-toolbar"><input id="opsActivitySearch" class="uppercase-search" placeholder="BUSCAR EN ACTIVIDAD" oninput="scheduleOpsActivitySearch()"><button onclick="loadOpsActivity()">↻ Actualizar</button></div><div id="opsActivityList" class="ops-list"><div class="ops-empty">Cargando actividad…</div></div></div><div id="opsTrashPane" class="hidden"><div class="ops-toolbar"><span class="muted">Los elementos eliminados pueden restaurarse durante 30 días.</span><button onclick="loadOpsTrash()">↻ Actualizar</button></div><div id="opsTrashList" class="ops-list"><div class="ops-empty">Cargando Papelera…</div></div></div>`;config.insertAdjacentElement('beforebegin',section)}ensurePatientDrawer();ensureSmartAgendaHost();ensureDiagnosticsCard()}
 function switchOpsTab(tab){const activity=tab!=='trash';$('#opsActivityTab')?.classList.toggle('active',activity);$('#opsTrashTab')?.classList.toggle('active',!activity);$('#opsActivityPane')?.classList.toggle('hidden',!activity);$('#opsTrashPane')?.classList.toggle('hidden',activity);if(activity)loadOpsActivity();else loadOpsTrash()}window.switchOpsTab=switchOpsTab;
 let opsSearchTimer=null;window.scheduleOpsActivitySearch=()=>{clearTimeout(opsSearchTimer);opsSearchTimer=setTimeout(loadOpsActivity,220)};
 async function loadOpsActivity(){const box=$('#opsActivityList');if(!box)return;box.innerHTML='<div class="ops-empty">Cargando actividad…</div>';try{const q=String($('#opsActivitySearch')?.value||'').trim();const rows=await api('/api/ops/activity?limit=160'+(q?'&q='+encodeURIComponent(q):''));box.innerHTML=rows.map(r=>`<article class="ops-card"><div class="ops-card-icon">${actionIcon(r.action)}</div><div class="ops-card-copy"><b>${opsEsc(actionLabel(r.action))}</b><span>${opsEsc(r.detail||'Sin detalle adicional')}</span><small>${opsEsc(opsDateTime(r.ts))} · <span class="ops-origin">${opsEsc(r.origin||'PC')}</span></small></div><div></div></article>`).join('')||'<div class="ops-empty">Todavía no hay actividad registrada.</div>'}catch(e){box.innerHTML=`<div class="ops-empty">${opsEsc(e.message)}</div>`}}window.loadOpsActivity=loadOpsActivity;
 function trashIcon(t){return t==='patient'?'👤':t==='visit'?'✚':t==='appointment'||t==='staged_appointment'?'▣':'↶'}function trashType(t){return t==='patient'?'Paciente':t==='visit'?'Atención':t==='appointment'||t==='staged_appointment'?'Cita':'Elemento'}
 async function loadOpsTrash(){const box=$('#opsTrashList');if(!box)return;box.innerHTML='<div class="ops-empty">Cargando Papelera…</div>';try{const rows=await api('/api/ops/trash?limit=160');box.innerHTML=rows.map(r=>`<article class="ops-card"><div class="ops-card-icon">${trashIcon(r.entity_type)}</div><div class="ops-card-copy"><b>${opsEsc(trashType(r.entity_type))} · ${opsEsc(r.label)}</b><span>Eliminado ${opsEsc(opsDateTime(r.deleted_at))} · ${opsEsc(r.origin||'PC')}</span><small>${Number(r.days_left||0)} día${Number(r.days_left||0)===1?'':'s'} para recuperación automática</small></div><div class="ops-card-actions"><button class="primary-soft" onclick="restoreTrash(${Number(r.id)})">↶ Restaurar</button><button class="danger ghost" onclick="deleteTrashForever(${Number(r.id)})">Eliminar definitivo</button></div></article>`).join('')||'<div class="ops-empty">La Papelera está vacía.</div>'}catch(e){box.innerHTML=`<div class="ops-empty">${opsEsc(e.message)}</div>`}}window.loadOpsTrash=loadOpsTrash;
 async function restoreTrash(id){try{await singleFlightMutation(`trash:restore:${id}`,async()=>{const d=await api(`/api/ops/trash/${id}/restore`,{method:'POST'});await loadOpsTrash();await loadOpsActivity();try{invalidateAttentionWeekCache()}catch{}try{invalidateAgendaSlotCache()}catch{}try{await refreshVisibleSectionLocal()}catch{}return d},'Restaurando…')}catch(e){alert(e.message)}}window.restoreTrash=restoreTrash;
 async function deleteTrashForever(id){if(!confirm('¿Eliminar definitivamente este elemento de la Papelera? Después ya no podrá recuperarse.'))return;try{await api(`/api/ops/trash/${id}`,{method:'DELETE'});await loadOpsTrash()}catch(e){alert(e.message)}}window.deleteTrashForever=deleteTrashForever;
 function showUndoToast(data){if(!data?.trash_id)return;document.querySelector('.ops-toast')?.remove();const t=document.createElement('div');t.className='ops-toast';t.innerHTML=`<div class="ops-toast-copy"><b>Elemento enviado a Papelera</b><small>${opsEsc(data.trash_label||'Puedes recuperarlo durante 30 días.')}</small></div><button onclick="undoTrashFromToast(${Number(data.trash_id)})">Deshacer</button><button class="ops-toast-close" onclick="this.parentElement.remove()">×</button>`;document.body.appendChild(t);setTimeout(()=>t.remove(),9000)}
 async function undoTrashFromToast(id){try{await api(`/api/ops/trash/${id}/restore`,{method:'POST'});document.querySelector('.ops-toast')?.remove();try{invalidateAttentionWeekCache()}catch{}try{invalidateAgendaSlotCache()}catch{}try{await refreshVisibleSectionLocal()}catch{}if(!$('#agenda')?.classList.contains('hidden'))await loadAgenda()}catch(e){alert(e.message)}}window.undoTrashFromToast=undoTrashFromToast;
 function ensurePatientDrawer(){if(document.querySelector('#patientQuickDrawer'))return;document.body.insertAdjacentHTML('beforeend','<div id="patientQuickBackdrop" class="patient-quick-drawer-backdrop" onclick="closePatientQuick()"></div><aside id="patientQuickDrawer" class="patient-quick-drawer" aria-hidden="true"><div id="patientQuickContent"></div></aside>')}function closePatientQuick(){document.querySelector('#patientQuickBackdrop')?.classList.remove('open');const d=document.querySelector('#patientQuickDrawer');d?.classList.remove('open');d?.setAttribute('aria-hidden','true')}window.closePatientQuick=closePatientQuick;function visitService(v){return opsEsc(v?.procedimiento||'CONSULTA')}
 async function openPatientQuick(id){ensurePatientDrawer();const drawer=$('#patientQuickDrawer'),back=$('#patientQuickBackdrop'),content=$('#patientQuickContent');content.innerHTML='<div class="pq-head"><div><h2>Cargando paciente…</h2></div><button class="pq-close" onclick="closePatientQuick()">×</button></div>';drawer.classList.add('open');back.classList.add('open');drawer.setAttribute('aria-hidden','false');try{const d=await api(`/api/patients/${Number(id)}/quick`),p=d.patient||{},next=d.next_appointment,last=d.last_visit;const history=(d.recent_visits||[]).map(v=>`<div class="pq-history-row"><span>${opsEsc(fmtDate(v.fecha))}</span><b>${visitService(v)}</b><strong>${opsEsc(money(v.valor))}</strong></div>`).join('')||'<span class="muted">Sin atenciones registradas desde 2026.</span>';const warnings=(d.missing||[]).length?`<div class="pq-card pq-warning"><h3>⚠ Registro del paciente</h3><div class="pq-contact">Falta completar: <b>${opsEsc(d.missing.join(', '))}</b></div></div>`:'';content.innerHTML=`<div class="pq-head"><div><h2>${opsEsc(p.nombre||'Paciente')}</h2><p>${opsEsc(p.cedula||'Sin cédula')} · ${Number(d.visit_count||0)?'Subsecuente':'Nuevo'}</p></div><button class="pq-close" onclick="closePatientQuick()">×</button></div><div class="pq-body"><div class="pq-kpis"><div class="pq-kpi"><b>${Number(d.visit_count||0)}</b><span>Atenciones</span></div><div class="pq-kpi"><b>${last?opsEsc(fmtDate(last.fecha)):'—'}</b><span>Última</span></div><div class="pq-kpi"><b>${next?opsEsc(fmtDate(next.fecha)):'—'}</b><span>Próxima</span></div></div><div class="pq-card"><h3>Contacto</h3><div class="pq-contact"><span>☎ ${opsEsc(p.celular||'Sin celular')}</span><span>✉ ${opsEsc(p.correo||'Sin correo')}</span><span>⌖ ${opsEsc(p.lugar||'Sin lugar registrado')}</span></div></div>${next?`<div class="pq-card pq-next"><h3>Próxima cita</h3><div class="pq-contact"><b>${opsEsc(fmtDate(next.fecha))} · ${opsEsc(fmtTime(next.hora))}</b><span>${opsEsc(next.nota||'Sin nota')}</span></div></div>`:''}${warnings}<div class="pq-card"><h3>Últimas atenciones</h3><div class="pq-history">${history}</div></div><div class="pq-actions"><button onclick="closePatientQuick();openPatient(${Number(p.id)},'patients')">Ver historial completo</button><button class="primary" onclick="closePatientQuick();attentionFor(${Number(p.id)})">Nueva atención</button></div></div>`}catch(e){content.innerHTML=`<div class="pq-head"><div><h2>No se pudo abrir</h2><p>${opsEsc(e.message)}</p></div><button class="pq-close" onclick="closePatientQuick()">×</button></div>`}}window.openPatientQuick=openPatientQuick;
 const fullOpenPatient=window.openPatient;if(typeof fullOpenPatient==='function')window.openPatient=async function(id,source='general'){if(source==='home'||source==='quick'||source==='general')return openPatientQuick(id);return fullOpenPatient(id,source)};
 function ensureSmartAgendaHost(){const title=document.querySelector('#agenda .agenda-native-title-row');if(title&&!document.querySelector('#smartAgendaCard'))title.insertAdjacentHTML('afterend','<div id="smartAgendaCard" class="smart-agenda-card"><div class="muted">Preparando resumen inteligente…</div></div>')}
 async function loadSmartAgenda(){ensureSmartAgendaHost();const box=$('#smartAgendaCard');if(!box)return;try{const d=await api('/api/ops/agenda-smart');const next=d.next,free=d.free_slots||[],label=d.is_today?'Hoy':`Próxima jornada · ${fmtDate(d.date)}`;box.innerHTML=`<div class="smart-agenda-top"><div class="smart-agenda-title"><b>${opsEsc(label)}</b><span>Resumen automático de la agenda.</span></div><button onclick="loadSmartAgenda()">↻</button></div><div class="smart-agenda-chips"><span class="smart-chip">${Number(d.total||0)} citas</span><span class="smart-chip">${Number(d.new||0)} nuevos</span><span class="smart-chip">${Number(d.subsequent||0)} subsecuentes</span><span class="smart-chip good">${Number(d.attended||0)} atendidos</span>${Number(d.late_count||0)?`<span class="smart-chip warn">⚠ ${Number(d.late_count)} pendientes atrasados</span>`:''}${Number(d.incomplete_today||0)?`<span class="smart-chip warn">⚠ ${Number(d.incomplete_today)} fichas incompletas</span>`:''}</div><div class="smart-agenda-bottom"><div class="smart-mini"><b>Siguiente paciente</b><span>${next?`${opsEsc(fmtTime(next.time))} · ${opsEsc(next.name)}`:'No hay otra cita pendiente.'}</span></div><div class="smart-mini"><b>Horarios libres</b><div class="smart-free-slots">${free.length?free.slice(0,6).map(x=>`<i>${opsEsc(fmtTime(x))}</i>`).join(''):'<span>Sin huecos disponibles.</span>'}</div></div></div>`}catch(e){box.innerHTML=`<div class="muted">No se pudo preparar el resumen: ${opsEsc(e.message)}</div>`}}window.loadSmartAgenda=loadSmartAgenda;const oldLoadAgenda=window.loadAgenda;if(typeof oldLoadAgenda==='function')window.loadAgenda=async function(...args){const r=await oldLoadAgenda(...args);setTimeout(loadSmartAgenda,0);return r};
 function ensureDiagnosticsCard(){const sys=document.querySelector('[data-config-section="sistema"]');if(!sys||sys.querySelector('#opsDiagnosticPanel'))return;const card=document.createElement('div');card.id='opsDiagnosticPanel';card.className='panel compact-config-panel ops-diagnostic-panel';card.innerHTML='<div class="config-panel-head"><div><h3>Revisar sistema</h3><p class="muted">Comprueba Recepción, Neon, AZUR, WhatsApp, Agenda y actualizaciones sin mostrar claves.</p></div><span class="performance-pill">Diagnóstico</span></div><div id="opsDiagnosticGrid" class="ops-diagnostic-grid"><div class="muted">Pulsa Revisar sistema cuando necesites comprobar todo.</div></div><div class="diag-actions"><button class="primary-soft" onclick="runOpsDiagnostics()">🔧 Revisar sistema</button><button id="copyOpsDiagnosticsBtn" class="hidden" onclick="copyOpsDiagnostics()">Copiar diagnóstico</button></div>';sys.prepend(card)}let lastSafeDiagnostic='';async function runOpsDiagnostics(){const box=$('#opsDiagnosticGrid');if(!box)return;box.innerHTML='<div class="muted">Comprobando servicios…</div>';try{const d=await api('/api/ops/diagnostics');lastSafeDiagnostic=d.safe_text||'';const order=['local','neon','azur','whatsapp','mensajes','agenda','updates'];box.innerHTML=order.map(k=>{const x=d.services?.[k]||{},state=String(x.status||x.state||'').toUpperCase(),cls=['ONLINE','OK','READY','ACTIVO'].some(v=>state.includes(v))?'ok':['OFFLINE','ERROR','FAILED'].some(v=>state.includes(v))?'bad':'warn';return `<div class="diag-item ${cls}"><span class="diag-dot"></span><div class="diag-copy"><b>${opsEsc(x.name||k)}</b><span>${opsEsc(x.detail||x.message||state||'Sin detalle')}</span></div></div>`}).join('');$('#copyOpsDiagnosticsBtn')?.classList.remove('hidden')}catch(e){box.innerHTML=`<div class="muted">${opsEsc(e.message)}</div>`}}window.runOpsDiagnostics=runOpsDiagnostics;async function copyOpsDiagnostics(){if(!lastSafeDiagnostic)return;try{await navigator.clipboard.writeText(lastSafeDiagnostic);alert('Diagnóstico copiado.')}catch{prompt('Copia este diagnóstico:',lastSafeDiagnostic)}}window.copyOpsDiagnostics=copyOpsDiagnostics;
 window.deletePatient=async function(id,visitCount){const extra=visitCount?` También se eliminarán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'}.`:'';if(!confirmDeletion(`¿Borrar este paciente?${extra}\n\nPodrás recuperarlo desde Actividad > Papelera durante 30 días.`))return;try{await singleFlightMutation(`patient:delete:${id}`,async()=>{const d=await api('/api/safety/patients/'+id,{method:'DELETE'});closeModal();show('pacientes');await searchPatients();await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()]);showUndoToast(d)},'Borrando…')}catch(e){alert(e.message)}};
 window.deleteVisit=async function(visitId,patientId){if(!confirmDeletion('¿Borrar esta atención? Se enviará a Papelera durante 30 días.'))return;try{await singleFlightMutation(`visit:delete:${visitId}`,async()=>{const d=await api('/api/safety/visits/'+visitId,{method:'DELETE'});invalidateAttentionWeekCache();await fullOpenPatient(patientId,'patients');await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()]);showUndoToast(d)},'Borrando…')}catch(e){alert(e.message)}};
 window.deleteVisitFromHome=async function(visitId,fecha){if(!confirmDeletion('¿Borrar esta atención? Se enviará a Papelera durante 30 días y se quitará su pre-factura asociada.'))return;try{await singleFlightMutation(`visit:delete:${visitId}`,async()=>{const d=await api('/api/safety/visits/'+visitId,{method:'DELETE'});invalidateAttentionWeekCache();await Promise.all([loadWeek(fecha||selectedHomeDate||toISO(new Date()),fecha||selectedHomeDate),refreshPendingBadges()]);showUndoToast(d)},'Borrando…')}catch(e){alert(e.message)}};
 window.deleteAgendaAppointment=async function(id){if(!confirmDeletion('¿Eliminar esta cita y liberar el horario? La ficha del paciente no se borrará y podrás restaurar la cita durante 30 días.'))return;try{await singleFlightMutation(`appointment:delete:${id}`,async()=>{const d=await api(`/api/safety/appointments/${id}`,{method:'DELETE'});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();await loadAgenda();showUndoToast(d)},'Eliminando…')}catch(e){alert(e.message)}};
 window.deleteUnlinkedAppointment=async function(itemId){if(!confirmDeletion('¿Eliminar esta cita y liberar el horario? Podrás recuperarla desde Papelera durante 30 días.'))return;try{const d=await api(`/api/safety/unlinked/${Number(itemId)}`,{method:'DELETE'});closeModal();invalidateAgendaSlotCache();invalidateAttentionWeekCache();await loadAgenda();showUndoToast(d)}catch(e){alert(e.message)}};
 const oldShow=window.show;if(typeof oldShow==='function')window.show=function(id,configTab=null){const r=oldShow(id,configTab);if(id==='actividad')setTimeout(()=>switchOpsTab('activity'),0);if(id==='agenda')setTimeout(loadSmartAgenda,0);if(id==='config')setTimeout(ensureDiagnosticsCard,0);return r};
 function maybeDailyBrief(){const key='rp_v440_brief_'+toISO(new Date());if(localStorage.getItem(key))return;setTimeout(async()=>{try{const d=await api('/api/ops/agenda-smart');if(!d.is_today||!Number(d.total||0))return;localStorage.setItem(key,'1');document.querySelector('.ops-toast')?.remove();const t=document.createElement('div');t.className='ops-toast';t.innerHTML=`<div class="ops-toast-copy"><b>Jornada de hoy · ${Number(d.total||0)} citas</b><small>${Number(d.new||0)} nuevos · ${Number(d.subsequent||0)} subsecuentes${d.next?` · primero pendiente ${fmtTime(d.next.time)}`:''}</small></div><button onclick="show('agenda');this.parentElement.remove()">Ver agenda</button><button class="ops-toast-close" onclick="this.parentElement.remove()">×</button>`;document.body.appendChild(t);setTimeout(()=>t.remove(),12000)}catch{}},1800)}function init(){ensureOpsUI();maybeDailyBrief()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else setTimeout(init,0);
})();'''


def patch_app(s: str) -> str:
    s=replace_once(s,'APP_VERSION = "4.3.104"','APP_VERSION = "4.4.0"','versión backend')
    s=replace_once(s,"const VERSION=\\'4.3.104\\';","const VERSION=\\'4.4.0\\';",'versión visual')
    s=replace_once(s,'cloud_schema_ready_v4_3_19_visual_','cloud_schema_ready_v4_4_0_ops_','marcador esquema cloud')
    model_marker='class SyncOperation(Base):'
    if s.count(model_marker)!=1: raise SystemExit('marker SyncOperation inesperado')
    s=s.replace(model_marker,TRASH_MODEL+model_marker,1)
    old_audit='''def audit(db: Session, username_or_user, action: str, detail: str = ""):\n    username = getattr(username_or_user, "username", None) or str(username_or_user or "admin")\n    db.add(Audit(username=username, action=action, detail=detail))\n'''
    s=replace_once(s,old_audit,AUDIT_REPLACEMENT,'audit con origen de PC')
    endpoint_marker='@app.get("/api/procedures")'
    if s.count(endpoint_marker)!=1: raise SystemExit('marker procedures inesperado')
    s=s.replace(endpoint_marker,BACKEND_OPS+'\n'+endpoint_marker,1)
    overlay_marker='@app.get("/v460/overlay.css")'
    if s.count(overlay_marker)!=1: raise SystemExit('overlay marker inesperado')
    overlay=('V440_OPS_CSS = r"""'+OPS_CSS+'"""\n'+'V440_OPS_JS = r"""'+OPS_JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V440_OPS_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V440_OPS_JS\n\n'+overlay_marker)
    s=s.replace(overlay_marker,overlay,1)
    compile(s,'app.py','exec')
    required=['APP_VERSION = "4.4.0"','class TrashItem(Base):','TRASH_RETENTION_DAYS = 30','/api/safety/patients/{pid}','/api/safety/visits/{visit_id}','/api/safety/appointments/{appointment_id}','/api/ops/trash','/api/ops/activity','/api/patients/{pid}/quick','/api/ops/agenda-smart','/api/ops/diagnostics','V440_OPS_JS','Actividad','Papelera','Revisar sistema','smart-agenda-card','patient-quick-drawer','V43104_ALERT_JS','V43103_SERVICES_CSS','Procedimientos y servicios',"price.textContent='$40.00'",'Revisando AZUR','Emitir por lotes','cloud_schema_ready_v4_4_0_ops_']
    for token in required:
        if token not in s: raise SystemExit('app falta '+token)
    return s


def main() -> None:
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    (OUT/'static').mkdir(parents=True,exist_ok=True)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8'); static_app=(SRC/'static'/'app.js').read_text(encoding='utf-8')
    (OUT/'static'/'index.html').write_text(index,encoding='utf-8',newline='');(OUT/'static'/'app.js').write_text(static_app,encoding='utf-8',newline='')
    ab,lb,ib,jb=app.encode(),launcher.encode(),index.encode(),static_app.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','static/app.js','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v440/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.4.0: añade Papelera con Deshacer, Actividad, ficha rápida del paciente, Agenda inteligente y Revisar sistema, preservando la base estable v4.3.104.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'static/app.js','url':base+'static/app.js','sha256':sha(jb),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb),sha(jb))

if __name__=='__main__': main()
