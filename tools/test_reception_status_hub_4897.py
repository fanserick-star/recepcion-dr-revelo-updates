"""Recepción 4.8.97 — panel único de estados reales, sin sondeos a Neon."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1] / "recepcion/app"
html = (root/"static/index.html").read_text(encoding="utf-8")
css = (root/"static/home_remaster_4886.css").read_text(encoding="utf-8")
js = (root/"static/sidebar_status_hub_4897.js").read_text(encoding="utf-8")
app = (root/"app.py").read_text(encoding="utf-8")
version = json.loads((root/"recepcion-version.json").read_text(encoding="utf-8"))
manifest = json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
assert tuple(map(int, version["version"].split("."))) >= (4,8,97)
assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == version["version"]
assert "static/sidebar_status_hub_4897.js" in manifest["copy"]
assert "static/sidebar_status_hub_4897.js" in manifest["required_dependencies"]
assert '/static/sidebar_status_hub_4897.js?v=4.8.105' in html
assert '/static/home_remaster_4886.css?v=' + version["version"] in html

aside = html[html.index("<aside>"):html.index("</aside>")]
assert aside.count("r497-status-row") == 4
for name in ("r497SystemValue","r497HistoryValue","r497TvValue","r497VersionValue",
             "r497SystemRow","r497HistoryRow","r497TvRow","r497VersionRow"):
    assert 'id="'+name+'"' in aside, name
assert "r497-status-sources" in aside
for name in ("connectionBadge","historiaDoctorBadge","sidebarRealVersion"):
    assert aside.count('id="'+name+'"') == 1
assert 'onclick="openProtectionStatus()"' in aside
assert 'onclick="show(\'tv\')"' in aside
assert "r486-tv-card" not in aside

# Never conflate the independent TV state with LAN or cloud state.
assert "source.classList.contains(x)" in js
assert "lan.classList.contains('lan')" in js
assert "lan.classList.contains('error')" in js
assert "const count=pending?" in js
assert "'Conectada'+(count>0" in js
assert "online?'Conectada':reachable?'Sin conexión':'Sin comprobar'" in js
assert "'/api/reception/tv/status'" in js
assert "data?.tv_online===true" in js and "data?.ok===true" in js
assert "'/api/tv-turnos/health'" in js
assert "event.source!==frame.contentWindow" in js
assert "event.origin!==allowedOrigin" in js
assert "data.type!=='reception-tv-heartbeat-v1'" in js
assert "window.addEventListener('message',onTvMessage)" in js
assert 'sendTvStatusToReception(s)' in (root/'tv_control.html').read_text(encoding='utf-8')
assert "typeof data.tv_online!=='boolean'" in js
assert "document.hidden||reading" in js
assert "app.classList.contains('hidden')" in js
assert "new MutationObserver(renderOriginals)" in js
assert "authState.observe(app" in js
assert "setInterval(()=>refreshTv(false),30000)" in js
for denied in ("/api/protection","/api/historia-bridge","neon","CloudSession",
               "localStorage","sessionStorage","/api/v4501/system-status"):
    assert denied not in js, denied
assert 'from reception_tv_turns import SERVICE' in app
assert 'status = SERVICE.status()' in app
assert 'http://127.0.0.1:8899/api/status' not in app
assert '"tv_online": bool(status.get("tv_online"))' in app
assert 'timeout=1.3' not in app

assert 'aside .r495-sidebar-status.r497-status-hub' in css
assert "r497-status-row" in css and "r497-status-sources" in css
assert "overflow:hidden!important" in css
import subprocess
subprocess.run(["node", "tools/test_reception_tv_sidebar_message_48105.mjs"], check=True)
print("RECEPTION_STATUS_HUB_4897_OK")
