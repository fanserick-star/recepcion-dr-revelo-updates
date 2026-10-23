"""Static clinical document delivery contract; never accesses patients, R2 or Meta."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]
r=(ROOT/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
h=(ROOT/"historia-clinica/app/lan_bridge.py").read_text(encoding="utf-8")
ui=(ROOT/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
profile=(ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
html=(ROOT/"recepcion/app/static/index.html").read_text(encoding="utf-8")
main=(ROOT/"recepcion/app/app.py").read_text(encoding="utf-8")
ast.parse(r);ast.parse(h)

for marker in [
  "def _linked_patient(pid):", "l.verified=1", "l.deleted_at IS NULL",
  "def _signed_pdf(pid, kind, doc_id):", "if not any(d[\"id\"] == doc_id",
  "X-Historia-LAN-Token", "application/pdf", "def _guard(patient, data):",
  "if not data.consent_confirmed or not data.identity_confirmed:",
  "WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE", "WHATSAPP_CLINICAL_VIDEO_TEMPLATE",
  "CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED", '"X-Amz-Expires"',
  "604800", "LIMIT_VIDEO = 550 * 1024 * 1024", 'with open(tmp,"rb") as video_check:',
  "_send_template(phone,name,kind,expiry,url)",
]:
  assert marker in r,marker
assert "ZoneInfo" not in r
assert "Path(tmp).read_bytes()" not in r
assert "import clinical_delivery as _clinical_delivery" in main
assert 'data-profile-tab="documentos"' in profile
assert 'data-profile-panel="documentos"' in profile
assert 'window.loadClinicalDelivery' in profile
assert 'clinical_delivery.js?v=4.8.63' in html
assert 'consent_confirmed:true' in ui and 'identity_confirmed:true' in ui
assert 'send-document' in ui and 'send-video' in ui
assert 'document.getElementById("rx-save")' not in ui

for marker in [
    "def signed_document_for_reception(self, reception_id: str, kind: str, doc_id: str)",
    "SELECT clinical_patient_id FROM patient_links",
    "verified=1 LIMIT 1",
    'WHERE document_type=? AND document_id=?',
    'hmac.compare_digest(digest',
    'source.is_relative_to(archive)',
    'if path == "/delivery/signed-pdf"',
    'service._valid_token(self.remote_ip, token)',
    'self.send_header("Cache-Control", "no-store, private")',
    'X-Revelo-Delivery-Proof',
    '_valid_delivery_proof(',
]:
    assert marker in h,marker
section=h.split("def signed_document_for_reception",1)[1].split("def _handler_class",1)[0]
assert "_sign_pdf" not in section and "UPDATE " not in section and "INSERT " not in section
print("RECEPTION_CLINICAL_DELIVERY_READONLY_PRIVACY_CONTRACT_4858_OK")
