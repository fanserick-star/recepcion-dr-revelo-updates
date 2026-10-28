"""Regresión visual-contract: nombres largos en el expediente de Recepción.
No usa datos reales, no conecta Neon ni genera atención.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "recepcion" / "app"
css = (ROOT / "static" / "patient_dossier_review_48100.css").read_text(encoding="utf-8")
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

def rule(selector):
    m = re.search(re.escape(selector) + r"\s*\{([^{}]+)\}", css)
    assert m, selector
    return m.group(1)

shell=rule("#modal .modalbox.v4413-profile-shell>#modalBody")
assert "width:100%!important" in shell and "min-width:0!important" in shell
head=rule("#modal .v4100-dossier>.v4413-profile-head")
assert "grid-template-columns:minmax(0,1fr)!important" in head
assert "width:100%!important" in head
name=rule("#modal .v4100-dossier .v4413-profile-name>h2")
assert "word-break:normal!important" in name
assert "overflow-wrap:break-word!important" in name
assert "hyphens:none!important" in name
actions=rule("#modal .v4100-dossier .v4413-profile-actions")
assert "display:flex!important" in actions and "flex-wrap:wrap!important" in actions
buttons=rule("#modal .v4100-dossier .v4413-profile-actions>button")
assert "width:auto!important" in buttons and "max-width:100%!important" in buttons
tablet_start=css.index("@media(max-width:1060px)")
mobile=css[tablet_start:css.index("@media(max-width:770px)", tablet_start)]
assert "grid-template-columns:minmax(0,1fr)!important" in mobile

# La corrección no puede cambiar el contrato administrativo ni médico.
p=js[js.index("async function openPatient(id,source='general')"):js.index("async function editPatient(",js.index("async function openPatient(id,source='general')"))]
for key in ('v4100-dossier','v4413-profile-head','v4413-profile-name','v4413-profile-actions',
            'v4413ProfileTabs','v4413ProfilePanels','rpClinicalDocs','v4417-continue-attention','data-continue-attention',
            'openAgendaPatient(','attentionFor(','editPatient('):
    assert key in p, key
for section in ('resumen','atenciones','agenda','facturacion','documentos'):
    assert f'data-profile-panel="{section}"' in p
assert '/static/patient_dossier_review_48100.css' in html
print("RECEPTION_DOSSIER_LONG_NAME_LAYOUT_OK")
