"""Historia 1.4.41: patient video badge and large viewer, synthetic/static regression.

Never reads or transfers a patient video, LAN traffic, clinical database or Neon.
"""
from pathlib import Path
import ast
import json

root=Path(__file__).resolve().parents[1]
app=root/"historia-clinica/app"
js=(app/"static/clinical_video_library.js").read_text(encoding="utf-8")
css=(app/"static/style.css").read_text(encoding="utf-8")
panel=(app/"patient_document_panel.py").read_text(encoding="utf-8")
backend=(app/"clinical_video_library.py").read_text(encoding="utf-8")
version=json.loads((app/"historia-version.json").read_text(encoding="utf-8"))["version"]
manifest=json.loads((app/"update_manifest.json").read_text(encoding="utf-8"))
assert version==manifest["version"]==manifest["app_version"]==manifest["runtime_version"]=="1.4.41"
assert manifest["mandatory"] and not manifest["notes"]["database_schema_changes"]
assert "static/clinical_video_library.js" in manifest["copy"]
assert "clinical_video_library.js?v=1.4.41" in panel
ast.parse((app/"app.py").read_text(encoding="utf-8"))
ast.parse(panel)
ast.parse(backend)

# Counter: no stale count or false '0' when Reception is disconnected.
assert "open.append(counter)" in js
assert "setCount(videos.length)" in js
assert "setCount(null,true)" in js
assert "open.dataset.videoState=state" in js
assert "open.dataset.videoState='loading'" in js
assert "load();" in js  # read once on patient chart, not background polling
assert "setInterval(" not in js
for state in ("ready","empty","unavailable","loading"):
    assert '[data-video-state="'+state+'"]' in css
assert "cp-video-trigger-count" in css

# Single theater: each row presents a large direct action, not a tiny native player.
assert "const theater=document.createElement('section')" in js
assert "showTheater(player,title.textContent,launch)" in js
assert "row.append(title,meta,launch,buttons)" in js
assert "row.append(title,meta,player,buttons)" not in js
assert "player.playsInline=true" in js and "player.controls=true" in js
assert "player.preload='none'" in js
assert "object-fit:contain" in css
assert "cp-video-theater-play" in css and "width:88px" in css
assert "dialog.addEventListener('cancel'" in js
assert "dialog.addEventListener('close',hideTheater)" in js
assert "stage.requestFullscreen" in js

# The established verified streaming and cache paths must never change.
assert "source.src=url+'/play/'+encodeURIComponent(item.id)" in js
assert "url+'/cached-play/'" in js and "url+'/prepare/'" in js
assert "clinical_video_cache.install(app, root, _url, _fetch, _local_only, _existing_patient)" in backend
assert "_existing_patient(patient_id)" in backend
assert "ProxyHandler({})" in backend
assert "CLINICAL_DELIVERY_LAN_SECRET" in backend
print("HISTORIA_1441_VIDEO_COUNT_LARGE_VIEWER_LAN_PRIVACY_OK")
