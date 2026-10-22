"""Regresión visual de Historia 1.4.16: foco por consulta/revisión y controles intactos.

No crea, elimina ni edita pacientes, colas, llamadas o historias clínicas.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
source = (ROOT / "app.py").read_text(encoding="utf-8")
css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
calls = (ROOT / "doctor_turn_call.py").read_text(encoding="utf-8")
tree = ast.parse(source)

# El diagnóstico de la atención se toma de los datos existentes, no de índices
# inventados. Procedimientos nunca se confunden con revisiones gratuitas.
assert 'queue_kind_class = "queue-row-review" if exam_review else (' in source
assert '"queue-row-procedure-muted" if is_procedure' in source
assert 'queue_status_class = "queue-row-waiting" if is_waiting else "queue-row-attending"' in source
assert 'queue_kind_label = "REVISIÓN DE EXÁMENES" if exam_review' in source
assert 'queue_state_label = "EN ESPERA" if is_waiting else "EN ATENCIÓN"' in source
assert "if not is_procedure else" in source
assert "waiting_consult_count = sum(" in source
assert "waiting_review_count = sum(" in source
assert 'if row["status"] == "waiting"' in source
assert "queue-spotlight-totals" in source and "queue-spotlight-head" in source

# Acciones existentes y navegación del doctor conservadas.
assert 'href="/" title="Volver al inicio"' in source
assert "doctor_turn_call.queue_button(r, real_turn, _queue_is_procedure)" in source
assert "f\"<a class='queue-row-main' href='{href}'" in source
assert "class='queue-dismiss-form js-queue-dismiss'" in source
assert "clinic" not in calls.lower() or "/api/doctor-turn-call/" in calls
assert "def new_consultation_v135" in source
assert "confirm-finalize" in source

# La animación se aplica solo al anillo del foco, nunca a la ficha completa.
assert "@keyframes doctor-beacon-ring" in css
assert ".queue-beacon::before" in css
assert ".queue-row-attending .queue-beacon::before" in css
assert "animation:none!important" in css
assert "@media(prefers-reduced-motion:reduce)" in css
assert ".queue-row-review" in css and ".queue-row-procedure-muted" in css
assert "queue-row>.js-doctor-call" in css
assert ".queue-row-action" in css
assert "queue-row:first-child" in css
assert "font-size:22px!important" in css
assert "grid-template-columns:1fr!important" in css

print("HISTORIA_QUEUE_BEACON_UI_1416_OK")
