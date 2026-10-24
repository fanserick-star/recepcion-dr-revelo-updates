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
import shutil
import subprocess
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core_runtime as core
import clinical_delivery_config as clinical_config
import historia_lan_transport as lan
import reception_history_identity_consolidated as identity
from fastapi import Request, BackgroundTasks
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
                 "label": LABELS.get(str(c),"Documento clínico")} for a,b,c in rows],rid,clinical_id
    finally:
        conn.close()



def _lan_pdf_failure(exc):
    """Translate Historia's legacy LAN errors without exposing paths or clinical data."""
    try:
        payload = json.loads(exc.read(1024).decode("utf-8", "replace"))
        reason = str(payload.get("error") or "").lower()
    except (OSError, ValueError, AttributeError, TypeError):
        reason = ""
    if exc.code == 403:
        return (503, "Historia rechazó la autorización de PDF. Comprueba que ambas PC tengan la misma clave LAN de entrega clínica.")
    if exc.code == 404:
        if "todavía no ha guardado un pdf firmado" in reason:
            return (404, "El documento está guardado, pero todavía no tiene PDF firmado. El doctor debe firmarlo en Historia Clínica.")
        if "copia original firmada no está disponible" in reason:
            return (404, "Existe un registro de firma, pero el PDF original no está disponible en la PC de Historia. No se ha generado otra copia.")
        if "documento no está sincronizado" in reason:
            return (404, "El documento está en Neon, pero falta en la base local de Historia. Comprueba su sincronización; el PDF no se ha modificado.")
        if "vinculación local difiere" in reason or "vinculación local contradictoria" in reason:
            return (409, "Historia tiene una vinculación local distinta de la ficha verificada en Neon. Se bloqueó la lectura para proteger los datos; revisa la sincronización en Historia.")
        if "tipo de documento no coincide" in reason:
            return (409, "Historia y Neon no coinciden en la clasificación de este documento. Se bloqueó el acceso hasta verificar el tipo correcto.")
        if "vinculación clínica verificada" in reason or "no pertenece a la ficha" in reason or "tipo de documento no coincide" in reason:
            return (409, "Historia no reconoce la vinculación o el documento de esta ficha. Revisa la sincronización de fichas; no se modificó ninguna.")
        if "integridad" in reason or "límite de seguridad" in reason:
            return (409, "Historia rechazó el PDF firmado por una comprobación de integridad o tamaño. El original no se modificó.")
        return (409, "Historia no pudo verificar este PDF. Comprueba la vinculación y que exista la firma original en la PC del doctor.")
    if exc.code == 503:
        return (503, "Historia respondió, pero no pudo consultar su archivo clínico local. Revisa Historia en la PC del doctor.")
    return (503, "Historia no pudo completar la consulta segura de este PDF.")

def _signed_pdf(pid, kind, doc_id):
    if kind not in LABELS or kind == "video" or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", doc_id):
        raise core.HTTPException(400, "Documento inválido")
    docs, rid, clinical_id = _documents(pid)
    if not any(d["id"] == doc_id and d["kind"] == kind for d in docs):
        raise core.HTTPException(404, "Documento no pertenece al paciente vinculado")
    secret=_clinical_setting("CLINICAL_DELIVERY_LAN_SECRET")
    if len(secret)<32:
        raise core.HTTPException(503,"Falta la clave privada compartida de entrega clínica por LAN")
    stamp=str(int(time.time()))
    proof=hmac.new(secret.encode("utf-8"),
                   f"{rid}|{clinical_id}|{kind}|{doc_id}|{stamp}".encode("utf-8"),hashlib.sha256).hexdigest()
    query = urllib.parse.urlencode({"reception_id":rid,"clinical_patient_id":clinical_id,
                                   "kind":kind,"doc_id":doc_id})
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
            code, message = _lan_pdf_failure(exc)
            raise core.HTTPException(code, message) from exc
        except Exception:
            continue
    raise core.HTTPException(503, "La PC de Historia no está disponible para recuperar el PDF original firmado")



def _unsigned_preview_html(pid, kind, doc_id):
    """Read-only unsigned HTML preview; never creates or signs a PDF."""
    if kind not in {"receta", "certificado", "reposo", "informe"} or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,100}", doc_id):
        raise core.HTTPException(400, "Documento inválido")
    docs, rid, clinical_id = _documents(pid)
    if not any(d["id"] == doc_id and d["kind"] == kind for d in docs):
        raise core.HTTPException(404, "Documento no pertenece al paciente vinculado")
    secret = _clinical_setting("CLINICAL_DELIVERY_LAN_SECRET")
    if len(secret) < 32:
        raise core.HTTPException(503, "Falta la autorización privada LAN de Historia")
    stamp = str(int(time.time()))
    proof = hmac.new(secret.encode("utf-8"),
                     f"{rid}|{clinical_id}|{kind}|{doc_id}|{stamp}".encode("utf-8"),
                     hashlib.sha256).hexdigest()
    query = urllib.parse.urlencode({
        "reception_id": rid, "clinical_patient_id": clinical_id,
        "kind": kind, "doc_id": doc_id,
    })
    for host in lan._candidate_hosts():
        challenge = lan._challenge(host, timeout=0.7)
        if not challenge:
            continue
        url = f"http://{host}:{lan.LAN_HTTP_PORT}/delivery/unsigned-preview?{query}"
        req = urllib.request.Request(url, headers={
            "X-Historia-LAN-Token": str(challenge["token"]),
            "X-Revelo-Delivery-Time": stamp,
            "X-Revelo-Delivery-Proof": proof,
            "Cache-Control": "no-store",
        })
        try:
            with urllib.request.urlopen(req, timeout=25) as result:
                if result.headers.get("Content-Type", "").split(";")[0] != "text/html":
                    raise ValueError("Historia no devolvió una vista segura")
                if result.headers.get("X-Clinical-Preview-Unsigned") != "1":
                    raise ValueError("Historia no identificó la vista como no firmada")
                if int(result.headers.get("Content-Length", "0") or 0) > 2 * 1024 * 1024:
                    raise ValueError("Vista demasiado grande")
                data = result.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024 or b"SIN FIRMA ELECTR" not in data:
                    raise ValueError("Vista sin identificación de firma inválida")
                return data
        except urllib.error.HTTPError as exc:
            code, message = _lan_pdf_failure(exc)
            raise core.HTTPException(code, message) from exc
        except Exception:
            continue
    raise core.HTTPException(503, "No se pudo consultar la vista sin firma en la PC de Historia")


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
    # The Cloudflare Worker owns the proven Meta sender credential. Reception
    # issues a bounded, single-use capability via its existing Neon connection.
    # Local WhatsApp access tokens are deliberately NOT used for clinical sends.
    wa_ready=bool(getattr(core,"CloudSessionLocal",None)
                  and not getattr(core,"FORCE_OFFLINE",False))
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
                ("Conexión Neon para el Worker clínico",wa_ready),
                ("Plantilla de documentos aprobada",bool(template_doc)),
                ("Clave LAN compartida con Historia",lan_ready),
                ("Plantilla de video aprobada",bool(template_video)),
            ] if not present],
            "test_missing":[name for name,present in [
                ("Plantillas Meta aprobadas",approved),
                ("Almacenamiento R2 y eliminación a 7 días",ready_r2),
                ("Conexión Neon al Worker de WhatsApp",wa_ready),
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


def _upload_r2(filename, key, media_type, progress_callback=None):
    """Stream 512 KiB at a time. Count transmitted bytes, confirm R2 response.

    Progress is socket-transmitted bytes, NOT server-confirmed storage. UI must
    show 'verificando' until the HTTP response and HEAD validation succeed.
    """
    signed=_r2_url("PUT",key,3600)
    url=urllib.parse.urlsplit(signed)
    size=Path(filename).stat().st_size
    conn=http.client.HTTPSConnection(url.hostname,timeout=300)
    done=0
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
                done+=len(chunk)
                if progress_callback:
                    progress_callback(done,size)
        result=conn.getresponse()
        result.read(1024)
        if result.status not in (200,201,204):
            raise RuntimeError(f"R2 rechazó la subida (HTTP {result.status})")
    finally:
        conn.close()


CLINICAL_WORKER_URL = "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/clinical/dispatch"


def _issue_clinical_capability(phone, mode):
    """Neon holds only random capability and recipient hashes; no PHI or URLs."""
    if mode not in ("test","patient") or not re.fullmatch(r"5939\d{8}",phone):
        raise core.HTTPException(400,"Permiso clínico inválido")
    session_factory = getattr(core,"CloudSessionLocal",None)
    if not session_factory or getattr(core,"FORCE_OFFLINE",False):
        raise core.HTTPException(503,"Se necesita conexión segura a Neón para solicitar el envío")
    token=secrets.token_urlsafe(32)
    digest=hashlib.sha256(token.encode("ascii")).hexdigest()
    recipient_hash=hashlib.sha256((token+"|"+phone).encode("ascii")).hexdigest()
    try:
        with session_factory() as session:
            session.execute(core.text("""
                INSERT INTO whatsapp_cloud.clinical_delivery_caps
                    (token_hash,recipient_hash,mode,expires_at)
                VALUES (:token_hash,:recipient_hash,:mode,now()+interval '120 seconds')
            """),{"token_hash":digest,"recipient_hash":recipient_hash,"mode":mode})
            session.commit()
    except Exception as exc:
        raise core.HTTPException(503,"No se pudo solicitar autorización clínica temporal al Worker") from exc
    return token



CLINICAL_SHORT_BASE = "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/d/"


def _short_r2_link(signed_get_url, expires_at):
    """Create opaque 132-bit link manifest in private R2. No patient data in Neon.

    Worker only redirects to signed R2; never proxies video bytes.
    """
    import base64
    import urllib.error
    if not _setup()["ready_r2"]:
        raise core.HTTPException(503, "R2 privado no está configurado")
    expiry_epoch=int(expires_at.timestamp())
    remaining=expiry_epoch-int(time.time())
    if remaining<=60 or remaining>604800:
        raise core.HTTPException(400, "Caducidad del enlace no válida")
    parsed=urllib.parse.urlsplit(signed_get_url)
    cfg=_clinical_settings()
    if (parsed.scheme!="https" or parsed.netloc!=cfg["CLINICAL_R2_ACCOUNT_ID"].lower()+".r2.cloudflarestorage.com" or
        not parsed.path.startswith("/dr-revelo-clinical-2026/clinical-temp/") or
        not re.fullmatch(r"[0-9a-f]{64}",urllib.parse.parse_qs(parsed.query).get("X-Amz-Signature",[""])[0])):
        raise core.HTTPException(400, "El destino privado de R2 no es válido")
    slug=base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}",slug):
        raise RuntimeError("Identificador temporal inválido")
    record=json.dumps({"expires_epoch":expiry_epoch,"signed_get_url":signed_get_url},
                      separators=(",",":"),ensure_ascii=True).encode("utf-8")
    tmpname=None
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_private_link_",suffix=".json",delete=False) as tmp:
            tmpname=tmp.name
            tmp.write(record)
        _upload_r2(tmpname,"clinical-temp/short-links/"+slug+".json","application/json")
    finally:
        if tmpname:
            try:os.unlink(tmpname)
            except OSError:pass
    result=CLINICAL_SHORT_BASE+slug
    # Fail closed: verify route, R2 mapping and signed target before any WhatsApp.
    request=urllib.request.Request(
        result,method="GET",headers={"User-Agent":"curl/8.10.1","Range":"bytes=0-0"})
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            valid=response.read(1)
            target=urllib.parse.urlsplit(response.geturl())
        if not valid or target.hostname!=parsed.hostname or target.path!=parsed.path:
            raise RuntimeError("La redirección no llegó al archivo privado")
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError) as exc:
        raise core.HTTPException(502,"El enlace corto todavía no está disponible; no se envió WhatsApp") from exc
    return result


def _send_template(phone, name, kind, expiry, url, label_override=None, *, test_mode=False):
    cfg=_clinical_settings()
    template=(cfg["WHATSAPP_CLINICAL_VIDEO_TEMPLATE"]
              if kind=="video" else cfg["WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE"])
    if template not in ("entrega_documento_clinico","entrega_video_clinico"):
        raise core.HTTPException(503,"Configura las plantillas clínicas aprobadas en Meta")
    if not re.fullmatch(r"5939\d{8}",str(phone)):
        raise core.HTTPException(400,"Número clínico inválido")
    if test_mode:
        if name!="PACIENTE DE PRUEBA" or label_override not in ("DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)","VIDEO DE PRUEBA (SIN DATOS MEDICOS)","VIDEO CLINICO AUTORIZADO") or kind=="video":
            raise core.HTTPException(400,"Solo se permiten archivos ficticios en la prueba")
    elif _setup()["clinical_delivery_enabled"] is not True:
        raise core.HTTPException(503,"Las entregas a pacientes continúan desactivadas")
    # The file was already uploaded directly from Reception to R2. Only a
    # short text payload and single-use capability cross the Worker.
    capability=_issue_clinical_capability(phone,"test" if test_mode else "patient")
    payload={
      "token":capability,
      "mode":"test" if test_mode else "patient",
      "phone":phone,
      "template":template,
      "body_params":[name,label_override or LABELS[kind],expiry,url],
    }
    request=urllib.request.Request(
        CLINICAL_WORKER_URL,
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json","Accept":"application/json",
                 "User-Agent":"curl/8.10.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            answer=json.loads(response.read(4096).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Never surface raw Worker/Meta responses, signed URLs or phone data.
        try:
            result=json.loads(exc.read(2048).decode("utf-8"))
        except (UnicodeError,ValueError):
            result={}
        error=str(result.get("error","")) if isinstance(result,dict) else ""
        allowed={"sender_unavailable","clinical_permission_unavailable",
                 "expired_or_used_clinical_permission","invalid_clinical_request",
                 "invalid_url","meta_rejected_no_retry","meta_unconfirmed_no_retry"}
        err=error if error in allowed else "worker_rejected"
        code=result.get("meta_code") if isinstance(result,dict) else None
        suffix=(f" · Meta {code}" if type(code) is int and 0<code<1000000 else "")
        raise core.HTTPException(502,"Worker clínico: "+err+suffix+
                  ". No repetir automáticamente; verificar el resultado en WhatsApp.") from exc
    except (urllib.error.URLError,TimeoutError) as exc:
        raise core.HTTPException(502,"No se confirmó la respuesta del Worker. No reintentar sin verificar WhatsApp.") from exc
    mid=str((answer.get("message_id") or "") if isinstance(answer,dict) else "")
    if not (answer.get("accepted_by_meta") is True and mid):
        raise core.HTTPException(502,"Worker no confirmó la aceptación del mensaje; no repetir automáticamente")
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
        short_url=_short_r2_link(url,expiry_dt)
        phone=_phone(patient)
        message_id=_send_template(phone,name,kind,expiry,short_url)
        _audit(pid,kind,doc_id,message_id,expiry_dt.isoformat(),str(getattr(user,"username","recepcion")))
        return {"ok":True,"sent":True,"message_id":message_id,"expires_at":expiry_dt.isoformat()}
    finally:
        with _MUTEX:
            _BUSY.discard(lock_id)


# Manual video speed test / delivery progress. Only local process RAM has job
# state; no polling Neon, Cloudflare Workers, appointments, or patient histories.
_PROGRESS_LOCK=threading.Lock()
_PROGRESS_JOBS={}
_PROGRESS_MAX=6


def _progress_set(job_id, **values):
    with _PROGRESS_LOCK:
        job=_PROGRESS_JOBS.get(job_id)
        if job:
            job.update(values)


def _progress_snapshot(job_id):
    with _PROGRESS_LOCK:
        job=_PROGRESS_JOBS.get(job_id)
        if not job:
            raise core.HTTPException(404,"Prueba no disponible o expirada")
        now=time.monotonic()
        stage=str(job.get("stage","preparando"))
        uploaded=int(job.get("r2_bytes",0))
        started=float(job.get("r2_started",now))
        finished=float(job.get("r2_finished") or now)
        elapsed=max(0,finished-started) if job.get("r2_started") else 0
        rate=(uploaded/1048576/elapsed) if elapsed>0 and uploaded else 0.0
        return {"ok":True,"stage":stage,"total_bytes":job["size"],
                "local_bytes":int(job.get("local_bytes",0)),
                "r2_bytes":uploaded,"elapsed_seconds":round(elapsed,1),
                "upload_mibps":round(rate,2),
                "done":stage in ("complete","error"),
                "error":str(job.get("error","")) if stage=="error" else "",
                "r2_verified":bool(job.get("r2_verified",False)),
                "r2_deleted":bool(job.get("r2_deleted",False)),
                "whatsapp_accepted":bool(job.get("whatsapp_accepted",False)),
                "mode":job["mode"],"expires_at":str(job.get("expires_at","")) if stage=="complete" else ""}


def _upload_progress_hook(job_id):
    def report(written,total):
        _progress_set(job_id,stage="subiendo_r2",r2_bytes=written)
    return report


def _verify_benchmark_r2(key,expected_size):
    req=urllib.request.Request(_r2_url("HEAD",key,180),method="HEAD")
    with urllib.request.urlopen(req,timeout=30) as response:
        length=response.headers.get("Content-Length")
        if response.status!=200 or str(length)!=str(expected_size):
            raise RuntimeError("R2 no confirmó la integridad del tamaño del video")
    return True


def _delete_benchmark_r2(key):
    req=urllib.request.Request(_r2_url("DELETE",key,180),method="DELETE")
    with urllib.request.urlopen(req,timeout=30) as response:
        if response.status not in (200,202,204):
            raise RuntimeError("R2 no confirmó la eliminación de la copia temporal")
    return True


def _r2_video_benchmark(job_id,filename):
    with _PROGRESS_LOCK:
        job=_PROGRESS_JOBS[job_id]
        expected=int(job["size"])
    key="clinical-temp/speed-test/"+secrets.token_hex(24)+".mp4"
    began=time.monotonic()
    try:
        _progress_set(job_id,stage="subiendo_r2",r2_started=began)
        _upload_r2(filename,key,"video/mp4",_upload_progress_hook(job_id))
        _progress_set(job_id,stage="verificando_r2",r2_finished=time.monotonic())
        _verify_benchmark_r2(key,expected)
        _progress_set(job_id,stage="eliminando_copia",r2_verified=True)
        _delete_benchmark_r2(key)
        _progress_set(job_id,stage="complete",r2_deleted=True,
                      r2_elapsed_seconds=round(time.monotonic()-began,2))
    except Exception as exc:
        # Never return raw provider errors, signed URLs or patient identifiers.
        _progress_set(job_id,stage="error",error="No se completó la subida, verificación o eliminación en R2")
        try:
            _delete_benchmark_r2(key)
            _progress_set(job_id,r2_deleted=True)
        except Exception:
            # R2 7-day lifecycle is still configured and mandatory.
            pass
    finally:
        try:os.unlink(filename)
        except OSError:pass


class VideoProgressStart(BaseModel):
    size_bytes:int
    confirmed_patient:bool=False
    upload_consent:bool=False


@app.post("/api/clinical-delivery/patients/{pid}/video-speed-test/start")
def video_speed_start(pid:int,data:VideoProgressStart,db=core.Depends(core.get_db),
                      user=core.Depends(core.current_user)):
    if not _setup()["ready_r2"]:
        raise core.HTTPException(503,"Cloudflare R2 privado y su borrado a 7 días deben estar configurados")
    _patient(db,pid)
    _linked_patient(pid)
    if not data.confirmed_patient or not data.upload_consent:
        raise core.HTTPException(400,"Confirma ficha correcta y autorización para la subida temporal")
    if not (1024<=data.size_bytes<=LIMIT_VIDEO):
        raise core.HTTPException(413,"Solo MP4 de 1 KB a 550 MiB")
    with _PROGRESS_LOCK:
        now=time.monotonic()
        for jid,job in list(_PROGRESS_JOBS.items()):
            if now-job["created"]>3600 and job.get("stage") in ("complete","error","preparando"):
                del _PROGRESS_JOBS[jid]
        if len(_PROGRESS_JOBS)>=_PROGRESS_MAX:
            raise core.HTTPException(429,"Hay demasiadas pruebas activas; finaliza la anterior")
        if any(job["pid"]==pid and job["stage"] not in ("complete","error") for job in _PROGRESS_JOBS.values()):
            raise core.HTTPException(409,"Ya existe una subida activa para esta ficha")
        job_id=secrets.token_urlsafe(24)
        _PROGRESS_JOBS[job_id]={"pid":pid,"mode":"velocidad","size":data.size_bytes,
                               "stage":"preparando","created":now,"local_bytes":0,
                               "r2_bytes":0,"r2_verified":False,"r2_deleted":False}
    return {"ok":True,"job_id":job_id,"max_bytes":LIMIT_VIDEO,
            "note":"Mide subida a R2, verifica bytes y borra la copia; nunca envía WhatsApp."}


@app.get("/api/clinical-delivery/patients/{pid}/video-speed-test/{job_id}")
def video_speed_status(pid:int,job_id:str,user=core.Depends(core.current_user)):
    with _PROGRESS_LOCK:
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,40}",job_id) or (
            job_id not in _PROGRESS_JOBS or _PROGRESS_JOBS[job_id]["pid"]!=pid):
            raise core.HTTPException(404,"Prueba no disponible")
    return _progress_snapshot(job_id)


@app.post("/api/clinical-delivery/patients/{pid}/video-speed-test/{job_id}/upload")
async def video_speed_upload(pid:int,job_id:str,request:Request,
                              user=core.Depends(core.current_user)):
    if "video/mp4" not in request.headers.get("content-type","").lower():
        raise core.HTTPException(415,"Solo se aceptan archivos MP4")
    with _PROGRESS_LOCK:
        job=_PROGRESS_JOBS.get(job_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,40}",job_id) or not job or job["pid"]!=pid:
            raise core.HTTPException(404,"Prueba inexistente")
        if job["stage"]!="preparando":
            raise core.HTTPException(409,"Esta prueba ya fue iniciada")
        job["stage"]="recibiendo_archivo"
        size=int(job["size"])
    tmp=None
    received=0
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_speed_video_",suffix=".mp4",delete=False) as out:
            tmp=out.name
            async for chunk in request.stream():
                received+=len(chunk)
                if received>size or received>LIMIT_VIDEO:
                    raise core.HTTPException(413,"Video más grande de lo declarado")
                out.write(chunk)
                _progress_set(job_id,local_bytes=received)
        if received!=size:
            raise core.HTTPException(400,"La copia local quedó incompleta")
        with open(tmp,"rb") as check:
            header=check.read(24)
        if b"ftyp" not in header or len(header)<24:
            raise core.HTTPException(415,"El archivo no parece MP4")
        _progress_set(job_id,stage="preparando_r2")
        # Background thread handles cloud transfer; this request waits for its
        # final outcome, while browser separately polls progress through GET.
        await asyncio.to_thread(_r2_video_benchmark,job_id,tmp)
        tmp=None
        result=_progress_snapshot(job_id)
        if result["stage"]!="complete":
            raise core.HTTPException(502,result.get("error") or "Falló la prueba R2")
        return result
    except Exception:
        _progress_set(job_id,stage="error",error="La prueba no terminó correctamente")
        raise
    finally:
        if tmp:
            try:os.unlink(tmp)
            except OSError:pass


# iPhone compatibility diagnostics: read-only original MP4 and synthetic R2
# byte-range probe. No real MP4 bytes are uploaded, transcoded, or exposed.
def _mp4_atom_details(filename):
    """Inspect MP4 box structure with bounded reads; no codec conversion."""
    path=Path(filename)
    size=path.stat().st_size
    if size<32:
        raise ValueError("MP4 demasiado pequeño")
    boxes=[]
    moov=None
    ftyp=False
    with open(path,"rb") as media:
        offset=0
        for _ in range(1024):
            if offset+8>size:
                break
            media.seek(offset)
            head=media.read(16)
            if len(head)<8:
                break
            n=int.from_bytes(head[:4],"big")
            kind=head[4:8]
            header=8
            if n==1:
                if len(head)<16:
                    break
                n=int.from_bytes(head[8:16],"big")
                header=16
            elif n==0:
                n=size-offset
            if n<header or offset+n>size:
                break
            if kind==b"ftyp":
                ftyp=True
            if kind==b"moov":
                moov=(offset,n,header)
            if kind in (b"mdat",b"moov",b"ftyp"):
                boxes.append((kind.decode("ascii","replace"),offset,n))
            offset+=n
            if offset>=size:
                break
        if not ftyp:
            raise ValueError("No se encontró cabecera MP4 válida")
        if not moov:
            return {"container":"MP4","moov_found":False,
                    "metadata_before_video":False,"codecs":[],
                    "iphone_codec_hint":"unknown",
                    "recommendation":"No se encontró el índice moov; revisar MP4 original"}
        moov_start,moov_bytes,header=moov
        max_probe=12*1024*1024
        if moov_bytes>max_probe:
            return {"container":"MP4","moov_found":True,
                    "metadata_before_video":moov_start<next((pos for k,pos,_ in boxes if k=="mdat"),size),
                    "codecs":[],"iphone_codec_hint":"unknown",
                    "recommendation":"Índice MP4 grande; verificar con ffprobe en PC"}
        media.seek(moov_start)
        moov_data=media.read(moov_bytes)
    found=set()
    parents={b"moov",b"trak",b"mdia",b"minf",b"stbl"}
    def walk(start,end,depth):
        if depth>8:
            return
        pos=start
        checked=0
        while pos+8<=end and checked<2048:
            checked+=1
            length=int.from_bytes(moov_data[pos:pos+4],"big")
            typ=moov_data[pos+4:pos+8]
            header_len=8
            if length==1:
                if pos+16>end:
                    break
                length=int.from_bytes(moov_data[pos+8:pos+16],"big")
                header_len=16
            elif length==0:
                length=end-pos
            if length<header_len or pos+length>end:
                break
            content=pos+header_len
            end_pos=pos+length
            if typ==b"stsd" and content+8<=end_pos:
                count=min(int.from_bytes(moov_data[content+4:content+8],"big"),24)
                entry=content+8
                for _ in range(count):
                    if entry+8>end_pos:
                        break
                    entry_size=int.from_bytes(moov_data[entry:entry+4],"big")
                    if entry_size<8 or entry+entry_size>end_pos:
                        break
                    fourcc=moov_data[entry+4:entry+8].decode("ascii","replace")
                    if re.fullmatch(r"[a-zA-Z0-9 ]{4}",fourcc):
                        found.add(fourcc.strip())
                    entry+=entry_size
            elif typ in parents:
                walk(content,end_pos,depth+1)
            pos=end_pos
    if len(moov_data)>=header+8:
        walk(header,len(moov_data),0)
    codecs=sorted(found)
    video_entries={"avc1","avc3","hvc1","hev1","mp4v","mjpg","jpeg","mjp2","av01","vp09","s263"}
    supported={"avc1","avc3","hvc1","hev1"}
    videos=set(codecs)&video_entries
    if not videos:
        hint="unknown"
    elif videos<=supported:
        hint="likely_compatible"
    else:
        hint="possible_unsupported_codec"
    mdat_offset=next((pos for k,pos,_ in boxes if k=="mdat"),size)
    faststart=moov_start<mdat_offset
    if hint=="possible_unsupported_codec":
        next_step="Códec posiblemente no compatible con Safari; evaluar copia de reproducción H.264 sin tocar original"
    elif not faststart:
        next_step="Índice moov al final; Safari necesita rangos HTTP para buscarlo, valorar faststart"
    else:
        next_step="Estructura compatible en principio; verificar rangos R2 y perfil del códec"
    return {"container":"MP4","moov_found":True,"metadata_before_video":faststart,
            "codecs":codecs,"iphone_codec_hint":hint,"recommendation":next_step}


def _r2_synthetic_range_206():
    """Probe HTTP 206 with 2 synthetic bytes; always delete temporary R2 object."""
    if not _setup()["ready_r2"]:
        return {"status":"not_configured"}
    key="clinical-temp/self-test/ios-range-"+secrets.token_hex(16)+".bin"
    data=b"DRREVELO_RANGE_TEST_SYNTHETIC_"+secrets.token_bytes(96)
    name=None
    uploaded=False
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_ios_range_",suffix=".bin",delete=False) as tmp:
            name=tmp.name
            tmp.write(data)
        _upload_r2(name,key,"application/octet-stream")
        uploaded=True
        signed=_r2_url("GET",key,180)
        req=urllib.request.Request(signed,method="GET",
                                   headers={"Range":"bytes=0-1"})
        with urllib.request.urlopen(req,timeout=20) as response:
            status=int(response.status)
            content_range=response.headers.get("Content-Range","")
            chunk=response.read(3)
        good=(status==206 and chunk==data[:2] and
              content_range.lower()==f"bytes 0-1/{len(data)}")
        return {"status":"ok" if good else "incompatible",
                "range_206":good}
    except (OSError,TimeoutError,ValueError,urllib.error.URLError):
        return {"status":"unavailable"}
    finally:
        if uploaded:
            try:
                _delete_benchmark_r2(key)
            except Exception:
                pass  # 7-day lifecycle covers unexpected Cloudflare outages.
        if name:
            try:os.unlink(name)
            except OSError:pass


@app.post("/api/clinical-delivery/patients/{pid}/archived-video/{video_id}/iphone-diagnostic")
async def archived_iphone_diagnostic(pid:int,video_id:str,
                                     db=core.Depends(core.get_db),
                                     user=core.Depends(core.current_user)):
    if not re.fullmatch(r"[0-9a-f]{32}",video_id):
        raise core.HTTPException(400,"Identificador de video inválido")
    _patient(db,pid)
    clinical_id,_,conn=_linked_patient(pid)
    conn.close()
    from clinical_video_library import _row_by_id,_local_file
    row=_row_by_id(video_id,clinical_id)
    media=_local_file(row)
    try:
        fmt=await asyncio.to_thread(_mp4_atom_details,media)
    except (OSError,ValueError):
        fmt={"container":"MP4","moov_found":False,"metadata_before_video":False,
             "codecs":[],"iphone_codec_hint":"unknown",
             "recommendation":"No se pudo analizar la estructura; revisar el archivo MP4 en Recepción"}
    range_result=await asyncio.to_thread(_r2_synthetic_range_206)
    return {"ok":True,"codec":fmt["codecs"],
            "moov_found":fmt["moov_found"],
            "metadata_before_video":fmt["metadata_before_video"],
            "iphone_codec_hint":fmt["iphone_codec_hint"],
            "r2_range_status":range_result["status"],
            "r2_range_206":bool(range_result.get("range_206",False)),
            "recommendation":fmt["recommendation"],
            "faststart_tool_available":bool(_faststart_ffmpeg_path()),
            "faststart_preparation_needed":bool(fmt["moov_found"] and not fmt["metadata_before_video"]),
            "no_video_upload":True,"no_whatsapp":True}


# Remux an independent temporary delivery copy for iPhone without changing
# compressed audio/video streams. Never mutate the archived diagnostic original.
# If FFmpeg is unavailable or verification fails, fail before any R2 or Meta call.
def _faststart_ffmpeg_path():
    candidates=[
        shutil.which("ffmpeg"),
        str(ROOT/"tools"/"ffmpeg.exe"),
        str(ROOT/"bin"/"ffmpeg.exe"),
        str(Path(core.DATA_DIR)/"tools"/"ffmpeg.exe"),
    ]
    # WinGet portable installs link into the *user's* app-local location;
    # the running launcher may have a stale PATH even after installation.
    if os.name=="nt":
        local=os.environ.get("LOCALAPPDATA","")
        if local:
            win=Path(local)/"Microsoft"/"WinGet"
            candidates.append(str(win/"Links"/"ffmpeg.exe"))
            packages=win/"Packages"
            if packages.is_dir():
                for root in packages.glob("Gyan.FFmpeg_*"):
                    if root.is_dir():
                        for p in root.glob("ffmpeg-*/bin/ffmpeg.exe"):
                            candidates.append(str(p))
                        candidates.append(str(root/"bin"/"ffmpeg.exe"))
        system=os.environ.get("ProgramFiles","")
        if system:
            candidates.append(str(Path(system)/"WinGet"/"Links"/"ffmpeg.exe"))
    for item in candidates:
        if not item:
            continue
        try:
            binary=Path(item).resolve()
            if binary.is_file() and binary.stat().st_size>0:
                return str(binary)
        except OSError:
            continue
    return None


# FFmpeg installation is an EXPLICIT, local-machine user action.
# Windows package ID/version/source are fixed (never supplied by HTTP request).
# Existing patient data, R2, WhatsApp and appointment workers are untouched.
_FFMPEG_SETUP_LOCK=threading.Lock()
_FFMPEG_SETUP={"state":"idle","detail":""}
_FFMPEG_WINGET_PACKAGE="Gyan.FFmpeg"
_FFMPEG_WINGET_VERSION="9.0.2"


def _clinical_install_local_only(request):
    if os.name!="nt":
        raise core.HTTPException(400,"Esta instalación solo se admite desde Recepción en Windows")
    remote=str(getattr(getattr(request,"client",None),"host","") or "")
    if remote not in ("127.0.0.1","::1","::ffff:127.0.0.1"):
        raise core.HTTPException(403,"La instalación de programas solo se permite desde la PC local de Recepción")


def _clinical_find_winget():
    paths=[shutil.which("winget")]
    local=os.environ.get("LOCALAPPDATA","")
    if local:
        paths.append(str(Path(local)/"Microsoft"/"WindowsApps"/"winget.exe"))
    for item in paths:
        if item:
            try:
                p=Path(item).resolve()
                if p.is_file() and p.stat().st_size>0:
                    return str(p)
            except OSError:
                pass
    return None


def _clinical_install_ffmpeg_winget():
    """User-initiated WinGet install. No arbitrary commands and no patient bytes."""
    global _FFMPEG_SETUP
    cmd=_clinical_find_winget()
    if not cmd:
        with _FFMPEG_SETUP_LOCK:
            _FFMPEG_SETUP={"state":"error",
                "detail":"WinGet no está disponible. Instala App Installer de Microsoft y vuelve a intentar."}
        return
    try:
        run=subprocess.run(
            [cmd,"install","--exact","--id",_FFMPEG_WINGET_PACKAGE,
             "--version",_FFMPEG_WINGET_VERSION,"--source","winget",
             "--scope","user","--silent","--accept-source-agreements",
             "--accept-package-agreements","--disable-interactivity"],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=420,check=False,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        candidate=_faststart_ffmpeg_path()
        if run.returncode!=0 or not candidate:
            raise RuntimeError("WinGet no confirmó la instalación o Windows aún no encuentra FFmpeg")
        verify=subprocess.run([candidate,"-version"],stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                              timeout=15,check=False,
                              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if verify.returncode!=0:
            raise RuntimeError("El FFmpeg instalado no pasó la comprobación")
        with _FFMPEG_SETUP_LOCK:
            _FFMPEG_SETUP={"state":"ready","detail":"FFmpeg instalado y verificado. Puedes ejecutar de nuevo el diagnóstico."}
    except (OSError,subprocess.SubprocessError,RuntimeError):
        with _FFMPEG_SETUP_LOCK:
            _FFMPEG_SETUP={"state":"error","detail":
                "Windows no pudo completar la instalación silenciosa. Usa WinGet o el enlace oficial de FFmpeg."}


@app.post("/api/clinical-delivery/ffmpeg/install")
def install_clinical_ffmpeg(request:Request,background_tasks:BackgroundTasks,
                           user=core.Depends(core.current_user)):
    _clinical_install_local_only(request)
    with _FFMPEG_SETUP_LOCK:
        if _FFMPEG_SETUP["state"]=="running":
            return {"ok":True,"state":"running","message":"La instalación continúa"}
        if _faststart_ffmpeg_path():
            return {"ok":True,"state":"ready","message":"FFmpeg ya está disponible"}
        if not _clinical_find_winget():
            raise core.HTTPException(503,
                "WinGet no está disponible. Instala App Installer de Microsoft o FFmpeg desde el sitio oficial")
        _FFMPEG_SETUP.update(state="running",detail="Windows está instalando FFmpeg desde WinGet")
    background_tasks.add_task(_clinical_install_ffmpeg_winget)
    return {"ok":True,"state":"running",
            "message":"Instalación iniciada en esta PC; no se envía ningún documento"}


@app.get("/api/clinical-delivery/ffmpeg/status")
def clinical_ffmpeg_setup_status(request:Request,
                                 user=core.Depends(core.current_user)):
    _clinical_install_local_only(request)
    with _FFMPEG_SETUP_LOCK:
        state=_FFMPEG_SETUP["state"]
        detail=_FFMPEG_SETUP["detail"]
    available=bool(_faststart_ffmpeg_path())
    if available and state!="running":
        state="ready"
        detail="FFmpeg disponible en Recepción"
    return {"ok":True,"state":state,"available":available,"detail":detail}


def _delivery_faststart_copy(original):
    """Return (path_for_upload, temporary_path_or_None), fail closed.

    -c copy guarantees the video/audio codec payload is NOT re-encoded.
    +faststart moves moov metadata before mdat for Safari progressive loading.
    Source never modified; private temporary derivative is removed after use.
    """
    original=Path(original).resolve(strict=True)
    source_meta=_mp4_atom_details(original)
    if not source_meta["moov_found"]:
        raise RuntimeError("El MP4 no contiene un índice moov válido")
    if source_meta["metadata_before_video"]:
        return original,None
    if source_meta["iphone_codec_hint"]=="possible_unsupported_codec":
        raise RuntimeError("Códec no compatible; no transformar video diagnóstico automáticamente")
    executable=_faststart_ffmpeg_path()
    if not executable:
        raise RuntimeError("Falta FFmpeg en Recepción para preparar la copia compatible con iPhone")
    size=original.stat().st_size
    temp_dir=Path(core.DATA_DIR).resolve()/"clinical_delivery_tmp"
    temp_dir.mkdir(parents=True,exist_ok=True)
    try:
        temp_dir.chmod(0o700)
    except OSError:
        pass
    # Keep enough disk for a full second copy plus margin. No R2 cost yet.
    free=shutil.disk_usage(temp_dir).free
    if free<size+max(128*1024*1024,int(size*0.08)):
        raise RuntimeError("Espacio libre insuficiente para crear copia temporal sin alterar el original")
    target=None
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_ios_faststart_",suffix=".mp4",
                                         dir=str(temp_dir),delete=False) as tmp:
            target=Path(tmp.name)
        cmd=[executable,"-hide_banner","-nostdin","-loglevel","error",
             "-y","-i",str(original),"-map","0","-c","copy",
             "-movflags","+faststart",str(target)]
        completed=subprocess.run(cmd,stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                                 timeout=600,check=False)
        if completed.returncode!=0:
            raise RuntimeError("FFmpeg no pudo preparar la copia sin recodificar")
        if not target.is_file() or not 1024<target.stat().st_size<=LIMIT_VIDEO:
            raise RuntimeError("Copia MP4 temporal inválida o superior al límite clínico")
        output_meta=_mp4_atom_details(target)
        if (not output_meta["moov_found"] or not output_meta["metadata_before_video"]
              or set(output_meta["codecs"])!=set(source_meta["codecs"])):
            raise RuntimeError("La copia temporal no conservó la estructura de video esperada")
        return target,target
    except Exception:
        if target:
            try:target.unlink()
            except OSError:pass
        raise


# Real clinical video test: guarded by verified Reception↔Historia patient link,
# local archived video ownership, two explicit user confirmations and preapproved
# operator TEST PHONE only. Does NOT enable patient live sends.
_LAST_REAL_VIDEO_TEST=0.0
_REAL_VIDEO_TEST_COOLDOWN=300


class ArchivedVideoTestRequest(BaseModel):
    phone:str
    identity_confirmed:bool=False
    patient_authorized_staff_delivery:bool=False


def _send_archived_video_to_test_phone(job_id,source,patient_id,video_id,phone,username):
    with _PROGRESS_LOCK:
        job=_PROGRESS_JOBS[job_id]
        expected=int(job["size"])
    now=datetime.now(TZ)
    expiry_dt=now+timedelta(days=7)
    key="clinical-temp/authorized-test/"+secrets.token_hex(24)+".mp4"
    meta_attempted=False
    uploaded=False
    prepared_tmp=None
    try:
        _progress_set(job_id,stage="preparando_iphone")
        ready_source,prepared_tmp=_delivery_faststart_copy(source)
        expected=Path(ready_source).stat().st_size
        _progress_set(job_id,size=expected,local_bytes=expected,prepared_faststart=bool(prepared_tmp))
        _progress_set(job_id,stage="subiendo_r2",r2_started=time.monotonic())
        _upload_r2(str(ready_source),key,"video/mp4",_upload_progress_hook(job_id))
        uploaded=True
        _progress_set(job_id,stage="verificando_r2",r2_finished=time.monotonic())
        _verify_benchmark_r2(key,expected)
        _progress_set(job_id,stage="preparando_enlace",r2_verified=True)
        signed=_r2_url("GET",key,604800)
        short=_short_r2_link(signed,expiry_dt)
        # Record ambiguity before invoking Meta. A failed response may still
        # mean Meta accepted the message. Never automatically retry.
        meta_attempted=True
        _progress_set(job_id,stage="enviando_whatsapp")
        message_id=_send_template(
            phone,"PACIENTE DE PRUEBA","receta",
            expiry_dt.strftime("%d/%m/%Y a las %H:%M"),
            short,label_override="VIDEO CLINICO AUTORIZADO",test_mode=True
        )
        _progress_set(job_id,stage="complete",whatsapp_accepted=True,
                      expires_at=expiry_dt.isoformat())
        try:
            _audit(patient_id,"video",video_id,message_id,expiry_dt.isoformat(),
                   username)
        except Exception:
            # A local audit failure must not falsely claim the already accepted
            # message failed and tempt a second send.
            _progress_set(job_id,audit_warning=True)
    except Exception:
        if not meta_attempted:
            # No WhatsApp call occurred: remove the private R2 copy if possible.
            try:
                _delete_benchmark_r2(key)
                _progress_set(job_id,r2_deleted=True)
            except Exception:
                pass
            error=("Falta FFmpeg en Recepción para preparar la copia compatible. "
                   "No se envió WhatsApp." if not _faststart_ffmpeg_path()
                   else "No se pudo preparar o verificar la copia iPhone. No se envió WhatsApp.")
        else:
            # Keep the link if Meta's result is ambiguous: the recipient could
            # still receive it. Automatic R2 lifecycle removes it after 7 days.
            error="Meta no confirmó la aceptación. Comprueba tu WhatsApp antes de repetir."
        _progress_set(job_id,stage="error",error=error)
    finally:
        # Remove only the temporary remux. The archived source stays unchanged.
        if prepared_tmp:
            try:Path(prepared_tmp).unlink()
            except OSError:pass


@app.post("/api/clinical-delivery/patients/{pid}/archived-video/{video_id}/send-to-test-phone")
async def send_archived_video_test(pid:int,video_id:str,data:ArchivedVideoTestRequest,
                                   background_tasks:BackgroundTasks,
                                   db=core.Depends(core.get_db),
                                   user=core.Depends(core.current_user)):
    global _LAST_REAL_VIDEO_TEST
    if not _setup()["ready_test"]:
        raise core.HTTPException(503,"Pruebas de WhatsApp o R2 no configuradas")
    if not data.identity_confirmed or not data.patient_authorized_staff_delivery:
        raise core.HTTPException(400,"Verifica ficha correcta y autorización del paciente para enviar a este número")
    if not re.fullmatch(r"[0-9a-f]{32}",video_id):
        raise core.HTTPException(400,"Identificador de videocistoscopía inválido")
    raw=re.sub(r"\D","",str(data.phone or ""))
    if len(raw)==10 and raw.startswith("09"):
        raw="593"+raw[1:]
    allow=re.sub(r"\D","",str(_clinical_setting("WHATSAPP_TEST_PHONE") or core.WHATSAPP_TEST_PHONE or ""))
    if len(allow)==10 and allow.startswith("09"):
        allow="593"+allow[1:]
    if not re.fullmatch(r"5939\d{8}",raw) or not hmac.compare_digest(raw,allow):
        raise core.HTTPException(403,"Solo se permite el WhatsApp configurado como número de prueba")
    _patient(db,pid)
    clinical_id,_,conn=_linked_patient(pid)
    conn.close()
    from clinical_video_library import _row_by_id, _local_file
    row=_row_by_id(video_id,clinical_id)  # must belong to VERIFIED patient chart
    path=_local_file(row)
    # Fail before reserving a job or sending clinical bytes when faststart is
    # required but the trusted local remux tool is not installed.
    try:
        meta=_mp4_atom_details(path)
    except (OSError,ValueError):
        raise core.HTTPException(415,"Video local no tiene estructura MP4 válida")
    if not meta["moov_found"]:
        raise core.HTTPException(415,"Índice MP4 no disponible; no se enviará el original")
    if (not meta["metadata_before_video"] and not _faststart_ffmpeg_path()):
        raise core.HTTPException(503,
            "Falta FFmpeg en Recepción. No se ha subido ni enviado el video; instala FFmpeg para preparar copia faststart.")
    if meta["iphone_codec_hint"]=="possible_unsupported_codec":
        raise core.HTTPException(415,"Códec posiblemente incompatible con iPhone; requiere revisión antes de enviar")
    size=int(row["size_bytes"])
    if not (1024<=size<=LIMIT_VIDEO):
        raise core.HTTPException(413,"Solo videocistoscopías de hasta 550 MiB")
    with _PROGRESS_LOCK:
        now_m=time.monotonic()
        if now_m-_LAST_REAL_VIDEO_TEST<_REAL_VIDEO_TEST_COOLDOWN:
            raise core.HTTPException(429,"Ya se inició un envío clínico de prueba; espera cinco minutos antes de otro")
        for jid,j in list(_PROGRESS_JOBS.items()):
            if now_m-j["created"]>3600 and j["stage"] in ("complete","error","preparando"):
                del _PROGRESS_JOBS[jid]
        if len(_PROGRESS_JOBS)>=_PROGRESS_MAX:
            raise core.HTTPException(429,"Demasiadas transferencias activas")
        if any(j["pid"]==pid and j["stage"] not in ("complete","error") for j in _PROGRESS_JOBS.values()):
            raise core.HTTPException(409,"Ya hay una transferencia activa para esta ficha")
        job_id=secrets.token_urlsafe(24)
        _PROGRESS_JOBS[job_id]={"pid":pid,"mode":"envio_prueba","size":size,
                               "stage":"preparando","created":now_m,"local_bytes":size,
                               "r2_bytes":0,"r2_verified":False,
                               "r2_deleted":False,"whatsapp_accepted":False}
        _LAST_REAL_VIDEO_TEST=now_m
    # Start after HTTP response; the UI uses the opaque job id to monitor
    # transfer and the single Meta attempt without blocking Reception.
    # No names, phones or signed URLs are returned via status or stored in Neon.
    username=str(getattr(user,"username","recepcion"))
    background_tasks.add_task(_send_archived_video_to_test_phone,
                              job_id,path,pid,video_id,raw,username)
    return {"ok":True,"job_id":job_id,
            "note":"Subida autorizada iniciada; el estado no confirma envío hasta Meta."}


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
    stage = "preparación del PDF ficticio"
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_synthetic_test_",suffix=".pdf",delete=False) as tmp:
            temp_name=tmp.name
            pdf=_test_pdf()
            tmp.write(pdf)
        stage = "subida temporal a R2"
        _upload_r2(temp_name, key, "application/pdf")
        url = _r2_url("GET", key, 604800)
        # Verify the R2 object is readable and byte-identical before sending.
        stage = "verificación de descarga R2"
        with urllib.request.urlopen(url, timeout=25) as response:
            downloaded = response.read(len(pdf)+1)
        if not hmac.compare_digest(hashlib.sha256(downloaded).digest(),hashlib.sha256(pdf).digest()):
            raise RuntimeError("El PDF de prueba descargado desde R2 no coincide con el original")
        stage = "creación y prueba del enlace corto"
        short_url=_short_r2_link(url,expires_at)
        stage = "solicitud a Meta"
        message_id = _send_template(raw, "PACIENTE DE PRUEBA", "receta",
            expires_at.strftime("%d/%m/%Y a las %H:%M"), short_url,
            label_override="DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)",test_mode=True)
        return {"ok": True, "sent": True, "message_id": message_id,
                "expires_at": expires_at.isoformat(),
                "note": "Meta aceptó el envío. Confirma personalmente su recepción y descarga en tu iPhone."}
    except (core.WhatsAppError, core.HTTPException):
        raise
    except Exception as exc:
        raise core.HTTPException(
            502,
            "No se completó la prueba durante " + stage +
            ". No se confirmó la aceptación por Meta; verifica WhatsApp antes de repetir.",
        ) from exc
    finally:
        if temp_name:
            try:os.unlink(temp_name)
            except OSError:pass


def _test_video_bytes():
    """Bundled synthetic MP4 (2 seconds, tiny blue/white card); no patient files."""
    import base64
    fixture=ROOT/"clinical_selftest_mp4.b64"
    raw=base64.b64decode(fixture.read_text(encoding="ascii").strip(),validate=True)
    if not (1500<=len(raw)<=20000 and b"ftypisom" in raw[:32] and b"moov" in raw[:1200]):
        raise RuntimeError("El MP4 ficticio de prueba está incompleto")
    return raw


def _test_send_video(phone: str):
    """Operator-initiated synthetic MP4, own approved phone, no clinical records."""
    global _LAST_TEST_SEND
    if not _setup()["ready_test"]:
        raise core.HTTPException(503,"Faltan R2, plantilla aprobada o número de prueba")
    raw=re.sub(r"\D","",str(phone or ""))
    if len(raw)==10 and raw.startswith("09"):
        raw="593"+raw[1:]
    allowed=re.sub(r"\D","",str(_clinical_setting("WHATSAPP_TEST_PHONE") or core.WHATSAPP_TEST_PHONE or ""))
    if len(allowed)==10 and allowed.startswith("09"):
        allowed="593"+allowed[1:]
    if not raw or not hmac.compare_digest(raw,allowed):
        raise core.HTTPException(403,"Solo se permite el celular autorizado como WHATSAPP_TEST_PHONE")
    with _TEST_SEND_LOCK:
        if time.monotonic()-_LAST_TEST_SEND<300:
            raise core.HTTPException(429,"Ya se hizo una prueba. Se admite otra en cinco minutos")
        _LAST_TEST_SEND=time.monotonic()
    now=datetime.now(TZ)
    expires_at=now+timedelta(days=7)
    key="clinical-temp/self-test/"+secrets.token_hex(24)+".mp4"
    tmpname=None
    stage="preparación del MP4 ficticio"
    try:
        payload=_test_video_bytes()
        with tempfile.NamedTemporaryFile(prefix="revelo_synthetic_video_",suffix=".mp4",delete=False) as tmp:
            tmpname=tmp.name
            tmp.write(payload)
        stage="subida de MP4 ficticio a R2"
        _upload_r2(tmpname,key,"video/mp4")
        signed_url=_r2_url("GET",key,604800)
        stage="verificación del MP4 en R2"
        request=urllib.request.Request(signed_url,headers={"Range":"bytes=0-4095"},method="GET")
        with urllib.request.urlopen(request,timeout=25) as resp:
            downloaded=resp.read(len(payload)+1)
        if not hmac.compare_digest(hashlib.sha256(downloaded).digest(),hashlib.sha256(payload).digest()):
            raise RuntimeError("El MP4 descargado no coincide con el archivo ficticio")
        stage="verificación del enlace corto"
        short_url=_short_r2_link(signed_url,expires_at)
        stage="solicitud a Meta"
        # Reuse already approved working DOCUMENT template for the technical
        # video proof; this does NOT prove approval of entrega_video_clinico.
        message_id=_send_template(raw,"PACIENTE DE PRUEBA","receta",
            expires_at.strftime("%d/%m/%Y a las %H:%M"),short_url,
            label_override="VIDEO DE PRUEBA (SIN DATOS MEDICOS)",test_mode=True)
        return {"ok":True,"sent":True,"message_id":message_id,
                "expires_at":expires_at.isoformat(),"video_duration_seconds":2,
                "note":"Meta aceptó la prueba MP4 ficticia con enlace corto. Confirma reproducción en tu iPhone."}
    except core.HTTPException:
        raise
    except Exception as exc:
        raise core.HTTPException(502,"No se completó la prueba de video durante "+stage+
            ". No se confirmó el envío; revisa WhatsApp antes de repetir.") from exc
    finally:
        if tmpname:
            try:os.unlink(tmpname)
            except OSError:pass


def _clinical_test_meta_failure(exc):
    """Safe coded Meta diagnostic; never echo secrets, URLs, phones or provider text."""
    status = getattr(exc, "meta_http_status", None)
    code = getattr(exc, "meta_error_code", None)
    subcode = getattr(exc, "meta_error_subcode", None)
    hints = {
        190: "Revisa el token Meta local y sus permisos.",
        132001: "Revisa que la plantilla aprobada, su idioma y la cuenta Meta coincidan.",
        132000: "Revisa el número y orden de variables de la plantilla.",
        131021: "El número destinatario no puede ser el mismo número remitente.",
        131026: "Meta no pudo entregar al destinatario; revisa elegibilidad y formato.",
    }
    if not isinstance(status, int) or not (100 <= status <= 599):
        return ("No se pudo confirmar la aceptación del mensaje por Meta. "
                "Verifica primero tu WhatsApp antes de volver a probar.")
    parts = [f"HTTP {status}"]
    if isinstance(code, int) and 0 <= code <= 999999:
        parts.append(f"código {code}")
    if isinstance(subcode, int) and 0 <= subcode <= 999999:
        parts.append(f"subcódigo {subcode}")
    hint = hints.get(code, "Comprueba la cuenta, la plantilla, el destinatario y la autorización Meta.")
    return ("Meta rechazó la solicitud de prueba (" + ", ".join(parts) + "). "
            + hint + " No se confirmó un envío.")


class TestDelivery(BaseModel):
    phone: str
    confirmation: str


@app.post("/api/clinical-delivery/send-self-test")
async def delivery_self_test(data: TestDelivery, user=core.Depends(core.current_user)):
    if data.confirmation != "ENVIAR PRUEBA":
        raise core.HTTPException(400, "Confirma explícitamente ENVIAR PRUEBA")
    try:
        return await asyncio.to_thread(_test_send,data.phone)
    except core.WhatsAppError as exc:
        raise core.HTTPException(502, _clinical_test_meta_failure(exc)) from exc


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


def _meta_readonly_diagnostic():
    """Two manual GET-only Graph probes. No messages, R2, Neon or patient access.

    Never return token, phone, provider prose, request URLs or Graph identity.
    A successful metadata GET does not prove permission to send messages.
    """
    import urllib.error
    cfg = _clinical_settings()
    token = cfg["WHATSAPP_CLINICAL_ACCESS_TOKEN"]
    graph = cfg["WHATSAPP_GRAPH_VERSION"] or core.WHATSAPP_GRAPH_VERSION
    phone_id = cfg["WHATSAPP_PHONE_NUMBER_ID"] or core.WHATSAPP_PHONE_NUMBER_ID
    if not token or not re.fullmatch(r"v[0-9]{2,3}[.][0-9]+", graph or "") or not re.fullmatch(r"[0-9]{8,32}", phone_id or ""):
        raise core.HTTPException(503, "Configura el token clínico, versión Graph e identificador del número")
    base = "https://graph.facebook.com/" + graph
    probes = (
        ("token_identity", base + "/me?fields=id"),
        ("phone_metadata", base + "/" + phone_id + "?fields=id,display_phone_number"),
    )
    output = {}
    headers = {"Authorization":"Bearer "+token,
               "Accept":"application/json",
               "User-Agent":"Recepcion-Revelo-Clinical-ReadOnly/1.0"}
    for name, url in probes:
        try:
            req = urllib.request.Request(url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                data = json.loads(response.read(4096).decode("utf-8"))
            output[name] = {"ok":bool(isinstance(data,dict) and data.get("id"))}
        except urllib.error.HTTPError as exc:
            # Meta can include numbers, message text, URLs or provider internals.
            # Only bounded numeric status/codes go back to the local operator.
            try:
                body = json.loads(exc.read(4096).decode("utf-8"))
                error = body.get("error", {}) if isinstance(body,dict) else {}
                if not isinstance(error,dict):
                    error = {}
            except (ValueError, UnicodeError, OSError):
                error = {}
            result = {"ok":False, "http_status":int(exc.code)}
            for field, key in (("meta_code", "code"), ("meta_subcode", "error_subcode")):
                number = error.get(key)
                if isinstance(number,int) and 0 <= number <= 999999:
                    result[field] = number
            output[name] = result
        except (urllib.error.URLError, TimeoutError, ValueError, UnicodeError, OSError):
            output[name] = {"ok":False, "network_error":True}
    return {
        "ok":True, "no_message_sent":True, "checks":output,
        "note":"Solo lectura: comprobar identidad del token y metadatos del número. "
               "Esta prueba no confirma permiso de envío ni la entrega en WhatsApp.",
    }


@app.post("/api/clinical-delivery/check-meta")
async def delivery_check_meta(user=core.Depends(core.current_user)):
    return await asyncio.to_thread(_meta_readonly_diagnostic)


@app.post("/api/clinical-delivery/send-self-test-video")
async def delivery_self_test_video(data: TestDelivery, user=core.Depends(core.current_user)):
    if data.confirmation != "ENVIAR PRUEBA":
        raise core.HTTPException(400, "Confirma explícitamente ENVIAR PRUEBA")
    return await asyncio.to_thread(_test_send_video,data.phone)


@app.post("/api/clinical-delivery/check-r2")
async def delivery_check_r2(user=core.Depends(core.current_user)):
    return await asyncio.to_thread(_check_r2)


@app.get("/api/clinical-delivery/status")
def delivery_status(user=core.Depends(core.current_user)):
    return {"ok":True,**_setup(),"ffmpeg_available":bool(_faststart_ffmpeg_path()),"privacy":"private-bucket-presigned-link"}


@app.get("/api/clinical-delivery/patients/{pid}/documents")
def delivery_documents(pid:int,db=core.Depends(core.get_db),user=core.Depends(core.current_user)):
    _patient(db,pid)
    try:
        docs,_,clinical_id=_documents(pid)
        from clinical_video_library import _records
        return {"ok":True,"documents":docs,"videos":_records(clinical_id),**_setup(),"ffmpeg_available":bool(_faststart_ffmpeg_path())}
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


@app.get("/api/clinical-delivery/patients/{pid}/unsigned/{kind}/{doc_id}")
def delivery_unsigned_preview(pid:int,kind:str,doc_id:str,user=core.Depends(core.current_user)):
    data=_unsigned_preview_html(pid,kind,doc_id)
    return Response(data,media_type="text/html; charset=utf-8",headers={
        "Cache-Control":"private, no-store",
        "X-Clinical-Preview-Unsigned":"1",
        "Content-Security-Policy":(
            "default-src 'none'; sandbox; script-src 'none'; connect-src 'none'; "
            "style-src 'unsafe-inline'; img-src data: blob:; "
            "font-src data:; form-action 'none'; base-uri 'none'"
        ),
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
