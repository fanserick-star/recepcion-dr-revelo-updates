"""Historia 1.4.35: restore working pre-1.4.33 video stream transport.
Tests only synthetic source code; never reads patient files or Neon.
"""
from pathlib import Path
import ast
root=Path(__file__).resolve().parents[1]
py=(root/"historia-clinica/app/clinical_video_library.py").read_text(encoding="utf-8")
js=(root/"historia-clinica/app/static/clinical_video_library.js").read_text(encoding="utf-8")
panel=(root/"historia-clinica/app/patient_document_panel.py").read_text(encoding="utf-8")
manifest=(root/"historia-clinica/app/update_manifest.json").read_text(encoding="utf-8")
ast.parse(py)
assert "_buffered_video_body" not in py, "Faulty read-ahead remains"
assert "_VIDEO_PREFETCH_CHUNKS" not in py
assert "queue.Queue" not in py
assert "threading.Thread" not in py
assert "while True:" in py
assert "upstream.read(256 * 1024)" in py
assert "StreamingResponse(stream(), status_code=upstream.status" in py
assert '"Content-Range", "Content-Length"' in py
assert 'headers={"Range": incoming_range}' in py
assert 'upstream.close()' in py
assert "player.preload='none'" in js
assert "player.preload='auto'" not in js
assert "markWaiting" not in js
assert "Cargando por LAN desde Recepción" not in js
assert "source.src=url+'/play/'+encodeURIComponent(item.id)" in js
assert "clinical_video_library.js?v=1.4.35" in panel
assert '"version": "1.4.35"' in manifest
assert "documentos_clinicos.py" in manifest and "informes_clinicos.py" in manifest
print("HISTORIA_VIDEO_ROLLBACK_1435_PRESERVES_RANGE_PATIENT_GUARDS_AND_DOCS_OK")
