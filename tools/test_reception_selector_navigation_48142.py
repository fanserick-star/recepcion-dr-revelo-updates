"""Regression for Reception 4.8.142: clinical Neon selector must survive navigation.

The former show() used 'main section' and hid #historiaNeonSelectorPanel
when the operator opened Configuration. This is intentionally static and
read-only: no clinical databases or patient records are accessed.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html = (root / "recepcion/app/static/index.html").read_text(encoding="utf-8")
app = (root / "recepcion/app/static/app.js").read_text(encoding="utf-8")
config = (root / "recepcion/app/static/configuration.js").read_text(encoding="utf-8")
manifest = (root / "recepcion/app/update_manifest.json").read_text(encoding="utf-8")

assert "document.querySelectorAll('main > section').forEach(x=>x.classList.add('hidden'));" in app
assert "document.querySelectorAll('main section').forEach(x=>x.classList.add('hidden'));" not in app
assert '<section id="config"' in html
assert re.search(r'<div\b[^>]*\bid="historiaNeonSelectorPanel"', html)
assert not re.search(r'<section\b[^>]*\bid="historiaNeonSelectorPanel"', html)
assert "const panel=document.createElement('div');\n  panel.id='historiaNeonSelectorPanel';" in config
assert 'ensureHistoriaNeonSelectorPanel()' in config
assert "window.loadHistoriaNeonSelector()" in config
assert 'name="historiaNeonTarget" value="official"' in html
assert 'name="historiaNeonTarget" value="emergency"' in html
assert tuple(int(x) for x in __import__("json").loads(manifest)["version"].split(".")[:3]) >= (4, 8, 142)
print("RECEPTION_48142_SELECTOR_VISIBLE_AFTER_NAVIGATION_OK")
