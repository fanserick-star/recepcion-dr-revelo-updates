"""Recepción 4.8.122: prueba de integración de vistas compactas sin cambiar la lógica."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
app = root / "recepcion" / "app"
html = (app / "static" / "index.html").read_text(encoding="utf-8")
js = (app / "static" / "app.js").read_text(encoding="utf-8")
css = (app / "static" / "reception_compact_workflow_48122.css").read_text(encoding="utf-8")
manifest = json.loads((app / "update_manifest.json").read_text(encoding="utf-8"))
version = json.loads((app / "recepcion-version.json").read_text(encoding="utf-8"))["version"]

assert tuple(map(int, version.split("."))) >= (4, 8, 122), "Debe conservar la mejora 4.8.122 o posterior"
assert all(manifest[key] == version for key in ("version", "app_version", "runtime_version"))
asset = "static/reception_compact_workflow_48122.css"
assert asset in manifest["copy"] and asset in manifest["required_dependencies"]
assert '/static/reception_compact_workflow_48122.css?v=' + version in html
assert html.index("patient_dossier_review_48100.css") < html.index("reception_compact_workflow_48122.css")
assert "v4122-attention-compact" in js
assert "box.classList.toggle('v4122-attention-compact'" in js
assert "'v4122-attention-compact'" in js[js.index("function closeModal()"):js.index("function closeModal()")+400]
assert "grid-template-columns:188px minmax(0,1fr)" in css
assert "grid-template-areas:" in css and '"services review"' in css
assert "grid-area:actions" in css
assert "min-height:44px" in css and "max-height:125px" in css
assert "data-profile-tab=\"documentos\"" in css
# Deben permanecer los mismos controles de recepción y no perderse funciones.
for control in ("Nueva atención", "Agendar cita", "Editar datos", "data-profile-tab=\"documentos\"",
                "saveAttention(${id})", "saveExamReviewTurn(${id})",
                "toggleService('CONSULTA')", "procedureValuesBox", "aFecha"):
    assert control in js, control
assert css.count("{") == css.count("}"), "CSS sin equilibrar"
print("RECEPTION_COMPACT_WORKFLOW_48122_OK")
