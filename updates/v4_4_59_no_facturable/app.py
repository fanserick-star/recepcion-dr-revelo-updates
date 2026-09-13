from __future__ import annotations

# v4.4.59 — Facturación: archivar pacientes sin identificación como NO FACTURABLES.
# No migra base de datos, no modifica Nueva atención y mantiene v4.4.58 como base fail-open.

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


def _state(value):
    return str(value or "").strip().upper()


def _clear(record):
    record.approved_at = None
    record.numero_factura = None
    record.emitted_at = None


try:
    _stable_sync = core.sync_one_operation

    def _sync(q, ldb, cdb):
        if q.operation not in {"billing.nonbillable", "billing.restore"}:
            return _stable_sync(q, ldb, cdb)
        old = cdb.get(core.SyncOperation, q.token)
        if old:
            return old.result_id
        payload = core.json.loads(q.payload or "{}")
        local_visit_id = int(payload["visit_id"])
        visit_id = core.resolve_cloud_id(ldb, "visit", local_visit_id)
        b = cdb.scalar(core.select(core.BillingRecord).where(core.BillingRecord.visit_id == visit_id))
        if not b:
            b = core.BillingRecord(visit_id=visit_id, estado="PENDIENTE")
            cdb.add(b)
            cdb.flush()
        if _state(b.estado) == "EMITIDA":
            raise RuntimeError("Una factura emitida no puede cambiar a No facturable")
        if q.operation == "billing.nonbillable":
            b.estado = NON_BILLABLE_STATE
        elif _state(b.estado) == NON_BILLABLE_STATE:
            b.estado = "PENDIENTE"
        _clear(b)
        core.audit(cdb, q.username, "sincronizar_no_facturable", f"Atención {visit_id}: {b.estado}")
        cdb.add(core.SyncOperation(token=q.token, operation=q.operation, result_id=b.id))
        return b.id

    core.sync_one_operation = _sync

    def _change(data, target, db, user):
        pid, fecha = int(data.patient_id), data.fecha
        patient = db.get(core.Patient, pid)
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")
        if target == NON_BILLABLE_STATE and str(getattr(patient, "cedula", "") or "").strip():
            raise core.HTTPException(409, "Esta opción es solo para pacientes sin cédula/identificación.")
        rows = core.billing_group_records(db, pid, fecha)
        if not rows:
            raise core.HTTPException(409, "Esta factura ya fue emitida o ya no está disponible.")
        offline = bool(core.is_offline_db(db))
        touched = []
        for b, v in rows:
            before = _state(b.estado)
            if target == NON_BILLABLE_STATE:
                if before not in {"PENDIENTE", "APROBADA", NON_BILLABLE_STATE}:
                    continue
                b.estado = NON_BILLABLE_STATE
                op = "billing.nonbillable"
            else:
                if before != NON_BILLABLE_STATE:
                    continue
                b.estado = "PENDIENTE"
                op = "billing.restore"
            _clear(b)
            touched.append(b)
            if offline and before != _state(b.estado):
                core.add_queue(db, op, "billing", {"visit_id": int(v.id)}, user.username, b.id)
        if not touched:
            raise core.HTTPException(409, "La ficha ya no está en un estado que pueda modificarse.")
        core.audit(
            db,
            user,
            "marcar_no_facturable" if target == NON_BILLABLE_STATE else "restaurar_factura_pendiente",
            f"Paciente {pid}, {fecha}: {target}",
        )
        db.commit()
        if not offline:
            for b in touched:
                try:
                    core.mirror_billing_to_local(b)
                except Exception:
                    pass
        return {
            "ok": True,
            "state": target,
            "patient_id": pid,
            "fecha": fecha.isoformat(),
            "reason": NON_BILLABLE_REASON if target == NON_BILLABLE_STATE else None,
            "offline": offline,
        }

    @app.post("/api/billing/non-billable")
    def mark_non_billable(data: BillingNonBillableIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        return _change(data, NON_BILLABLE_STATE, db, user)

    @app.post("/api/billing/non-billable/restore")
    def restore_non_billable(data: BillingNonBillableIn, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        return _change(data, "PENDIENTE", db, user)

    @app.get("/api/billing/non-billable")
    def list_non_billable(db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
        rows = db.execute(
            core.select(core.BillingRecord, core.Visit, core.Patient)
            .join(core.Visit, core.BillingRecord.visit_id == core.Visit.id)
            .join(core.Patient, core.Visit.patient_id == core.Patient.id)
            .where(
                core.Visit.fecha >= core.BILLING_QUEUE_START_DATE,
                core.BillingRecord.estado == NON_BILLABLE_STATE,
            )
            .order_by(core.Visit.fecha.desc(), core.Visit.id.desc())
        ).all()
        groups = {}
        for b, v, p in rows:
            key = (int(p.id), v.fecha)
            g = groups.setdefault(key, {
                "patient": core.p_dict(p), "fecha": v.fecha.isoformat(),
                "reason": NON_BILLABLE_REASON, "items": [], "total": 0.0,
            })
            g["items"].append({"billing": core.billing_dict(b), "visit": core.v_dict(v), "patient": core.p_dict(p)})
            try:
                g["total"] += float(v.valor or 0)
            except Exception:
                pass
        out = list(groups.values())
        for g in out:
            g["total"] = round(g["total"], 2)
        return {"groups": out, "count": len(out)}

    CSS = r"""
#facturacion .billing-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}
#facturacion .v4459-tab.active{border-color:#c5965f!important;background:#fff6ea!important;color:#7a542a!important}
#facturacion .v4459-mark{border-color:#e2c7a5!important;background:#fff8ee!important;color:#79552c!important}
#facturacion .v4459-status{background:#fff1df!important;color:#8a5b25!important}
#facturacion .v4459-reason{margin:9px 0;padding:9px 11px;border:1px solid #ead4b8;border-radius:10px;background:#fff8ef;color:#76542d;font-size:11px;font-weight:800}
#facturacion .v4459-empty{padding:26px 18px;border:1px dashed #d5dee8;border-radius:13px;text-align:center;color:#6d8197}
#facturacion .v4459-restore{border-color:#bdd4c5!important;background:#eef9f1!important;color:#2f6842!important}
@media(max-width:760px){#facturacion .billing-summary{grid-template-columns:1fr!important}}
"""

    JS = r"""
;(()=>{
if(window.__v4459)return;window.__v4459=true;let archive=false,cache=[],timer=0;
const n=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fd=v=>{try{return fmtDate(v)}catch(_){return String(v||'')}};const cash=v=>{try{return money(Number(v||0))}catch(_){return `$${Number(v||0).toFixed(2)}`}};
function id(card){const p=Number(card?.dataset?.patientId||0),f=String(card?.dataset?.fecha||'').slice(0,10);if(p&&/^\d{4}-\d{2}-\d{2}$/.test(f))return[p,f];for(const x of [...(card?.querySelectorAll?.('[onclick]')||[])]){const m=/\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]/.exec(String(x.getAttribute('onclick')||''));if(m)return[Number(m[1]),m[2]]}return null}
function noid(card){return n(card?.querySelector?.('.billing-meta')?.textContent).includes('sin cedula')}
function tab(){const s=document.querySelector('#billingSummary');if(!s)return;let b=document.getElementById('v4459Tab');if(!b){b=document.createElement('button');b.id='v4459Tab';b.className='v4459-tab';b.innerHTML='<span>No facturables</span><b id="v4459Count">0</b>';b.onclick=open;s.appendChild(b)}[...s.querySelectorAll('button')].forEach(x=>{if(x===b)x.classList.toggle('active',archive);else if(archive)x.classList.remove('active')});return b}
async function count(){try{const d=await api('/api/billing/non-billable');cache=d.groups||[];tab();const c=document.getElementById('v4459Count');if(c)c.textContent=String(d.count||0);return d}catch(_){return null}}
function decorate(){if(archive)return;document.querySelectorAll('#billingList .billing-card').forEach(card=>{if(card.classList.contains('emitida')||!noid(card))return;const k=id(card),h=card.querySelector('.billing-actions');if(!k||!h||h.querySelector('.v4459-mark'))return;const b=document.createElement('button');b.className='v4459-mark';b.textContent='🚫 No se puede facturar';b.onclick=()=>mark(...k);h.prepend(b)})}
async function mark(pid,fecha){if(!confirm('¿Marcar como No facturable?\n\nSaldrá de Por emitir y de los recordatorios. La atención no se borrará.'))return;try{await api('/api/billing/non-billable',{method:'POST',body:JSON.stringify({patient_id:pid,fecha})});archive=false;await window.loadBilling?.();await count();refresh()}catch(x){alert(x.message||'No se pudo marcar.')}}
async function restore(pid,fecha){if(!confirm('¿Volver esta ficha a Por emitir?'))return;try{await api('/api/billing/non-billable/restore',{method:'POST',body:JSON.stringify({patient_id:pid,fecha})});await open();refresh()}catch(x){alert(x.message||'No se pudo restaurar.')}}
function refresh(){for(const k of ['loadPendingSummary','refreshPendingSummary','loadHome','refreshHome'])try{if(typeof window[k]==='function')Promise.resolve(window[k]()).catch(()=>{})}catch(_){}}
function services(g){try{return billingServicesHtml({items:g.items||[],patient:g.patient,fecha:g.fecha})}catch(_){return(g.items||[]).map(x=>`<div class="billing-line"><span>${e(x.visit?.tipo||'Atención')}</span><strong>${cash(x.visit?.valor)}</strong></div>`).join('')}}
function render(){const list=document.querySelector('#billingList');if(!list)return;archive=true;tab();if(!cache.length){list.innerHTML='<div class="v4459-empty">No hay fichas marcadas como No facturables.</div>';return}list.innerHTML=cache.map(g=>{const p=g.patient||{},f=String(g.fecha||'').slice(0,10);return`<article class="billing-card pendiente" data-patient-id="${p.id}" data-fecha="${e(f)}"><div class="billing-card-head"><div><div class="billing-patient-name">${e(p.nombre||'Paciente')}</div><div class="billing-meta"><span><b>Cédula:</b> ${e(p.cedula||'Sin cédula')}</span><span><b>Fecha:</b> ${fd(f)}</span></div></div><span class="billing-status v4459-status">NO FACTURABLE</span></div><div class="v4459-reason">Motivo: Paciente sin cédula/identificación</div><div class="billing-lines">${services(g)}</div><div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${cash(g.total)}</strong></div><div class="billing-actions"><button class="v4459-restore">↩ Volver a pendientes</button></div></div></article>`}).join('');list.querySelectorAll('.billing-card').forEach(c=>{const k=id(c);if(k)c.querySelector('.v4459-restore').onclick=()=>restore(...k)})}
async function open(){archive=true;const s=document.querySelector('#bEstado');if(s)s.value='PENDIENTE';const d=await count();if(d)render()}
function later(){clearTimeout(timer);timer=setTimeout(()=>{tab();decorate()},30)}
const old=window.loadBilling;if(typeof old==='function'){window.loadBilling=async function(){archive=false;const r=await old.apply(this,arguments);tab();await count();decorate();return r}}
const oldSet=window.setBillingStatus;if(typeof oldSet==='function'){window.setBillingStatus=async function(){archive=false;const r=await oldSet.apply(this,arguments);tab();await count();decorate();return r}}
const start=()=>{tab();count().finally(later);const l=document.querySelector('#billingList');if(l)new MutationObserver(later).observe(l,{childList:true})};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        previous.FEATURE_BOOT_ERROR = (str(getattr(previous, "FEATURE_BOOT_ERROR", "") or "") + " | v4.4.59: " + PATCH_BOOT_ERROR).strip(" |")[:1200]
    except Exception:
        pass
    try:
        core.logging.getLogger(__name__).error("v4.4.59 patch failed: %s\n%s", PATCH_BOOT_ERROR, _traceback.format_exc())
    except Exception:
        pass


@app.get("/api/v4459/non-billable-health")
def v4459_health(user=core.Depends(core.current_user)):
    return {"ok": PATCH_BOOT_OK, "version": APP_VERSION, "error": PATCH_BOOT_ERROR, "schema_migration": False, "attention_changed": False}
