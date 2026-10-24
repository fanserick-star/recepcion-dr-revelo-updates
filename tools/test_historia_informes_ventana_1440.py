"""Historia 1.4.40: ventana de Informes independiente, sin cambiar ficha ni documentos."""
import ast
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
app = (root / "app.py").read_text(encoding="utf-8")
documents = (root / "documentos_clinicos.py").read_text(encoding="utf-8")
reports = (root / "informes_clinicos.py").read_text(encoding="utf-8")
version = json.loads((root / "historia-version.json").read_text(encoding="utf-8"))["version"]
manifest = json.loads((root / "update_manifest.json").read_text(encoding="utf-8"))
assert version == manifest["version"] == manifest["app_version"] in {"1.4.40", "1.4.41"}
ast.parse(app, filename="app.py")
ast.parse(documents, filename="documentos_clinicos.py")
ast.parse(reports, filename="informes_clinicos.py")
# Desde ficha, todos los documentos abren una ventana independiente de Historia.
assert """f"<a class='secondary btn-link cp-prescription' target='_blank' href='/recetas/nueva?patient_id={e(patient_id)}'>Receta médica</a>" """ .strip() in app
assert """f"<a class='secondary btn-link cp-certificate' target='_blank' href='/certificados/nuevo?patient_id={e(patient_id)}'>Certificado médico</a>" """ .strip() in app
assert """f"<a class='secondary btn-link cp-reports' target='_blank' rel='noopener' href='/informes?patient_id={e(patient_id)}'>Informes médicos</a>" """ .strip() in app
assert "f\"<a class='secondary btn-link cp-reports' href='/informes?" not in app
# La lista ofrece ambos informes y conserva el contexto del paciente/consulta.
assert '"<a class=\'doc-light\' href=\'/informes/nuevo?patient_id="' in reports
assert '+"&tipo=cistoscopia"+context' in reports
assert '+"&tipo=ecografia"+context' in reports
assert '@app.get("/informes/nuevo"' in reports
# Nunca alteramos la ventana clínica ni los atajos dentro de la consulta.
assert "window.open(route+'?'+qs.toString(),'_blank')" in app
assert "kind==='cert'?'/certificados/nuevo':'/informes'" in app
# No cambiamos protección del video ni el panel de documentos.
assert "patient-videos-open" in app
assert "patient-docs-open" in app
assert "CLINICAL_DELIVERY_LAN_SECRET" in (root / "clinical_video_library.py").read_text(encoding="utf-8")
# WebView2 launcher recibe URLs locales y crea un formulario propio.
launcher = (root.parents[0] / "launcher-v1" / "HistoriaLauncher" / "Program.cs").read_text(encoding="utf-8")
assert 'web.CoreWebView2.NewWindowRequested' in launcher
assert 'var child = new HistoriaForm(root, e.Uri, true);' in launcher
print("HISTORIA_1440_INFORMES_POPUP_INDEPENDIENTE_CERTIFICADO_RECETAS_VIDEOS_OK")
