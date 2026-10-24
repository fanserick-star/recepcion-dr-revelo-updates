"""No-network safety tests: only verified archived video to allowlisted staff test phone."""
import ast
import datetime
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import secrets
import re
from unittest.mock import Mock
root=Path(__file__).resolve().parents[1]
src=(root/"recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
ui=(root/"recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
worker=(root/"cloudflare/whatsapp_worker.js").read_text(encoding="utf-8")
tree=ast.parse(src)
func={f.name:f for f in tree.body if isinstance(f,ast.FunctionDef)}
assert {"_send_archived_video_to_test_phone","_progress_set"} <= set(func)
assert '@app.post("/api/clinical-delivery/patients/{pid}/archived-video/{video_id}/send-to-test-phone")' in src
handler=src.split("async def send_archived_video_test(",1)[1].split("# Self-test never touches patients",1)[0]
assert 'data.patient_authorized_staff_delivery' in handler
assert 'data.identity_confirmed' in handler
assert 'hmac.compare_digest(raw,allow)' in handler
assert '_linked_patient(pid)' in handler
assert '_row_by_id(video_id,clinical_id)' in handler
assert '_local_file(row)' in handler
assert 'background_tasks.add_task(_send_archived_video_to_test_phone' in handler
assert '"mode":"envio_prueba"' in handler
assert '"CLINICAL_DELIVERY_LIVE_ENABLED"' in src
assert 'label_override="VIDEO CLINICO AUTORIZADO",test_mode=True' in src
assert '"VIDEO CLINICO AUTORIZADO"' in worker
assert 'if (!claimed) return json({ok:false,error:"expired_or_used_clinical_permission"},403);' in worker
assert "Envio a todos los pacientes" not in ui
assert 'Enviar ESTE video a MI WhatsApp de pruebas' in ui
assert 'patient_authorized_staff_delivery:true' in ui
assert 'sendArchivedVideoTest(v,testPhone)' in ui
assert "state.ready_test" in ui
assert 'CLINICAL_DELIVERY_LIVE_ENABLED=1' not in ui
assert "No se enviará WhatsApp" in ui  # speed test remains no-send

# Call isolated worker function. All external effects mocked, no real file.
namespace={
    "_PROGRESS_LOCK":threading.Lock(),
    "_PROGRESS_JOBS":{
        "success":{"pid":1,"size":1024,"mode":"envio_prueba","r2_bytes":0,"stage":"preparando"},
        "earlyfail":{"pid":1,"size":1024,"mode":"envio_prueba","r2_bytes":0,"stage":"preparando"},
        "ambiguous":{"pid":1,"size":1024,"mode":"envio_prueba","r2_bytes":0,"stage":"preparando"},
    },
    "datetime":datetime.datetime,
    "timedelta":datetime.timedelta,
    "TZ":datetime.timezone(datetime.timedelta(hours=-5)),
    "secrets":secrets,
    "time":time,
}
exec(compile(ast.Module(body=[func["_progress_set"]],type_ignores=[]),"isolated_progress","exec"),namespace)
uploaded=[]
deleted=[]
sent=[]
audited=[]
namespace.update({
    "_upload_r2":lambda src,key,media,callback:(
        uploaded.append((src,key,media)),callback(1024,1024)),
    "_upload_progress_hook":lambda jobid:lambda written,total:
        namespace["_progress_set"](jobid,stage="subiendo_r2",r2_bytes=written),
    "_verify_benchmark_r2":lambda key,size:True,
    "_delete_benchmark_r2":lambda key:deleted.append(key),
    "_r2_url":lambda meth,key,exp:"https://synthetic-r2-only.invalid/signed",
    "_short_r2_link":lambda url,expires:"https://synthetic-worker.invalid/d/"+"x"*22,
    "_send_template":lambda *args,**kwargs:sent.append((args,kwargs)) or "synthetic-mid",
    "_audit":lambda *args:audited.append(args),
})
exec(compile(ast.Module(body=[func["_send_archived_video_to_test_phone"]],type_ignores=[]),
             "isolated_archived_send","exec"),namespace)
send=namespace["_send_archived_video_to_test_phone"]
send("success",Path("/synthetic-only.mp4"),1,"f"*32,"593999999999","operator")
job=namespace["_PROGRESS_JOBS"]["success"]
assert job["stage"]=="complete" and job["r2_verified"] and job["whatsapp_accepted"]
assert len(sent)==1 and len(audited)==1 and not deleted
assert sent[0][1]["test_mode"] is True
assert sent[0][1]["label_override"]=="VIDEO CLINICO AUTORIZADO"
assert sent[0][0][0]=="593999999999"
assert sent[0][0][1]=="PACIENTE DE PRUEBA"
assert sent[0][0][4].startswith("https://synthetic-worker.invalid/d/")
assert audited[0][0]==1 and audited[0][1]=="video"
assert "whatsapp_accepted" in job and not "phone" in job

def fail_before_meta(*args,**kwargs):
    raise ValueError("synthetic HEAD failure")
namespace["_verify_benchmark_r2"]=fail_before_meta
namespace["_PROGRESS_JOBS"]["earlyfail"]["size"]=1024
send("earlyfail",Path("/synthetic-only.mp4"),1,"e"*32,"593999999999","operator")
early=namespace["_PROGRESS_JOBS"]["earlyfail"]
assert early["stage"]=="error" and early["r2_deleted"] and not early.get("whatsapp_accepted")
assert len(sent)==1 and len(deleted)==1
namespace["_verify_benchmark_r2"]=lambda key,size:True
def fail_meta(*args,**kwargs):
    sent.append((args,kwargs))
    raise RuntimeError("synthetic ambiguous Meta failure")
namespace["_send_template"]=fail_meta
send("ambiguous",Path("/synthetic-only.mp4"),1,"d"*32,"593999999999","operator")
amb=namespace["_PROGRESS_JOBS"]["ambiguous"]
assert amb["stage"]=="error" and not amb.get("whatsapp_accepted")
assert len(sent)==2 and len(deleted)==1, "Never delete if Meta response is ambiguous"
assert len(audited)==1
print("RECEPTION_ARCHIVED_VIDEO_ONE_SHOT_STAFF_ALLOWLIST_NO_PATIENT_MODE_NO_DUPLICATES_OK")
