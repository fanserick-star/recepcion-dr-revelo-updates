from __future__ import annotations

# v4.5.7 — Bendo Smart: flujo manual asistido según respuesta oficial de Bendo.
#
# Confirmado por Atención Cliente Bendo (18-09-2026):
# - Actualmente no ofrecen integración API para plataformas.
# - El cobro en Bendo Smart se realiza manualmente.
#
# Esta versión:
# - Habilita Tarjeta en Nueva atención con flujo manual asistido.
# - Muestra el total exacto a digitar en Bendo Smart.
# - Exige confirmar "Pago aprobado" antes de guardar la atención.
# - Permite registrar Débito/Crédito y voucher/autorización opcional.
# - No pide PAN/CVV.
# - Configuración > Datáfono muestra estado real: Bendo Smart / Manual asistido.
# - Conserva un bloque de "Integración futura" solo como preparación, sin fingir
#   que existe una API oficial hoy.
# - No cambia DB/Neon/Agenda ni diseños térmicos.

import app_patch_4506 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.7"

_mod = previous
_seen = set()
for _ in range(150):
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
    V4507_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.7"!important;
  font-size:9px!important;
  line-height:1!important;
  font-weight:850!important
}

/* Ocultamos la opción Tarjeta heredada que v4.5.5 dejó bloqueada. */
.attention-form-modal .v4504-pay-option[data-mode="TARJETA"]{
  display:none!important
}

/* 3 columnas: efectivo, transferencia y Bendo Smart. */
.attention-form-modal .v4504-pay-options{
  grid-template-columns:repeat(3,minmax(0,1fr))!important
}

.v4507-bendo-option{
  min-height:61px!important;
  border:1px solid #b9cad9!important;
  border-radius:11px!important;
  background:#fff!important;
  color:#36536d!important;
  padding:10px 11px!important;
  box-shadow:none!important;
  display:grid!important;
  grid-template-columns:auto 1fr;
  grid-template-rows:auto auto;
  column-gap:8px;
  text-align:left!important
}
.v4507-bendo-option>span{
  grid-row:1/3;
  align-self:center;
  font-size:20px
}
.v4507-bendo-option>b{
  font-size:13px;
  line-height:1.1
}
.v4507-bendo-option>small{
  font-size:9px;
  color:#75899c
}
.v4507-bendo-option.selected{
  border-color:#6eaa88!important;
  background:#edf8f2!important;
  color:#245e41!important
}

.v4507-bendo-panel{
  margin-top:10px;
  padding:12px;
  border:1px solid #d7e1eb;
  border-radius:12px;
  background:#fff
}
.v4507-bendo-panel.hidden{display:none!important}
.v4507-bendo-amount{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:10px 12px;
  border-radius:10px;
  background:#eef6ff;
  border:1px solid #d1e2f2
}
.v4507-bendo-amount span{
  font-size:9px;
  font-weight:850;
  color:#60778d
}
.v4507-bendo-amount strong{
  font-size:24px;
  color:#1f4f7e;
  letter-spacing:-.02em
}
.v4507-bendo-steps{
  margin:10px 0 0;
  padding:0 0 0 18px;
  color:#596e83;
  font-size:9px;
  line-height:1.45
}
.v4507-bendo-type{
  display:flex;
  gap:7px;
  margin-top:10px
}
.v4507-bendo-type button{
  min-height:34px!important;
  border-radius:9px!important;
  border:1px solid #ced9e4!important;
  background:#fff!important;
  color:#50677e!important;
  box-shadow:none!important;
  font-size:9px!important;
  font-weight:850!important
}
.v4507-bendo-type button.selected{
  background:#eaf4ff!important;
  border-color:#85acd3!important;
  color:#265e93!important
}
.v4507-bendo-meta{
  display:grid;
  grid-template-columns:1fr auto;
  gap:8px;
  margin-top:9px;
  align-items:end
}
.v4507-bendo-meta label{
  display:block;
  margin-bottom:4px;
  font-size:7.5px;
  font-weight:850;
  color:#75889b;
  text-transform:uppercase
}
.v4507-bendo-meta input{
  height:34px!important;
  border-radius:8px!important;
  font-size:9px!important
}
.v4507-bendo-confirm{
  min-height:36px!important;
  border-radius:9px!important;
  font-size:9px!important;
  font-weight:900!important
}
.v4507-bendo-confirm.confirmed{
  background:#e5f6eb!important;
  border-color:#83bd99!important;
  color:#246944!important
}
.v4507-bendo-warning{
  margin-top:9px;
  padding:8px 10px;
  border-radius:9px;
  background:#fff8e8;
  border:1px solid #ead59f;
  color:#7d641f;
  font-size:8px;
  line-height:1.35
}

/* La nota antigua de "cuando llegue el datáfono" ya no aplica. */
.v4505-dataphone-note{display:none!important}

/* Configuración realista para Bendo */
.v4507-config{
  max-width:980px
}
.v4507-config-hero{
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  gap:14px;
  align-items:center;
  padding:16px 17px;
  border:1px solid #d8e4ee;
  border-radius:15px;
  background:linear-gradient(135deg,#f7fbff,#eef6ff)
}
.v4507-config-hero h3{
  margin:0 0 4px;
  font-size:18px;
  color:#24415e
}
.v4507-config-hero p{
  margin:0;
  font-size:10px;
  line-height:1.4;
  color:#687d91
}
.v4507-status-pill{
  padding:6px 10px;
  border-radius:999px;
  border:1px solid #ead29a;
  background:#fff5dd;
  color:#7c5a18;
  font-size:9px;
  font-weight:900;
  white-space:nowrap
}
.v4507-config-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:10px;
  margin-top:10px
}
.v4507-config-card{
  padding:13px 14px;
  border:1px solid #dfe7ef;
  border-radius:13px;
  background:#fff
}
.v4507-config-card.full{grid-column:1/-1}
.v4507-config-card h4{
  margin:0 0 4px;
  font-size:12px;
  color:#35536e
}
.v4507-config-card p,
.v4507-config-card li{
  font-size:9px;
  line-height:1.45;
  color:#687b8e
}
.v4507-config-card ul{
  margin:7px 0 0;
  padding-left:18px
}
.v4507-config-flow{
  display:grid;
  grid-template-columns:repeat(5,auto);
  gap:6px;
  align-items:center;
  justify-content:start;
  margin-top:8px;
  font-size:9px;
  font-weight:800;
  color:#456078
}
.v4507-config-flow span{
  padding:6px 8px;
  border:1px solid #dde6ee;
  border-radius:8px;
  background:#f9fbfd
}
.v4507-config-note{
  margin-top:9px;
  padding:9px 10px;
  border-radius:9px;
  background:#f4f7fa;
  color:#607386;
  font-size:8.5px;
  line-height:1.4
}
.v4507-future{
  margin-top:10px
}
.v4507-future summary{
  cursor:pointer;
  font-size:9px;
  font-weight:850;
  color:#526c84
}
.v4507-future div{
  margin-top:8px;
  padding:9px 10px;
  border:1px dashed #ccd8e3;
  border-radius:9px;
  color:#6b7d8f;
  font-size:8.5px;
  line-height:1.4
}
@media(max-width:760px){
  .attention-form-modal .v4504-pay-options{
    grid-template-columns:1fr!important
  }
  .v4507-bendo-meta{grid-template-columns:1fr}
  .v4507-config-grid{grid-template-columns:1fr}
  .v4507-config-flow{grid-template-columns:1fr}
}
"""

    V4507_JS = r"""
;(()=>{
  if(window.__v4507BendoManual)return;
  window.__v4507BendoManual=true;

  const VERSION='4.5.7';
  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
  const money=n=>'$'+Number(n||0).toFixed(2);

  let bendoSelected=false;
  let bendoConfirmed=false;
  let bendoType='DEBITO';
  let bendoVoucher='';
  let confirmedAmount=0;

  function attentionBox(){
    return document.querySelector('.attention-form-modal');
  }

  function total(){
    try{
      return Number(window.__v4504PaymentTest?.total?.()||0);
    }catch(_e){
      return 0;
    }
  }

  function setInternalFallback(){
    // v4.5.4 necesita internamente un método válido antes de guardar.
    // Lo dejamos en EFECTIVO y reemplazamos el payload por tarjeta justo
    // antes de llegar al servidor, solo si el pago Bendo fue confirmado.
    const btn=q('.attention-form-modal .v4504-pay-option[data-mode="EFECTIVO"]');
    if(btn&&!btn.classList.contains('selected')){
      btn.click();
    }
  }

  function resetConfirmation(){
    bendoConfirmed=false;
    confirmedAmount=0;
    renderBendo();
  }

  function ensureBendo(){
    const box=attentionBox();
    const options=q('.v4504-pay-options',box);
    if(!box||!options)return;

    let button=q('#v4507BendoOption',box);
    if(!button){
      button=document.createElement('button');
      button.id='v4507BendoOption';
      button.type='button';
      button.className='v4507-bendo-option';
      button.innerHTML='<span>💳</span><b>Tarjeta</b><small>Bendo Smart · manual asistido</small>';
      options.appendChild(button);
      button.addEventListener('click',()=>{
        bendoSelected=true;
        bendoConfirmed=false;
        confirmedAmount=0;
        setInternalFallback();
        renderBendo();
      });
    }

    let panel=q('#v4507BendoPanel',box);
    if(!panel){
      panel=document.createElement('div');
      panel.id='v4507BendoPanel';
      panel.className='v4507-bendo-panel hidden';
      options.insertAdjacentElement('afterend',panel);
    }
    renderBendo();
  }

  function renderBendo(){
    const box=attentionBox();
    if(!box)return;
    const button=q('#v4507BendoOption',box);
    const panel=q('#v4507BendoPanel',box);
    if(!button||!panel)return;

    const amount=total();
    button.classList.toggle('selected',bendoSelected);
    panel.classList.toggle('hidden',!bendoSelected);

    if(!bendoSelected)return;

    const amountChanged=bendoConfirmed&&Math.abs(amount-confirmedAmount)>0.009;
    if(amountChanged){
      bendoConfirmed=false;
      confirmedAmount=0;
    }

    panel.innerHTML=
      '<div class="v4507-bendo-amount"><span>DIGITA ESTE VALOR EN BENDO SMART</span>'
      +'<strong>'+money(amount)+'</strong></div>'
      +'<ol class="v4507-bendo-steps">'
      +'<li>En el Bendo Smart inicia un cobro por <b>'+money(amount)+'</b>.</li>'
      +'<li>El paciente paga directamente en el equipo.</li>'
      +'<li>Cuando Bendo muestre el pago como aprobado, selecciona el tipo y confirma aquí.</li>'
      +'</ol>'
      +'<div class="v4507-bendo-type">'
      +'<button type="button" data-v4507-card="DEBITO" class="'+(bendoType==='DEBITO'?'selected':'')+'">Débito · SRI 16</button>'
      +'<button type="button" data-v4507-card="CREDITO" class="'+(bendoType==='CREDITO'?'selected':'')+'">Crédito · SRI 19</button>'
      +'</div>'
      +'<div class="v4507-bendo-meta"><div><label>Voucher / autorización</label>'
      +'<input id="v4507Voucher" maxlength="40" autocomplete="off" placeholder="Opcional" value="'+esc(bendoVoucher)+'"></div>'
      +'<button id="v4507Confirm" type="button" class="v4507-bendo-confirm '+(bendoConfirmed?'confirmed':'')+'">'
      +(bendoConfirmed?'✓ Pago aprobado confirmado':'Confirmar pago aprobado')+'</button></div>'
      +'<div class="v4507-bendo-warning">'
      +'<b>No confirmes antes de tiempo.</b> Recepción no puede consultar el Bendo automáticamente hoy; '
      +'esta confirmación indica que viste el pago aprobado en el equipo.'
      +'</div>';

    qa('[data-v4507-card]',panel).forEach(btn=>btn.addEventListener('click',()=>{
      bendoType=btn.dataset.v4507Card||'DEBITO';
      bendoConfirmed=false;
      confirmedAmount=0;
      renderBendo();
    }));

    q('#v4507Voucher',panel)?.addEventListener('input',e=>{
      bendoVoucher=e.target.value;
    });

    q('#v4507Confirm',panel)?.addEventListener('click',()=>{
      const current=total();
      if(current<=0){
        alert('Selecciona primero una consulta o procedimiento con valor.');
        return;
      }
      bendoConfirmed=true;
      confirmedAmount=current;
      renderBendo();
    });
  }

  function cardPayload(){
    if(!bendoSelected)return null;
    const amount=total();
    if(!bendoConfirmed){
      throw Error('Primero cobra en el Bendo Smart y confirma aquí que el pago fue aprobado.');
    }
    if(Math.abs(amount-confirmedAmount)>0.009){
      bendoConfirmed=false;
      confirmedAmount=0;
      throw Error('El valor de la atención cambió. Verifica el nuevo total en Bendo y vuelve a confirmar el pago.');
    }
    return {
      payment_method:bendoType==='CREDITO'?'TARJETA_CREDITO':'TARJETA_DEBITO',
      card_plan:bendoType==='CREDITO'?'CORRIENTE':null,
      installments:bendoType==='CREDITO'?1:null,
      voucher:String(bendoVoucher||'').trim()
    };
  }

  // v4.5.5 bloquea el botón viejo Tarjeta. Nosotros añadimos nuestro propio
  // botón y reemplazamos el payload de la atención solo después de confirmar.
  const stableSave=window.saveAttention;
  if(typeof stableSave==='function'){
    window.saveAttention=async function(){
      let replacement=null;
      try{
        replacement=cardPayload();
      }catch(error){
        alert(error?.message||String(error));
        return;
      }

      if(!replacement){
        return await stableSave.apply(this,arguments);
      }

      setInternalFallback();

      const originalWindowApi=window.api;
      const originalGlobalApi=typeof api!=='undefined'?api:null;
      const baseApi=originalWindowApi||originalGlobalApi;

      const intercept=async function(url,opt={}){
        if(String(url)==='/api/visits/batch-payment'){
          let body={};
          try{
            body=JSON.parse(opt?.body||'{}');
          }catch(_e){}
          Object.assign(body,replacement);
          return baseApi(url,{...opt,body:JSON.stringify(body)});
        }
        return baseApi(url,opt);
      };

      try{
        window.api=intercept;
        try{api=intercept}catch(_e){}
        const result=await stableSave.apply(this,arguments);
        return result;
      }finally{
        window.api=originalWindowApi;
        try{api=originalGlobalApi}catch(_e){}
      }
    };
  }

  // Si el usuario toca Efectivo, Transferencia o Mixto, salimos del flujo Bendo.
  document.addEventListener('click',event=>{
    const btn=event.target?.closest?.(
      '.attention-form-modal .v4504-pay-option[data-mode="EFECTIVO"],'
      +'.attention-form-modal .v4504-pay-option[data-mode="TRANSFERENCIA"],'
      +'.attention-form-modal .v4504-pay-option[data-mode="MIXTO"]'
    );
    if(!btn)return;
    if(event.isTrusted){
      bendoSelected=false;
      bendoConfirmed=false;
      confirmedAmount=0;
      setTimeout(renderBendo,20);
    }
  },true);

  // Si cambian servicios/precios, cualquier confirmación anterior deja de valer.
  document.addEventListener('click',event=>{
    if(event.target?.closest?.('.attention-form-modal .service-card')){
      if(bendoSelected){
        bendoConfirmed=false;
        confirmedAmount=0;
      }
      setTimeout(ensureBendo,35);
      setTimeout(ensureBendo,150);
    }
  },true);

  document.addEventListener('input',event=>{
    if(
      bendoSelected
      &&event.target?.closest?.('.attention-form-modal')
      &&event.target?.type==='number'
    ){
      bendoConfirmed=false;
      confirmedAmount=0;
      setTimeout(renderBendo,20);
    }
  },true);

  const stableAttentionFor=window.attentionFor;
  if(typeof stableAttentionFor==='function'){
    window.attentionFor=async function(){
      bendoSelected=false;
      bendoConfirmed=false;
      bendoType='DEBITO';
      bendoVoucher='';
      confirmedAmount=0;
      const result=await stableAttentionFor.apply(this,arguments);
      setTimeout(ensureBendo,40);
      setTimeout(ensureBendo,170);
      setTimeout(ensureBendo,340);
      return result;
    };
  }

  function renderDataphoneConfig(){
    const section=q('[data-config-section="dataphone"]');
    if(!section)return;
    section.className='config-section v4507-config';

    section.innerHTML=
      '<div class="v4507-config-hero">'
      +'<div><h3>💳 Bendo Smart</h3>'
      +'<p>Configuración del flujo real que usaremos mientras Bendo no habilite integración ECR/API para plataformas externas.</p></div>'
      +'<span class="v4507-status-pill">MODO MANUAL ASISTIDO</span></div>'

      +'<div class="v4507-config-grid">'
      +'<section class="v4507-config-card"><h4>Estado actual</h4>'
      +'<p><b>Proveedor:</b> Bendo · <b>Equipo:</b> Bendo Smart</p>'
      +'<ul><li>El monto se digita manualmente en el Bendo Smart.</li>'
      +'<li>El pago se confirma visualmente en el terminal.</li>'
      +'<li>Recepción guarda Débito/Crédito y autorización opcional.</li>'
      +'<li>No se guarda número de tarjeta ni CVV.</li></ul></section>'

      +'<section class="v4507-config-card"><h4>Respuesta oficial</h4>'
      +'<p>Atención Cliente Bendo confirmó el 18/09/2026 que actualmente no manejan integración API para plataformas y que el sistema se opera de forma manual.</p>'
      +'<div class="v4507-config-note">Tenemos una última consulta enviada directamente a PUBLIPROMUEVE/PPM para confirmar si existe ECR, SDK, protocolo local o integración privada para partners.</div></section>'

      +'<section class="v4507-config-card full"><h4>Flujo en Recepción</h4>'
      +'<div class="v4507-config-flow">'
      +'<span>1 · Seleccionar Tarjeta</span><b>→</b>'
      +'<span>2 · Ver total</span><b>→</b>'
      +'<span>3 · Digitar en Bendo</span><b>→</b>'
      +'<span>4 · Paciente paga</span><b>→</b>'
      +'<span>5 · Confirmar aprobado</span></div>'
      +'<div class="v4507-config-note">El botón Guardar atención queda protegido: si elegiste Bendo, no permitirá registrar la atención como tarjeta hasta confirmar que el terminal mostró el pago aprobado.</div></section>'
      +'</div>'

      +'<details class="v4507-future"><summary>Integración futura (solo si PUBLIPROMUEVE la habilita)</summary>'
      +'<div>La infraestructura de v4.5.6 permanece en el programa para que, si PUBLIPROMUEVE nos entrega una API, SDK, ECR o protocolo oficial, podamos conectar el flujo automático sin reconstruir el módulo de cobros. Hasta entonces no se usan endpoints, tokens ni credenciales ficticias.</div>'
      +'</details>';
  }

  document.addEventListener('click',event=>{
    if(event.target?.closest?.('[data-config-tab="dataphone"]')){
      setTimeout(renderDataphoneConfig,60);
      setTimeout(renderDataphoneConfig,220);
    }
  },true);

  function boot(){
    qa('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
    ensureBendo();
    if(q('[data-config-section="dataphone"]:not(.hidden)')){
      renderDataphoneConfig();
    }
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',boot,{once:true});
  }else{
    boot();
  }

  window.__v4507BendoState={
    mode:'manual_assisted',
    provider:'BENDO',
    model:'Bendo Smart',
    apiPlatformAvailable:false,
    awaitingTechnicalReply:true
  };
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "")
        + "\n"
        + V4507_CSS
    )
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "")
        + "\n"
        + V4507_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4507/bendo/status")
def v4507_bendo_status(
    user=core.Depends(core.current_user),
):
    return {
        "ok": True,
        "version": APP_VERSION,
        "provider": "BENDO",
        "model": "Bendo Smart",
        "mode": "MANUAL_ASSISTED",
        "api_platform_available": False,
        "api_platform_source": "Bendo customer service reply 2026-09-18",
        "awaiting_ppm_technical_reply": True,
        "manual_card_entry": False,
        "pan_or_cvv_stored": False,
        "requires_approved_confirmation": True,
        "debit_credit_supported": True,
        "voucher_optional": True,
        "mixed_card_payment_enabled": False,
        "future_ecr_adapter_preserved": True,
    }


@app.get("/api/v4507/health")
def v4507_health(
    user=core.Depends(core.current_user),
):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "bendo_manual_assisted": True,
        "requires_terminal_approval_confirmation": True,
        "consultation_card_restored": True,
        "procedures_compact": True,
        "payment_typography_enlarged": True,
        "database_changes": False,
        "database_schema_changes": False,
        "neon_writes_added": False,
        "agenda_changes": False,
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
