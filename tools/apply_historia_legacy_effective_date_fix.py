from pathlib import Path

APP = Path('historia-clinica/app/app.py')
text = APP.read_text(encoding='utf-8-sig')


def replace_once(old: str, new: str, label: str):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontré {count}')
    text = text.replace(old, new, 1)


replace_once(
'''    return "".join(cards), detected, len(segments)\n\n\ndef clean_title(value, fallback="Consulta"):\n''',
'''    return "".join(cards), detected, len(segments)\n\n\ndef _history_date_iso(value):\n    raw = str(value or "").strip()\n    if not raw:\n        return ""\n    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):\n        try:\n            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")\n        except Exception:\n            pass\n    return ""\n\n\ndef legacy_effective_date(value, encounter_date=""):\n    """Fecha clínica efectiva de un registro importado sin modificar su texto.\n\n    Consulta Práctica podía guardar varios controles fechados dentro de una sola\n    historia cuyo encounter_date corresponde únicamente al registro contenedor.\n    Para ordenar/mostrar el historial usamos la fecha conocida más reciente entre\n    el registro original y los marcadores internos; el dato almacenado no cambia.\n    """\n    candidates = []\n    base_date = _history_date_iso(encounter_date)\n    if base_date:\n        candidates.append(base_date)\n    _text, markers = legacy_date_markers(value)\n    for marker in markers:\n        normalized = marker.get("normalized")\n        effective = _history_date_iso(normalized)\n        if effective:\n            candidates.append(effective)\n    return max(candidates) if candidates else str(encounter_date or "").strip()\n\n\ndef history_effective_date(h):\n    status = h["note_status"] or ("legacy" if h["is_legacy_locked"] else "signed")\n    raw_date = h["encounter_date"] or ""\n    if status == "legacy":\n        return legacy_effective_date(h["clinical_note"], raw_date)\n    return _history_date_iso(raw_date) or str(raw_date).strip()\n\n\ndef history_sort_key(h):\n    effective = history_effective_date(h)\n    original = _history_date_iso(h["encounter_date"])\n    status = h["note_status"] or ("legacy" if h["is_legacy_locked"] else "signed")\n    # Si un registro legacy representa un control interno posterior, la hora del\n    # contenedor antiguo no pertenece a ese control y no debe influir en el orden.\n    time_value = "" if status == "legacy" and effective != original else str(h["encounter_time"] or "")[:8]\n    try:\n        legacy_id = int(h["legacy_history_id"] or -1)\n    except Exception:\n        legacy_id = -1\n    return (effective, time_value, legacy_id, str(h["updated_at"] or ""))\n\n\ndef clean_title(value, fallback="Consulta"):\n''',
'insertar helpers de fecha efectiva',
)

replace_once(
'''    summary_title = clean_title(h["clinical_note"], "Registro clínico")\n    date_label = human_date(h["encounter_date"]) or h["encounter_date"] or "Sin fecha"\n    time_label = (h["encounter_time"] or "")[:5]\n    origin = "Registro histórico" if status == "legacy" else "Consulta registrada"\n''',
'''    summary_title = clean_title(h["clinical_note"], "Registro clínico")\n    original_date = _history_date_iso(h["encounter_date"]) or str(h["encounter_date"] or "").strip()\n    effective_date = history_effective_date(h)\n    legacy_rollup = status == "legacy" and bool(effective_date) and bool(original_date) and effective_date != original_date\n    date_label = human_date(effective_date or h["encounter_date"]) or h["encounter_date"] or "Sin fecha"\n    time_label = "" if legacy_rollup else (h["encounter_time"] or "")[:5]\n    date_caption = "Último control:" if legacy_rollup else "Fecha de consulta:"\n    origin = "Registro histórico" if status == "legacy" else "Consulta registrada"\n    if legacy_rollup:\n        origin += f" · registro original {human_date(original_date)}"\n''',
'actualizar encabezado de tarjeta legacy',
)

replace_once(
'''      <div class="cp-history-date"><span>Fecha de consulta:</span><strong>{e(date_label)}</strong>{f'<time>{e(time_label)}</time>' if time_label else ''}</div>\n''',
'''      <div class="cp-history-date"><span>{e(date_caption)}</span><strong>{e(date_label)}</strong>{f'<time>{e(time_label)}</time>' if time_label else ''}</div>\n''',
'usar etiqueta dinámica en tarjeta',
)

replace_once(
'''        all_histories = conn.execute(\n            "SELECT * FROM encounters WHERE patient_id=? AND note_status!='draft' ORDER BY encounter_date DESC, encounter_time DESC, legacy_history_id DESC",\n            (patient_id,),\n        ).fetchall()\n''',
'''        all_histories = list(conn.execute(\n            "SELECT * FROM encounters WHERE patient_id=? AND note_status!='draft' ORDER BY encounter_date DESC, encounter_time DESC, legacy_history_id DESC",\n            (patient_id,),\n        ).fetchall())\n        all_histories.sort(key=history_sort_key, reverse=True)\n''',
'ordenar historial completo por fecha efectiva',
)

replace_once(
'''            histories = conn.execute("""\n                SELECT * FROM encounters WHERE patient_id=? AND\n                note_status!='draft' AND (clinical_note LIKE ? OR legacy_history_t LIKE ?)\n                ORDER BY encounter_date DESC, encounter_time DESC, legacy_history_id DESC\n            """, (patient_id, like, like)).fetchall()\n''',
'''            histories = list(conn.execute("""\n                SELECT * FROM encounters WHERE patient_id=? AND\n                note_status!='draft' AND (clinical_note LIKE ? OR legacy_history_t LIKE ?)\n                ORDER BY encounter_date DESC, encounter_time DESC, legacy_history_id DESC\n            """, (patient_id, like, like)).fetchall())\n            histories.sort(key=history_sort_key, reverse=True)\n''',
'ordenar búsqueda de historial por fecha efectiva',
)

replace_once(
'''    last_date = human_date(last_signed["encounter_date"]) if last_signed else "Sin registros"\n''',
'''    last_date = human_date(history_effective_date(last_signed)) if last_signed else "Sin registros"\n''',
'corregir último control',
)

APP.write_text(text, encoding='utf-8')
print('FIX_APPLIED', APP)
