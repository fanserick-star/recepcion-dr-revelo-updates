"""Regresiones estáticas del Inicio y TV integrados en Recepción 4.8.86."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion/app"
html = (APP / "static/index.html").read_text(encoding="utf-8")
js = (APP / "static/home_remaster_4886.js").read_text(encoding="utf-8")
css = (APP / "static/home_remaster_4886.css").read_text(encoding="utf-8")
server = (APP / "app.py").read_text(encoding="utf-8")
manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))
version = json.loads((APP / "recepcion-version.json").read_text(encoding="utf-8"))

assert tuple(map(int, version["version"].split("."))) >= (4, 8, 86)  # v4.8.86 y futuras versiones conservan el remaster
assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == version["version"]
for name in ["static/home_remaster_4886.js", "static/home_remaster_4886.css"]:
    assert name in manifest["copy"] and name in manifest["required_dependencies"], name
    assert name in html, name

assert 'data-section="tv"' in html
assert 'onclick="show(\'tv\')"' in html
assert 'id="r486TvFrame"' in html
assert 'id="r486TvState"' not in html  # control duplicado de TV retirado del lateral
assert 'id="r486Metrics"' in html
assert "http://127.0.0.1:8899/control" in js
assert 'from reception_tv_turns import SERVICE' in server
assert 'status = SERVICE.status()' in server
assert "http://127.0.0.1:8899/api/status" not in server
assert '@app.get("/api/reception/tv/status", dependencies=[core.Depends(core.current_user)])' in server
assert "status.get(\"tv_online\")" in server and "status.get(\"history_online\")" in server
assert "tvState&&tvState.ok&&tvState.history_online" in js
assert "setInterval(" not in js
assert "WHATSAPP_ACCESS_TOKEN" not in js
assert "#inicio .week-cards" in css
assert "grid-template-columns:repeat(4,minmax(0,1fr))" in css
assert "r486-tv-card" not in html
assert "r486-shortcut" not in html
assert 'class="r495-sidebar-status r497-status-hub"' in html
assert 'class="r494-connection-strip"' not in html
assert 'id="connectionBadge"' in html
assert "Revisiones" in js and "Sin cobro" in js
assert "patient_id" not in js.lower()
print("RECEPTION_HOME_TV_REMASTER_4886_OK")
