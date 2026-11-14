"""Historia 1.4.97: UI-only consultation toolbar regression.

No patient data, Neon connections, HTTP calls, PDF changes, or live equipment.
"""
from __future__ import annotations
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
app=(root/"historia-clinica/app/app.py").read_text(encoding="utf-8")
css=(root/"historia-clinica/app/static/style.css").read_text(encoding="utf-8")
material=(root/"historia-clinica/app/material_pacientes.py").read_text(encoding="utf-8")
consent=(root/"historia-clinica/app/consentimiento_informado.py").read_text(encoding="utf-8")
version=json.loads((root/"historia-clinica/app/historia-version.json").read_text(encoding="utf-8"))
manifest=json.loads((root/"historia-clinica/app/update_manifest.json").read_text(encoding="utf-8"))
assert manifest["version"]==manifest["app_version"]==manifest["runtime_version"]==version["version"]
assert (1, 4, 97) <= tuple(map(int, version["version"].split("."))) < (2, 0, 0)
assert manifest["notes"]["database_schema_changes"] is False
assert manifest["notes"]["clinical_data_changes"] is False
assert manifest["notes"]["cloud_sync_data_logic_changes"] is False
start=css.index("/* Historia 1.4.97: barra de herramientas")
added=css[start:]
assert ".cp-remaster-app .clinical-editor .consult-tools" in added
assert ".cp-remaster-app .clinical-editor .consult-tools > button" in added
assert "display:flex!important" in added and "flex-wrap:wrap!important" in added
assert 'stroke%3D%22%2314558c%22' in added, "Icon stroke must match patient header SVG"
# Every button already inserted by the real render pipeline keeps its original
# unique ID and behavior. This version adds only decorative ::before icons.
sources={
    "toggle-macros":app,
    "open-prescription":app,
    "open-certificate":app,
    "open-consent":consent,
    "open-material":material,
    "open-reports":app,
}
for button_id, origin in sources.items():
    assert "id='"+button_id+"'" in origin, button_id
    assert ".consult-tools #"+button_id+"::before" in added, button_id
assert "Frases rápidas" in app
assert "Receta médica" in app
assert "Certificado médico" in app
assert "Consentimiento informado" in consent
assert ">Material</button>" in material
assert "Informes médicos" in app
# Consent and Material still insert beside the original certificate marker.
anchor="<button id='open-certificate' class='secondary document-action' type='button'>Certificado médico</button>"
assert anchor in app and anchor in material and anchor in consent
assert "id='open-prescription'" in app
assert "id='open-reports'" in app
assert "async function openClinicalDocument" in app
assert "save(true)" in app
assert "id='clinical-note'" in app
assert "id='sign-note'" in app
assert 'id="cp-quick-sex"' in app or 'id=\"cp-quick-sex\"' in app
print("HISTORIA_CONSULT_TOOLBAR_1497_SIX_SVG_BUTTONS_NO_LOGIC_CHANGE_OK")
