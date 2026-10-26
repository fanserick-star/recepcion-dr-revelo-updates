"""4.8.94: Inicio sin accesos duplicados y lista de pacientes protagonista.

Regresión puramente visual/estructural: sin historias clínicas ni red.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion/app"
html = (APP / "static/index.html").read_text(encoding="utf-8")
css = (APP / "static/home_remaster_4886.css").read_text(encoding="utf-8")
js = (APP / "static/home_remaster_4886.js").read_text(encoding="utf-8")
tv = (APP / "reception_tv_turns.py").read_text(encoding="utf-8")

start = html.index('<section id="inicio">')
finish = html.index('<section id="tv"')
home = html[start:finish]
assert home.index('id="r486Metrics"') < home.index('id="todayTable"'), "Mantener métricas compactas"
assert home.index('id="homeWeekNav"') < home.index('id="selectedDayTitle"')
assert home.index('id="selectedDayTitle"') < home.index('id="todayTable"')
assert home.index('id="todayTable"') < home.index('id="weekCards"'), "Atenciones antes que resumen semanal"
assert 'r494-attentions-primary' in home
assert 'r494-weekly-secondary' in home

# Solo quitar accesos redundantes del Inicio, no la página real de cada módulo.
for label in ("Mensajes de WhatsApp", "Facturación pendiente", "Sistema y respaldos"):
    assert label not in home, label
assert 'r486-shortcut' not in home
assert 'data-section="tv"' in html
assert 'id="r486TvFrame"' in html
assert 'onclick="show(\'facturacion\')"' in html
assert 'onclick="show(\'agenda\')"' in html

# El lateral conserva solo menú y no pierde la consulta de conexión ni la versión.
aside = html[html.index("<aside>"):html.index("</aside>")]
assert 'r486-tv-card' not in aside
assert 'id="connectionBadge"' not in aside
assert 'class="r494-connection-strip"' in html
assert 'id="connectionBadge"' in html
assert html.index('class="r494-connection-strip"') < html.index('<section id="inicio">')
assert "openProtectionStatus()" in html
assert 'id="logoutBtn"' in aside

# La TV permanece disponible desde su único menú; sin acceso flotante ni modal.
assert 'tvOfficialShortcut' not in tv
assert 'tvOfficialModal' not in tv
assert '@app.on_event("startup")' in tv
assert 'SERVICE.start()' in tv
assert '/api/tv-turnos/health' in tv

# Desplazamiento interno de la tabla, sticky th y cambio de fecha sin alterar API.
assert '#inicio .r494-attentions-primary #todayTable{' in css
assert 'overflow-y:auto!important' in css
assert 'position:sticky!important' in css
assert 'overscroll-behavior:contain' in css
assert "get('selectedDayTitle')" in js
assert "scrollIntoView({behavior:'smooth'" in js
assert "refreshTv()" in js  # mantener conteo de espera

print("RECEPTION_HOME_PATIENTS_FIRST_CLEANUP_4894_OK")
