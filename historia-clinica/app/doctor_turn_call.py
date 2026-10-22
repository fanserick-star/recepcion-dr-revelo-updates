from __future__ import annotations

"""Llamados explícitos desde Historia: evento local para la TV vía LAN.

Sin escritura en waiting_queue, encounters, receipts ni Neon.
Solamente número de turno, ID técnico de cola y marca de revisión.
"""
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

_LOCK = threading.RLock()
MAX_EVENT_AGE_SECONDS = 25
MIN_RECALL_SECONDS = 2.5


def _event_path(root: Path) -> Path:
    return Path(root) / "data" / "tv_llamados" / "last_call.json"


def _read_event(root: Path) -> dict | None:
    try:
        raw = json.loads(_event_path(root).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        age = time.time() - float(raw.get("at_epoch") or 0)
        if age < -3 or age > MAX_EVENT_AGE_SECONDS:
            return None
        if not re.fullmatch(r"[a-f0-9-]{36}", str(raw.get("event_id") or "")):
            return None
        turn = int(raw.get("turn") or 0)
        if turn < 1 or turn > 9999:
            return None
        return {
            "event_id": str(raw["event_id"]),
            "queue_id": str(raw.get("queue_id") or "")[:100],
            "turn": turn,
            "exam_review": raw.get("exam_review") is True,
            "at_epoch": float(raw["at_epoch"]),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return None


def latest(root: Path) -> dict | None:
    # Después de 25 segundos, el evento expira y jamás se reenvía por reconexión.
    with _LOCK:
        return _read_event(root)


def _require_local_action(request: Request) -> None:
    host = str(getattr(getattr(request, "client", None), "host", "") or "").lower()
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(403, "Solo el doctor puede llamar desde su PC.")
    if str(request.headers.get("x-historia-doctor-call") or "") != "1":
        raise HTTPException(403, "Acción de llamado no autorizada.")
    if str(request.headers.get("sec-fetch-site") or "").lower() == "cross-site":
        raise HTTPException(403, "Origen externo no autorizado.")
    origin = str(request.headers.get("origin") or "").strip()
    if origin:
        a, b = urlsplit(origin), urlsplit(str(request.base_url))
        if (a.scheme, a.netloc) != (b.scheme, b.netloc):
            raise HTTPException(403, "Origen no autorizado.")


def _is_review(value) -> bool:
    raw = " ".join(str(value or "").strip().upper().split())
    return raw in {"REVISION DE EXAMENES", "REVISIÓN DE EXÁMENES"}


def install(app, db_factory, root: Path, queue_turn_number, is_procedure):
    @app.post("/api/doctor-turn-call/{queue_id}")
    def doctor_turn_call(queue_id: str, request: Request):
        _require_local_action(request)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", queue_id):
            return JSONResponse({"ok": False, "error": "Turno inválido."}, status_code=400)
        with db_factory() as conn:
            row = conn.execute(
                """SELECT * FROM waiting_queue
                   WHERE id=? AND status IN ('waiting','in_consultation') LIMIT 1""",
                (queue_id,),
            ).fetchone()
            if not row:
                return JSONResponse({"ok": False, "error": "El turno ya no está en espera ni en atención."}, status_code=409)
            if is_procedure(row):
                return JSONResponse({"ok": False, "error": "Los procedimientos no tienen número de turno para la TV."}, status_code=409)
            today = datetime.now().date().isoformat()
            queued_day = str(row["queued_at"] or "")[:10]
            if queued_day and queued_day != today:
                return JSONResponse({"ok": False, "error": "No es un turno del día de hoy."}, status_code=409)
            n = queue_turn_number(conn, queue_id)
            if not n or not (1 <= int(n) <= 9999):
                return JSONResponse({"ok": False, "error": "Este paciente no tiene un número de turno válido."}, status_code=409)
            review = _is_review(row["attention_type"])
        with _LOCK:
            prev = _read_event(root)
            now = time.time()
            if prev and prev["queue_id"] == queue_id and now - prev["at_epoch"] < MIN_RECALL_SECONDS:
                return JSONResponse({"ok": False, "error": "El llamado acaba de enviarse. Evite pulsar varias veces."}, status_code=429)
            event = {
                "event_id": str(uuid.uuid4()),
                "queue_id": queue_id,
                "turn": int(n),
                "exam_review": review,
                "at_epoch": now,
            }
            target = _event_path(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                with temp.open("x", encoding="utf-8") as fd:
                    json.dump(event, fd, ensure_ascii=False)
                    fd.flush()
                    os.fsync(fd.fileno())
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        return JSONResponse({
            "ok": True, "turn": int(n),
            "exam_review": review,
            "delivery": "pending_lan",  # sin prometer que TV reprodujo el sonido
            "message": f"Llamado del turno {int(n)} enviado por LAN; la reproducción en la TV depende de su conexión.",
        })



def queue_button(row, number, is_procedure) -> str:
    """Botón separado de la tarjeta de navegación; nunca dispara Atender."""
    if not number or is_procedure(row):
        return ""
    if str(row["status"] or "") not in {"waiting", "in_consultation"}:
        return ""
    if not str(row["clinical_patient_id"] or ""):
        return ""
    queue_id = str(row["id"] or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", queue_id):
        return ""
    return (
        '<button type="button" class="js-doctor-call" data-queue-id="' +
        queue_id + '" title="Anunciar este turno en la TV, sin iniciar la consulta">' +
        '🔊 Llamar #' + str(int(number)) + '</button>'
    )


def patient_button(db_factory, patient_id, queue_turn_number, is_procedure) -> str:
    """Se muestra al revisar ficha ANTES de pulsar atender; no cambia su estado."""
    with db_factory() as conn:
        rows = conn.execute(
            """SELECT * FROM waiting_queue
               WHERE clinical_patient_id=? AND status IN ('waiting','in_consultation')
               ORDER BY CASE status WHEN 'waiting' THEN 0 ELSE 1 END,
                        queued_at DESC LIMIT 8""", (patient_id,),
        ).fetchall()
        for row in rows:
            if str(row["queued_at"] or "")[:10] != datetime.now().date().isoformat():
                continue
            number = queue_turn_number(conn, str(row["id"]))
            if number:
                button = queue_button(row, number, is_procedure)
                if button:
                    return button
    return ""


def consultation_button(row, turn, patient_id, is_procedure) -> str:
    if row is None:
        return ""
    if str(row["clinical_patient_id"] or "") != str(patient_id):
        return ""
    button = queue_button(row, turn, is_procedure)
    return '<div class="consult-turn-call">' + button + '</div>' if button else ""

# Añadido solo a base() de Historia: NO reemplaza ni oculta el botón INICIO.
CALL_SCRIPT = r"""<style>
.js-doctor-call{border:1px solid #167a9e!important;background:#e8f7ff!important;color:#07577c!important;border-radius:10px!important;padding:10px 13px!important;font-weight:850!important;font-size:14px!important;cursor:pointer!important;white-space:nowrap}
.js-doctor-call:disabled{opacity:.55;cursor:wait!important}
.js-doctor-call.call-repeated{background:#eff7ef!important;color:#13633b!important}
.consult-turn-call{margin-left:auto;align-self:center}
</style><script>
(function(){
 if(window.__doctorTurnCallInstalled)return;
 window.__doctorTurnCallInstalled=true;
 document.addEventListener('click',async ev=>{
  const btn=ev.target.closest?.('.js-doctor-call');
  if(!btn)return;
  ev.preventDefault();ev.stopPropagation();
  if(btn.disabled)return;
  const q=String(btn.dataset.queueId||'');
  if(!q)return;
  btn.disabled=true;
  const original=btn.textContent;
  btn.textContent='Enviando llamado…';
  try{
   const r=await fetch('/api/doctor-turn-call/'+encodeURIComponent(q),{
     method:'POST',headers:{'X-Historia-Doctor-Call':'1','Content-Type':'application/json'},cache:'no-store',
     body:'{}'
   });
   const d=await r.json().catch(()=>({}));
   if(!r.ok||!d.ok)throw new Error(d.error||'No se pudo enviar el llamado.');
   btn.textContent='🔁 Repetir llamado';
   btn.classList.add('call-repeated');
   btn.title='Repetir llamado del turno '+d.turn;
   if(window.showAppToast)window.showAppToast('Turno #'+d.turn+' enviado a Recepción · TV (audio sujeto a conexión).','success');
  }catch(err){
   btn.textContent=original;
   if(window.showAppToast)window.showAppToast(err.message||'Error al llamar.','error');
   else alert(err.message||'Error al llamar.');
  }finally{btn.disabled=false;}
 });
})();
</script>"""
