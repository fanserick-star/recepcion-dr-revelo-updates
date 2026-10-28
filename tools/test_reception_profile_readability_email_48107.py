"""Visual/UX regression: enlarged patient dossier + optional email check.
No patient data, Neon or real actions. Keeps the clinical navigation contract intact.
"""
from pathlib import Path
import re

app = Path(__file__).resolve().parents[1] / "recepcion" / "app"
css = (app / "static/patient_dossier_review_48100.css").read_text(encoding="utf-8")
core = (app / "core_runtime.py").read_text(encoding="utf-8")
js = (app / "static/app.js").read_text(encoding="utf-8")

def rule(selector):
    match = re.search(re.escape(selector) + r"\s*\{([^{}]+)\}", css)
    assert match, selector
    return match.group(1)

shell = rule("#modal .modalbox.v4413-profile-shell")
assert "width:min(1720px,96vw)!important" in shell
assert "max-width:96vw!important" in shell
assert "max-height:95vh!important" in shell
layout = rule("#modal .v4100-dossier")
assert "grid-template-columns:238px minmax(0,1fr)!important" in layout
name = rule("#modal .v4100-dossier .v4413-profile-name>h2")
assert "clamp(25px,2.15vw,34px)!important" in name
assert "word-break:normal!important" in name
tabs = rule("#modal .v4100-dossier>.v4413-profile-tabs>button")
assert "font-size:14px!important" in tabs
assert "min-height:47px!important" in tabs
actions = rule("#modal .v4100-dossier .v4413-profile-actions>button")
assert "font-size:13px!important" in actions
assert "min-height:43px!important" in actions
assert "width:auto!important" in actions
grid = rule("#modal .v4100-dossier .v4413-data-grid>div>b")
assert "font-size:14px!important" in grid
assert "@media(max-width:770px)" in css
assert "display:flex!important;flex-direction:column!important" in css

# The older version checked mail on every keystroke and immediately painted
# "Correo no válido"; the new flow waits for blur, and blank is always valid.
start = core.index('V481_PATIENT_JS = r"""')
end = core.index('V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V481_PATIENT_CSS', start)
email = core[start:end]
assert "emailTouched=false" in email
assert "const showMailError=emailTouched&&!mailOk;" in email
assert "email?.addEventListener('input',()=>{emailTouched=false;updateSave()})" in email
assert "email?.addEventListener('blur',()=>{emailTouched=true;updateSave()})" in email
assert "if(!email||!String(email.value||'').trim())return true" in email
assert "showMailError?'block':'none'" in email
assert "wEmail?.classList.toggle('v481-field-invalid',!mailOk)" not in email
assert "email?.addEventListener('input',updateSave)" not in email

# Back-end and original form still validate before saving; optional remains optional.
assert "correo&&!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/.test(correo)" in js
assert "correo:correo||null" in js
for k in ("v4100-dossier","data-profile-panel=\"resumen\"",
          "data-profile-panel=\"documentos\"","data-continue-attention",
          "rpClinicalDocs"):
    assert k in js, k
print("RECEPTION_PROFILE_READABILITY_EMAIL_48107_OK")
