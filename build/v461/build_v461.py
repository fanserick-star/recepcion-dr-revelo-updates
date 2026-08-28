from pathlib import Path
import hashlib, json, re

ROOT=Path(__file__).resolve().parents[2]
VERSION='4.3.61'
BASE_VERSION='4.3.60'
BASE_SHA='63f5171cc66d04eb82d0b9e2b0dd4c13a4822be1a6cd391c4c75a7b2d5c088a3'
oldroot=ROOT/'updates'/'v460'
parts=sorted(oldroot.glob('app.part*'),key=lambda p:int(p.name.split('part')[-1]))
raw=b''.join(p.read_bytes() for p in parts)
if hashlib.sha256(raw).hexdigest()!=BASE_SHA:
    raise SystemExit('La base v4.3.60 no coincide con la publicada')

s=raw.decode('utf-8')

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: se esperó 1 coincidencia y hubo {n}')
    s=s.replace(old,new,1)

def regex_one(pattern,repl,label):
    global s
    s2,n=re.subn(pattern,repl,s,count=1,flags=re.S)
    if n!=1:
        raise SystemExit(f'{label}: se esperó 1 coincidencia y hubo {n}')
    s=s2

one('APP_VERSION = "4.3.60"','APP_VERSION = "4.3.61"','APP_VERSION')
one("const VERSION='4.3.60';","const VERSION='4.3.61';",'badge version')
one('/v460/overlay.css?v=4.3.60','/v460/overlay.css?v=4.3.61','overlay css cache')
one('/v460/overlay.js?v=4.3.60','/v460/overlay.js?v=4.3.61','overlay js cache')
one('WHATSAPP_AUTO_CITA_AGENDADA = (os.getenv("WHATSAPP_AUTO_CITA_AGENDADA") or "0").strip() == "1"','WHATSAPP_AUTO_CITA_AGENDADA = (os.getenv("WHATSAPP_AUTO_CITA_AGENDADA") or "1").strip() != "0"','auto cita_agendada')
one('WHATSAPP_AUTO_RECORDATORIO_HOY = (os.getenv("WHATSAPP_AUTO_RECORDATORIO_HOY") or "0").strip() == "1"','WHATSAPP_AUTO_RECORDATORIO_HOY = (os.getenv("WHATSAPP_AUTO_RECORDATORIO_HOY") or "1").strip() != "0"','auto recordatorio_hoy')
one('WHATSAPP_APPROVED_CITA_AGENDADA = (os.getenv("WHATSAPP_APPROVED_CITA_AGENDADA") or "0").strip() == "1"','WHATSAPP_APPROVED_CITA_AGENDADA = (os.getenv("WHATSAPP_APPROVED_CITA_AGENDADA") or "1").strip() != "0"','approved cita_agendada')
one('WHATSAPP_APPROVED_RECORDATORIO_HOY = (os.getenv("WHATSAPP_APPROVED_RECORDATORIO_HOY") or "0").strip() == "1"','WHATSAPP_APPROVED_RECORDATORIO_HOY = (os.getenv("WHATSAPP_APPROVED_RECORDATORIO_HOY") or "1").strip() != "0"','approved recordatorio_hoy')
old_js = r"if(template!==\\'recordatorio_cita\\'){alert(\\'Esa plantilla todavía está pendiente de Meta. Por ahora probaremos Confirmación · recordatorio_cita.\\');return}"
new_js = r"if(![\\'recordatorio_cita\\',\\'cita_agendada\\',\\'recordatorio_hoy\\'].includes(template)){alert(\\'Plantilla de prueba no válida.\\');return}"
one(old_js,new_js,'selector prueba Cloud')

helpers = """
WHATSAPP_CLOUD_TEST_TEMPLATES = {"recordatorio_cita", "cita_agendada", "recordatorio_hoy"}


def _whatsapp_cloud_test_parse_source_hash(value: str) -> tuple[str, str]:
    raw = str(value or "")
    if not raw.startswith(WHATSAPP_CLOUD_TEST_PREFIX):
        return "", ""
    rest = raw[len(WHATSAPP_CLOUD_TEST_PREFIX):]
    parts = rest.split(":")
    if len(parts) >= 2 and parts[0] in WHATSAPP_CLOUD_TEST_TEMPLATES:
        return parts[0], parts[-1]
    return "recordatorio_cita", rest


def _whatsapp_cloud_test_source_hash(template_key: str, token: str) -> str:
    return f"{WHATSAPP_CLOUD_TEST_PREFIX}{template_key}:{token}"


def _whatsapp_cloud_test_template_name(template_key: str) -> str:
    if template_key == "cita_agendada":
        return WHATSAPP_TEMPLATE_CITA_AGENDADA
    if template_key == "recordatorio_hoy":
        return WHATSAPP_TEMPLATE_RECORDATORIO_HOY
    return whatsapp_recordatorio_template_name()


def _whatsapp_cloud_test_approved(template_key: str) -> bool:
    if template_key == "cita_agendada":
        return bool(WHATSAPP_APPROVED_CITA_AGENDADA)
    if template_key == "recordatorio_hoy":
        return bool(WHATSAPP_APPROVED_RECORDATORIO_HOY)
    return bool(WHATSAPP_APPROVED_RECORDATORIO_CITA)


def _wa_cita_agendada_allowed(fecha: date, hora: str, created_at: Optional[datetime]) -> bool:
    # No se envía con menos de 24 h ni si ya es el día de confirmación.
    created = created_at or datetime.now()
    try:
        hh, mm = [int(x) for x in str(hora or "00:00")[:5].split(":")]
        appointment_at = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
    except Exception:
        appointment_at = datetime.combine(fecha, datetime.min.time())
    return (appointment_at - created) >= timedelta(hours=24) and created.date() < (fecha - timedelta(days=1))
"""
marker="def _whatsapp_cloud_test_ready() -> tuple[bool, str]:"
if marker not in s:
    raise SystemExit('No se encontró ready Cloud')
s=s.replace(marker,helpers+'\n\n'+marker,1)

regex_one(r"""def _whatsapp_cloud_test_ready\(\) -> tuple\[bool, str\]:.*?(?=\n\ndef _cleanup_old_whatsapp_cloud_tests\(\))""", """def _whatsapp_cloud_test_ready() -> tuple[bool, str]:
    if not WHATSAPP_CLOUD_MODE:
        return False, "WhatsApp Cloud 24/7 está desactivado"
    if not cloud_configured() or not CloudSessionLocal or FORCE_OFFLINE:
        return False, "Neon no está disponible"
    return True, ""
""", 'ready Cloud general')

post_func = """@app.post("/api/whatsapp/cloud-test")
def whatsapp_cloud_test(payload: dict, request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "La prueba solo puede iniciarse desde la PC de Recepción")
    ready, reason = _whatsapp_cloud_test_ready()
    if not ready:
        raise HTTPException(503, reason)
    template_key = str(payload.get("template") or "recordatorio_cita").strip().lower()
    if template_key not in WHATSAPP_CLOUD_TEST_TEMPLATES:
        raise HTTPException(400, "Plantilla de prueba no válida")
    if not _whatsapp_cloud_test_approved(template_key):
        raise HTTPException(409, f"La plantilla {template_key} todavía no está aprobada en la configuración de Recepción")
    phone = confirmafy_phone(str(payload.get("phone") or WHATSAPP_TEST_PHONE or ""))
    if not re.fullmatch(r"\\d{10,15}", phone or ""):
        raise HTTPException(400, "Ingresa un número válido. Ecuador: 09xxxxxxxx o 5939xxxxxxxx.")
    name = re.sub(r"\\s+", " ", str(payload.get("name") or "Prueba").strip())[:60] or "Prueba"
    raw_date = str(payload.get("date") or "").strip()
    raw_time = str(payload.get("time") or "").strip()[:5]
    try:
        test_date = date.fromisoformat(raw_date)
    except Exception:
        raise HTTPException(400, "Selecciona una fecha válida para la prueba")
    if not re.fullmatch(r"(?:[01]\\d|2[0-3]):[0-5]\\d", raw_time):
        raise HTTPException(400, "Selecciona una hora válida para la prueba")
    try:
        hh, mm = [int(x) for x in raw_time.split(":")]
        if datetime(test_date.year, test_date.month, test_date.day, hh, mm) <= datetime.now():
            raise HTTPException(400, "La fecha y hora mostradas en la prueba deben estar en el futuro")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Fecha u hora inválida")
    _cleanup_old_whatsapp_cloud_tests()
    token = secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:22]
    source_hash = _whatsapp_cloud_test_source_hash(template_key, token)
    item = ConfirmafyAgendaItem(nombre=name.upper(), celular=phone, fecha=test_date, hora=raw_time, duracion=20, source_hash=source_hash)
    try:
        with CloudSessionLocal() as cdb:
            cdb.add(item); cdb.commit(); cdb.refresh(item)
            source_id = int(item.id)
    except Exception as exc:
        raise HTTPException(503, f"No se pudo registrar la prueba en Cloud: {str(exc)[:180]}")
    return {"ok": True, "mode": "cloud", "test_id": source_id, "token": token, "to": phone, "template": template_key, "worker_cycle_minutes": 5, "message": "Prueba registrada en Cloud. No se usó ningún token de Meta en esta PC. El worker enviará únicamente la plantilla elegida."}

"""
regex_one(r"""@app\.post\("/api/whatsapp/cloud-test"\)\ndef whatsapp_cloud_test\(.*?(?=@app\.get\("/api/whatsapp/cloud-test/\{test_id\}"\))""",post_func,'POST cloud-test')

status_func = """@app.get("/api/whatsapp/cloud-test/{test_id}")
def whatsapp_cloud_test_status(test_id: int, token: str, user: User = Depends(current_user)):
    ready, reason = _whatsapp_cloud_test_ready()
    if not ready:
        return {"ok": False, "status": "UNAVAILABLE", "status_label": reason, "terminal": True}
    try:
        with CloudSessionLocal() as cdb:
            item = cdb.execute(text(\"\"\"SELECT source_hash FROM public.confirmafy_agenda_items WHERE id=:source_id AND source_hash LIKE :prefix LIMIT 1\"\"\"), {"source_id": int(test_id), "prefix": WHATSAPP_CLOUD_TEST_PREFIX + "%"}).mappings().first()
            if not item:
                return {"ok": False, "status": "CLEANED", "status_label": "Prueba finalizada o vencida", "terminal": True}
            template_key, stored_token = _whatsapp_cloud_test_parse_source_hash(str(item.get("source_hash") or ""))
            if not stored_token or not hmac.compare_digest(stored_token, str(token or "")):
                return {"ok": False, "status": "CLEANED", "status_label": "Prueba finalizada o vencida", "terminal": True}
            template_name = _whatsapp_cloud_test_template_name(template_key)
            event = cdb.execute(text(\"\"\"SELECT status, message_id, created_at, sent_at, delivered_at, read_at, error_text FROM whatsapp_cloud.events WHERE source_type='staged' AND source_id=:source_id AND template_name=:template ORDER BY created_at DESC LIMIT 1\"\"\"), {"source_id": int(test_id), "template": template_name}).mappings().first()
        if not event:
            return {"ok": True, "status": "QUEUED", "status_label": "Esperando al worker Cloud", "terminal": False, "template": template_key}
        st = str(event.get("status") or "").upper()
        label, _tone = _wa_event_display_status(st)
        timestamp = event.get("read_at") or event.get("delivered_at") or event.get("sent_at") or event.get("created_at")
        return {"ok": st not in {"ERROR", "FAILED"}, "status": st, "status_label": label, "terminal": st in {"SENT", "DELIVERED", "READ", "ERROR", "FAILED"}, "message_id": str(event.get("message_id") or ""), "timestamp": timestamp.isoformat() if timestamp else None, "error": str(event.get("error_text") or "")[:240], "template": template_key}
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "status_label": "No se pudo consultar Cloud", "terminal": False, "error": str(exc)[:220]}

"""
regex_one(r"""@app\.get\("/api/whatsapp/cloud-test/\{test_id\}"\)\ndef whatsapp_cloud_test_status\(.*?(?=@app\.delete\("/api/whatsapp/cloud-test/\{test_id\}"\))""",status_func,'GET cloud-test')

finish_func = """@app.delete("/api/whatsapp/cloud-test/{test_id}")
def whatsapp_cloud_test_finish(test_id: int, token: str, user: User = Depends(current_user)):
    if not cloud_configured() or not CloudSessionLocal:
        raise HTTPException(503, "Neon no está disponible")
    try:
        with CloudSessionLocal() as cdb:
            item = cdb.execute(text(\"\"\"SELECT source_hash FROM public.confirmafy_agenda_items WHERE id=:source_id AND source_hash LIKE :prefix LIMIT 1\"\"\"), {"source_id": int(test_id), "prefix": WHATSAPP_CLOUD_TEST_PREFIX + "%"}).mappings().first()
            if item:
                _template_key, stored_token = _whatsapp_cloud_test_parse_source_hash(str(item.get("source_hash") or ""))
                if stored_token and hmac.compare_digest(stored_token, str(token or "")):
                    cdb.execute(text("DELETE FROM public.confirmafy_agenda_items WHERE id=:source_id"), {"source_id": int(test_id)})
                    cdb.commit()
        return {"ok": True, "message": "Prueba técnica finalizada. No se modificó ningún paciente ni cita real."}
    except Exception as exc:
        raise HTTPException(503, f"No se pudo finalizar la prueba: {str(exc)[:180]}")

"""
regex_one(r"""@app\.delete\("/api/whatsapp/cloud-test/\{test_id\}"\)\ndef whatsapp_cloud_test_finish\(.*?(?=@app\.post\("/api/whatsapp/test-message"\))""",finish_func,'DELETE cloud-test')

old_timeline="""        elif not node["approved"]:
            item.update({"status": "META_PENDING", "status_label": "Pendiente de Meta", "tone": "muted", "timestamp": None, "error": ""})
"""
new_timeline="""        elif node["key"] == "cita_agendada" and not _wa_cita_agendada_allowed(fecha, hora, created_at):
            item.update({"status": "SKIPPED_RULE", "status_label": "Omitido por regla", "tone": "muted", "timestamp": None, "error": "", "planned": "No se envía si faltan menos de 24 h o si ya es el día de confirmación"})
        elif not node["approved"]:
            item.update({"status": "META_PENDING", "status_label": "Pendiente de Meta", "tone": "muted", "timestamp": None, "error": ""})
"""
one(old_timeline,new_timeline,'timeline regla 24h')

final=s.encode('utf-8')
app_sha=hashlib.sha256(final).hexdigest()
out=ROOT/'updates'/'v461'
out.mkdir(parents=True,exist_ok=True)
for p in out.glob('app.part*'): p.unlink()
chunks=[]; cur=[]; size=0
for ch in s:
    b=len(ch.encode('utf-8'))
    if cur and size+b>70000:
        chunks.append(''.join(cur)); cur=[ch]; size=b
    else:
        cur.append(ch); size+=b
if cur: chunks.append(''.join(cur))
for i,ch in enumerate(chunks,1): (out/f'app.part{i}').write_text(ch,encoding='utf-8',newline='')
rebuilt=b''.join((out/f'app.part{i}').read_bytes() for i in range(1,len(chunks)+1))
if rebuilt!=final: raise SystemExit('Las partes no reconstruyen el app.py exacto')
manifest={"product":"recepcion-pacientes","version":VERSION,"app_version":VERSION,"runtime_version":VERSION,"launcher_version":"4.3.57-standalone-1","updater_version":"integrado-en-launcher","copy":["ABRIR_RECEPCION.py","app.py","update_manifest.json"]}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(out/'update_manifest.json').write_bytes(manifest_bytes)
(out/'test_v461.py').write_bytes((ROOT/'build'/'v461'/'test_v461.py').read_bytes())
release_meta={"product":"recepcion-pacientes","version":VERSION,"base_version":BASE_VERSION,"base_sha256":BASE_SHA,"app_size":len(final),"app_sha256":app_sha,"parts_count":len(chunks),"part_max_bytes":70000,"manifest_sha256":hashlib.sha256(manifest_bytes).hexdigest()}
(out/'release_meta.json').write_text(json.dumps(release_meta,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='')
print('V461_BUILT',release_meta)
