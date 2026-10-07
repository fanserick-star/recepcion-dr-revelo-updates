from __future__ import annotations
import reception_history_bridge as _dep_history_bridge
import reception_payment_terminal_panel as _dep_payment_terminal_panel
import features_runtime
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import historia_bridge
core = _dep_payment_terminal_panel.core
app = _dep_payment_terminal_panel.app
import reception_deleted_visit_guard as _deleted_visit_guard
_VERSION_PATH = Path(__file__).with_name('recepcion-version.json')
_VERSION_DOC = json.loads(_VERSION_PATH.read_text(encoding='utf-8'))
APP_VERSION = str(_VERSION_DOC['version']).strip()
if not APP_VERSION:
    raise RuntimeError('recepcion-version.json no contiene una versión válida')
core.APP_VERSION = APP_VERSION
V4533_VERSION_CSS = f'\n.v460-version::after,#currentVersionBadge::after{{\n  content:"v{APP_VERSION}"!important;\n}}\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4533_VERSION_CSS
_LAUNCHER_APP_CHANNEL = 'https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/launcher-v1/app-channel.json'

def _canonical_update_channel_status():
    started = time.perf_counter()
    req = urllib.request.Request(_LAUNCHER_APP_CHANNEL + f'?rp_ts={time.time_ns()}', headers={'User-Agent': f'Recepcion-Dr-Revelo/{APP_VERSION}', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=8) as response:
        remote = json.loads(response.read(512000).decode('utf-8-sig'))
    latest = str(remote.get('appVersion') or '').strip()
    if remote.get('product') != 'recepcion-dr-revelo' or not latest:
        raise RuntimeError('El canal de Recepción respondió con un manifiesto no válido')

    def _vt(value):
        out = []
        for part in str(value or '0').split('.'):
            digits = ''.join((ch for ch in part if ch.isdigit()))
            out.append(int(digits or 0))
        return tuple((out + [0, 0, 0, 0])[:4])
    return {'local': APP_VERSION, 'latest': latest, 'update_available': _vt(latest) > _vt(APP_VERSION), 'latency_ms': (time.perf_counter() - started) * 1000}
core._read_update_channel_status = _canonical_update_channel_status
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/program/update-now' and 'POST' in (getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.post('/api/program/update-now')
def program_update_now_canonical():
    try:
        info = _canonical_update_channel_status()
        if info['update_available']:
            return {'ok': True, 'update': True, 'mandatory': True, 'current': APP_VERSION, 'latest': info['latest'], 'message': f"Actualización obligatoria {info['latest']} disponible. Cierra y abre Recepción para instalarla antes de continuar."}
        return {'ok': True, 'update': False, 'mandatory': True, 'current': APP_VERSION, 'latest': info['latest'], 'message': f'Recepción {APP_VERSION} está actualizada.'}
    except Exception as exc:
        return {'ok': False, 'update': False, 'mandatory': True, 'current': APP_VERSION, 'message': f'No se pudo consultar el canal: {str(exc)[:200]}'}

def _v4541_consultation_turn(visit):
    if visit is None or str(getattr(visit, 'procedimiento', '') or '').strip():
        return None
    fecha = getattr(visit, 'fecha', None)
    patient_id = int(getattr(visit, 'patient_id', 0) or 0)
    if not fecha or not patient_id:
        return None
    with core.LocalSessionLocal() as local_db:
        rows = list(local_db.scalars(core.select(core.Visit).where(core.Visit.fecha == fecha).order_by(core.Visit.id.desc())))
        hidden = set()
        try:
            hidden = set(core.active_deleted_visit_ids(local_db))
        except Exception:
            hidden = set()
        if hidden:
            rows = [row for row in rows if int(getattr(row, 'id', 0) or 0) not in hidden]
    groups = {}
    order = []
    for row in rows:
        pid = int(getattr(row, 'patient_id', 0) or 0)
        if pid not in groups:
            groups[pid] = {'first_visit_id': int(getattr(row, 'id', 0) or 0), 'has_consultation': False}
            order.append(pid)
        item = groups[pid]
        rid = int(getattr(row, 'id', 0) or 0)
        if not item['first_visit_id'] or (rid and rid < item['first_visit_id']):
            item['first_visit_id'] = rid
        if not str(getattr(row, 'procedimiento', '') or '').strip():
            item['has_consultation'] = True
    ordered_groups = sorted(groups.items(), key=lambda pair: int(pair[1]['first_visit_id'] or 0))
    turn = 0
    for pid, item in ordered_groups:
        if not item['has_consultation']:
            continue
        turn += 1
        if int(pid) == patient_id:
            return turn
    return None
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.post('/api/visits/batch-payment')
def v4535_create_visit_batch_payment(data: _dep_history_bridge.payment_core.V4504VisitBatchPaymentIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    try:
        _hist_patient = db.get(core.Patient, int(data.patient_id))
        if _hist_patient and core.historical_summary_for_patient(_hist_patient):
            try:
                data.tipo = 'S'
            except Exception:
                object.__setattr__(data, 'tipo', 'S')
    except Exception:
        pass
    result = _dep_history_bridge._old_batch(data, db, user)
    try:
        patient = db.get(core.Patient, int(data.patient_id))
        if patient:
            services = list(getattr(data, 'services', None) or [])
            procedures = [str(getattr(x, 'procedimiento', '') or '').strip() for x in services]
            has_consultation = not services or any((not x for x in procedures))
            items = list((result or {}).get('items') or []) if isinstance(result, dict) else []
            visit_ids = [x.get('id') for x in items if isinstance(x, dict) and x.get('id') is not None]
            type_code = str(getattr(data, 'tipo', '') or '').strip().upper()
            if not type_code and items and isinstance(items[0], dict):
                type_code = str(items[0].get('tipo') or '').strip().upper()
            patient_status = {'N': 'Nuevo', 'S': 'Subsecuente'}.get(type_code, '')
            if has_consultation:
                attention_type = 'Consulta'
            else:
                _procedure_names = []
                for _procedure in procedures:
                    _name = ' '.join(str(_procedure or '').split()).upper()
                    if _name and _name not in _procedure_names:
                        _procedure_names.append(_name)
                attention_type = 'Procedimiento'
                if _procedure_names:
                    attention_type += ' · ' + ' / '.join(_procedure_names)
            reception_turn = None
            if has_consultation and visit_ids:
                created_visits = list(db.scalars(core.select(core.Visit).where(core.Visit.id.in_([int(x) for x in visit_ids if x is not None]))))
                consultation_visit = next((v for v in sorted(created_visits, key=lambda x: int(x.id)) if not str(getattr(v, 'procedimiento', '') or '').strip()), None)
                reception_turn = _v4541_consultation_turn(consultation_visit)
            birth = getattr(patient, 'fecha_nacimiento', None)
            historia_bridge.queue_attention(reception_patient_id=int(patient.id), display_name=str(getattr(patient, 'nombre', '') or 'Paciente'), identification=str(getattr(patient, 'cedula', '') or ''), attention_type=attention_type, patient_status=patient_status, reception_turn=reception_turn, visit_ids=visit_ids, birth_date=str(birth or ''), phone=str(getattr(patient, 'celular', '') or ''), email=str(getattr(patient, 'correo', '') or ''), address=str(getattr(patient, 'lugar', '') or ''))
    except Exception as exc:
        try:
            core.audit(db, user, 'historia_bridge_pending', f'Puente Historia Clínica pendiente: {type(exc).__name__}')
            db.commit()
        except Exception:
            pass
    return result

@app.on_event('startup')
def _v4541_repair_recent_historia_handoffs():
    """Repara y reenvía por LAN + nube los handoffs recientes con el turno EXACTO de Inicio."""
    try:
        outbox = historia_bridge.OUTBOX_DB
        if not outbox.is_file():
            return
        cutoff = (datetime.now() - timedelta(days=2)).isoformat(timespec='seconds')
        resend = []
        with core.LocalSessionLocal() as db:
            with sqlite3.connect(outbox, timeout=8) as local:
                local.row_factory = sqlite3.Row
                rows = local.execute('SELECT event_id,payload_json FROM events WHERE created_at>=? AND cancelled=0 ORDER BY created_at', (cutoff,)).fetchall()
                for row in rows:
                    try:
                        payload = json.loads(row['payload_json'])
                    except Exception:
                        continue
                    if str(payload.get('action') or 'handoff').lower() != 'handoff':
                        continue
                    ids = []
                    for value in payload.get('visit_ids') or []:
                        try:
                            ids.append(int(value))
                        except Exception:
                            pass
                    if not ids:
                        continue
                    visits = list(db.scalars(core.select(core.Visit).where(core.Visit.id.in_(ids))))
                    if not visits:
                        continue
                    has_consultation = any((not str(getattr(v, 'procedimiento', '') or '').strip() for v in visits))
                    first_type = str(getattr(visits[0], 'tipo', '') or '').strip().upper()
                    wanted_status = {'N': 'Nuevo', 'S': 'Subsecuente'}.get(first_type, '')
                    wanted_type = 'Consulta' if has_consultation else 'Procedimiento'
                    consultation_visit = next((v for v in sorted(visits, key=lambda x: int(x.id)) if not str(getattr(v, 'procedimiento', '') or '').strip()), None)
                    wanted_turn = _v4541_consultation_turn(consultation_visit) if has_consultation else None
                    try:
                        current_turn = int(payload.get('reception_turn')) if payload.get('reception_turn') not in (None, '') else None
                    except Exception:
                        current_turn = None
                    needs_repair = str(payload.get('attention_type') or '') != wanted_type or str(payload.get('patient_status') or '') != wanted_status or current_turn != wanted_turn
                    if not needs_repair:
                        continue
                    payload['attention_type'] = wanted_type
                    payload['patient_status'] = wanted_status
                    payload['reception_turn'] = wanted_turn
                    local.execute("UPDATE events SET payload_json=?,sent_at=NULL,attempts=0,last_attempt_at=NULL,last_error='' WHERE event_id=?", (json.dumps(payload, ensure_ascii=False, separators=(',', ':')), row['event_id']))
                    resend.append(payload)
                if resend:
                    local.commit()
        for payload in resend:
            try:
                historia_bridge.queue_attention(reception_patient_id=payload.get('reception_patient_id'), display_name=payload.get('display_name') or 'Paciente', identification=payload.get('identification') or '', attention_type=payload.get('attention_type') or 'Consulta', patient_status=payload.get('patient_status') or '', reception_turn=payload.get('reception_turn'), visit_ids=list(payload.get('visit_ids') or []), birth_date=payload.get('birth_date') or '', phone=payload.get('phone') or '', email=payload.get('email') or '', address=payload.get('address') or '')
            except Exception:
                pass
        if resend:
            try:
                historia_bridge.flush_pending(max_items=100, background=True)
            except Exception:
                pass
    except Exception:
        pass

@app.get('/api/v4535/health')
def v4535_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_attention_kind_from_services': True, 'historia_cloud_schema': 'historia', 'repairs_recent_handoffs': True, 'database_schema_changes': False, 'reception_ui_changes': False}

@app.get('/api/v4533/health')
def v4533_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'version_chain_synced': True, 'visual_version_synced': True, 'database_schema_changes': False, 'preserves_data_env_excel': True}

@app.on_event('startup')
def _v4536_flush_historia_backlog():
    try:
        historia_bridge.flush_pending(max_items=200, background=True)
    except Exception:
        pass

@app.get('/api/v4541/health')
def v4541_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_turn_source': 'reception_local_visible_list', 'startup_repair_uses_local_cache': True, 'startup_repair_resends_lan_and_cloud': True, 'procedures_consume_turn': False}

@app.get('/api/v4539/health')
def v4539_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_turn_source': 'reception_exact', 'turn_matches_reception_daily_list': True, 'procedures_consume_turn': False}

@app.get('/api/v4537/health')
def v4537_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'historia_service_kind_separated': True, 'patient_status_separated': True, 'consultations_consume_turn': True, 'procedures_consume_turn': False, 'database_schema_changes': False, 'reception_data_changes': False}

@app.get('/api/v4536/health')
def v4536_health(user=core.Depends(core.current_user)):
    status = historia_bridge.bridge_status()
    return {'ok': True, 'version': APP_VERSION, 'historia_bridge_recovery': True, 'historia_remote_unique_event': True, 'historia_pending': int(status.get('pending') or 0), 'historia_last_error': str(status.get('last_error') or '')[:220], 'status_retry_seconds': 60, 'database_schema_changes': False, 'reception_data_changes': False}
_V4543_BASE_ACTIVATE_HISTORICAL = core.activate_historical_patient
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/historical/{hid}/activate' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

@app.post('/api/historical/{hid}/activate')
def v4543_activate_historical_patient(hid: int, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    source_key = ''
    try:
        with core.LocalSessionLocal() as ldb:
            historical = ldb.get(core.HistoricalPatient, int(hid))
            if historical is None:
                raise core.HTTPException(404, 'Paciente histórico no encontrado')
            source_key = str(historical.source_key or '')
    except core.HTTPException:
        raise
    except Exception:
        source_key = ''
    result = _V4543_BASE_ACTIVATE_HISTORICAL(int(hid), db, user)
    patient_id = int((result or {}).get('id') or 0)
    if patient_id and source_key:
        core._historical_link_patient(source_key, patient_id)
    if isinstance(result, dict):
        historical_summary = result.get('historical')
        result['historical_summary'] = historical_summary
        result['historical'] = False
        result['activated_from_historical'] = True
        result['suggested_type'] = 'S'
    return result
V4543_PRINT_MENU_CSS = '\n/* v4.5.43 — el desplegable Imprimir no puede salir por debajo del cuadro.\n   La tabla de Inicio tiene overflow para conservarse usable en la PC antigua;\n   por eso el menú abre hacia ARRIBA del botón, donde sí hay espacio visible. */\n#inicio .v4486-print-menu{\n  position:relative!important;\n}\n#inicio .v4486-print-menu[open]{\n  z-index:2147483000!important;\n}\n#inicio .v4486-print-pop{\n  top:auto!important;\n  bottom:calc(100% + 6px)!important;\n  right:0!important;\n  z-index:2147483001!important;\n  margin:0!important;\n}\n#inicio .v4486-print-pop button{\n  position:relative!important;\n  z-index:2147483002!important;\n}\n'
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4543_PRINT_MENU_CSS

@app.get('/api/v4543/health')
def v4543_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'rebuilt_from': '4.5.41', 'inherits_v4542_logic': False, 'historical_click_activates': True, 'historical_link_persisted': True, 'historical_data_completes_empty_fields': True, 'historical_attention_subsequent': True, 'print_menu_opens_upward': True, 'database_schema_changes': False, 'historia_clinica_changes': False}
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/v4470/print-visit/{visit_id}' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        app.router.routes.remove(_route)

class _V4544PrintVisitIn(core.BaseModel):
    pass

@app.post('/api/v4470/print-visit/{visit_id}')
def v4544_print_visit_exact_status(visit_id: int, data: _V4544PrintVisitIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    visit = db.get(core.Visit, int(visit_id))
    if not visit:
        return {'ok': True, 'printed': False, 'reason': 'visit_not_found', 'message': 'Atención guardada, pero no se encontró el registro para imprimir.'}
    if str(getattr(visit, 'procedimiento', '') or '').strip():
        return {'ok': True, 'printed': False, 'reason': 'procedure_only', 'message': 'Atención guardada. Los procedimientos no generan recibo.'}
    patient = db.get(core.Patient, int(visit.patient_id))
    if not patient:
        return {'ok': True, 'printed': False, 'reason': 'patient_not_found', 'message': 'Atención guardada, pero no se encontró el paciente para imprimir.'}
    tipo = str(getattr(visit, 'tipo', '') or '').strip().upper()
    is_new = tipo == 'N'
    turn = _v4541_consultation_turn(visit)
    birth = None
    if getattr(patient, 'fecha_nacimiento', None):
        try:
            birth = patient.fecha_nacimiento.strftime('%d/%m/%Y')
        except Exception:
            birth = str(patient.fecha_nacimiento)
    payload = core.ReceiptPrintIn(fecha=visit.fecha.strftime('%d/%m/%Y'), nombre=str(patient.nombre or '').strip().upper(), fecha_nacimiento=birth, celular=str(patient.celular or '').strip() or None, turno=turn, is_new=is_new)
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = core._print_receipt_windows(payload, printer, bool(prefs.get('show_blood_pressure', True)))
        return {'ok': True, 'printed': True, 'printer': used, 'turno': turn, 'tipo': tipo, 'is_new': is_new, 'message': 'Atención guardada. Recibo enviado a la impresora.'}
    except Exception as exc:
        try:
            core.logging.getLogger(__name__).warning('v4.5.44: atención %s guardada, impresión falló: %s', visit_id, exc)
        except Exception:
            pass
        return {'ok': True, 'printed': False, 'reason': 'printer_error', 'turno': turn, 'tipo': tipo, 'is_new': is_new, 'error': str(exc)[:240], 'message': 'Atención guardada. No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.'}
V4544_PRINT_PORTAL_CSS = '\n.v4544-print-portal{\n  position:fixed!important;\n  z-index:2147483640!important;\n  display:grid!important;\n  gap:5px!important;\n  min-width:190px!important;\n  padding:7px!important;\n  border:1px solid #d7e1ec!important;\n  border-radius:11px!important;\n  background:#fff!important;\n  box-shadow:0 14px 34px rgba(35,55,80,.24)!important;\n  box-sizing:border-box!important;\n}\n.v4544-print-portal button{\n  width:100%!important;\n  min-height:38px!important;\n  display:flex!important;\n  align-items:center!important;\n  gap:8px!important;\n  border:0!important;\n  border-radius:9px!important;\n  background:#fff!important;\n  color:#344c69!important;\n  padding:9px 10px!important;\n  font-size:10px!important;\n  font-weight:850!important;\n  text-align:left!important;\n  white-space:nowrap!important;\n  cursor:pointer!important;\n}\n.v4544-print-portal button:hover{background:#f1f6fb!important}\n.v4544-print-portal button:disabled{\n  opacity:.42!important;\n  cursor:not-allowed!important;\n  background:#f7f8fa!important;\n}\n.v4544-print-portal .v488-home-action-svg{\n  width:14px!important;height:14px!important;flex:0 0 14px!important;\n}\n'
V4544_PRINT_PORTAL_JS = "\n;(()=>{\n  if(window.__v4544PrintPortal)return;\n  window.__v4544PrintPortal=true;\n\n  let portal=null;\n  let anchor=null;\n\n  function closePortal(){\n    if(portal){try{portal.remove()}catch(_){}}\n    portal=null;\n    if(anchor){\n      try{\n        anchor.closest('.v4486-print-menu')?.removeAttribute('open');\n        anchor.setAttribute('aria-expanded','false');\n      }catch(_){}\n    }\n    anchor=null;\n  }\n\n  function place(){\n    if(!portal||!anchor)return;\n    const r=anchor.getBoundingClientRect();\n    const w=Math.max(190,portal.offsetWidth||190);\n    const h=Math.max(86,portal.offsetHeight||86);\n    let left=r.right-w;\n    left=Math.max(8,Math.min(left,window.innerWidth-w-8));\n    let top;\n    // Preferimos abrir arriba, pero solo si CABE COMPLETO.\n    if(r.top>=h+10) top=r.top-h-6;\n    else top=Math.min(window.innerHeight-h-8,r.bottom+6);\n    portal.style.left=Math.round(left)+'px';\n    portal.style.top=Math.max(8,Math.round(top))+'px';\n  }\n\n  function openPortal(summary){\n    closePortal();\n    const details=summary.closest('.v4486-print-menu');\n    const source=details?.querySelector('.v4486-print-pop');\n    if(!details||!source)return;\n\n    details.removeAttribute('open');\n    anchor=summary;\n    anchor.setAttribute('aria-expanded','true');\n\n    portal=document.createElement('div');\n    portal.className='v4544-print-portal';\n    portal.setAttribute('role','menu');\n\n    [...source.querySelectorAll('button')].forEach(original=>{\n      const clone=original.cloneNode(true);\n      clone.removeAttribute('style');\n      clone.addEventListener('click',()=>{\n        setTimeout(closePortal,0);\n      },{once:true});\n      portal.appendChild(clone);\n    });\n\n    document.body.appendChild(portal);\n    place();\n  }\n\n  document.addEventListener('click',e=>{\n    const summary=e.target?.closest?.('.v4486-print-summary');\n    if(summary){\n      // Impide que <details> abra dentro de la tabla.\n      e.preventDefault();\n      e.stopPropagation();\n      openPortal(summary);\n      return;\n    }\n    if(portal&&!portal.contains(e.target))closePortal();\n  },true);\n\n  window.addEventListener('resize',closePortal,{passive:true});\n  window.addEventListener('scroll',closePortal,true);\n  document.addEventListener('keydown',e=>{\n    if(e.key==='Escape')closePortal();\n  });\n})();\n"
core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4544_PRINT_PORTAL_CSS
core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + V4544_PRINT_PORTAL_JS

@app.get('/api/v4544/health')
def v4544_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'automatic_receipt_status_source': 'visit.tipo', 'N_prints_as': 'PRIMERO', 'S_prints_as': 'SUBSECUENTE', 'automatic_receipt_turn_source': 'reception_local_visible_list', 'reprint_status_source': 'visit.tipo', 'database_schema_changes': False, 'patient_data_changes': False}
_LEGACY_DISABLED_ROUTE_PATHS = frozenset({'/api/mobile/remote/status', '/api/mobile/remote/quick/start', '/api/mobile/remote/stable/restart', '/api/mobile/remote/stop', '/api/update/apply'})

def _remove_legacy_dead_routes() -> int:
    before = len(app.router.routes)
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', None) not in _LEGACY_DISABLED_ROUTE_PATHS]
    try:
        app.openapi_schema = None
    except Exception:
        pass
    return before - len(app.router.routes)
LEGACY_DEAD_ROUTES_REMOVED = _remove_legacy_dead_routes()
LEGACY_CLOUDFLARE_TUNNEL_EXTERNAL_HELPER_REQUIRED = False
LEGACY_ZIP_UPDATER_ACTIVE = False
_V463_PERF_PRELUDE = '\n;window.__v4517HistoriaLink=true;\nwindow.__v4518RealVersion=true;\n'
core.V460_OVERLAY_JS = _V463_PERF_PRELUDE + '\n' + (getattr(core, 'V460_OVERLAY_JS', '') or '')
core.V460_OVERLAY_JS = core.V460_OVERLAY_JS.replace('setInterval(()=>fetchReal(true),30000);', '/* v4.6.3: versión en boot/focus/cambio de UI; sin polling periódico */')
core.V460_OVERLAY_JS = core.V460_OVERLAY_JS.replace('setInterval(refresh,7000);', 'setInterval(refresh,30000);')
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)
RUNTIME_CONSOLIDATED = True
RUNTIME_CONSOLIDATED_EXTERNAL_PATCH_FILES_REQUIRED = False
RUNTIME_CONSOLIDATED_EMBEDDED_MODULE_COUNT = 0
RUNTIME_AZUR_HELPER_EMBEDDED = False
RUNTIME_WHATSAPP_HELPER_EMBEDDED = False
RUNTIME_EXTERNAL_FUNCTIONAL_HELPERS_REQUIRED = True
_V466_BASE_BATCH = None
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/visits/batch-payment' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        _V466_BASE_BATCH = getattr(_route, 'endpoint', None)
        app.router.routes.remove(_route)
        break
if _V466_BASE_BATCH is None:
    raise RuntimeError('v4.6.6 no encontró la ruta activa de guardado de atención')

def _v466_local_attention_db():
    """Sesión SQLite duradera para el guardado crítico de Nueva atención."""
    db = core.LocalSessionLocal()
    try:
        db.info['offline'] = True
        db.info['local_first'] = True
        db.info['v466_attention_write_behind'] = True
        yield db
    finally:
        db.close()

def _v466_sync_attention_queue_later():

    def _worker():
        try:
            time.sleep(1.0)
            core.process_offline_queue()
        except Exception as exc:
            try:
                core.logging.getLogger(__name__).warning('v4.6.6: sync posterior a atención pendiente: %s', exc)
            except Exception:
                pass
    try:
        core.threading.Thread(target=_worker, name='rp-attention-cloud-sync', daemon=True).start()
    except Exception:
        pass

@app.post('/api/visits/batch-payment')
def v466_fast_local_attention_save(data: _dep_history_bridge.payment_core.V4504VisitBatchPaymentIn, db=core.Depends(_v466_local_attention_db), user=core.Depends(core.current_user)):
    started = time.perf_counter()
    result = _V466_BASE_BATCH(data, db, user)
    save_ms = (time.perf_counter() - started) * 1000.0
    _v466_sync_attention_queue_later()
    if isinstance(result, dict):
        result['local_first'] = True
        result['cloud_sync_scheduled'] = True
        result['save_ms'] = round(save_ms, 1)
    return result
_V466_BASE_PRINT = None
for _route in list(app.router.routes):
    if getattr(_route, 'path', None) == '/api/v4470/print-visit/{visit_id}' and 'POST' in set(getattr(_route, 'methods', set()) or set()):
        _V466_BASE_PRINT = getattr(_route, 'endpoint', None)
        app.router.routes.remove(_route)
        break
if _V466_BASE_PRINT is None:
    raise RuntimeError('v4.6.6 no encontró la ruta activa de impresión de recibo')

@app.post('/api/v4470/print-visit/{visit_id}')
def v466_print_visit_local_first(visit_id: int, data: _V4544PrintVisitIn, db=core.Depends(_v466_local_attention_db), user=core.Depends(core.current_user)):
    return _V466_BASE_PRINT(visit_id, data, db, user)
_V466_OLD_BUSY = 'Guardando atención e imprimiendo recibo…'
_V466_NEW_BUSY = 'Guardando atención…'
_V466_BUSY_REPLACEMENTS = (getattr(core, 'V460_OVERLAY_JS', '') or '').count(_V466_OLD_BUSY)
# Compatibilidad: runtimes nuevos pueden llegar ya normalizados por una capa semántica anterior.
# Si aún existe el texto legacy lo corregimos; si ya no existe, no es un error.
if _V466_BUSY_REPLACEMENTS:
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '').replace(_V466_OLD_BUSY, _V466_NEW_BUSY)

@app.get('/api/v466/health')
def v466_health(user=core.Depends(core.current_user)):
    return {'ok': True, 'version': APP_VERSION, 'attention_write': 'sqlite-first-cloud-write-behind', 'cloud_sync_background': True, 'print_source': 'sqlite-local', 'procedure_auto_print': False, 'consultation_auto_print': True, 'procedure_printing_label_removed': True, 'database_schema_changes': False, 'billing_logic_changes': False, 'azur_logic_changes': False, 'whatsapp_logic_changes': False}
