from __future__ import annotations
import reception_billing_data_form_layout as _dep_billing_data_form_layout
import json
import os
import shutil
import sys
import time
from pathlib import Path
core = _dep_billing_data_form_layout.core
app = _dep_billing_data_form_layout.app
APP_VERSION = '4.5.1'
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
REMOVED_REDUNDANT_JS_BLOCKS = 0
REMOVED_REDUNDANT_TIMEOUTS = 0

def _strip_redundant_version_overlays():
    """Quita solo capas que repintaban versión/actualizador.

    No toca el JS funcional del formulario v4.4.89 ni facturación, agenda,
    atenciones, WhatsApp, pacientes o impresión.
    """
    global REMOVED_REDUNDANT_JS_BLOCKS, REMOVED_REDUNDANT_TIMEOUTS
    js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    targets = [('reception_update_restart', 'V4482_JS'), ('reception_update_launcher', 'V4483_JS'), ('reception_payment_proof_margins', 'V4487_JS'), ('reception_payment_proof_layout', 'V4488_JS'), ('reception_billing_data_form_compact', 'V4490_JS'), ('reception_billing_data_form_layout', 'V4491_JS')]
    blocks = 0
    timers = 0
    for module_name, attr in targets:
        mod = sys.modules.get(module_name)
        block = getattr(mod, attr, '') if mod is not None else ''
        if block and block in js:
            timers += block.count('setTimeout(')
            js = js.replace(block, '')
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
    db_path = Path(str(getattr(core, 'OFFLINE_DB_PATH', Path(str(core.DATA_DIR)) / 'offline_cache.db')))
    ok = False
    error = ''
    try:
        with core.LocalSessionLocal() as db:
            db.execute(core.text('SELECT 1'))
        ok = True
    except Exception as exc:
        error = str(exc)[:220]
    pending = None
    try:
        pending = int(core.queue_count())
    except Exception:
        pass
    return {'ok': ok, 'name': db_path.name, 'exists': db_path.exists(), 'size_bytes': _safe_size(db_path), 'pending_sync': pending, 'error': error}

def _neon_status(deep: bool=False) -> dict:
    if deep:
        try:
            return core._probe_neon_service()
        except Exception as exc:
            return {'status': 'ERROR', 'detail': str(exc)[:220]}
    try:
        if not core.cloud_configured():
            return {'status': 'NO CONFIGURADO', 'detail': 'DATABASE_URL no está configurado en esta PC.'}
    except Exception:
        return {'status': 'SIN COMPROBAR', 'detail': 'No se pudo leer la configuración de Neon.'}
    try:
        lock = getattr(core, '_state_lock', None)
        state = getattr(core, '_state', {}) or {}
        if lock is not None:
            with lock:
                state = dict(state)
        else:
            state = dict(state)
        online = state.get('online')
        err = str(state.get('last_error') or '')[:180]
        if online is True:
            return {'status': 'ONLINE', 'detail': 'Último estado conocido: conectado.'}
        if online is False:
            return {'status': 'OFFLINE', 'detail': err or 'Último estado conocido: sin conexión.'}
    except Exception:
        pass
    return {'status': 'SIN COMPROBAR', 'detail': 'Pulsa Revisar sistema para comprobar Neon.'}

def _printer_status() -> dict:
    info = core._windows_printer_info()
    prefs = core._app_preferences()
    selected = str(prefs.get('printer') or info.get('default_printer') or '').strip()
    printers = list(info.get('printers') or [])
    queue_state = {}
    qmod = sys.modules.get('reception_printing_queue')
    try:
        lock = getattr(qmod, '_PRINT_LOCK', None)
        raw = getattr(qmod, '_PRINT_STATE', {}) or {}
        if lock is not None:
            with lock:
                queue_state = dict(raw)
        else:
            queue_state = dict(raw)
        q = getattr(qmod, '_PRINT_QUEUE', None)
        t = getattr(qmod, '_PRINT_THREAD', None)
        queue_state['queue_depth'] = int(q.qsize()) if q is not None else 0
        queue_state['worker_alive'] = bool(t and t.is_alive())
    except Exception:
        queue_state = {}
    return {'ok': bool(info.get('supported') and selected and (not printers or selected in printers)), 'selected': selected, 'default': str(info.get('default_printer') or ''), 'available_count': len(printers), 'error': str(info.get('error') or '')[:220], 'queue': queue_state}

def _backup_status() -> dict:
    backup_dir = Path(str(getattr(core, 'BACKUP_DIR', Path(str(core.DATA_DIR)) / 'backups')))
    try:
        files = sorted(backup_dir.glob('recepcion_backup_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        files = []
    latest = files[0] if files else None
    value = ''
    try:
        with core.LocalSessionLocal() as db:
            row = db.get(core.CacheMeta, 'last_backup')
            value = str(getattr(row, 'value', '') or '')
    except Exception:
        pass
    if not value and latest:
        try:
            value = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(latest.stat().st_mtime))
        except Exception:
            pass
    return {'ok': bool(value or latest), 'last_backup': value, 'count': len(files), 'latest_size_bytes': _safe_size(latest) if latest else 0}

def _update_status(deep: bool=False) -> dict:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    local = {}
    state = {}
    try:
        local = json.loads((root / 'update_manifest.json').read_text(encoding='utf-8-sig'))
    except Exception:
        pass
    try:
        state_path = data / 'auto_update_state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8-sig'))
    except Exception:
        pass
    out = {'ok': True, 'local': str(local.get('version') or APP_VERSION), 'launcher_version': str(local.get('launcher_version') or ''), 'last_check_ok': state.get('last_check_ok'), 'last_error': str(state.get('last_error') or '')[:220], 'last_installed_version': str(state.get('last_installed_version') or ''), 'startup_rollback': bool(state.get('startup_rollback'))}
    if deep:
        try:
            live = core._read_update_channel_status()
            out.update({'latest': live.get('latest'), 'update_available': bool(live.get('update_available')), 'latency_ms': live.get('latency_ms')})
        except Exception as exc:
            out['ok'] = False
            out['error'] = str(exc)[:220]
    return out

def _old_temp_candidates() -> list[Path]:
    root = Path(str(core.BASE_DIR))
    data = Path(str(core.DATA_DIR))
    now = time.time()
    out = []
    staging = data / 'update_staging'
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
    for pattern in ('*.tmp', '*.rollback_tmp', '*.startup_rollback_tmp', '*.new_*'):
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

def _trim_log(path: Path, keep_bytes: int=384 * 1024) -> int:
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
                for item in path.rglob('*'):
                    if item.is_file():
                        size += _safe_size(item)
                shutil.rmtree(path, ignore_errors=False)
                freed += size
                removed_dirs += 1
        except Exception:
            pass
    for log_name in ('backend_startup.log', 'launcher_errors.log'):
        freed += _trim_log(data / log_name)
    try:
        bdir = Path(str(getattr(core, 'BACKUP_DIR', data / 'backups')))
        backups = sorted(bdir.glob('recepcion_backup_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[10:]:
            try:
                freed += _safe_size(old)
                old.unlink()
                removed_files += 1
            except Exception:
                pass
    except Exception:
        pass
    return {'ok': True, 'removed_files': removed_files, 'removed_dirs': removed_dirs, 'freed_bytes': int(freed), 'protected_data_untouched': True}

def _print_test_ticket(printer_name: str='') -> str:
    if os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    doc.DocumentName = 'Prueba impresora Recepción'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Prueba 80 mm', 315, 255)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    logo = {'img': None}

    def font(size, bold=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
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
    stamp = time.strftime('%d/%m/%Y %H:%M')

    def on_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        logo_path = os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if os.path.exists(logo_path):
            try:
                logo['img'] = Image.FromFile(logo_path)
                g.DrawImage(logo['img'], 0.0, 1.0, 34.0, 34.0)
            except Exception:
                logo['img'] = None
        x = 39.0 if logo['img'] is not None else 0.0
        g.DrawString('DR. ARMANDO REVELO', f_head, Brushes.Black, RectangleF(x, 2.0, width - x, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_sub, Brushes.Black, RectangleF(x, 18.0, width - x, 13.0), center)
        y = 42.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 12.0
        g.DrawString('IMPRESORA OK', f_ok, Brushes.Black, RectangleF(0.0, y, width, 22.0), center)
        y += 29.0
        g.DrawString(f'Recepción v{APP_VERSION}', f_body, Brushes.Black, RectangleF(0.0, y, width, 15.0), center)
        y += 18.0
        g.DrawString(stamp, f_body, Brushes.Black, RectangleF(0.0, y, width, 15.0), center)
        y += 22.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 8.0
        g.DrawString('80 mm · margen y corte', f_small, Brushes.Black, RectangleF(0.0, y, width, 14.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_page
        except Exception:
            pass
        if logo.get('img') is not None:
            try:
                logo['img'].Dispose()
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

@app.get('/api/v4501/system-status')
def v4501_system_status(deep: bool=False, user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'optimization': {'stable_runtime_chain': True, 'experimental_runtime_consolidation': False, 'redundant_js_blocks_removed': REMOVED_REDUNDANT_JS_BLOCKS, 'redundant_timeouts_removed': REMOVED_REDUNDANT_TIMEOUTS, 'new_mutation_observers': 0, 'persistent_timers_added': 0}, 'local': _local_db_status(), 'neon': _neon_status(bool(deep)), 'printer': _printer_status(), 'updater': _update_status(bool(deep)), 'backup': _backup_status(), 'cleanup': {'candidates': len(_old_temp_candidates())}}

@app.post('/api/v4501/maintenance/cleanup')
def v4501_cleanup(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'La limpieza solo se ejecuta desde la PC de Recepción')
    return _safe_housekeeping()

@app.post('/api/v4501/printing/test')
def v4501_print_test(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, '_is_loopback_client') and (not core._is_loopback_client(request)):
        raise core.HTTPException(403, 'Esta prueba solo se ejecuta desde la PC de Recepción')
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = _print_test_ticket(printer)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo imprimir la prueba: {exc}')
    return {'ok': True, 'printer': used, 'paper_width_mm': 80, 'version': APP_VERSION}
V4501_CSS = '\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.5.1"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n.v4486-print-menu>summary,.home-actions button,.attention-actions button{\n  min-height:32px;border-radius:8px!important;font-weight:750\n}\n.v4501-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:12px 0}\n.v4501-card{border:1px solid #dfe6ef;border-radius:12px;padding:12px;background:#fbfcfe;min-height:100px}\n.v4501-card .top{display:flex;align-items:center;justify-content:space-between;gap:8px}\n.v4501-card b{font-size:14px;color:#263a55}\n.v4501-card small{display:block;margin-top:7px;color:#6f7f95;line-height:1.35}\n.v4501-pill{font-size:9px;font-weight:850;border-radius:999px;padding:4px 7px;background:#edf1f6;color:#66768b}\n.v4501-pill.ok{background:#e7f7ed;color:#176f3c}\n.v4501-pill.warn{background:#fff4db;color:#8a6118}\n.v4501-pill.err{background:#ffe9e8;color:#9d3933}\n.v4501-actions{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}\n.v4501-actions button{min-height:34px;border-radius:9px;padding:7px 11px;font-weight:750}\n.v4501-note{padding:10px 12px;border-radius:10px;background:#f1f6fb;color:#5b6f86;font-size:12px;line-height:1.4}\n@media(max-width:1050px){.v4501-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}\n@media(max-width:720px){.v4501-grid{grid-template-columns:1fr}}\n'
V4501_JS = '\n;(()=>{\n  if(window.__v4501StableMaintenance)return;\n  window.__v4501StableMaintenance=true;\n  const VERSION=\'4.5.1\';\n  const q=(s,r=document)=>r.querySelector(s);\n  const esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n  const call=async(url,opt={})=>{\n    if(typeof window.api===\'function\')return window.api(url,opt);\n    const r=await fetch(url,{headers:{\'Content-Type\':\'application/json\',...(opt.headers||{})},...opt});\n    const d=await r.json().catch(()=>({}));\n    if(!r.ok)throw Error(d.detail||d.message||\'No se pudo completar la operación\');\n    return d;\n  };\n  const fmtBytes=n=>{\n    n=Number(n||0);\n    if(n<1024)return n+\' B\';\n    if(n<1048576)return (n/1024).toFixed(1)+\' KB\';\n    return (n/1048576).toFixed(1)+\' MB\';\n  };\n  const cls=v=>{\n    v=String(v||\'\').toUpperCase();\n    if(v===\'OK\'||v===\'ONLINE\'||v===\'IDLE\'||v===\'PRINTED\')return \'ok\';\n    if(v===\'ERROR\'||v===\'OFFLINE\')return \'err\';\n    return \'warn\';\n  };\n\n  function paint(){\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;\n      el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n    document.querySelectorAll(\'button[onclick*="restartReception"]\').forEach(btn=>{\n      btn.textContent=\'⬆ Instalar actualización\';\n      btn.title=\'Abre el actualizador seguro\';\n    });\n  }\n\n  async function launchUpdater(){\n    const status=q(\'#updateStatus\');\n    try{\n      if(status)status.textContent=\'Abriendo actualizador seguro…\';\n      const d=await call(\'/api/v4483/launch-updater\',{method:\'POST\',body:\'{}\'});\n      if(status)status.textContent=\'Actualizador abierto.\';\n      return d;\n    }catch(e){\n      if(status)status.textContent=e?.message||String(e);\n      alert(e?.message||String(e));\n      throw e;\n    }\n  }\n  window.restartReception=launchUpdater;\n\n  function card(label,state,detail){\n    return \'<div class="v4501-card"><div class="top"><b>\'+esc(label)+\'</b><span class="v4501-pill \'+cls(state)+\'">\'+esc(state||\'—\')+\'</span></div><small>\'+esc(detail||\'\')+\'</small></div>\';\n  }\n\n  function render(d){\n    const host=q(\'#v4501Grid\');\n    if(!host)return;\n    const l=d.local||{},n=d.neon||{},p=d.printer||{},u=d.updater||{},b=d.backup||{},o=d.optimization||{},queue=p.queue||{};\n    host.innerHTML=[\n      card(\'Base local\',l.ok?\'OK\':\'ERROR\',(l.name||\'SQLite\')+\' · \'+fmtBytes(l.size_bytes)+(l.pending_sync!=null?\' · \'+l.pending_sync+\' pendiente(s)\':\'\')),\n      card(\'Neon\',n.status||\'SIN COMPROBAR\',n.detail||\'\'),\n      card(\'Impresora\',p.ok?\'OK\':\'REVISAR\',(p.selected||\'Sin impresora seleccionada\')+(queue.queue_depth!=null?\' · cola \'+queue.queue_depth:\'\')),\n      card(\'Actualizador\',u.ok!==false?\'OK\':\'REVISAR\',\'Local \'+(u.local||VERSION)+(u.latest?\' · Canal \'+u.latest:\'\')+(u.last_error?\' · \'+u.last_error:\'\')),\n      card(\'Respaldo\',b.ok?\'OK\':\'SIN COPIA\',b.last_backup?\'Último: \'+b.last_backup+\' · \'+(b.count||0)+\' copia(s)\':\'Todavía no hay respaldo local registrado.\'),\n      card(\'Optimización\',\'OK\',(o.redundant_js_blocks_removed||0)+\' overlays y \'+(o.redundant_timeouts_removed||0)+\' esperas redundantes retiradas\')\n    ].join(\'\');\n    const note=q(\'#v4501Note\');\n    if(note)note.textContent=\'Recepción v\'+VERSION+\'. La limpieza no toca pacientes, atenciones, agenda, .env, BASE DE DATOS 2026.xlsx ni las bases SQLite.\';\n  }\n\n  async function refresh(deep,btn){\n    if(btn){btn.disabled=true;btn.textContent=deep?\'Revisando…\':\'Actualizando…\'}\n    try{\n      render(await call(\'/api/v4501/system-status?deep=\'+(deep?\'true\':\'false\')));\n    }catch(e){\n      const note=q(\'#v4501Note\');\n      if(note)note.textContent=e?.message||String(e);\n    }finally{\n      if(btn){btn.disabled=false;btn.textContent=deep?\'↻ Revisar sistema\':\'Actualizar\'}\n    }\n  }\n\n  async function action(kind,btn){\n    if(btn)btn.disabled=true;\n    try{\n      if(kind===\'print\'){\n        await call(\'/api/v4501/printing/test\',{method:\'POST\',body:\'{}\'});\n        if(typeof window.rpNotice===\'function\')window.rpNotice(\'Prueba enviada a la impresora.\');\n      }else if(kind===\'backup\'){\n        await call(\'/api/backup/now\',{method:\'POST\',body:\'{}\'});\n        if(typeof window.rpNotice===\'function\')window.rpNotice(\'Respaldo creado correctamente.\');\n      }else if(kind===\'cleanup\'){\n        const d=await call(\'/api/v4501/maintenance/cleanup\',{method:\'POST\',body:\'{}\'});\n        const msg=\'Limpieza terminada: \'+(d.removed_files||0)+\' archivo(s), \'+(d.removed_dirs||0)+\' carpeta(s), \'+fmtBytes(d.freed_bytes||0)+\' liberados.\';\n        if(typeof window.rpNotice===\'function\')window.rpNotice(msg);else alert(msg);\n      }\n      await refresh(false,null);\n    }catch(e){\n      alert(e?.message||String(e));\n    }finally{\n      if(btn)btn.disabled=false;\n    }\n  }\n\n  function mount(){\n    paint();\n    const config=q(\'#config\'),tabs=q(\'.config-tabs\',config);\n    if(!config||!tabs)return;\n\n    let sec=q(\'[data-config-section="maintenance"]\',config);\n    if(!sec){\n      sec=document.createElement(\'div\');\n      sec.dataset.configSection=\'maintenance\';\n      sec.className=\'config-section hidden\';\n      sec.innerHTML=\'<div class="panel"><div class="config-panel-head"><div><h2>Mantenimiento</h2><p>Estado local, impresora, respaldo y limpieza segura del programa.</p></div></div><div id="v4501Grid" class="v4501-grid"></div><div class="v4501-actions"><button type="button" class="primary" data-v4501="review">↻ Revisar sistema</button><button type="button" data-v4501="print">🖨 Imprimir prueba</button><button type="button" data-v4501="backup">Crear respaldo</button><button type="button" data-v4501="cleanup">Limpiar temporales</button></div><div id="v4501Note" class="v4501-note">Cargando estado local…</div></div>\';\n      config.appendChild(sec);\n      q(\'[data-v4501="review"]\',sec)?.addEventListener(\'click\',function(){refresh(true,this)});\n      q(\'[data-v4501="print"]\',sec)?.addEventListener(\'click\',function(){action(\'print\',this)});\n      q(\'[data-v4501="backup"]\',sec)?.addEventListener(\'click\',function(){action(\'backup\',this)});\n      q(\'[data-v4501="cleanup"]\',sec)?.addEventListener(\'click\',function(){action(\'cleanup\',this)});\n    }\n\n    let btn=q(\'[data-config-tab="maintenance"]\',tabs);\n    if(!btn){\n      btn=document.createElement(\'button\');\n      btn.type=\'button\';\n      btn.dataset.configTab=\'maintenance\';\n      btn.textContent=\'Mantenimiento\';\n      tabs.appendChild(btn);\n      btn.addEventListener(\'click\',()=>{\n        if(typeof window.showConfigTab===\'function\')window.showConfigTab(\'maintenance\',btn);\n        refresh(false,null);\n      });\n    }\n  }\n\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',mount,{once:true});\n  else mount();\n  setTimeout(mount,500);\n})();\n'
try:
    _strip_redundant_version_overlays()
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4501_CSS
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4501_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'


# 4.8.14 — Centro de alertas bajo demanda, sin sondeo periódico de Neon.
# No envía mensajes, no toca las historias y nunca cambia las facturas.
@app.get('/api/ops/alerts')
def reception_4814_alerts(user=core.Depends(core.current_user)):
    pending_sync = 0
    try:
        pending_sync = int(core.queue_count())
    except Exception:
        pass
    backup = _backup_status()
    result = {
        'ok': True, 'cloud_checked': False, 'cloud_error': '',
        'pending_sync': pending_sync, 'backup_ok': bool(backup.get('ok')),
        'missing_confirmations': [], 'delivery_errors': [],
        'missing_count': 0, 'delivery_error_count': 0,
        'alarm_hint': {},
        'no_message_sent': True, 'automatic_neon_polling': False,
    }
    lock = getattr(core, '_wa_alarm_hint_lock', None)
    if lock is not None:
        with lock:
            result['alarm_hint'] = dict(getattr(core, '_wa_alarm_hint_diag', {}) or {})
    if not core.cloud_configured() or not core.CloudSessionLocal or core.FORCE_OFFLINE:
        result['cloud_error'] = 'Neon no disponible. Se muestran solo alertas locales.'
        return result
    try:
        with core.CloudSessionLocal() as db:
            # New local Reception appointments eligible for immediate confirmation
            # with NO cloud event. Never assume Meta has sent a message.
            # The 12h window matches the Worker's expiration policy: no replay
            # of old registrations and no accidental backfill on this GET.
            missing = db.execute(core.text("""
                SELECT a.id, a.patient_id, p.nombre, a.fecha::text AS fecha,
                       a.hora, a.created_at
                FROM public.appointments a
                JOIN public.patients p ON p.id = a.patient_id
                WHERE a.created_at AT TIME ZONE 'UTC' >= now() - interval '12 hours'
                  AND a.created_at AT TIME ZONE 'UTC' <= now() - interval '3 minutes'
                  AND a.fecha >= (now() AT TIME ZONE 'America/Guayaquil')::date
                  AND upper(coalesce(a.estado,'')) NOT IN
                      ('CANCELADA','CANCELADO','NO_ASISTIRA','NO_ASISTIRÁ')
                  AND a.origen <> 'CONFIRMAFY_ATENDIDO'
                  AND ((a.fecha + a.hora::time) AT TIME ZONE 'America/Guayaquil') > now()
                  AND ((a.fecha + a.hora::time) AT TIME ZONE 'America/Guayaquil')
                      - (a.created_at AT TIME ZONE 'UTC') >= interval '24 hours'
                  AND ((a.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date
                      < (a.fecha - 1)
                  AND length(regexp_replace(coalesce(p.celular,''),'[^0-9]','','g'))
                      BETWEEN 10 AND 15
                  AND NOT EXISTS (
                      SELECT 1 FROM whatsapp_cloud.events e
                      WHERE e.source_type = 'appointment' AND e.source_id = a.id
                        AND e.template_name = 'cita_agendada'
                        AND e.appointment_date = a.fecha
                        AND left(e.appointment_time::text,5) = left(a.hora,5)
                  )
                ORDER BY a.created_at DESC LIMIT 30
            """)).mappings().all()
            delivery = db.execute(core.text("""
                SELECT e.patient_name,e.template_name,e.status,
                       e.appointment_date::text AS fecha,
                       e.appointment_time AS hora,e.error_code
                FROM whatsapp_cloud.events e
                WHERE e.updated_at >= now() - interval '24 hours'
                  AND (
                      e.status IN ('ERROR','FAILED')
                      OR (e.status='SENDING' AND e.updated_at < now()-interval '10 minutes')
                  )
                ORDER BY e.updated_at DESC LIMIT 30
            """)).mappings().all()
        result['cloud_checked'] = True
        result['missing_count'] = len(missing)
        result['delivery_error_count'] = len(delivery)
        result['missing_confirmations'] = [{
            'appointment_id': int(r['id']), 'patient_id': int(r['patient_id']),
            'patient': str(r['nombre'] or ''), 'date': str(r['fecha'] or '')[:10],
            'time': str(r['hora'] or '')[:5],
            'problem': 'Sin evento de cita agendada en WhatsApp Cloud',
        } for r in missing]
        result['delivery_errors'] = [{
            'patient': str(r['patient_name'] or ''),
            'template': str(r['template_name'] or ''),
            'date': str(r['fecha'] or '')[:10], 'time': str(r['hora'] or '')[:5],
            'status': str(r['status'] or ''), 'error_code': str(r['error_code'] or '')[:70],
        } for r in delivery]
    except Exception as exc:
        # Never expose DB credentials or raw exception details to the UI.
        result['cloud_error'] = type(exc).__name__ + ': no se pudo consultar WhatsApp Cloud.'
    return result



# 4.8.15 — Auditoría de identidad de solo lectura, a petición de Recepción.
# No crea pacientes, no modifica historias, no fusiona ni verifica enlaces.
@app.get('/api/ops/clinical-integrity')
def reception_4815_integrity(user=core.Depends(core.current_user)):
    from datetime import date, datetime, timedelta
    import re
    result = {
        'ok': False, 'history_checked': False, 'checked': 0, 'issues': [],
        'missing_links': 0, 'data_discrepancies': 0, 'invalid_links': 0,
        'message': '', 'no_mutations': True, 'manual_only': True,
    }
    try:
        since_day = date.today() - timedelta(days=7)
        with core.LocalSessionLocal() as local_db:
            rows = list(local_db.scalars(
                core.select(core.Patient)
                .where(core.or_(
                    core.Patient.created_at >= datetime.utcnow() - timedelta(days=7),
                    core.Patient.id.in_(core.select(core.Visit.patient_id).where(core.Visit.fecha >= since_day)),
                ))
                .order_by(core.Patient.id.desc())
                .limit(60)
            ))
    except Exception:
        result['message'] = 'No se pudo leer la copia local de pacientes.'
        return result
    if not rows:
        result.update(ok=True, history_checked=False,
                      message='No hay pacientes recientes para revisar.')
        return result
    result['checked'] = len(rows)
    try:
        import reception_history_identity_consolidated as identity
        conn = identity._connect_public()
        try:
            cursor = conn.cursor()
            values = [str(int(p.id)) for p in rows]
            placeholders = ','.join('%s' for _ in values)
            cursor.execute(
                'SELECT l.reception_patient_id,l.clinical_patient_id,l.verified,'
                'p.name,p.national_id_search,p.birth_date,p.deleted_at '
                'FROM public.patient_links l LEFT JOIN public.patients p '
                'ON p.id=l.clinical_patient_id '
                'WHERE l.deleted_at IS NULL '
                'AND l.reception_patient_id IN (' + placeholders + ')',
                tuple(values),
            )
            names = [str(col[0]) for col in cursor.description]
            linked = {str(d['reception_patient_id']): d for raw in cursor.fetchall()
                      for d in [dict(zip(names, raw))]}
        finally:
            conn.close()
    except Exception:
        result['message'] = 'No se pudo consultar Historia. Ninguna ficha fue modificada.'
        return result

    def normalized_id(value):
        return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())

    issues = []
    for patient in rows:
        reception_id = int(patient.id)
        name = str(patient.nombre or '')
        record = linked.get(str(reception_id))
        if not record:
            result['missing_links'] += 1
            issues.append({'kind': 'unlinked', 'patient_id': reception_id,
                           'patient': name, 'description': 'Ficha sin vínculo verificado en Historia.'})
            continue
        if record.get('name') is None or record.get('deleted_at') is not None or int(record.get('verified') or 0) != 1:
            result['invalid_links'] += 1
            issues.append({'kind': 'invalid_link', 'patient_id': reception_id,
                           'patient': name, 'description': 'El vínculo clínico necesita revisión.'})
            continue
        reception_ident = normalized_id(patient.cedula)
        clinical_ident = normalized_id(record.get('national_id_search'))
        reception_birth = str(patient.fecha_nacimiento or '')[:10]
        clinical_birth = str(record.get('birth_date') or '')[:10]
        mismatches = []
        if reception_ident and clinical_ident and reception_ident != clinical_ident:
            mismatches.append('identificación')
        if reception_birth and clinical_birth and reception_birth != clinical_birth:
            mismatches.append('fecha de nacimiento')
        if mismatches:
            result['data_discrepancies'] += 1
            issues.append({'kind': 'data_difference', 'patient_id': reception_id,
                           'patient': name, 'description': 'Diferencia de ' + ' y '.join(mismatches) + '.'})
    result.update(ok=True, history_checked=True, issues=issues[:60],
                  message='Auditoría completa. Los vínculos y datos existentes permanecen intactos.')
    return result



# 4.8.16 — Resumen local y lista de espera exclusivamente administrativa.
# La nueva tabla SQLite es aislada; nunca escribe en Neon ni toca facturas,
# turnos, citas existentes o expedientes clínicos.
_WAITLIST_4816_READY = False
_WAITLIST_4816_LOCK = core.threading.Lock()
_WAITLIST_4816_DDL = """
CREATE TABLE IF NOT EXISTS reception_waitlist_4816 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    desired_date TEXT NOT NULL DEFAULT '',
    desired_time TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

def _waitlist_4816_init(db):
    global _WAITLIST_4816_READY
    if _WAITLIST_4816_READY:
        return
    with _WAITLIST_4816_LOCK:
        if not _WAITLIST_4816_READY:
            db.execute(core.text(_WAITLIST_4816_DDL))
            db.commit()
            _WAITLIST_4816_READY = True


def _waitlist_4816_date_time(desired_date, desired_time):
    from datetime import date
    date_text = str(desired_date or '').strip()
    time_text = str(desired_time or '').strip()
    if date_text:
        try:
            if date.fromisoformat(date_text).isoformat() != date_text:
                raise ValueError()
        except ValueError:
            raise core.HTTPException(400, 'La fecha deseada no es válida.')
    if time_text:
        parts = time_text.split(':')
        if (len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2
            or not all(p.isdigit() for p in parts)
            or int(parts[0]) > 23 or int(parts[1]) > 59):
            raise core.HTTPException(400, 'La hora deseada debe ser HH:MM.')
    return date_text, time_text


@app.get('/api/ops/today')
def reception_4816_today(user=core.Depends(core.current_user)):
    """Solo SQLite local, activada al abrir Inicio; cero consultas Neon."""
    from datetime import date
    today = date.today()
    with core.LocalSessionLocal() as db:
        visits = list(db.scalars(core.select(core.Visit).where(core.Visit.fecha == today).limit(600)))
        appointments = list(db.scalars(core.select(core.Appointment).where(
            core.Appointment.fecha == today,
            core.Appointment.origen != core.CONFIRMAFY_ATTENDED_ORIGIN,
        ).limit(600)))
        external = list(db.scalars(core.select(core.ConfirmafyAgendaItem).where(
            core.ConfirmafyAgendaItem.fecha == today
        ).limit(600)))
    valid_visits = [v for v in visits if str(getattr(v,'estado','') or '').upper()
                    not in {'CANCELADA','CANCELADO'}]
    reviews = sum(1 for v in valid_visits if core.is_exam_review_no_charge(v))
    consultations = sum(1 for v in valid_visits if not str(getattr(v,'procedimiento','') or '').strip()
                        and not core.is_exam_review_no_charge(v))
    scheduled = sum(1 for a in appointments if str(getattr(a,'estado','') or '').upper()
                    not in {'CANCELADA','CANCELADO','NO_ASISTIRA','NO_ASISTIRÁ'})
    return {'ok': True, 'date': today.isoformat(), 'consultations': consultations,
            'exam_reviews': reviews, 'scheduled_today': scheduled+len(external),
            'source': 'local_sqlite', 'no_cloud_queries': True}


class ReceptionWaitlist4816In(core.BaseModel):
    patient_id: int
    desired_date: str = ''
    desired_time: str = ''
    note: str = ''


@app.get('/api/ops/waitlist')
def reception_4816_waitlist_list(
    date_filter: str = '', time_filter: str = '', include_closed: bool = False,
    user=core.Depends(core.current_user),
):
    desired_date, desired_time = _waitlist_4816_date_time(date_filter, time_filter)
    filters = [] if include_closed else ["status='OPEN'"]
    params = {}
    if desired_date:
        filters.append("(desired_date='' OR desired_date=:desired_date)")
        params['desired_date'] = desired_date
    if desired_time:
        filters.append("(desired_time='' OR desired_time=:desired_time)")
        params['desired_time'] = desired_time
    where = ' WHERE ' + ' AND '.join(filters) if filters else ''
    with core.LocalSessionLocal() as db:
        _waitlist_4816_init(db)
        raw = db.execute(core.text(
            "SELECT id,patient_id,desired_date,desired_time,note,status,created_at "
            "FROM reception_waitlist_4816" + where + " ORDER BY id DESC LIMIT 80"
        ), params).mappings().all()
        patient_ids = sorted({int(r['patient_id']) for r in raw})
        people = {}
        if patient_ids:
            people = {int(p.id): str(p.nombre or '') for p in db.scalars(
                core.select(core.Patient).where(core.Patient.id.in_(patient_ids))
            )}
        items = [dict(r) | {'patient': people.get(int(r['patient_id']), 'Paciente no encontrado')}
                 for r in raw]
    return {'ok': True, 'items': items, 'count': len(items),
            'source': 'local_sqlite', 'no_messages_sent': True}


@app.post('/api/ops/waitlist')
def reception_4816_waitlist_add(
    data: ReceptionWaitlist4816In, user=core.Depends(core.current_user),
):
    from datetime import date
    desired_date, desired_time = _waitlist_4816_date_time(data.desired_date, data.desired_time)
    if desired_date and date.fromisoformat(desired_date) < date.today():
        raise core.HTTPException(400, 'No registres una fecha ya vencida.')
    note = ' '.join(str(data.note or '').split())[:220]
    patient_id = int(data.patient_id)
    if patient_id <= 0:
        raise core.HTTPException(400, 'Selecciona un paciente válido.')
    with core.LocalSessionLocal() as db:
        if not db.get(core.Patient, patient_id):
            raise core.HTTPException(404, 'Paciente no encontrado en Recepción.')
        # Un paciente recién creado offline debe sincronizar su ID antes.
        in_queue = db.scalar(core.select(core.OfflineQueue.id).where(
            core.OfflineQueue.entity == 'patient',
            core.OfflineQueue.local_entity_id == patient_id
        ).limit(1))
        if in_queue is not None:
            raise core.HTTPException(409, 'Espera a sincronizar este paciente antes de agregarlo.')
        _waitlist_4816_init(db)
        found = db.execute(core.text(
            "SELECT id FROM reception_waitlist_4816 WHERE patient_id=:pid "
            "AND desired_date=:day AND desired_time=:hour AND status='OPEN' LIMIT 1"
        ), {'pid': patient_id, 'day': desired_date, 'hour': desired_time}).scalar()
        if found is not None:
            return {'ok': True, 'id': int(found), 'already_exists': True}
        row_id = db.execute(core.text(
            "INSERT INTO reception_waitlist_4816(patient_id,desired_date,desired_time,note) "
            "VALUES(:pid,:day,:hour,:note) RETURNING id"
        ), {'pid':patient_id,'day':desired_date,'hour':desired_time,'note':note}).scalar_one()
        db.commit()
    return {'ok': True, 'id': int(row_id), 'already_exists': False, 'no_messages_sent': True}


@app.post('/api/ops/waitlist/{waitlist_id}/close')
def reception_4816_waitlist_close(waitlist_id: int, user=core.Depends(core.current_user)):
    with core.LocalSessionLocal() as db:
        _waitlist_4816_init(db)
        changed = db.execute(core.text(
            "UPDATE reception_waitlist_4816 SET status='CLOSED',updated_at=datetime('now') "
            "WHERE id=:id AND status='OPEN'"
        ), {'id':int(waitlist_id)})
        db.commit()
    return {'ok': True, 'updated': int(changed.rowcount or 0),
            'history_kept': True, 'no_messages_sent': True}


@app.get('/api/v4501/health')
def v4501_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'stable_runtime_chain': True, 'experimental_runtime_consolidation': False, 'redundant_js_blocks_removed': REMOVED_REDUNDANT_JS_BLOCKS, 'redundant_timeouts_removed': REMOVED_REDUNDANT_TIMEOUTS, 'new_mutation_observers': 0, 'persistent_timers_added': 0, 'maintenance_tab': True, 'printer_test': True, 'safe_cleanup': True, 'database_changes': False, 'neon_writes_added': False, 'receipt_layout_version': '4.4.69', 'payment_proof_layout_version': '4.4.88', 'billing_form_layout_version': '4.4.91'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
