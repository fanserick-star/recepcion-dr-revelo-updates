"""Regression: canonical Reception 4.8.141 must show the clinical Neon picker.

This test only inspects code and static HTML/JS. It makes no network calls,
database changes, cloud writes, clinical reads, or patient associations.
"""
from pathlib import Path
import ast

base=Path(__file__).resolve().parents[1]
f=(base/"recepcion/app/features_runtime.py").read_text(encoding="utf-8")
ui=(base/"recepcion/app/static/index.html").read_text(encoding="utf-8")
js=(base/"recepcion/app/static/configuration.js").read_text(encoding="utf-8")
app=(base/"recepcion/app/app.py").read_text(encoding="utf-8")
manifest=(base/"recepcion/app/update_manifest.json").read_text(encoding="utf-8")
assert ast.parse(f)
assert ast.parse(app)
assert 'id="historiaNeonSelectorPanel"' in ui
assert 'data-config-section="sistema"' in ui
assert 'name="historiaNeonTarget" value="official"' in ui
assert 'name="historiaNeonTarget" value="emergency"' in ui
assert 'window.loadHistoriaNeonSelector()' in js
assert 'ensureHistoriaNeonSelectorPanel()' in js
assert "tab.insertBefore(panel,tab.firstChild)" in js
assert "if(!tab||q('#historiaNeonSelectorPanel'))return;" in js
assert "document.addEventListener('change',event=>" in js
assert "no-store, no-cache, must-revalidate, max-age=0" in f
assert 'X-Reception-UI-Version' in f
assert 'core_runtime.HTMLResponse(' in f
assert "'/static/configuration.js" in f
assert 'reception_history_neon_selector.py' in manifest
assert "_history_neon_selector.apply_pending_at_startup()" in app
print("RECEPTION_48141_CLINICAL_NEON_SELECTOR_VISIBLE_AND_FRESH_OK")
