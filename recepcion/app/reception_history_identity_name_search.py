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

    row_name = identity._fuzzy_text(row.get("name") or row.get("name_search"))
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
            # A different cédula must be visibly flagged, never hidden when
            # both typed surnames match. The doctor still confirms manually.
            score -= 90
            reasons.append("⚠ identificación diferente: verificar antes de vincular")

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
    """Fetch full surname matches before any broad, recency-truncated candidates.

    The doctor types names in arbitrary order. Never mix an explicit manual
    name with the Reception patient's other name tokens in the SQL prefilter.
    Results are suggestions only: linking still requires manual confirmation.
    """
    raw_query = str(query or "").strip()
    q_norm = identity._fuzzy_text(raw_query)
    is_name_query = any(ch.isalpha() for ch in q_norm)
    query_name = q_norm if is_name_query else identity._fuzzy_text(demo.get("name"))
    tokens = list(dict.fromkeys(t for t in query_name.split() if len(t) >= 2))[:8]

    # Do not turn "PICO VELIZ" into a fake alphanumeric cédula.
    is_identifier_query = (
        not is_name_query
        and bool(re.search(r"\d", raw_query))
        and bool(re.fullmatch(r"[\sA-Za-z0-9.-]+", raw_query))
    )
    manual_id = identity._usable_id(raw_query) if is_identifier_query else ""
    demo_id = identity._usable_id(demo.get("national_id"))
    digits = identity._norm_phone(raw_query) if is_identifier_query else ""
    demo_phone = identity._norm_phone(demo.get("phone"))
    birth = identity._iso_date(demo.get("birth_date"))

    name_expr = (
        "TRANSLATE(UPPER(CONCAT_WS(' ',"
        "NULLIF(COALESCE(p.name_search,''),''),"
        "NULLIF(COALESCE(p.name,''),''))),"
        "'ÁÉÍÓÚÜÑZ','AEIOUUNS')"
    )
    name_parts = [name_expr + " LIKE %s" for _ in tokens]
    name_params = ["%" + token + "%" for token in tokens]

    extras, extra_params = [], []
    for identifier in dict.fromkeys((manual_id, demo_id)):
        if identifier:
            extras.append("p.national_id_search=%s")
            extra_params.append(identifier)
    for phone in dict.fromkeys((digits, demo_phone)):
        if phone and len(phone) >= 7:
            extras.append("regexp_replace(COALESCE(p.phone,''),'[^0-9]','','g') LIKE %s")
            extra_params.append("%" + phone[-9:] + "%")
    if birth:
        extras.append("p.birth_date=%s")
        extra_params.append(birth)

    limit = max(1, min(int(limit or 30), 40))
    sql_limit = max(100, min(200, limit * 5))
    select_sql = """
        SELECT p.id,p.name,p.name_search,p.national_id,p.national_id_search,
               p.birth_date,p.phone,p.email,p.address,p.merged_into_patient_id,
               (SELECT COUNT(DISTINCT e.encounter_date)
                  FROM public.encounters e
                 WHERE e.patient_id=p.id
                   AND e.deleted_at IS NULL
                   AND COALESCE(e.note_status,'signed') <> 'draft'
                   AND NULLIF(TRIM(COALESCE(e.encounter_date,'')),'') IS NOT NULL
               ) AS history_date_count,
               (SELECT MAX(e.encounter_date)
                  FROM public.encounters e
                 WHERE e.patient_id=p.id
                   AND e.deleted_at IS NULL
                   AND COALESCE(e.note_status,'signed') <> 'draft'
               ) AS last_history_date
        FROM public.patients p
        WHERE p.deleted_at IS NULL
          AND ({where})
        ORDER BY p.name ASC, p.id
        LIMIT %s
    """

    def fetch_candidates(condition, params):
        if not condition:
            return []
        cur.execute(select_sql.format(where=condition), tuple(params + [sql_limit]))
        return [identity._dict_row(cur, raw) for raw in (cur.fetchall() or [])]

    # The old OR query could return 90 newer single-surname records and never
    # even fetch a matching older chart. A complete multi-surname match wins.
    matches = []
    if name_parts:
        matches = fetch_candidates("(" + " AND ".join(name_parts) + ")", name_params)

    if not matches:
        fallback = []
        params = []
        if name_parts:
            fallback.append("(" + " OR ".join(name_parts) + ")")
            params.extend(name_params)
        fallback.extend(extras)
        params.extend(extra_params)
        matches = fetch_candidates(" OR ".join(fallback), params)

    rows, seen = [], set()
    for row in matches:
        if not row:
            continue
        canonical_id = identity._clean(row.get("merged_into_patient_id"), 120) or identity._clean(row.get("id"), 120)
        if not canonical_id or canonical_id in seen:
            continue
        if canonical_id != identity._clean(row.get("id"), 120):
            canonical = identity._patient_row(cur, canonical_id)
            if canonical:
                row = canonical
            else:
                continue
        name = str(row.get("name") or "").strip()
        if not name or not any(ch.isalpha() for ch in name):
            continue
        score, reasons = _candidate_score_name_first(row, demo, raw_query)
        if score <= 0:
            continue
        row["match_score"] = int(score)
        row["match_reasons"] = reasons
        rows.append(row)
        seen.add(str(row["id"]))

    rows.sort(
        key=lambda r: (
            int(r.get("match_score") or 0),
            int(r.get("history_date_count") or 0),
            identity._clean(r.get("last_history_date"), 20),
        ),
        reverse=True,
    )
    return rows[:limit]


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
  function visibleReceptionName(overlay){
    const candidates=[
      ...document.querySelectorAll('.v4413-profile-name h2'),
      ...document.querySelectorAll('.patient-profile h2'),
      ...document.querySelectorAll('.attention-patient-name')
    ];
    for(const el of candidates){
      if(!el||overlay.contains(el))continue;
      const value=String(el.textContent||'').trim();
      if(value&&/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(value))return value;
    }
    return '';
  }
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
      const receptionName=visibleReceptionName(overlay);
      const initial=String(input.value||'').trim();
      if(receptionName&&(!/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(initial)||/^\d+$/.test(initial))){
        input.value=receptionName;
        setTimeout(()=>{ if(go&&!go.disabled) go.click(); },0);
      }
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
        "prefill_uses_reception_name": True,
        "single_query_history_summary": True,
        "identification_is_secondary_signal": True,
        "manual_confirmation_preserved": True,
        "different_valid_identifications_blocked_by_existing_link_route": False,
        "confirmed_history_id_corrects_reception_identification": True,
        "doctor_identity_correction_required": False,
        "patient_data_destructive_changes": False,
    }


PATCH_BOOT_OK = True
