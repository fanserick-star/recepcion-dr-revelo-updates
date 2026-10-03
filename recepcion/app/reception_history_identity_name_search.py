from __future__ import annotations

import difflib

import reception_history_identity_consolidated as identity

core = identity.core
app = identity.app
APP_VERSION = identity.APP_VERSION


def _name_tokens(value):
    return [t for t in identity._fuzzy_text(value).split() if len(t) >= 2]


def _best_ratio(token, candidates):
    if not token or not candidates:
        return 0.0
    if token in candidates:
        return 1.0
    return max(difflib.SequenceMatcher(None, token, cand).ratio() for cand in candidates)


def _candidate_score_name_first(row, demo, query):
    score = 0
    reasons = []

    row_name = identity._fuzzy_text(row.get("name_search") or row.get("name"))
    typed_name = identity._fuzzy_text(query)
    patient_name = identity._fuzzy_text(demo.get("name"))
    basis = typed_name if any(ch.isalpha() for ch in typed_name) else patient_name
    wanted_tokens = _name_tokens(basis)
    row_tokens = _name_tokens(row_name)

    if basis and row_name:
        if basis == row_name:
            score += 700
            reasons.append("mismo nombre completo")
        elif wanted_tokens:
            exact = 0
            fuzzy = 0
            for token in wanted_tokens:
                ratio = _best_ratio(token, row_tokens)
                if ratio >= 0.999:
                    score += 115
                    exact += 1
                elif ratio >= 0.86:
                    score += 82
                    fuzzy += 1
                elif ratio >= 0.74:
                    score += 46
                    fuzzy += 1
            matched = exact + fuzzy
            if matched == len(wanted_tokens):
                score += 180
                reasons.append("nombre coincide aunque esté en otro orden")
            elif matched >= max(2, len(wanted_tokens) - 1):
                score += 90
                reasons.append("nombre muy parecido")
            elif matched:
                reasons.append("nombre parcialmente parecido")

    wanted_id = identity._usable_id(demo.get("national_id"))
    row_id = identity._usable_id(row.get("national_id_search") or row.get("national_id"))
    if wanted_id and row_id:
        if wanted_id == row_id:
            score += 460
            reasons.append("misma identificación")
        else:
            score -= 500
            reasons.append("identificación diferente")

    wanted_phone = identity._norm_phone(demo.get("phone"))
    row_phone = identity._norm_phone(row.get("phone"))
    if wanted_phone and row_phone and wanted_phone[-9:] == row_phone[-9:]:
        score += 180
        reasons.append("mismo celular")

    wanted_birth = identity._iso_date(demo.get("birth_date"))
    row_birth = identity._iso_date(row.get("birth_date"))
    if wanted_birth and row_birth and wanted_birth == row_birth:
        score += 200
        reasons.append("misma fecha de nacimiento")

    history_count = int(row.get("history_date_count") or 0)
    score += min(20, history_count)
    return score, reasons


def _search_candidates_name_first(cur, demo, query, limit):
    ident = identity._usable_id(query)
    phone = identity._norm_phone(query)
    q_norm = identity._fuzzy_text(query)
    q_tokens = [t for t in q_norm.split() if len(t) >= 2]
    demo_tokens = _name_tokens(demo.get("name"))
    birth = identity._iso_date(demo.get("birth_date"))
    demo_id = identity._usable_id(demo.get("national_id"))
    demo_phone = identity._norm_phone(demo.get("phone"))

    where = []
    params = []
    name_expr = (
        "TRANSLATE(UPPER(COALESCE(p.name_search,p.name,'')),"
        "'ÁÉÍÓÚÜÑZ','AEIOUUNS')"
    )

    # El nombre es la entrada principal. Basta con una palabra para mostrar una
    # lista; la puntuación posterior coloca arriba las coincidencias más completas.
    tokens = q_tokens or demo_tokens
    if tokens:
        name_parts = []
        for token in tokens[:8]:
            name_parts.append(name_expr + " LIKE %s")
            params.append("%" + token + "%")
        where.append("(" + " OR ".join(name_parts) + ")")

    # Cédula, celular y nacimiento siguen siendo señales fuertes de confirmación,
    # pero ya no son el punto de entrada obligatorio para encontrar la ficha.
    for value in (ident, demo_id):
        if value:
            where.append("p.national_id_search=%s")
            params.append(value)
    for value in (phone, demo_phone):
        if value and len(value) >= 7:
            where.append("regexp_replace(COALESCE(p.phone,''),'[^0-9]','','g') LIKE %s")
            params.append("%" + value[-9:] + "%")
    if birth:
        where.append("p.birth_date=%s")
        params.append(birth)

    if not where:
        return []

    sql_limit = max(40, min(90, int(limit or 30) * 3))
    cur.execute(
        """
        SELECT p.id,p.name,p.name_search,p.national_id,p.national_id_search,
               p.birth_date,p.phone,p.email,p.address,p.merged_into_patient_id,
               COALESCE(h.history_date_count,0) AS history_date_count,
               h.last_history_date
        FROM public.patients p
        LEFT JOIN (
          SELECT e.patient_id,
                 COUNT(DISTINCT CASE
                   WHEN e.deleted_at IS NULL
                    AND COALESCE(e.note_status,'signed') <> 'draft'
                    AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL
                   THEN e.encounter_date END) AS history_date_count,
                 MAX(CASE
                   WHEN e.deleted_at IS NULL
                    AND COALESCE(e.note_status,'signed') <> 'draft'
                   THEN e.encounter_date END) AS last_history_date
          FROM public.encounters e
          GROUP BY e.patient_id
        ) h ON h.patient_id=p.id
        WHERE p.deleted_at IS NULL
          AND COALESCE(p.merged_into_patient_id,'')=''
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
        row = identity._dict_row(cur, raw)
        pid = identity._clean(row.get("id"), 120)
        if not pid or pid in seen:
            continue
        score, reasons = _candidate_score_name_first(row, demo, query)
        if score <= 0:
            continue
        row["match_score"] = int(score)
        row["match_reasons"] = reasons
        rows.append(row)
        seen.add(pid)

    rows.sort(
        key=lambda r: (
            int(r.get("match_score") or 0),
            int(r.get("history_date_count") or 0),
            identity._clean(r.get("last_history_date"), 20),
        ),
        reverse=True,
    )
    return rows[: max(1, min(int(limit or 30), 40))]


# Las rutas existentes usan estos nombres globales al ejecutar cada petición.
# Se reemplaza únicamente la estrategia de búsqueda; el vínculo confirmado,
# auditoría y sincronización de datos continúan en el módulo consolidado.
identity._candidate_score = _candidate_score_name_first
identity._search_candidates = _search_candidates_name_first

V4637_CSS = r"""
.v4613-dialog{width:min(900px,97vw)!important}
.v4613-search{position:sticky;top:-20px;z-index:2;background:#fff;padding:12px 0 8px;margin:8px 0 10px!important}
.v4613-search input{font-size:16px!important;font-weight:800!important;padding:13px 14px!important}
.v4613-results{max-height:58vh;overflow:auto;padding-right:3px}
.v4613-result b{font-size:15px!important}
.v4613-name-live-note{margin:-4px 0 8px;color:#557187;font-size:12px;font-weight:700}
"""

V4637_JS = r"""
;(()=>{
  if(window.__v4637NameFirstHistoryLink)return;
  window.__v4637NameFirstHistoryLink=true;
  let debounce=0;
  function enhance(){
    const overlay=document.querySelector('.v4613-overlay');
    if(!overlay||overlay.dataset.nameFirst==='1')return;
    overlay.dataset.nameFirst='1';
    const head=overlay.querySelector('.v4613-head');
    const title=head?.querySelector('h3');
    const desc=head?.querySelector('p');
    const input=overlay.querySelector('.v4613-search input');
    const go=overlay.querySelector('.v4613-search button');
    if(title)title.textContent='Buscar ficha por nombre';
    if(desc)desc.textContent='Escribe nombres o apellidos. La lista se actualiza sola; cédula, celular y fecha de nacimiento se usan como refuerzo para confirmar la ficha correcta.';
    if(input){
      input.placeholder='Escriba nombre o apellido…';
      input.setAttribute('aria-label','Buscar ficha por nombre');
      input.addEventListener('input',()=>{
        clearTimeout(debounce);
        debounce=setTimeout(()=>{ if(go&&!go.disabled) go.click(); },220);
      });
    }
    if(go)go.textContent='Buscar ahora';
    const search=overlay.querySelector('.v4613-search');
    if(search&&!overlay.querySelector('.v4613-name-live-note')){
      const note=document.createElement('div');
      note.className='v4613-name-live-note';
      note.textContent='Búsqueda en vivo · el nombre es la referencia principal';
      search.insertAdjacentElement('afterend',note);
    }
  }
  new MutationObserver(enhance).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('click',()=>setTimeout(enhance,0),true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',enhance,{once:true});else enhance();
})();
"""

core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4637_CSS
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4637_JS


@app.get("/api/v4637/history-name-link/health")
def v4637_history_name_link_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "name_is_primary_search": True,
        "live_results": True,
        "single_query_history_summary": True,
        "identification_is_secondary_signal": True,
        "manual_confirmation_preserved": True,
        "different_valid_identifications_blocked_by_existing_link_route": True,
        "patient_data_destructive_changes": False,
    }


PATCH_BOOT_OK = True
