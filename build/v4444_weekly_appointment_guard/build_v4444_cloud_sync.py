from __future__ import annotations

import json

import build_v4444 as base


SYNC_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.44 — puente seguro Cloud/WhatsApp -> agenda SQLite visible.
    # -----------------------------------------------------------------------
    # La agenda de Recepción sigue leyendo SQLite. Al abrir una semana, traemos
    # únicamente las citas externas de esos siete días desde Neon y las copiamos
    # a ConfirmafyAgendaItem local. No crea Patients, no migra tablas, no borra
    # filas locales y se omite por completo si existe una cola offline pendiente.
    _v4444_cloud_staged_lock = core.threading.Lock()
    _v4444_cloud_staged_at = {}

    def _v4444_sync_cloud_staged_for_dates(dates, min_interval: float = 5.0) -> int:
        normalized = []
        for value in dates or []:
            try:
                item_date = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
            except Exception:
                continue
            if item_date not in normalized:
                normalized.append(item_date)
        normalized.sort()
        if not normalized:
            return 0
        if not core.cloud_configured() or core.FORCE_OFFLINE or not core.CloudSessionLocal:
            return 0
        if core.queue_count() > 0:
            return 0

        key = "|".join(x.isoformat() for x in normalized)
        now = core.time.time()
        if not _v4444_cloud_staged_lock.acquire(blocking=False):
            return 0
        try:
            last = float(_v4444_cloud_staged_at.get(key) or 0.0)
            if last and now - last < max(1.0, float(min_interval or 5.0)):
                return 0
            if not core.check_cloud(force=False):
                return 0

            changed = 0
            with core.CloudSessionLocal() as cdb, core.LocalSessionLocal() as ldb:
                rows = list(cdb.scalars(
                    core.select(core.ConfirmafyAgendaItem)
                    .where(core.ConfirmafyAgendaItem.fecha.in_(normalized))
                    .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)
                ))
                for row in rows:
                    source_hash = str(getattr(row, "source_hash", "") or "").strip()
                    if not source_hash or source_hash.startswith("mobile:whatsapp-cloud-test:"):
                        continue

                    existing = ldb.scalar(
                        core.select(core.ConfirmafyAgendaItem)
                        .where(core.ConfirmafyAgendaItem.source_hash == source_hash)
                        .limit(1)
                    )
                    if existing is not None:
                        values = {
                            "nombre": row.nombre,
                            "celular": row.celular,
                            "fecha": row.fecha,
                            "hora": row.hora,
                            "duracion": int(row.duracion or 20),
                            "created_at": row.created_at,
                        }
                        dirty = False
                        for attr, value in values.items():
                            if getattr(existing, attr, None) != value:
                                setattr(existing, attr, value)
                                dirty = True
                        if dirty:
                            changed += 1
                        continue

                    cloud_id = int(row.id)
                    # No sobreescribimos jamás otra fila local que por casualidad
                    # use el mismo ID. La copia completa normal resolverá ese caso
                    # excepcional sin arriesgar una cita existente.
                    if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:
                        continue
                    ldb.add(core.ConfirmafyAgendaItem(
                        id=cloud_id,
                        nombre=row.nombre,
                        celular=row.celular,
                        fecha=row.fecha,
                        hora=row.hora,
                        duracion=int(row.duracion or 20),
                        source_hash=source_hash,
                        created_at=row.created_at,
                    ))
                    changed += 1
                if changed:
                    ldb.commit()
            _v4444_cloud_staged_at[key] = core.time.time()
            return changed
        except Exception:
            # La agenda local debe seguir abriendo aunque Neon no responda.
            return 0
        finally:
            _v4444_cloud_staged_lock.release()

    @app.middleware("http")
    async def v4444_cloud_staged_agenda_catchup(request, call_next):
        # Solo la vista semanal necesita esta lectura. El resto del programa
        # continúa 100 % local-first y no añade sondeos periódicos a Neon.
        if request.url.path == "/api/agenda/week":
            try:
                raw_anchor = str(request.query_params.get("anchor") or "").strip()
                anchor_date = _date.fromisoformat(raw_anchor[:10])
                monday = anchor_date - core.timedelta(days=anchor_date.weekday())
                week_dates = [monday + core.timedelta(days=i) for i in range(7)]
                _v4444_sync_cloud_staged_for_dates(week_dates)
            except Exception:
                pass
        return await call_next(request)
'''


PHONE_GUARD_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.44 — protección de celular duplicado al completar/crear pacientes.
    # -----------------------------------------------------------------------
    # La protección es deliberadamente de aplicación, no un UNIQUE en la base:
    # no migra tablas ni altera datos existentes. Excluye al propio paciente al
    # editar, pero detecta el mismo 09... aunque otra ficha guarde 5939....
    @app.get("/api/identity/phone-owner")
    def v4444_phone_owner(
        phone: str,
        exclude_id: int = 0,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        normalized = core.normalize_lookup_phone(phone)
        if not normalized or len(normalized) < 9:
            return {"duplicate": False, "patient": None}
        variants = {normalized}
        if len(normalized) == 10 and normalized.startswith("0"):
            variants.add("593" + normalized[1:])
        rows = list(db.scalars(
            core.select(core.Patient)
            .where(core.Patient.celular.is_not(None))
            .order_by(core.Patient.id)
        ))
        for patient in rows:
            if int(exclude_id or 0) and int(patient.id) == int(exclude_id):
                continue
            if core.normalize_lookup_phone(patient.celular) == normalized:
                return {
                    "duplicate": True,
                    "patient": {
                        "id": int(patient.id),
                        "nombre": patient.nombre,
                        "cedula": patient.cedula,
                        "celular": patient.celular,
                    },
                    "normalized": normalized,
                }
        return {"duplicate": False, "patient": None, "normalized": normalized}

    V4444_PHONE_GUARD_CSS = r"""
.v4444-phone-duplicate{margin:7px 0 0;padding:10px 11px;border-radius:10px;border:1px solid #e2b66a;background:#fff7e8;color:#6d5223;display:grid;gap:3px}
.v4444-phone-duplicate b{font-size:11px;color:#8a5910}.v4444-phone-duplicate span{font-size:10px;line-height:1.35}.v4444-phone-duplicate small{font-size:9px;color:#806b49}
.v4444-phone-duplicate button{justify-self:start;margin-top:5px;min-height:30px;padding:5px 9px;border:1px solid #c99c50;border-radius:8px;background:#fff;color:#725019;font-size:9px;font-weight:900;cursor:pointer}
"""

    V4444_PHONE_GUARD_JS = r"""
;(()=>{
  if(window.__v4444PhoneDuplicateGuard)return;
  window.__v4444PhoneDuplicateGuard=true;
  let watcherSeq=0,watcherTimer=0,stagedContext=null,lastOwner=null;

  const cleanPhone=v=>String(v||'').replace(/\D/g,'');
  async function phoneOwner(value,excludeId=0){
    const q=cleanPhone(value);if(q.length<9)return null;
    try{
      const d=await api('/api/identity/phone-owner?phone='+encodeURIComponent(q)+'&exclude_id='+Number(excludeId||0));
      return d?.duplicate&&d?.patient?d.patient:null;
    }catch(_e){return null}
  }
  function warningHost(){return $('#fCel')?.closest('.form-field')||$('#fCel')?.parentElement||null}
  function clearWarning(){document.querySelector('#v4444PhoneDuplicateWarning')?.remove();lastOwner=null}
  function renderWarning(owner,allowUse=false){
    clearWarning();if(!owner)return;
    lastOwner=owner;const host=warningHost();if(!host)return;
    const box=document.createElement('div');box.id='v4444PhoneDuplicateWarning';box.className='v4444-phone-duplicate';
    const phone=formatPhoneValue(owner.celular||'')||String(owner.celular||'');
    box.innerHTML=`<b>⚠ Este celular ya está registrado</b><span>${esc(owner.nombre||'Paciente existente')}</span><small>${esc(owner.cedula||'Sin cédula')} · ${esc(phone)}</small>${allowUse?'<button type="button" id="v4444UseExistingPhoneOwner">Usar esta ficha</button>':''}`;
    host.appendChild(box);
    if(allowUse){
      box.querySelector('#v4444UseExistingPhoneOwner')?.addEventListener('click',async()=>{
        const ctx=stagedContext,hit=lastOwner;if(!ctx||!hit)return;
        await usePatientForStaged(Number(ctx.itemId),Number(hit.id),String(ctx.fecha||toISO(new Date())).slice(0,10));
      });
    }
  }
  async function checkVisiblePhone(excludeId=0,allowUse=false){
    const input=$('#fCel');if(!input)return null;
    const seq=++watcherSeq,owner=await phoneOwner(input.value,excludeId);if(seq!==watcherSeq)return null;
    renderWarning(owner,allowUse);return owner;
  }
  function installWatcher(excludeId=0,ctx=null){
    stagedContext=ctx||null;const input=$('#fCel');if(!input)return;
    const allowUse=!!ctx?.itemId;
    const run=()=>{clearTimeout(watcherTimer);watcherTimer=setTimeout(()=>checkVisiblePhone(excludeId,allowUse),120)};
    input.addEventListener('input',run);input.addEventListener('blur',()=>checkVisiblePhone(excludeId,allowUse));
    setTimeout(()=>checkVisiblePhone(excludeId,allowUse),20);
  }
  async function stopIfDuplicate(excludeId=0,allowUse=false){
    const owner=await checkVisiblePhone(excludeId,allowUse);if(!owner)return false;
    alert(`⚠ Este celular ya está registrado\n\n${owner.nombre||'Paciente existente'}\n${formatPhoneValue(owner.celular||'')||owner.celular||''}\n\nNo se guardó ningún cambio. Revisa o usa la ficha existente.`);
    return true;
  }

  // Completar datos desde Nueva atención: aquí estaba el bug. El código antiguo
  // consideraba editMode y omitía por completo checkPhone(). Ahora se comprueba
  // contra OTRAS fichas, pero conservar el propio número nunca genera falso aviso.
  const stableEditFromAttention=window.editPatientFromAttention;
  if(typeof stableEditFromAttention==='function')window.editPatientFromAttention=async function(id){
    const r=await stableEditFromAttention.apply(this,arguments);
    setTimeout(()=>installWatcher(Number(id||0),attentionDraft?.stagedId?{itemId:Number(attentionDraft.stagedId),fecha:attentionDraft.fecha}:null),35);
    return r;
  };
  const stableSaveAndReturn=window.savePatientAndReturnToAttention;
  if(typeof stableSaveAndReturn==='function')window.savePatientAndReturnToAttention=async function(id){
    if(await stopIfDuplicate(Number(id||0),!!attentionDraft?.stagedId))return;
    return stableSaveAndReturn.apply(this,arguments);
  };

  // Edición normal de la ficha: misma protección y exclusión del paciente actual.
  const stableEditPatient=window.editPatient;
  if(typeof stableEditPatient==='function')window.editPatient=async function(id){
    const r=await stableEditPatient.apply(this,arguments);setTimeout(()=>installWatcher(Number(id||0),null),35);return r;
  };
  const stableSavePatient=window.savePatient;
  if(typeof stableSavePatient==='function')window.savePatient=async function(id){
    if(await stopIfDuplicate(Number(id||0),false))return;
    return stableSavePatient.apply(this,arguments);
  };

  // Nuevo paciente general: la advertencia puede verse mientras se escribe y el
  // guardado no pasa silenciosamente si ese teléfono pertenece a otra ficha.
  const stableNewPatient=window.newPatient;
  if(typeof stableNewPatient==='function')window.newPatient=async function(){
    const r=await stableNewPatient.apply(this,arguments);setTimeout(()=>installWatcher(0,null),35);return r;
  };
  const stableSaveNewPatient=window.saveNewPatient;
  if(typeof stableSaveNewPatient==='function')window.saveNewPatient=async function(){
    if(await stopIfDuplicate(0,false))return;
    return stableSaveNewPatient.apply(this,arguments);
  };

  // Cita WhatsApp/Cloud sin ficha: el celular viene precargado, por lo que la
  // comprobación se ejecuta al abrir el formulario sin esperar que recepción lo
  // vuelva a escribir. Si ya existe, ofrece usar directamente la ficha correcta.
  const stableNewFromStaged=window.newPatientFromStaged;
  if(typeof stableNewFromStaged==='function')window.newPatientFromStaged=async function(itemId,fecha){
    const r=await stableNewFromStaged.apply(this,arguments);
    setTimeout(()=>installWatcher(0,{itemId:Number(itemId),fecha:String(fecha||'').slice(0,10)}),35);return r;
  };
  const stableSaveNewFromStaged=window.saveNewPatientFromStaged;
  if(typeof stableSaveNewFromStaged==='function')window.saveNewPatientFromStaged=async function(itemId,fecha){
    stagedContext={itemId:Number(itemId),fecha:String(fecha||'').slice(0,10)};
    if(await stopIfDuplicate(0,true))return;
    return stableSaveNewFromStaged.apply(this,arguments);
  };

  // Importación manual de Confirmafy: evita que una creación heredada vuelva a
  // introducir el mismo problema por un camino distinto.
  const stableSaveFromConfirmafy=window.saveNewPatientFromConfirmafy;
  if(typeof stableSaveFromConfirmafy==='function')window.saveNewPatientFromConfirmafy=async function(){
    if(await stopIfDuplicate(0,false))return;
    return stableSaveFromConfirmafy.apply(this,arguments);
  };

  window.__v4444PhoneGuardTest={phoneOwner,checkVisiblePhone,installWatcher};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4444_PHONE_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4444_PHONE_GUARD_JS
'''


def main() -> None:
    base.FEATURE_BLOCK = base.FEATURE_BLOCK + SYNC_BLOCK + PHONE_GUARD_BLOCK
    base.build()

    # El contenido binario y los SHA ya fueron calculados por build() con los
    # bloques acumulativos incluidos. Solo ampliamos el texto informativo.
    candidate_path = base.OUT / "candidate_latest.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["message"] = (
        "v4.4.44: Nueva cita advierte si el mismo paciente ya tiene otra cita en la semana y permite Agendar de todas formas solo con confirmación manual. "
        "Las citas creadas desde WhatsApp/Agenda Cloud bajan a la agenda local al abrir la semana para que Nueva atención muestre todos los pacientes. "
        "Además, completar o crear una ficha vuelve a comprobar el celular incluso si viene precargado desde una cita: si pertenece a otro paciente muestra la advertencia y detiene el guardado para evitar duplicados. "
        "No cambia tablas, .env, launcher ni bases de datos; conserva el modo local-first y el funcionamiento offline."
    )
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BUILD_V4444_ALL_FIXES_OK")


if __name__ == "__main__":
    main()
