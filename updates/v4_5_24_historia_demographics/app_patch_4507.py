from __future__ import annotations

# v4.5.7 — flujo real Bendo Smart (manual confirmado) + UI definitiva.
#
# Bendo confirmó por correo el 18/09/2026 que actualmente no maneja integración
# API para plataformas y que el cobro con Bendo Smart se realiza manualmente.
#
# Esta versión adapta Recepción a ese flujo real:
# - Tarjeta vuelve a estar disponible, pero como "Bendo Smart · manual".
# - Recepción muestra en grande el valor exacto a digitar en el terminal.
# - Para guardar una atención con tarjeta exige confirmar que el pago fue aprobado.
# - Permite registrar Débito/Crédito, corriente/diferido, cuotas y voucher opcional.
# - No guarda PAN/CVV ni intenta controlar el terminal.
# - Configuración > Datáfono deja de mostrar una API inexistente y explica el flujo
#   actual, conservando internamente la arquitectura futura por si PUBLIPROMUEVE
#   habilita ECR/SDK/API/Intent más adelante.
# - No cambia DB, Neon, AZUR, Agenda ni diseños térmicos.

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

/* Consulta conserva presencia; procedimientos siguen compactos. */
.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"],
.attention-form-modal .consultation-service-section .service-card[data-service="consulta"]{
  min-height:66px!important;
  padding:13px 42px!important;
  border-radius:13px!important
}
.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] b,
.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] b,
.attention-form-modal .consultation-service-section .service-card[data-service="CONSULTA"] strong,
.attention-form-modal .consultation-service-section .service-card[data-service="consulta"] strong{
  font-size:12.5px!important
}
.attention-form-modal .procedures-service-section .service-card[data-service]{
  min-height:46px!important;
  padding:7px 8px!important
}

/* La forma de pago tiene mayor jerarquía. */
.v4504-pay{
  padding:15px!important;
  border-radius:15px!important
}
.v4504-pay-head b{
  font-size:16px!important
}
.v4504-pay-head small{
  font-size:9.5px!important
}
.v4504-pay-option{
  min-height:63px!important;
  padding:10px 12px!important
}
.v4504-pay-option>span{
  font-size:21px!important
}
.v4504-pay-option>b,
.v4504-pay-option[data-v4507-card="1"] b{
  font-size:13px!important;
  line-height:1.1!important
}
.v4504-pay-option>small,
.v4504-pay-option[data-v4507-card="1"] small{
  font-size:9px!important;
  line-height:1.2!important
}
.v4504-pay-option[data-v4507-card="1"]{
  border-style:solid!important;
  background:#fff!important;
  cursor:pointer!important
}
.v4504-pay-option[data-v4507-card="1"].selected{
  border-color:#6d9fd0!important;
  background:#eef6ff!important;
  color:#255b8d!important;
  box-shadow:0 0 0 2px rgba(68,123,177,.09)!important
}
.v4505-dataphone-note{
  display:none!important
}
#v4504Card{
  display:none!important
}

/* Flujo manual Bendo. */
.v4507-bendo-flow{
  margin-top:10px;
  border:1px solid #cbdceb;
  border-radius:14px;
  background:linear-gradient(180deg,#f8fbff 0%,#ffffff 100%);
  overflow:hidden
}
.v4507-bendo-top{
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:center;
  gap:14px;
  padding:13px 14px;
  background:#eef6ff;
  border-bottom:1px solid #dce8f2
}
.v4507-bendo-top small{
  display:block;
  color:#6e8297;
  font-size:8.5px;
  font-weight:800;
  text-transform:uppercase;
  letter-spacing:.05em
}
.v4507-bendo-top strong{
  display:block;
  margin-top:2px;
  color:#234d73;
  font-size:14px
}
.v4507-bendo-amount{
  min-width:126px;
  text-align:center;
  padding:7px 12px;
  border-radius:11px;
  background:#173f65;
  color:#fff
}
.v4507-bendo-amount span{
  display:block;
  font-size:7.5px;
  font-weight:800;
  opacity:.76;
  letter-spacing:.08em
}
.v4507-bendo-amount b{
  display:block;
  margin-top:1px;
  font-size:24px;
  line-height:1.05
}
.v4507-bendo-body{
  padding:12px 14px
}
.v4507-bendo-steps{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:7px;
  margin-bottom:10px
}
.v4507-bendo-step{
  min-height:56px;
  padding:8px 9px;
  border:1px solid #e0e7ef;
  border-radius:10px;
  background:#fbfcfe
}
.v4507-bendo-step span{
  display:block;
  color:#315d84;
  font-size:8px;
  font-weight:950
}
.v4507-bendo-step b{
  display:block;
  margin-top:3px;
  color:#536b82;
  font-size:9px;
  line-height:1.25
}
.v4507-bendo-options{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px
}
.v4507-bendo-options button,
.v4507-bendo-plan button{
  min-height:34px!important;
  border:1px solid #d1dde8!important;
  border-radius:9px!important;
  background:#fff!important;
  color:#4b647c!important;
  font-size:9px!important;
  font-weight:900!important;
  box-shadow:none!important
}
.v4507-bendo-options button.selected,
.v4507-bendo-plan button.selected{
  border-color:#7aa7cf!important;
  background:#eaf4ff!important;
  color:#235c8e!important
}
.v4507-bendo-plan{
  display:flex;
  gap:6px;
  margin-top:8px
}
.v4507-bendo-fields{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
  margin-top:9px
}
.v4507-bendo-field label{
  display:block;
  margin-bottom:4px;
  color:#73869a;
  font-size:7.5px;
  font-weight:900;
  text-transform:uppercase
}
.v4507-bendo-field input{
  width:100%;
  height:34px!important;
  border-radius:8px!important;
  font-size:9px!important
}
.v4507-bendo-actions{
  display:flex;
  gap:7px;
  margin-top:10px;
  align-items:center;
  flex-wrap:wrap
}
.v4507-bendo-actions button{
  min-height:36px!important;
  border-radius:9px!important;
  font-size:9px!important;
  font-weight:900!important
}
.v4507-bendo-actions .approve{
  background:#2f7a51!important;
  border-color:#2f7a51!important;
  color:#fff!important
}
.v4507-bendo-actions .approve.done{
  background:#e7f7ed!important;
  border-color:#a9d8b9!important;
  color:#246440!important
}
.v4507-bendo-result{
  flex:1;
  min-width:190px;
  text-align:right;
  color:#718397;
  font-size:8.5px
}
.v4507-bendo-result.ok{
  color:#276a46;
  font-weight:850
}
.v4507-bendo-warning{
  margin-top:9px;
  padding:7px 9px;
  border-radius:9px;
  background:#fff8e9;
  color:#82621e;
  font-size:8px;
  line-height:1.35
}

/* Configuración: modo real Bendo. */
.v4507-config{
  max-width:980px!important
}
.v4507-config-hero{
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  gap:16px;
  align-items:center;
  padding:17px;
  border:1px solid #d9e4ef;
  border-radius:15px;
  background:linear-gradient(135deg,#f6fbff 0%,#eef6ff 100%);
  margin-bottom:12px
}
.v4507-config-hero h3{
  margin:0 0 4px;
  color:#203d59;
  font-size:18px
}
.v4507-config-hero p{
  margin:0;
  color:#657b91;
  font-size:10px;
  line-height:1.45
}
.v4507-status-pill{
  padding:6px 10px;
  border-radius:999px;
  border:1px solid #ead5a5;
  background:#fff5df;
  color:#855f19;
  font-size:9px;
  font-weight:950;
  white-space:nowrap
}
.v4507-config-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:10px
}
.v4507-config-card{
  padding:14px;
  border:1px solid #dfe7ef;
  border-radius:13px;
  background:#fff
}
.v4507-config-card.full{
  grid-column:1/-1
}
.v4507-config-card h4{
  margin:0 0 4px;
  color:#304d68;
  font-size:13px
}
.v4507-config-card p{
  margin:0;
  color:#72859a;
  font-size:9px;
  line-height:1.45
}
.v4507-flow{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:7px;
  margin-top:11px
}
.v4507-flow>div{
  position:relative;
  padding:10px;
  border:1px solid #e1e7ee;
  border-radius:10px;
  background:#fafcfe
}
.v4507-flow span{
  display:block;
  color:#2f628f;
  font-size:8px;
  font-weight:950
}
.v4507-flow b{
  display:block;
  margin-top:3px;
  color:#536a81;
  font-size:9px;
  line-height:1.3
}
.v4507-config-list{
  display:grid;
  gap:7px;
  margin-top:9px
}
.v4507-config-row{
  display:flex;
  justify-content:space-between;
  gap:12px;
  align-items:center;
  padding:8px 9px;
  border:1px solid #e2e8ef;
  border-radius:9px;
  background:#fbfcfe
}
.v4507-config-row span{
  color:#62778d;
  font-size:9px
}
.v4507-config-row b{
  color:#324f6a;
  font-size:9px;
  text-align:right
}
.v4507-future{
  margin-top:10px;
  padding:9px 10px;
  border:1px dashed #cdd9e5;
  border-radius:10px;
  background:#f8fafc;
  color:#64798f;
  font-size:8.5px;
  line-height:1.4
}
@media(max-width:780px){
  .v4507-bendo-top,.v4507-config-hero{grid-template-columns:1fr}
  .v4507-bendo-steps{grid-template-columns:1fr}
  .v4507-config-grid,.v4507-flow{grid-template-columns:1fr}
  .v4507-bendo-fields{grid-template-columns:1fr}
}
"""

    V4507_JS = r"""
;(()=>{
  if(window.__v4507BendoManual)return;
  window.__v4507BendoManual=true;
  const VERSION='4.5.7';
  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const money=n=>'$'+Number(n||0).toFixed(2);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));

  let internalBaseClick=false;
  let state={
    active:false,
    cardType:'',
    creditPlan:'CORRIENTE',
    installments:3,
    voucher:'',
    approved:false,
    approvedAmount:null
  };

  function amount(){
    try{
      const value=window.__v4504PaymentTest?.total?.();
      return Math.round(Number(value||0)*100)/100;
    }catch(_e){
      return 0;
    }
  }

  function resetBendo(){
    state={
      active:false,
      cardType:'',
      creditPlan:'CORRIENTE',
      installments:3,
      voucher:'',
      approved:false,
      approvedAmount:null
    };
  }

  function invalidateIfAmountChanged(){
    const current=amount();
    if(
      state.approved
      &&Math.abs(Number(state.approvedAmount||0)-current)>0.009
    ){
      state.approved=false;
      state.approvedAmount=null;
    }
  }

  function actualPayload(){
    const total=amount();
    if(!state.active)return null;
    if(total<=0)throw Error('Selecciona primero la consulta o procedimiento.');
    if(!state.cardType)throw Error('Selecciona si el pago fue con tarjeta Débito o Crédito.');
    if(!state.approved)throw Error('Confirma que el pago fue APROBADO en el Bendo Smart.');
    if(Math.abs(Number(state.approvedAmount||0)-total)>0.009){
      state.approved=false;
      state.approvedAmount=null;
      throw Error('El valor cambió después de aprobar el cobro. Vuelve a confirmar el pago en Bendo.');
    }

    const method=state.cardType==='CREDITO'
      ?'TARJETA_CREDITO'
      :'TARJETA_DEBITO';

    const payload={
      payment_method:method,
      voucher:String(state.voucher||'').trim()
    };

    if(method==='TARJETA_CREDITO'){
      payload.card_plan=state.creditPlan;
      payload.installments=(
        state.creditPlan==='DIFERIDO'
          ?Number(state.installments||0)
          :1
      );
      if(
        state.creditPlan==='DIFERIDO'
        &&(
          !Number.isInteger(payload.installments)
          ||payload.installments<2
          ||payload.installments>99
        )
      ){
        throw Error('Ingresa una cantidad válida de cuotas para el crédito diferido.');
      }
    }
    return payload;
  }

  function chooseBaseCash(){
    const host=q('.attention-form-modal #v4504Payment');
    const cash=q('[data-mode="EFECTIVO"]',host);
    if(!cash)return false;
    internalBaseClick=true;
    try{
      cash.click();
      return true;
    }finally{
      internalBaseClick=false;
    }
  }

  function selectBendo(){
    state.active=true;
    state.approved=false;
    state.approvedAmount=null;
    patchPayment();
  }

  function cardButton(){
    const host=q('.attention-form-modal #v4504Payment');
    if(!host)return null;

    let current=q('[data-v4507-card="1"]',host);
    if(current)return current;

    const legacy=q('[data-mode="TARJETA"]',host);
    if(!legacy)return null;

    const clone=legacy.cloneNode(true);
    clone.removeAttribute('data-mode');
    clone.removeAttribute('aria-disabled');
    clone.dataset.v4507Card='1';
    clone.classList.remove('selected');
    clone.setAttribute(
      'title',
      'Cobro manual en Bendo Smart'
    );
    const title=q('b',clone);
    const small=q('small',clone);
    if(title)title.textContent='Tarjeta';
    if(small)small.textContent='Bendo Smart · manual';
    clone.addEventListener('click',event=>{
      event.preventDefault();
      event.stopPropagation();
      selectBendo();
    });
    legacy.replaceWith(clone);
    return clone;
  }

  function renderFlow(){
    const host=q('.attention-form-modal #v4504Payment');
    if(!host)return;

    let flow=q('#v4507BendoFlow',host);
    if(!state.active){
      flow?.remove();
      return;
    }

    invalidateIfAmountChanged();
    const total=amount();

    if(!flow){
      flow=document.createElement('div');
      flow.id='v4507BendoFlow';
      flow.className='v4507-bendo-flow';
      const options=q('.v4504-pay-options',host);
      options?.insertAdjacentElement('afterend',flow);
    }

    flow.innerHTML=
      '<div class="v4507-bendo-top">'
      +'<div><small>COBRO CON TARJETA</small>'
      +'<strong>Bendo Smart · operación manual</strong></div>'
      +'<div class="v4507-bendo-amount"><span>DIGITAR EN BENDO</span>'
      +'<b>'+money(total)+'</b></div></div>'

      +'<div class="v4507-bendo-body">'
      +'<div class="v4507-bendo-steps">'
      +'<div class="v4507-bendo-step"><span>1 · MONTO</span><b>Digita '+money(total)+' en el Bendo Smart.</b></div>'
      +'<div class="v4507-bendo-step"><span>2 · COBRAR</span><b>El paciente paga directamente en el equipo.</b></div>'
      +'<div class="v4507-bendo-step"><span>3 · CONFIRMAR</span><b>Solo guarda si Bendo muestra pago aprobado.</b></div>'
      +'</div>'

      +'<div class="v4507-bendo-options">'
      +'<button type="button" data-v4507-cardtype="DEBITO" class="'
      +(state.cardType==='DEBITO'?'selected':'')
      +'">Tarjeta de débito · SRI 16</button>'
      +'<button type="button" data-v4507-cardtype="CREDITO" class="'
      +(state.cardType==='CREDITO'?'selected':'')
      +'">Tarjeta de crédito · SRI 19</button>'
      +'</div>'

      +(state.cardType==='CREDITO'
        ?'<div class="v4507-bendo-plan">'
         +'<button type="button" data-v4507-plan="CORRIENTE" class="'
         +(state.creditPlan==='CORRIENTE'?'selected':'')
         +'">Corriente</button>'
         +'<button type="button" data-v4507-plan="DIFERIDO" class="'
         +(state.creditPlan==='DIFERIDO'?'selected':'')
         +'">Diferido</button></div>'
        :'')

      +'<div class="v4507-bendo-fields">'
      +(state.cardType==='CREDITO'&&state.creditPlan==='DIFERIDO'
        ?'<div class="v4507-bendo-field"><label>Cuotas</label>'
         +'<input id="v4507Installments" type="number" min="2" max="99" value="'
         +Number(state.installments||3)+'"></div>'
        :'')
      +'<div class="v4507-bendo-field"><label>Voucher / autorización</label>'
      +'<input id="v4507Voucher" maxlength="40" placeholder="Opcional" value="'
      +esc(state.voucher)+'"></div>'
      +'</div>'

      +'<div class="v4507-bendo-actions">'
      +'<button type="button" id="v4507Approve" class="approve '
      +(state.approved?'done':'')+'">'
      +(state.approved?'✓ Pago aprobado confirmado':'✓ Confirmar PAGO APROBADO')
      +'</button>'
      +'<button type="button" id="v4507CancelCard">Cambiar forma de pago</button>'
      +'<span class="v4507-bendo-result '+(state.approved?'ok':'')+'">'
      +(state.approved
        ?'✓ Listo para guardar la atención'
        :'Esperando confirmación del Bendo Smart')
      +'</span></div>'

      +'<div class="v4507-bendo-warning">'
      +'Recepción no controla el terminal ni guarda número de tarjeta/CVV. '
      +'La confirmación indica que verificaste visualmente el resultado en Bendo.'
      +'</div></div>';

    qa('[data-v4507-cardtype]',flow).forEach(button=>{
      button.addEventListener('click',()=>{
        state.cardType=button.dataset.v4507Cardtype||'';
        state.approved=false;
        state.approvedAmount=null;
        renderFlow();
      });
    });

    qa('[data-v4507-plan]',flow).forEach(button=>{
      button.addEventListener('click',()=>{
        state.creditPlan=button.dataset.v4507Plan||'CORRIENTE';
        state.approved=false;
        state.approvedAmount=null;
        renderFlow();
      });
    });

    q('#v4507Installments',flow)?.addEventListener('input',event=>{
      state.installments=Number(event.target.value||0);
      state.approved=false;
      state.approvedAmount=null;
    });

    q('#v4507Voucher',flow)?.addEventListener('input',event=>{
      state.voucher=event.target.value;
    });

    q('#v4507Approve',flow)?.addEventListener('click',()=>{
      if(!state.cardType){
        alert('Selecciona primero Débito o Crédito.');
        return;
      }
      if(
        state.cardType==='CREDITO'
        &&state.creditPlan==='DIFERIDO'
        &&(
          !Number.isInteger(Number(state.installments))
          ||Number(state.installments)<2
        )
      ){
        alert('Ingresa la cantidad de cuotas.');
        return;
      }
      if(total<=0){
        alert('Selecciona primero la consulta o procedimiento.');
        return;
      }
      state.approved=true;
      state.approvedAmount=total;
      renderFlow();
    });

    q('#v4507CancelCard',flow)?.addEventListener('click',()=>{
      resetBendo();
      patchPayment();
    });
  }

  function patchPayment(){
    const host=q('.attention-form-modal #v4504Payment');
    if(!host)return;

    const card=cardButton();
    if(!card)return;

    qa('.v4504-pay-option',host).forEach(button=>{
      if(state.active){
        button.classList.toggle(
          'selected',
          button.dataset.v4507Card==='1'
        );
      }
    });

    const status=q('.v4504-pay-state',host);
    if(status&&state.active){
      status.classList.add('ready');
      status.textContent=state.approved
        ?'✓ Tarjeta · Bendo aprobado'
        :'Tarjeta · pendiente de cobro';
    }

    renderFlow();
  }

  // Si el usuario selecciona otra forma, se abandona el flujo Bendo.
  document.addEventListener('click',event=>{
    if(internalBaseClick)return;
    const other=event.target?.closest?.(
      '.attention-form-modal [data-mode="EFECTIVO"],'
      +'.attention-form-modal [data-mode="TRANSFERENCIA"],'
      +'.attention-form-modal [data-mode="MIXTO"]'
    );
    if(!other)return;
    resetBendo();
    setTimeout(patchPayment,60);
  },false);

  // Al cambiar servicios o descuento, el total puede variar y una aprobación
  // anterior deja de ser válida.
  document.addEventListener('click',event=>{
    if(
      event.target?.closest?.(
        '.attention-form-modal .service-card,'
        +'.attention-form-modal [data-v4502-couple-discount],'
        +'.attention-form-modal input[type="checkbox"]'
      )
    ){
      const old=amount();
      setTimeout(()=>{
        const now=amount();
        if(
          state.approved
          &&Math.abs(now-Number(state.approvedAmount||0))>0.009
        ){
          state.approved=false;
          state.approvedAmount=null;
        }
        patchPayment();
      },70);
    }
  },true);

  const stableAttentionFor=window.attentionFor;
  if(typeof stableAttentionFor==='function'){
    window.attentionFor=async function(){
      resetBendo();
      const result=await stableAttentionFor.apply(this,arguments);
      setTimeout(patchPayment,90);
      setTimeout(patchPayment,260);
      return result;
    };
  }

  // Envoltura final del guardado: el v4.5.4 conserva compatibilidad interna con
  // el guardado estable. Aquí reemplazamos únicamente el payload del pago cuando
  // el usuario confirmó una tarjeta real en Bendo.
  const stableSave=window.saveAttention;
  if(typeof stableSave==='function'){
    window.saveAttention=async function(){
      if(!state.active){
        return await stableSave.apply(this,arguments);
      }

      let cardPayload;
      try{
        cardPayload=actualPayload();
      }catch(error){
        alert(error?.message||String(error));
        patchPayment();
        return;
      }

      if(!chooseBaseCash()){
        alert('No se pudo preparar el guardado de la forma de pago. Cierra y vuelve a abrir Nueva atención.');
        return;
      }

      const previousWindowApi=window.api;
      const previousApi=api;
      const downstream=previousWindowApi||previousApi;

      const intercept=async function(url,opt={}){
        if(String(url)==='/api/visits/batch-payment'){
          let body={};
          try{
            body=JSON.parse(opt?.body||'{}');
          }catch(_e){
            body={};
          }
          Object.assign(body,cardPayload);
          return downstream(
            url,
            {
              ...opt,
              body:JSON.stringify(body)
            }
          );
        }
        return downstream(url,opt);
      };

      try{
        window.api=intercept;
        api=intercept;
        return await stableSave.apply(this,arguments);
      }finally{
        window.api=previousWindowApi;
        api=previousApi;
      }
    };
  }

  // ---------- Corrección de forma de pago desde Facturación ----------
  function billingIdentity(card){
    try{
      const cards=qa('#billingList .billing-card');
      const index=cards.indexOf(card);
      const groups=Array.isArray(window.billingGroupsCache)
        ?window.billingGroupsCache
        :(typeof billingGroupsCache!=='undefined'&&Array.isArray(billingGroupsCache)
          ?billingGroupsCache
          :[]);
      const group=index>=0?groups[index]:null;
      const patientId=Number(
        card?.dataset?.patientId
        ||group?.patient?.id
        ||0
      );
      const fecha=String(
        card?.dataset?.fecha
        ||group?.fecha
        ||''
      ).slice(0,10);
      if(!patientId||!fecha)return null;
      return {patientId,fecha};
    }catch(_e){
      return null;
    }
  }

  async function saveBillingCard(card,method){
    const id=billingIdentity(card);
    if(!id){
      alert('No se pudo identificar esta ficha de facturación.');
      return;
    }

    const approved=confirm(
      'Usa esta opción únicamente si el cobro YA fue aprobado en el Bendo Smart.\n\n¿Confirmar pago con tarjeta?'
    );
    if(!approved)return;

    let extra={};
    if(method==='TARJETA_CREDITO'){
      const mode=String(
        prompt(
          'Crédito: escribe C para CORRIENTE o D para DIFERIDO.',
          'C'
        )||''
      ).trim().toUpperCase();
      if(!mode)return;
      if(mode==='D'){
        const qty=Number(prompt('Número de cuotas:','3')||0);
        if(!Number.isInteger(qty)||qty<2){
          alert('Cantidad de cuotas inválida.');
          return;
        }
        extra={card_plan:'DIFERIDO',installments:qty};
      }else{
        extra={card_plan:'CORRIENTE',installments:1};
      }
    }

    try{
      await (window.api||api)(
        '/api/billing/payment-method',
        {
          method:'POST',
          body:JSON.stringify({
            patient_id:id.patientId,
            fecha:id.fecha,
            payment_method:method,
            ...extra
          })
        }
      );
      await window.loadBilling?.();
      setTimeout(patchBilling,80);
      setTimeout(patchBilling,260);
    }catch(error){
      alert(error?.message||String(error));
    }
  }

  function patchBilling(){
    qa('#billingList .billing-card').forEach(card=>{
      qa(
        '.v4504-billchoices [data-bm="TARJETA_DEBITO"],'
        +'.v4504-billchoices [data-bm="TARJETA_CREDITO"]',
        card
      ).forEach(button=>{
        const method=button.dataset.bm;
        const clone=button.cloneNode(true);
        clone.removeAttribute('data-bm');
        clone.dataset.v4507Bm=method;
        clone.setAttribute(
          'title',
          'Registrar tarjeta solo después de verificar pago aprobado en Bendo'
        );
        clone.addEventListener('click',event=>{
          event.preventDefault();
          event.stopPropagation();
          saveBillingCard(card,method);
        });
        button.replaceWith(clone);
      });
    });
  }

  const stableLoadBilling=window.loadBilling;
  if(typeof stableLoadBilling==='function'){
    window.loadBilling=async function(){
      const result=await stableLoadBilling.apply(this,arguments);
      setTimeout(patchBilling,60);
      setTimeout(patchBilling,220);
      return result;
    };
  }

  // ---------- Configuración > Datáfono ----------
  function renderManualConfig(){
    const section=q('[data-config-section="dataphone"]');
    if(!section)return;

    section.className='config-section v4507-config';
    section.innerHTML=
      '<div class="v4507-config-hero">'
      +'<div><h3>💳 Bendo Smart</h3>'
      +'<p>Flujo configurado según la operación actualmente soportada por Bendo. '
      +'El cobro se inicia manualmente en el terminal; Recepción controla el monto, '
      +'la validación del resultado y el registro administrativo.</p></div>'
      +'<span class="v4507-status-pill">MODO MANUAL CONFIRMADO</span>'
      +'</div>'

      +'<div class="v4507-config-grid">'
      +'<section class="v4507-config-card full"><h4>Cómo se cobrará</h4>'
      +'<p>El programa reduce al mínimo el trabajo manual sin inventar una API que Bendo no ofrece actualmente.</p>'
      +'<div class="v4507-flow">'
      +'<div><span>1 · RECEPCIÓN</span><b>Calcula el total exacto de la atención.</b></div>'
      +'<div><span>2 · BENDO SMART</span><b>Recepción muestra en grande el valor que debes digitar.</b></div>'
      +'<div><span>3 · PACIENTE</span><b>El paciente paga directamente en el terminal.</b></div>'
      +'<div><span>4 · CONFIRMACIÓN</span><b>Solo se guarda Tarjeta después de confirmar “Aprobado”.</b></div>'
      +'</div></section>'

      +'<section class="v4507-config-card"><h4>Estado actual</h4>'
      +'<div class="v4507-config-list">'
      +'<div class="v4507-config-row"><span>Proveedor</span><b>Bendo</b></div>'
      +'<div class="v4507-config-row"><span>Equipo</span><b>Bendo Smart</b></div>'
      +'<div class="v4507-config-row"><span>Integración API/ECR</span><b>No disponible actualmente</b></div>'
      +'<div class="v4507-config-row"><span>Inicio del cobro</span><b>Manual en el terminal</b></div>'
      +'<div class="v4507-config-row"><span>Confirmación en Recepción</span><b>Obligatoria</b></div>'
      +'</div></section>'

      +'<section class="v4507-config-card"><h4>Qué registra Recepción</h4>'
      +'<div class="v4507-config-list">'
      +'<div class="v4507-config-row"><span>Débito / Crédito</span><b>Sí</b></div>'
      +'<div class="v4507-config-row"><span>Corriente / Diferido</span><b>Sí</b></div>'
      +'<div class="v4507-config-row"><span>Cuotas</span><b>Si aplica</b></div>'
      +'<div class="v4507-config-row"><span>Voucher / autorización</span><b>Opcional</b></div>'
      +'<div class="v4507-config-row"><span>Número de tarjeta / CVV</span><b>Nunca</b></div>'
      +'</div></section>'

      +'<section class="v4507-config-card full"><h4>Integración futura</h4>'
      +'<p>La arquitectura técnica que preparamos se conserva internamente, pero no se muestra como si estuviera disponible. '
      +'Si PUBLIPROMUEVE confirma ECR, SDK, Intent, API privada o programa de partners, podremos sustituir únicamente este paso manual.</p>'
      +'<div class="v4507-future">'
      +'<b>Consulta técnica en curso:</b> se solicitó confirmación directa a PUBLIPROMUEVE/Desarrollo. '
      +'Hasta recibir documentación oficial, Recepción no intentará enviar órdenes de cobro al dispositivo.'
      +'</div></section>'
      +'</div>';
  }

  function patchConfigTab(){
    const tabs=q('#config .config-tabs');
    if(!tabs)return;

    let button=q('[data-config-tab="dataphone"]',tabs);
    if(!button)return;

    if(button.dataset.v4507Manual==='1')return;

    const clone=button.cloneNode(true);
    clone.dataset.v4507Manual='1';
    clone.textContent='Datáfono';
    clone.onclick=()=>{
      window.showConfigTab?.('dataphone',clone);
      renderManualConfig();
    };
    button.replaceWith(clone);
  }

  function boot(){
    qa('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
    patchConfigTab();
    patchPayment();
    patchBilling();
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

  setTimeout(boot,220);

  window.__v4507BendoState={
    mode:'MANUAL_CONFIRMED',
    provider:'Bendo',
    model:'Bendo Smart',
    apiAvailable:false,
    requiresApprovedConfirmation:true,
    cardSensitiveDataStored:false
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
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "provider": "Bendo",
        "model": "Bendo Smart",
        "operating_mode": "MANUAL_CONFIRMED",
        "external_api_available": False,
        "external_ecr_available": False,
        "manual_amount_entry": True,
        "approval_confirmation_required": True,
        "debit_credit_recording": True,
        "credit_plan_recording": True,
        "voucher_optional": True,
        "stores_pan": False,
        "stores_cvv": False,
        "technical_escalation_pending": True,
        "confirmed_by_vendor_date": "2026-09-18",
    }


@app.get("/api/v4507/health")
def v4507_health(
    user=core.Depends(core.current_user),
):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "bendo_manual_flow": True,
        "card_payment_enabled": True,
        "card_requires_manual_approval_confirmation": True,
        "automatic_terminal_control": False,
        "consultation_card_restored": True,
        "procedures_compact": True,
        "payment_typography_enlarged": True,
        "config_reflects_vendor_confirmation": True,
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
