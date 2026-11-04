"""Recepción 4.8.123: pago visible y protección clínica sin regresiones."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"
html = (APP / "static/index.html").read_text(encoding="utf-8")
css = (APP / "static/reception_attention_cleanup_48123.css").read_text(encoding="utf-8")
js = (APP / "static/app.js").read_text(encoding="utf-8")
payment = (APP / "reception_payment_terminal.py").read_text(encoding="utf-8")
lan = (APP / "historia_lan_transport.py").read_text(encoding="utf-8")
identity = (APP / "reception_history_identity_consolidated.py").read_text(encoding="utf-8")
manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))
version = json.loads((APP / "recepcion-version.json").read_text(encoding="utf-8"))["version"]

assert tuple(map(int, version.split("."))) >= (4, 8, 123)
assert all(manifest[k] == version for k in ("version", "app_version", "runtime_version"))
asset = "static/reception_attention_cleanup_48123.css"
assert asset in manifest["copy"] and asset in manifest["required_dependencies"]
assert "/static/reception_attention_cleanup_48123.css?v=" + version in html
assert html.index("reception_compact_workflow_48122.css") < html.index("reception_attention_cleanup_48123.css")
assert css.count("{") == css.count("}")
assert '"services payment"' in css and '"services summary"' in css
assert 'grid-area:payment!important' in css and 'grid-area:summary!important' in css
assert '#v4504Payment .v4504-pay-options' in css
assert 'grid-template-columns:repeat(2,minmax(0,1fr))!important' in css
assert '#v4504Payment .v4504-pay-option>b' in css
assert '#v4504Payment .v4504-pay-option>small' in css
assert '>.attention-date-card' in css and 'display:none!important' in css
# Fecha en backend: se mantiene para validar la regla "solo hoy".
assert 'id="aFecha"' in js and "$('#aFecha').value" in js
# Un vínculo verificado no ocupa un panel grande; warning/error conserva botón.
assert '.v4613-history-card.warn' in css and '.v4613-history-card.error' in css
assert ':not(.warn):not(.error)' in css
assert 'Historia vinculada' in css
assert "Vincular con Historia Clínica" in identity
# La UI comprueba vinculación antes de guardar; el trabajador LAN NO envía sin
# vínculo verificado, ni confía en IDs aportados por el navegador.
assert "clinical_patient?.verified" in js
assert "Primero vincula la ficha de Historia Clínica" in js
assert "AND l.verified=1" in lan and "AND l.deleted_at IS NULL" in lan
flush = lan[lan.index("def _flush_lan_outbox"):lan.index("def remap_pending_patient_id")]
assert flush.index("if not verified_id:") < flush.index("if send_lan(payload):")
assert '_cloud_link_id(patient_id)' in flush
assert "clinical_patient_id\": \"\"" not in css
# Eventos de pago y Bendo siguen siendo los del módulo original.
assert "v4504Payment" in payment and "v4504Summary" in payment
assert "optionButton(" in payment and "v4504-pay-option" in payment
assert "v4525Bendo" not in css
print("RECEPTION_ATTENTION_PAYMENT_LINK_48123_OK")
