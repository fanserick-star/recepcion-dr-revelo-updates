from __future__ import annotations

from datetime import date as _date
import core_runtime as core

app = core.app
APP_VERSION = getattr(core, "APP_VERSION", "")
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""


class DiscardBillingIn(core.BaseModel):
    patient_id: int
    fecha: _date


_stable_billing_group_records = core.billing_group_records


def _billing_group_records_without_discarded(db, patient_id: int, fecha):
    rows = _stable_billing_group_records(db, int(patient_id), fecha)
    return [
        (billing, visit)
        for billing, visit in rows
        if str(getattr(billing, "estado", "") or "").upper() != "DESCARTADA"
    ]


core.billing_group_records = _billing_group_records_without_discarded


@app.post("/api/billing/discard")
def discard_pending_billing(
    data: DiscardBillingIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    if core.is_offline_db(db):
        raise core.HTTPException(503, "Quitar una factura de Por emitir requiere conexión a Internet.")
    patient = db.get(core.Patient, int(data.patient_id))
    if not patient:
        raise core.HTTPException(404, "Paciente no encontrado")
    rows = _stable_billing_group_records(db, int(data.patient_id), data.fecha)
    rows = [
        (billing, visit)
        for billing, visit in rows
        if str(getattr(billing, "estado", "") or "").upper() in {"PENDIENTE", "APROBADA"}
    ]
    if not rows:
        raise core.HTTPException(404, "Esta factura ya no está en Por emitir.")
    group_key = core._azur_group_key_for_rows(int(data.patient_id), data.fecha, rows)
    emission = db.scalar(core.select(core.AzurEmission).where(core.AzurEmission.group_key == group_key))
    if emission and (
        str(getattr(emission, "clave_acceso", "") or "").strip()
        or str(getattr(emission, "numero_factura", "") or "").strip()
    ):
        raise core.HTTPException(409, "Esta factura ya fue enviada a AZUR y no puede eliminarse de Por emitir.")
    touched = []
    for billing, _visit in rows:
        billing.estado = "DESCARTADA"
        billing.approved_at = None
        billing.numero_factura = None
        billing.emitted_at = None
        touched.append(billing)
    core.audit(
        db,
        user,
        "descartar_factura_pendiente",
        f"Paciente {int(data.patient_id)}, fecha {data.fecha}, líneas {len(touched)}",
    )
    db.commit()
    for billing in touched:
        try:
            core.mirror_billing_to_local(billing)
        except Exception:
            pass
    return {
        "ok": True,
        "patient_id": int(data.patient_id),
        "fecha": data.fecha.isoformat(),
        "discarded": len(touched),
        "message": "Factura quitada de Por emitir. La atención y el paciente se conservaron.",
    }


BILLING_DISCARD_JS = r''';(()=>{
 if(window.__billingDiscardCanonical)return;window.__billingDiscardCanonical=true;
 window.discardPendingBilling=async function(patientId,fecha,event){
   try{event?.preventDefault?.();event?.stopPropagation?.()}catch(_e){}
   const msg='¿Quitar esta factura de Por emitir?\n\nLa atención y el paciente NO se borrarán. Solo desaparecerá de la cola de facturación.\n\nSi ya fue enviada a AZUR, el sistema no permitirá quitarla.';
   const ok=typeof window.rpConfirm==='function'?await window.rpConfirm(msg,'Quitar de Por emitir'):window.confirm(msg);
   if(!ok)return;
   try{
     const fn=window.api;if(typeof fn!=='function')throw new Error('API no disponible');
     const out=await fn('/api/billing/discard',{method:'POST',body:JSON.stringify({patient_id:Number(patientId),fecha:String(fecha||'').slice(0,10)})});
     if(typeof window.loadBilling==='function')await window.loadBilling();
     try{if(typeof window.refreshPendingBadges==='function')await window.refreshPendingBadges()}catch(_e){}
     const message=out?.message||'Factura quitada de Por emitir.';
     if(typeof window.rpNotice==='function')window.rpNotice(message);else alert(message);
   }catch(e){alert(e?.message||String(e))}
 };
})();'''

try:
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + BILLING_DISCARD_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/billing/discard/health")
def billing_discard_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "canonical": True,
        "post_render_decorator": False,
        "version_painter": False,
    }
