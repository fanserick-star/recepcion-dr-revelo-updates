"""4.8.95 — Sidebar readable, fiscal automation in Configuration only.

Synthetic UI/source regression; no patient data, invoices, WhatsApp or Neon touched.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion/app"
html = (APP / "static/index.html").read_text(encoding="utf-8")
css = (APP / "static/home_remaster_4886.css").read_text(encoding="utf-8")
fiscal = (APP / "static/night_closing_4888.js").read_text(encoding="utf-8")
history = (APP / "reception_history_transport.py").read_text(encoding="utf-8")
version = json.loads((APP / "recepcion-version.json").read_text(encoding="utf-8"))
manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))

assert version["version"] == manifest["version"] == manifest["app_version"] == manifest["runtime_version"]
assert tuple(map(int, version["version"].split("."))) >= (4, 8, 95)

aside = html[html.index("<aside>"):html.index("</aside>")]
top = html[html.index('<div class="global-toolbar">'):html.index('<section id="inicio">')]
assert 'class="r495-sidebar-status r497-status-hub"' in aside
assert 'id="connectionBadge"' in aside
assert 'onclick="openProtectionStatus()"' in aside
assert 'class="r494-connection-strip"' not in html
assert 'id="connectionBadge"' not in top
assert 'id="connectionBadge"' == 'id="connectionBadge"'
assert aside.count('id="connectionBadge"') == 1
assert "ensureBadge()" in history and "c.insertAdjacentElement('afterend',b)" in history
assert "sidebarRealVersion" in (APP / "reception_version_sidebar.py").read_text(encoding="utf-8")
assert "r495-sidebar-status #historiaDoctorBadge.lan" in css
assert "r495-sidebar-status #sidebarRealVersion" in css
assert "overflow-y:auto!important" in css and "aside .side-nav" in css
assert '/static/home_remaster_4886.css?v=' + version["version"] in html

# No fiscal controls in everyday invoices; keep AZUR invoices area unchanged.
billing = html[html.index('<section id="facturacion"'):html.index('<section id="reportes"')]
assert 'Cierre fiscal inteligente' not in billing
assert 'rpNightState' not in billing

config = html[html.index('<section id="config"'):html.index('</main>')]
billing_config = config[config.index('data-config-section="facturacion"'):config.index('data-config-section="sistema"')]
assert 'id="nightFiscalSettings"' in billing_config
assert 'id="nightFiscalConfigSlot"' in billing_config
assert '<summary>Cierre fiscal inteligente · 19:00 (opcional)</summary>' in billing_config
assert 'config-advanced' in billing_config
assert 'id="nightFiscalSettings"' not in config[config.index('data-config-section="sistema"'):]

# Read-only refresh only while the detail is expanded and settings visible.
assert "document.getElementById('nightFiscalConfigSlot')" in fiscal
assert "document.getElementById('nightFiscalSettings')" in fiscal
assert "slot.appendChild(panel)" in fiscal
assert "disclosure.addEventListener('toggle'" in fiscal
assert "!document.getElementById('config')?.classList.contains('hidden')" in fiscal
assert "document.getElementById('facturacion')" not in fiscal
assert "section.insertBefore(panel" not in fiscal
assert "'/api/night-close/status'" in fiscal
assert "'/api/night-close/config'" in fiscal
assert "FACTURAR AUTOMATICAMENTE" in fiscal
assert "if(!window.confirm(" in fiscal
assert '/static/night_closing_4888.js?v=4.8.95' in html

# Core clinical/business routines remain present.
assert 'id="todayTable"' in html
assert 'data-section="tv"' in html
assert 'id="r486TvFrame"' in html
assert 'data-config-tab="facturacion"' in html
print("RECEPTION_SIDEBAR_FISCAL_SETTINGS_4895_OK")
