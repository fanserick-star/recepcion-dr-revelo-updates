from __future__ import annotations
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.18"
APP_SRC = "updates/v4_4_17_continue_attention/app.py"
JS_SRC = "updates/v4_4_17_continue_attention/static/app.js"
INDEX_SRC = "updates/v4_4_17_continue_attention/static/index.html"
OUT = ROOT / "updates/v4_4_18_whatsapp_responses"


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)


def text_file(path: str) -> str:
    return git_bytes(path).decode("utf-8-sig")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


app = text_file(APP_SRC)
js = text_file(JS_SRC)
index = text_file(INDEX_SRC)

assert 'APP_VERSION = "4.4.17"' in app
assert "const VERSION=\\'4.4.17\\';" in app
assert '/static/app.js?v=4.4.17' in index
assert '<section id="config" class="hidden">' in index
assert 'data-section="agenda"' in index

app = app.replace('APP_VERSION = "4.4.17"', 'APP_VERSION = "4.4.18"', 1)
app = app.replace("const VERSION=\\'4.4.17\\';", "const VERSION=\\'4.4.18\\';", 1)

API_BLOCK = r'''

# ---------------------------------------------------------------------------
# v4.4.18 — Bandeja de respuestas de WhatsApp
# ---------------------------------------------------------------------------
# Las respuestas entrantes viven en Neon, dentro de whatsapp_cloud, porque el
# webhook funciona 24/7 aunque la PC esté apagada. La PC solo consulta esta
# bandeja cuando recepción abre Inicio o la sección Respuestas WhatsApp.

def _wa_inbound_table_ready(conn) -> bool:
    try:
        return conn.execute(text("SELECT to_regclass('whatsapp_cloud.inbound_responses')")).scalar() is not None
    except Exception:
        return False


def _wa_cloud_unavailable_payload() -> dict:
    return {
        "available": False,
        "pending": 0,
        "items": [],
        "message": "Las respuestas de WhatsApp necesitan conexión con Neon.",
    }


def _wa_json_row(row) -> dict:
    out = dict(row)
    for key, value in list(out.items()):
        if value is None or isinstance(value, (str, int, float, bool)):
            continue
        try:
            out[key] = value.isoformat()
        except Exception:
            out[key] = str(value)
    return out


def _wa_apply_ok(result: str) -> bool:
    value = str(result or "").strip().upper()
    if not value or value in {"NOT_FOUND", "STALE", "UNKNOWN"}:
        return False
    return not (value.startswith("ERROR") or value.startswith("INVALID"))


@app.get("/api/whatsapp-responses/count")
def whatsapp_responses_count(user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        return _wa_cloud_unavailable_payload()
    try:
        with cloud_engine.connect() as conn:
            if not _wa_inbound_table_ready(conn):
                return {"available": True, "pending": 0, "items": [], "ready": False}
            pending = int(conn.execute(text("""
                SELECT count(*)
                FROM whatsapp_cloud.inbound_responses
                WHERE resolved_at IS NULL AND upper(coalesce(interpretation,''))='REVISAR'
            """)).scalar() or 0)
            return {"available": True, "ready": True, "pending": pending}
    except Exception as exc:
        return {**_wa_cloud_unavailable_payload(), "error": str(exc)[:180]}


@app.get("/api/whatsapp-responses")
def whatsapp_responses_list(scope: str = "review", limit: int = 80, user: User = Depends(current_user)):
    scope = str(scope or "review").strip().lower()
    if scope not in {"review", "all", "resolved"}:
        scope = "review"
    limit = max(1, min(int(limit or 80), 200))
    if FORCE_OFFLINE or cloud_engine is None:
        return _wa_cloud_unavailable_payload()
    try:
        with cloud_engine.connect() as conn:
            if not _wa_inbound_table_ready(conn):
                return {"available": True, "ready": False, "pending": 0, "items": []}
            where = ""
            if scope == "review":
                where = "WHERE resolved_at IS NULL AND upper(coalesce(interpretation,''))='REVISAR'"
            elif scope == "resolved":
                where = "WHERE resolved_at IS NOT NULL"
            rows = conn.execute(text(f"""
                SELECT id,message_id,phone,message_type,raw_text,transcription,media_id,media_mime_type,
                       interpretation,confidence,source_type,source_id,appointment_date,appointment_time,
                       patient_name,match_method,apply_result,received_at,resolved_at,resolved_by,resolution
                FROM whatsapp_cloud.inbound_responses
                {where}
                ORDER BY received_at DESC, id DESC
                LIMIT :limit
            """), {"limit": limit}).mappings().all()
            pending = int(conn.execute(text("""
                SELECT count(*) FROM whatsapp_cloud.inbound_responses
                WHERE resolved_at IS NULL AND upper(coalesce(interpretation,''))='REVISAR'
            """)).scalar() or 0)
            return {"available": True, "ready": True, "pending": pending, "items": [_wa_json_row(r) for r in rows]}
    except Exception as exc:
        return {**_wa_cloud_unavailable_payload(), "error": str(exc)[:180]}


@app.post("/api/whatsapp-responses/{response_id}/resolve")
def whatsapp_response_resolve(response_id: int, payload: dict, user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        raise HTTPException(503, "Se necesita conexión con Neon para resolver esta respuesta")
    action = str((payload or {}).get("action") or "").strip().upper()
    if action not in {"CONFIRMAR", "CANCELAR", "RESUELTO"}:
        raise HTTPException(400, "Acción no válida")
    username = str(getattr(user, "username", "recepcion") or "recepcion")[:80]
    with cloud_engine.begin() as conn:
        if not _wa_inbound_table_ready(conn):
            raise HTTPException(404, "La bandeja de WhatsApp todavía no está disponible")
        row = conn.execute(text("""
            SELECT id,message_id,source_type,source_id,appointment_date,appointment_time,resolved_at
            FROM whatsapp_cloud.inbound_responses
            WHERE id=:id
            FOR UPDATE
        """), {"id": int(response_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Respuesta no encontrada")
        if action == "RESUELTO":
            conn.execute(text("""
                UPDATE whatsapp_cloud.inbound_responses
                SET resolved_at=COALESCE(resolved_at,now()), resolved_by=:user,
                    resolution='RESUELTO', updated_at=now()
                WHERE id=:id
            """), {"id": int(response_id), "user": username})
            return {"ok": True, "action": "RESUELTO"}
        source_type = str(row.get("source_type") or "").strip().lower()
        source_id = int(row.get("source_id") or 0)
        if source_type not in {"appointment", "staged"} or source_id <= 0:
            raise HTTPException(409, "No pude vincular esta respuesta con una cita. Revísala y usa Marcar como resuelto.")
        message_id = f"manual:{int(response_id)}:{int(time.time())}"
        result = str(conn.execute(text("""
            SELECT public.whatsapp_apply_response(:action,:source_type,:source_id,:message_id,:phone) AS result
        """), {
            "action": action,
            "source_type": source_type,
            "source_id": source_id,
            "message_id": message_id,
            "phone": "manual-recepcion",
        }).scalar() or "UNKNOWN")
        if not _wa_apply_ok(result):
            raise HTTPException(409, f"La cita ya cambió o no pudo actualizarse ({result}). Actualiza la bandeja y revísala manualmente.")
        interpretation = "CONFIRMADO" if action == "CONFIRMAR" else "NO_ASISTIRA"
        conn.execute(text("""
            UPDATE whatsapp_cloud.inbound_responses
            SET interpretation=:interpretation, confidence=100, apply_result=:result,
                resolved_at=now(), resolved_by=:user, resolution=:resolution, updated_at=now()
            WHERE id=:id
        """), {
            "id": int(response_id), "interpretation": interpretation, "result": result,
            "user": username, "resolution": action,
        })
        return {"ok": True, "action": action, "interpretation": interpretation, "result": result}


@app.get("/api/whatsapp-responses/{response_id}/audio")
def whatsapp_response_audio(response_id: int, user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        raise HTTPException(503, "Se necesita conexión para escuchar el audio")
    if not WHATSAPP_ACCESS_TOKEN:
        raise HTTPException(503, "Falta el token de WhatsApp en esta PC")
    try:
        with cloud_engine.connect() as conn:
            if not _wa_inbound_table_ready(conn):
                raise HTTPException(404, "Audio no disponible")
            row = conn.execute(text("""
                SELECT media_id,media_mime_type FROM whatsapp_cloud.inbound_responses WHERE id=:id
            """), {"id": int(response_id)}).mappings().first()
        media_id = str((row or {}).get("media_id") or "").strip()
        if not media_id or not re.fullmatch(r"[A-Za-z0-9._:-]{3,180}", media_id):
            raise HTTPException(404, "Esta respuesta no tiene un audio disponible")
        graph_version = (WHATSAPP_GRAPH_VERSION or "v26.0").strip().lstrip("/")
        meta_req = urllib.request.Request(
            f"https://graph.facebook.com/{graph_version}/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": "Recepcion-Dr-Revelo/4.4.18"},
        )
        with urllib.request.urlopen(meta_req, timeout=12) as resp:
            meta = json.loads(resp.read(512000).decode("utf-8"))
        media_url = str(meta.get("url") or "").strip()
        if not media_url.startswith("https://"):
            raise HTTPException(502, "Meta no devolvió la dirección del audio")
        audio_req = urllib.request.Request(
            media_url,
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": "Recepcion-Dr-Revelo/4.4.18"},
        )
        with urllib.request.urlopen(audio_req, timeout=20) as resp:
            content_type = str(resp.headers.get("content-type") or (row or {}).get("media_mime_type") or "audio/ogg").split(";", 1)[0]
            data = resp.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "El audio es demasiado grande para reproducirlo aquí")
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=60"})
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        raise HTTPException(502, f"Meta no permitió descargar el audio ({exc.code})")
    except Exception as exc:
        raise HTTPException(502, f"No se pudo abrir el audio: {str(exc)[:160]}")
'''

anchor = '\n\nif __name__ == "__main__":'
assert anchor in app
app = app.replace(anchor, API_BLOCK + anchor, 1)

JS_BLOCK = r'''

// ---------------------------------------------------------------------------
// v4.4.18 — Respuestas WhatsApp: texto, audio y revisión humana
// ---------------------------------------------------------------------------
var whatsappReviewPendingValue=0;
var whatsappResponseItems=[];
var whatsappResponseScope='review';
var whatsappReviewLastCheck=0;
var whatsappReviewBusy=false;
const WHATSAPP_REVIEW_REFRESH_MS=10*60*1000;

function waInterpretationLabel(value){
  const v=String(value||'REVISAR').toUpperCase();
  if(v==='CONFIRMADO')return {text:'Confirmado',cls:'confirmed',icon:'✓'};
  if(v==='NO_ASISTIRA')return {text:'No asistirá',cls:'no-show',icon:'×'};
  return {text:'Por revisar',cls:'review',icon:'!'};
}
function waMessageBody(item){
  const transcript=String(item?.transcription||'').trim();
  const raw=String(item?.raw_text||'').trim();
  if(String(item?.message_type||'').toLowerCase()==='audio')return transcript||'Audio recibido · transcripción pendiente';
  return raw||transcript||'Respuesta sin texto';
}
function setWhatsappReviewBadge(n){
  whatsappReviewPendingValue=Math.max(0,Number(n||0));
  const badge=$('#whatsappResponsesNavBadge');
  if(badge){badge.textContent=String(whatsappReviewPendingValue);badge.classList.toggle('hidden',whatsappReviewPendingValue<=0)}
  const strip=$('#homeWhatsappReviewStrip');
  if(strip){
    if(whatsappReviewPendingValue>0){
      strip.innerHTML=`<button class="wa-home-review-card" onclick="show('whatsappRespuestas')"><span class="wa-home-review-icon">!</span><div><small>WHATSAPP</small><b>${whatsappReviewPendingValue} ${whatsappReviewPendingValue===1?'respuesta necesita':'respuestas necesitan'} revisión</b><em>Ver mensajes que no se interpretaron con seguridad</em></div><span class="wa-home-review-arrow">›</span></button>`;
      strip.classList.remove('hidden');
    }else{strip.innerHTML='';strip.classList.add('hidden')}
  }
}
async function refreshWhatsappReviewBadge(force=false){
  if(whatsappReviewBusy||appIdleMode)return null;
  const now=Date.now();if(!force&&now-whatsappReviewLastCheck<WHATSAPP_REVIEW_REFRESH_MS)return null;
  whatsappReviewBusy=true;
  try{
    const d=await api('/api/whatsapp-responses/count');
    whatsappReviewLastCheck=Date.now();
    if(d?.available!==false)setWhatsappReviewBadge(d?.pending||0);
    return d;
  }catch{return null}
  finally{whatsappReviewBusy=false}
}
function setWhatsappResponseScope(scope,button=null){
  whatsappResponseScope=['review','all','resolved'].includes(scope)?scope:'review';
  document.querySelectorAll('[data-wa-response-scope]').forEach(b=>b.classList.toggle('active',b.dataset.waResponseScope===whatsappResponseScope));
  if(button)button.classList.add('active');
  loadWhatsappResponses(whatsappResponseScope,true);
}
function waResponseRow(item){
  const tag=waInterpretationLabel(item.interpretation);
  const audio=String(item.message_type||'').toLowerCase()==='audio';
  const unresolved=!item.resolved_at;
  const appointment=item.appointment_date?`${fmtDate(item.appointment_date)} · ${fmtTimeCompact(item.appointment_time||'')}`:'Sin cita vinculada';
  const message=waMessageBody(item);
  return `<button class="wa-response-row ${unresolved&&tag.cls==='review'?'needs-review':''}" onclick="openWhatsappResponse(${Number(item.id)})">
    <span class="wa-response-type ${audio?'audio':'text'}">${audio?'🎙':'Aa'}</span>
    <span class="wa-response-main"><span class="wa-response-name">${esc(item.patient_name||item.phone||'Paciente')}</span><span class="wa-response-message">${esc(message)}</span><span class="wa-response-meta">${esc(appointment)} · recibido ${esc(fmtDateTime(item.received_at))}</span></span>
    <span class="wa-response-state ${tag.cls}"><b>${tag.icon}</b>${tag.text}</span><span class="wa-response-chevron">›</span>
  </button>`;
}
function renderWhatsappResponses(data){
  const box=$('#whatsappResponseList'),summary=$('#whatsappResponseSummary');if(!box)return;
  if(data?.available===false){
    if(summary)summary.innerHTML='<span class="wa-summary-pill muted">Sin conexión</span>';
    box.innerHTML='<div class="wa-response-empty"><span>☁</span><b>Necesito conexión para leer las respuestas</b><p>La bandeja vive en Neon para seguir recibiendo mensajes aunque esta PC esté apagada.</p></div>';
    return;
  }
  setWhatsappReviewBadge(data?.pending||0);
  whatsappResponseItems=Array.isArray(data?.items)?data.items:[];
  if(summary)summary.innerHTML=`<span class="wa-summary-pill review"><b>${Number(data?.pending||0)}</b> por revisar</span><span class="wa-summary-pill"><b>${whatsappResponseItems.length}</b> visibles</span>`;
  if(!data?.ready){box.innerHTML='<div class="wa-response-empty"><span>💬</span><b>Bandeja lista</b><p>Aparecerán aquí los mensajes de los pacientes cuando llegue la primera respuesta al nuevo webhook.</p></div>';return}
  if(!whatsappResponseItems.length){
    const msg=whatsappResponseScope==='review'?'No hay respuestas pendientes de revisión.':'Todavía no hay respuestas en este filtro.';
    box.innerHTML=`<div class="wa-response-empty"><span>✓</span><b>${esc(msg)}</b><p>Los Sí/No claros se procesan automáticamente.</p></div>`;return;
  }
  box.innerHTML=`<div class="wa-response-list">${whatsappResponseItems.map(waResponseRow).join('')}</div>`;
}
async function loadWhatsappResponses(scope=whatsappResponseScope,force=false){
  whatsappResponseScope=['review','all','resolved'].includes(scope)?scope:'review';
  document.querySelectorAll('[data-wa-response-scope]').forEach(b=>b.classList.toggle('active',b.dataset.waResponseScope===whatsappResponseScope));
  const box=$('#whatsappResponseList');if(box)box.innerHTML='<div class="wa-response-loading">Cargando respuestas de WhatsApp…</div>';
  try{
    const d=await api('/api/whatsapp-responses?scope='+encodeURIComponent(whatsappResponseScope)+'&limit=100');
    whatsappReviewLastCheck=Date.now();renderWhatsappResponses(d);return d;
  }catch(e){if(box)box.innerHTML=`<div class="wa-response-empty"><span>!</span><b>No pude cargar las respuestas</b><p>${esc(e.message||'Intenta nuevamente.')}</p></div>`;return null}
}
function openWhatsappResponse(id){
  const item=whatsappResponseItems.find(x=>Number(x.id)===Number(id));if(!item)return;
  const tag=waInterpretationLabel(item.interpretation),audio=String(item.message_type||'').toLowerCase()==='audio';
  const linked=!!(item.source_type&&item.source_id&&item.appointment_date);
  const unresolved=!item.resolved_at;
  const transcript=String(item.transcription||'').trim();
  const raw=String(item.raw_text||'').trim();
  const actions=unresolved?`<div class="wa-review-actions">
    ${linked?`<button class="primary wa-confirm-btn" onclick="resolveWhatsappResponse(${Number(item.id)},'CONFIRMAR')">✓ Confirmar</button><button class="wa-no-btn" onclick="resolveWhatsappResponse(${Number(item.id)},'CANCELAR')">× No asistirá</button>`:''}
    <button class="wa-resolved-btn" onclick="resolveWhatsappResponse(${Number(item.id)},'RESUELTO')">Marcar como resuelto</button>
  </div>`:'';
  const audioBlock=audio?`<div class="wa-audio-card"><div><b>🎙 Audio del paciente</b><span>${transcript?'Transcripción disponible':'Sin transcripción automática'}</span></div><audio controls preload="none" src="/api/whatsapp-responses/${Number(item.id)}/audio"></audio></div>`:'';
  const body=audio?(transcript||'No se pudo transcribir automáticamente este audio.'):(raw||'Sin texto');
  $('#modalBody').innerHTML=`<div class="wa-review-modal">
    <div class="wa-review-modal-head"><div><span class="wa-modal-eyebrow">RESPUESTA DE WHATSAPP</span><h2>${esc(item.patient_name||item.phone||'Paciente')}</h2><p>${item.appointment_date?`Cita: ${esc(fmtDate(item.appointment_date))} · ${esc(fmtTime(item.appointment_time||''))}`:'No se pudo vincular automáticamente con una cita'}</p></div><span class="wa-response-state ${tag.cls}"><b>${tag.icon}</b>${tag.text}</span></div>
    ${audioBlock}
    <div class="wa-message-card"><span>${audio?'TRANSCRIPCIÓN':'MENSAJE RECIBIDO'}</span><p>${esc(body)}</p></div>
    <div class="wa-review-details"><div><span>Número</span><b>${esc(item.phone||'—')}</b></div><div><span>Recibido</span><b>${esc(fmtDateTime(item.received_at))}</b></div><div><span>Vinculación</span><b>${linked?'Cita encontrada':'Revisión manual'}</b></div><div><span>Confianza</span><b>${Number(item.confidence||0)}%</b></div></div>
    ${unresolved&&!linked?'<div class="wa-link-warning">No se encontró una cita única para este mensaje. Por seguridad el programa no modificó nada.</div>':''}
    ${actions}
  </div>`;
  $('#modal').classList.remove('hidden');
}
async function resolveWhatsappResponse(id,action){
  const labels={CONFIRMAR:'Confirmar asistencia',CANCELAR:'Marcar que no asistirá',RESUELTO:'Marcar como resuelto'};
  if(action!=='RESUELTO'&&!confirm(`${labels[action]} para esta cita?`))return;
  await singleFlightMutation(`wa-response-${id}`,async()=>{
    try{
      await api(`/api/whatsapp-responses/${Number(id)}/resolve`,{method:'POST',body:JSON.stringify({action})});
      closeModal();
      await loadWhatsappResponses(whatsappResponseScope,true);
      await refreshWhatsappReviewBadge(true);
    }catch(e){alert(e.message||'No se pudo resolver la respuesta')}
  },'Guardando…');
}

// Inicio consulta como máximo cada 10 minutos mientras hay actividad. El modo
// AFK sigue sin despertar Neon.
const v4418OriginalLoadDashboard=loadDashboard;
loadDashboard=function(){const result=v4418OriginalLoadDashboard.apply(this,arguments);refreshWhatsappReviewBadge(false);return result;};
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!appIdleMode)refreshWhatsappReviewBadge(false)});
'''

js = js.rstrip() + "\n" + JS_BLOCK.strip() + "\n"
show_anchor = "  if(id==='reportes')loadReport();\n  if(id==='config')showConfigTab(configTab||'general');"
assert show_anchor in js
js = js.replace(show_anchor, "  if(id==='reportes')loadReport();\n  if(id==='whatsappRespuestas')loadWhatsappResponses('review',true);\n  if(id==='config')showConfigTab(configTab||'general');", 1)

NAV_ANCHOR = '      <button class="nav-btn" data-section="config" onclick="show(\'config\')"><span class="nav-icon">⚙</span><span>Configuración</span></button>'
assert NAV_ANCHOR in index
NAV_HTML = '''      <button class="nav-btn whatsapp-responses-nav-btn" data-section="whatsappRespuestas" onclick="show('whatsappRespuestas')"><span class="nav-icon nav-brand-icon whatsapp"><img src="/static/whatsapp_mark.svg" alt=""></span><span>Respuestas WhatsApp</span><span id="whatsappResponsesNavBadge" class="nav-count-badge hidden">0</span></button>\n'''
index = index.replace(NAV_ANCHOR, NAV_HTML + NAV_ANCHOR, 1)

HOME_ANCHOR = '      <div id="homePendingStrip" class="home-pending-strip hidden"></div>'
assert HOME_ANCHOR in index
index = index.replace(HOME_ANCHOR, '      <div id="homeWhatsappReviewStrip" class="wa-home-review-strip hidden"></div>\n' + HOME_ANCHOR, 1)

SECTION_ANCHOR = '    <section id="config" class="hidden">'
assert SECTION_ANCHOR in index
SECTION_HTML = '''    <section id="whatsappRespuestas" class="hidden wa-responses-page">
      <div class="wa-page-head">
        <div><span class="page-eyebrow">WHATSAPP DEL CONSULTORIO</span><h1>Respuestas WhatsApp</h1><p>Solo necesitas intervenir cuando un mensaje no pudo interpretarse con seguridad.</p></div>
        <button onclick="loadWhatsappResponses(whatsappResponseScope,true)">↻ Actualizar</button>
      </div>
      <div class="wa-response-toolbar">
        <div class="wa-response-filters" role="group" aria-label="Filtros de respuestas WhatsApp">
          <button class="active" data-wa-response-scope="review" onclick="setWhatsappResponseScope('review',this)">Por revisar</button>
          <button data-wa-response-scope="all" onclick="setWhatsappResponseScope('all',this)">Todas</button>
          <button data-wa-response-scope="resolved" onclick="setWhatsappResponseScope('resolved',this)">Resueltas</button>
        </div>
        <div id="whatsappResponseSummary" class="wa-response-summary"></div>
      </div>
      <div class="panel wa-response-panel"><div id="whatsappResponseList"><div class="wa-response-loading">Cargando respuestas de WhatsApp…</div></div></div>
    </section>

'''
index = index.replace(SECTION_ANCHOR, SECTION_HTML + SECTION_ANCHOR, 1)

CSS_BLOCK = r'''
<style id="v4418-whatsapp-responses-style">
.whatsapp-responses-nav-btn .nav-count-badge{margin-left:auto}.wa-home-review-strip{margin:0 0 13px}.wa-home-review-card{width:100%;display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:12px;align-items:center;text-align:left;border:1px solid #efc85a;border-radius:14px;background:linear-gradient(135deg,#fff9df,#fff4bf);padding:11px 13px;color:#5c470b;cursor:pointer;box-shadow:0 3px 12px rgba(122,91,10,.06)}.wa-home-review-icon{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:#f2b923;color:#fff;font-size:22px;font-weight:950}.wa-home-review-card small{display:block;font-size:8px;letter-spacing:.09em;font-weight:950;color:#9b7511}.wa-home-review-card b{display:block;margin-top:2px;font-size:12px}.wa-home-review-card em{display:block;margin-top:2px;font-size:9px;font-style:normal;color:#84691e}.wa-home-review-arrow{font-size:27px;color:#b18c22}.wa-responses-page{max-width:1180px}.wa-page-head{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:14px}.wa-page-head h1{margin:3px 0 4px}.wa-page-head p{margin:0;color:#6d7f94;font-size:11px}.wa-page-head>button{min-height:36px}.wa-response-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 0 10px}.wa-response-filters{display:flex;gap:6px;flex-wrap:wrap}.wa-response-filters button{border:1px solid #d8e2ed;background:#fff;color:#60758d;border-radius:999px;padding:7px 11px;font-size:9px;font-weight:850}.wa-response-filters button.active{background:#eaf4ef;border-color:#add3be;color:#2d6d49}.wa-response-summary{display:flex;gap:6px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.wa-summary-pill{display:inline-flex;gap:5px;align-items:center;border:1px solid #dae4ee;background:#fff;border-radius:999px;padding:5px 9px;font-size:8.5px;color:#65788e}.wa-summary-pill.review{border-color:#efd584;background:#fff9e5;color:#7f6314}.wa-response-panel{padding:0!important;overflow:hidden}.wa-response-list{display:grid}.wa-response-row{display:grid;grid-template-columns:42px minmax(0,1fr) auto 20px;gap:11px;align-items:center;width:100%;padding:12px 13px;border:0;border-bottom:1px solid #e5ecf3;background:#fff;text-align:left;cursor:pointer}.wa-response-row:last-child{border-bottom:0}.wa-response-row:hover{background:#f8fbfe}.wa-response-row.needs-review{background:#fffdf7}.wa-response-type{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:#eef3f8;color:#60758c;font-size:11px;font-weight:950}.wa-response-type.audio{background:#edf8f2;color:#2e7851;font-size:17px}.wa-response-main{min-width:0;display:grid;gap:3px}.wa-response-name{font-size:12px;font-weight:900;color:#243a54}.wa-response-message{font-size:10px;color:#4d627a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.wa-response-meta{font-size:8.5px;color:#8493a4}.wa-response-state{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:5px 8px;font-size:8.5px;font-weight:900;white-space:nowrap}.wa-response-state b{display:grid;place-items:center;width:16px;height:16px;border-radius:50%;font-size:10px}.wa-response-state.confirmed{background:#eaf8ef;color:#2e7249}.wa-response-state.confirmed b{background:#56a677;color:#fff}.wa-response-state.no-show{background:#fff0ef;color:#914943}.wa-response-state.no-show b{background:#c96c64;color:#fff}.wa-response-state.review{background:#fff6d9;color:#7e6112}.wa-response-state.review b{background:#e2ac23;color:#fff}.wa-response-chevron{font-size:24px;color:#98a9ba}.wa-response-empty,.wa-response-loading{padding:36px 20px;text-align:center;color:#728397}.wa-response-empty>span{display:block;font-size:25px;margin-bottom:7px}.wa-response-empty b{display:block;color:#354d68;font-size:12px}.wa-response-empty p{margin:5px auto 0;max-width:520px;font-size:9.5px}.wa-review-modal{display:grid;gap:13px;min-width:min(650px,82vw)}.wa-review-modal-head{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;padding-right:35px}.wa-modal-eyebrow{font-size:8px;font-weight:950;letter-spacing:.08em;color:#6d88a4}.wa-review-modal-head h2{margin:3px 0 4px;font-size:21px;color:#203750}.wa-review-modal-head p{margin:0;font-size:10px;color:#73869b}.wa-message-card{border:1px solid #dfe7ef;border-radius:13px;background:#f8fafc;padding:12px 13px}.wa-message-card>span{font-size:8px;font-weight:950;letter-spacing:.07em;color:#71869c}.wa-message-card p{margin:6px 0 0;font-size:12px;line-height:1.48;color:#2c4057;white-space:pre-wrap}.wa-audio-card{display:grid;grid-template-columns:minmax(0,1fr) minmax(250px,360px);gap:12px;align-items:center;border:1px solid #cde4d6;border-radius:13px;background:#f2faf5;padding:11px 12px}.wa-audio-card b,.wa-audio-card span{display:block}.wa-audio-card b{font-size:11px;color:#2b6545}.wa-audio-card span{font-size:8.5px;color:#6d8878;margin-top:3px}.wa-audio-card audio{width:100%;height:35px}.wa-review-details{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.wa-review-details>div{border:1px solid #e2e9f1;border-radius:10px;padding:8px}.wa-review-details span,.wa-review-details b{display:block}.wa-review-details span{font-size:7.5px;font-weight:850;color:#7b8ca0;text-transform:uppercase}.wa-review-details b{margin-top:3px;font-size:9.5px;color:#30475f;overflow-wrap:anywhere}.wa-link-warning{border:1px solid #efd388;border-radius:11px;background:#fff8df;color:#725711;padding:9px 11px;font-size:9.5px}.wa-review-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;border-top:1px solid #e1e8ef;padding-top:12px}.wa-review-actions button{min-height:38px;padding:8px 13px;border-radius:10px;font-weight:850}.wa-confirm-btn{background:#198754!important;color:#fff!important}.wa-no-btn{border-color:#e0a49f!important;background:#fff5f4!important;color:#954c46!important}.wa-resolved-btn{margin-left:auto}.wa-response-state.muted{background:#f0f3f6;color:#6f8091}@media(max-width:760px){.wa-page-head{display:grid}.wa-response-toolbar{align-items:flex-start;display:grid}.wa-response-summary{justify-content:flex-start}.wa-response-row{grid-template-columns:38px minmax(0,1fr) 18px}.wa-response-state{grid-column:2;width:max-content}.wa-response-chevron{grid-column:3;grid-row:1/3}.wa-review-modal{min-width:0}.wa-review-modal-head{display:grid}.wa-review-details{grid-template-columns:repeat(2,minmax(0,1fr))}.wa-audio-card{grid-template-columns:1fr}.wa-review-actions{display:grid;grid-template-columns:1fr}.wa-review-actions button,.wa-resolved-btn{width:100%;margin-left:0}}
</style>
'''
assert '</head>' in index
index = index.replace('</head>', CSS_BLOCK.strip() + '\n</head>', 1)
index = index.replace('/static/app.js?v=4.4.17', '/static/app.js?v=4.4.18', 1)

assert 'v4.4.18' in app
assert '@app.get("/api/whatsapp-responses/count")' in app
assert '@app.get("/api/whatsapp-responses/{response_id}/audio")' in app
assert "data-section=\"whatsappRespuestas\"" in index
assert 'homeWhatsappReviewStrip' in index
assert 'v4418-whatsapp-responses-style' in index
assert "if(id==='whatsappRespuestas')loadWhatsappResponses('review',true);" in js
assert 'resolveWhatsappResponse' in js
assert '/static/app.js?v=4.4.18' in index

if OUT.exists():
    shutil.rmtree(OUT)
write(OUT / 'app.py', app)
write(OUT / 'static/app.js', js)
write(OUT / 'static/index.html', index)

files = []
for rel in ['app.py','static/app.js','static/index.html']:
    data = (OUT / rel).read_bytes()
    files.append({
        'path': rel,
        'sha256': sha256(data),
        'size': len(data),
        'url': f'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_18_whatsapp_responses/{rel}',
    })
manifest = {
    'version': VERSION,
    'created': '2026-08-30',
    'files': files,
    'notes': [
        'Nueva bandeja Respuestas WhatsApp con contador y alerta en Inicio.',
        'Muestra texto, audios y transcripciones; por defecto enseña solo lo que necesita revisión.',
        'Permite resolver manualmente como Confirmado, No asistirá o Marcar como resuelto.',
        'Los mensajes ambiguos nunca modifican una cita automáticamente.',
        'Compatible con el worker WhatsApp v2.6; conserva todas las funciones previas de v4.4.17.',
    ],
}
write(OUT / 'update_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
write(ROOT / 'build/v4418_whatsapp_responses/candidate_latest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('V4418_BUILD_OK')
