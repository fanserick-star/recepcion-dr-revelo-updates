from __future__ import annotations

import difflib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "historia_clinica.db"


def _norm_text(value: object) -> str:
    raw = unicodedata.normalize("NFD", str(value or ""))
    raw = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", raw).strip().upper()


def _norm_id(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _norm_text(value))


def _tokens(value: object) -> list[str]:
    return [t for t in re.findall(r"[A-Z0-9]+", _norm_text(value)) if len(t) >= 2]


def _fmt_date(value: object) -> str:
    raw = str(value or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else raw


def _best_token_ratio(token: str, candidates: list[str]) -> float:
    if not token or not candidates:
        return 0.0
    if token in candidates:
        return 1.0
    return max(difflib.SequenceMatcher(None, token, c).ratio() for c in candidates)


def _candidate_rows(queue_id: str, query: str = "", limit: int = 15) -> dict:
    if not DB_PATH.is_file():
        return {"ok": False, "results": [], "error": "Base local de Historia no disponible"}

    with sqlite3.connect(DB_PATH, timeout=8) as conn:
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
        queue_ident = _norm_id(queue["identification"] or "")
        manual = str(query or "").strip()
        manual_ident = _norm_id(manual)
        manual_has_letters = bool(re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", manual))
        name_basis = manual if manual_has_letters else queue_name

        wanted_tokens = _tokens(name_basis)
        queue_tokens = _tokens(queue_name)
        pool_tokens = []
        for token in wanted_tokens + queue_tokens:
            if token not in pool_tokens:
                pool_tokens.append(token)
        pool_tokens = pool_tokens[:8]

        where = ["COALESCE(p.merged_into_patient_id,'')=''"]
        match_parts = []
        params: list[object] = []

        for ident in (manual_ident, queue_ident):
            if ident and len(ident) >= 6:
                match_parts.append("COALESCE(p.national_id_search,'')=?")
                params.append(ident)

        for token in pool_tokens:
            match_parts.append("UPPER(COALESCE(p.name_search,p.name,'')) LIKE ?")
            params.append("%" + token + "%")

        if not match_parts:
            return {
                "ok": True,
                "queue_id": str(queue_id),
                "initial_query": queue_ident or queue_name,
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
            WHERE {' AND '.join(where)}
              AND ({' OR '.join(match_parts)})
            ORDER BY COALESCE(p.updated_at,p.created_at,'') DESC
            LIMIT 140
        """
        rows = conn.execute(sql, params).fetchall()

    results = []
    q_name_norm = _norm_text(name_basis)
    min_name_matches = 1 if len(wanted_tokens) <= 1 else 2
    for row in rows:
        cand_name = str(row["name"] or "").strip()
        cand_name_norm = _norm_text(row["name_search"] or cand_name)
        cand_tokens = _tokens(cand_name_norm)
        cand_ident = _norm_id(row["national_id_search"] or row["national_id"] or "")

        score = 0
        reasons: list[str] = []
        matched_tokens = 0

        if manual_ident and len(manual_ident) >= 6 and cand_ident == manual_ident:
            score += 1500
            reasons.append("cédula buscada")
        if queue_ident and cand_ident and cand_ident == queue_ident:
            score += 1200
            reasons.append("misma cédula")

        if q_name_norm and cand_name_norm == q_name_norm:
            score += 320
            reasons.append("mismo nombre")

        for token in wanted_tokens or queue_tokens:
            ratio = _best_token_ratio(token, cand_tokens)
            if ratio >= 0.999:
                score += 70
                matched_tokens += 1
            elif ratio >= 0.86:
                score += 55
                matched_tokens += 1
            elif ratio >= 0.74:
                score += 34
                matched_tokens += 1

        if matched_tokens >= max(2, len(wanted_tokens or queue_tokens) - 1):
            reasons.append("nombre muy parecido")
        elif matched_tokens:
            reasons.append("nombre parcialmente parecido")

        history_count = int(row["history_count"] or 0)
        score += min(history_count, 15)

        id_conflict = bool(queue_ident and cand_ident and cand_ident != queue_ident)
        if id_conflict:
            score -= 90

        exact_id = bool(
            cand_ident
            and (
                (manual_ident and cand_ident == manual_ident)
                or (queue_ident and cand_ident == queue_ident)
            )
        )
        if not exact_id:
            required = min_name_matches
            if matched_tokens < required:
                continue
            if score < (65 if required == 1 else 95):
                continue

        results.append(
            {
                "id": str(row["id"]),
                "name": cand_name or "SIN NOMBRE",
                "national_id": str(row["national_id"] or "").strip(),
                "birth_date": _fmt_date(row["birth_date"]),
                "history_count": history_count,
                "last_history_date": _fmt_date(row["last_history_date"]),
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
        "initial_query": queue_ident or queue_name,
        "queue_name": queue_name,
        "queue_identification": str(queue["identification"] or "").strip(),
        "results": results[: max(1, min(int(limit or 15), 20))],
    }


def _helper_markup(queue_id: str, initial: str) -> str:
    qid_js = json.dumps(str(queue_id), ensure_ascii=False)
    initial_js = json.dumps(str(initial or ""), ensure_ascii=False)
    return f"""
<style id="v1393-link-style">
.v1393-link{{margin:14px 0;padding:15px;border:1px solid #cbdceb;border-radius:14px;background:#f8fbff}}
.v1393-link h2{{margin:0 0 5px;color:#173b66;font-size:18px}}
.v1393-link p{{margin:0 0 12px;color:#60758a;font-size:12px}}
.v1393-search{{display:flex;gap:8px;margin-bottom:12px}}
.v1393-search input{{flex:1;min-width:0;border:1px solid #b9c9d8;border-radius:10px;padding:10px 12px;font-size:14px;font-weight:750}}
.v1393-search button{{border:0;border-radius:10px;background:#246fae;color:#fff;padding:10px 16px;font-weight:850;cursor:pointer}}
.v1393-list{{display:grid;gap:8px}}
.v1393-card{{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:11px 12px;border:1px solid #d8e3ec;border-radius:11px;background:#fff}}
.v1393-card.warn{{border-color:#e8c980;background:#fffaf0}}
.v1393-card b{{display:block;color:#173b66;font-size:14px}}
.v1393-card strong{{display:inline-block;margin-top:3px;color:#162b3f;font-size:13px}}
.v1393-card small{{display:block;margin-top:3px;color:#6a7c8d;font-size:11px}}
.v1393-card a{{text-decoration:none;border-radius:9px;background:#2475d0;color:#fff;padding:9px 11px;font-weight:850;white-space:nowrap}}
.v1393-empty{{padding:12px;border:1px dashed #cbd5e1;border-radius:10px;color:#6b7d90;background:#fff}}
@media(max-width:680px){{.v1393-search{{flex-direction:column}}.v1393-card{{grid-template-columns:1fr}}}}
</style>
<section id="v1393-link-helper" class="v1393-link">
  <h2>Buscar y vincular ficha</h2>
  <p>La búsqueda usa primero la cédula y además tolera nombres incompletos o con errores de escritura.</p>
  <div class="v1393-search">
    <input id="v1393-link-q" autocomplete="off" placeholder="Cédula o parte del nombre">
    <button id="v1393-link-go" type="button">Buscar</button>
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
    if(!rows.length){{list.innerHTML='<div class="v1393-empty">No encontré una coincidencia segura. Puedes cambiar la cédula o escribir parte del nombre.</div>';return}}
    hideLegacy();
    list.innerHTML=rows.map(r=>{{
      const id=r.national_id?'<strong>Cédula: '+esc(r.national_id)+'</strong>':'<strong>Sin cédula registrada en Historia</strong>';
      const hist=(Number(r.history_count||0)===1?'1 historia':Number(r.history_count||0)+' historias')+(r.last_history_date?' · Última: '+esc(r.last_history_date):'');
      const birth=r.birth_date?' · Nac. '+esc(r.birth_date):'';
      const warn=r.id_conflict?'<small>⚠ La cédula de esta ficha es diferente. Revísala antes de vincular.</small>':'';
      const cls=r.id_conflict?'v1393-card warn':'v1393-card';
      return '<div class="'+cls+'"><div><b>'+esc(r.name||'SIN NOMBRE')+'</b>'+id+'<small>'+esc(hist)+birth+'</small>'+warn+'</div><a href="/cola/'+encodeURIComponent(qid)+'/vincular/'+encodeURIComponent(r.id)+'"'+(r.id_conflict?' data-conflict="1"':'')+'>Vincular esta ficha</a></div>';
    }}).join('');
    list.querySelectorAll('a[data-conflict="1"]').forEach(a=>a.addEventListener('click',ev=>{{
      if(!confirm('La cédula de esta ficha es diferente a la enviada por Recepción. ¿Está seguro de que es la ficha correcta?'))ev.preventDefault();
    }}));
  }};
  const run=async()=>{{
    list.innerHTML='<div class="v1393-empty">Buscando fichas…</div>';
    try{{
      const r=await fetch('/api/v1393/queue-link-candidates/'+encodeURIComponent(qid)+'?q='+encodeURIComponent(input.value||'')+'&limit=15',{{cache:'no-store'}});
      const d=await r.json();
      if(!r.ok||d.ok===false)throw new Error(d.error||'No se pudo buscar');
      render(Array.isArray(d.results)?d.results:[]);
    }}catch(err){{list.innerHTML='<div class="v1393-empty">'+esc(err.message||'No se pudo buscar')+'</div>'}}
  }};
  btn.addEventListener('click',run);
  input.addEventListener('keydown',e=>{{if(e.key==='Enter'){{e.preventDefault();run()}}}});
  run();
}})();
</script>
"""


def _inject_link_helper(text: str, queue_id: str, initial: str) -> str:
    if "v1393-link-helper" in text:
        return text
    if "Vincular ficha" not in text and "Paciente por vincular" not in text:
        return text

    encoded = quote(str(initial or ""), safe="")
    text = re.sub(
        r"href='/pacientes\?q=[^']*'",
        "href='/pacientes?q=" + encoded + "'",
        text,
    )

    helper = _helper_markup(queue_id, initial)
    marker = "</section>"
    if marker in text:
        return text.replace(marker, marker + helper, 1)
    return text.replace("</body>", helper + "</body>", 1)


def _queue_initial(queue_id: str) -> str:
    try:
        with sqlite3.connect(DB_PATH, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT display_name,identification FROM waiting_queue WHERE id=? LIMIT 1",
                (str(queue_id),),
            ).fetchone()
            if not row:
                return ""
            return str(row["identification"] or "").strip() or str(row["display_name"] or "").strip()
    except Exception:
        return ""


def _install_on_app(app: FastAPI) -> None:
    if getattr(app.state, "historia_link_helper_installed", False):
        return
    app.state.historia_link_helper_installed = True

    @app.get("/api/v1393/queue-link-candidates/{queue_id}")
    def v1393_queue_link_candidates(
        queue_id: str,
        q: str = Query("", max_length=180),
        limit: int = Query(15, ge=1, le=20),
    ):
        data = _candidate_rows(queue_id, q, limit)
        return JSONResponse(data, status_code=200 if data.get("ok") else 404)

    @app.get("/api/v1393/link-helper/health")
    def v1393_link_helper_health():
        return {
            "ok": True,
            "search_prefers_identification": True,
            "fuzzy_name_candidates": True,
            "multiple_candidates": True,
            "legacy_link_route_preserved": True,
            "patient_data_writes": False,
        }

    @app.middleware("http")
    async def _v1393_link_middleware(request: Request, call_next):
        response = await call_next(request)
        match = re.fullmatch(r"/cola/([^/]+)/atender/?", request.url.path)
        if not match:
            return response
        content_type = str(response.headers.get("content-type") or "")
        if "text/html" not in content_type.lower() or response.status_code != 200:
            return response

        chunks = []
        try:
            async for chunk in response.body_iterator:
                chunks.append(bytes(chunk))
        except Exception:
            return response

        raw = b"".join(chunks)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return HTMLResponse(
                raw.decode("utf-8", errors="replace"),
                status_code=response.status_code,
            )

        queue_id = match.group(1)
        initial = _queue_initial(queue_id)
        new_text = _inject_link_helper(text, queue_id, initial)
        headers = {
            k: v for k, v in dict(response.headers).items()
            if k.lower() not in {"content-length", "content-type"}
        }
        return HTMLResponse(new_text, status_code=response.status_code, headers=headers)


def install_fastapi_hook() -> None:
    """Mejora sólo el buscador de vínculo entre cola e Historia."""
    if getattr(FastAPI, "_historia_link_helper_hook", False):
        return
    FastAPI._historia_link_helper_hook = True
    original_init = FastAPI.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _install_on_app(self)
        except Exception:
            pass

    FastAPI.__init__ = patched_init
