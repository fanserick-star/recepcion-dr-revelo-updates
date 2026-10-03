from __future__ import annotations

import difflib
import json
import re
import sqlite3

import historia_link_helper as helper

PATCH_VERSION = "1.3.96"


def _queue_initial_name_first(queue_id: str) -> str:
    try:
        with sqlite3.connect(helper.DB_PATH, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT display_name,identification FROM waiting_queue WHERE id=? LIMIT 1",
                (str(queue_id),),
            ).fetchone()
            if not row:
                return ""
            return str(row["display_name"] or "").strip() or str(row["identification"] or "").strip()
    except Exception:
        return ""


def _candidate_rows_name_first(queue_id: str, query: str = "", limit: int = 15) -> dict:
    if not helper.DB_PATH.is_file():
        return {"ok": False, "results": [], "error": "Base local de Historia no disponible"}

    with sqlite3.connect(helper.DB_PATH, timeout=8) as conn:
        conn.row_factory = sqlite3.Row
        queue = conn.execute(
            """SELECT id,display_name,identification,status
               FROM waiting_queue
               WHERE id=? AND status IN ('waiting','in_consultation')
               LIMIT 1""",
            (str(queue_id),),
        ).fetchone()
        if not queue:
            return {"ok": False, "results": [], "error": "Turno no encontrado"}

        queue_name = str(queue["display_name"] or "").strip()
        queue_ident = helper._norm_id(queue["identification"] or "")
        manual = str(query or "").strip()
        manual_has_letters = bool(re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", manual))
        name_basis = manual if manual_has_letters else queue_name
        manual_ident = helper._norm_id(manual) if not manual_has_letters else ""

        wanted_tokens = helper._tokens(name_basis)
        queue_tokens = helper._tokens(queue_name)
        pool_tokens = []
        for token in wanted_tokens + queue_tokens:
            if token not in pool_tokens:
                pool_tokens.append(token)
        pool_tokens = pool_tokens[:8]

        match_parts = []
        params = []
        # Nombre primero: basta una parte para construir una lista amplia.
        for token in pool_tokens:
            match_parts.append("UPPER(COALESCE(p.name_search,p.name,'')) LIKE ?")
            params.append("%" + token + "%")
        # Identificación queda como refuerzo cuando realmente existe.
        for ident in (manual_ident, queue_ident):
            if ident and len(ident) >= 6:
                match_parts.append("COALESCE(p.national_id_search,'')=?")
                params.append(ident)

        if not match_parts:
            return {
                "ok": True,
                "queue_id": str(queue_id),
                "initial_query": queue_name or queue_ident,
                "queue_name": queue_name,
                "queue_identification": str(queue["identification"] or "").strip(),
                "results": [],
            }

        sql = f"""
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
              AND ({' OR '.join(match_parts)})
            ORDER BY COALESCE(p.updated_at,p.created_at,'') DESC
            LIMIT 120
        """
        rows = conn.execute(sql, params).fetchall()

    q_name_norm = helper._norm_text(name_basis)
    results = []
    for row in rows:
        cand_name = str(row["name"] or "").strip()
        cand_name_norm = helper._norm_text(row["name_search"] or cand_name)
        cand_tokens = helper._tokens(cand_name_norm)
        cand_ident = helper._norm_id(row["national_id_search"] or row["national_id"] or "")

        score = 0
        reasons = []
        matched_tokens = 0
        if q_name_norm and cand_name_norm == q_name_norm:
            score += 700
            reasons.append("mismo nombre completo")
        else:
            for token in wanted_tokens or queue_tokens:
                if not cand_tokens:
                    continue
                ratio = max(difflib.SequenceMatcher(None, token, c).ratio() for c in cand_tokens)
                if ratio >= 0.999:
                    score += 115
                    matched_tokens += 1
                elif ratio >= 0.86:
                    score += 82
                    matched_tokens += 1
                elif ratio >= 0.74:
                    score += 46
                    matched_tokens += 1
            total = len(wanted_tokens or queue_tokens)
            if total and matched_tokens == total:
                score += 180
                reasons.append("nombre coincide aunque esté en otro orden")
            elif matched_tokens >= max(2, total - 1):
                score += 90
                reasons.append("nombre muy parecido")
            elif matched_tokens:
                reasons.append("nombre parcialmente parecido")

        if manual_ident and cand_ident and cand_ident == manual_ident:
            score += 460
            reasons.append("misma identificación buscada")
        if queue_ident and cand_ident:
            if cand_ident == queue_ident:
                score += 460
                reasons.append("misma identificación")
            else:
                score -= 500
                reasons.append("identificación diferente")

        history_count = int(row["history_count"] or 0)
        score += min(history_count, 20)
        if score <= 0:
            continue

        id_conflict = bool(queue_ident and cand_ident and cand_ident != queue_ident)
        results.append(
            {
                "id": str(row["id"]),
                "name": cand_name or "SIN NOMBRE",
                "national_id": str(row["national_id"] or "").strip(),
                "birth_date": helper._fmt_date(row["birth_date"]),
                "history_count": history_count,
                "last_history_date": helper._fmt_date(row["last_history_date"]),
                "score": int(score),
                "reasons": reasons,
                "id_conflict": id_conflict,
            }
        )

    results.sort(
        key=lambda x: (x["score"], x["history_count"], x["last_history_date"]),
        reverse=True,
    )
    return {
        "ok": True,
        "queue_id": str(queue_id),
        "initial_query": queue_name or queue_ident,
        "queue_name": queue_name,
        "queue_identification": str(queue["identification"] or "").strip(),
        "results": results[: max(1, min(int(limit or 15), 20))],
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
  <p>Escribe nombres o apellidos. La lista se actualiza automáticamente; la cédula se usa como refuerzo cuando existe.</p>
  <div class="v1393-live">Búsqueda en vivo · no necesitas presionar Buscar</div>
  <div class="v1393-search">
    <input id="v1393-link-q" autocomplete="off" placeholder="Nombre o apellido del paciente">
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
  const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
  const hideLegacy=()=>{{
    document.querySelectorAll('.queue-link-choice').forEach(a=>{{const p=a.closest('.panel');if(p)p.style.display='none'}});
    document.querySelectorAll("a.btn-link[href^='/pacientes?q=']").forEach(a=>{{const p=a.closest('p');if(p)p.style.display='none'}});
  }};
  const render=rows=>{{
    if(!rows.length){{list.innerHTML='<div class="v1393-empty">No encontré fichas con ese nombre. Prueba con un apellido, otro nombre o la cédula si la conoces.</div>';return}}
    hideLegacy();
    list.innerHTML=rows.map(r=>{{
      const id=r.national_id?'<strong>Cédula: '+esc(r.national_id)+'</strong>':'<strong>Sin cédula registrada</strong>';
      const hist=(Number(r.history_count||0)===1?'1 historia':Number(r.history_count||0)+' historias')+(r.last_history_date?' · Última: '+esc(r.last_history_date):'');
      const birth=r.birth_date?' · Nac. '+esc(r.birth_date):'';
      const reasons=(Array.isArray(r.reasons)?r.reasons:[]).filter(x=>x!=='identificación diferente').join(' · ');
      const warn=r.id_conflict?'<small>⚠ BLOQUEADO: esta ficha tiene una cédula diferente a la enviada por Recepción.</small>':'';
      const action=r.id_conflict?'<span class="blocked">No vincular</span>':'<a href="/cola/'+encodeURIComponent(qid)+'/vincular/'+encodeURIComponent(r.id)+'">Vincular esta ficha</a>';
      return '<div class="v1393-card'+(r.id_conflict?' warn':'')+'"><div><b>'+esc(r.name||'SIN NOMBRE')+'</b>'+id+'<small>'+esc(hist)+birth+'</small>'+(reasons?'<small>Coincide: '+esc(reasons)+'</small>':'')+warn+'</div>'+action+'</div>';
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


helper._queue_initial = _queue_initial_name_first
helper._candidate_rows = _candidate_rows_name_first
helper._helper_markup = _helper_markup_name_first

PATCH_BOOT_OK = True
