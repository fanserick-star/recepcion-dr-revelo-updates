from __future__ import annotations

import json
import re
import ssl
import unicodedata
from datetime import date, datetime

import core_runtime as core
import historia_bridge

app = core.app
APP_VERSION = "4.6.8"
core.APP_VERSION = APP_VERSION

HISTORIA_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"
_original_bridge_connect = getattr(historia_bridge, "_connect", None)


def _clean(value, limit=500):
    return str(value or "").strip()[:limit]


def _norm_text(value):
    raw = unicodedata.normalize("NFD", _clean(value, 500))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", raw).strip().upper()


def _norm_id(value):
    return re.sub(r"[^A-Z0-9]", "", _norm_text(value))


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
    return raw[:10]


def _endpoint_id(host):
    label = _clean(host, 255).lower().split(".", 1)[0]
    if label.endswith("-pooler"):
        label = label[:-7]
    return label


def _connect_public():
    """Conecta solamente al Neon dedicado de Historia y usa public.* canónico."""
    url = historia_bridge._database_url()
    if not url:
        raise RuntimeError("Historia Clínica no está configurada en esta PC")
    cfg = historia_bridge._parse_pg_url(url)
    if _endpoint_id(cfg.get("host")) != HISTORIA_ENDPOINT_ID:
        raise RuntimeError("Se bloqueó una conexión que no corresponde al Neon de Historia Clínica")
    from pg8000 import dbapi
    conn = dbapi.connect(
        user=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
        ssl_context=ssl.create_default_context(),
        timeout=12,
    )
    try:
        cur = conn.cursor()
        cur.execute("SET search_path TO public")
        cur.execute(
            """SELECT
                 to_regclass('public.patients'),
                 to_regclass('public.encounters'),
                 to_regclass('public.patient_links'),
                 to_regclass('public.waiting_queue')"""
        )
        row = cur.fetchone() or (None, None, None, None)
        if not row[0] or not row[1]:
            raise RuntimeError("El Neon de Historia no contiene las tablas clínicas canónicas")
        conn.commit()
        return conn
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise


def _bridge_public_connect():
    """Hace que el puente activo deje de escribir al esquema histórico `historia`."""
    conn = _connect_public()
    cur = conn.cursor()
    cur.execute(
        """SELECT
             to_regclass('public.patient_links'),
             to_regclass('public.waiting_queue'),
             (SELECT COUNT(*) FROM information_schema.columns
               WHERE table_schema='public' AND table_name='patient_links'
                 AND column_name='cloud_updated_at'),
             (SELECT COUNT(*) FROM information_schema.columns
               WHERE table_schema='public' AND table_name='waiting_queue'
                 AND column_name='cloud_updated_at')"""
    )
    row = cur.fetchone() or (None, None, 0, 0)
    conn.commit()
    if row[0] and row[1] and int(row[2] or 0) > 0 and int(row[3] or 0) > 0:
        return conn
    try:
        conn.close()
    except Exception:
        pass
    if callable(_original_bridge_connect):
        return _original_bridge_connect()
    raise RuntimeError("El puente de Historia no tiene tablas de vínculo/cola disponibles")


# Desde 4.6.8 el camino normal del puente usa public.*; el fallback solo existe
# para no romper una instalación antigua cuyo esquema canónico todavía no tenga
# patient_links/waiting_queue con las columnas de sincronización actuales.
historia_bridge._connect = _bridge_public_connect


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
    names = [str(col[0]) for col in cur.description]
    return dict(zip(names, row))


def _history_summary(cur, clinical_patient_id):
    cur.execute(
        """SELECT
             COUNT(DISTINCT CASE
               WHEN e.deleted_at IS NULL
                AND COALESCE(e.note_status,'signed') <> 'draft'
                AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL
               THEN e.encounter_date END) AS date_count,
             MAX(CASE
               WHEN e.deleted_at IS NULL
                AND COALESCE(e.note_status,'signed') <> 'draft'
               THEN e.encounter_date END) AS last_date
           FROM public.encounters e
           WHERE e.patient_id=%s""",
        (str(clinical_patient_id),),
    )
    row = cur.fetchone() or (0, None)
    return {
        "history_date_count": int(row[0] or 0),
        "last_history_date": _clean(row[1], 20),
    }


def _linked_patient(cur, reception_patient_id):
    cur.execute(
        """SELECT p.id,p.name,p.national_id,p.birth_date,p.phone,p.email,p.address,
                  l.matched_by,l.verified
           FROM public.patient_links l
           JOIN public.patients p ON p.id=l.clinical_patient_id
           WHERE l.reception_patient_id=%s
             AND l.deleted_at IS NULL
             AND p.deleted_at IS NULL
           LIMIT 1""",
        (str(reception_patient_id),),
    )
    row = _dict_row(cur, cur.fetchone())
    if not row:
        return None
    row.update(_history_summary(cur, row["id"]))
    return row


def _safe_exact_identification_match(cur, identification):
    ident = _norm_id(identification)
    if not ident:
        return None
    cur.execute(
        """SELECT id,name,national_id,birth_date,phone,email,address
           FROM public.patients
           WHERE deleted_at IS NULL
             AND national_id_search=%s
           LIMIT 2""",
        (ident,),
    )
    rows = [_dict_row(cur, r) for r in (cur.fetchall() or [])]
    if len(rows) != 1:
        return None
    row = rows[0]
    row.update(_history_summary(cur, row["id"]))
    return row


def _upsert_link(cur, reception_patient_id, clinical_patient_id, matched_by):
    stamp = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """INSERT INTO public.patient_links(
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
             cloud_updated_at=now()""",
        (
            str(reception_patient_id),
            str(clinical_patient_id),
            _clean(matched_by, 80),
            stamp,
            stamp,
            stamp,
        ),
    )
    # Repara cualquier turno de Recepción que ya haya llegado sin vínculo.
    cur.execute(
        """UPDATE public.waiting_queue
           SET clinical_patient_id=%s,updated_at=%s,cloud_updated_at=now()
           WHERE reception_patient_id=%s
             AND deleted_at IS NULL
             AND (clinical_patient_id IS NULL OR clinical_patient_id='')""",
        (str(clinical_patient_id), stamp, str(reception_patient_id)),
    )


def _sync_demographics(cur, reception_patient_id, clinical_patient_id, demo):
    cur.execute(
        """SELECT id,name,name_search,birth_date,address,phone,
                  national_id,national_id_search,email
           FROM public.patients
           WHERE id=%s AND deleted_at IS NULL
           LIMIT 1""",
        (str(clinical_patient_id),),
    )
    before = _dict_row(cur, cur.fetchone())
    if not before:
        raise RuntimeError("La ficha vinculada ya no existe en Historia Clínica")

    changes = {}
    warnings = []

    wanted_id = _clean(demo.get("national_id"), 120)
    wanted_id_search = _norm_id(wanted_id)
    if wanted_id_search and wanted_id_search != _norm_id(before.get("national_id_search") or before.get("national_id")):
        cur.execute(
            """SELECT id,name FROM public.patients
               WHERE deleted_at IS NULL
                 AND national_id_search=%s
                 AND id<>%s
               LIMIT 1""",
            (wanted_id_search, str(clinical_patient_id)),
        )
        conflict = cur.fetchone()
        if conflict:
            warnings.append(
                "La cédula/identificación no se actualizó porque ya pertenece a otra ficha de Historia."
            )
        else:
            changes["national_id"] = wanted_id
            changes["national_id_search"] = wanted_id_search

    wanted_name = _clean(demo.get("name"), 260)
    if wanted_name and wanted_name != _clean(before.get("name"), 260):
        changes["name"] = wanted_name
        changes["name_search"] = _norm_text(wanted_name)

    for field, column, limit in (
        ("birth_date", "birth_date", 20),
        ("address", "address", 400),
        ("phone", "phone", 120),
        ("email", "email", 180),
    ):
        wanted = _clean(demo.get(field), limit)
        current = _clean(before.get(column), limit)
        # Recepción manda datos administrativos; un campo vacío nunca borra un
        # valor que ya existe en Historia.
        if wanted and wanted != current:
            changes[column] = wanted

    if changes:
        stamp = datetime.now().isoformat(timespec="seconds")
        assignments = []
        values = []
        for column, value in changes.items():
            assignments.append(f'"{column}"=%s')
            values.append(value)
        assignments.extend(["updated_at=%s", "cloud_updated_at=now()"])
        values.extend([stamp, str(clinical_patient_id)])
        cur.execute(
            "UPDATE public.patients SET "
            + ",".join(assignments)
            + " WHERE id=%s AND deleted_at IS NULL",
            tuple(values),
        )

    return changes, warnings


def _prepare_identity(db, reception_patient_id, *, auto_link=True, sync=True):
    patient = _reception_patient(db, reception_patient_id)
    demo = _demographics(patient)
    conn = _connect_public()
    try:
        cur = conn.cursor()
        linked = _linked_patient(cur, patient.id)
        matched_now = False
        if linked is None and auto_link:
            exact = _safe_exact_identification_match(cur, demo["national_id"])
            if exact:
                _upsert_link(cur, patient.id, exact["id"], "reception_exact_identification")
                conn.commit()
                matched_now = True
                linked = _linked_patient(cur, patient.id)

        changed = {}
        warnings = []
        if linked is not None and sync:
            changed, warnings = _sync_demographics(
                cur, patient.id, linked["id"], demo
            )
            if changed:
                conn.commit()
                linked = _linked_patient(cur, patient.id)
            else:
                conn.commit()

        return {
            "ok": True,
            "reception_patient_id": int(patient.id),
            "reception_name": demo["name"],
            "linked": bool(linked),
            "auto_linked": bool(matched_now),
            "clinical_patient": linked,
            "history_date_count": int((linked or {}).get("history_date_count") or 0),
            "last_history_date": _clean((linked or {}).get("last_history_date"), 20),
            "demographics_changed": changed,
            "warnings": warnings,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
            db, reception_patient_id, auto_link=False, sync=False
        )
    except core.HTTPException:
        raise
    except Exception as exc:
        return {
            "ok": False,
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
            db, reception_patient_id, auto_link=True, sync=True
        )
        if result.get("demographics_changed") or result.get("warnings"):
            try:
                core.audit(
                    db,
                    user,
                    "historia_identity_sync",
                    json.dumps(
                        {
                            "reception_patient_id": reception_patient_id,
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
    try:
        result = _prepare_identity(
            db, reception_patient_id, auto_link=False, sync=True
        )
        if result.get("demographics_changed") or result.get("warnings"):
            try:
                core.audit(
                    db,
                    user,
                    "historia_identity_sync",
                    json.dumps(
                        {
                            "reception_patient_id": reception_patient_id,
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
            "linked": False,
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
        }


@app.get("/api/historia-identity/search")
def historia_identity_search(
    q: str = "",
    limit: int = 20,
    user=core.Depends(core.current_user),
):
    query = _clean(q, 160)
    if len(query) < 2:
        return {"ok": True, "results": []}

    text_norm = _norm_text(query)
    ident = _norm_id(query)
    phone = _norm_phone(query)
    tokens = [x for x in text_norm.split(" ") if len(x) >= 2][:6]

    conn = _connect_public()
    try:
        cur = conn.cursor()
        where = []
        params = []

        if ident:
            where.append("p.national_id_search=%s")
            params.append(ident)
        if phone and len(phone) >= 7:
            where.append(
                "regexp_replace(COALESCE(p.phone,''),'[^0-9]','','g') LIKE %s"
            )
            params.append("%" + phone[-9:] + "%")
        if tokens:
            token_parts = []
            for token in tokens:
                token_parts.append(
                    "TRANSLATE(UPPER(COALESCE(p.name_search,p.name,'')),'ÁÉÍÓÚÜÑ','AEIOUUN') LIKE %s"
                )
                params.append("%" + token + "%")
            where.append("(" + " AND ".join(token_parts) + ")")

        if not where:
            return {"ok": True, "results": []}

        safe_limit = max(1, min(int(limit or 20), 40))
        cur.execute(
            """SELECT p.id,p.name,p.national_id,p.birth_date,p.phone,p.email,p.address
               FROM public.patients p
               WHERE p.deleted_at IS NULL
                 AND ("""
            + " OR ".join(where)
            + """)
               ORDER BY COALESCE(p.updated_at,p.created_at,'') DESC
               LIMIT %s""",
            tuple(params + [safe_limit]),
        )
        rows = []
        for raw in cur.fetchall() or []:
            item = _dict_row(cur, raw)
            item.update(_history_summary(cur, item["id"]))
            rows.append(item)
        return {"ok": True, "results": rows}
    except Exception as exc:
        return {
            "ok": False,
            "results": [],
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
        raise core.HTTPException(400, "Seleccione una ficha de Historia Clínica")

    conn = _connect_public()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id,name,national_id,birth_date,phone,email,address
               FROM public.patients
               WHERE id=%s AND deleted_at IS NULL
               LIMIT 1""",
            (clinical_id,),
        )
        target = _dict_row(cur, cur.fetchone())
        if not target:
            raise core.HTTPException(404, "La ficha seleccionada ya no existe")

        reception_ident = _norm_id(demo.get("national_id"))
        target_ident = _norm_id(target.get("national_id"))
        if reception_ident and target_ident and reception_ident != target_ident:
            raise core.HTTPException(
                409,
                "La ficha seleccionada tiene otra cédula/identificación. Revise antes de vincular.",
            )

        _upsert_link(
            cur, patient.id, clinical_id, "reception_manual_verified"
        )
        changes, warnings = _sync_demographics(
            cur, patient.id, clinical_id, demo
        )
        conn.commit()
        target = _linked_patient(cur, patient.id)
        conn.commit()

        try:
            core.audit(
                db,
                user,
                "historia_identity_manual_link",
                json.dumps(
                    {
                        "reception_patient_id": int(patient.id),
                        "clinical_patient_id": clinical_id,
                        "history_date_count": int(
                            (target or {}).get("history_date_count") or 0
                        ),
                        "demographics_changed": changes,
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
            "linked": True,
            "clinical_patient": target,
            "history_date_count": int(
                (target or {}).get("history_date_count") or 0
            ),
            "last_history_date": _clean(
                (target or {}).get("last_history_date"), 20
            ),
            "demographics_changed": changes,
            "warnings": warnings,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


V468_CSS = r"""
.v468-history-card{
  margin:10px 0;padding:10px 12px;border:1px solid #cfe0ee;border-radius:12px;
  background:#f7fbff;color:#31516d;display:flex;align-items:center;
  justify-content:space-between;gap:12px;font-size:11px
}
.v468-history-card b{display:block;font-size:12px;color:#244966}
.v468-history-card small{display:block;margin-top:2px;color:#6c8193}
.v468-history-card .v468-count{font-size:18px;font-weight:900;color:#245f8b;white-space:nowrap}
.v468-history-card.warn{border-color:#ead29b;background:#fffaf0}
.v468-history-card.warn .v468-count{font-size:11px;color:#8b681e}
.v468-link-overlay{position:fixed;inset:0;z-index:2147483640;background:rgba(22,38,55,.46);
  display:grid;place-items:center;padding:18px}
.v468-link-dialog{width:min(760px,96vw);max-height:88vh;overflow:auto;background:#fff;border-radius:18px;
  box-shadow:0 24px 80px rgba(18,38,56,.28);padding:20px}
.v468-link-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}
.v468-link-head h3{margin:0;color:#274b68;font-size:19px}
.v468-link-head p{margin:4px 0 0;color:#73869a;font-size:11px}
.v468-link-close{border:0!important;background:#eef3f7!important;color:#52687d!important;border-radius:10px!important;
  width:34px!important;height:34px!important;font-weight:900!important}
.v468-search-row{display:flex;gap:8px;margin:15px 0 11px}
.v468-search-row input{flex:1;min-width:0}
.v468-results{display:grid;gap:8px}
.v468-result{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;
  padding:11px 12px;border:1px solid #e0e8ef;border-radius:12px;background:#fff}
.v468-result b{font-size:12px;color:#2f4e69}.v468-result span{display:block;margin-top:3px;color:#718497;font-size:10px}
.v468-result button{white-space:nowrap}
.v468-empty{padding:24px;text-align:center;border:1px dashed #d8e1e9;border-radius:12px;color:#718497;font-size:11px}
@media(max-width:620px){.v468-result{grid-template-columns:1fr}.v468-search-row{flex-direction:column}}
"""

V468_JS = r"""
;(()=>{
  if(window.__v468HistoryIdentity)return;
  window.__v468HistoryIdentity=true;

  const txt=v=>String(v??'').replace(/\s+/g,' ').trim();
  const norm=v=>txt(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
  let stableApi=null;
  let lastPanelPatient=0;
  let panelTimer=0;
  const identityCache=new Map();
  const identityPending=new Map();

  function apiBase(){
    if(stableApi)return stableApi;
    const fn=window.api;
    if(typeof fn==='function')stableApi=fn.__v468Base||fn.__v4470Base||fn;
    return stableApi||fn;
  }

  function patientIdFromModal(){
    const modal=document.querySelector('#modal,.modal,.modal-backdrop')||document;
    const attrs=[...modal.querySelectorAll('button[onclick],a[onclick]')].map(x=>String(x.getAttribute('onclick')||''));
    for(const raw of attrs){
      const m=/(?:saveAttention|savePatient|savePatientAndReturnToAttention|editPatientFromAttention)\s*\(\s*(\d+)/.exec(raw);
      if(m)return Number(m[1]||0);
    }
    return 0;
  }

  function modalHost(){
    const modal=document.querySelector('#modal .modalbox,.modal .modalbox,.modalbox');
    if(!modal||modal.querySelector('.v468-link-overlay'))return modal;
    return modal;
  }

  function formatDate(v){
    const s=txt(v);if(!s)return '';
    const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    return m?`${m[3]}/${m[2]}/${m[1]}`:s;
  }

  function panel(data,pid){
    const host=modalHost();if(!host||!pid)return;
    let el=host.querySelector('.v468-history-card');
    if(!el){el=document.createElement('div');el.className='v468-history-card';const form=host.querySelector('.form-grid,.attention-form,.modal-form-heading');if(form)form.insertAdjacentElement('afterend',el);else host.prepend(el)}
    const linked=!!data?.linked,count=Number(data?.history_date_count||0),last=formatDate(data?.last_history_date||'');
    el.classList.toggle('warn',!linked);
    if(linked){
      el.innerHTML=`<div><b>Historia clínica vinculada</b><small>${count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas'}${last?' · Última: '+last:''}</small></div><div class="v468-count">${count}</div>`;
    }else{
      el.innerHTML=`<div><b>Historia clínica</b><small>Esta ficha de Recepción todavía no está vinculada.</small></div><div class="v468-count">SIN VÍNCULO</div>`;
    }
  }

  async function refreshPanel(pid,force=false){
    pid=Number(pid||patientIdFromModal()||0);if(!pid)return;
    if(!force&&pid===lastPanelPatient)return;
    const call=apiBase();if(typeof call!=='function')return;
    lastPanelPatient=pid;
    try{const d=await call('/api/historia-identity/status/'+pid);panel(d,pid)}catch(_e){}
  }

  function warnings(data){
    const rows=Array.isArray(data?.warnings)?data.warnings:[];
    if(rows.length&&typeof window.rpAlert==='function')window.rpAlert(rows.join('\n'),'Datos personales');
    else if(rows.length)alert(rows.join('\n'));
  }

  function closeSearch(){document.querySelector('.v468-link-overlay')?.remove()}

  async function showSearch(pid,initial=''){
    closeSearch();
    const overlay=document.createElement('div');overlay.className='v468-link-overlay';
    overlay.innerHTML=`<div class="v468-link-dialog">
      <div class="v468-link-head"><div><h3>Buscar ficha en Historia Clínica</h3><p>Seleccione la ficha correcta. Recepción será la autoridad de los datos personales.</p></div><button class="v468-link-close" type="button">×</button></div>
      <div class="v468-search-row"><input id="v468HistorySearch" class="search uppercase-search" autocomplete="off" placeholder="Cédula, apellidos y nombres o celular"><button id="v468HistoryGo" class="primary" type="button">Buscar</button></div>
      <div id="v468HistoryResults" class="v468-results"><div class="v468-empty">Buscando fichas…</div></div>
    </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('.v468-link-close').onclick=closeSearch;
    const input=overlay.querySelector('#v468HistorySearch'),results=overlay.querySelector('#v468HistoryResults');
    input.value=txt(initial);
    const run=async()=>{
      const q=txt(input.value);if(q.length<2){results.innerHTML='<div class="v468-empty">Escriba al menos 2 caracteres.</div>';return}
      results.innerHTML='<div class="v468-empty">Buscando…</div>';
      let d;try{d=await apiBase()('/api/historia-identity/search?q='+encodeURIComponent(q)+'&limit=30')}catch(e){d={ok:false,results:[]}}
      if(d&&d.ok===false){results.innerHTML='<div class="v468-empty">No pude consultar Historia Clínica en este momento. Puede cerrar esta búsqueda y continuar; quedará disponible el mecanismo de emergencia del doctor.</div>';return}
      const rows=Array.isArray(d?.results)?d.results:[];
      if(!rows.length){results.innerHTML='<div class="v468-empty">No encontré una ficha con esa búsqueda. Si realmente es un paciente nuevo, cambie el tipo de atención a NUEVO.</div>';return}
      results.innerHTML='';
      rows.forEach(r=>{
        const card=document.createElement('div');card.className='v468-result';
        const count=Number(r.history_date_count||0),last=formatDate(r.last_history_date||'');
        const details=[txt(r.national_id)&&'CI/ID '+txt(r.national_id),txt(r.birth_date)&&'Nac. '+formatDate(r.birth_date),txt(r.phone)&&txt(r.phone),count===1?'1 fecha clínica':count+' fechas clínicas',last&&'Última '+last].filter(Boolean).join(' · ');
        card.innerHTML=`<div><b>${txt(r.name)||'PACIENTE'}</b><span>${details}</span></div><button class="secondary" type="button">Vincular esta ficha</button>`;
        card.querySelector('button').onclick=async()=>{
          const btn=card.querySelector('button');btn.disabled=true;btn.textContent='Vinculando…';
          try{
            const out=await apiBase()('/api/historia-identity/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reception_patient_id:Number(pid),clinical_patient_id:String(r.id)})});
            if(!out?.ok)throw new Error(out?.error||'No se pudo vincular');
            identityCache.set(Number(pid),{at:Date.now(),data:out});warnings(out);closeSearch();lastPanelPatient=0;await refreshPanel(pid,true);
            if(typeof window.rpAlert==='function')window.rpAlert('Ficha vinculada correctamente. Ya puede guardar la atención.','Historia Clínica');
          }catch(e){btn.disabled=false;btn.textContent='Vincular esta ficha';alert(e.message||e)}
        };
        results.appendChild(card);
      });
    };
    overlay.querySelector('#v468HistoryGo').onclick=run;
    input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();run()}});
    setTimeout(()=>{input.focus();if(input.value)run()},30);
  }

  function startIdentityPrepare(pid){
    pid=Number(pid||patientIdFromModal()||0);if(!pid)return Promise.resolve(null);
    const cached=identityCache.get(pid);
    if(cached&&Date.now()-Number(cached.at||0)<60000)return Promise.resolve(cached.data||null);
    if(identityPending.has(pid))return identityPending.get(pid);
    const call=apiBase();if(typeof call!=='function')return Promise.resolve(null);
    const task=Promise.resolve(call('/api/historia-identity/prepare/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}))
      .then(d=>{
        identityCache.set(pid,{at:Date.now(),data:d||null});
        if(d&&d.ok!==false){panel(d,pid);warnings(d)}
        return d||null;
      })
      .catch(()=>{identityCache.set(pid,{at:Date.now(),data:{ok:false,linked:false}});return null})
      .finally(()=>identityPending.delete(pid));
    identityPending.set(pid,task);
    return task;
  }

  function installSaveGate(){
    const base=window.saveAttention;
    if(typeof base!=='function'||base.__v468HistoryGate)return false;
    const wrapped=async function(patientId){
      const pid=Number(patientId||patientIdFromModal()||0);
      const apiBefore=window.api;
      const globalBefore=(()=>{try{return api}catch(_e){return null}})();
      let blocked=false;
      const gate=async function(url,opt={}){
        const u=String(url||'');
        if((u==='/api/visits/batch-payment'||u==='/api/visits/batch')&&pid){
          let body={};try{body=JSON.parse(String(opt?.body||'{}'))}catch(_e){}
          const isSub=norm(body?.tipo)==='S'||norm(body?.tipo)==='SUBSECUENTE';
          const cached=identityCache.get(pid)?.data||null;
          if(isSub&&cached&&cached.ok!==false&&!cached.linked){
            blocked=true;
            showSearch(pid,cached?.reception_name||'');
            const err=new Error('__HISTORIA_LINK_REQUIRED__');err.__historiaLinkRequired=true;throw err;
          }
          // Nunca esperamos a Historia dentro del clic Guardar. Si todavía no
          // terminó el prefetch, la vinculación continúa en segundo plano y puede
          // reparar waiting_queue después de guardar.
          startIdentityPrepare(pid);
        }
        return apiBefore.apply(this,arguments);
      };
      gate.__v468Base=apiBase()||apiBefore;
      try{
        window.api=gate;try{api=gate}catch(_e){}
        return await base.apply(this,arguments);
      }catch(e){
        if(blocked||e?.__historiaLinkRequired||String(e?.message||'').includes('__HISTORIA_LINK_REQUIRED__'))return;
        throw e;
      }finally{
        window.api=apiBefore;try{api=globalBefore||apiBefore}catch(_e){}
      }
    };
    wrapped.__v468HistoryGate=true;wrapped.__v468Base=base;window.saveAttention=wrapped;
    return true;
  }

  function installPatientSync(name){
    const base=window[name];if(typeof base!=='function'||base.__v468HistorySync)return;
    const wrapped=async function(){
      const before=Number(arguments[0]||patientIdFromModal()||0);
      const out=await base.apply(this,arguments);
      const pid=Number(before||patientIdFromModal()||0);
      if(pid){setTimeout(async()=>{try{const d=await apiBase()('/api/historia-identity/sync/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});identityCache.set(Number(pid),{at:Date.now(),data:d});warnings(d);lastPanelPatient=0;refreshPanel(pid,true)}catch(_e){}},80)}
      return out;
    };
    wrapped.__v468HistorySync=true;window[name]=wrapped;
  }

  function boot(){
    installSaveGate();
    ['savePatient','savePatientAndReturnToAttention'].forEach(installPatientSync);
    clearTimeout(panelTimer);panelTimer=setTimeout(()=>{const pid=Number(patientIdFromModal()||0);if(pid)startIdentityPrepare(pid)},80);
  }
  new MutationObserver(boot).observe(document.documentElement,{subtree:true,childList:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setTimeout(boot,300);setTimeout(boot,1000);
})();
"""

core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V468_CSS
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V468_JS


@app.get("/api/v468/health")
def v468_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "reception_identity_authority": True,
        "history_search_from_reception": True,
        "subsequent_requires_history_link": True,
        "demographics_sync_nonblank": True,
        "identification_conflict_guard": True,
        "history_date_count_in_reception": True,
        "history_clinical_notes_exposed_to_reception": False,
        "history_cloud_schema": "public",
        "doctor_manual_link_normal_flow": False,
        "doctor_manual_link_emergency_fallback": True,
        "offline_historia_fallback_preserved": True,
        "name_search_accent_tolerant": True,
        "public_bridge_column_guard": True,
        "database_schema_changes": False,
    }


PATCH_BOOT_OK = True
