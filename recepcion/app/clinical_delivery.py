"""Manual clinical media delivery from Reception only.

Read-only Historia document inventory and verified signed PDF over local LAN.
No patient matching, invoice mutation, worker alarms, or automatic sending.
Requires explicit R2 credentials, bucket retention configuration and approved
WhatsApp templates before sending any patient content.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core_runtime as core
import clinical_delivery_config as clinical_config
import historia_lan_transport as lan
import reception_history_identity_consolidated as identity
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel

app = core.app
TZ = timezone(timedelta(hours=-5))
ROOT = Path(__file__).resolve().parent
AUDIT_DB = ROOT / "data" / "clinical_delivery_audit.db"
LIMIT_VIDEO = 550 * 1024 * 1024
LIMIT_PDF = 20 * 1024 * 1024


def _clinical_settings():
    """Read the wizard's local .env only for clinical delivery, without mutating
    environment variables, appointment messaging or the Cloudflare Worker.
    Reflect updates saved by the wizard even when Reception is already open.
    """
    saved = clinical_config.parse_existing()
    return {
        key: str(saved.get(key) or os.getenv(key, "") or "").strip()
        for key in clinical_config.ALLOWED
    }


def _clinical_setting(key):
    return _clinical_settings().get(key, "")


_MUTEX = threading.Lock()
_BUSY = set()

LABELS = {
    "receta": "Receta médica",
    "certificado": "Certificado médico",
    "reposo": "Certificado de reposo",
    "informe": "Informe médico",
    "video": "Videocistoscopía",
}


def _patient(db, pid):
    patient = db.get(core.Patient, int(pid))
    if patient is None:
        raise core.HTTPException(404, "Paciente no encontrado en Recepción")
    return patient


def _cloud_reception_id(pid):
    rid = str(int(pid))
    try:
        with core.LocalSessionLocal() as local:
            mapped = core.get_id_map(local, "patient", int(pid))
            if mapped is not None:
                rid = str(mapped)
    except Exception:
        pass
    return rid


def _linked_patient(pid):
    """Fail closed: only Reception-verified mapping from dedicated clinical Neon."""
    with core.LocalSessionLocal() as local:
        _patient(local, pid)
    rid = _cloud_reception_id(pid)
    conn = identity._connect_public()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT l.clinical_patient_id
            FROM public.patient_links l
            JOIN public.patients p ON p.id=l.clinical_patient_id
            WHERE l.reception_patient_id=%s AND l.verified=1
              AND l.deleted_at IS NULL AND p.deleted_at IS NULL
            LIMIT 1
        """, (rid,))
        row = cur.fetchone()
        if not row or not row[0]:
            raise core.HTTPException(409, "La ficha no está vinculada y verificada en Historia")
        return str(row[0]), rid, conn
    except Exception:
        conn.close()
        raise


def _documents(pid):
    clinical_id, rid, conn = _linked_patient(pid)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id::text,issued_at::text,'receta' AS kind
            FROM public.prescriptions
            WHERE patient_id=%s AND (deleted_at IS NULL OR deleted_at::text='')
            UNION ALL
            SELECT id::text,issued_at::text,
                   CASE WHEN certificate_type='rest_isolation' THEN 'reposo'
                        WHEN certificate_type IN ('report_cystoscopy','report_ultrasound') THEN 'informe'
                        ELSE 'certificado' END AS kind
            FROM public.certificates
            WHERE patient_id=%s AND (deleted_at IS NULL OR deleted_at::text='')
            ORDER BY issued_at DESC LIMIT 100
        """, (clinical_id, clinical_id))
        rows = cur.fetchall() or []
        return [{"id":str(a),"date":str(b)[:16],"kind":str(c),
                 "label": LABELS.get(str(c),"Documento clínico")} for a,b,c in rows],rid
    finally:
        conn.close()


def _signed_pdf(pid, kind, doc_id):
    if kind not in LABELS or kind == "video" or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", doc_id):
        raise core.HTTPException(400, "Documento inválido")
    docs, rid = _documents(pid)
    if not any(d["id"] == doc_id and d["kind"] == kind for d in docs):
        raise core.HTTPException(404, "Documento no pertenece al paciente vinculado")
    secret=_clinical_setting("CLINICAL_DELIVERY_LAN_SECRET")
    if len(secret)<32:
        raise core.HTTPException(503,"Falta la clave privada compartida de entrega clínica por LAN")
    stamp=str(int(time.time()))
    proof=hmac.new(secret.encode("utf-8"),
                   f"{rid}|{kind}|{doc_id}|{stamp}".encode("utf-8"),hashlib.sha256).hexdigest()
    query = urllib.parse.urlencode({"reception_id":rid,"kind":kind,"doc_id":doc_id})
    for host in lan._candidate_hosts():
        challenge = lan._challenge(host, timeout=0.7)
        if not challenge:
            continue
        url = f"http://{host}:{lan.LAN_HTTP_PORT}/delivery/signed-pdf?{query}"
        req = urllib.request.Request(url, headers={
            "X-Historia-LAN-Token":str(challenge["token"]),
            "X-Revelo-Delivery-Time":stamp,
            "X-Revelo-Delivery-Proof":proof,
            "Cache-Control":"no-store",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                if response.headers.get("Content-Type","").split(";")[0] != "application/pdf":
                    raise ValueError("Respuesta de Historia inválida")
                declared = int(response.headers.get("Content-Length","0") or 0)
                if declared > LIMIT_PDF:
                    raise ValueError("El PDF supera el máximo de seguridad")
                data = response.read(LIMIT_PDF+1)
                if not data.startswith(b"%PDF") or len(data)>LIMIT_PDF:
                    raise ValueError("El PDF firmado es inválido")
                return data
        except urllib.error.HTTPError as exc:
            if exc.code in (403,404):
                raise core.HTTPException(409, "PDF firmado no disponible o ficha sin vinculación verificada") from exc
        except Exception:
            continue
    raise core.HTTPException(503, "La PC de Historia no está disponible para recuperar el PDF original firmado")


def _phone(patient):
    raw = re.sub(r"\D", "", str(getattr(patient,"celular","") or ""))
    if len(raw) == 10 and raw.startswith("09"):
        return "593"+raw[1:]
    if len(raw) == 12 and raw.startswith("5939"):
        return raw
    raise core.HTTPException(409,"Verifica primero el celular del paciente en su ficha")


def _setup():
    cfg = _clinical_settings()
    account=cfg["CLINICAL_R2_ACCOUNT_ID"]
    bucket=cfg["CLINICAL_R2_BUCKET"]
    key=cfg["CLINICAL_R2_ACCESS_KEY_ID"]
    secret=cfg["CLINICAL_R2_SECRET_ACCESS_KEY"]
    template_doc=cfg["WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE"]
    template_video=cfg["WHATSAPP_CLINICAL_VIDEO_TEMPLATE"]
    # Fail closed while either Meta template is in review. Saving API keys or
    # naming templates alone must never unlock patient messaging.
    approved=cfg["WHATSAPP_CLINICAL_TEMPLATES_APPROVED"]=="1"
    live_enabled=cfg["CLINICAL_DELIVERY_LIVE_ENABLED"]=="1"
    retention=cfg["CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED"]=="1"
    ready_r2=all((account,bucket,key,secret,retention)) and bool(re.fullmatch(r"[a-z0-9-]{3,63}",bucket))
    wa_ready=all((cfg["WHATSAPP_GRAPH_VERSION"] or core.WHATSAPP_GRAPH_VERSION,\
                  cfg["WHATSAPP_PHONE_NUMBER_ID"] or core.WHATSAPP_PHONE_NUMBER_ID,\
                  cfg["WHATSAPP_ACCESS_TOKEN"] or core.WHATSAPP_ACCESS_TOKEN))
    lan_ready=len(cfg["CLINICAL_DELIVERY_LAN_SECRET"])>=32
    test_phone=re.sub(r"\D","",cfg["WHATSAPP_TEST_PHONE"] or core.WHATSAPP_TEST_PHONE or "")
    if len(test_phone)==10 and test_phone.startswith("09"):
        test_phone="593"+test_phone[1:]
    ready_test=bool(approved and ready_r2 and wa_ready and template_doc and template_video and re.fullmatch(r"5939\d{8}",test_phone))
    return {"ready_r2":ready_r2,"ready_whatsapp":wa_ready,"ready_test":ready_test,
            "clinical_delivery_enabled":live_enabled,
            "clinical_templates_approved":approved,
            "ready_document":bool(live_enabled and approved and ready_r2 and wa_ready and template_doc and lan_ready),
            "ready_video":bool(live_enabled and approved and ready_r2 and wa_ready and template_video),
            "missing":[name for name,present in [
                ("Habilitación clínica manual (desactivada por seguridad)",live_enabled),
                ("Aprobación de ambas plantillas en Meta",approved),
                ("Cuenta/bucket y claves R2",all((account,bucket,key,secret))),
                ("Regla de borrado R2 a 7 días",retention),
                ("Credenciales WhatsApp",wa_ready),
                ("Plantilla de documentos aprobada",bool(template_doc)),
                ("Clave LAN compartida con Historia",lan_ready),
                ("Plantilla de video aprobada",bool(template_video)),
            ] if not present],
            "test_missing":[name for name,present in [
                ("Plantillas Meta aprobadas",approved),
                ("Almacenamiento R2 y eliminación a 7 días",ready_r2),
                ("Número y credenciales WhatsApp de Recepción",wa_ready),
                ("Plantilla de documentos aprobada por Meta",bool(template_doc)),
                ("Plantilla de video aprobada por Meta",bool(template_video)),
                ("WHATSAPP_TEST_PHONE de tu iPhone",bool(re.fullmatch(r"5939\d{8}",test_phone))),
            ] if not present]}


def _r2_url(method, key, expires=604800):
    cfg = _clinical_settings()
    account=cfg["CLINICAL_R2_ACCOUNT_ID"]
    bucket=cfg["CLINICAL_R2_BUCKET"]
    access=cfg["CLINICAL_R2_ACCESS_KEY_ID"]
    secret=cfg["CLINICAL_R2_SECRET_ACCESS_KEY"]
    host=f"{account}.r2.cloudflarestorage.com"
    path="/"+urllib.parse.quote(bucket+"/"+key,safe="/-_.~")
    now=datetime.now(timezone.utc)
    stamp=now.strftime("%Y%m%dT%H%M%SZ")
    day=stamp[:8]
    scope=f"{day}/auto/s3/aws4_request"
    params={
        "X-Amz-Algorithm":"AWS4-HMAC-SHA256",
        "X-Amz-Credential":f"{access}/{scope}",
        "X-Amz-Date":stamp,
        "X-Amz-Expires":str(int(expires)),
        "X-Amz-SignedHeaders":"host",
    }
    qs=urllib.parse.urlencode(sorted(params.items()),quote_via=urllib.parse.quote,safe="~")
    canonical=f"{method}\n{path}\n{qs}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    to_sign=f"AWS4-HMAC-SHA256\n{stamp}\n{scope}\n{digest}"
    sign=lambda key,msg:hmac.new(key,msg.encode(),hashlib.sha256).digest()
    signing=sign(sign(sign(sign(("AWS4"+secret).encode(),day),"auto"),"s3"),"aws4_request")
    sig=hmac.new(signing,to_sign.encode(),hashlib.sha256).hexdigest()
    return f"https://{host}{path}?{qs}&X-Amz-Signature={sig}"


def _upload_r2(filename, key, media_type):
    """Upload by streaming, never loading a 400MB USB recording into memory."""
    signed=_r2_url("PUT",key,300)
    url=urllib.parse.urlsplit(signed)
    size=Path(filename).stat().st_size
    conn=http.client.HTTPSConnection(url.hostname,timeout=150)
    try:
        conn.putrequest("PUT",url.path+"?"+url.query)
        conn.putheader("Content-Length",str(size))
        conn.putheader("Content-Type",media_type)
        conn.endheaders()
        with open(filename,"rb") as f:
            while True:
                chunk=f.read(512*1024)
                if not chunk:break
                conn.send(chunk)
        result=conn.getresponse()
        message=result.read(1024)
        if result.status not in (200,201,204):
            raise RuntimeError(f"R2 rechazó la subida (HTTP {result.status})")
    finally:
        conn.close()


def _send_template(phone, name, kind, expiry, url, label_override=None):
    cfg = _clinical_settings()
    template = (cfg["WHATSAPP_CLINICAL_VIDEO_TEMPLATE"]
                if kind=="video" else cfg["WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE"])
    if not template:
        raise RuntimeError("Falta configurar la plantilla aprobada por Meta")
    payload = core.whatsapp_build_template_payload(
        to=phone,template_name=template,
        language_code=cfg["WHATSAPP_CLINICAL_LANGUAGE"] or "es_EC",
        body_params=[name,label_override or LABELS[kind],expiry,url],
    )
    response=core.whatsapp_send_template(
        graph_version=cfg["WHATSAPP_GRAPH_VERSION"] or core.WHATSAPP_GRAPH_VERSION,
        phone_number_id=cfg["WHATSAPP_PHONE_NUMBER_ID"] or core.WHATSAPP_PHONE_NUMBER_ID,
        access_token=cfg["WHATSAPP_ACCESS_TOKEN"] or core.WHATSAPP_ACCESS_TOKEN,
        payload=payload,
    )
    mid=str((response.get("messages") or [{}])[0].get("id") or "")
    if not mid:raise RuntimeError("Meta no confirmó el identificador del mensaje")
    return mid


def _audit(pid,kind,doc_id,message_id,expiry,username):
    AUDIT_DB.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(AUDIT_DB,timeout=10) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS deliveries(
         id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id INTEGER NOT NULL,kind TEXT NOT NULL,
         document_id TEXT,message_id TEXT NOT NULL,expires_at TEXT NOT NULL,
         sent_at TEXT NOT NULL,operator TEXT NOT NULL)""")
        conn.execute("""INSERT INTO deliveries(patient_id,kind,document_id,message_id,expires_at,sent_at,operator)
         VALUES(?,?,?,?,?,?,?)""",(pid,kind,doc_id,message_id,expiry,
                                 datetime.now(TZ).isoformat(timespec="seconds"),username))


class DeliverDocument(BaseModel):
    document_id:str
    kind:str
    confirmed_phone:str
    consent_confirmed:bool=False
    identity_confirmed:bool=False


def _guard(patient, data):
    if not data.consent_confirmed or not data.identity_confirmed:
        raise core.HTTPException(400,"Confirma la identidad, el número y el consentimiento del paciente")
    phone=_phone(patient)
    if re.sub(r"\D","",data.confirmed_phone or "")!=phone:
        raise core.HTTPException(409,"El número confirmado no coincide con la ficha")
    return phone


def _deliver_temp(pid,kind,doc_id,file_path,media_type,patient,user):
    lock_id=(pid,kind,doc_id)
    with _MUTEX:
        if lock_id in _BUSY:
            raise core.HTTPException(409,"Este archivo ya se está enviando")
        _BUSY.add(lock_id)
    try:
        name=" ".join(str(patient.nombre or "").split()).upper()
        now=datetime.now(TZ)
        expiry_dt=now+timedelta(days=7)
        expiry=expiry_dt.strftime("%d/%m/%Y a las %H:%M")
        key="clinical-temp/"+now.strftime("%Y/%m/%d")+"/"+secrets.token_hex(24)+(".mp4" if kind=="video" else ".pdf")
        _upload_r2(file_path,key,media_type)
        url=_r2_url("GET",key,604800)
        phone=_phone(patient)
        message_id=_send_template(phone,name,kind,expiry,url)
        _audit(pid,kind,doc_id,message_id,expiry_dt.isoformat(),str(getattr(user,"username","recepcion")))
        return {"ok":True,"sent":True,"message_id":message_id,"expires_at":expiry_dt.isoformat()}
    finally:
        with _MUTEX:
            _BUSY.discard(lock_id)


# Self-test never touches patients, encounters, clinical files or medical database.
_LAST_TEST_SEND = 0.0
_TEST_SEND_LOCK = threading.Lock()


def _test_pdf():
    """Minimal valid self-contained PDF: synthetic text only, no patient data."""
    stream = b"BT /F1 20 Tf 46 160 Td (PRUEBA SIN DATOS MEDICOS) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 550 240] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    positions = [0]
    for i, body in enumerate(objects, 1):
        positions.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    position = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in positions[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(position).encode() + b"\n%%EOF\n"
    return out


def _test_send(phone: str):
    """Real Meta/R2 test only to preapproved self-test number, operator initiated."""
    global _LAST_TEST_SEND
    if not _setup()["ready_test"]:
        raise core.HTTPException(503, "Faltan R2, plantilla aprobada o número de pruebas")
    raw = re.sub(r"\D", "", str(phone or ""))
    if len(raw) == 10 and raw.startswith("09"):
        raw = "593" + raw[1:]
    allow = re.sub(r"\D", "", str(_clinical_setting("WHATSAPP_TEST_PHONE") or core.WHATSAPP_TEST_PHONE or ""))
    if len(allow) == 10 and allow.startswith("09"):
        allow = "593" + allow[1:]
    if not raw or not hmac.compare_digest(raw, allow):
        raise core.HTTPException(403, "Solo se permite enviar al celular autorizado como WHATSAPP_TEST_PHONE")
    with _TEST_SEND_LOCK:
        if time.monotonic() - _LAST_TEST_SEND < 300:
            raise core.HTTPException(429, "Ya se hizo una prueba. Se admite otra en cinco minutos")
        _LAST_TEST_SEND = time.monotonic()
    now = datetime.now(TZ)
    expires_at = now + timedelta(days=7)
    key = "clinical-temp/self-test/" + secrets.token_hex(24) + ".pdf"
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_synthetic_test_",suffix=".pdf",delete=False) as tmp:
            temp_name=tmp.name
            pdf=_test_pdf()
            tmp.write(pdf)
        _upload_r2(temp_name, key, "application/pdf")
        url = _r2_url("GET", key, 604800)
        # Verify the R2 object is readable and byte-identical before sending.
        with urllib.request.urlopen(url, timeout=25) as response:
            downloaded = response.read(len(pdf)+1)
        if not hmac.compare_digest(hashlib.sha256(downloaded).digest(),hashlib.sha256(pdf).digest()):
            raise RuntimeError("El PDF de prueba descargado desde R2 no coincide con el original")
        message_id = _send_template(raw, "PACIENTE DE PRUEBA", "receta",
            expires_at.strftime("%d/%m/%Y a las %H:%M"), url,
            label_override="DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)")
        return {"ok": True, "sent": True, "message_id": message_id,
                "expires_at": expires_at.isoformat(),
                "note": "Meta aceptó el envío. Confirma personalmente su recepción y descarga en tu iPhone."}
    finally:
        if temp_name:
            try:os.unlink(temp_name)
            except OSError:pass


class TestDelivery(BaseModel):
    phone: str
    confirmation: str


@app.post("/api/clinical-delivery/send-self-test")
async def delivery_self_test(data: TestDelivery, user=core.Depends(core.current_user)):
    if data.confirmation != "ENVIAR PRUEBA":
        raise core.HTTPException(400, "Confirma explícitamente ENVIAR PRUEBA")
    return await asyncio.to_thread(_test_send,data.phone)


def _check_r2():
    """Probe isolated synthetic bytes, expiration metadata, and cleanup; no patients."""
    if not _setup()["ready_r2"]:
        raise core.HTTPException(503, "Completa primero el bucket privado, claves y la regla de 7 días")
    from email.utils import parsedate_to_datetime
    key = "clinical-temp/self-test/r2-check-" + secrets.token_hex(16) + ".bin"
    temp = None
    uploaded = False
    expected = secrets.token_bytes(144)
    deletion_ok = False
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_r2_probe_",suffix=".bin",delete=False) as out:
            temp=out.name
            out.write(expected)
        _upload_r2(temp,key,"application/octet-stream")
        uploaded = True
        with urllib.request.urlopen(_r2_url("GET",key,180),timeout=20) as resp:
            actual = resp.read(len(expected)+1)
        if not hmac.compare_digest(actual,expected):
            raise RuntimeError("R2 devolvió contenido diferente al enviado")
        signed_head = _r2_url("HEAD",key,180)
        with urllib.request.urlopen(urllib.request.Request(signed_head,method="HEAD"),timeout=20) as resp:
            expiration_header=resp.headers.get("x-amz-expiration","")
        lifecycle_verified=False
        match=re.search(r'expiry-date="([^"]+)"',expiration_header or "",flags=re.I)
        if match:
            try:
                expire=parsedate_to_datetime(match.group(1))
                days=(expire-datetime.now(timezone.utc)).total_seconds()/86400
                lifecycle_verified=6.0<=days<=8.1
            except (ValueError,TypeError):
                pass
        return {"ok":True,"r2_upload_download_verified":True,
                "lifecycle_7_day_header_verified":lifecycle_verified,
                "note":"Comprobación R2 correcta. La política de borrado "
                       +("refleja aproximadamente 7 días." if lifecycle_verified
                         else "no pudo verificarse por cabecera: revisa Object Lifecycles.")}
    finally:
        if uploaded:
            try:
                delete=urllib.request.Request(_r2_url("DELETE",key,180),method="DELETE")
                with urllib.request.urlopen(delete,timeout=15):
                    deletion_ok=True
            except Exception:
                pass  # Existing 7-day lifecycle remains the cleanup fallback.
        if temp:
            try:os.unlink(temp)
            except OSError:pass


@app.post("/api/clinical-delivery/check-r2")
async def delivery_check_r2(user=core.Depends(core.current_user)):
    return await asyncio.to_thread(_check_r2)


@app.get("/api/clinical-delivery/status")
def delivery_status(user=core.Depends(core.current_user)):
    return {"ok":True,**_setup(),"privacy":"private-bucket-presigned-link"}


@app.get("/api/clinical-delivery/patients/{pid}/documents")
def delivery_documents(pid:int,db=core.Depends(core.get_db),user=core.Depends(core.current_user)):
    _patient(db,pid)
    try:
        docs,_=_documents(pid)
        return {"ok":True,"documents":docs,**_setup()}
    except core.HTTPException:raise
    except Exception:
        return {"ok":False,"documents":[],"error":"No se pudo consultar Historia Clínica; vuelve a intentarlo"}


@app.get("/api/clinical-delivery/patients/{pid}/signed/{kind}/{doc_id}")
def delivery_signed_preview(pid:int,kind:str,doc_id:str,user=core.Depends(core.current_user)):
    data=_signed_pdf(pid,kind,doc_id)
    return Response(data,media_type="application/pdf",headers={
        "Cache-Control":"private, no-store",
        "Content-Disposition":'inline; filename="Documento_firmado.pdf"',
        "X-Content-Type-Options":"nosniff",
    })


@app.post("/api/clinical-delivery/patients/{pid}/send-document")
async def delivery_send_document(pid:int,data:DeliverDocument,db=core.Depends(core.get_db),
                                 user=core.Depends(core.current_user)):
    if not _setup()["ready_document"]:
        raise core.HTTPException(503,"Envío desactivado: configura R2, retención y plantilla aprobada de documentos")
    patient=_patient(db,pid)
    _guard(patient,data)
    pdf=await asyncio.to_thread(_signed_pdf,pid,data.kind,data.document_id)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_delivery_",suffix=".pdf",delete=False) as f:
            tmp=f.name
            f.write(pdf)
        return await asyncio.to_thread(_deliver_temp,pid,data.kind,data.document_id,tmp,
                                       "application/pdf",patient,user)
    finally:
        if tmp:
            try:os.unlink(tmp)
            except OSError:pass


@app.post("/api/clinical-delivery/patients/{pid}/send-video")
async def delivery_send_video(pid:int,request:Request,confirmed_phone:str,
                              consent_confirmed:bool=False,identity_confirmed:bool=False,
                              db=core.Depends(core.get_db),
                              user=core.Depends(core.current_user)):
    if not _setup()["ready_video"]:
        raise core.HTTPException(503,"Envío desactivado: configura R2, retención y plantilla aprobada de video")
    patient=_patient(db,pid)
    _guard(patient,DeliverDocument(document_id="usb",kind="video",confirmed_phone=confirmed_phone,
                                   consent_confirmed=consent_confirmed,identity_confirmed=identity_confirmed))
    if "video/mp4" not in request.headers.get("content-type","").lower():
        raise core.HTTPException(415,"Solo se aceptan archivos MP4")
    tmp=None
    size=0
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_video_",suffix=".mp4",delete=False) as f:
            tmp=f.name
            async for chunk in request.stream():
                size+=len(chunk)
                if size>LIMIT_VIDEO:
                    raise core.HTTPException(413,"Video demasiado grande (máximo 550 MB)")
                f.write(chunk)
        with open(tmp,"rb") as video_check:
            header=video_check.read(24)
        if size<1024 or b"ftyp" not in header:
            raise core.HTTPException(415,"El archivo no parece un video MP4 válido")
        return await asyncio.to_thread(_deliver_temp,pid,"video",secrets.token_hex(12),tmp,
                                       "video/mp4",patient,user)
    finally:
        if tmp:
            try:os.unlink(tmp)
            except OSError:pass
