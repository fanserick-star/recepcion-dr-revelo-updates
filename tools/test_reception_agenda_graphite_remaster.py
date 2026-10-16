"""UI-only remaster contract: no clinical/agenda/WhatsApp write paths modified."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/"recepcion/app/static/index.html").read_text(encoding="utf-8")
js=(ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
css=(ROOT/"recepcion/app/static/style.css").read_text(encoding="utf-8")
assert '<section id="agenda" class="hidden agenda-remaster-dark">' in html
assert '<div class="agenda-focus-toolbar">' in html
for value in ("morning","afternoon","all"):
    assert 'data-agenda-range="'+value+'"' in html
    assert "setAgendaTimeRange('"+value+"')" in html
assert "function agendaVisibleSlotTimes()" in js
assert "for(const time of agendaVisibleSlotTimes())" in js
assert "if(agendaRemasterRange==='all'&&!lunch&&time==='14:00')" in js
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
assert "agendaRemasterRange='morning'" in js
assert ".agenda-focus-tabs button.active" in css
print("RECEPTION_AGENDA_GRAPHITE_DISPLAY_ONLY_4_DAYS_DAYPARTS_OK")
