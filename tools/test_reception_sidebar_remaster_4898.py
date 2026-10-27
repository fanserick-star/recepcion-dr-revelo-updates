"""Recepción 4.8.98 — menú lateral profesional sin quitar auditoría ni datos."""
from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]/"recepcion/app"
html=(root/"static/index.html").read_text(encoding="utf-8")
css=(root/"static/home_remaster_4886.css").read_text(encoding="utf-8")
core=(root/"core_runtime.py").read_text(encoding="utf-8")
manifest=json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
version=json.loads((root/"recepcion-version.json").read_text(encoding="utf-8"))["version"]

assert version=="4.8.98"==manifest["version"]==manifest["app_version"]==manifest["runtime_version"]
assert '/static/home_remaster_4886.css?v=4.8.98' in html
aside=html[html.index("<aside>"):html.index("</aside>")]
nav=aside[aside.index("<nav"):aside.index("</nav>")]
for name in ("inicio","agenda","facturacion","reportes","pacientes","tv","config"):
    assert f'data-section="{name}"' in nav, name
assert 'data-section="actividad"' not in nav

# Original v4.4.0 Audit UI still injects Activity at runtime and
# handles show('actividad'). We hide only that menu button and keep its page.
assert "function ensureOpsUI()" in core
assert "configBtn.insertAdjacentHTML('beforebegin'" in core
assert "section.id='actividad'" in core
assert "if(id==='actividad')setTimeout(()=>switchOpsTab('activity'),0)" in core

config=html[html.index('<section id="config"'):html.index('</main>')]
system=config[config.index('data-config-section="sistema"'):]
assert 'id="configActivityAccess"' in system
assert '<summary>Registro de actividad · Avanzado</summary>' in system
assert 'onclick="show(\'actividad\')"' in system

# Styling is scoped to the sidebar, preserving all pages and system badges.
assert 'body.r486-ui aside .side-nav .nav-btn[data-section="actividad"]' in css
assert 'display:none!important' in css
assert 'body.r486-ui aside .brand.brand-wide' in css
assert 'body.r486-ui aside .r495-sidebar-status.r497-status-hub' in css
assert 'body.r486-ui aside .r497-status-row' in css
assert 'min-height:42px!important;height:42px!important' in css
assert '@media(max-height:700px) and (min-width:801px)' in css
assert 'background:linear-gradient(180deg,#eaf2fa 0%,#e4edf7 100%)' in css
assert 'background:#f8fbff!important' in css
assert 'border-color:#84b0e4!important' in css
for id in ("r497SystemRow","r497HistoryRow","r497TvRow","r497VersionRow"):
    assert 'id="'+id+'"' in aside, id
for id in ("connectionBadge","historiaDoctorBadge","sidebarRealVersion"):
    assert 'id="'+id+'"' in aside, id
assert 'id="todayTable"' in html
assert 'id="r486TvFrame"' in html
assert 'id="nightFiscalSettings"' in html

print("RECEPTION_SIDEBAR_REMASTER_4898_OK")
