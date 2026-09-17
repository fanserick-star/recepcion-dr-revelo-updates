from __future__ import annotations

# v4.4.75 — guardado de atención en una sola transacción + eliminación fiable de servicios.
# - Parte de v4.4.74 (interfaz estable + impresión en segundo plano).
# - Atención + forma de pago se guardan en el mismo COMMIT a Neon/SQLite.
# - Reduce flush/round-trips sin cambiar la pantalla de Nueva atención.
# - Corrige Eliminar en Servicios y precios con un endpoint POST compatible con todos los wrappers.
# - No usa MutationObserver nuevo ni reemplaza la interfaz general.
# - Conserva el recibo térmico aprobado v4.4.69.

import app_patch_4474 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.75"

_mod = previous
_seen = set()
for _ in range(28):
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

PAYMENT_SENTINELS = {
    "EFECTIVO": -442901,
    "TRANSFERENCIA": -442920,
}
SRI_PAYMENT_CODES = {
    "EFECTIVO": "01",
    "TRANSFERENCIA": "20",
}


def _normalize_payment_method(value: object) -> str:
    raw = " ".join(str(value or "").strip().upper().split())
    aliases = {
        "TRANSFERENCIA BANCARIA": "TRANSFERENCIA",
        "BANCO": "TRANSFERENCIA",
        "CASH": "EFECTIVO",
    }
    raw = aliases.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise core.HTTPException(
            400,
            "Selecciona la forma de pago: Efectivo o Transferencia bancaria.",
        )
    return raw


def _remove_api_route(path: str, method: str) -> int:
    """Quita una ruta anterior exacta antes de registrar su reemplazo."""
    wanted = str(method or "").upper()
    removed = 0
    kept = []
    for route in list(app.router.routes):
        methods = {str(x).upper() for x in (getattr(route, "methods", None) or set())}
        if getattr(route, "path", None) == path and wanted in methods:
            removed += 1
            continue
        kept.append(route)
    if removed:
        app.router.routes[:] = kept
        try:
            app.openapi_schema = None
        except Exception:
            pass
    return removed


try:
    class V4475VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str

    # Reemplaza SOLO este endpoint. La pantalla sigue usando exactamente
    # /api/visits/batch-payment como desde v4.4.51.
    _REMOVED_BATCH_PAYMENT_ROUTES = _remove_api_route("/api/visits/batch-payment", "POST")

    @app.post("/api/visits/batch-payment")
    def v4475_create_visit_batch_payment(
        data: V4475VisitBatchPaymentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        method = _normalize_payment_method(data.payment_method)
        sentinel = PAYMENT_SENTINELS[method]

        p = db.get(core.Patient, int(data.patient_id))
        if not p:
            raise core.HTTPException(404, "Paciente no encontrado")
        if not data.services:
            raise core.HTTPException(400, "Selecciona al menos una atención")
        if len(data.services) > 20:
            raise core.HTTPException(400, "Hay demasiadas acciones seleccionadas")

        override = (data.tipo or "").strip().upper()
        if override and override not in {"N", "S"}:
            raise core.HTTPException(400, "Estado de paciente inválido")

        prior = db.scalar(
            core.select(core.func.count(core.Visit.id)).where(
                core.Visit.patient_id == int(p.id)
            )
        ) or 0
        historical_prior = bool(
            not prior and core.historical_summary_for_patient(p)
        )
        first_type = override or ("S" if prior or historical_prior else "N")

        normalized = []
        seen = set()
        for item in data.services:
            procedimiento = (item.procedimiento or "").strip().upper() or None
            key = procedimiento or "CONSULTA"
            if key in seen:
                continue
            seen.add(key)
            valor = 40.0 if procedimiento is None else item.valor
            if valor is None:
                raise core.HTTPException(400, f"Ingresa el valor de {key}")
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                raise core.HTTPException(400, f"El valor de {key} no es válido")
            if valor < 0:
                raise core.HTTPException(400, f"El valor de {key} no es válido")
            normalized.append((procedimiento, valor))

        if not normalized:
            raise core.HTTPException(400, "Selecciona al menos una atención")

        offline = core.is_offline_db(db)

        # Conserva el comportamiento previo: si el paciente ya tenía otras líneas
        # PENDIENTES/APROBADAS el mismo día, todas quedan con el mismo método.
        # La diferencia es que ahora se hace dentro de ESTA misma transacción.
        existing_payment_visits = list(db.scalars(
            core.select(core.Visit)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.patient_id == int(data.patient_id),
                core.Visit.fecha == data.fecha,
                core.BillingRecord.estado != "EMITIDA",
            )
            .order_by(core.Visit.id)
        ))
        for old_visit in existing_payment_visits:
            old_visit.source_row = sentinel

        created = []
        specs = []

        # Un solo flush para obtener todos los IDs de Visit.
        for index, (procedimiento, valor) in enumerate(normalized):
            tipo = first_type if index == 0 else "S"
            visit = core.Visit(
                patient_id=int(data.patient_id),
                fecha=data.fecha,
                tipo=tipo,
                procedimiento=procedimiento,
                valor=valor,
                observacion=data.observacion,
                source_row=sentinel,
            )
            db.add(visit)
            created.append(visit)
            specs.append((visit, tipo, procedimiento, valor))
        db.flush()

        billings = []
        for visit in created:
            billing = core.BillingRecord(visit_id=int(visit.id), estado="PENDIENTE")
            db.add(billing)
            billings.append(billing)

        # Auditoría y cola offline forman parte del MISMO commit.
        for visit, tipo, procedimiento, valor in specs:
            service_name = procedimiento or "CONSULTA"
            if offline:
                payload = {
                    "patient_id": int(data.patient_id),
                    "fecha": data.fecha.isoformat(),
                    "tipo": tipo,
                    "procedimiento": procedimiento,
                    "valor": valor,
                    "observacion": data.observacion,
                    "source_row": sentinel,
                }
                core.add_queue(
                    db,
                    "visit.create",
                    "visit",
                    payload,
                    user.username,
                    int(visit.id),
                )
                core.audit(
                    db,
                    user,
                    "crear_atencion_multiple_offline",
                    f"Atención local {visit.id}, paciente {p.id}, {service_name}",
                )
            else:
                core.audit(
                    db,
                    user,
                    "crear_atencion_multiple",
                    f"Atención {visit.id}, paciente {p.id}, estado {tipo}, servicio {service_name}",
                )

        core.audit(
            db,
            user,
            "registrar_forma_pago_atencion",
            f"Paciente {int(data.patient_id)}, {data.fecha}: {method}",
        )

        # Punto clave v4.4.75: UN solo commit para atención + BillingRecord + pago.
        db.commit()

        if not offline:
            mirrored = set()
            for visit in existing_payment_visits:
                try:
                    core.mirror_visit_to_local(visit)
                    mirrored.add(int(visit.id))
                except Exception:
                    pass
            for visit, billing in zip(created, billings):
                if int(visit.id) not in mirrored:
                    try:
                        core.mirror_visit_to_local(visit)
                    except Exception:
                        pass
                try:
                    core.mirror_billing_to_local(billing)
                except Exception:
                    pass

        with core.LocalSessionLocal() as summary_db:
            billing_actions = core._billing_action_counts(summary_db)
            pending_summary_local = {
                "billing": billing_actions["total"],
                "billing_pending": billing_actions["pending"],
                "billing_approved": billing_actions["approved"],
                "agenda": int(
                    summary_db.scalar(
                        core.select(core.func.count(core.Appointment.id)).where(
                            core.Appointment.estado == "PENDIENTE"
                        )
                    )
                    or 0
                ),
            }

        return {
            "ok": True,
            "count": len(created),
            "items": [core.v_dict(v) for v in created],
            "offline": offline,
            "pending": pending_summary_local,
            "payment_method": method,
            "sri_payment_code": SRI_PAYMENT_CODES[method],
            "single_commit": True,
        }

    # Endpoint alterno por POST. Evita depender de DELETE en wrappers antiguos
    # del WebView y conserva la misma política: archivar si tiene historial.
    @app.post("/api/v4475/procedures/{procedure_id}/delete")
    def v4475_delete_procedure(
        procedure_id: int,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        if core.is_offline_db(db):
            raise core.HTTPException(
                503,
                "Eliminar o archivar procedimientos requiere conexión a Internet",
            )
        proc = db.get(core.Procedure, int(procedure_id))
        if not proc:
            raise core.HTTPException(404, "Procedimiento no encontrado")

        used = int(
            db.scalar(
                core.select(core.func.count(core.Visit.id)).where(
                    core.func.upper(
                        core.func.coalesce(core.Visit.procedimiento, "")
                    )
                    == str(proc.nombre or "").upper()
                )
            )
            or 0
        )
        name = str(proc.nombre or "").strip() or f"Servicio {procedure_id}"

        if used:
            proc.activo = 0
            core.audit(
                db,
                user,
                "archivar_procedimiento",
                f"{name}; {used} atención(es) históricas",
            )
            db.commit()
            try:
                core.mirror_procedure_local(proc)
            except Exception:
                pass
            return {
                "ok": True,
                "archived": True,
                "used": used,
                "message": "Servicio archivado. Ya no aparecerá en nuevas atenciones y el historial se conserva.",
            }

        db.delete(proc)
        core.audit(db, user, "eliminar_procedimiento", name)
        db.commit()
        try:
            with core.LocalSessionLocal() as ldb:
                local = ldb.get(core.Procedure, int(procedure_id))
                if local:
                    ldb.delete(local)
                ldb.commit()
        except Exception:
            pass
        return {
            "ok": True,
            "archived": False,
            "used": 0,
            "message": "Servicio eliminado.",
        }

    V4475_JS = r"""
;(()=>{
  if(window.__v4475FastSaveAndServiceDelete)return;
  window.__v4475FastSaveAndServiceDelete=true;
  const VERSION='4.4.75';
  let managerBusy=false;

  const text=v=>String(v??'').replace(/\s+/g,' ').trim();
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));

  function call(url,opt={}){
    const fn=window.api;
    if(typeof fn!=='function')return Promise.reject(new Error('API no disponible'));
    return fn(url,opt);
  }

  function serviceHost(){
    return document.querySelector('[data-config-section="procedimientos"]')
      || document.querySelector('[data-config-section="services"]')
      || document.querySelector('#v458ServicePanel')?.closest('.config-section')
      || document.querySelector('#v458ServicePanel')?.parentElement
      || null;
  }

  async function deleteService(id,name,button,rowEl){
    if(!id)return;
    if(!confirm(`¿Eliminar "${name||'este servicio'}"?\n\nSi tiene atenciones anteriores, se archivará y el historial se conservará.`))return;
    if(button)button.disabled=true;
    try{
      const out=await call('/api/v4475/procedures/'+Number(id)+'/delete',{
        method:'POST',body:'{}'
      });
      rowEl?.remove();
      try{
        if(typeof window.loadProcedures==='function')await window.loadProcedures();
      }catch(_e){}
      setTimeout(mountManager,80);
      const message=out?.message||'Servicio eliminado.';
      if(typeof window.rpNotice==='function')window.rpNotice(message);
      else alert(message);
    }catch(e){
      if(button)button.disabled=false;
      alert(e?.message||String(e));
    }
  }

  // Corrige también los botones creados por v4.4.70. El listener en captura
  // evita que el handler antiguo intente usar DELETE después de esta acción.
  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('.v4470-proc-delete');
    if(!btn||btn.classList.contains('v4475-delete'))return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const row=btn.closest('.v4470-proc-row');
    const id=Number(btn.dataset.delete||row?.dataset.id||0);
    const name=text(row?.querySelector('b')?.textContent||'Servicio');
    deleteService(id,name,btn,row);
  },true);

  async function mountManager(){
    if(managerBusy)return;
    const host=serviceHost();
    if(!host)return;
    // Si el administrador viejo ya está visible, no duplicamos la lista:
    // sus botones quedaron reparados por el listener anterior.
    if(host.querySelector('#v4470ProcedureManager'))return;

    managerBusy=true;
    try{
      const rows=await call('/api/procedures');
      let box=host.querySelector('#v4475ProcedureManager');
      if(!box){
        box=document.createElement('div');
        box.id='v4475ProcedureManager';
        box.className='v4470-proc-manager';
        host.appendChild(box);
      }
      const list=Array.isArray(rows)?rows:[];
      box.innerHTML=`<div class="v4470-proc-manager-head"><div><h4>Eliminar servicios y precios</h4><small>Los servicios con historial se archivan; las atenciones antiguas no cambian.</small></div></div>
        <div class="v4470-proc-list">${
          list.map(p=>`<div class="v4470-proc-row" data-v4475-id="${Number(p.id)}">
            <b>${esc(p.nombre)}</b>
            <span>${p.valor_default==null?'Sin precio':'$'+Number(p.valor_default).toFixed(2)}</span>
            <button type="button" class="v4470-proc-delete v4475-delete" data-v4475-delete="${Number(p.id)}">Eliminar</button>
          </div>`).join('')||'<small>No hay servicios activos.</small>'
        }</div>`;
      box.querySelectorAll('[data-v4475-delete]').forEach(btn=>{
        btn.addEventListener('click',e=>{
          e.preventDefault();e.stopPropagation();
          const row=btn.closest('.v4470-proc-row');
          const id=Number(btn.dataset.v4475Delete||0);
          const name=text(row?.querySelector('b')?.textContent||'Servicio');
          deleteService(id,name,btn,row);
        });
      });
    }catch(_e){
      // La pantalla de configuración sigue operativa aunque Neon esté temporalmente caído.
    }finally{
      managerBusy=false;
    }
  }

  function hookLoader(){
    const fn=window.loadProcedures;
    if(typeof fn!=='function'||fn.__v4475DeleteHook)return;
    const wrapped=async function(){
      const out=await fn.apply(this,arguments);
      setTimeout(mountManager,60);
      return out;
    };
    wrapped.__v4475DeleteHook=true;
    window.loadProcedures=wrapped;
  }

  document.addEventListener('click',e=>{
    const tab=e.target?.closest?.('[data-config-tab]');
    const key=String(tab?.dataset?.configTab||'').toLowerCase();
    if(key==='procedimientos'||key==='services'){
      setTimeout(()=>{hookLoader();mountManager()},90);
    }
  });

  function boot(){
    hookLoader();
    mountManager();
    setTimeout(()=>{hookLoader();mountManager()},400);
    setTimeout(()=>{hookLoader();mountManager()},1400);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();

  // Igual que v4.4.73/74: solo sustitución estática de texto, sin observer nuevo.
  try{
    const badges=document.querySelectorAll('.v460-version,#currentVersionBadge');
    badges.forEach(el=>{if(text(el.textContent)!=='v'+VERSION)el.textContent='v'+VERSION});
  }catch(_e){}
})();
"""

    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "")
        .replace("const VERSION='4.4.74';", "const VERSION='4.4.75';")
        + "\n"
        + V4475_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.75 fast save/service delete patch failed: %s",
            PATCH_BOOT_ERROR,
        )
    except Exception:
        pass


@app.get("/api/v4475/health")
def v4475_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "batch_payment_single_commit": True,
        "service_delete_post_endpoint": True,
        "background_print_preserved": True,
        "base_ui": "4.4.74 / stable 4.4.73",
        "uses_new_dom_observer": False,
        "receipt_layout_version": "4.4.69",
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
