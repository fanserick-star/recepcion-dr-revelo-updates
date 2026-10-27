"""Reception 4.8.99 — Profile remaster is visual and preserves existing patient actions."""
from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]/"recepcion/app"
html=(root/"static/index.html").read_text(encoding="utf-8")
js=(root/"static/app.js").read_text(encoding="utf-8")
css=(root/"static/patient_profile_remaster_4899.css").read_text(encoding="utf-8")
history=(root/"reception_history_identity_consolidated.py").read_text(encoding="utf-8")
version=json.loads((root/"recepcion-version.json").read_text(encoding="utf-8"))["version"]
manifest=json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
assert version==manifest["version"]==manifest["app_version"]==manifest["runtime_version"]
assert tuple(map(int,version.split("."))) >= (4,8,99)
assert "static/patient_profile_remaster_4899.css" in manifest["copy"]
assert "static/patient_profile_remaster_4899.css" in manifest["required_dependencies"]
assert '/static/patient_profile_remaster_4899.css?v=4.8.99' in html
assert '/static/app.js?v=4.8.100' in html  # El JS clínico se conserva; 4.8.101 cambia solo CSS
start=js.index("async function openPatient(id,source='general')")
end=js.index("  if(window.loadClinicalDelivery)",start)
p=js[start:end]
assert "v499-patient-redesign" in p
assert "v499-profile-eyebrow" in p
assert "v499-profile-dashboard" in p
assert "v499-personal-panel" in p
assert "v499-profile-note-panel" in p
assert "v499-profile-flags" in p
assert "v499-profile-note-panel" in css
assert "v499-profile-flag" in css
assert "v499-profile-eyebrow" in css
assert "v499-patient-redesign .v4413-profile-tabs" in css
assert "v499-patient-redesign .v4413-profile-kpis" in css
assert "v499-patient-redesign .v4413-data-grid" in css
assert "grid-template-columns:minmax(0,1.78fr) minmax(270px,.92fr)" in css
assert "@media(max-width:710px)" in css
assert "avatar" not in p.lower() and "initials" not in p.lower()
assert "AS" not in css
assert "patientProfileWarningHtml(p)" in p
assert "missing.length?patientProfileWarningHtml(p):''" in p
assert "openAgendaPatient(" in p
assert "attentionFor(" in p
assert "editPatient(" in p
assert "deletePatient(" in p
assert "canDelete=source==='patients'" in p
assert "data-profile-tab=\"resumen\"" in p
for tab in ("atenciones","agenda","facturacion","documentos"):
    assert 'data-profile-tab="'+tab+'"' in p, tab
    assert 'data-profile-panel="'+tab+'"' in p, tab
assert "id=\"rpClinicalDocs\"" in p
assert "window.loadClinicalDelivery" in js[end:end+160]
assert "v4613-history-card" in history
assert "Cambiar vínculo" in history
# Notes editor is the existing demographic form; no new unsupported save endpoint.
assert 'v499-note-edit' in p
assert 'editPatient(' in p[p.index('v499-profile-note-panel'):]
assert "Guardar nota" not in p
assert "/api/patients/" in js
assert "setPatientProfileTab" in js
# No changes to the LAN backend or billing schemas are required for presentation.
assert manifest["notes"].get("database_schema_changes") is False
print("RECEPTION_PATIENT_PROFILE_REMASTER_4899_OK")
