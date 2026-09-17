from __future__ import annotations

# v4.4.70 — flujo de atención e identidad más práctico para recepción.
# - Un celular puede pertenecer a varias personas: avisa, no bloquea.
# - Al guardar una CONSULTA imprime automáticamente el recibo y vuelve a Inicio.
# - Si la impresora falla, la atención ya guardada NO se revierte.
# - Agrega una administración confiable para eliminar/archivar servicios y precios.
# - La versión junto a "En línea" se pinta desde la versión real de esta capa.
# - Conserva intacto el recibo térmico v4.4.69 aprobado visualmente.

import app_patch_4469 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.70"

_mod = previous
_seen = set()
for _ in range(20):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    class _V4470PrintVisitIn(core.BaseModel):
        pass

    def _v4470_is_consultation(visit) -> bool:
        return not str(getattr(visit, "procedimiento", None) or "").strip()

    def _v4470_consultation_turn(db, visit) -> int | None:
        rows = list(db.scalars(
            core.select(core.Visit)
            .where(core.Visit.fecha == visit.fecha)
            .order_by(core.Visit.id)
        ))
        first_by_patient = {}
        for row in rows:
            if not _v4470_is_consultation(row):
                continue
            first_by_patient.setdefault(int(row.patient_id), int(row.id))
        ordered = [
            pid for pid, _first_id in
            sorted(first_by_patient.items(), key=lambda item: item[1])
        ]
        try:
            return ordered.index(int(visit.patient_id)) + 1
        except ValueError:
            return None

    def _v4470_is_first_consultation(db, visit) -> bool:
        prior = int(db.scalar(
            core.select(core.func.count(core.Visit.id)).where(
                core.Visit.patient_id == int(visit.patient_id),
                core.Visit.id < int(visit.id),
                core.func.length(
                    core.func.trim(core.func.coalesce(core.Visit.procedimiento, ""))
                ) == 0,
            )
        ) or 0)
        return prior == 0

    @app.post("/api/v4470/print-visit/{visit_id}")
    def v4470_print_visit(
        visit_id: int,
        data: _V4470PrintVisitIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        visit = db.get(core.Visit, int(visit_id))
        if not visit:
            return {
                "ok": True,
                "printed": False,
                "reason": "visit_not_found",
                "message": "Atención guardada, pero no se encontró el registro para imprimir.",
            }
        if not _v4470_is_consultation(visit):
            return {
                "ok": True,
                "printed": False,
                "reason": "procedure_only",
                "message": "Atención guardada. Los procedimientos no generan recibo.",
            }

        patient = db.get(core.Patient, int(visit.patient_id))
        if not patient:
            return {
                "ok": True,
                "printed": False,
                "reason": "patient_not_found",
                "message": "Atención guardada, pero no se encontró el paciente para imprimir.",
            }

        turn = _v4470_consultation_turn(db, visit)
        is_new = _v4470_is_first_consultation(db, visit)
        birth = None
        if getattr(patient, "fecha_nacimiento", None):
            try:
                birth = patient.fecha_nacimiento.strftime("%d/%m/%Y")
            except Exception:
                birth = str(patient.fecha_nacimiento)

        payload = core.ReceiptPrintIn(
            fecha=visit.fecha.strftime("%d/%m/%Y"),
            nombre=str(patient.nombre or "").strip().upper(),
            fecha_nacimiento=birth,
            celular=str(patient.celular or "").strip() or None,
            turno=turn,
            is_new=is_new,
        )
        prefs = core._app_preferences()
        printer = str(prefs.get("printer") or "").strip()
        try:
            used = core._print_receipt_windows(
                payload,
                printer,
                bool(prefs.get("show_blood_pressure", True)),
            )
            return {
                "ok": True,
                "printed": True,
                "printer": used,
                "turno": turn,
                "message": "Atención guardada. Recibo enviado a la impresora.",
            }
        except Exception as exc:
            try:
                core.logging.getLogger(__name__).warning(
                    "v4.4.70: atención %s guardada, impresión falló: %s",
                    visit_id, exc,
                )
            except Exception:
                pass
            return {
                "ok": True,
                "printed": False,
                "reason": "printer_error",
                "turno": turn,
                "error": str(exc)[:240],
                "message": "Atención guardada. No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.",
            }

    @app.get("/api/v4470/version")
    def v4470_version(user=core.Depends(core.current_user)):
        return {"version": APP_VERSION}

    V4470_CSS = r"""
.v4470-busy{position:fixed;inset:0;z-index:2147483500;background:rgba(245,249,253,.94);display:grid;place-items:center;padding:24px;backdrop-filter:blur(2px)}
.v4470-busy-card{min-width:290px;max-width:430px;padding:24px 26px;border-radius:18px;background:#fff;border:1px solid #d9e5ef;box-shadow:0 18px 55px rgba(28,58,85,.18);text-align:center;color:#27445f}
.v4470-spinner{width:42px;height:42px;margin:0 auto 14px;border:4px solid #d9e7f2;border-top-color:#3e789f;border-radius:50%;animation:v4470spin .8s linear infinite}
@keyframes v4470spin{to{transform:rotate(360deg)}}
.v4470-busy-card b{display:block;font-size:15px;line-height:1.25;margin-bottom:5px}.v4470-busy-card small{display:block;font-size:11px;color:#70859a}
.v4470-toast{position:fixed;right:18px;bottom:18px;z-index:2147483501;max-width:420px;padding:12px 14px;border-radius:12px;background:#225f42;color:#fff;box-shadow:0 10px 30px rgba(25,62,45,.24);font-size:12px;font-weight:800}.v4470-toast.warn{background:#8a6419}
.v4470-phone-shared{margin-top:6px;padding:7px 9px;border:1px solid #dfc36e;border-radius:9px;background:#fff9e8;color:#705617;font-size:10px;line-height:1.35}.v4470-phone-shared b{display:block;margin-bottom:2px}
.v4470-proc-manager{margin-top:14px;padding:13px;border:1px solid #d6e1eb;border-radius:13px;background:#fbfdff}.v4470-proc-manager-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:9px}.v4470-proc-manager-head h4{margin:0;font-size:13px;color:#294b68}.v4470-proc-manager-head small{display:block;margin-top:2px;color:#71869a}.v4470-proc-list{display:grid;gap:6px}.v4470-proc-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:9px;align-items:center;padding:8px 9px;border:1px solid #e2eaf1;border-radius:10px;background:#fff}.v4470-proc-row b{font-size:11px;color:#314f68}.v4470-proc-row span{font-size:11px;font-weight:800;color:#577087;white-space:nowrap}.v4470-proc-delete{border:1px solid #dfb3b3!important;background:#fff6f6!important;color:#9a3838!important;border-radius:8px!important;padding:6px 9px!important;font-size:10px!important;font-weight:900!important}
@media(max-width:640px){.v4470-proc-row{grid-template-columns:minmax(0,1fr) auto}.v4470-proc-row span{grid-column:1}}
"""

    V4470_JS = r"""
;(()=>{
  if(window.__v4470WorkflowFix)return;
  window.__v4470WorkflowFix=true;
  const VERSION='4.4.70';
  let attentionBusy=false,procBusy=false;
  const text=v=>String(v??'').replace(/\s+/g,' ').trim();
  const norm=v=>text(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
  const phoneKey=v=>{let d=String(v||'').replace(/\D/g,'');if(d.length===12&&d.startsWith('593'))d='0'+d.slice(3);return d};
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  function baseApi(){const fn=window.api;return fn?.__v4470Base||fn}

  function installPhoneSharing(){
    if(typeof window.api!=='function'){setTimeout(installPhoneSharing,120);return}
    if(window.api.__v4470SharedPhone)return;
    const stable=window.api;
    const shim=async function(url,opt={}){
      const u=String(url||'');
      if(u.startsWith('/api/identity/phone-owner'))return {duplicate:false,patient:null,normalized:''};
      return stable.apply(this,arguments);
    };
    shim.__v4470SharedPhone=true;shim.__v4470Base=stable;window.api=shim;try{api=shim}catch(_e){}
  }

  function currentPatientId(){
    const modal=document.querySelector('#modal,.modal,.modal-backdrop')||document;
    const attrs=[...modal.querySelectorAll('button[onclick],a[onclick]')].map(x=>String(x.getAttribute('onclick')||''));
    for(const raw of attrs){const m=/(?:savePatient|savePatientAndReturnToAttention|editPatientFromAttention)\s*\(\s*(\d+)/.exec(raw);if(m)return Number(m[1]||0)}
    return 0;
  }
  async function passivePhoneWarning(){
    const input=document.querySelector('#fCel');if(!input)return;
    const host=input.closest('.form-field')||input.parentElement;host?.querySelector('.v4470-phone-shared')?.remove();
    const wanted=phoneKey(input.value);if(wanted.length<9)return;const call=baseApi();if(typeof call!=='function')return;
    let rows=[];try{const vars=[wanted];if(wanted.length===10&&wanted.startsWith('0'))vars.push('593'+wanted.slice(1));const batches=await Promise.all(vars.map(q=>call('/api/patients?q='+encodeURIComponent(q)+'&limit=30').catch(()=>[])));rows=batches.flat()}catch(_e){return}
    const exclude=currentPatientId(),found=new Map();
    for(const p of rows){if(!p||Number(p.id||0)<=0||Number(p.id)===exclude)continue;if(phoneKey(p.celular)===wanted)found.set(Number(p.id),p)}
    const hits=[...found.values()];if(!hits.length||!host)return;
    const names=hits.slice(0,3).map(p=>text(p.nombre)||'Paciente').join(', '),note=document.createElement('div');
    note.className='v4470-phone-shared';note.innerHTML=`<b>ℹ Celular compartido</b>Este número también está registrado para ${names}. Puedes guardarlo igualmente si corresponde a esta persona.`;host.appendChild(note);
  }
  function installPhoneWatcher(){
    const attach=()=>{const input=document.querySelector('#fCel');if(!input||input.dataset.v4470PhoneWatcher)return;input.dataset.v4470PhoneWatcher='1';let timer=0;const run=()=>{clearTimeout(timer);timer=setTimeout(passivePhoneWarning,330)};input.addEventListener('input',run);input.addEventListener('blur',run);setTimeout(run,80)};
    new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});attach();
  }

  function busyOverlay(message){document.querySelector('.v4470-busy')?.remove();const el=document.createElement('div');el.className='v4470-busy';el.innerHTML=`<div class="v4470-busy-card"><div class="v4470-spinner"></div><b>${message}</b><small>Espera un momento…</small></div>`;document.body.appendChild(el);return el}
  function busyText(el,message){const b=el?.querySelector('b');if(b)b.textContent=message}function hideBusy(el){try{el?.remove()}catch(_e){}}
  function toast(message,warn=false){document.querySelector('.v4470-toast')?.remove();const el=document.createElement('div');el.className='v4470-toast'+(warn?' warn':'');el.textContent=message;document.body.appendChild(el);setTimeout(()=>el.remove(),5200)}
  function goHome(){try{if(typeof window.closeModal==='function')window.closeModal()}catch(_e){}const els=[...document.querySelectorAll('nav button,nav a,.sidebar button,.sidebar a,.menu button,.menu a,button,a')];const home=els.find(el=>norm(el.textContent)==='INICIO');if(home){try{home.click();return}catch(_e){}}for(const id of ['inicio','home']){try{if(typeof window.show==='function'){window.show(id);return}}catch(_e){}}}

  function installAttentionFlow(){
    if(typeof window.saveAttention!=='function'){setTimeout(installAttentionFlow,120);return}if(window.saveAttention.__v4470AutoPrint)return;
    const stableSave=window.saveAttention;
    const patched=async function(patientId){
      if(attentionBusy)return;attentionBusy=true;let savedBatch=null;const overlay=busyOverlay('Guardando atención e imprimiendo recibo…');const apiBefore=window.api;const globalBefore=(()=>{try{return api}catch(_e){return null}})();
      const capture=async function(url,opt={}){const result=await apiBefore.apply(this,arguments);const u=String(url||'');if(u==='/api/visits/batch-payment'||u==='/api/visits/batch'){if(result&&typeof result==='object')savedBatch=result}return result};
      try{window.api=capture;try{api=capture}catch(_e){}await stableSave.apply(this,arguments)}catch(err){hideBusy(overlay);attentionBusy=false;throw err}finally{window.api=apiBefore;try{api=globalBefore||apiBefore}catch(_e){}}
      try{
        if(!savedBatch||savedBatch.ok===false){hideBusy(overlay);attentionBusy=false;return}
        const items=Array.isArray(savedBatch.items)?savedBatch.items:[],consult=items.find(v=>!text(v?.procedimiento));let printResult=null;
        if(consult&&Number(consult.id||0)>0){busyText(overlay,'Atención guardada. Imprimiendo recibo…');try{printResult=await apiBefore('/api/v4470/print-visit/'+Number(consult.id),{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}catch(e){printResult={printed:false}}}
        goHome();try{if(typeof window.invalidateAttentionWeekCache==='function')window.invalidateAttentionWeekCache();if(typeof window.loadWeek==='function'){const d=text(consult?.fecha||items[0]?.fecha||'').slice(0,10);Promise.resolve(window.loadWeek(d||undefined,d||undefined)).catch(()=>{})}if(typeof window.refreshPendingBadges==='function')Promise.resolve(window.refreshPendingBadges()).catch(()=>{})}catch(_e){}
        hideBusy(overlay);if(consult){if(printResult?.printed)toast('✓ Atención guardada. Recibo enviado a la impresora.');else toast('✓ Atención guardada. ⚠ No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.',true)}else toast('✓ Atención guardada.');
      }finally{attentionBusy=false}
    };
    patched.__v4470AutoPrint=true;patched.__v4470Stable=stableSave;window.saveAttention=patched;
  }

  async function renderProcedureManager(){
    const sec=document.querySelector('[data-config-section="procedimientos"]');if(!sec||procBusy)return;procBusy=true;
    try{const call=window.api;if(typeof call!=='function')return;const rows=await call('/api/procedures');let box=sec.querySelector('#v4470ProcedureManager');if(!box){box=document.createElement('div');box.id='v4470ProcedureManager';box.className='v4470-proc-manager';sec.appendChild(box)}const list=Array.isArray(rows)?rows:[];
      box.innerHTML=`<div class="v4470-proc-manager-head"><div><h4>Eliminar servicios</h4><small>Si un servicio ya tiene historial, se archiva y las atenciones antiguas se conservan.</small></div></div><div class="v4470-proc-list">${list.map(p=>`<div class="v4470-proc-row" data-id="${Number(p.id)}"><b>${text(p.nombre)}</b><span>${p.valor_default==null?'Sin precio':'$'+Number(p.valor_default).toFixed(2)}</span><button type="button" class="v4470-proc-delete" data-delete="${Number(p.id)}">Eliminar</button></div>`).join('')||'<small>No hay servicios activos.</small>'}</div>`;
      box.querySelectorAll('[data-delete]').forEach(btn=>btn.addEventListener('click',async()=>{const id=Number(btn.dataset.delete||0),row=list.find(x=>Number(x.id)===id);if(!id)return;if(!confirm(`¿Eliminar "${text(row?.nombre)||'este servicio'}"?\n\nSi tiene atenciones anteriores, se archivará para no alterar el historial.`))return;btn.disabled=true;try{const d=await call('/api/procedures/'+id,{method:'DELETE'});toast(d?.message||'Servicio eliminado.');try{if(typeof window.loadProcedures==='function')await window.loadProcedures()}catch(_e){}await sleep(60);box.remove();renderProcedureManager()}catch(e){alert(e?.message||e);btn.disabled=false}}));
    }catch(_e){}finally{procBusy=false}
  }
  function installProcedureManager(){
    const attempt=()=>{const sec=document.querySelector('[data-config-section="procedimientos"]');if(sec&&!sec.querySelector('#v4470ProcedureManager'))renderProcedureManager();if(typeof window.loadProcedures==='function'&&!window.loadProcedures.__v4470Manager){const stable=window.loadProcedures;const wrapped=async function(){const r=await stable.apply(this,arguments);setTimeout(renderProcedureManager,40);return r};wrapped.__v4470Manager=true;window.loadProcedures=wrapped}};
    new MutationObserver(()=>setTimeout(attempt,30)).observe(document.documentElement,{childList:true,subtree:true});attempt();
  }

  function paintVersion(){const expected='v'+VERSION;document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{if(text(el.textContent)!==expected)el.textContent=expected});const badge=document.querySelector('#connectionBadge');if(badge){let v=badge.querySelector('.v460-version');if(!v){v=document.createElement('span');v.className='v460-version';badge.appendChild(v)}if(text(v.textContent)!==expected)v.textContent=expected}}
  function installVersionPainter(){let scheduled=false;const run=()=>{if(scheduled)return;scheduled=true;setTimeout(()=>{scheduled=false;paintVersion()},20)};new MutationObserver(run).observe(document.documentElement,{childList:true,subtree:true,characterData:true});paintVersion();setTimeout(paintVersion,250);setTimeout(paintVersion,900)}

  function boot(){installPhoneSharing();installPhoneWatcher();installAttentionFlow();installProcedureManager();installVersionPainter()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4470_CSS
    )
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4470_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.70 workflow patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4470/health")
def v4470_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "shared_phone_allowed": True,
        "automatic_receipt_after_consultation": True,
        "attention_survives_printer_error": True,
        "procedure_delete_manager": True,
        "dynamic_version_badge": True,
        "receipt_design": "v4.4.69",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )
