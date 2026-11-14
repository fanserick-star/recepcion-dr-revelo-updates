"""Historia 1.4.98: private inline videocystoscopy gallery regression.

Synthetic/static assertions only. Never opens a clinical MP4, a real patient
database, Reception LAN, Neon, or an external network connection.
"""
from __future__ import annotations
import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
base=ROOT/"historia-clinica/app"
js=(base/"static/clinical_video_library.js").read_text(encoding="utf-8")
css=(base/"static/style.css").read_text(encoding="utf-8")
app=(base/"app.py").read_text(encoding="utf-8")
panel=(base/"patient_document_panel.py").read_text(encoding="utf-8")
backend=(base/"clinical_video_library.py").read_text(encoding="utf-8")
version=json.loads((base/"historia-version.json").read_text(encoding="utf-8"))
manifest=json.loads((base/"update_manifest.json").read_text(encoding="utf-8"))
assert version["version"]==manifest["version"]==manifest["app_version"]==manifest["runtime_version"]=="1.4.98"
assert manifest["notes"]["database_schema_changes"] is False
assert manifest["notes"]["clinical_data_changes"] is False
assert manifest["notes"]["cloud_sync_data_logic_changes"] is False

# The gallery is inserted IN the history, before consultations, never above
# patient identity or inside signed document editors.
assert "document.querySelector('.cp-history-window .cp-timeline')" in js
assert "historyTimeline.before(historyStrip)" in js
assert "function renderHistoryStrip(videos)" in js
assert "videos.slice(0,4).forEach" in js
assert "Videocistoscopías guardadas" in js
assert "Ver todas (" in js
assert "cp-history-video-cards" in js
assert ".cp-history-video-card" in css
assert ".cp-history-video-cover" in css
assert "grid-template-columns:repeat(4,minmax(0,1fr))" in css
assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css

# Only a positive patient-owned catalog response shows the strip.
strip=js.split("function renderHistoryStrip(videos){",1)[1].split("async function load(",1)[0]
assert "if(!historyTimeline||!videos.length)" in strip
assert "clearHistoryStrip();" in strip
assert "historyStrip.replaceChildren(head,cards)" in strip
assert "textContent=when||'Fecha no disponible'" in strip
assert "card.setAttribute('aria-haspopup','dialog')" in strip
assert "open.click();" in strip
assert "selectVideo(item,modalCard)" in strip
assert "Array.from(list.children).find" in strip
assert "document.createElement('video')" not in strip
assert "fetch(" not in strip
assert "new Image(" not in strip
assert "source.src" not in strip
assert "videos.slice(0,4)" in strip

# No new Neon queries, image transfers or duplicate LAN catalog fetch.
assert js.count("fetch(url,{cache:'no-store'")==1
assert "renderHistoryStrip(videos);" in js
assert "clearHistoryStrip();\n      loaded=false;" in js
assert "open.addEventListener('click',()=>load(false))" in js
assert "refresh?.addEventListener('click',()=>load(true))" in js
assert "load();" in js
assert "setInterval(" not in js
assert "document.createElement('video')" in js
assert js.count("document.createElement('video')")==1
assert "player.preload='none'" in js
assert "source.src=url+'/play/'+encodeURIComponent(item.id)" in js
assert "dialog.addEventListener('close',stopPlayer)" in js
assert "previewById=new Map()" in js
assert "previewById.set(videoId,image)" in js

# Do not change verified-patient lookup or LAN key matching.
assert "_existing_patient(patient_id)" in backend
assert "_local_only(request)" in backend
assert 'url = _url("catalog", patient_id' in backend
assert "CLINICAL_DELIVERY_LAN_SECRET" in backend
assert "ProxyHandler({})" in backend
assert "clinical_video_library.js?v=1.4.98" in panel
assert "data-clinical-video-patient=" in panel
assert 'id="patient-videos-dialog"' in app
assert 'id="patient-videos-open"' in app
ast.parse(app)
ast.parse(panel)
print("HISTORIA_HISTORY_VIDEO_STRIP_1498_PRIVATE_CATALOG_NO_MP4_PRELOAD_OK")
