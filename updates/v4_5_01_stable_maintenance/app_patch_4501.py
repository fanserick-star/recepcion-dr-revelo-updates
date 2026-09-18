from __future__ import annotations

# v4.5.1 — mantenimiento estable sobre la base probada v4.4.91.
# Esta versión descarta el runtime consolidado experimental de v4.5.0.
# Conserva la cadena estable que ya funcionaba en el consultorio y aplica
# optimizaciones de bajo riesgo:
# - retira repintados JS redundantes de versión/actualizador;
# - añade Estado del sistema, prueba de impresora y limpieza segura;
# - no añade MutationObserver ni temporizadores persistentes;
# - no cambia BD, Neon, AZUR, Agenda, atenciones ni diseños térmicos aprobados.

import json
import os
import shutil
import sys
import time
from pathlib import Path

import app_patch_4491 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.1"

_mod = previous
_seen = set()
for _ in range(96):
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
REMOVED_REDUNDANT_JS_BLOCKS = 0
REMOVED_REDUNDANT_TIMEOUTS = 0


def _strip_redundant_version_overlays():
    """Quita solo capas que repintaban versión/actualizador.

    No toca el JS funcional del formulario v4.4.89 ni facturación, agenda,
    atenciones, WhatsApp, pacientes o impresión.
    """
    global REMOVED_REDUNDANT_JS_BLOCKS, REMOVED_REDUNDANT_TIMEOUTS
    js = getattr(core, "V460_OVERLAY_JS", "") or ""
    targets = [
        ("app_patch_4482", "V4482_JS"),
        ("app_patch_4483", "V4483_JS"),
        ("app_patch_4487", "V4487_JS"),
        ("app_patch_4488", "V4488_JS"),
        ("app_patch_4490", "V4490_JS"),
        ("app_patch_4491", "V4491_JS"),
    ]
    blocks = 0
    timers = 0
    for module_name, attr in targets:
        mod = sys.modules.get(module_name)
        block = getattr(mod, attr, "") if mod is not None else ""
        if block and block in js:
            timers += block.count("setTimeout(")
            js = js.replace(block, "")
            blocks += 1
    core.V460_OVERLAY_JS = js
    REMOVED_REDUNDANT_JS_BLOCKS = blocks
    REMOVED_REDUNDANT_TIMEOUTS = timers


def _safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0


def _local_db_status() -> dict:
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
        "size_bytes": _safe_size(db_path),
        "pending_sync": pending,
        "error": error,
    }


def _neon_status(deep: bool = False) -> dict:
    if deep:
        try:
            return core._probe_neon_service()
        except Exception as exc:
            return {"status": "ERROR", "detail": str(exc)[:220]}
    try:
        if not core.cloud_configured():
            return {"status": "NO CONFIGURADO", "detail": "DATABASE_URL no está configurado en esta PC."}
    except Exception:
        return {"status": "SIN COMPROBAR", "detail": "No se pudo leer la configuración de Neon."}

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


def _printer_status() -> dict:
    info = core._windows_printer_info()
    prefs = core._app_preferences()
    selected = str(prefs.get("printer") or info.get("default_printer") or "").strip()
    printers = list(info.get("printers") or [])
    queue_state = {}
    qmod = sys.modules.get("app_patch_4474")
    try:
        lock = getattr(qmod, "_PRINT_LOCK", None)
        raw = getattr(qmod, "_PRINT_STATE", {}) or {}
        if lock is not None:
            with lock:
                queue_state = dict(raw)
        else:
            queue_state = dict(raw)
        q = getattr(qmod, "_PRINT_QUEUE", None)
        t = getattr(qmod, "_PRINT_THREAD", None)
        queue_state["queue_depth"] = int(q.qsize()) if q is not None else 0
        queue_state["worker_alive"] = bool(t and t.is_alive())
    except Exception:
        queue_state = {}
    return {
        "ok": bool(info.get("supported") and selected and (not printers or selected in printers)),
        "selected": selected,
        "default": str(info.get("default_printer") or ""),
        "available_count": len(printers),
        "error": str(info.get("error") or "")[:220],
        "queue": queue_state,
    }


def _backup_status() -> dict:
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
            pass
    return {
        "ok": bool(value or latest),
        "last_backup": value,
        "count": len(files),
        "latest_size_bytes": _safe_size(latest) if latest else 0,
    }


def _update_status(deep: bool = False) -> dict:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    local = {}
    state = {}
    try:
        local = json.loads((root / "update_manifest.json").read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    try:
        state_path = data / "auto_update_state.json"
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
        "startup_rollback": bool(state.get("startup_rollback")),
    }
    if deep:
        try:
            live = core._read_update_channel_status()
            out.update({
                "latest": live.get("latest"),
                "update_available": bool(live.get("update_available")),
                "latency_ms": live.get("latency_ms"),
            })
        except Exception as exc:
            out["ok"] = False
            out["error"] = str(exc)[:220]
    return out


def _old_temp_candidates() -> list[Path]:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    now = time.time()
    out = []

    staging = data / "update_staging"
    if staging.exists():
        try:
            for item in staging.iterdir():
                try:
                    if now - item.stat().st_mtime >= 24 * 60 * 60:
                        out.append(item)
                except Exception:
                    pass
        except Exception:
            pass

    for pattern in ("*.tmp", "*.rollback_tmp", "*.startup_rollback_tmp", "*.new_*"):
        try:
            for item in root.glob(pattern):
                try:
                    if now - item.stat().st_mtime >= 60 * 60:
                        out.append(item)
                except Exception:
                    pass
        except Exception:
            pass
    return out


def _trim_log(path: Path, keep_bytes: int = 384 * 1024) -> int:
    try:
        if not path.is_file() or path.stat().st_size <= keep_bytes * 2:
            return 0
        raw = path.read_bytes()
        path.write_bytes(raw[-keep_bytes:])
        return max(0, len(raw) - keep_bytes)
    except Exception:
        return 0


def _safe_housekeeping() -> dict:
    data = Path(str(core.DATA_DIR))
    removed_files = 0
    removed_dirs = 0
    freed = 0

    for path in _old_temp_candidates():
        try:
            if path.is_file():
                freed += _safe_size(path)
                path.unlink()
                removed_files += 1
            elif path.is_dir():
                size = 0
                for item in path.rglob("*"):
                    if item.is_file():
                        size += _safe_size(item)
                shutil.rmtree(path, ignore_errors=False)
                freed += size
                removed_dirs += 1
        except Exception:
            pass

    for log_name in ("backend_startup.log", "launcher_errors.log"):
        freed += _trim_log(data / log_name)

    # Mantiene las 10 copias clínicas locales más recientes, misma política
    # que ya usa create_local_backup_snapshot().
    try:
        bdir = Path(str(getattr(core, "BACKUP_DIR", data / "backups")))
        backups = sorted(
            bdir.glob("recepcion_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[10:]:
            try:
                freed += _safe_size(old)
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


def _print_test_ticket(printer_name: str = "") -> str:
    if os.name != "nt":
        raise RuntimeError("La impresión directa solo está disponible en Windows")

    import clr  # type: ignore
    clr.AddReference("System.Drawing")
    from System.Drawing import (  # type: ignore
        Font, FontStyle, Brushes, Pen, Image, Color,
        StringFormat, StringAlignment, RectangleF
    )
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins  # type: ignore

    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or "").strip() or str(PrinterSettings().PrinterName or "").strip()
    if not chosen:
        raise RuntimeError("Windows no tiene una impresora predeterminada")
    if available and chosen not in available:
        raise RuntimeError(f"La impresora ‘{chosen}’ ya no está disponible")

    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")
    doc.DocumentName = "Prueba impresora Recepción"
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize("Prueba 80 mm", 315, 255)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)

    fonts = []
    logo = {"img": None}

    def font(size, bold=False):
        f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f

    f_head = font(9.4, True)
    f_sub = font(7.0)
    f_ok = font(12.0, True)
    f_body = font(7.2)
    f_small = font(6.3)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near
    stamp = time.strftime("%d/%m/%Y %H:%M")

    def on_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        logo_path = os.path.join(str(core.BASE_DIR), "static", "doctor_isotype.png")
        if os.path.exists(logo_path):
            try:
                logo["img"] = Image.FromFile(logo_path)
                g.DrawImage(logo["img"], 0.0, 1.0, 34.0, 34.0)
            except Exception:
                logo["img"] = None
        x = 39.0 if logo["img"] is not None else 0.0
        g.DrawString("DR. ARMANDO REVELO", f_head, Brushes.Black,
                     RectangleF(x, 2.0, width - x, 15.0), center)
        g.DrawString("CIRUJANO URÓLOGO", f_sub, Brushes.Black,
                     RectangleF(x, 18.0, width - x, 13.0), center)
        y = 42.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 12.0
        g.DrawString("IMPRESORA OK", f_ok, Brushes.Black,
                     RectangleF(0.0, y, width, 22.0), center)
        y += 29.0
        g.DrawString(f"Recepción v{APP_VERSION}", f_body, Brushes.Black,
                     RectangleF(0.0, y, width, 15.0), center)
        y += 18.0
        g.DrawString(stamp, f_body, Brushes.Black,
                     RectangleF(0.0, y, width, 15.0), center)
        y += 22.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 8.0
        g.DrawString("80 mm · margen y corte", f_small, Brushes.Black,
                     RectangleF(0.0, y, width, 14.0), center)
        e.HasMorePages = False

    doc.PrintPage += on_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_page
        except Exception:
            pass
        if logo.get("img") is not None:
            try:
                logo["img"].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen


@app.get("/api/v4501/system-status")
def v4501_system_status(deep: bool = False, user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "optimization": {
            "stable_runtime_chain": True,
            "experimental_runtime_consolidation": False,
            "redundant_js_blocks_removed": REMOVED_REDUNDANT_JS_BLOCKS,
            "redundant_timeouts_removed": REMOVED_REDUNDANT_TIMEOUTS,
            "new_mutation_observers": 0,
            "persistent_timers_added": 0,
        },
        "local": _local_db_status(),
        "neon": _neon_status(bool(deep)),
        "printer": _printer_status(),
        "updater": _update_status(bool(deep)),
        "backup": _backup_status(),
        "cleanup": {"candidates": len(_old_temp_candidates())},
    }


@app.post("/api/v4501/maintenance/cleanup")
def v4501_cleanup(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "La limpieza solo se ejecuta desde la PC de Recepción")
    return _safe_housekeeping()


@app.post("/api/v4501/printing/test")
def v4501_print_test(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "Esta prueba solo se ejecuta desde la PC de Recepción")
    prefs = core._app_preferences()
    printer = str(prefs.get("printer") or "").strip()
    try:
        used = _print_test_ticket(printer)
    except Exception as exc:
        raise core.HTTPException(500, f"No se pudo imprimir la prueba: {exc}")
    return {"ok": True, "printer": used, "paper_width_mm": 80, "version": APP_VERSION}


V4501_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.1"!important;font-size:9px!important;line-height:1!important;font-weight:850!important
}
.v4486-print-menu>summary,.home-actions button,.attention-actions button{
  min-height:32px;border-radius:8px!important;font-weight:750
}
.v4501-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}
.v4501-card{border:1px solid #dfe6ef;border-radius:12px;padding:12px;background:#fbfcfe;min-height:100px}
.v4501-card .top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.v4501-card b{font-size:14px;color:#263a55}
.v4501-card small{display:block;margin-top:7px;color:#6f7f95;line-height:1.35}
.v4501-pill{font-size:9px;font-weight:850;border-radius:999px;padding:4px 7px;background:#edf1f6;color:#66768b}
.v4501-pill.ok{background:#e7f7ed;color:#176f3c}
.v4501-pill.warn{background:#fff4db;color:#8a6118}
.v4501-pill.err{background:#ffe9e8;color:#9d3933}
.v4501-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.v4501-actions button{min-height:34px;border-radius:9px;padding:7px 11px;font-weight:750}
.v4501-note{padding:10px 12px;border-radius:10px;background:#f1f6fb;color:#5b6f86;font-size:12px;line-height:1.4}
@media(max-width:1050px){.v4501-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){.v4501-grid{grid-template-columns:1fr}}
"""

V4501_JS = r"""
;(()=>{
  if(window.__v4501StableMaintenance)return;
  window.__v4501StableMaintenance=true;
  const VERSION='4.5.1';
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

  function paint(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
    document.querySelectorAll('button[onclick*="restartReception"]').forEach(btn=>{
      btn.textContent='⬆ Instalar actualización';
      btn.title='Abre el actualizador seguro';
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

  function card(label,state,detail){
    return '<div class="v4501-card"><div class="top"><b>'+esc(label)+'</b><span class="v4501-pill '+cls(state)+'">'+esc(state||'—')+'</span></div><small>'+esc(detail||'')+'</small></div>';
  }

  function render(d){
    const host=q('#v4501Grid');
    if(!host)return;
    const l=d.local||{},n=d.neon||{},p=d.printer||{},u=d.updater||{},b=d.backup||{},o=d.optimization||{},queue=p.queue||{};
    host.innerHTML=[
      card('Base local',l.ok?'OK':'ERROR',(l.name||'SQLite')+' · '+fmtBytes(l.size_bytes)+(l.pending_sync!=null?' · '+l.pending_sync+' pendiente(s)':'')),
      card('Neon',n.status||'SIN COMPROBAR',n.detail||''),
      card('Impresora',p.ok?'OK':'REVISAR',(p.selected||'Sin impresora seleccionada')+(queue.queue_depth!=null?' · cola '+queue.queue_depth:'')),
      card('Actualizador',u.ok!==false?'OK':'REVISAR','Local '+(u.local||VERSION)+(u.latest?' · Canal '+u.latest:'')+(u.last_error?' · '+u.last_error:'')),
      card('Respaldo',b.ok?'OK':'SIN COPIA',b.last_backup?'Último: '+b.last_backup+' · '+(b.count||0)+' copia(s)':'Todavía no hay respaldo local registrado.'),
      card('Optimización','OK',(o.redundant_js_blocks_removed||0)+' overlays y '+(o.redundant_timeouts_removed||0)+' esperas redundantes retiradas')
    ].join('');
    const note=q('#v4501Note');
    if(note)note.textContent='Recepción v'+VERSION+'. La limpieza no toca pacientes, atenciones, agenda, .env, BASE DE DATOS 2026.xlsx ni las bases SQLite.';
  }

  async function refresh(deep,btn){
    if(btn){btn.disabled=true;btn.textContent=deep?'Revisando…':'Actualizando…'}
    try{
      render(await call('/api/v4501/system-status?deep='+(deep?'true':'false')));
    }catch(e){
      const note=q('#v4501Note');
      if(note)note.textContent=e?.message||String(e);
    }finally{
      if(btn){btn.disabled=false;btn.textContent=deep?'↻ Revisar sistema':'Actualizar'}
    }
  }

  async function action(kind,btn){
    if(btn)btn.disabled=true;
    try{
      if(kind==='print'){
        await call('/api/v4501/printing/test',{method:'POST',body:'{}'});
        if(typeof window.rpNotice==='function')window.rpNotice('Prueba enviada a la impresora.');
      }else if(kind==='backup'){
        await call('/api/backup/now',{method:'POST',body:'{}'});
        if(typeof window.rpNotice==='function')window.rpNotice('Respaldo creado correctamente.');
      }else if(kind==='cleanup'){
        const d=await call('/api/v4501/maintenance/cleanup',{method:'POST',body:'{}'});
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
    paint();
    const config=q('#config'),tabs=q('.config-tabs',config);
    if(!config||!tabs)return;

    let sec=q('[data-config-section="maintenance"]',config);
    if(!sec){
      sec=document.createElement('div');
      sec.dataset.configSection='maintenance';
      sec.className='config-section hidden';
      sec.innerHTML='<div class="panel"><div class="config-panel-head"><div><h2>Mantenimiento</h2><p>Estado local, impresora, respaldo y limpieza segura del programa.</p></div></div><div id="v4501Grid" class="v4501-grid"></div><div class="v4501-actions"><button type="button" class="primary" data-v4501="review">↻ Revisar sistema</button><button type="button" data-v4501="print">🖨 Imprimir prueba</button><button type="button" data-v4501="backup">Crear respaldo</button><button type="button" data-v4501="cleanup">Limpiar temporales</button></div><div id="v4501Note" class="v4501-note">Cargando estado local…</div></div>';
      config.appendChild(sec);
      q('[data-v4501="review"]',sec)?.addEventListener('click',function(){refresh(true,this)});
      q('[data-v4501="print"]',sec)?.addEventListener('click',function(){action('print',this)});
      q('[data-v4501="backup"]',sec)?.addEventListener('click',function(){action('backup',this)});
      q('[data-v4501="cleanup"]',sec)?.addEventListener('click',function(){action('cleanup',this)});
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

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
  else mount();
  setTimeout(mount,500);
})();
"""

try:
    _strip_redundant_version_overlays()
    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4501_CSS
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + V4501_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4501/health")
def v4501_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "stable_runtime_chain": True,
        "experimental_runtime_consolidation": False,
        "redundant_js_blocks_removed": REMOVED_REDUNDANT_JS_BLOCKS,
        "redundant_timeouts_removed": REMOVED_REDUNDANT_TIMEOUTS,
        "new_mutation_observers": 0,
        "persistent_timers_added": 0,
        "maintenance_tab": True,
        "printer_test": True,
        "safe_cleanup": True,
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
