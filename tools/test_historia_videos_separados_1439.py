"""Safety test: isolated videocystoscopy UI, same LAN routes, no patient data changes.

Synthetic markup only. This test never contacts Reception, Neon or reads MP4.
"""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app_root = ROOT / "historia-clinica" / "app"
panel_path = app_root / "patient_document_panel.py"
app_path = app_root / "app.py"
source = panel_path.read_text(encoding="utf-8")
app_source = app_path.read_text(encoding="utf-8")
javascript = (app_root / "static" / "clinical_video_library.js").read_text(encoding="utf-8")
css = (app_root / "static" / "style.css").read_text(encoding="utf-8")
backend = (app_root / "clinical_video_library.py").read_text(encoding="utf-8")
version = json.loads((app_root / "historia-version.json").read_text(encoding="utf-8"))["version"]
manifest = json.loads((app_root / "update_manifest.json").read_text(encoding="utf-8"))
assert version == manifest["version"] == manifest["app_version"] == manifest["runtime_version"] in {"1.4.39", "1.4.40", "1.4.41", "1.4.42", "1.4.43"}
ast.parse(app_source, filename="app.py")
ast.parse(source, filename="patient_document_panel.py")
spec = importlib.util.spec_from_file_location("isolated_documents_panel", panel_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

documents = module.render_patient_documents(None, "patient-synthetic", documents=[])
videos = module.render_patient_videos("patient-synthetic")
assert "cp-patient-documents" in documents
assert "cp-clinical-videos" not in documents
assert "clinical_video_library.js" not in documents
assert "cp-clinical-videos" in videos
assert "data-clinical-video-patient='patient-synthetic'" in videos
assert "clinical_video_library.js?v=1.4.42" in videos
assert "<script defer" in videos
assert "patient-videos-open" in app_source and "patient-docs-open" in app_source
assert "patient-videos-dialog" in app_source and "patient-docs-dialog" in app_source
assert "bindPatientDialog('docs');" in app_source
assert "bindPatientDialog('videos');" in app_source
assert "dialog.querySelectorAll('video').forEach(video=>video.pause());" in app_source
assert "const open=document.getElementById('patient-videos-open');" in javascript
assert "const open=document.getElementById('patient-docs-open');" not in javascript
assert "Medir velocidad LAN" not in javascript
assert "Preparar video para reproducir sin cortes" not in javascript
assert ".cp-history-archive-actions" in css
assert "cp-patient-videos-dialog" in app_source
assert "source.src=url+'/play/'" in javascript
assert "cp-video-gallery-card" in javascript
assert "cp-video-gallery-viewer" in javascript
assert "RECEPTION_VIDEO_LAN_HOST" in backend
assert "StreamingResponse(stream()" in backend
assert "_existing_patient(patient_id)" in backend
assert "CLINICAL_DELIVERY_LAN_SECRET" in backend
assert "cloud" not in videos.lower()
assert "neon" not in videos.lower()
print("HISTORIA_VIDEO_SEPARADO_1439_HTML_RUTAS_FICHA_SEGURIDAD_OK")
