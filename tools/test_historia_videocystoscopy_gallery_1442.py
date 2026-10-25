"""Historia 1.4.42 videocystoscopy gallery read-only UI regression.

No clinical video, live Reception, Neon, patient record or external network used.
"""
import ast
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/"historia-clinica/app"
js=(root/"static/clinical_video_library.js").read_text(encoding="utf-8")
css=(root/"static/style.css").read_text(encoding="utf-8")
panel=(root/"patient_document_panel.py").read_text(encoding="utf-8")
backend=(root/"clinical_video_library.py").read_text(encoding="utf-8")
version=json.loads((root/"historia-version.json").read_text(encoding="utf-8"))["version"]
manifest=json.loads((root/"update_manifest.json").read_text(encoding="utf-8"))
assert version==manifest["version"]==manifest["runtime_version"]==manifest["app_version"]in {"1.4.42","1.4.43","1.4.44","1.4.45"}
assert manifest["mandatory"] is True
assert manifest["notes"]["database_schema_changes"] is False
assert manifest["notes"]["patient_data_destructive_changes"] is False
assert "static/clinical_video_library.js" in manifest["copy"]
assert "clinical_video_library.js?v=1.4.42" in panel
ast.parse((root/"app.py").read_text(encoding="utf-8"))
ast.parse(backend)

# Buttons removed from UI but existing diagnostic + cache server remain unchanged.
for removed in ("Medir velocidad LAN", "Preparar video para reproducir sin cortes"):
    assert removed not in js
assert "url+'/prepare/'" not in js
assert "url+'/cached-play/'" not in js
assert "clinical_video_cache.install(app, root, _url, _fetch, _local_only, _existing_patient)" in backend

# Real patient-scoped listing and one player opened only after selecting a card.
assert "data-clinical-video-patient" in js
assert "fetch(url,{cache:'no-store'" in js
assert "source.src=url+'/play/'+encodeURIComponent(item.id)" in js
assert "function makeCard(item,index)" in js
assert "button.addEventListener('click',()=>selectVideo(item,button))" in js
assert "const player=document.createElement('video')" in js
assert "player.preload='none'" in js
assert "player.controls=true" in js and "player.playsInline=true" in js
assert "const previewById=new Map()" in js
assert "player.currentTime>0.15" in js
assert "canvas.toDataURL('image/jpeg',0.68)" in js
assert "setInterval(" not in js
assert "document.createElement('video')" in js and js.count("document.createElement('video')")==1
assert "dialog.addEventListener('close',stopPlayer)" in js
assert "stopPlayer()" in js
assert "setCount(null,true)" in js
assert "source.type='video/mp4'" in js

# Two-column responsive gallery and full-height player, no old per-row viewer.
for cls in (".cp-video-gallery-card",".cp-video-card-thumbnail",
            ".cp-video-gallery-viewer",".cp-video-gallery-player",
            ".cp-video-gallery-big-play"):
    assert cls in css
assert "grid-template-columns:minmax(320px,46%) minmax(0,1fr)" in css
assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css
assert "object-fit:contain" in css
assert "background-image:radial-gradient(" in css
print("HISTORIA_1442_VIDEOGALERIA_TARJETAS_REPRODUCTOR_LAN_SEGURA_OK")
