from __future__ import annotations

import json
import re
import ssl
import threading
import unicodedata
from datetime import date, datetime
from pathlib import Path

import core_runtime as core
import historia_bridge

app = core.app
_VERSION_DOC = json.loads(
    Path(__file__).with_name("recepcion-version.json").read_text(encoding="utf-8-sig")
)
APP_VERSION = str(_VERSION_DOC.get("version") or "").strip()
if not APP_VERSION:
    raise RuntimeError("recepcion-version.json no contiene una versión válida")
core.APP_VERSION = APP_VERSION

HISTORIA_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_VALIDATED = set()

_PLACEHOLDER_IDS = {
    "X", "XX", "XXX", "XXXX", "XXXXX", "TESTIGO", "QUEVEDO", "LAMANA",
    "ECUASANITAS", "TJ", "N/A", "NA", "SINID", "SINCEDULA",
}


def _clean(value, limit=500):
    return str(value or "").strip()[:limit]


def _norm_text(value):
    raw = unicodedata.normalize("NFD", _clean(value, 500))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", raw).strip().upper()


def _fuzzy_text(value):
    # Equivalencias conservadoras para errores frecuentes del archivo legado.
    # BASURTO/BAZURTO debe ser encontrable, pero nunca se autovincula sólo por nombre.
    raw = _norm_text(value)
    return raw.replace("Z", "S")


def _norm_id(value):
    return re.sub(r"[^A-Z0-9]", "", _norm_text(value))


def _usable_id(value):
    ident = _norm_id(value)
    if not ident or ident in _PLACEHOLDER_IDS:
        return ""
    if len(ident) < 6:
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
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    return m.group(0) if m else raw[:10]


def _endpoint_id(host):
    label = _clean(host, 255).lower().split(".", 1)[0]
    if label.endswith("-pooler"):
        label = label[:-7]
    return label


def _connect_public():
    """Única conexión operativa de Recepción hacia Historia: public.*."""
    url = historia_bridge._database_url()
    if not url:
        raise RuntimeError("Historia Clínica no está configurada en esta PC")
    cfg = historia_bridge._parse_pg_url(url)
    if _endpoint_id(cfg.get("host")) != HISTORIA_ENDPOINT_ID:
        raise RuntimeError("Se bloqueó una conexión que no corresponde al Neon de Historia Clínica")
    from pg8000 import dbapi
    conn = dbapi.connect(
        user=cfg["user"], password=cfg["password"], host=cfg["host"],
        port=cfg["port"], database=cfg["database"],
        ssl_context=ssl.create_default_context(), timeout=12,
    )
    key = (str(cfg["host"]).lower(), int(cfg["port"]), str(cfg["database"]), str(cfg["user"]))
    try:
        cur = conn.cursor()
        cur.execute("SET search_path TO public")
        if key not in _SCHEMA_VALIDATED:
            with _SCHEMA_LOCK:
                if key not in _SCHEMA_VALIDATED:
                    cur.execute("""
                        SELECT table_name,column_name
                        FROM information_schema.columns
                        WHERE table_schema='public'
                          AND table_name IN ('patients','encounters','patient_links')
                    """)
                    found = {}
                    for table, column in cur.fetchall() or []:
                        found.setdefault(str(table), set()).add(str(column))
                    required = {
                        "patients": {"id","name","name_search","birth_date","phone","national_id","national_id_search","email","deleted_at","cloud_updated_at"},
                        "encounters": {"id","patient_id","encounter_date","note_status","deleted_at","cloud_updated_at"},
                        "patient_links": {"reception_patient_id","clinical_patient_id","matched_by","verified","deleted_at","cloud_updated_at"},
                    }
                    missing = {table: sorted(cols-found.get(table,set())) for table, cols in required.items() if not cols.issubset(found.get(table,set()))}
                    if missing:
                        raise RuntimeError("El esquema canónico de Historia está incompleto: " + json.dumps(missing, ensure_ascii=False))
                    _SCHEMA_VALIDATED.add(key)
        conn.commit()
        return conn
    except Exception:
        try: conn.close()
        except Exception: pass
        raise


# Todo el puente de nube queda fijado al esquema clínico canónico.
# No existe fallback operativo al antiguo schema historia.*.
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
        "name": re.sub(
            r"\s+", " ", _clean(getattr(patient, "nombre", ""), 260)
        ).strip().upper(),
        "birth_date": _iso_date(getattr(patient, "fecha_nacimiento", None)),
        "address": _clean(getattr(patient, "lugar", ""), 400),
        "phone": _clean(getattr(patient, "celular", ""), 120),
        "national_id": _clean(getattr(patient, "cedula", ""), 120),
        "email": _clean(getattr(patient, "correo", ""), 180).lower(),
    }


def _dict_row(cur, row):
    if not row:
        return None
    names = [str(col[0]) for col in cur.description]
    return dict(zip(names, row))


def _history_summary(cur, clinical_patient_id):
    cur.execute(
        """
        SELECT
          COUNT(DISTINCT CASE
            WHEN e.deleted_at IS NULL
             AND COALESCE(e.note_status,'signed') <> 'draft'
             AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL
            THEN e.encounter_date END) AS date_count,
          MAX(CASE
            WHEN e.deleted_at IS NULL
             AND COALESCE(e.note_status,'signed') <> 'draft'
             AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL
            THEN e.encounter_date END) AS last_date
        FROM public.encounters e
        WHERE e.patient_id=%s
        """,
        (str(clinical_patient_id),),
    )
    row = cur.fetchone() or (0, None)
    return {
        "history_date_count": int(row[0] or 0),
        "last_history_date": _clean(row[1], 20),
    }


def _patient_row(cur, clinical_patient_id):
    cur.execute(
        """
        SELECT id,name,name_search,national_id,national_id_search,birth_date,
               phone,email,address,merged_into_patient_id
        FROM public.patients
        WHERE id=%s AND deleted_at IS NULL
        LIMIT 1
        """,
        (str(clinical_patient_id),),
    )
    row = _dict_row(cur, cur.fetchone())
    if not row:
        return None
    merged = _clean(row.get("merged_into_patient_id"), 120)
    if merged and merged != str(row["id"]):
        cur.execute(
            """
            SELECT id,name,name_search,national_id,national_id_search,birth_date,
                   phone,email,address,merged_into_patient_id
            FROM public.patients
            WHERE id=%s AND deleted_at IS NULL
            LIMIT 1
            """,
            (merged,),
        )
        canonical = _dict_row(cur, cur.fetchone())
        if canonical:
            row = canonical
    row.update(_history_summary(cur, row["id"]))
    return row


def _linked_patient(cur, reception_patient_id):
    cur.execute(
        """
        SELECT l.clinical_patient_id,l.matched_by,l.verified
        FROM public.patient_links l
        WHERE l.reception_patient_id=%s
          AND l.deleted_at IS NULL
        LIMIT 1
        """,
        (str(reception_patient_id),),
    )
    link = _dict_row(cur, cur.fetchone())
    if not link:
        return None
    row = _patient_row(cur, link["clinical_patient_id"])
    if not row:
        return None
    row["matched_by"] = link.get("matched_by")
    row["verified"] = link.get("verified")
    return row






def _upsert_link(cur, reception_patient_id, clinical_patient_id, matched_by):
    stamp = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO public.patient_links(
          reception_patient_id,clinical_patient_id,matched_by,verified,
          verified_at,created_at,updated_at,deleted_at,cloud_updated_at
        )
        VALUES(%s,%s,%s,1,%s,%s,%s,NULL,now())
        ON CONFLICT(reception_patient_id) DO UPDATE SET
          clinical_patient_id=EXCLUDED.clinical_patient_id,
          matched_by=EXCLUDED.matched_by,
          verified=1,
          verified_at=EXCLUDED.verified_at,
          updated_at=EXCLUDED.updated_at,
          deleted_at=NULL,
          cloud_updated_at=now()
        """,
        (
            str(reception_patient_id),
            str(clinical_patient_id),
            _clean(matched_by, 80),
            stamp,
            stamp,
            stamp,
        ),
    )


def _sync_demographics(cur, clinical_patient_id, demo):
    before = _patient_row(cur, clinical_patient_id)
    if not before:
        raise RuntimeError("La ficha vinculada ya no existe en Historia Clínica")
    changes = {}
    warnings = []

    wanted_id = _clean(demo.get("national_id"), 120)
    wanted_id_search = _usable_id(wanted_id)
    current_id = _usable_id(before.get("national_id_search") or before.get("national_id"))
    if wanted_id_search and wanted_id_search != current_id:
        cur.execute("""SELECT id,name,birth_date FROM public.patients
                       WHERE deleted_at IS NULL AND national_id_search=%s AND id<>%s LIMIT 8""",
                    (wanted_id_search, str(clinical_patient_id)))
        conflicts = [_dict_row(cur, r) for r in (cur.fetchall() or [])]
        if conflicts:
            warnings.append("La cédula/identificación no se actualizó porque ya pertenece a otra ficha de Historia.")
        elif current_id:
            warnings.append("La identificación de Recepción difiere de Historia; no se cambió automáticamente.")
        else:
            changes["national_id"] = wanted_id
            changes["national_id_search"] = wanted_id_search

    wanted_name = _clean(demo.get("name"), 260)
    current_name = _clean(before.get("name"), 260)
    if wanted_name and _norm_text(wanted_name) != _norm_text(current_name):
        if current_name:
            warnings.append("El nombre de Recepción difiere de Historia; se conservó el nombre clínico existente.")
        else:
            changes["name"] = wanted_name
            changes["name_search"] = _norm_text(wanted_name)

    wanted_birth = _iso_date(demo.get("birth_date"))
    current_birth = _iso_date(before.get("birth_date"))
    if wanted_birth and wanted_birth != current_birth:
        if current_birth:
            warnings.append("La fecha de nacimiento difiere; se conservó la registrada en Historia.")
        else:
            changes["birth_date"] = wanted_birth

    for field, column, limit in (("address","address",400),("phone","phone",120),("email","email",180)):
        wanted = _clean(demo.get(field), limit)
        current = _clean(before.get(column), limit)
        if wanted and wanted != current:
            changes[column] = wanted

    if changes:
        stamp = datetime.now().isoformat(timespec="seconds")
        assignments, values = [], []
        for column, value in changes.items():
            assignments.append(f'"{column}"=%s'); values.append(value)
        assignments.extend(["updated_at=%s", "cloud_updated_at=now()"])
        values.extend([stamp, str(clinical_patient_id)])
        cur.execute("UPDATE public.patients SET " + ",".join(assignments) + " WHERE id=%s AND deleted_at IS NULL", tuple(values))
    return changes, warnings



def _reception_patient_update_payload(patient, *, extranjero: bool) -> dict:
    return {
        "patient_id": int(patient.id),
        "extranjero": bool(extranjero),
        "cedula": getattr(patient, "cedula", None),
        "nombre": getattr(patient, "nombre", None),
        "fecha_nacimiento": getattr(patient, "fecha_nacimiento", None),
        "celular": getattr(patient, "celular", None),
        "correo": getattr(patient, "correo", None),
        "lugar": getattr(patient, "lugar", None),
        "notas": getattr(patient, "notas", None),
    }


def _correct_reception_identification_from_history(db, patient, clinical_patient, user) -> dict:
    """Corrige exclusivamente la ficha administrativa de Recepción.

    Solo se ejecuta con una ficha de Historia ya vinculada/confirmada. Historia
    nunca es modificada por esta función y el doctor no participa en la corrección.
    """
    target_raw = _clean((clinical_patient or {}).get("national_id"), 120)
    target_search = _clean((clinical_patient or {}).get("national_id_search"), 120)
    target_key = _usable_id(target_search or target_raw)
    if not target_key:
        return {}
    if not target_raw:
        target_raw = target_search

    current_raw = _clean(getattr(patient, "cedula", ""), 120)
    current_key = _usable_id(current_raw)
    if current_key == target_key:
        return {}

    # Nunca crear dos pacientes de Recepción con la misma identificación.
    duplicate = db.scalar(
        core.select(core.Patient).where(
            core.Patient.cedula == target_raw,
            core.Patient.id != int(patient.id),
        )
    )
    if duplicate:
        raise core.HTTPException(
            409,
            "La cédula correcta de Historia ya está registrada en otra ficha de Recepción. "
            "Revise ese duplicado antes de vincular; no se cambió ningún dato.",
        )

    before = current_raw
    patient.cedula = target_raw

    digits = re.sub(r"\D", "", target_raw)
    extranjero = not (
        len(digits) == 10
        and getattr(core, "valid_ecuadorian_cedula", lambda _v: False)(digits)
    )

    detail = {
        "reception_patient_id": int(patient.id),
        "before": before,
        "after": target_raw,
        "source": "historia_verified_identity",
        "clinical_patient_id": _clean((clinical_patient or {}).get("id"), 120),
    }

    if core.is_offline_db(db):
        core.add_queue(
            db,
            "patient.update",
            "patient",
            _reception_patient_update_payload(patient, extranjero=extranjero),
            user.username,
            int(patient.id),
        )
        core.audit(
            db,
            user,
            "corregir_cedula_desde_historia_offline",
            json.dumps(detail, ensure_ascii=False),
        )
        db.commit()
    else:
        core.audit(
            db,
            user,
            "corregir_cedula_desde_historia",
            json.dumps(detail, ensure_ascii=False),
        )
        db.commit()
        core.mirror_patient_to_local(patient)

    return detail


def _prepare_identity(db, reception_patient_id, *, sync=True, user=None):
    patient = _reception_patient(db, reception_patient_id)
    demo = _demographics(patient)
    conn = _connect_public()
    try:
        cur = conn.cursor()
        linked = _linked_patient(cur, patient.id)
        changed, warnings = {}, []
        reception_correction = {}
        if linked is not None and sync:
            reception_correction = _correct_reception_identification_from_history(
                db, patient, linked, user
            )
            demo = _demographics(patient)
            _upsert_link(cur, patient.id, linked["id"], linked.get("matched_by") or "reception_verified")
            changed, warnings = _sync_demographics(cur, linked["id"], demo)
            conn.commit()
            linked = _linked_patient(cur, patient.id)
        return {
            "ok": True,
            "reachable": True,
            "reception_patient_id": int(patient.id),
            "reception_name": demo["name"],
            "reception_birth_date": demo["birth_date"],
            "linked": bool(linked),
            "auto_linked": False,
            "duplicate_exact_id_resolved": False,
            "clinical_patient": linked,
            "history_date_count": int((linked or {}).get("history_date_count") or 0),
            "last_history_date": _clean((linked or {}).get("last_history_date"), 20),
            "demographics_changed": changed,
            "reception_identification_corrected": reception_correction,
            "warnings": warnings,
        }
    finally:
        try: conn.close()
        except Exception: pass


def _candidate_score(row, demo, query):
    score = 0
    reasons = []

    wanted_id = _usable_id(demo.get("national_id"))
    row_id = _usable_id(row.get("national_id_search") or row.get("national_id"))
    if wanted_id and row_id and wanted_id == row_id:
        score += 120
        reasons.append("misma identificación")

    wanted_phone = _norm_phone(demo.get("phone"))
    row_phone = _norm_phone(row.get("phone"))
    if wanted_phone and row_phone and wanted_phone[-9:] == row_phone[-9:]:
        score += 80
        reasons.append("mismo celular")

    wanted_birth = _iso_date(demo.get("birth_date"))
    row_birth = _iso_date(row.get("birth_date"))
    if wanted_birth and row_birth and wanted_birth == row_birth:
        score += 70
        reasons.append("misma fecha de nacimiento")

    wanted_name = _fuzzy_text(demo.get("name"))
    row_name = _fuzzy_text(row.get("name_search") or row.get("name"))
    if wanted_name and row_name:
        if wanted_name == row_name:
            score += 75
            reasons.append("mismo nombre")
        else:
            tokens = [t for t in wanted_name.split() if len(t) >= 2]
            matches = sum(1 for token in tokens if token in row_name)
            if matches:
                score += min(55, matches * 11)
                if matches >= max(2, len(tokens) - 1):
                    reasons.append("nombre muy parecido")

    q = _fuzzy_text(query)
    if q:
        q_tokens = [t for t in q.split() if len(t) >= 2]
        matches = sum(1 for token in q_tokens if token in row_name)
        score += min(30, matches * 6)

    history_count = int(row.get("history_date_count") or 0)
    if history_count > 0:
        score += min(15, history_count)
    return score, reasons


def _search_candidates(cur, demo, query, limit):
    ident = _usable_id(query)
    phone = _norm_phone(query)
    q_norm = _fuzzy_text(query)
    q_tokens = [t for t in q_norm.split() if len(t) >= 2]
    demo_tokens = [t for t in _fuzzy_text(demo.get("name")).split() if len(t) >= 2]
    birth = _iso_date(demo.get("birth_date"))
    demo_id = _usable_id(demo.get("national_id"))
    demo_phone = _norm_phone(demo.get("phone"))

    where = []
    params = []
    if ident:
        where.append("p.national_id_search=%s")
        params.append(ident)
    if demo_id:
        where.append("p.national_id_search=%s")
        params.append(demo_id)
    for value in [phone, demo_phone]:
        if value and len(value) >= 7:
            where.append(
                "regexp_replace(COALESCE(p.phone,''),'[^0-9]','','g') LIKE %s"
            )
            params.append("%" + value[-9:] + "%")
    if birth:
        where.append("p.birth_date=%s")
        params.append(birth)

    name_expr = (
        "TRANSLATE(UPPER(COALESCE(p.name_search,p.name,'')),"
        "'ÁÉÍÓÚÜÑZ','AEIOUUNS')"
    )
    tokens = q_tokens or demo_tokens
    if tokens:
        token_parts = []
        for token in tokens[:6]:
            token_parts.append(name_expr + " LIKE %s")
            params.append("%" + token + "%")
        # No exigimos todos los tokens: así BASURTO/BAZURTO y un nombre
        # incompleto siguen siendo candidatos manuales.
        where.append("(" + " OR ".join(token_parts) + ")")

    if not where:
        return []

    sql_limit = max(30, min(120, int(limit or 30) * 4))
    cur.execute(
        """
        SELECT p.id,p.name,p.name_search,p.national_id,p.national_id_search,
               p.birth_date,p.phone,p.email,p.address,p.merged_into_patient_id
        FROM public.patients p
        WHERE p.deleted_at IS NULL
          AND ("""
        + " OR ".join(where)
        + """)
        ORDER BY COALESCE(p.updated_at,p.created_at,'') DESC
        LIMIT %s
        """,
        tuple(params + [sql_limit]),
    )
    rows = []
    seen = set()
    for raw in cur.fetchall() or []:
        row = _dict_row(cur, raw)
        canonical_id = _clean(row.get("merged_into_patient_id"), 120) or _clean(row.get("id"), 120)
        if not canonical_id or canonical_id in seen:
            continue
        if canonical_id != _clean(row.get("id"), 120):
            canonical = _patient_row(cur, canonical_id)
            if canonical:
                row = canonical
        row.update(_history_summary(cur, row["id"]))
        score, reasons = _candidate_score(row, demo, query)
        if score <= 0:
            continue
        row["match_score"] = score
        row["match_reasons"] = reasons
        rows.append(row)
        seen.add(str(row["id"]))

    rows.sort(
        key=lambda r: (
            int(r.get("match_score") or 0),
            int(r.get("history_date_count") or 0),
            _clean(r.get("last_history_date"), 20),
        ),
        reverse=True,
    )
    return rows[: max(1, min(int(limit or 30), 40))]


class _HistoryLinkIn(core.BaseModel):
    reception_patient_id: int
    clinical_patient_id: str


@app.get("/api/historia-identity/status/{reception_patient_id}")
def historia_identity_status(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    try:
        return _prepare_identity(
            db, reception_patient_id, sync=False
        )
    except core.HTTPException:
        raise
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "linked": False,
            "history_date_count": 0,
            "last_history_date": "",
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
        }


@app.post("/api/historia-identity/prepare/{reception_patient_id}")
def historia_identity_prepare(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    try:
        result = _prepare_identity(
            db, reception_patient_id, sync=True, user=user
        )
        if (
            result.get("auto_linked")
            or result.get("demographics_changed")
            or result.get("warnings")
        ):
            try:
                core.audit(
                    db,
                    user,
                    "historia_identity_prepare",
                    json.dumps(
                        {
                            "reception_patient_id": reception_patient_id,
                            "auto_linked": bool(result.get("auto_linked")),
                            "duplicate_exact_id_resolved": bool(
                                result.get("duplicate_exact_id_resolved")
                            ),
                            "changes": result.get("demographics_changed") or {},
                            "warnings": result.get("warnings") or [],
                        },
                        ensure_ascii=False,
                    ),
                )
                db.commit()
            except Exception:
                pass
        return result
    except core.HTTPException:
        raise
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "linked": False,
            "history_date_count": 0,
            "last_history_date": "",
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
        }


@app.post("/api/historia-identity/sync/{reception_patient_id}")
def historia_identity_sync(
    reception_patient_id: int,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    return historia_identity_prepare(reception_patient_id, db, user)


@app.get("/api/historia-identity/search")
def historia_identity_search(
    q: str = "",
    reception_patient_id: int = 0,
    limit: int = 30,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    query = _clean(q, 160)
    demo = {
        "name": query,
        "birth_date": "",
        "phone": query,
        "national_id": query,
    }
    if reception_patient_id:
        patient = _reception_patient(db, reception_patient_id)
        demo = _demographics(patient)

    try:
        conn = _connect_public()
        try:
            cur = conn.cursor()
            rows = _search_candidates(cur, demo, query, limit)
            return {
                "ok": True,
                "reachable": True,
                "reception_patient_id": int(reception_patient_id or 0),
                "results": [
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "national_id": r.get("national_id"),
                        "birth_date": r.get("birth_date"),
                        "phone": r.get("phone"),
                        "email": r.get("email"),
                        "address": r.get("address"),
                        "history_date_count": int(r.get("history_date_count") or 0),
                        "last_history_date": r.get("last_history_date") or "",
                        "match_score": int(r.get("match_score") or 0),
                        "match_reasons": r.get("match_reasons") or [],
                    }
                    for r in rows
                ],
            }
        finally:
            conn.close()
    except core.HTTPException:
        raise
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "results": [],
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
        }


@app.post("/api/historia-identity/link")
def historia_identity_link(
    data: _HistoryLinkIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
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

        previous = _linked_patient(cur, patient.id)
        reception_correction = _correct_reception_identification_from_history(
            db, patient, target, user
        )
        # A partir de aquí la ficha administrativa de Recepción ya contiene la
        # identificación confirmada de Historia; ese es el dato que se enviará
        # al doctor y a los siguientes handoffs.
        demo = _demographics(patient)
        _upsert_link(
            cur, patient.id, target["id"], "reception_manual_verified"
        )
        changes, warnings = _sync_demographics(cur, target["id"], demo)
        conn.commit()
        linked = _linked_patient(cur, patient.id)

        try:
            core.audit(
                db,
                user,
                "historia_identity_manual_link",
                json.dumps(
                    {
                        "reception_patient_id": int(patient.id),
                        "previous_clinical_patient_id": (
                            (previous or {}).get("id") or ""
                        ),
                        "clinical_patient_id": target["id"],
                        "reception_identification_corrected": reception_correction,
                        "changes": changes,
                        "warnings": warnings,
                    },
                    ensure_ascii=False,
                ),
            )
            db.commit()
        except Exception:
            pass

        return {
            "ok": True,
            "reachable": True,
            "linked": True,
            "reception_patient_id": int(patient.id),
            "clinical_patient": linked,
            "history_date_count": int((linked or {}).get("history_date_count") or 0),
            "last_history_date": _clean((linked or {}).get("last_history_date"), 20),
            "reception_identification_corrected": reception_correction,
            "warnings": warnings,
        }
    finally:
        conn.close()



V4613_CSS = r"""
.v4613-history-card{
  margin:12px 0;padding:12px 14px;border:1px solid #cfe0ee;border-radius:13px;
  background:#f7fbff;color:#274a69;display:flex;align-items:center;
  justify-content:space-between;gap:14px
}
.v4613-history-card.warn{background:#fff8ea;border-color:#efd39d}
.v4613-history-card.error{background:#fff4f2;border-color:#e6b3aa}
.v4613-history-copy{display:flex;flex-direction:column;gap:3px;min-width:0}
.v4613-history-copy b{font-size:13px;color:#183d5f}
.v4613-history-copy small{font-size:11px;color:#687d91}
.v4613-history-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}
.v4613-history-count{font-size:18px;font-weight:900;color:#245f8b;min-width:24px;text-align:center}
.v4613-btn{border:0;border-radius:10px;background:#2475d0;color:#fff;font-weight:800;padding:9px 12px;cursor:pointer;white-space:nowrap}
.v4613-btn.secondary{background:#e8f0f8;color:#245273}
.v4613-overlay{position:fixed;inset:0;z-index:2147483641;background:rgba(25,42,58,.44);display:flex;align-items:center;justify-content:center;padding:20px}
.v4613-dialog{width:min(800px,96vw);max-height:86vh;overflow:auto;background:#fff;border-radius:18px;box-shadow:0 22px 70px rgba(0,0,0,.24);padding:20px}
.v4613-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.v4613-head h3{margin:0 0 4px;color:#173b5d}.v4613-head p{margin:0;color:#718497;font-size:12px}
.v4613-close{border:0;background:#eef2f6;border-radius:9px;padding:7px 10px;cursor:pointer;font-weight:800;color:#587087}
.v4613-search{display:flex;gap:9px;margin:16px 0}.v4613-search input{flex:1;min-width:0;padding:11px 12px;border:1px solid #ccd9e5;border-radius:10px;font-size:13px}.v4613-search button{border:0;border-radius:10px;background:#2475d0;color:#fff;font-weight:800;padding:10px 18px;cursor:pointer}
.v4613-results{display:flex;flex-direction:column;gap:9px}.v4613-result{border:1px solid #d8e3ec;border-radius:12px;padding:12px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}.v4613-result b{display:block;color:#183d5f;font-size:13px}.v4613-result small{display:block;color:#718497;margin-top:3px}.v4613-result button{border:0;border-radius:9px;background:#1f8b55;color:#fff;font-weight:800;padding:9px 12px;cursor:pointer}.v4613-empty{padding:22px;text-align:center;border:1px dashed #d7e0e8;border-radius:11px;color:#718497}
@media(max-width:650px){.v4613-history-card{align-items:flex-start;flex-direction:column}.v4613-history-actions{width:100%;justify-content:space-between}.v4613-search{flex-direction:column}.v4613-result{grid-template-columns:1fr}}
"""

V4613_JS = r"""
;(()=>{
  if(window.__v4613UnifiedHistoryIdentity)return;
  window.__v4613UnifiedHistoryIdentity=true;

  const text=v=>String(v??'').replace(/\s+/g,' ').trim();
  const norm=v=>text(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
  const esc=v=>text(v).replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]));
  const fmt=v=>{const s=text(v),m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s);return m?`${m[3]}/${m[2]}/${m[1]}`:s};
  const statusCache=new Map();
  let activePid=0;

  async function call(url,opt={}){
    if(typeof window.api==='function')return window.api(url,opt);
    const r=await fetch(url,{cache:'no-store',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(d.detail||d.error||'Error al consultar Historia');
    return d;
  }

  function modalRoots(){
    const roots=[];
    for(const el of document.querySelectorAll('#modal .patient-profile-modal,.modal .patient-profile-modal,.patient-profile-modal,#modal .attention-form-modal,.modal .attention-form-modal,.attention-form-modal')){
      if(el && !roots.includes(el))roots.push(el);
    }
    return roots;
  }
  function pidFrom(host){
    if(!host)return 0;
    const direct=Number(host.dataset?.patientId||host.getAttribute?.('data-patient-id')||0);
    if(direct)return direct;
    for(const el of host.querySelectorAll('[onclick]')){
      const raw=String(el.getAttribute('onclick')||'');
      const m=/(?:attentionFor|editPatient|openPatient|saveAttention|savePatient|savePatientAndReturnToAttention|editPatientFromAttention)\s*\(\s*(\d+)/.exec(raw);
      if(m)return Number(m[1]||0);
    }
    const modal=host.closest('#modal,.modal')||document.querySelector('#modal,.modal')||document;
    for(const el of modal.querySelectorAll('[onclick]')){
      const raw=String(el.getAttribute('onclick')||'');
      const m=/(?:attentionFor|editPatient|openPatient|saveAttention|savePatient|savePatientAndReturnToAttention|editPatientFromAttention)\s*\(\s*(\d+)/.exec(raw);
      if(m)return Number(m[1]||0);
    }
    return activePid||0;
  }
  function labelFrom(host){
    return text(
      host.querySelector('.v4413-profile-identity b')?.textContent||
      host.querySelector('.v4413-profile-name h2')?.textContent||
      host.querySelector('h2')?.textContent||''
    );
  }
  function place(host,card){
    const attentionStatus=host.querySelector('#attentionStatus');
    if(host.matches('.attention-form-modal')&&attentionStatus){attentionStatus.insertAdjacentElement('afterend',card);return}
    const continueWrap=host.querySelector('.v4417-continue-wrap');
    if(continueWrap){continueWrap.insertAdjacentElement('beforebegin',card);return}
    const tabs=host.querySelector('.v4413-profile-tabs');
    if(tabs){tabs.insertAdjacentElement('beforebegin',card);return}
    const form=host.querySelector('.form-grid,.attention-form,.modal-form-heading');
    if(form){form.insertAdjacentElement('afterend',card);return}
    host.prepend(card);
  }
  function closeSearch(){document.querySelector('.v4613-overlay')?.remove()}
  function clearPatientCache(pid){statusCache.delete(Number(pid||0))}

  async function status(pid,force=false){
    pid=Number(pid||0);if(!pid)return null;
    const cached=statusCache.get(pid);
    if(!force&&cached&&Date.now()-cached.at<20000)return cached.data;
    const d=await call('/api/historia-identity/status/'+pid);
    if(d?.ok!==false)statusCache.set(pid,{at:Date.now(),data:d});
    return d;
  }
  async function prepare(pid,force=false){
    pid=Number(pid||0);if(!pid)return null;
    if(!force){
      const cached=statusCache.get(pid);
      if(cached&&Date.now()-cached.at<4000&&cached.data?.linked)return cached.data;
    }
    const d=await call('/api/historia-identity/prepare/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(d?.ok!==false)statusCache.set(pid,{at:Date.now(),data:d});
    return d;
  }

  async function searchDialog(pid,initial=''){
    closeSearch();
    const overlay=document.createElement('div');overlay.className='v4613-overlay';
    overlay.innerHTML=`<div class="v4613-dialog"><div class="v4613-head"><div><h3>Buscar ficha en Historia Clínica</h3><p>Recepción compara identificación, celular, fecha de nacimiento y nombres. Los nombres parecidos se muestran para confirmación manual; nunca se autovinculan solos.</p></div><button class="v4613-close" type="button">×</button></div><div class="v4613-search"><input autocomplete="off" placeholder="Cédula, apellidos y nombres o celular"><button type="button">Buscar</button></div><div class="v4613-results"><div class="v4613-empty">Buscando candidatos del paciente…</div></div></div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('.v4613-close').onclick=closeSearch;
    overlay.addEventListener('click',e=>{if(e.target===overlay)closeSearch()});
    const input=overlay.querySelector('input'),go=overlay.querySelector('.v4613-search button'),results=overlay.querySelector('.v4613-results');
    input.value=text(initial);

    const run=async()=>{
      const q=text(input.value);
      results.innerHTML='<div class="v4613-empty">Buscando fichas…</div>';
      try{
        const out=await call('/api/historia-identity/search?reception_patient_id='+encodeURIComponent(pid)+'&q='+encodeURIComponent(q)+'&limit=30');
        if(out?.ok===false)throw Error(out.error||'No se pudo consultar Historia');
        const rows=Array.isArray(out?.results)?out.results:[];
        if(!rows.length){results.innerHTML='<div class="v4613-empty">No encontré una ficha candidata. Revise el nombre o busque con otro dato.</div>';return}
        results.innerHTML='';
        for(const r of rows){
          const card=document.createElement('div');card.className='v4613-result';
          const count=Number(r.history_date_count||0),last=fmt(r.last_history_date||''),birth=fmt(r.birth_date||'');
          const reasons=(Array.isArray(r.match_reasons)?r.match_reasons:[]).join(' · ');
          card.innerHTML=`<div><b>${esc(r.name||'SIN NOMBRE')}</b><small>${esc(r.national_id||'Sin identificación')}${r.phone?' · '+esc(r.phone):''}${birth?' · Nac. '+esc(birth):''}</small><small>${count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas'}${last?' · Última: '+esc(last):''}</small>${reasons?'<small><b>Coincidencias:</b> '+esc(reasons)+'</small>':''}</div><button type="button">Vincular esta ficha</button>`;
          card.querySelector('button').onclick=async()=>{
            const btn=card.querySelector('button');
            if(btn.dataset.confirm!=='1'){
              btn.dataset.confirm='1';btn.textContent='Confirmar vínculo';btn.style.background='#a96f18';
              const note=document.createElement('small');note.className='v4613-confirm-note';note.textContent='Confirma que esta es la ficha clínica correcta.';card.querySelector('div')?.appendChild(note);return;
            }
            btn.disabled=true;btn.textContent='Vinculando…';
            try{
              const linked=await call('/api/historia-identity/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reception_patient_id:Number(pid),clinical_patient_id:String(r.id)})});
              if(linked?.ok===false)throw Error(linked.error||'No se pudo vincular');
              statusCache.set(Number(pid),{at:Date.now(),data:linked});closeSearch();
              for(const host of modalRoots()){const c=host.querySelector(':scope > .v4613-history-card');if(c&&Number(c.dataset.pid||0)===Number(pid))c.dataset.settled='0'}
              renderAll(false);
              if(typeof window.rpAlert==='function'){
                const correction=linked?.reception_identification_corrected||{};
                const msg=correction.after
                  ? 'Ficha vinculada correctamente. Recepción corrigió la cédula a '+correction.after+'.'
                  : 'Ficha vinculada correctamente.';
                window.rpAlert(msg,'Historia Clínica');
              }
            }catch(err){btn.disabled=false;btn.dataset.confirm='0';btn.textContent='Vincular esta ficha';btn.style.background='';results.insertAdjacentHTML('afterbegin',`<div class="v4613-empty">${esc(err.message||'No se pudo vincular.')}</div>`)}
          };
          results.appendChild(card);
        }
      }catch(err){results.innerHTML=`<div class="v4613-empty">${esc(err.message||'No se pudo consultar Historia Clínica.')}</div>`}
    };
    go.onclick=run;input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();run()}});
    input.focus();run();
  }

  async function renderHost(host,force=false){
    const pid=pidFrom(host);if(!pid)return;
    const attentionModal=host.matches('.attention-form-modal');
    const attentionIsSubsequent=attentionModal&&(()=>{try{return typeof currentDetectedStatus==='function'&&norm(currentDetectedStatus())==='S'}catch(_e){return false}})();
    if(attentionModal&&!attentionIsSubsequent){host.querySelector(':scope > .v4613-history-card')?.remove();return}
    let card=host.querySelector(':scope > .v4613-history-card');
    if(!card){card=document.createElement('div');card.className='v4613-history-card';place(host,card)}
    if(Number(card.dataset.pid||0)===pid&&card.dataset.busy==='1')return;
    if(!force&&Number(card.dataset.pid||0)===pid&&card.dataset.settled==='1')return;
    card.dataset.pid=String(pid);card.dataset.at=String(Date.now());card.dataset.busy='1';card.dataset.settled='0';
    card.className='v4613-history-card';
    card.innerHTML='<div class="v4613-history-copy"><b>Historia clínica</b><small>Consultando vínculo…</small></div>';

    try{
      const d=await status(pid,force);
      if(!card.isConnected||Number(card.dataset.pid)!==pid)return;
      if(d?.ok===false)throw Error(d.error||'Historia no disponible');
      card.dataset.busy='0';card.dataset.settled='1';
      const linked=!!d?.linked,count=Number(d?.history_date_count||0),last=fmt(d?.last_history_date||'');
      if(linked){
        const linkedTitle=attentionModal?'✓ Vinculado con Historia Clínica':'Historia clínica vinculada';
        const cp=d?.clinical_patient||{};
        const identityLine=[text(cp.name||''),cp.national_id?'ID '+text(cp.national_id):''].filter(Boolean).join(' · ');
        const historyLine=(count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas')+(last?' · Última: '+last:'');
        const action=attentionModal?'':`<button type="button" class="v4613-btn secondary">Cambiar vínculo</button>`;
        card.innerHTML=`<div class="v4613-history-copy"><b>${linkedTitle}</b><small>${identityLine?esc(identityLine)+' · ':''}${esc(historyLine)}</small></div><div class="v4613-history-actions"><span class="v4613-history-count">${count}</span>${action}</div>`;
        if(!attentionModal)card.querySelector('button')?.addEventListener('click',()=>searchDialog(pid,labelFrom(host)));
      }else{
        card.classList.add('warn');
        const unlinkedTitle=attentionModal?'⚠ Sin vincular con Historia Clínica':'Historia clínica · SIN VÍNCULO';
        const linkButton=attentionModal?'Vincular con Historia Clínica':'🔗 Buscar y vincular ficha';
        card.innerHTML=`<div class="v4613-history-copy"><b>${unlinkedTitle}</b><small>Busque la ficha correcta antes de guardar una consulta subsecuente.</small></div><div class="v4613-history-actions"><button type="button" class="v4613-btn">${linkButton}</button></div>`;
        card.querySelector('button').onclick=()=>searchDialog(pid,labelFrom(host));
      }
    }catch(err){
      card.dataset.busy='0';card.dataset.settled='1';
      card.classList.add('error');
      card.innerHTML=`<div class="v4613-history-copy"><b>Historia clínica no disponible</b><small>${esc(err.message||'No se pudo consultar el vínculo.')}</small></div><div class="v4613-history-actions"><button type="button" class="v4613-btn secondary">Reintentar</button></div>`;
      card.querySelector('button').onclick=()=>{clearPatientCache(pid);renderHost(host,true)};
    }
  }

  function renderAll(force=false){
    for(const host of modalRoots())void renderHost(host,force);
  }

  function isSubsequent(body){
    const values=[body?.tipo,body?.attention_type];
    for(const row of (Array.isArray(body?.services)?body.services:[]))values.push(row?.tipo,row?.attention_type);
    for(const row of (Array.isArray(body?.items)?body.items:[]))values.push(row?.tipo,row?.attention_type);
    return values.some(v=>{const n=norm(v);return n==='S'||n==='SUBSECUENTE'});
  }

  function installSaveGate(){
    const base=window.api;
    if(typeof base!=='function'||base.__v4613IdentityGate)return;
    const wrapped=async function(url,opt={}){
      const u=String(url||'');
      if(u==='/api/visits/batch-payment'||u==='/api/visits/batch'){
        let body={};try{body=JSON.parse(String(opt?.body||'{}'))}catch(_e){}
        if(isSubsequent(body)){
          const pid=Number(body?.patient_id||pidFrom(modalRoots()[0])||0);
          if(pid){
            let pre=null;
            try{pre=await prepare(pid,true)}catch(_e){pre={ok:false,reachable:false}}
            if(pre?.ok!==false&&pre?.reachable!==false&&!pre?.linked){
              await searchDialog(pid,text(pre?.reception_name||''));
              const err=new Error('__HISTORIA_LINK_REQUIRED__');err.__historiaLinkRequired=true;throw err;
            }
            // Si Historia está realmente fuera de línea no se bloquea Recepción:
            // el outbox/LAN seguirá protegiendo el turno y el doctor conserva el fallback.
          }
        }
      }
      return base.apply(this,arguments);
    };
    wrapped.__v4613IdentityGate=true;wrapped.__v4613Base=base;window.api=wrapped;
  }

  function installPatientSync(name){
    const base=window[name];
    if(typeof base!=='function'||base.__v4613HistorySync)return;
    const wrapped=async function(){
      const pid=Number(arguments[0]||pidFrom(modalRoots()[0])||0);
      const out=await base.apply(this,arguments);
      if(pid){
        clearPatientCache(pid);
        setTimeout(async()=>{try{await call('/api/historia-identity/sync/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});clearPatientCache(pid);renderAll(true)}catch(_e){}},80);
      }
      return out;
    };
    wrapped.__v4613HistorySync=true;window[name]=wrapped;
  }

  function trackPatientOpener(name){
    const base=window[name];
    if(typeof base!=='function'||base.__v4614HistoryTracked)return;
    const wrapped=function(){
      const pid=Number(arguments[0]||0);
      if(pid)activePid=pid;
      const out=base.apply(this,arguments);
      Promise.resolve(out).finally(()=>{
        setTimeout(()=>renderAll(false),0);
        setTimeout(()=>renderAll(false),20);
      });
      return out;
    };
    wrapped.__v4614HistoryTracked=true;
    wrapped.__v4614Base=base;
    window[name]=wrapped;
  }

  let timer=0;
  function boot(){
    installSaveGate();
    ['savePatient','savePatientAndReturnToAttention'].forEach(installPatientSync);
    ['openPatient','attentionFor'].forEach(trackPatientOpener);
    clearTimeout(timer);timer=setTimeout(()=>renderAll(false),0);
  }
  new MutationObserver(boot).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('click',()=>{setTimeout(boot,0);setTimeout(boot,20)},true);
  window.addEventListener('focus',()=>renderAll(true));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(boot,250);setTimeout(boot,900);
})();
"""

core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4613_CSS
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4613_JS


@app.get("/api/v4613/health")
def v4613_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "identity_ui_single_component": True,
        "history_cloud_schema": "public",
        "legacy_historia_schema_operational": False,
        "subsequent_waits_for_identity_preflight": True,
        "offline_reception_fallback_preserved": True,
        "failed_identity_results_cached": False,
        "fuzzy_name_candidates": True,
        "birth_date_candidate_search": True,
        "exact_id_duplicate_safe_resolution": True,
        "demographics_blank_never_overwrites": True,
        "clinical_notes_exposed_to_reception": False,
        "waiting_queue_contract": ["patient_status", "reception_turn"],
        "history_panel_placeholder_immediate": True,
        "identity_render_parallel": True,
        "patient_open_id_tracked": True,
        "identity_status_cache_seconds": 20,
    }
