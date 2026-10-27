"""Recepción 4.8.100 — expediente administrativo y confirmación segura de revisión."""
from pathlib import Path
import json

APP=Path(__file__).resolve().parents[1]/"recepcion/app"
js=(APP/"static/app.js").read_text(encoding="utf-8")
html=(APP/"static/index.html").read_text(encoding="utf-8")
css=(APP/"static/patient_dossier_review_48100.css").read_text(encoding="utf-8")
history=(APP/"reception_history_identity_consolidated.py").read_text(encoding="utf-8")
manifest=json.loads((APP/"update_manifest.json").read_text(encoding="utf-8"))
version=json.loads((APP/"recepcion-version.json").read_text(encoding="utf-8"))["version"]
assert version==manifest["version"]==manifest["app_version"]==manifest["runtime_version"]
assert tuple(map(int,version.split("."))) >= (4,8,100)
assert "static/patient_dossier_review_48100.css" in manifest["copy"]
assert "static/patient_dossier_review_48100.css" in manifest["required_dependencies"]
assert '/static/patient_dossier_review_48100.css?v=' + version in html
assert '/static/app.js?v=' + version in html
assert '#modal .v4100-dossier' in css
assert 'grid-template-columns:218px minmax(0,1fr)' in css
assert '.v4413-profile-tabs' in css and 'flex-direction:column!important' in css
assert '.v4413-profile-kpis>div:before{display:none!important' in css
assert 'background:transparent!important;border:0!important' in css
assert 'SIN COBRO' in js and '.r4100-review-dialog' in css

start=js.index("async function openPatient(id,source='general')")
end=js.index("async function editPatient(",start)
patient=js[start:end]
assert 'v4100-dossier' in patient
assert 'Expediente de recepción' in patient
assert 'Datos personales' in patient
for tab in ("resumen","atenciones","agenda","facturacion","documentos"):
    assert f'data-profile-tab="{tab}"' in patient
    assert f'data-profile-panel="{tab}"' in patient
assert 'id="v4413ProfileTabs"' in patient
assert 'id="v4413ProfilePanels"' in patient
assert 'id="rpClinicalDocs"' in patient
assert 'window.loadClinicalDelivery' in patient
assert 'fromAttentionSearch' in patient
assert 'continueAttention' in patient
assert "canDelete=source==='patients'" in patient
assert 'openAgendaPatient(' in patient
assert 'attentionFor(' in patient
assert 'editPatient(' in patient
assert 'deletePatient(' in patient
assert 'v499-profile-note-panel' in patient
assert 'v499-note-edit' in patient and 'Guardar nota' not in patient
assert 'avatar' not in patient.lower() and 'initials' not in patient.lower()

# Historia linkage insertion intentionally stays a DIRECT child of the root.
assert "tabs.insertAdjacentElement('beforebegin',card)" in history
assert "host.querySelector(':scope > .v4613-history-card')" in history
assert "#modal .v4100-dossier>.v4613-history-card" in css
assert "Cambio" not in js[start:end] or "Cambiar vínculo" in history

# Transaction is strictly guarded: no POST unless user confirms.
review=js[js.index('async function saveExamReviewTurn(id){'):js.index('async function saveAttention(id)')]
assert "if(attentionSaveInFlight)return" in review
assert "if(selectedServices.size)" in review
assert "if(fecha!==toISO(new Date()))" in review
assert "status?.linked" in review and "['true','1'].includes(flag)" in review
assert "if(!await examReviewDialog({" in review
assert "confirm(" not in review and "alert(" not in review
assert review.index("if(!await examReviewDialog({") < review.index("api('/api/visits/exam-review',{method:'POST'")
assert "sendExamReviewTicketDirect(reviewId)" in review
assert "await api('/api/agenda/confirmafy-staged/'" in review
assert "attentionSaveInFlight=false" in review
assert "new Promise(resolve=>" in js
assert "overlay.remove()" in js
assert "panel.setAttribute('aria-modal','true')" in js
assert "prior.focus()" in js
assert "cancelled.onclick=()=>cleanup(false)" in js
assert "accept.onclick=()=>cleanup(true)" in js
assert "event.key==='Escape'" in js
assert "value.textContent=clinicalName" in js
assert "value.textContent=patient" in js
assert "overlay.addEventListener('click'" in js
assert "z-index:2147483000!important" in css
assert manifest["notes"].get("database_schema_changes") is False
print("RECEPTION_DOSSIER_REVIEW_DIALOG_48100_OK")
