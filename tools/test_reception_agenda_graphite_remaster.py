"""UI-only remaster contract: no clinical/agenda/WhatsApp write paths modified."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/"recepcion/app/static/index.html").read_text(encoding="utf-8")
js=(ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
css=(ROOT/"recepcion/app/static/style.css").read_text(encoding="utf-8")
assert '<section id="agenda" class="hidden agenda-remaster-dark">' in html
assert '<div class="agenda-focus-toolbar">' in html
assert 'data-agenda-range=' not in html
assert 'Jornada completa' in html and 'agendaFocusSummary' in html
assert "agendaRemasterRange='all'" in js
assert "return AGENDA_SLOT_TIMES;" in js
assert "function agendaVisibleSlotTimes()" in js
assert "for(const time of agendaVisibleSlotTimes())" in js
assert "if(!lunch&&time==='14:00')" in js
assert "if(dateObj.getDay()===3&&minute<10*60)return false" in js
assert "grid-template-columns:62px repeat(4,minmax(205px,1fr))" in css
assert "#agenda.agenda-remaster-dark" in css
assert "agenda-more-navigation" in html and "agenda-state-details" in html
assert "refreshAgendaWhatsapp()" in html
assert "moveNativeAgendaWeek(-1)" in html
assert "agendaNativeWeek" in js
assert "agendaNativeGrid" in html
assert "openAgendaSlotPicker(" in js
assert "openLinkedAgendaDetail(" in js
assert "openUnlinkedAgendaDetail(" in js
# The only new helper mutates display controls and grid, not patient or agenda API.
display=js.split("function setAgendaTimeRange(",1)[1].split("function agendaStatusInfo(",1)[0]
for forbidden in ("api(", "fetch(", "localStorage", "singleFlightMutation", "postMessage", "refreshWhatsappAlarm"):
    assert forbidden not in display
assert "function agendaTime12(value)" in js
assert "title=\\"Agendar cita ${esc(agendaTime12(time))}" in js or "agendaTime12(time)" in js
print("RECEPTION_AGENDA_GRAPHITE_FULL_DAY_12_HOURS_OK")
