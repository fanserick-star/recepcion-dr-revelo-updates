from __future__ import annotations

"""Búsqueda manual de Historia orientada al nombre escrito por Recepción.

Este módulo es semántico (no una cadena de versiones). Corrige el caso en el
que una búsqueda como ``ANCHUNDIA VELEZ MANUEL`` quedaba diluida entre cientos
de pacientes que sólo compartían ``MANUEL``.
"""

import re

import reception_history_identity_consolidated as identity

APP_VERSION = identity.APP_VERSION


def _typed_name_tokens(query):
    normalized = identity._fuzzy_text(query)
    tokens = [token for token in normalized.split() if len(token) >= 2]
    alpha_tokens = [token for token in tokens if any(ch.isalpha() for ch in token)]
    # Dos o más palabras alfabéticas representan una búsqueda por nombre.
    # Una identificación extranjera alfanumérica sin espacios sigue pasando
    # por el flujo de identificación.
    return alpha_tokens if len(alpha_tokens) >= 2 else []


def _score_candidate(row, demo, query, typed_tokens):
    score, reasons = identity._candidate_score(row, demo, query)
    if typed_tokens:
        row_name = identity._fuzzy_text(row.get("name_search") or row.get("name"))
        row_tokens = set(row_name.split())
        matches = sum(1 for token in typed_tokens if token in row_tokens)
        # La búsqueda que la recepcionista escribió manda sobre datos
        # administrativos antiguos o incompletos.
        score += matches * 45
        if matches == len(typed_tokens):
            score += 90
            reasons = ["nombre buscado"] + [r for r in reasons if r != "nombre muy parecido"]
        elif matches >= max(2, len(typed_tokens) - 1):
            score += 35
            reasons = ["nombre muy parecido"] + [r for r in reasons if r != "nombre muy parecido"]
    return score, reasons


def _search_candidates(cur, demo, query, limit):
    typed_tokens = _typed_name_tokens(query)
    q_norm = identity._fuzzy_text(query)
    q_tokens = [t for t in q_norm.split() if len(t) >= 2]
    demo_tokens = [
        t for t in identity._fuzzy_text(demo.get("name")).split() if len(t) >= 2
    ]

    name_expr = (
        "TRANSLATE(UPPER(COALESCE(p.name_search,p.name,'')),"
        "'ÁÉÍÓÚÜÑZ','AEIOUUNS')"
    )
    where = []
    params = []

    if typed_tokens:
        # Para 2-3 palabras exigimos todas. Para nombres más largos toleramos
        # una palabra ausente (p. ej. segundo nombre omitido en el legado).
        minimum = len(typed_tokens) if len(typed_tokens) <= 3 else len(typed_tokens) - 1
        match_terms = []
        for token in typed_tokens[:6]:
            match_terms.append(f"CASE WHEN {name_expr} LIKE %s THEN 1 ELSE 0 END")
            params.append("%" + token + "%")
        where.append("(" + " + ".join(match_terms) + ") >= %s")
        params.append(minimum)
    else:
        # Sin una búsqueda nominal clara conservamos los demás caminos:
        # identificación, celular, fecha de nacimiento y nombre parcial.
        ident = identity._usable_id(query) if len(q_tokens) <= 1 else ""
        phone = identity._norm_phone(query)
        birth = identity._iso_date(demo.get("birth_date"))
        demo_id = identity._usable_id(demo.get("national_id"))
        demo_phone = identity._norm_phone(demo.get("phone"))

        if ident:
            where.append("p.national_id_search=%s")
            params.append(ident)
        if demo_id:
            where.append("p.national_id_search=%s")
            params.append(demo_id)
        for value in (phone, demo_phone):
            if value and len(value) >= 7:
                where.append(
                    "regexp_replace(COALESCE(p.phone,''),'[^0-9]','','g') LIKE %s"
                )
                params.append("%" + value[-9:] + "%")
        if birth:
            where.append("p.birth_date=%s")
            params.append(birth)

        tokens = q_tokens or demo_tokens
        if tokens:
            token_parts = []
            for token in tokens[:6]:
                token_parts.append(name_expr + " LIKE %s")
                params.append("%" + token + "%")
            where.append("(" + " OR ".join(token_parts) + ")")

    if not where:
        return []

    sql_limit = max(30, min(160, int(limit or 30) * 5))
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
        row = identity._dict_row(cur, raw)
        canonical_id = (
            identity._clean(row.get("merged_into_patient_id"), 120)
            or identity._clean(row.get("id"), 120)
        )
        if not canonical_id or canonical_id in seen:
            continue
        if canonical_id != identity._clean(row.get("id"), 120):
            canonical = identity._patient_row(cur, canonical_id)
            if canonical:
                row = canonical
        row.update(identity._history_summary(cur, row["id"]))
        score, reasons = _score_candidate(row, demo, query, typed_tokens)
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
            identity._clean(r.get("last_history_date"), 20),
        ),
        reverse=True,
    )
    return rows[: max(1, min(int(limit or 30), 40))]


# El endpoint ya registrado resuelve este símbolo al momento de ejecutar la
# petición, por lo que no se duplica ninguna ruta ni se toca el flujo de link.
identity._search_candidates = _search_candidates
