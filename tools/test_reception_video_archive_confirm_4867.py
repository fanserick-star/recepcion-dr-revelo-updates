"""Clinical videocystoscopy local archiving confirmation UX regression.

Only the native confirmation of saving MP4 in Reception is replaced.
The two required explicit WhatsApp delivery confirmations stay unchanged.
"""
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
js=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
css=(root/"recepcion/app/static/style.css").read_text(encoding="utf-8")
html=(root/"recepcion/app/static/index.html").read_text(encoding="utf-8")
version=(root/"recepcion/app/recepcion-version.json").read_text(encoding="utf-8")
assert '"4.8.84"' in version
assert "clinical_delivery.js?v=4.8.84" in html
assert "function confirmVideoArchive(chosen)" in js
assert "if(!await confirmVideoArchive(selected))return;" in js
assert "if(state.sending||state.saving_video||state.benchmarking||state.pid!==pid)return;" in js
assert "accept.disabled=true" in js
assert "accept.disabled=!check.checked" in js
assert "Boolean(approved&&check.checked&&currentPatientId===state.pid)" in js
assert "shade.setAttribute('role','presentation')" in js
assert "dialog.setAttribute('role','dialog')" in js
assert "dialog.setAttribute('aria-modal','true')" in js
assert "dialog.setAttribute('aria-labelledby','rpVideoArchiveTitle')" in js
assert "dialog.setAttribute('aria-describedby','rpVideoArchiveDesc')" in js
assert "check.type='checkbox'" in js
assert "finish(false)" in js and "finish(true)" in js
assert "document.removeEventListener('keydown',onKey,true)" in js
assert "opener.focus()" in js
assert "appendDetail('PACIENTE',state.name" in js
assert "appendDetail(chosen.length===1?'ARCHIVO ORIGINAL'" in js
assert "appendDetail('TAMAÑO TOTAL'" in js
assert "No se enviará" in js or "No se enviará por WhatsApp" in js
assert "Guardar video en Recepción" in js
assert "fetch(path" in js or "api(url,{method:'POST'" in js
archive=js.split("async function saveVideo(file){",1)[1].split("async function sendVideo(file){",1)[0]
assert "window.confirm(" not in archive
assert "window.alert(" not in archive
# Prior identity + consent confirmations remain for actual WhatsApp delivery.
wa=js.split("function confirmDelivery(label){",1)[1].split("async function sendDoc(",1)[0]
assert wa.count("window.confirm(")==2
for cls in [".rp-video-confirm-shade", ".rp-video-confirm-dialog",
            ".rp-video-confirm-head",".rp-video-confirm-details",
            ".rp-video-confirm-checkbox",".rp-video-confirm-accept:disabled"]:
    assert cls in css,cls
assert "@media(max-width:600px)" in css
assert "rp-video-confirm-shade" not in html  # rendered only when needed
assert "patient_links" not in archive
print("RECEPTION_4867_VIDEO_ARCHIVE_IN_APP_CONFIRM_UX_AND_PATIENT_GUARDS_OK")
