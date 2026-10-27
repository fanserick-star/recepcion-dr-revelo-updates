"""Recepción 4.8.101 — archivo clínico no se estira en la barra lateral vertical."""
from pathlib import Path
import json
import re
app=Path(__file__).resolve().parents[1]/"recepcion/app"
css=(app/"static/patient_dossier_review_48100.css").read_text(encoding="utf-8")
old=(app/"static/patient_profile_remaster_4899.css").read_text(encoding="utf-8")
html=(app/"static/index.html").read_text(encoding="utf-8")
js=(app/"static/app.js").read_text(encoding="utf-8")
m=json.loads((app/"update_manifest.json").read_text(encoding="utf-8"))
version=json.loads((app/"recepcion-version.json").read_text(encoding="utf-8"))["version"]
assert version == m["version"] == m["runtime_version"] == m["app_version"]
assert tuple(map(int,version.split("."))) >= (4,8,101)
assert '/static/patient_dossier_review_48100.css?v=' + version in html
assert "static/patient_dossier_review_48100.css" in m["copy"]
assert "static/patient_dossier_review_48100.css" in m["required_dependencies"]
# Regression: previous horizontal tab CSS applies flex:1 0 auto!important to
# Archivo clínico; CSS after it must target that specific variant more strongly.
assert '.v4413-profile-tabs [data-profile-tab="documentos"]' in old
assert "flex:1 0 auto!important" in old
selector="#modal .v499-patient-redesign.v4100-dossier>.v4413-profile-tabs>button[data-profile-tab=\"documentos\"]"
assert selector in css
match=re.search(re.escape(selector)+r"\s*\{([^{}]+)\}",css)
assert match, "Explicit high-specificity Archivo fix is missing"
rule=match.group(1)
for property in (
    "flex:0 0 43px!important",
    "flex-grow:0!important",
    "flex-shrink:0!important",
    "flex-basis:43px!important",
    "height:43px!important",
    "min-height:43px!important",
    "max-height:43px!important",
    "width:100%!important",
    "align-self:stretch!important",
):
    assert property in rule, property
assert css.index(selector)>css.index("#modal .v4100-dossier>.v4413-profile-tabs>button{")
assert "@media(max-width:770px){" in css
mobile=css[css.index("@media(max-width:770px){",css.index(selector)):]
assert selector in mobile and "width:auto!important" in mobile
assert 'data-profile-tab="documentos"' in js
assert 'data-profile-panel="documentos"' in js
assert "id=\"rpClinicalDocs\"" in js
assert "window.loadClinicalDelivery" in js
print("RECEPTION_CLINICAL_ARCHIVE_NAV_HEIGHT_48101_OK")
