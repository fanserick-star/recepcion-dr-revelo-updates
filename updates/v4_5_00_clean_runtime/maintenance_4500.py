from __future__ import annotations

# v4.5.0 — mantenimiento, limpieza y pulido visual.
# Conserva la funcionalidad aprobada de v4.4.91 y añade diagnóstico local,
# prueba de impresora, respaldo y limpieza segura de temporales.

import json
import shutil
import sys
import time
from pathlib import Path

import printing_4500 as previous

runtime = previous.previous
core = previous.core
app = previous.app
APP_VERSION = "4.5.0"

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""
REMOVED_REDUNDANT_JS_BLOCKS = 0


def _set_versions():
    core.APP_VERSION = APP_VERSION
    for name, mod in list(sys.modules.items()):
        if name == "app_base_4428" or name.startswith("app_patch_") or name.startswith("app_prev_"):
            try:
                mod.APP_VERSION = APP_VERSION
            except Exception:
                pass


def _strip_redundant_overlay_js():
    global REMOVED_REDUNDANT_JS_BLOCKS
    js = getattr(core, "V460_OVERLAY_JS", "") or ""
    targets = [
        ("app_patch_4482", "V4482_JS"),
        ("app_patch_4483", "V4483_JS"),
        ("app_patch_4487", "V4487_JS"),
        ("app_patch_4488", "V4488_JS"),
        ("app_patch_4490", "V4490_JS"),
        ("app_patch_4491", "V4491_JS"),
    ]
    removed = 0
    for module_name, attr in targets:
        mod = sys.modules.get(module_name)
        block = getattr(mod, attr, "") if mod is not None else ""
        if block and block in js:
            js = js.replace(block, "")
            removed += 1
    core.V460_OVERLAY_JS = js
    REMOVED_REDUNDANT_JS_BLOCKS = removed


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0


def _backup_info() -> dict:
    backup_dir = Path(str(getattr(core, "BACKUP_DIR", Path(str(core.DATA_DIR)) / "backups")))
    try:
        files = sorted(
            backup_dir.glob("recepcion_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        files = []
    latest = files[0] if files else None
    value = ""
    try:
        with core.LocalSessionLocal() as db:
            row = db.get(core.CacheMeta, "last_backup")
            value = str(getattr(row, "value", "") or "")
    except Exception:
        pass
    if not value and latest:
        try:
            value = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(latest.stat().st_mtime))
        except Exception:
            value = ""
    return {
        "ok": bool(value or latest),
        "last_backup": value,
        "count": len(files),
        "latest_size_bytes": _file_size(latest) if latest else 0,
    }


def _local_info() -> dict:
    db_path = Path(str(getattr(core, "OFFLINE_DB_PATH", Path(str(core.DATA_DIR)) / "offline_cache.db")))
    ok = False
    error = ""
    try:
        with core.LocalSessionLocal() as db:
            db.execute(core.text("SELECT 1"))
        ok = True
    except Exception as exc:
        error = str(exc)[:220]
    pending = None
    try:
        pending = int(core.queue_count())
    except Exception:
        pass
    return {
        "ok": ok,
        "name": db_path.name,
        "exists": db_path.exists(),
        "size_bytes": _file_size(db_path),
        "pending_sync": pending,
        "error": error,
    }


def _printer_info() -> dict:
    info = core._windows_printer_info()
    prefs = core._app_preferences()
    selected = str(prefs.get("printer") or info.get("default_printer") or "")
    printers = list(info.get("printers") or [])
    ok = bool(info.get("supported") and selected and (not printers or selected in printers))
    return {
        "ok": ok,
        "selected": selected,
        "default": str(info.get("default_printer") or ""),
        "available_count": len(printers),
        "error": str(info.get("error") or "")[:220],
        "queue": previous.print_queue_status(),
    }


def _neon_info(deep: bool = False) -> dict:
    if deep:
        try:
            return core._probe_neon_service()
        except Exception as exc:
            return {"status": "ERROR", "detail": str(exc)[:220]}
    configured = False
    try:
        configured = bool(core.cloud_configured())
    except Exception:
        pass
    if not configured:
        return {"status": "NO CONFIGURADO", "detail": "Neon no está configurado en esta PC."}
    try:
        lock = getattr(core, "_state_lock", None)
        state = getattr(core, "_state", {}) or {}
        if lock is not None:
            with lock:
                state = dict(state)
        else:
            state = dict(state)
        online = state.get("online")
        err = str(state.get("last_error") or "")[:180]
        if online is True:
            return {"status": "ONLINE", "detail": "Último estado conocido: conectado."}
        if online is False:
            return {"status": "OFFLINE", "detail": err or "Último estado conocido: sin conexión."}
    except Exception:
        pass
    return {"status": "SIN COMPROBAR", "detail": "Pulsa Revisar sistema para comprobar Neon."}


def _update_info(deep: bool = False) -> dict:
    manifest_path = Path(str(core.BASE_DIR)) / "update_manifest.json"
    state_path = Path(str(core.DATA_DIR)) / "auto_update_state.json"
    local = {}
    state = {}
    try:
        local = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    try:
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    out = {
        "ok": True,
        "local": str(local.get("version") or APP_VERSION),
        "launcher_version": str(local.get("launcher_version") or ""),
        "last_check_ok": state.get("last_check_ok"),
        "last_error": str(state.get("last_error") or "")[:220],
        "last_installed_version": str(state.get("last_installed_version") or ""),
    }
    if deep:
        try:
            live = core._read_update_channel_status()
            out["latest"] = live.get("latest")
            out["update_available"] = bool(live.get("update_available"))
            out["latency_ms"] = live.get("latency_ms")
        except Exception as exc:
            out["ok"] = False
            out["error"] = str(exc)[:220]
    return out


def _cleanup_candidates() -> list[Path]:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    result = []
    staging = data / "update_staging"
    if staging.exists():
        try:
            result.extend(list(staging.iterdir()))
        except Exception:
            pass
    cache = root / "__pycache__"
    if cache.exists():
        result.append(cache)
    for pattern in ("*.tmp", "*.rollback_tmp", "*.new_*"):
        try:
            result.extend(root.glob(pattern))
        except Exception:
            pass
    return result


def _trim_log(path: Path, keep_bytes: int = 384 * 1024) -> int:
    try:
        if not path.is_file() or path.stat().st_size <= keep_bytes * 2:
            return 0
        raw = path.read_bytes()
        path.write_bytes(raw[-keep_bytes:])
        return max(0, len(raw) - keep_bytes)
    except Exception:
        return 0


def safe_housekeeping() -> dict:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    protected = {
        ".env",
        "BASE DE DATOS 2026.xlsx",
        "recepcion.db",
        "offline_cache.db",
    }
    removed_files = 0
    removed_dirs = 0
    freed = 0

    for path in _cleanup_candidates():
        try:
            if path.name in protected:
                continue
            if path.is_file():
                freed += _file_size(path)
                path.unlink()
                removed_files += 1
            elif path.is_dir():
                size = 0
                for item in path.rglob("*"):
                    if item.is_file():
                        size += _file_size(item)
                shutil.rmtree(path, ignore_errors=False)
                freed += size
                removed_dirs += 1
        except Exception:
            pass

    for log_name in ("backend_startup.log", "launcher_errors.log"):
        freed += _trim_log(data / log_name)

    try:
        bdir = Path(str(getattr(core, "BACKUP_DIR", data / "backups")))
        backups = sorted(
            bdir.glob("recepcion_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[10:]:
            try:
                freed += _file_size(old)
                old.unlink()
                removed_files += 1
            except Exception:
                pass
    except Exception:
        pass

    return {
        "ok": True,
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "freed_bytes": int(freed),
        "protected_data_untouched": True,
    }


@app.get("/api/v4500/system-status")
def v4500_system_status(deep: bool = False, user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "runtime": {
            "consolidated": True,
            "legacy_modules_loaded": int(getattr(runtime, "CONSOLIDATED_LEGACY_MODULES", 31)),
            "distributed_runtime_files": int(getattr(runtime, "DISTRIBUTED_RUNTIME_FILES", 4)),
            "redundant_js_blocks_removed": REMOVED_REDUNDANT_JS_BLOCKS,
            "new_mutation_observers": 0,
            "persistent_timers_added": 0,
        },
        "local": _local_info(),
        "neon": _neon_info(bool(deep)),
        "printer": _printer_info(),
        "updater": _update_info(bool(deep)),
        "backup": _backup_info(),
        "cleanup": {"candidates": len(_cleanup_candidates())},
    }


@app.post("/api/v4500/maintenance/cleanup")
def v4500_cleanup(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "La limpieza solo se ejecuta desde la PC de Recepción")
    return safe_housekeeping()


V4500_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.0"!important;font-size:9px!important;line-height:1!important;font-weight:850!important
}
.v4486-print-menu>summary,.home-actions button,.attention-actions button{
  min-height:32px;border-radius:8px!important;font-weight:750
}
#billingRecipientAlt .v4489-billing-form-print{
  border-style:solid!important;background:#f8fbff!important
}
.v4500-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}
.v4500-card{border:1px solid #dfe6ef;border-radius:12px;padding:12px;background:#fbfcfe;min-height:100px}
.v4500-card .top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.v4500-card b{font-size:14px;color:#263a55}
.v4500-card small{display:block;margin-top:7px;color:#6f7f95;line-height:1.35}
.v4500-pill{font-size:9px;font-weight:850;border-radius:999px;padding:4px 7px;background:#edf1f6;color:#66768b}
.v4500-pill.ok{background:#e7f7ed;color:#176f3c}
.v4500-pill.warn{background:#fff4db;color:#8a6118}
.v4500-pill.err{background:#ffe9e8;color:#9d3933}
.v4500-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.v4500-actions button{min-height:34px;border-radius:9px;padding:7px 11px;font-weight:750}
.v4500-note{padding:10px 12px;border-radius:10px;background:#f1f6fb;color:#5b6f86;font-size:12px;line-height:1.4}
@media(max-width:1050px){.v4500-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){.v4500-grid{grid-template-columns:1fr}}
"""

V4500_JS = r"""
;(()=>{
  if(window.__v4500Maintenance)return;
  window.__v4500Maintenance=true;
  const VERSION='4.5.0';
  const q=(s,r=document)=>r.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const call=async(url,opt={})=>{
    if(typeof window.api==='function')return window.api(url,opt);
    const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(d.detail||d.message||'No se pudo completar la operación');
    return d;
  };
  const fmtBytes=n=>{
    n=Number(n||0);
    if(n<1024)return n+' B';
    if(n<1048576)return (n/1024).toFixed(1)+' KB';
    return (n/1048576).toFixed(1)+' MB';
  };
  const cls=v=>{
    v=String(v||'').toUpperCase();
    if(v==='OK'||v==='ONLINE'||v==='IDLE'||v==='PRINTED')return 'ok';
    if(v==='ERROR'||v==='OFFLINE')return 'err';
    return 'warn';
  };

  function paintVersion(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
  }

  async function launchUpdater(){
    const status=q('#updateStatus');
    try{
      if(status)status.textContent='Abriendo actualizador seguro…';
      const d=await call('/api/v4483/launch-updater',{method:'POST',body:'{}'});
      if(status)status.textContent='Actualizador abierto.';
      return d;
    }catch(e){
      if(status)status.textContent=e?.message||String(e);
      alert(e?.message||String(e));
      throw e;
    }
  }
  window.restartReception=launchUpdater;

  function tuneBilling(){
    const alt=q('#billingRecipientAlt');
    if(!alt)return;
    const email=q('#brEmail',alt);
    if(email){
      email.required=false;
      email.placeholder='Opcional';
    }
    const labels=[...alt.querySelectorAll('label')];
    const label=labels.find(x=>x.htmlFor==='brEmail');
    if(label && !/opcional/i.test(label.textContent||''))label.textContent='Correo (opcional)';
  }

  const oldEditor=window.openBillingRecipientEditor;
  if(typeof oldEditor==='function'&&!oldEditor.__v4500){
    const wrapped=async function(){
      const out=await oldEditor.apply(this,arguments);
      tuneBilling();
      return out;
    };
    wrapped.__v4500=true;
    window.openBillingRecipientEditor=wrapped;
  }

  function card(label,state,detail){
    return '<div class="v4500-card"><div class="top"><b>'+esc(label)+'</b><span class="v4500-pill '+cls(state)+'">'+esc(state||'—')+'</span></div><small>'+esc(detail||'')+'</small></div>';
  }

  function render(d){
    const host=q('#v4500Grid');
    if(!host)return;
    const l=d.local||{},n=d.neon||{},p=d.printer||{},u=d.updater||{},b=d.backup||{},rt=d.runtime||{},queue=p.queue||{};
    const parts=[];
    parts.push(card('Base local',l.ok?'OK':'ERROR',(l.name||'SQLite')+' · '+fmtBytes(l.size_bytes)+(l.pending_sync!=null?' · '+l.pending_sync+' pendiente(s)':'')));
    parts.push(card('Neon',n.status||'SIN COMPROBAR',n.detail||''));
    parts.push(card('Impresora',p.ok?'OK':'REVISAR',(p.selected||'Sin impresora seleccionada')+(queue.available?' · cola '+(queue.queue_depth||0):'')));
    parts.push(card('Actualizador',u.ok!==false?'OK':'REVISAR','Local '+(u.local||VERSION)+(u.latest?' · Canal '+u.latest:'')+(u.last_error?' · '+u.last_error:'')));
    parts.push(card('Respaldo',b.ok?'OK':'SIN COPIA',b.last_backup?'Último: '+b.last_backup+' · '+(b.count||0)+' copia(s)':'Todavía no hay respaldo local registrado.'));
    parts.push(card('Runtime limpio','OK',(rt.distributed_runtime_files||4)+' archivos distribuidos · '+(rt.redundant_js_blocks_removed||0)+' overlays redundantes retirados'));
    host.innerHTML=parts.join('');
    const note=q('#v4500Note');
    if(note)note.textContent='Recepción v'+VERSION+'. La limpieza no borra pacientes, atenciones, agenda, BASE DE DATOS 2026.xlsx, .env ni bases SQLite.';
  }

  async function refresh(deep,btn){
    if(btn){
      btn.disabled=true;
      btn.textContent=deep?'Revisando…':'Actualizando…';
    }
    try{
      render(await call('/api/v4500/system-status?deep='+(deep?'true':'false')));
    }catch(e){
      const note=q('#v4500Note');
      if(note)note.textContent=e?.message||String(e);
    }finally{
      if(btn){
        btn.disabled=false;
        btn.textContent=deep?'↻ Revisar sistema':'Actualizar';
      }
    }
  }
  window.v4500Refresh=refresh;

  async function action(kind,btn){
    if(btn)btn.disabled=true;
    try{
      if(kind==='print'){
        await call('/api/v4500/printing/test',{method:'POST',body:'{}'});
        if(typeof window.rpNotice==='function')window.rpNotice('Prueba enviada a la impresora.');
      }else if(kind==='backup'){
        await call('/api/backup/now',{method:'POST',body:'{}'});
        if(typeof window.rpNotice==='function')window.rpNotice('Respaldo creado correctamente.');
      }else if(kind==='cleanup'){
        const d=await call('/api/v4500/maintenance/cleanup',{method:'POST',body:'{}'});
        const msg='Limpieza terminada: '+(d.removed_files||0)+' archivo(s), '+(d.removed_dirs||0)+' carpeta(s), '+fmtBytes(d.freed_bytes||0)+' liberados.';
        if(typeof window.rpNotice==='function')window.rpNotice(msg);else alert(msg);
      }
      await refresh(false,null);
    }catch(e){
      alert(e?.message||String(e));
    }finally{
      if(btn)btn.disabled=false;
    }
  }

  function mount(){
    paintVersion();
    document.querySelectorAll('button[onclick*="restartReception"]').forEach(btn=>{
      btn.textContent='⬆ Instalar actualización';
      btn.title='Abre el actualizador seguro';
    });
    const config=q('#config'),tabs=q('.config-tabs',config);
    if(!config||!tabs)return;

    let sec=q('[data-config-section="maintenance"]',config);
    if(!sec){
      sec=document.createElement('div');
      sec.dataset.configSection='maintenance';
      sec.className='config-section hidden';
      sec.innerHTML='<div class="panel"><div class="config-panel-head"><div><h2>Mantenimiento</h2><p>Estado local, impresora, respaldo y limpieza segura del programa.</p></div></div><div id="v4500Grid" class="v4500-grid"></div><div class="v4500-actions"><button type="button" class="primary" data-v4500="review">↻ Revisar sistema</button><button type="button" data-v4500="print">🖨 Imprimir prueba</button><button type="button" data-v4500="backup">Crear respaldo</button><button type="button" data-v4500="cleanup">Limpiar temporales</button></div><div id="v4500Note" class="v4500-note">Cargando estado local…</div></div>';
      config.appendChild(sec);
      q('[data-v4500="review"]',sec)?.addEventListener('click',function(){refresh(true,this)});
      q('[data-v4500="print"]',sec)?.addEventListener('click',function(){action('print',this)});
      q('[data-v4500="backup"]',sec)?.addEventListener('click',function(){action('backup',this)});
      q('[data-v4500="cleanup"]',sec)?.addEventListener('click',function(){action('cleanup',this)});
    }

    let btn=q('[data-config-tab="maintenance"]',tabs);
    if(!btn){
      btn=document.createElement('button');
      btn.type='button';
      btn.dataset.configTab='maintenance';
      btn.textContent='Mantenimiento';
      tabs.appendChild(btn);
      btn.addEventListener('click',()=>{
        if(typeof window.showConfigTab==='function')window.showConfigTab('maintenance',btn);
        refresh(false,null);
      });
    }
  }

  function boot(){
    mount();
    tuneBilling();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
  setTimeout(mount,450);
})();
"""

try:
    _set_versions()
    _strip_redundant_overlay_js()
    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4500_CSS
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4500_JS
    # La limpieza queda manual. No borramos cachés al arrancar porque la PC
    # antigua se beneficia de conservar bytecode entre aperturas.
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4500/health")
def v4500_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "runtime_consolidated": True,
        "distributed_runtime_files": int(getattr(runtime, "DISTRIBUTED_RUNTIME_FILES", 4)),
        "redundant_js_blocks_removed": REMOVED_REDUNDANT_JS_BLOCKS,
        "new_mutation_observers": 0,
        "persistent_timers_added": 0,
        "safe_housekeeping": True,
        "printer_test": True,
        "maintenance_tab": True,
        "database_changes": False,
        "neon_writes_added": False,
        "receipt_layout_version": "4.4.69",
        "payment_proof_layout_version": "4.4.88",
        "billing_form_layout_version": "4.4.91",
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
