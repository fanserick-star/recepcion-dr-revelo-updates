from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_26_neon_optimization'
OUT=ROOT/'updates/v4_4_27_neon_ultra'
VERSION='4.4.27'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')

assert 'APP_VERSION = "4.4.26"' in app
assert "const VERSION=\\'4.4.26\\';" in app
assert '/static/app.js?v=4.4.26' in html
assert 'CACHE_REFRESH_SECONDS = 3600' in app
assert 'REMOTE_REFRESH_IDLE_SECONDS = 30 * 60' in app
assert 'def refresh_local_cache(force: bool = False, cloud_already_checked: bool = False) -> bool:' in app
assert 'def schedule_local_cache_refresh(force: bool = False, cloud_already_checked: bool = False) -> bool:' in app

app=app.replace('APP_VERSION = "4.4.26"','APP_VERSION = "4.4.27"',1)
app=app.replace("const VERSION=\\'4.4.26\\';","const VERSION=\\'4.4.27\\';",1)
html=html.replace('/static/app.js?v=4.4.26','/static/app.js?v=4.4.27',1)

# La copia completa contiene pacientes, atenciones y facturación; casi todo eso se
# escribe desde esta misma PC y ya se espeja a SQLite al instante. Renovarla cada
# hora desperdicia lecturas/transferencia. La dejamos como reconciliación profunda
# cada 12 h; Agenda tiene su refresco ligero independiente cada 30 min cuando hace falta.
app=app.replace('CACHE_REFRESH_SECONDS = 3600','CACHE_REFRESH_SECONDS = 12 * 60 * 60\nAGENDA_CACHE_REFRESH_SECONDS = 30 * 60',1)

# Una copia completa también cuenta como Agenda actualizada.
old_stamp='''            cache_meta_set(ldb, "last_sync", datetime.now().isoformat(timespec="seconds"))\n            ldb.commit()'''
new_stamp='''            _sync_stamp = datetime.now().isoformat(timespec="seconds")\n            cache_meta_set(ldb, "last_sync", _sync_stamp)\n            cache_meta_set(ldb, "last_agenda_sync", _sync_stamp)\n            ldb.commit()'''
assert old_stamp in app
app=app.replace(old_stamp,new_stamp,1)

# Refresco remoto ultraligero: solo las dos tablas que pueden cambiar desde fuera
# de la PC (Agenda web, autoagendamiento y respuestas de confirmación). No descarga
# pacientes, visitas, facturación, usuarios ni procedimientos.
marker='''def schedule_local_cache_refresh(force: bool = False, cloud_already_checked: bool = False) -> bool:\n'''
assert marker in app
agenda_refresh=r'''
def effective_agenda_refresh_ts() -> float:
    raw = cache_meta_get("last_agenda_sync") or cache_meta_get("last_sync")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except Exception:
        return 0.0


def refresh_remote_agenda_cache(force: bool = False, cloud_already_checked: bool = False) -> bool:
    """Trae únicamente Agenda desde Neon; el resto de Recepción permanece local.

    Se usa al arrancar o volver de una pausa larga cuando la copia completa todavía
    es reciente. Así incorporamos autoagendadas/reagendamientos/confirmaciones sin
    releer pacientes, visitas y facturación completas.
    """
    if not cloud_configured() or FORCE_OFFLINE or queue_count() > 0:
        return False
    last_refresh = effective_agenda_refresh_ts()
    if not force and last_refresh and time.time() - last_refresh < AGENDA_CACHE_REFRESH_SECONDS:
        return True
    if not cloud_already_checked and not check_cloud(force=False):
        return False
    if not _cache_refresh_lock.acquire(blocking=False):
        return True
    try:
        week_start = date.today() - timedelta(days=date.today().weekday())
        with CloudSessionLocal() as cdb, LocalSessionLocal() as ldb:
            appointments = list(cdb.scalars(
                select(Appointment)
                .where(Appointment.fecha >= week_start)
                .order_by(Appointment.id)
            ))
            staged = list(cdb.scalars(
                select(ConfirmafyAgendaItem)
                .where(ConfirmafyAgendaItem.fecha >= week_start)
                .order_by(ConfirmafyAgendaItem.id)
            ))

            # Cola vacía = no existen cambios locales sin subir que podamos pisar.
            ldb.execute(delete(Appointment).where(Appointment.fecha >= week_start))
            ldb.execute(delete(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.fecha >= week_start))
            ldb.flush()
            ldb.add_all([Appointment(
                id=a.id, patient_id=a.patient_id, fecha=a.fecha, hora=a.hora,
                duracion=a.duracion, nota=a.nota, estado=a.estado, origen=a.origen,
                exported_at=a.exported_at, loaded_at=a.loaded_at,
                created_at=a.created_at, updated_at=a.updated_at,
            ) for a in appointments])
            ldb.add_all([ConfirmafyAgendaItem(
                id=a.id, nombre=a.nombre, celular=a.celular, fecha=a.fecha,
                hora=a.hora, duracion=a.duracion, source_hash=a.source_hash,
                created_at=a.created_at,
            ) for a in staged])
            cache_meta_set(ldb, "last_agenda_sync", datetime.now().isoformat(timespec="seconds"))
            ldb.commit()
        now = time.time()
        with _state_lock:
            _state["online"] = True
            _state["last_success"] = now
            _state["last_checked"] = now
            _state["consecutive_failures"] = 0
            _state["last_error"] = ""
        return True
    except Exception as e:
        with _state_lock:
            _state["last_error"] = f"No se pudo actualizar Agenda desde la nube: {e}"[:300]
        return False
    finally:
        _cache_refresh_lock.release()


def schedule_remote_agenda_refresh(force: bool = False, cloud_already_checked: bool = False) -> bool:
    """Agenda remota bajo demanda; nunca crea un temporizador contra Neon."""
    if not cloud_configured() or FORCE_OFFLINE or queue_count() > 0:
        return False
    last_refresh = effective_agenda_refresh_ts()
    due = force or not last_refresh or (time.time() - last_refresh >= AGENDA_CACHE_REFRESH_SECONDS)
    if not due or _cache_refresh_lock.locked():
        return False
    threading.Thread(
        target=refresh_remote_agenda_cache,
        kwargs={"force": force, "cloud_already_checked": cloud_already_checked},
        daemon=True,
        name="rp-agenda-refresh",
    ).start()
    return True


'''
app=app.replace(marker,agenda_refresh+marker,1)

# Al iniciar ya hay una única comprobación real. Si la copia total aún sirve,
# aprovechamos esa misma ventana activa para traer solo Agenda en vez de 9 tablas.
old_init_tail='''        schedule_local_cache_refresh(force=force_cleanup_refresh, cloud_already_checked=True)'''
new_init_tail='''        full_scheduled = schedule_local_cache_refresh(force=force_cleanup_refresh, cloud_already_checked=True)
        if not full_scheduled:
            schedule_remote_agenda_refresh(force=False, cloud_already_checked=True)'''
assert old_init_tail in app
app=app.replace(old_init_tail,new_init_tail,1)

# Volver de AFK corto ya NO despierta Neon. Solo reanuda SQLite. Neon se toca si
# existe cola pendiente o si la ausencia fue suficientemente larga para justificar
# incorporar cambios remotos. En ese caso preferimos Agenda ligera salvo que toque
# la reconciliación completa de 12 h.
old_wake='''    configured = cloud_configured()\n    online = check_cloud(force=True) if configured else False\n    sync_result = None\n    if online and queue_count() > 0:\n        sync_result = process_offline_queue(cloud_already_checked=True)\n    refresh_scheduled = False\n    if online and queue_count() == 0:\n        # Si la PC quedó abandonada bastante tiempo (por ejemplo al salir del\n        # consultorio), al volver actualizamos la copia en segundo plano para\n        # incorporar cambios que pudieron hacerse desde otra PC. Pausas cortas\n        # no descargan Neon completa.\n        refresh_scheduled = schedule_local_cache_refresh(force=idle_for >= REMOTE_REFRESH_IDLE_SECONDS, cloud_already_checked=True)\n    payload = _connectivity_payload(configured=configured, online=online)\n    payload["idle_for_seconds"] = round(idle_for)\n    payload["cache_refresh_scheduled"] = bool(refresh_scheduled)'''
new_wake='''    configured = cloud_configured()\n    pending = queue_count()\n    with _state_lock:\n        cached_online = bool(_state.get("online")) if configured else False\n    cloud_wake_needed = bool(configured and (pending > 0 or idle_for >= REMOTE_REFRESH_IDLE_SECONDS))\n    online = check_cloud(force=True) if cloud_wake_needed else cached_online\n    sync_result = None\n    if online and pending > 0:\n        sync_result = process_offline_queue(cloud_already_checked=True)\n        pending = queue_count()\n    refresh_scheduled = False\n    refresh_kind = "none"\n    if online and pending == 0 and idle_for >= REMOTE_REFRESH_IDLE_SECONDS:\n        last_full = effective_cache_refresh_ts()\n        full_due = (not last_full) or (time.time() - last_full >= CACHE_REFRESH_SECONDS)\n        if full_due:\n            refresh_scheduled = schedule_local_cache_refresh(force=False, cloud_already_checked=True)\n            refresh_kind = "full" if refresh_scheduled else "none"\n        else:\n            refresh_scheduled = schedule_remote_agenda_refresh(force=False, cloud_already_checked=True)\n            refresh_kind = "agenda" if refresh_scheduled else "none"\n    payload = _connectivity_payload(configured=configured, online=online)\n    payload["idle_for_seconds"] = round(idle_for)\n    payload["cache_refresh_scheduled"] = bool(refresh_scheduled)\n    payload["cache_refresh_kind"] = refresh_kind\n    payload["cloud_wake_skipped"] = bool(configured and not cloud_wake_needed)'''
assert old_wake in app
app=app.replace(old_wake,new_wake,1)

# Mensaje de retorno coherente: primero abre SQLite; no promete una conexión Neon.
old_ui="setConnectionBadge('syncing','Reanudando','Comprobando la nube solo porque volviste a usar Recepción…');"
new_ui="setConnectionBadge('syncing','Reanudando','Abriendo la copia local · Neon solo se usará si realmente hace falta…');"
assert old_ui in js
js=js.replace(old_ui,new_ui,1)

write(OUT/'app.py',app)
write(OUT/'static/app.js',js)
write(OUT/'static/index.html',html)
manifest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
  'copy':['app.py','static/app.js','static/index.html','update_manifest.json']
}
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
base_url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_27_neon_ultra/'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel
    files.append({'path':rel,'url':base_url+rel,'sha256':sha(p),'encoding':'utf-8'})
latest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'mandatory':True,'channel':'files-v3',
  'message':'v4.4.27: ultra optimización Neon en Recepción. Volver de pausas cortas ya no despierta Neon; trabaja desde SQLite. La sincronización remota habitual trae solo Agenda/autoagendadas y la reconciliación completa pasa a cada 12 horas o cuando realmente hace falta. Conserva cola offline, AFK y todos los datos locales.',
  'files':files
}
write(ROOT/'build/v4427_neon_ultra/candidate_latest.json',json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
print('V4427_NEON_ULTRA_BUILD_OK')
