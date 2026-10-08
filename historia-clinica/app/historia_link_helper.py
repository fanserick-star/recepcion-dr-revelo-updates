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


_ID_PLACEHOLDERS = {
    "SINCEDULA",
    "SINIDENTIFICACION",
    "NOIDENTIFICACION",
    "NOTIENE",
    "NOREGISTRA",
    "NOREGISTRADA",
    "NOAPLICA",
    "NINGUNA",
    "PENDIENTE",
    "CEDULAPENDIENTE",
    "NA",
}


def _usable_identification(value: object) -> str:
    """Return a normalized real identifier; ignore UI placeholders such as 'Sin cédula'."""
    compact = _norm_id(value)
    if not compact:
        return ""
    if compact in _ID_PLACEHOLDERS:
        return ""
    if compact.startswith("SINCEDULA") or compact.startswith("SINIDENTIFICACION"):
        return ""
    return compact


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
        queue_ident = _usable_identification(queue["identification"] or "")
        manual = str(query or "").strip()
        manual_ident = _usable_identification(manual)
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
        cand_ident = _usable_identification(row["national_id_search"] or row["national_id"] or "")

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
    """Read-only notice. Reception exclusively links patient identities."""
    return """
<section id="v1393-link-helper" style="margin:14px 0;padding:18px;border:1px solid #e2cbaa;border-radius:13px;background:#fff8e9">
  <h2 style="margin:0 0 7px">Pendiente de vinculación en Recepción</h2>
  <p>El doctor no puede vincular ni elegir fichas desde Historia Clínica.
  Solicite a Recepción que confirme la ficha correcta y vuelva a abrir este turno.</p>
</section>
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
            name = str(row["display_name"] or "").strip()
            if name and _norm_id(name) not in _ID_PLACEHOLDERS:
                return name
            return _usable_identification(row["identification"] or "")
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
            "legacy_link_route_preserved": False,
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
