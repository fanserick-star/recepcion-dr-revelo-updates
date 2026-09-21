from __future__ import annotations

# v4.5.5 — ajuste visual de cobros + tarjeta reservada para datáfono automático.
#
# - Forma de pago más legible y con tipografía mayor.
# - Procedimientos/servicios más compactos para reducir ruido visual.
# - La opción Tarjeta ya NO pide datos manuales en Nueva atención.
# - Hasta conectar el datáfono, Tarjeta se muestra como preparada pero no activa.
# - Pago mixto sigue disponible con Efectivo + Transferencia; las partes con
#   tarjeta se habilitarán cuando exista integración real con el datáfono.
# - No cambia base de datos, Neon, AZUR, Agenda ni diseños térmicos.

import os

import app_patch_4504 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.5"

_mod = previous
_seen = set()
for _ in range(130):
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
    V4505_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.5"!important;
  font-size:9px!important;
  line-height:1!important;
  font-weight:850!important
}

/* Forma de pago: más grande y clara */
.v4504-pay-head b{
  font-size:14px!important;
  line-height:1.15!important;
  letter-spacing:-.01em!important
}
.v4504-pay-head small{
  font-size:9px!important;
  line-height:1.35!important
}
.v4504-pay-state{
  font-size:9px!important;
  padding:5px 9px!important
}
.v4504-pay-option{
  min-height:56px!important;
  padding:9px 10px!important
}
.v4504-pay-option>span{
  font-size:18px!important
}
.v4504-pay-option>b{
  font-size:12px!important;
  line-height:1.1!important
}
.v4504-pay-option>small{
  font-size:8.5px!important;
  line-height:1.15!important
}

/* Tarjeta queda visualmente preparada, pero la operación será del datáfono. */
.v4504-pay-option[data-mode="TARJETA"]{
  position:relative!important;
  border-style:dashed!important;
  background:#f8fafc!important
}
.v4504-pay-option[data-mode="TARJETA"] b{
  font-size:0!important
}
.v4504-pay-option[data-mode="TARJETA"] b::after{
  content:"Tarjeta";
  font-size:12px!important;
  font-weight:900
}
.v4504-pay-option[data-mode="TARJETA"] small{
  font-size:0!important
}
.v4504-pay-option[data-mode="TARJETA"] small::after{
  content:"Con datáfono";
  font-size:8.5px!important;
  color:#72859a!important
}
#v4504Card{
  display:none!important
}

/* Procedimientos y servicios: más compactos que los cobros. */
.attention-form-modal .service-card[data-service]{
  min-height:0!important;
  padding:8px 9px!important;
  border-radius:10px!important
}
.attention-form-modal .service-card[data-service] b,
.attention-form-modal .service-card[data-service] strong{
  font-size:9.5px!important;
  line-height:1.15!important
}
.attention-form-modal .service-card[data-service] .service-price{
  font-size:10px!important;
  line-height:1.1!important
}
.attention-form-modal .service-card[data-service] small,
.attention-form-modal .service-card[data-service] .muted{
  font-size:7.5px!important;
  line-height:1.2!important
}

/* Facturación: forma de pago también gana jerarquía. */
.v4504-billpay-head span{
  font-size:10px!important
}
.v4504-billpay-head b{
  font-size:10.5px!important
}
.v4504-billchoices button{
  font-size:9.5px!important;
  min-height:31px!important
}

/* Nota discreta del futuro datáfono. */
.v4505-dataphone-note{
  margin-top:8px;
  padding:8px 10px;
  border:1px dashed #cbd8e5;
  border-radius:10px;
  background:#f9fbfd;
  color:#61758a;
  font-size:8.5px;
  line-height:1.35
}
.v4505-dataphone-note b{
  color:#355a78
}
"""

    V4505_JS = r"""
;(()=>{
  if(window.__v4505VisualAndDataphone)return;
  window.__v4505VisualAndDataphone=true;
  const VERSION='4.5.5';

  function paymentHost(){
    return document.querySelector('.attention-form-modal #v4504Payment');
  }

  function paintDataphoneNote(){
    const host=paymentHost();
    if(!host)return;

    const card=host.querySelector('[data-mode="TARJETA"]');
    if(card){
      card.setAttribute('aria-disabled','true');
      card.setAttribute(
        'title',
        'La tarjeta se habilitará cuando el datáfono esté conectado al programa.'
      );
    }

    let note=host.querySelector('.v4505-dataphone-note');
    if(!note){
      note=document.createElement('div');
      note.className='v4505-dataphone-note';
      note.innerHTML=
        '<b>💳 Datáfono:</b> cuando llegue el equipo, Tarjeta enviará el valor '
        +'directamente al terminal y el programa recibirá aprobación, tipo de '
        +'tarjeta y autorización automáticamente. No tendrás que escribir esos datos.';
      host.appendChild(note);
    }
  }

  function notifyDataphonePending(){
    const msg=
      'Tarjeta quedará automatizada con el datáfono. '
      +'Para conectarlo necesito el modelo del equipo y el proveedor/adquirente '
      +'cuando lo reciban.';
    if(typeof window.rpToast==='function'){
      try{window.rpToast(msg,'info');return}catch(_e){}
    }
    alert(msg);
  }

  // Bloquea el flujo manual de tarjeta de v4.5.4.
  document.addEventListener('click',event=>{
    // v4.5.24 compatibilidad: Bendo manual reemplazó el flujo automático
    // planificado en v4.5.5. No interceptar ningún clic cuando el flujo
    // Bendo actual ya está instalado.
    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;
    const card=event.target?.closest?.(
      '.attention-form-modal [data-mode="TARJETA"]'
    );
    if(!card)return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    notifyDataphonePending();
  },true);

  // Facturación tampoco permite registrar tarjeta manualmente.
  document.addEventListener('click',event=>{
    const paymentButton=event.target?.closest?.(
      '#billingList .v4504-billchoices [data-bm]'
    );
    if(!paymentButton)return;
    const method=String(paymentButton.dataset.bm||'');
    if(method!=='TARJETA_DEBITO'&&method!=='TARJETA_CREDITO')return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    notifyDataphonePending();
  },true);

  // En Pago mixto, por ahora solo Efectivo + Transferencia.
  document.addEventListener('change',event=>{
    if(window.__v4507BendoManual||window.__v4523BendoOperation)return;
    const select=event.target;
    if(!select?.matches?.('#v4504MixA,#v4504MixB'))return;
    if(!String(select.value||'').startsWith('TARJETA_'))return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    if(select.id==='v4504MixA'){
      select.value='EFECTIVO';
    }else{
      select.value='TRANSFERENCIA';
    }
    notifyDataphonePending();
  },true);

  // Filtra visualmente las opciones de tarjeta en mixto sin observers persistentes.
  function compactMixed(){
    document.querySelectorAll(
      '#v4504MixA option[value^="TARJETA_"],#v4504MixB option[value^="TARJETA_"]'
    ).forEach(option=>{
      option.disabled=true;
      option.hidden=true;
    });
  }

  function refresh(){
    paintDataphoneNote();
    compactMixed();
    document.querySelectorAll(
      '.v460-version,#currentVersionBadge'
    ).forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
  }

  const stableAttentionFor=window.attentionFor;
  if(typeof stableAttentionFor==='function'){
    window.attentionFor=async function(){
      const result=await stableAttentionFor.apply(this,arguments);
      setTimeout(refresh,40);
      setTimeout(refresh,180);
      setTimeout(refresh,360);
      return result;
    };
  }

  document.addEventListener('click',event=>{
    if(
      event.target?.closest?.(
        '.attention-form-modal .service-card,[data-mode="MIXTO"],[data-mode="EFECTIVO"],[data-mode="TRANSFERENCIA"]'
      )
    ){
      setTimeout(refresh,35);
      setTimeout(refresh,150);
    }
  },true);

  function boot(){
    refresh();
  }

  if(document.readyState==='loading'){
    document.addEventListener(
      'DOMContentLoaded',
      boot,
      {once:true}
    );
  }else{
    boot();
  }

  window.__v4505DataphoneState={
    automatic:true,
    connected:false,
    manualCardEntry:false,
    needs:['modelo del datáfono','proveedor/adquirente','método de integración']
  };
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "")
        + "\n"
        + V4505_CSS
    )
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "")
        + "\n"
        + V4505_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4505/dataphone/status")
def v4505_dataphone_status(
    user=core.Depends(core.current_user),
):
    provider = str(
        os.getenv("RP_DATAPHONE_PROVIDER") or ""
    ).strip()
    model = str(
        os.getenv("RP_DATAPHONE_MODEL") or ""
    ).strip()
    return {
        "ok": True,
        "version": APP_VERSION,
        "automatic_flow_designed": True,
        "connected": False,
        "manual_card_entry": False,
        "provider": provider or None,
        "model": model or None,
        "needs_device_details": not bool(provider and model),
        "message": (
            "Compatibilidad v4.5.5: este aviso quedó obsoleto; el flujo vigente es Bendo manual asistido. "
            "No se requiere modelo/proveedor para automatización porque no se usa integración automática."
        ),
    }


@app.get("/api/v4505/health")
def v4505_health(
    user=core.Depends(core.current_user),
):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "payment_typography_enlarged": True,
        "services_typography_compacted": True,
        "manual_card_entry_disabled": True,
        "dataphone_automatic_flow_planned": True,
        "cash_closing": False,
        "database_changes": False,
        "database_schema_changes": False,
        "neon_writes_added": False,
        "azur_contract_changes": False,
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
