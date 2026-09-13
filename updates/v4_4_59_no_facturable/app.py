from __future__ import annotations

# v4.4.59 — Facturación: pacientes sin identificación pueden archivarse como
# NO FACTURABLES sin borrar la atención ni contaminar recordatorios.
#
# Este parche se monta encima de la versión estable publicada v4.4.58. No crea
# tablas, no migra columnas y no modifica Nueva atención. Si la mejora falla al
# cargarse, la aplicación v4.4.58 sigue disponible (fail-open).

from datetime import date as _date
import traceback as _traceback

import app_prev_4458 as previous

core = previous.core
app = previous.app

APP_VERSION = "4.4.59"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION

NON_BILLABLE_STATE = "NO_FACTURABLE"
NON_BILLABLE_REASON = "Paciente sin cédula/identificación"
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""


class BillingNonBillableIn(core.BaseModel):
    patient_id: int
    fecha: _date


def _v4459_state(value: object) -> str:
    return str(value or "").strip().upper()


def _v4459_clear_invoice_fields(record) -> None:
    record.approved_at = None
    record.numero_factura = None
    record.emitted_at = None


try:
    # -----------------------------------------------------------------------
    # Sincronización offline segura
    # -----------------------------------------------------------------------
    _v4459_stable_sync_one_operation = core.sync_one_operation

    def _v4459_sync_one_operation(q, ldb, cdb):
        if q.operation not in {"billing.nonbillable", "billing.restore"}:
            return _v4459_stable_sync_one_operation(q, ldb, cdb)

        already = cdb.get(core.SyncOperation, q.token)
        if already:
            return already.result_id

        payload = core.json.loads(q.payload or "{}")
        local_visit_id = int(payload["visit_id"])
        cloud_visit_id = core.resolve_cloud_id(ldb, "visit", local_visit_id)
        billing = cdb.scalar(
            core.select(core.BillingRecord).where(core.BillingRecord.visit_id == cloud_visit_id)
        )
        if not billing:
            billing = core.BillingRecord(visit_id=cloud_visit_id, estado="PENDIENTE")
            cdb.add(billing)
            cdb.flush()

        current = _v4459_state(billing.estado)
        if current == "EMITIDA":
            raise RuntimeError("Una factura emitida no puede cambiar a No facturable")

        if q.operation == "billing.nonbillable":
            billing.estado = NON_BILLABLE_STATE
            action = "sincronizar_factura_no_facturable_offline"
        else:
            if current == NON_BILLABLE_STATE:
                billing.estado = "PENDIENTE"
            action = "sincronizar_restaurar_factura_offline"

        _v4459_clear_invoice_fields(billing)
        result_id = billing.id
        core.audit(
            cdb,
            q.username,
            action,
            f"Atención {cloud_visit_id}: {billing.estado}",
        )
        cdb.add(core.SyncOperation(token=q.token, operation=q.operation, result_id=result_id))
        return result_id

    core.sync_one_operation = _v4459_sync_one_operation

    # -----------------------------------------------------------------------
    # Cambio de estado del grupo abierto de facturación
    # -----------------------------------------------------------------------
    def _v4459_change_group(data, target: str, db, user):
        patient_id = int(data.patient_id)
        fecha = data.fecha
        patient = db.get(core.Patient, patient_id)
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        if target == NON_BILLABLE_STATE and str(getattr(patient, "cedula", "") or "").strip():
            raise core.HTTPException(
                409,
                "Esta opción es solo para pacientes sin cédula/identificación. Si ya tiene identificación, la ficha puede facturarse normalmente.",
            )

        rows = core.billing_group_records(db, patient_id, fecha)
        if not rows:
            raise core.HTTPException(
                409,
                "Esta factura ya fue emitida o ya no está disponible para cambiar de estado.",
            )

        current_states = {_v4459_state(b.estado) for b, _v in rows}
        if "EMITIDA" in current_states:
            raise core.HTTPException(409, "Una factura emitida no puede cambiar de estado.")

        offline = bool(core.is_offline_db(db))
        touched = []
        changed = 0

        for billing, visit in rows:
            state = _v4459_state(billing.estado)
            if target == NON_BILLABLE_STATE:
                if state not in {"PENDIENTE", "APROBADA", NON_BILLABLE_STATE}:
                    continue
                if state != NON_BILLABLE_STATE:
                    changed += 1
                billing.estado = NON_BILLABLE_STATE
                queue_op = "billing.nonbillable"
            else:
                if state != NON_BILLABLE_STATE:
                    continue
                billing.estado = "PENDIENTE"
                changed += 1
                queue_op = "billing.restore"

            _v4459_clear_invoice_fields(billing)
            touched.append(billing)
            if offline and state != _v4459_state(billing.estado):
                core.add_queue(
                    db,
                    queue_op,
                    "billing",
                    {"visit_id": int(visit.id)},
                    user.username,
                    billing.id,
                )

        if not touched:
            if target == NON_BILLABLE_STATE and current_states == {NON_BILLABLE_STATE}:
                return {
                    "ok": True,
                    "state": NON_BILLABLE_STATE,
                    "patient_id": patient_id,
                    "fecha": fecha.isoformat(),
                    "reason": NON_BILLABLE_REASON,
                    "offline": offline,
                    "changed": 0,
                }
            raise core.HTTPException(409, "La ficha ya no está en un estado que pueda modificarse.")

        if target == NON_BILLABLE_STATE:
            action = "marcar_factura_no_facturable" + ("_offline" if offline else "")
            detail = f"Paciente {patient_id}, {fecha}: {NON_BILLABLE_REASON}"
        else:
            action = "restaurar_factura_pendiente" + ("_offline" if offline else "")
            detail = f"Paciente {patient_id}, {fecha}: NO_FACTURABLE -> PENDIENTE"

        core.audit(db, user, action, detail)
        db.commit()

        if not offline:
            for billing in touched:
                try:
                    core.mirror_billing_to_local(billing)
                except Exception:
                    pass

        return {
            "ok": True,
            "state": target,
            "patient_id": patient_id,
            "fecha": fecha.isoformat(),
            "reason": NON_BILLABLE_REASON if target == NON_BILLABLE_STATE else None,
            "offline": offline,
            "changed": changed,
        }

    @app.post("/api/billing/non-billable")
    def billing_mark_non_billable_v4459(
        data: BillingNonBillableIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        return _v4459_change_group(data, NON_BILLABLE_STATE, db, user)

    @app.post("/api/billing/non-billable/restore")
    def billing_restore_non_billable_v4459(
        data: BillingNonBillableIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        return _v4459_change_group(data, "PENDIENTE", db, user)

    @app.get("/api/billing/non-billable")
    def billing_non_billable_list_v4459(
        desde: _date | None = None,
        hasta: _date | None = None,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        stmt = (
            core.select(core.BillingRecord, core.Visit, core.Patient)
            .join(core.Visit, core.BillingRecord.visit_id == core.Visit.id)
            .join(core.Patient, core.Visit.patient_id == core.Patient.id)
            .where(
                core.Visit.fecha >= core.BILLING_QUEUE_START_DATE,
                core.BillingRecord.estado == NON_BILLABLE_STATE,
            )
        )
        if desde:
            stmt = stmt.where(core.Visit.fecha >= desde)
        if hasta:
            stmt = stmt.where(core.Visit.fecha <= hasta)

        rows = db.execute(stmt.order_by(core.Visit.fecha.desc(), core.Visit.id.desc())).all()
        grouped = {}
        for billing, visit, patient in rows:
            key = (int(patient.id), visit.fecha)
            group = grouped.setdefault(
                key,
                {
                    "patient": core.p_dict(patient),
                    "fecha": visit.fecha.isoformat(),
                    "reason": NON_BILLABLE_REASON,
                    "items": [],
                    "total": 0.0,
                },
            )
            group["items"].append(
                {
                    "billing": core.billing_dict(billing),
                    "visit": core.v_dict(visit),
                    "patient": core.p_dict(patient),
                }
            )
            try:
                group["total"] += float(visit.valor or 0)
            except Exception:
                pass

        groups = list(grouped.values())
        groups.sort(key=lambda x: (x["fecha"], int(x["patient"].get("id") or 0)), reverse=True)
        for group in groups:
            group["total"] = round(float(group["total"] or 0), 2)
        return {"groups": groups, "count": len(groups), "reason": NON_BILLABLE_REASON}

    V4459_NON_BILLABLE_CSS = r"""
#facturacion .billing-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}
#facturacion .v4459-nonbillable-tab.active{border-color:#c5965f!important;background:#fff6ea!important;color:#7a542a!important}
#facturacion .v4459-mark-nonbillable{border-color:#e2c7a5!important;background:#fff8ee!important;color:#79552c!important}
#facturacion .v4459-nonbillable-status{background:#fff1df!important;color:#8a5b25!important}
#facturacion .v4459-reason{margin:9px 0;padding:9px 11px;border:1px solid #ead4b8;border-radius:10px;background:#fff8ef;color:#76542d;font-size:11px;font-weight:800}
#facturacion .v4459-empty{padding:26px 18px;border:1px dashed #d5dee8;border-radius:13px;background:#fbfcfe;color:#6d8197;text-align:center;font-size:12px}
#facturacion .v4459-restore{border-color:#bdd4c5!important;background:#eef9f1!important;color:#2f6842!important}
@media(max-width:760px){#facturacion .billing-summary{grid-template-columns:1fr!important}}
"""

    V4459_NON_BILLABLE_JS = r"""
;(()=>{
  if(window.__v4459NonBillable)return;
  window.__v4459NonBillable=true;
  let archiveMode=false,archiveCache=[],decorateTimer=0;
  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fd=v=>{try{return typeof fmtDate==='function'?fmtDate(v):String(v||'')}catch(_e){return String(v||'')}};
  const cash=v=>{try{return typeof money==='function'?money(Number(v||0)):`$${Number(v||0).toFixed(2)}`}catch(_e){return `$${Number(v||0).toFixed(2)}`}};
  function identify(card){const p=Number(card?.dataset?.patientId||0),f=String(card?.dataset?.fecha||'').slice(0,10);if(p&&/^\d{4}-\d{2}-\d{2}$/.test(f))return{patient_id:p,fecha:f};for(const el of [...(card?.querySelectorAll?.('[onclick]')||[])]){const m=/\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]/.exec(String(el.getAttribute('onclick')||''));if(m){card.dataset.patientId=m[1];card.dataset.fecha=m[2];return{patient_id:Number(m[1]),fecha:m[2]}}}return null}
  function missing(card){const t=norm(card?.querySelector?.('.billing-meta')?.textContent||'');return t.includes('cedula: sin cedula')||t.includes('sin cedula')}
  async function refreshOther(){for(const n of ['loadPendingSummary','refreshPendingSummary','loadHome','refreshHome']){try{const f=window[n];if(typeof f==='function')Promise.resolve(f()).catch(()=>{})}catch(_e){}}}
  async function mark(patient_id,fecha){if(!confirm('¿Marcar esta ficha como No facturable?\n\nSaldrá de Por emitir y de los recordatorios. La atención NO se borrará y podrás recuperarla desde “No facturables”.\n\nMotivo: Paciente sin cédula/identificación.'))return;try{await api('/api/billing/non-billable',{method:'POST',body:JSON.stringify({patient_id:Number(patient_id),fecha:String(fecha).slice(0,10)})});archiveMode=false;if(typeof window.loadBilling==='function')await window.loadBilling();await refreshCount();refreshOther()}catch(x){alert(x?.message||'No se pudo marcar la ficha como No facturable.')}}
  async function restore(patient_id,fecha){if(!confirm('¿Volver esta ficha a Por emitir?\n\nVolverá a aparecer en los recordatorios de facturación.'))return;try{await api('/api/billing/non-billable/restore',{method:'POST',body:JSON.stringify({patient_id:Number(patient_id),fecha:String(fecha).slice(0,10)})});await openArchive();refreshOther()}catch(x){alert(x?.message||'No se pudo devolver la ficha a pendientes.')}}
  function decorate(){if(archiveMode)return;document.querySelectorAll('#billingList .billing-card').forEach(card=>{if(card.classList.contains('emitida')||!missing(card))return;const id=identify(card),host=card.querySelector('.billing-actions');if(!id||!host||host.querySelector('.v4459-mark-nonbillable'))return;const b=document.createElement('button');b.type='button';b.className='v4459-mark-nonbillable';b.textContent='🚫 No se puede facturar';b.addEventListener('click',()=>mark(id.patient_id,id.fecha));host.prepend(b)})}
  function visuals(){const s=document.querySelector('#billingSummary');if(!s)return;[...s.querySelectorAll('button')].forEach(b=>{if(b.id==='v4459NonBillableTab')b.classList.toggle('active',archiveMode);else if(archiveMode)b.classList.remove('active')})}
  function ensureTab(){const s=document.querySelector('#billingSummary');if(!s)return null;let b=document.getElementById('v4459NonBillableTab');if(!b){b=document.createElement('button');b.type='button';b.id='v4459NonBillableTab';b.className='v4459-nonbillable-tab';b.innerHTML='<span>No facturables</span><b id="v4459NonBillableCount">0</b>';b.addEventListener('click',openArchive);s.appendChild(b)}visuals();return b}
  async function refreshCount(reload=true){try{const d=await api('/api/billing/non-billable');archiveCache=Array.isArray(d?.groups)?d.groups:[];ensureTab();const c=document.getElementById('v4459NonBillableCount');if(c)c.textContent=String(Number(d?.count||archiveCache.length||0));if(reload&&archiveMode)renderArchive();return d}catch(_e){return null}}
  function services(g){try{if(typeof billingServicesHtml==='function')return billingServicesHtml({items:g.items||[],patient:g.patient,fecha:g.fecha})}catch(_e){}return(g.items||[]).map(x=>{const v=x?.visit||{},label=String(v.tipo||'Atención')+(v.procedimiento?` · ${v.procedimiento}`:'');return`<div class="billing-line"><span>${e(label)}</span><strong>${cash(v.valor||0)}</strong></div>`}).join('')}
  function card(g){const p=g?.patient||{},f=String(g?.fecha||'').slice(0,10),pid=Number(p.id||0);return`<article class="billing-card pendiente" data-patient-id="${pid}" data-fecha="${e(f)}"><div class="billing-card-head"><div><div class="billing-patient-name">${e(p.nombre||'Paciente')}</div><div class="billing-meta"><span><b>Cédula:</b> ${e(p.cedula||'Sin cédula')}</span><span><b>Correo:</b> ${e(p.correo||'Sin correo')}</span><span><b>Fecha:</b> ${fd(f)}</span></div></div><span class="billing-status v4459-nonbillable-status">NO FACTURABLE</span></div><div class="v4459-reason">Motivo: ${e(g.reason||'Paciente sin cédula/identificación')}</div><div class="billing-lines">${services(g)}</div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${cash(g.total||0)}</strong></div><div class="billing-actions"><button type="button" class="v4459-restore" data-restore="1">↩ Volver a pendientes</button></div></div></article>`}
  function renderArchive(){const list=document.querySelector('#billingList');if(!list)return;archiveMode=true;ensureTab();visuals();if(!archiveCache.length){list.innerHTML='<div class="v4459-empty">No hay fichas marcadas como No facturables.</div>';return}list.innerHTML=archiveCache.map(card).join('');list.querySelectorAll('.billing-card').forEach(c=>{const id=identify(c),b=c.querySelector('[data-restore="1"]');if(id&&b)b.addEventListener('click',()=>restore(id.patient_id,id.fecha))})}
  async function openArchive(){archiveMode=true;ensureTab();visuals();const d=await refreshCount(false);if(d!==null)renderArchive()}
  function schedule(){clearTimeout(decorateTimer);decorateTimer=setTimeout(()=>{ensureTab();decorate()},30)}
  const oldLoad=window.loadBilling;if(typeof oldLoad==='function'&&!oldLoad.__v4459Wrapped){const w=async function(){archiveMode=false;const r=await oldLoad.apply(this,arguments);ensureTab();await refreshCount(false);decorate();visuals();return r};w.__v4459Wrapped=true;window.loadBilling=w}
  const oldSet=window.setBillingStatus;if(typeof oldSet==='function'&&!oldSet.__v4459Wrapped){const w=async function(){archiveMode=false;const r=await oldSet.apply(this,arguments);ensureTab();await refreshCount(false);decorate();visuals();return r};w.__v4459Wrapped=true;window.setBillingStatus=w}
  const start=()=>{ensureTab();refreshCount(false).finally(schedule);const list=document.querySelector('#billingList');if(list&&!list.__v4459Observed){list.__v4459Observed=true;new MutationObserver(()=>schedule()).observe(list,{childList:true,subtree:false})}};
  window.__v4459NonBillableTest={ensureTab,refreshCount,decorate,openArchive};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4459_NON_BILLABLE_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4459_NON_BILLABLE_JS
    PATCH_BOOT_OK = True

except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        previous.FEATURE_BOOT_ERROR = (
            str(getattr(previous, "FEATURE_BOOT_ERROR", "") or "")
            + " | v4.4.59: " + PATCH_BOOT_ERROR
        ).strip(" |")[:1200]
    except Exception:
        pass
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.59 no-facturable patch failed: %s\n%s",
            PATCH_BOOT_ERROR,
            _traceback.format_exc(),
        )
    except Exception:
        pass


@app.get("/api/v4459/non-billable-health")
def v4459_non_billable_health(user=core.Depends(core.current_user)):
    return {
        "ok": bool(PATCH_BOOT_OK),
        "version": APP_VERSION,
        "previous": "4.4.58",
        "state": NON_BILLABLE_STATE,
        "reason": NON_BILLABLE_REASON,
        "error": PATCH_BOOT_ERROR,
        "schema_migration": False,
        "attention_changed": False,
    }
