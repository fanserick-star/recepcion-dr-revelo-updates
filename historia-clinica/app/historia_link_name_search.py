from __future__ import annotations

import difflib
import json
import re
import sqlite3

import historia_link_helper as helper

PATCH_VERSION = "1.3.98"


def _human_name(value: object) -> str:
    """A reception ID is not a display name, even if stored in display_name."""
    name = " ".join(str(value or "").strip().split())
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}", name)
    if not words:
        return ""
    compact = helper._norm_id(name)
    if compact in helper._ID_PLACEHOLDERS or compact.startswith(("CEDULA", "IDENTIFICACION", "DNI")):
        return ""
    return name


def _queue_initial_name_first(queue_id: str) -> str:
    """Show an actual patient's name, never a raw ID masquerading as one."""
    try:
        with sqlite3.connect(helper.DB_PATH, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT display_name,identification,clinical_patient_id FROM waiting_queue WHERE id=? LIMIT 1",
                (str(queue_id),),
            ).fetchone()
            if not row:
                return ""
            name = _human_name(row["display_name"])
            if name:
                return name
            # Legacy handoffs sometimes put the cédula in display_name itself.
            identity = helper._usable_identification(row["identification"] or row["display_name"])
            linked = str(row["clinical_patient_id"] or "").strip()
            if linked:
                patient = conn.execute(
                    """SELECT name,national_id,national_id_search FROM patients
                       WHERE id=? AND COALESCE(merged_into_patient_id,'')='' LIMIT 1""",
                    (linked,),
                ).fetchone()
                if patient:
                    actual_id = helper._usable_identification(patient["national_id_search"] or patient["national_id"])
                    if not identity or not actual_id or identity == actual_id:
                        valid = _human_name(patient["name"])
                        if valid:
                            return valid
            if identity and len(identity) >= 6:
                candidates = conn.execute(
                    """SELECT name FROM patients
                       WHERE COALESCE(merged_into_patient_id,'')=''
                         AND (national_id_search=? OR national_id=?)
                       LIMIT 2""", (identity, identity),
                ).fetchall()
                if len(candidates) == 1:
                    return _human_name(candidates[0]["name"])
            # No verified name: don't prefill a misleading numeric value.
            return ""
    except (sqlite3.Error, OSError):
        return ""


def _candidate_rows_name_first(queue_id: str, query: str = "", limit: int = 15) -> dict:
    """Rank names typed by the doctor first; never link automatically.

    Search complete surname combinations before any broad/fuzzy search.
    A legacy queue ID cannot dilute the manual name query or displace the right
    record from a LIMIT ordered by last modification.
    """
    if not helper.DB_PATH.is_file():
        return {"ok": False, "results": [], "error": "Base local de Historia no disponible"}

    with sqlite3.connect(helper.DB_PATH, timeout=8) as conn:
        conn.row_factory = sqlite3.Row
        queue = conn.execute(
            """SELECT id,display_name,identification,clinical_patient_id,status
               FROM waiting_queue
               WHERE id=? AND status IN ('waiting','in_consultation')
               LIMIT 1""", (str(queue_id),),
        ).fetchone()
        if not queue:
            return {"ok": False, "results": [], "error": "Turno no encontrado"}

        queue_name = _human_name(queue["display_name"])
        queue_ident = helper._usable_identification(queue["identification"] or queue["display_name"])
        initial = _queue_initial_name_first(queue_id)
        manual = str(query or "").strip()
        manual_name = _human_name(manual)
        manual_ident = helper._usable_identification(manual) if not manual_name else ""
        name_basis = manual_name or initial
        wanted_tokens = list(dict.fromkeys(
            token for token in helper._tokens(name_basis) if re.search(r"[A-Z]", token)
        ))[:8]
        linked_id = str(queue["clinical_patient_id"] or "").strip()

        select_sql = """
            SELECT p.id,p.name,p.name_search,p.national_id,p.national_id_search,
                   p.birth_date,p.sex,
                   (SELECT COUNT(*) FROM encounters e
                     WHERE e.patient_id=p.id
                       AND COALESCE(e.note_status,'signed')!='draft'
                       AND COALESCE(e.deleted_at,'')='') AS history_count,
                   (SELECT MAX(e.encounter_date) FROM encounters e
                     WHERE e.patient_id=p.id
                       AND COALESCE(e.note_status,'signed')!='draft'
                       AND COALESCE(e.deleted_at,'')='') AS last_history_date
            FROM patients p
            WHERE COALESCE(p.merged_into_patient_id,'')=''
              AND ({where})
            LIMIT 650
        """
        def token_clause(token: str) -> tuple[str, list[str]]:
            # Legacy name_search may be missing or stale; consult name too.
            return (
                "(UPPER(COALESCE(p.name_search,'')) LIKE ? OR UPPER(COALESCE(p.name,'')) LIKE ?)",
                ["%" + token + "%", "%" + token + "%"],
            )

        collected: dict[str, sqlite3.Row] = {}
        def fetch(where: str, params: list[object]) -> int:
            if not where:
                return 0
            n = 0
            for row in conn.execute(select_sql.format(where=where), params).fetchall():
                if str(row["id"]) not in collected:
                    collected[str(row["id"])] = row
                    n += 1
            return n

        exact_parts, exact_params = [], []
        for token in wanted_tokens:
            fragment, params = token_clause(token)
            exact_parts.append(fragment)
            exact_params.extend(params)

        # Phase 1: all manually entered surname/name fragments must appear.
        strong_count = fetch(" AND ".join(exact_parts), exact_params) if exact_parts else 0

        # Phase 2: fuzzy recovery ONLY if there are no complete name matches.
        # Otherwise don't contaminate the first screen with partial names.
        if wanted_tokens and strong_count == 0:
            fetch(" OR ".join(exact_parts), exact_params)

        # Exact identification / verified link are optional fallback candidates.
        # They may not outrank an explicit complete surname match.
        if not collected or not wanted_tokens or not manual_name:
            id_parts, id_params = [], []
            if linked_id:
                id_parts.append("p.id=?")
                id_params.append(linked_id)
            for ident in (manual_ident, queue_ident):
                if ident and len(ident) >= 6:
                    id_parts.append("(p.national_id_search=? OR p.national_id=?)")
                    id_params.extend([ident, ident])
            if id_parts:
                fetch(" OR ".join(id_parts), id_params)

    results = []
    q_name_norm = helper._norm_text(name_basis)
    for row in collected.values():
        cand_name = _human_name(row["name"])
        if not cand_name:
            continue
        cand_name_norm = helper._norm_text(row["name_search"] or cand_name)
        cand_tokens = helper._tokens(cand_name_norm)
        # Some imported name_search fields do not match their visible names.
        cand_tokens = list(dict.fromkeys(cand_tokens + helper._tokens(cand_name)))
        cand_ident = helper._usable_identification(row["national_id_search"] or row["national_id"] or "")
        reception_linked = bool(linked_id and str(row["id"]) == linked_id)
        ratios = [
            max((difflib.SequenceMatcher(None, token, c).ratio() for c in cand_tokens), default=0)
            for token in wanted_tokens
        ]
        matched = sum(r >= 0.74 for r in ratios)
        complete = bool(wanted_tokens and len(ratios) == matched)
        exact = sum(r >= 0.999 for r in ratios)
        id_exact = bool(
            cand_ident and (
                (manual_ident and cand_ident == manual_ident)
                or (queue_ident and cand_ident == queue_ident)
            )
        )
        # With an explicit name query, never show an unrelated linked/ID row
        # ahead of the actual surname matches.
        if manual_name and not complete:
            if strong_count or matched < (1 if len(wanted_tokens) == 1 else max(1, len(wanted_tokens)-1)):
                continue
        elif wanted_tokens and not complete and not id_exact and not reception_linked:
            if matched < (1 if len(wanted_tokens) == 1 else max(1, len(wanted_tokens)-1)):
                continue

        reasons = []
        score = 0
        if complete:
            score += 1100 + 65 * len(wanted_tokens) + exact * 35
            reasons.append("coinciden todos los apellidos/nombres escritos")
        else:
            score += matched * 100 + exact * 25
            if matched:
                reasons.append("nombre parcialmente parecido")
        if q_name_norm and helper._norm_text(cand_name) == q_name_norm:
            score += 400
            reasons.append("nombre completo exacto")
        if manual_ident and cand_ident == manual_ident:
            score += 1200
            reasons.append("misma cédula buscada")
        if reception_linked:
            score += 90 if manual_name else 300
            reasons.append("ficha vinculada en Recepción")
        if queue_ident and cand_ident:
            if queue_ident == cand_ident:
                score += 90 if manual_name else 300
                reasons.append("misma cédula enviada")
            else:
                score -= 300
                reasons.append("cédula distinta")
        history_count = int(row["history_count"] or 0)
        score += min(history_count, 20)
        if score <= 0:
            continue
        results.append({
            "id": str(row["id"]),
            "name": cand_name,
            "national_id": (
                str(row["national_id"] or "").strip() if cand_ident else ""
            ),
            "birth_date": helper._fmt_date(row["birth_date"]),
            "history_count": history_count,
            "last_history_date": helper._fmt_date(row["last_history_date"]),
            "score": int(score),
            "reasons": reasons,
            "id_conflict": bool(queue_ident and cand_ident and cand_ident != queue_ident),
            "reception_linked": reception_linked,
        })
    results.sort(key=lambda x: (x["score"], x["history_count"], x["last_history_date"]), reverse=True)
    return {
        "ok": True,
        "queue_id": str(queue_id),
        "initial_query": initial,
        "queue_name": queue_name or initial,
        "queue_identification": str(queue["identification"] or "").strip(),
        "results": results[:max(1, min(int(limit or 15), 20))],
    }


def _helper_markup_name_first(queue_id: str, initial: str) -> str:
    qid_js = json.dumps(str(queue_id), ensure_ascii=False)
    initial_js = json.dumps(str(initial or ""), ensure_ascii=False)
    return f"""
<style id="v1396-link-style">
.v1393-link{{margin:14px 0;padding:16px;border:1px solid #cbdceb;border-radius:14px;background:#f8fbff}}
.v1393-link h2{{margin:0 0 5px;color:#173b66;font-size:20px}}
.v1393-link p{{margin:0 0 10px;color:#60758a;font-size:13px}}
.v1393-live{{font-size:12px;font-weight:800;color:#35688f;margin:0 0 8px}}
.v1393-search{{display:flex;gap:8px;margin-bottom:12px;position:sticky;top:0;background:#f8fbff;padding:5px 0;z-index:2}}
.v1393-search input{{flex:1;min-width:0;border:1px solid #9fb7ca;border-radius:10px;padding:12px 13px;font-size:16px;font-weight:800}}
.v1393-search button{{border:0;border-radius:10px;background:#246fae;color:#fff;padding:10px 16px;font-weight:850;cursor:pointer}}
.v1393-list{{display:grid;gap:8px;max-height:55vh;overflow:auto;padding-right:3px}}
.v1393-card{{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:12px 13px;border:1px solid #d8e3ec;border-radius:11px;background:#fff}}
.v1393-card.warn{{border-color:#e7b7b0;background:#fff5f3}}
.v1393-card b{{display:block;color:#173b66;font-size:16px}}
.v1393-card strong{{display:inline-block;margin-top:3px;color:#162b3f;font-size:12px}}
.v1393-card small{{display:block;margin-top:3px;color:#6a7c8d;font-size:11px}}
.v1393-card a{{text-decoration:none;border-radius:9px;background:#2475d0;color:#fff;padding:9px 11px;font-weight:850;white-space:nowrap}}
.v1393-card .blocked{{border-radius:9px;background:#e7ebef;color:#7d8993;padding:9px 11px;font-weight:850;white-space:nowrap}}
.v1393-empty{{padding:12px;border:1px dashed #cbd5e1;border-radius:10px;color:#6b7d90;background:#fff}}
@media(max-width:680px){{.v1393-search{{flex-direction:column}}.v1393-card{{grid-template-columns:1fr}}}}
</style>
<section id="v1393-link-helper" class="v1393-link">
  <h2>Buscar y vincular ficha por nombre</h2>
  <p>Busca por uno o dos apellidos, en cualquier orden. El nombre se muestra primero; la cédula sirve para verificar la identidad.</p>
  <div class="v1393-live">Búsqueda en vivo · no necesitas presionar Buscar</div>
  <div class="v1393-search">
    <input id="v1393-link-q" autocomplete="off" placeholder="Ej.: VELIZ PICO o MERO IZQUIERDO">
    <button id="v1393-link-go" type="button">Buscar ahora</button>
  </div>
  <div id="v1393-link-list" class="v1393-list"><div class="v1393-empty">Buscando fichas posibles…</div></div>
</section>
<script>
(()=>{{
  const qid={qid_js},initial={initial_js};
  const input=document.getElementById('v1393-link-q');
  const list=document.getElementById('v1393-link-list');
  const btn=document.getElementById('v1393-link-go');
  if(!input||!list||!btn)return;
  input.value=initial;
  // El mismo campo nunca se prellena con una cédula legada.
  const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
  const hideLegacy=()=>{{
    document.querySelectorAll('.queue-link-choice').forEach(a=>{{const p=a.closest('.panel');if(p)p.style.display='none'}});
    document.querySelectorAll("a.btn-link[href^='/pacientes?q=']").forEach(a=>{{const p=a.closest('p');if(p)p.style.display='none'}});
  }};
  const render=rows=>{{
    hideLegacy();
    if(!rows.length){{list.innerHTML='<div class="v1393-empty">No encontré fichas con ese nombre. Prueba con un apellido, otro nombre o la cédula si la conoces.</div>';return}}
    list.innerHTML=rows.map(r=>{{
      const id=r.national_id?'<strong>Cédula: '+esc(r.national_id)+'</strong>':'<strong>Sin cédula registrada</strong>';
      const hist=(Number(r.history_count||0)===1?'1 historia':Number(r.history_count||0)+' historias')+(r.last_history_date?' · Última: '+esc(r.last_history_date):'');
      const birth=r.birth_date?' · Nac. '+esc(r.birth_date):'';
      const reasons=(Array.isArray(r.reasons)?r.reasons:[]).filter(x=>x!=='identificación diferente').join(' · ');
      const linked=r.reception_linked?'<small>✓ Ficha vinculada desde Recepción</small>':'';
      const warn=r.id_conflict?'<small>⚠ BLOQUEADO: la cédula enviada por Recepción es diferente. Corrija el dato en Recepción antes de atender.</small>':'';
      const action=r.id_conflict?'<span class="blocked">Corregir en Recepción</span>':'<a href="/cola/'+encodeURIComponent(qid)+'/vincular/'+encodeURIComponent(r.id)+'">Vincular esta ficha</a>';
      return '<div class="v1393-card'+(r.id_conflict?' warn':'')+'"><div><b>'+esc(r.name||'SIN NOMBRE')+'</b>'+id+'<small>'+esc(hist)+birth+'</small>'+linked+(reasons?'<small>Coincide: '+esc(reasons)+'</small>':'')+warn+'</div>'+action+'</div>';
    }}).join('');
  }};
  let seq=0,debounce=0;
  const run=async()=>{{
    const mine=++seq;
    list.innerHTML='<div class="v1393-empty">Buscando fichas…</div>';
    try{{
      const r=await fetch('/api/v1393/queue-link-candidates/'+encodeURIComponent(qid)+'?q='+encodeURIComponent(input.value||'')+'&limit=20',{{cache:'no-store'}});
      const d=await r.json();
      if(mine!==seq)return;
      if(!r.ok||d.ok===false)throw new Error(d.error||'No se pudo buscar');
      render(Array.isArray(d.results)?d.results:[]);
    }}catch(err){{if(mine===seq)list.innerHTML='<div class="v1393-empty">'+esc(err.message||'No se pudo buscar')+'</div>'}}
  }};
  btn.addEventListener('click',run);
  input.addEventListener('input',()=>{{clearTimeout(debounce);debounce=setTimeout(run,220)}});
  input.addEventListener('keydown',e=>{{if(e.key==='Enter'){{e.preventDefault();run()}}}});
  run();
}})();
</script>
"""


# The original /cola screen was rendered from the legacy display_name, which
# may contain only a cédula. Replace its heading only when it is not a real name.
_original_inject_link = helper._inject_link_helper


def _inject_link_name(text: str, queue_id: str, initial: str) -> str:
    output = _original_inject_link(text, queue_id, initial)
    if re.search(r"<section class='page-head'>", output):
        import html
        def replace_heading(match):
            old = match.group("title")
            from html import unescape
            if _human_name(unescape(old)):
                return match.group(0)
            title = html.escape(_human_name(initial) or "Paciente por vincular")
            return match.group("prefix") + title + "</h1>"
        output = re.sub(
            r"(?P<prefix><section class='page-head'>.{0,240}?<h1>)(?P<title>[^<]+)</h1>",
            replace_heading,
            output,
            count=1,
            flags=re.S,
        )
    return output


helper._inject_link_helper = _inject_link_name
helper._queue_initial = _queue_initial_name_first
helper._candidate_rows = _candidate_rows_name_first
helper._helper_markup = _helper_markup_name_first

PATCH_BOOT_OK = True
