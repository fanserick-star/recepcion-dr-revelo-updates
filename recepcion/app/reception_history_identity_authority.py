from __future__ import annotations

import json
import re
import ssl
import unicodedata
from datetime import date, datetime
from pathlib import Path

import core_runtime as core
import historia_bridge

app = core.app
_VERSION_DOC = json.loads(Path(__file__).with_name("recepcion-version.json").read_text(encoding="utf-8-sig"))
APP_VERSION = str(_VERSION_DOC.get("version") or "").strip()
if not APP_VERSION:
    raise RuntimeError("recepcion-version.json no contiene una versión válida")
core.APP_VERSION = APP_VERSION

HISTORIA_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"
_PLACEHOLDER_IDS = {"X", "XX", "XXX", "XXXX", "XXXXX", "TESTIGO", "QUEVEDO", "LAMANA", "ECUASANITAS", "TJ", "N/A", "NA", "SINID", "SINCEDULA"}


def _clean(value, limit=500):
    return str(value or "").strip()[:limit]


def _norm_text(value):
    raw = unicodedata.normalize("NFD", _clean(value, 500))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", raw).strip().upper()


def _fuzzy_text(value):
    # Equivalencia conservadora para errores frecuentes del archivo legado.
    # BASURTO/BAZURTO se muestra como candidato, pero no se autovincula por nombre.
    return _norm_text(value).replace("Z", "S")


def _norm_id(value):
    return re.sub(r"[^A-Z0-9]", "", _norm_text(value))


def _usable_id(value):
    ident = _norm_id(value)
    if not ident or ident in _PLACEHOLDER_IDS or len(ident) < 6:
        return ""
    return ident


def _norm_phone(value):
    digits = re.sub(r"\D", "", _clean(value, 80))
    if len(digits) == 12 and digits.startswith("593"):
        digits = "0" + digits[3:]
    return digits


def _iso_date(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    raw = _clean(value, 30)
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    return match.group(0) if match else raw[:10]


def _endpoint_id(host):
    label = _clean(host, 255).lower().split(".", 1)[0]
    return label[:-7] if label.endswith("-pooler") else label


def _connect_public():
    """Única conexión operativa de Recepción hacia Historia: public.*."""
    url = historia_bridge._database_url()
    if not url:
        raise RuntimeError("Historia Clínica no está configurada en esta PC")
    cfg = historia_bridge._parse_pg_url(url)
    if _endpoint_id(cfg.get("host")) != HISTORIA_ENDPOINT_ID:
        raise RuntimeError("Se bloqueó una conexión que no corresponde al Neon de Historia Clínica")
    from pg8000 import dbapi
    conn = dbapi.connect(user=cfg["user"], password=cfg["password"], host=cfg["host"], port=cfg["port"], database=cfg["database"], ssl_context=ssl.create_default_context(), timeout=12)
    try:
        cur = conn.cursor()
        cur.execute("SET search_path TO public")
        cur.execute("""
            SELECT table_name,column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name IN ('patients','encounters','patient_links','waiting_queue')
        """)
        found = {}
        for table, column in cur.fetchall() or []:
            found.setdefault(str(table), set()).add(str(column))
        required = {
            "patients": {"id","name","name_search","birth_date","phone","national_id","national_id_search","email","deleted_at","cloud_updated_at"},
            "encounters": {"id","patient_id","encounter_date","note_status","deleted_at","cloud_updated_at"},
            "patient_links": {"reception_patient_id","clinical_patient_id","matched_by","verified","deleted_at","cloud_updated_at"},
            "waiting_queue": {"id","reception_event_id","reception_patient_id","clinical_patient_id","status","patient_status","reception_turn","deleted_at","cloud_updated_at"},
        }
        missing = {table: sorted(cols - found.get(table, set())) for table, cols in required.items() if not cols.issubset(found.get(table, set()))}
        if missing:
            raise RuntimeError("El esquema canónico de Historia está incompleto: " + json.dumps(missing, ensure_ascii=False))
        conn.commit()
        return conn
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


# El antiguo schema historia.* queda fuera del flujo operativo.
historia_bridge._connect = _connect_public


def _reception_patient(db, reception_patient_id):
    try:
        pid = int(reception_patient_id)
    except Exception as exc:
        raise core.HTTPException(400, "Paciente de Recepción inválido") from exc
    patient = db.get(core.Patient, pid)
    if not patient:
        raise core.HTTPException(404, "Paciente no encontrado en Recepción")
    return patient


def _demographics(patient):
    return {
        "name": re.sub(r"\s+", " ", _clean(getattr(patient, "nombre", ""), 260)).strip().upper(),
        "birth_date": _iso_date(getattr(patient, "fecha_nacimiento", None)),
        "address": _clean(getattr(patient, "lugar", ""), 400),
        "phone": _clean(getattr(patient, "celular", ""), 120),
        "national_id": _clean(getattr(patient, "cedula", ""), 120),
        "email": _clean(getattr(patient, "correo", ""), 180).lower(),
    }


def _dict_row(cur, row):
    if not row:
        return None
    return dict(zip([str(col[0]) for col in cur.description], row))


def _history_summary(cur, clinical_patient_id):
    cur.execute("""
        SELECT COUNT(DISTINCT CASE WHEN e.deleted_at IS NULL AND COALESCE(e.note_status,'signed') <> 'draft' AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL THEN e.encounter_date END),
               MAX(CASE WHEN e.deleted_at IS NULL AND COALESCE(e.note_status,'signed') <> 'draft' AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL THEN e.encounter_date END)
        FROM public.encounters e WHERE e.patient_id=%s
    """, (str(clinical_patient_id),))
    row = cur.fetchone() or (0, None)
    return {"history_date_count": int(row[0] or 0), "last_history_date": _clean(row[1], 20)}


def _patient_row(cur, clinical_patient_id):
    cur.execute("""
        SELECT id,name,name_search,national_id,national_id_search,birth_date,phone,email,address,merged_into_patient_id
        FROM public.patients WHERE id=%s AND deleted_at IS NULL LIMIT 1
    """, (str(clinical_patient_id),))
    row = _dict_row(cur, cur.fetchone())
    if not row:
        return None
    merged = _clean(row.get("merged_into_patient_id"), 120)
    if merged and merged != str(row["id"]):
        cur.execute("""
            SELECT id,name,name_search,national_id,national_id_search,birth_date,phone,email,address,merged_into_patient_id
            FROM public.patients WHERE id=%s AND deleted_at IS NULL LIMIT 1
        """, (merged,))
        canonical = _dict_row(cur, cur.fetchone())
        if canonical:
            row = canonical
    row.update(_history_summary(cur, row["id"]))
    return row


def _linked_patient(cur, reception_patient_id):
    cur.execute("""
        SELECT clinical_patient_id,matched_by,verified
        FROM public.patient_links
        WHERE reception_patient_id=%s AND deleted_at IS NULL LIMIT 1
    """, (str(reception_patient_id),))
    link = _dict_row(cur, cur.fetchone())
    if not link:
        return None
    row = _patient_row(cur, link["clinical_patient_id"])
    if not row:
        return None
    row["matched_by"] = link.get("matched_by")
    row["verified"] = link.get("verified")
    return row


def _same_identity_signature(rows):
    names = {_fuzzy_text(r.get("name")) for r in rows if _clean(r.get("name"))}
    births = {_iso_date(r.get("birth_date")) for r in rows if _iso_date(r.get("birth_date"))}
    return len(names) <= 1 and len(births) <= 1


def _safe_exact_identification_match(cur, identification):
    ident = _usable_id(identification)
    if not ident:
        return None, False
    cur.execute("""
        SELECT id,name,name_search,national_id,national_id_search,birth_date,phone,email,address,merged_into_patient_id
        FROM public.patients WHERE deleted_at IS NULL AND national_id_search=%s LIMIT 12
    """, (ident,))
    rows = [_dict_row(cur, r) for r in (cur.fetchall() or [])]
    if len(rows) == 1:
        rows[0].update(_history_summary(cur, rows[0]["id"]))
        return rows[0], False
    if len(rows) < 2 or not _same_identity_signature(rows):
        return None, False
    for row in rows:
        row.update(_history_summary(cur, row["id"]))
    with_history = [r for r in rows if int(r.get("history_date_count") or 0) > 0]
    if len(with_history) == 1 and sum(int(r.get("history_date_count") or 0) == 0 for r in rows) == len(rows) - 1:
        return with_history[0], True
    return None, False


def _upsert_link(cur, reception_patient_id, clinical_patient_id, matched_by):
    stamp = datetime.now().isoformat(timespec="seconds")
    cur.execute("""
        INSERT INTO public.patient_links(reception_patient_id,clinical_patient_id,matched_by,verified,verified_at,created_at,updated_at,deleted_at,cloud_updated_at)
        VALUES(%s,%s,%s,1,%s,%s,%s,NULL,now())
        ON CONFLICT(reception_patient_id) DO UPDATE SET
          clinical_patient_id=EXCLUDED.clinical_patient_id, matched_by=EXCLUDED.matched_by,
          verified=1, verified_at=EXCLUDED.verified_at, updated_at=EXCLUDED.updated_at,
          deleted_at=NULL, cloud_updated_at=now()
    """, (str(reception_patient_id), str(clinical_patient_id), _clean(matched_by, 80), stamp, stamp, stamp))
    cur.execute("""
        UPDATE public.waiting_queue
        SET clinical_patient_id=%s,updated_at=%s,cloud_updated_at=now()
        WHERE reception_patient_id=%s AND deleted_at IS NULL
          AND (status IN ('waiting','in_consultation') OR clinical_patient_id IS NULL OR clinical_patient_id='')
    """, (str(clinical_patient_id), stamp, str(reception_patient_id)))


def _sync_demographics(cur, clinical_patient_id, demo):
    before = _patient_row(cur, clinical_patient_id)
    if not before:
        raise RuntimeError("La ficha vinculada ya no existe en Historia Clínica")
    changes, warnings = {}, []
    wanted_id = _clean(demo.get("national_id"), 120)
    wanted_id_search = _usable_id(wanted_id)
    current_id = _usable_id(before.get("national_id_search") or before.get("national_id"))
    if wanted_id_search and wanted_id_search != current_id:
        cur.execute("""
            SELECT id,name,birth_date FROM public.patients
            WHERE deleted_at IS NULL AND national_id_search=%s AND id<>%s LIMIT 8
        """, (wanted_id_search, str(clinical_patient_id)))
        conflicts = [_dict_row(cur, r) for r in (cur.fetchall() or [])]
        compatible_duplicates = bool(conflicts) and all(
            _fuzzy_text(r.get("name")) == _fuzzy_text(demo.get("name")) and
            (not _iso_date(r.get("birth_date")) or not _iso_date(demo.get("birth_date")) or _iso_date(r.get("birth_date")) == _iso_date(demo.get("birth_date")))
            for r in conflicts
        )
        if conflicts and not compatible_duplicates:
            warnings.append("La cédula/identificación no se actualizó porque ya pertenece a otra ficha distinta de Historia.")
        elif not conflicts:
            changes["national_id"] = wanted_id
            changes["national_id_search"] = wanted_id_search
        else:
            warnings.append("Se detectó una ficha duplicada compatible con la misma identificación; no se creó otro duplicado.")
    wanted_name = _clean(demo.get("name"), 260)
    if wanted_name and _norm_text(wanted_name) != _norm_text(before.get("name")):
        changes["name"] = wanted_name
        changes["name_search"] = _norm_text(wanted_name)
    for field, column, limit in (("birth_date","birth_date",20),("address","address",400),("phone","phone",120),("email","email",180)):
        wanted, current = _clean(demo.get(field), limit), _clean(before.get(column), limit)
        if wanted and wanted != current:
            changes[column] = wanted
    if changes:
        stamp = datetime.now().isoformat(timespec="seconds")
        assignments, values = [], []
        for column, value in changes.items():
            assignments.append(f'"{column}"=%s')
            values.append(value)
        assignments.extend(["updated_at=%s", "cloud_updated_at=now()"])
        values.extend([stamp, str(clinical_patient_id)])
        cur.execute("UPDATE public.patients SET " + ",".join(assignments) + " WHERE id=%s AND deleted_at IS NULL", tuple(values))
    return changes, warnings


def _prepare_identity(db, reception_patient_id, *, auto_link=True, sync=True):
    patient = _reception_patient(db, reception_patient_id)
    demo = _demographics(patient)
    conn = _connect_public()
    try:
        cur = conn.cursor()
        linked = _linked_patient(cur, patient.id)
        matched_now = False
        duplicate_exact_id_resolved = False
        if linked is None and auto_link:
            exact, duplicate_exact_id_resolved = _safe_exact_identification_match(cur, demo["national_id"])
            if exact:
                method = "reception_exact_identification_canonical" if duplicate_exact_id_resolved else "reception_exact_identification"
                _upsert_link(cur, patient.id, exact["id"], method)
                conn.commit()
                matched_now = True
                linked = _linked_patient(cur, patient.id)
        changed, warnings = {}, []
        if linked is not None and sync:
            _upsert_link(cur, patient.id, linked["id"], linked.get("matched_by") or "reception_verified")
            changed, warnings = _sync_demographics(cur, linked["id"], demo)
            conn.commit()
            linked = _linked_patient(cur, patient.id)
        return {
            "ok": True, "reachable": True, "reception_patient_id": int(patient.id),
            "reception_name": demo["name"], "reception_birth_date": demo["birth_date"],
            "linked": bool(linked), "auto_linked": bool(matched_now),
            "duplicate_exact_id_resolved": bool(duplicate_exact_id_resolved),
            "clinical_patient": linked,
            "history_date_count": int((linked or {}).get("history_date_count") or 0),
            "last_history_date": _clean((linked or {}).get("last_history_date"), 20),
            "demographics_changed": changed, "warnings": warnings,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _candidate_score(row, demo, query):
    score, reasons = 0, []
    wanted_id, row_id = _usable_id(demo.get("national_id")), _usable_id(row.get("national_id_search") or row.get("national_id"))
    if wanted_id and row_id and wanted_id == row_id:
        score += 120; reasons.append("misma identificación")
    wanted_phone, row_phone = _norm_phone(demo.get("phone")), _norm_phone(row.get("phone"))
    if wanted_phone and row_phone and wanted_phone[-9:] == row_phone[-9:]:
        score += 80; reasons.append("mismo celular")
    wanted_birth, row_birth = _iso_date(demo.get("birth_date")), _iso_date(row.get("birth_date"))
    if wanted_birth and row_birth and wanted_birth == row_birth:
        score += 70; reasons.append("misma fecha de nacimiento")
    wanted_name, row_name = _fuzzy_text(demo.get("name")), _fuzzy_text(row.get("name_search") or row.get("name"))
    if wanted_name and row_name:
        if wanted_name == row_name:
            score += 75; reasons.append("mismo nombre")
        else:
            tokens = [t for t in wanted_name.split() if len(t) >= 2]
            matches = sum(1 for token in tokens if token in row_name)
            if matches:
                score += min(55, matches * 11)
                if matches >= max(2, len(tokens) - 1): reasons.append("nombre muy parecido")
    q_tokens = [t for t in _fuzzy_text(query).split() if len(t) >= 2]
    score += min(30, sum(1 for token in q_tokens if token in row_name) * 6)
    if int(row.get("history_date_count") or 0) > 0:
        score += min(15, int(row.get("history_date_count") or 0))
    return score, reasons


def _search_candidates(cur, demo, query, limit):
    ident, phone, birth = _usable_id(query), _norm_phone(query), _iso_date(demo.get("birth_date"))
    demo_id, demo_phone = _usable_id(demo.get("national_id")), _norm_phone(demo.get("phone"))
    q_tokens = [t for t in _fuzzy_text(query).split() if len(t) >= 2]
    demo_tokens = [t for t in _fuzzy_text(demo.get("name")).split() if len(t) >= 2]
    where, params = [], []
    for value in (ident, demo_id):
        if value:
            where.append("p.national_id_search=%s"); params.append(value)
    for value in (phone, demo_phone):
        if value and len(value) >= 7:
            where.append("regexp_replace(COALESCE(p.phone,''),'[^0-9]','','g') LIKE %s"); params.append("%" + value[-9:] + "%")
    if birth:
        where.append("p.birth_date=%s"); params.append(birth)
    name_expr = "TRANSLATE(UPPER(COALESCE(p.name_search,p.name,'')),'ÁÉÍÓÚÜÑZ','AEIOUUNS')"
    tokens = q_tokens or demo_tokens
    if tokens:
        parts = []
        for token in tokens[:6]:
            parts.append(name_expr + " LIKE %s"); params.append("%" + token + "%")
        where.append("(" + " OR ".join(parts) + ")")
    if not where:
        return []
    cur.execute("""
        SELECT p.id,p.name,p.name_search,p.national_id,p.national_id_search,p.birth_date,p.phone,p.email,p.address,p.merged_into_patient_id
        FROM public.patients p
        WHERE p.deleted_at IS NULL AND (""" + " OR ".join(where) + ") ORDER BY COALESCE(p.updated_at,p.created_at,'') DESC LIMIT %s", tuple(params + [max(30, min(120, int(limit or 30) * 4))]))
    rows, seen = [], set()
    for raw in cur.fetchall() or []:
        row = _dict_row(cur, raw)
        canonical_id = _clean(row.get("merged_into_patient_id"), 120) or _clean(row.get("id"), 120)
        if not canonical_id or canonical_id in seen:
            continue
        if canonical_id != _clean(row.get("id"), 120):
            canonical = _patient_row(cur, canonical_id)
            if canonical: row = canonical
        row.update(_history_summary(cur, row["id"]))
        score, reasons = _candidate_score(row, demo, query)
        if score <= 0: continue
        row["match_score"], row["match_reasons"] = score, reasons
        rows.append(row); seen.add(str(row["id"]))
    rows.sort(key=lambda r: (int(r.get("match_score") or 0), int(r.get("history_date_count") or 0), _clean(r.get("last_history_date"), 20)), reverse=True)
    return rows[:max(1, min(int(limit or 30), 40))]


class _HistoryLinkIn(core.BaseModel):
    reception_patient_id: int
    clinical_patient_id: str


@app.get("/api/historia-identity/status/{reception_patient_id}")
def historia_identity_status(reception_patient_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    try:
        return _prepare_identity(db, reception_patient_id, auto_link=False, sync=False)
    except core.HTTPException:
        raise
    except Exception as exc:
        return {"ok": False, "reachable": False, "linked": False, "history_date_count": 0, "last_history_date": "", "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


@app.post("/api/historia-identity/prepare/{reception_patient_id}")
def historia_identity_prepare(reception_patient_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    try:
        result = _prepare_identity(db, reception_patient_id, auto_link=True, sync=True)
        if result.get("auto_linked") or result.get("demographics_changed") or result.get("warnings"):
            try:
                core.audit(db, user, "historia_identity_prepare", json.dumps({"reception_patient_id": reception_patient_id, "auto_linked": bool(result.get("auto_linked")), "duplicate_exact_id_resolved": bool(result.get("duplicate_exact_id_resolved")), "changes": result.get("demographics_changed") or {}, "warnings": result.get("warnings") or []}, ensure_ascii=False))
                db.commit()
            except Exception:
                pass
        return result
    except core.HTTPException:
        raise
    except Exception as exc:
        return {"ok": False, "reachable": False, "linked": False, "history_date_count": 0, "last_history_date": "", "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


@app.post("/api/historia-identity/sync/{reception_patient_id}")
def historia_identity_sync(reception_patient_id: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    return historia_identity_prepare(reception_patient_id, db, user)


@app.get("/api/historia-identity/search")
def historia_identity_search(q: str = "", reception_patient_id: int = 0, limit: int = 30, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    query = _clean(q, 160)
    demo = {"name": query, "birth_date": "", "phone": query, "national_id": query}
    if reception_patient_id:
        demo = _demographics(_reception_patient(db, reception_patient_id))
    try:
        conn = _connect_public()
        try:
            rows = _search_candidates(conn.cursor(), demo, query, limit)
            return {"ok": True, "reachable": True, "reception_patient_id": int(reception_patient_id or 0), "results": [{"id": r.get("id"), "name": r.get("name"), "national_id": r.get("national_id"), "birth_date": r.get("birth_date"), "phone": r.get("phone"), "email": r.get("email"), "address": r.get("address"), "history_date_count": int(r.get("history_date_count") or 0), "last_history_date": r.get("last_history_date") or "", "match_score": int(r.get("match_score") or 0), "match_reasons": r.get("match_reasons") or []} for r in rows]}
        finally:
            conn.close()
    except core.HTTPException:
        raise
    except Exception as exc:
        return {"ok": False, "reachable": False, "results": [], "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


@app.post("/api/historia-identity/link")
def historia_identity_link(data: _HistoryLinkIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    patient = _reception_patient(db, data.reception_patient_id)
    demo = _demographics(patient)
    clinical_id = _clean(data.clinical_patient_id, 120)
    if not clinical_id:
        raise core.HTTPException(400, "Falta la ficha clínica")
    conn = _connect_public()
    try:
        cur = conn.cursor()
        target = _patient_row(cur, clinical_id)
        if not target:
            raise core.HTTPException(404, "La ficha seleccionada ya no existe")
        reception_ident, target_ident = _usable_id(demo.get("national_id")), _usable_id(target.get("national_id"))
        if reception_ident and target_ident and reception_ident != target_ident:
            raise core.HTTPException(409, "La ficha seleccionada tiene otra cédula/identificación. Revise antes de vincular.")
        previous = _linked_patient(cur, patient.id)
        _upsert_link(cur, patient.id, target["id"], "reception_manual_verified")
        changes, warnings = _sync_demographics(cur, target["id"], demo)
        conn.commit()
        linked = _linked_patient(cur, patient.id)
        try:
            core.audit(db, user, "historia_identity_manual_link", json.dumps({"reception_patient_id": int(patient.id), "previous_clinical_patient_id": (previous or {}).get("id") or "", "clinical_patient_id": target["id"], "changes": changes, "warnings": warnings}, ensure_ascii=False))
            db.commit()
        except Exception:
            pass
        return {"ok": True, "reachable": True, "linked": True, "reception_patient_id": int(patient.id), "clinical_patient": linked, "history_date_count": int((linked or {}).get("history_date_count") or 0), "last_history_date": _clean((linked or {}).get("last_history_date"), 20), "warnings": warnings}
    finally:
        conn.close()


V4613_CSS = r"""
.v4613-history-card{margin:12px 0;padding:12px 14px;border:1px solid #cfe0ee;border-radius:13px;background:#f7fbff;color:#274a69;display:flex;align-items:center;justify-content:space-between;gap:14px}.v4613-history-card.warn{background:#fff8ea;border-color:#efd39d}.v4613-history-card.error{background:#fff4f2;border-color:#e6b3aa}.v4613-history-copy{display:flex;flex-direction:column;gap:3px;min-width:0}.v4613-history-copy b{font-size:13px;color:#183d5f}.v4613-history-copy small{font-size:11px;color:#687d91}.v4613-history-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}.v4613-history-count{font-size:18px;font-weight:900;color:#245f8b;min-width:24px;text-align:center}.v4613-btn{border:0;border-radius:10px;background:#2475d0;color:#fff;font-weight:800;padding:9px 12px;cursor:pointer;white-space:nowrap}.v4613-btn.secondary{background:#e8f0f8;color:#245273}.v4613-overlay{position:fixed;inset:0;z-index:2147483641;background:rgba(25,42,58,.44);display:flex;align-items:center;justify-content:center;padding:20px}.v4613-dialog{width:min(800px,96vw);max-height:86vh;overflow:auto;background:#fff;border-radius:18px;box-shadow:0 22px 70px rgba(0,0,0,.24);padding:20px}.v4613-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.v4613-head h3{margin:0 0 4px;color:#173b5d}.v4613-head p{margin:0;color:#718497;font-size:12px}.v4613-close{border:0;background:#eef2f6;border-radius:9px;padding:7px 10px;cursor:pointer;font-weight:800;color:#587087}.v4613-search{display:flex;gap:9px;margin:16px 0}.v4613-search input{flex:1;min-width:0;padding:11px 12px;border:1px solid #ccd9e5;border-radius:10px;font-size:13px}.v4613-search button{border:0;border-radius:10px;background:#2475d0;color:#fff;font-weight:800;padding:10px 18px;cursor:pointer}.v4613-results{display:flex;flex-direction:column;gap:9px}.v4613-result{border:1px solid #d8e3ec;border-radius:12px;padding:12px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}.v4613-result b{display:block;color:#183d5f;font-size:13px}.v4613-result small{display:block;color:#718497;margin-top:3px}.v4613-result button{border:0;border-radius:9px;background:#1f8b55;color:#fff;font-weight:800;padding:9px 12px;cursor:pointer}.v4613-empty{padding:22px;text-align:center;border:1px dashed #d7e0e8;border-radius:11px;color:#718497}@media(max-width:650px){.v4613-history-card{align-items:flex-start;flex-direction:column}.v4613-history-actions{width:100%;justify-content:space-between}.v4613-search{flex-direction:column}.v4613-result{grid-template-columns:1fr}}
"""

V4613_JS = r"""
;(()=>{
 if(window.__v4613UnifiedHistoryIdentity)return;window.__v4613UnifiedHistoryIdentity=true;
 const text=v=>String(v??'').replace(/\s+/g,' ').trim(),norm=v=>text(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase(),esc=v=>text(v).replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m])),fmt=v=>{const s=text(v),m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s);return m?`${m[3]}/${m[2]}/${m[1]}`:s};
 const cache=new Map();
 async function call(url,opt={}){if(typeof window.api==='function')return window.api(url,opt);const r=await fetch(url,{cache:'no-store',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt}),d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.error||'Error al consultar Historia');return d}
 function roots(){const a=[];for(const e of document.querySelectorAll('#modal .patient-profile-modal,.modal .patient-profile-modal,.patient-profile-modal,#modal .attention-form,#modal .modal-content,.modal .attention-form'))if(e&&!a.includes(e))a.push(e);return a}
 function pid(host){if(!host)return 0;const d=Number(host.dataset?.patientId||host.getAttribute?.('data-patient-id')||0);if(d)return d;const scope=host.closest('#modal,.modal')||host;for(const e of scope.querySelectorAll('[onclick]')){const m=/(?:attentionFor|editPatient|openPatient|saveAttention|savePatient|savePatientAndReturnToAttention|editPatientFromAttention)\s*\(\s*(\d+)/.exec(String(e.getAttribute('onclick')||''));if(m)return Number(m[1]||0)}return 0}
 function label(host){return text(host.querySelector('.v4413-profile-identity b')?.textContent||host.querySelector('.v4413-profile-name h2')?.textContent||host.querySelector('h2')?.textContent||'')}
 function place(host,card){const c=host.querySelector('.v4417-continue-wrap');if(c){c.insertAdjacentElement('beforebegin',card);return}const t=host.querySelector('.v4413-profile-tabs');if(t){t.insertAdjacentElement('beforebegin',card);return}const f=host.querySelector('.form-grid,.attention-form,.modal-form-heading');if(f){f.insertAdjacentElement('afterend',card);return}host.prepend(card)}
 function close(){document.querySelector('.v4613-overlay')?.remove()}
 async function status(id,force=false){const old=cache.get(id);if(!force&&old&&Date.now()-old.at<5000)return old.data;const d=await call('/api/historia-identity/status/'+id);if(d?.ok!==false)cache.set(id,{at:Date.now(),data:d});return d}
 async function prepare(id){const d=await call('/api/historia-identity/prepare/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(d?.ok!==false)cache.set(id,{at:Date.now(),data:d});return d}
 async function search(id,initial=''){close();const o=document.createElement('div');o.className='v4613-overlay';o.innerHTML=`<div class="v4613-dialog"><div class="v4613-head"><div><h3>Buscar ficha en Historia Clínica</h3><p>Se comparan identificación, celular, fecha de nacimiento y nombres. Los nombres parecidos requieren confirmación manual.</p></div><button class="v4613-close">×</button></div><div class="v4613-search"><input autocomplete="off" placeholder="Cédula, apellidos y nombres o celular"><button>Buscar</button></div><div class="v4613-results"><div class="v4613-empty">Buscando candidatos del paciente…</div></div></div>`;document.body.appendChild(o);o.querySelector('.v4613-close').onclick=close;o.addEventListener('click',e=>{if(e.target===o)close()});const input=o.querySelector('input'),go=o.querySelector('.v4613-search button'),out=o.querySelector('.v4613-results');input.value=text(initial);
  const run=async()=>{out.innerHTML='<div class="v4613-empty">Buscando fichas…</div>';try{const d=await call('/api/historia-identity/search?reception_patient_id='+encodeURIComponent(id)+'&q='+encodeURIComponent(text(input.value))+'&limit=30');if(d?.ok===false)throw Error(d.error||'No se pudo consultar Historia');const rows=Array.isArray(d?.results)?d.results:[];if(!rows.length){out.innerHTML='<div class="v4613-empty">No encontré una ficha candidata. Revise el nombre o busque con otro dato.</div>';return}out.innerHTML='';for(const r of rows){const c=document.createElement('div');c.className='v4613-result';const n=Number(r.history_date_count||0),last=fmt(r.last_history_date||''),birth=fmt(r.birth_date||''),reasons=(Array.isArray(r.match_reasons)?r.match_reasons:[]).join(' · ');c.innerHTML=`<div><b>${esc(r.name||'SIN NOMBRE')}</b><small>${esc(r.national_id||'Sin identificación')}${r.phone?' · '+esc(r.phone):''}${birth?' · Nac. '+esc(birth):''}</small><small>${n===1?'1 fecha con historia clínica':n+' fechas con historias clínicas'}${last?' · Última: '+esc(last):''}</small>${reasons?'<small><b>Coincidencias:</b> '+esc(reasons)+'</small>':''}</div><button>Vincular esta ficha</button>`;c.querySelector('button').onclick=async()=>{const b=c.querySelector('button');b.disabled=true;b.textContent='Vinculando…';try{const l=await call('/api/historia-identity/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reception_patient_id:Number(id),clinical_patient_id:String(r.id)})});if(l?.ok===false)throw Error(l.error||'No se pudo vincular');cache.delete(id);close();await renderAll(true);if(typeof window.rpAlert==='function')window.rpAlert('Ficha vinculada correctamente.','Historia Clínica');else alert('Ficha vinculada correctamente.')}catch(e){b.disabled=false;b.textContent='Vincular esta ficha';alert(e.message||e)}};out.appendChild(c)}}catch(e){out.innerHTML=`<div class="v4613-empty">${esc(e.message||'No se pudo consultar Historia Clínica.')}</div>`}};go.onclick=run;input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();run()}});input.focus();run()}
 async function render(host,force=false){const id=pid(host);if(!id)return;for(const old of host.querySelectorAll('.v468-history-card,.v4611-history-card'))old.remove();let c=host.querySelector(':scope > .v4613-history-card');if(!c){c=document.createElement('div');c.className='v4613-history-card';place(host,c)}if(!force&&Number(c.dataset.pid||0)===id&&Date.now()-Number(c.dataset.at||0)<4500)return;c.dataset.pid=String(id);c.dataset.at=String(Date.now());c.className='v4613-history-card';c.innerHTML='<div class="v4613-history-copy"><b>Historia clínica</b><small>Consultando vínculo…</small></div>';try{const d=await status(id,force);if(!c.isConnected||Number(c.dataset.pid)!==id)return;if(d?.ok===false)throw Error(d.error||'Historia no disponible');const linked=!!d.linked,n=Number(d.history_date_count||0),last=fmt(d.last_history_date||'');if(linked){c.innerHTML=`<div class="v4613-history-copy"><b>Historia clínica vinculada</b><small>${n===1?'1 fecha con historia clínica':n+' fechas con historias clínicas'}${last?' · Última: '+esc(last):''}</small></div><div class="v4613-history-actions"><span class="v4613-history-count">${n}</span><button class="v4613-btn secondary">Revisar vínculo</button></div>`;c.querySelector('button').onclick=()=>search(id,label(host))}else{c.classList.add('warn');c.innerHTML='<div class="v4613-history-copy"><b>Historia clínica · SIN VÍNCULO</b><small>Busque la ficha correcta antes de guardar una consulta subsecuente.</small></div><div class="v4613-history-actions"><button class="v4613-btn">🔗 Buscar y vincular ficha</button></div>';c.querySelector('button').onclick=()=>search(id,label(host))}}catch(e){c.classList.add('error');c.innerHTML=`<div class="v4613-history-copy"><b>Historia clínica no disponible</b><small>${esc(e.message||'No se pudo consultar el vínculo.')}</small></div><div class="v4613-history-actions"><button class="v4613-btn secondary">Reintentar</button></div>`;c.querySelector('button').onclick=()=>{cache.delete(id);render(host,true)}}}
 async function renderAll(force=false){for(const h of roots())await render(h,force)}
 function isSub(body){const v=[body?.tipo,body?.attention_type];for(const r of (Array.isArray(body?.services)?body.services:[]))v.push(r?.tipo,r?.attention_type);for(const r of (Array.isArray(body?.items)?body.items:[]))v.push(r?.tipo,r?.attention_type);return v.some(x=>{const n=norm(x);return n==='S'||n==='SUBSECUENTE'})}
 function gate(){const base=window.api;if(typeof base!=='function'||base.__v4613IdentityGate)return;const w=async function(url,opt={}){const u=String(url||'');if((u==='/api/visits/batch-payment'||u==='/api/visits/batch')){let body={};try{body=JSON.parse(String(opt?.body||'{}'))}catch(_e){}if(isSub(body)){const id=Number(body?.patient_id||pid(roots()[0])||0);if(id){let pre=null;try{pre=await prepare(id)}catch(_e){pre={ok:false,reachable:false}}if(pre?.ok!==false&&pre?.reachable!==false&&!pre?.linked){await search(id,text(pre.reception_name||''));const e=new Error('__HISTORIA_LINK_REQUIRED__');e.__historiaLinkRequired=true;throw e}}}}return base.apply(this,arguments)};w.__v4613IdentityGate=true;window.api=w}
 function sync(name){const base=window[name];if(typeof base!=='function'||base.__v4613HistorySync)return;const w=async function(){const id=Number(arguments[0]||pid(roots()[0])||0),out=await base.apply(this,arguments);if(id){cache.delete(id);setTimeout(async()=>{try{await call('/api/historia-identity/sync/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});cache.delete(id);renderAll(true)}catch(_e){}},80)}return out};w.__v4613HistorySync=true;window[name]=w}
 let timer=0;function boot(){gate();['savePatient','savePatientAndReturnToAttention'].forEach(sync);clearTimeout(timer);timer=setTimeout(()=>renderAll(false),60)}new MutationObserver(boot).observe(document.documentElement,{childList:true,subtree:true});document.addEventListener('click',()=>setTimeout(boot,50),true);window.addEventListener('focus',()=>renderAll(true));if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();setTimeout(boot,250);setTimeout(boot,900);
})();
"""

core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4613_CSS
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4613_JS


@app.get("/api/v4613/health")
def v4613_health(user=core.Depends(core.current_user)):
    return {"ok": True, "version": APP_VERSION, "identity_ui_single_component": True, "history_cloud_schema": "public", "legacy_historia_schema_operational": False, "subsequent_waits_for_identity_preflight": True, "offline_reception_fallback_preserved": True, "failed_identity_results_cached": False, "fuzzy_name_candidates": True, "birth_date_candidate_search": True, "exact_id_duplicate_safe_resolution": True, "demographics_blank_never_overwrites": True, "clinical_notes_exposed_to_reception": False, "waiting_queue_contract": ["patient_status", "reception_turn"]}
