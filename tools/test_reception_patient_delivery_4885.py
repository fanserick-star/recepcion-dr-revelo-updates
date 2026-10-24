"""Offline privacy, file naming and patient delivery safeguards. Never uses real patients."""
import ast
from datetime import datetime, timedelta, timezone
import re
import secrets
import threading
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(ROOT/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
css=(ROOT/"recepcion/app/static/style.css").read_text(encoding="utf-8")
wizard=(ROOT/"recepcion/app/clinical_delivery_setup.pyw").read_text(encoding="utf-8")
ast.parse(source)
ast.parse(wizard)
func={n.name:n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
assert {"_clinical_download_name","_send_archived_video_to_patient","_upload_r2"}<=func.keys()
assert '"/api/clinical-delivery/patients/{pid}/archived-video/{video_id}/send-to-patient"' in source
route=source.split("async def delivery_send_archived_patient_video(",1)[1].split("# Self-test never touches patients",1)[0]
for fragment in ('_setup()["ready_video"]','_guard(patient,DeliverDocument',
                 '_linked_patient(pid)','_row_by_id(video_id,clinical_id)',
                 '_local_file(row)','metadata["moov_found"]','_PATIENT_VIDEO_RECENT',
                 'background_tasks.add_task(_send_archived_video_to_patient'):
    assert fragment in route,fragment
assert route.index('_guard(')<route.index('_linked_patient(')<route.index('_row_by_id(')
assert "CLINICAL_DELIVERY_LIVE_ENABLED" in source
assert "WHATSAPP_CLINICAL_TEMPLATES_APPROVED" in source
assert '"CLINICAL_DELIVERY_LIVE_ENABLED":"1" if active else "0"' in wizard
assert "if not approved:" in wizard and "messagebox.askyesno" in wizard
assert "sendArchivedVideoPatient(v)" in ui
assert "sendArchivedVideoTest(v,testPhone)" in ui
assert "addSelfTest(tools,data)" in ui
assert "rp-clinical-maintenance" in ui and "rp-clinical-maintenance" in css
assert 'data-profile-tab="documentos"' in (ROOT/"recepcion/app/static/app.js").read_text()
assert 'Archivo clínico</button>' in (ROOT/"recepcion/app/static/app.js").read_text()
assert "Archivo clínico" in ui.upper().title() or "ARCHIVO CLÍNICO" in ui

ns={"unicodedata":unicodedata,"re":re,"datetime":datetime,
    "TZ":timezone(timedelta(hours=-5))}
exec(compile(ast.Module(body=[func["_clinical_download_name"]],type_ignores=[]),
             "safe_name", "exec"),ns)
patient=SimpleNamespace(nombre="Gómez Ñáñez / Persona de Prueba")
pdf=ns["_clinical_download_name"](patient,"receta","pdf")
video=ns["_clinical_download_name"](patient,"video","mp4")
assert re.fullmatch(r"RECETA_GOMEZ_NANEZ_PERSONA_DE_PRUEBA_\\d{4}-\\d{2}-\\d{2}\\.pdf",pdf),pdf
assert video.startswith("VIDEOCISTOSCOPIA_GOMEZ_NANEZ_PERSONA_DE_PRUEBA_")
assert "/" not in video and "\\n" not in video

jobs={"mock":{"pid":1,"size":1111,"stage":"preparando","r2_bytes":0}}
progress=[]
sent=[]
uploads=[]
checks=[]
audits=[]
deletes=[]
class Clock: pass
worker={
    "_PROGRESS_LOCK":threading.Lock(),"_PROGRESS_JOBS":jobs,
    "datetime":datetime,"timedelta":timedelta,"TZ":timezone(timedelta(hours=-5)),
    "secrets":secrets,"time":time,"Path":Path,
    "_progress_set":lambda job_id,**values:(jobs[job_id].update(values),progress.append(values)),
    "_upload_progress_hook":lambda job_id:lambda n,total:None,
    "_upload_r2":lambda path,key,media,callback,download_name=None:uploads.append((key,media,download_name)),
    "_verify_benchmark_r2":lambda key,size,**kw:checks.append((key,kw)) or True,
    "_r2_url":lambda method,key,expires:"https://private-invalid.example/opaque",
    "_short_r2_link":lambda url,expiry:"https://worker-invalid.example/d/opaque",
    "_send_template":lambda *a,**k:sent.append((a,k)) or "synthetic-meta-id",
    "_delete_benchmark_r2":lambda key:deletes.append(key),
    "_audit":lambda *a:audits.append(a),
}
exec(compile(ast.Module(body=[func["_send_archived_video_to_patient"]],type_ignores=[]),
             "patient_worker", "exec"),worker)
fixture=ROOT/"recepcion/app/clinical_selftest_mp4.b64"
worker["_send_archived_video_to_patient"](
    "mock",fixture,1,"a"*32,"593999999999","PACIENTE FICTICIO",video,"staff")
assert jobs["mock"]["stage"]=="complete" and jobs["mock"]["whatsapp_accepted"]
assert checks and checks[0][1]["expected_name"]==video
assert uploads[0][2]==video and uploads[0][1]=="video/mp4"
assert len(sent)==1 and sent[0][0][1]=="PACIENTE FICTICIO" and sent[0][0][2]=="video"
assert sent[0][1].get("test_mode") is not True
assert audits[0][0]==1 and not deletes

# No message goes to Meta if private storage verification fails.
jobs["fail"]={"pid":1,"size":1111,"stage":"preparando","r2_bytes":0}
worker["_verify_benchmark_r2"]=lambda *a,**k:(_ for _ in ()).throw(RuntimeError("synthetic HEAD failure"))
worker["_send_archived_video_to_patient"](
    "fail",fixture,1,"b"*32,"593999999999","PACIENTE FICTICIO",video,"staff")
assert jobs["fail"]["stage"]=="error" and jobs["fail"]["r2_deleted"]
assert len(sent)==1 and len(deletes)==1
print("CLINICAL_PATIENT_VERIFIED_MP4_NAMED_FILES_OPT_IN_NO_META_OFFLINE_OK")
