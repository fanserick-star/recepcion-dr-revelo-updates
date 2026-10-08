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
        queue_ident = helper._usable_identification(queue["identification"])
        if not queue_ident and not _human_name(queue["display_name"]):
            queue_ident = helper._usable_identification(queue["display_name"])
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
    """Keep existing helper injection as notice only; no linking UI in Historia."""
    return _reception_only_link_notice(queue_id, initial)


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


_reception_only_link_notice = helper._helper_markup
helper._inject_link_helper = _inject_link_name
helper._queue_initial = _queue_initial_name_first
helper._candidate_rows = _candidate_rows_name_first
helper._helper_markup = _helper_markup_name_first

PATCH_BOOT_OK = True
