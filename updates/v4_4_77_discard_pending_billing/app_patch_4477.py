from __future__ import annotations

# v4.4.77 — quitar facturas de Por emitir sin borrar la atención.
# - Parte de v4.4.76 y conserva historial fiscal, servicios compactos y guardado rápido.
# - Agrega "Quitar de Por emitir" únicamente a comprobantes aún no enviados.
# - No borra paciente ni atención: marca las líneas de facturación como DESCARTADA.
# - Una línea DESCARTADA queda fuera de futuros envíos a AZUR.
# - Si el comprobante ya fue enviado a AZUR, el servidor bloquea la operación.
# - No agrega MutationObserver ni toca el recibo térmico.

from datetime import date as _date

import app_patch_4476 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.77"

_mod = previous
_seen = set()
for _ in range(36):
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

try:
    class V4477DiscardBillingIn(core.BaseModel):
        patient_id: int
        fecha: _date

    # DESCARTADA no es una factura emitida ni elimina la atención clínica.
    # La quitamos también del grupo operativo para que nunca vuelva a entrar
    # accidentalmente en un envío futuro si ese paciente recibe otra atención
    # el mismo día.
    _stable_billing_group_records = core.billing_group_records

    def _billing_group_records_v4477(db, patient_id: int, fecha):
        rows = _stable_billing_group_records(db, int(patient_id), fecha)
        return [
            (billing, visit)
            for billing, visit in rows
            if str(getattr(billing, "estado", "") or "").upper() != "DESCARTADA"
        ]

    core.billing_group_records = _billing_group_records_v4477

    @app.post("/api/v4477/billing/discard")
    def v4477_discard_pending_billing(
        data: V4477DiscardBillingIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        if core.is_offline_db(db):
            raise core.HTTPException(
                503,
                "Quitar una factura de Por emitir requiere conexión a Internet.",
            )

        patient = db.get(core.Patient, int(data.patient_id))
        if not patient:
            raise core.HTTPException(404, "Paciente no encontrado")

        rows = _stable_billing_group_records(
            db, int(data.patient_id), data.fecha
        )
        rows = [
            (billing, visit)
            for billing, visit in rows
            if str(getattr(billing, "estado", "") or "").upper()
            in {"PENDIENTE", "APROBADA"}
        ]
        if not rows:
            raise core.HTTPException(
                404,
                "Esta factura ya no está en Por emitir.",
            )

        group_key = core._azur_group_key_for_rows(
            int(data.patient_id), data.fecha, rows
        )
        emission = db.scalar(
            core.select(core.AzurEmission).where(
                core.AzurEmission.group_key == group_key
            )
        )
        if emission and (
            str(getattr(emission, "clave_acceso", "") or "").strip()
            or str(getattr(emission, "numero_factura", "") or "").strip()
        ):
            raise core.HTTPException(
                409,
                "Esta factura ya fue enviada a AZUR y no puede eliminarse de Por emitir.",
            )

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
            "message": (
                "Factura quitada de Por emitir. "
                "La atención y el paciente se conservaron."
            ),
        }

    V4477_CSS = r"""
.v4477-discard-billing{
  border:1px solid #dfb4b4!important;
  background:#fff6f6!important;
  color:#963d3d!important;
}
.v4477-discard-billing:hover{
  background:#fdecec!important;
  border-color:#cf8f8f!important;
}
"""

    V4477_JS = r"""
;(()=>{
  if(window.__v4477DiscardPendingBilling)return;
  window.__v4477DiscardPendingBilling=true;
  const VERSION='4.4.77';

  const apiCall=(url,opt={})=>{
    const fn=window.api;
    return typeof fn==='function'
      ?fn(url,opt)
      :Promise.reject(new Error('API no disponible'));
  };

  window.v4477DiscardPendingBilling=async function(patientId,fecha,event){
    try{event?.preventDefault?.();event?.stopPropagation?.()}catch(_e){}
    const msg='¿Quitar esta factura de Por emitir?\n\n'
      +'La atención y el paciente NO se borrarán. '
      +'Solo desaparecerá de la cola de facturación.\n\n'
      +'Si ya fue enviada a AZUR, el sistema no permitirá quitarla.';
    const ok=typeof window.rpConfirm==='function'
      ?await window.rpConfirm(msg,'Quitar de Por emitir')
      :window.confirm(msg);
    if(!ok)return;

    try{
      const out=await apiCall('/api/v4477/billing/discard',{
        method:'POST',
        body:JSON.stringify({
          patient_id:Number(patientId),
          fecha:String(fecha||'').slice(0,10)
        })
      });
      try{if(typeof window.loadBilling==='function')await window.loadBilling()}catch(_e){}
      try{if(typeof window.refreshPendingBadges==='function')await window.refreshPendingBadges()}catch(_e){}
      const message=out?.message||'Factura quitada de Por emitir.';
      if(typeof window.rpNotice==='function')window.rpNotice(message);
      else alert(message);
    }catch(e){
      alert(e?.message||String(e));
    }
  };

  const stableBillingCardHtml=window.billingCardHtml;
  if(typeof stableBillingCardHtml==='function'){
    window.billingCardHtml=function(group){
      let html=stableBillingCardHtml.apply(this,arguments);
      const view=String(document.querySelector('#bEstado')?.value||'PENDIENTE').toUpperCase();
      if(view==='EMITIDA'||!html)return html;

      const patientId=Number(group?.patient?.id||0);
      const fecha=String(group?.fecha||group?.items?.[0]?.visit?.fecha||'').slice(0,10);
      if(!patientId||!/^\d{4}-\d{2}-\d{2}$/.test(fecha))return html;

      const button=`<button type="button" class="v4477-discard-billing" onclick="v4477DiscardPendingBilling(${patientId},'${fecha}',event)">🗑 Quitar de Por emitir</button>`;
      const marker='<div class="billing-actions">';
      if(html.includes(marker)){
        html=html.replace(marker,marker+button);
      }else{
        html=html.replace('</article>',`<div class="billing-actions">${button}</div></article>`);
      }
      return html;
    };
  }

  try{
    const badges=document.querySelectorAll('.v460-version,#currentVersionBadge');
    badges.forEach(el=>{el.textContent='v'+VERSION});
  }catch(_e){}
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4477_CSS
    )
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "")
        .replace("const VERSION='4.4.76';", "const VERSION='4.4.77';")
        + "\n"
        + V4477_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.77 discard pending billing patch failed: %s",
            PATCH_BOOT_ERROR,
        )
    except Exception:
        pass


@app.get("/api/v4477/health")
def v4477_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "discard_pending_billing": True,
        "discard_preserves_visit": True,
        "discard_excluded_from_future_azur": True,
        "base": "4.4.76",
        "uses_new_dom_observer": False,
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
