from __future__ import annotations

import threading
from datetime import datetime

import historia_bridge
from sqlalchemy import text

_STATE = {
    "ready": False,
    "last_error": "",
    "updated_at": "",
    "mode": "postgres_fdw",
}
_LOCK = threading.Lock()
_INSTALL_STARTED = False


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sql_literal(value: object) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _history_config() -> dict:
    url = historia_bridge._database_url()
    if not url:
        raise RuntimeError("Historia Clínica no está configurada en Recepción")
    cfg = historia_bridge._parse_pg_url(url)
    host = str(cfg.get("host") or "").strip()
    # postgres_fdw trabaja mejor contra el endpoint directo, no el pooler.
    if "-pooler." in host:
        host = host.replace("-pooler.", ".", 1)
    cfg["host"] = host
    return cfg


def _set_state(**values) -> None:
    with _LOCK:
        _STATE.update(values)
        _STATE["updated_at"] = _now()


def status() -> dict:
    with _LOCK:
        return dict(_STATE)


def _function_sql() -> list[str]:
    return [
        r"""
CREATE OR REPLACE FUNCTION public.agenda_historia_search(
    p_token text,
    p_query text
)
RETURNS TABLE(
    patient_id text,
    name text,
    national_id text,
    birth_date text,
    history_count bigint,
    last_history_date text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, agenda_private, historia_mobile_fdw, pg_temp
AS $$
DECLARE
    q text := translate(upper(trim(coalesce(p_query,''))), 'ÁÉÍÓÚÜÑ', 'AEIOUUN');
BEGIN
    IF coalesce(public.agenda_web_role(p_token),'') <> 'doctor' THEN
        RAISE EXCEPTION 'Acceso clínico no autorizado' USING ERRCODE='42501';
    END IF;
    IF length(q) < 2 THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        p.id::text,
        coalesce(p.name,'')::text,
        coalesce(p.national_id,'')::text,
        coalesce(p.birth_date::text,'')::text,
        count(e.id) FILTER (
            WHERE e.deleted_at IS NULL
              AND coalesce(e.note_status,'signed') <> 'draft'
        )::bigint AS history_count,
        coalesce(max(e.encounter_date::text) FILTER (
            WHERE e.deleted_at IS NULL
              AND coalesce(e.note_status,'signed') <> 'draft'
        ),'')::text AS last_history_date
    FROM historia_mobile_fdw.patients p
    LEFT JOIN historia_mobile_fdw.encounters e
      ON e.patient_id = p.id
    WHERE p.deleted_at IS NULL
      AND coalesce(p.merged_into_patient_id,'') = ''
      AND (
        regexp_replace(upper(coalesce(p.national_id_search,p.national_id,'')), '[^A-Z0-9]', '', 'g')
          LIKE '%' || regexp_replace(q, '[^A-Z0-9]', '', 'g') || '%'
        OR NOT EXISTS (
          SELECT 1
          FROM unnest(regexp_split_to_array(q, '\s+')) AS tok
          WHERE length(tok) > 0
            AND translate(upper(coalesce(p.name_search,p.name,'')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')
                NOT LIKE '%' || tok || '%'
        )
      )
    GROUP BY p.id,p.name,p.national_id,p.birth_date,p.name_search
    ORDER BY
      CASE
        WHEN translate(upper(coalesce(p.name_search,p.name,'')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN') = q THEN 0
        ELSE 1
      END,
      max(e.encounter_date) DESC NULLS LAST,
      p.name
    LIMIT 30;
END
$$;
""",
        r"""
CREATE OR REPLACE FUNCTION public.agenda_historia_patient(
    p_token text,
    p_patient_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, agenda_private, historia_mobile_fdw, pg_temp
AS $$
DECLARE
    wanted text := coalesce(p_patient_id,'');
    merged text := '';
    result jsonb;
BEGIN
    IF coalesce(public.agenda_web_role(p_token),'') <> 'doctor' THEN
        RAISE EXCEPTION 'Acceso clínico no autorizado' USING ERRCODE='42501';
    END IF;

    SELECT coalesce(merged_into_patient_id,'')
      INTO merged
    FROM historia_mobile_fdw.patients
    WHERE id=wanted AND deleted_at IS NULL
    LIMIT 1;

    IF merged <> '' THEN
        wanted := merged;
    END IF;

    SELECT jsonb_build_object(
      'patient',
        jsonb_build_object(
          'id', p.id,
          'name', coalesce(p.name,''),
          'national_id', coalesce(p.national_id,''),
          'birth_date', coalesce(p.birth_date::text,''),
          'sex', coalesce(p.sex,''),
          'phone', coalesce(p.phone,''),
          'email', coalesce(p.email,'')
        ),
      'encounters',
        coalesce((
          SELECT jsonb_agg(
            jsonb_build_object(
              'id', e.id,
              'date', coalesce(e.encounter_date::text,''),
              'time', coalesce(e.encounter_time::text,''),
              'clinical_note', coalesce(e.clinical_note,''),
              'diagnosis', coalesce(e.diagnosis,''),
              'treatment', coalesce(e.treatment,''),
              'source', coalesce(e.source,''),
              'addenda', coalesce((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'text', coalesce(a.text,''),
                    'created_at', coalesce(a.created_at::text,''),
                    'actor', coalesce(a.actor,'')
                  )
                  ORDER BY a.created_at
                )
                FROM historia_mobile_fdw.encounter_addenda a
                WHERE a.encounter_id=e.id
              ), '[]'::jsonb)
            )
            ORDER BY coalesce(e.encounter_date,'' ) DESC,
                     coalesce(e.encounter_time,'') DESC,
                     coalesce(e.updated_at::text,'') DESC
          )
          FROM historia_mobile_fdw.encounters e
          WHERE e.patient_id=wanted
            AND e.deleted_at IS NULL
            AND coalesce(e.note_status,'signed') <> 'draft'
        ), '[]'::jsonb),
      'prescriptions',
        coalesce((
          SELECT jsonb_agg(
            jsonb_build_object(
              'id', r.id,
              'issued_at', coalesce(r.issued_at::text,''),
              'diagnosis', coalesce(r.diagnosis,''),
              'cie10', coalesce(r.cie10,''),
              'items_json', coalesce(r.items_json,'[]'),
              'instructions', coalesce(r.instructions,'')
            )
            ORDER BY r.issued_at DESC
          )
          FROM historia_mobile_fdw.prescriptions r
          WHERE r.patient_id=wanted AND r.deleted_at IS NULL
        ), '[]'::jsonb),
      'certificates',
        coalesce((
          SELECT jsonb_agg(
            jsonb_build_object(
              'id', c.id,
              'issued_at', coalesce(c.issued_at::text,''),
              'diagnosis', coalesce(c.diagnosis,''),
              'cie10', coalesce(c.cie10,''),
              'additional_diagnosis', coalesce(c.additional_diagnosis,''),
              'additional_cie10', coalesce(c.additional_cie10,''),
              'procedure_text', coalesce(c.procedure_text,''),
              'rest_days', coalesce(c.rest_days,0),
              'rest_from', coalesce(c.rest_from::text,''),
              'rest_to', coalesce(c.rest_to::text,''),
              'body_text', coalesce(c.body_text,''),
              'certificate_type', coalesce(c.certificate_type,'medical')
            )
            ORDER BY c.issued_at DESC
          )
          FROM historia_mobile_fdw.certificates c
          WHERE c.patient_id=wanted AND c.deleted_at IS NULL
        ), '[]'::jsonb)
    )
    INTO result
    FROM historia_mobile_fdw.patients p
    WHERE p.id=wanted AND p.deleted_at IS NULL
    LIMIT 1;

    IF result IS NULL THEN
        RAISE EXCEPTION 'Ficha clínica no encontrada' USING ERRCODE='P0002';
    END IF;
    RETURN result;
END
$$;
""",
        r"""
CREATE OR REPLACE FUNCTION public.agenda_historia_linked_patient(
    p_token text,
    p_reception_patient_id text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, agenda_private, historia_mobile_fdw, pg_temp
AS $$
DECLARE
    clinical_id text;
BEGIN
    IF coalesce(public.agenda_web_role(p_token),'') <> 'doctor' THEN
        RAISE EXCEPTION 'Acceso clínico no autorizado' USING ERRCODE='42501';
    END IF;
    SELECT l.clinical_patient_id::text
      INTO clinical_id
    FROM historia_mobile_fdw.patient_links l
    WHERE l.reception_patient_id::text=coalesce(p_reception_patient_id,'')
      AND coalesce(l.verified,0)=1
      AND l.deleted_at IS NULL
    LIMIT 1;
    RETURN coalesce(clinical_id,'');
END
$$;
""",
    ]


def setup(core) -> dict:
    if not getattr(core, "CloudSessionLocal", None):
        raise RuntimeError("Neon de Recepción no está configurado")
    cfg = _history_config()
    host = _sql_literal(cfg["host"])
    database = _sql_literal(cfg["database"])
    port = _sql_literal(str(cfg["port"]))
    user = _sql_literal(cfg["user"])
    password = _sql_literal(cfg["password"])

    statements = [
        "CREATE EXTENSION IF NOT EXISTS postgres_fdw",
        "CREATE SCHEMA IF NOT EXISTS historia_mobile_fdw",
        "REVOKE ALL ON SCHEMA historia_mobile_fdw FROM PUBLIC",
        "DROP SERVER IF EXISTS historia_mobile_server CASCADE",
        (
            "CREATE SERVER historia_mobile_server FOREIGN DATA WRAPPER postgres_fdw "
            f"OPTIONS (host {host}, dbname {database}, port {port}, sslmode 'require')"
        ),
        (
            "CREATE USER MAPPING FOR CURRENT_USER SERVER historia_mobile_server "
            f"OPTIONS (user {user}, password {password})"
        ),
        (
            "IMPORT FOREIGN SCHEMA public LIMIT TO "
            "(patients,encounters,encounter_addenda,prescriptions,certificates,patient_links) "
            "FROM SERVER historia_mobile_server INTO historia_mobile_fdw"
        ),
        "REVOKE ALL ON ALL TABLES IN SCHEMA historia_mobile_fdw FROM PUBLIC",
    ]

    with core.CloudSessionLocal() as db:
        try:
            for sql in statements:
                db.execute(text(sql))
            for sql in _function_sql():
                db.execute(text(sql))
            for fn in (
                "public.agenda_historia_search(text,text)",
                "public.agenda_historia_patient(text,text)",
                "public.agenda_historia_linked_patient(text,text)",
            ):
                db.execute(text(f"GRANT EXECUTE ON FUNCTION {fn} TO PUBLIC"))
            db.commit()
        except Exception:
            db.rollback()
            raise

    _set_state(ready=True, last_error="")
    return status()


def _background_setup(core) -> None:
    try:
        setup(core)
    except Exception as exc:
        _set_state(ready=False, last_error=f"{type(exc).__name__}: {str(exc)[:240]}")


def install(app, core) -> None:
    global _INSTALL_STARTED

    @app.on_event("startup")
    def _mobile_history_setup():
        global _INSTALL_STARTED
        if _INSTALL_STARTED:
            return
        _INSTALL_STARTED = True
        threading.Thread(
            target=_background_setup,
            args=(core,),
            daemon=True,
            name="agenda-history-fdw-setup",
        ).start()

    @app.get("/api/mobile-history/status")
    def _mobile_history_status():
        return status()
