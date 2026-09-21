from __future__ import annotations

# v4.5.25 — hotfix Tarjeta/Bendo.
# El panel se monta directamente al hacer clic en Tarjeta, sin MutationObserver
# ni temporizadores de búsqueda del DOM. Conserva el guardado Bendo manual.
# No modifica base de datos, Neon, Historia ni facturación.

import app_patch_4524 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.25"

_mod = previous
_seen = set()
for _ in range(720):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

V4525_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.5.25"!important;
  font-size:9px!important;
  font-weight:850!important
}
.attention-form-modal [data-mode="TARJETA"],
.attention-form-modal [data-v4507-card="1"]{
  border-style:solid!important;
  cursor:pointer!important
}
.v4525-bendo{
  margin-top:10px;
  border:1px solid #cadbea;
  border-radius:14px;
  background:#fff;
  overflow:hidden
}
.v4525-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:12px 14px;
  background:#eef6ff;
  border-bottom:1px solid #dce8f2
}
.v4525-head small{
  display:block;
  color:#6d8297;
  font-size:8px;
  font-weight:900
}
.v4525-head strong{
  display:block;
  margin-top:2px;
  color:#244e74;
  font-size:13px
}
.v4525-amount{
  min-width:120px;
  padding:7px 11px;
  border-radius:10px;
  background:#173f65;
  color:#fff;
  text-align:center
}
.v4525-amount span{
  display:block;
  font-size:7px;
  font-weight:850
}
.v4525-amount b{
  display:block;
  font-size:22px;
  line-height:1.05
}
.v4525-body{padding:12px 14px}
.v4525-types{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px
}
.v4525-types button{
  min-height:36px!important;
  border:1px solid #d3dee8!important;
  border-radius:9px!important;
  background:#fff!important;
  color:#50677e!important;
  font-size:9px!important;
  font-weight:900!important
}
.v4525-types button.selected{
  border-color:#7aa7cf!important;
  background:#eaf4ff!important;
  color:#235c8e!important
}
.v4525-meta{
  display:grid;
  grid-template-columns:minmax(0,1fr) 150px 110px;
  gap:8px;
  margin-top:9px
}
.v4525-meta label{
  display:block;
  margin-bottom:4px;
  color:#71859a;
  font-size:7.5px;
  font-weight:900;
  text-transform:uppercase
}
.v4525-meta input,.v4525-meta select{
  width:100%;
  height:34px!important;
  border-radius:8px!important;
  font-size:9px!important
}
.v4525-noop{
  display:flex;
  align-items:center;
  gap:6px;
  margin-top:8px;
  color:#647b90;
  font-size:8.5px
}
.v4525-noop input{width:auto!important}
.v4525-actions{
  display:flex;
  gap:8px;
  align-items:center;
  flex-wrap:wrap;
  margin-top:10px
}
.v4525-actions button{
  min-height:36px!important;
  border-radius:9px!important;
  font-size:9px!important;
  font-weight:900!important
}
#v4525Approve{
  background:#2f7a51!important;
  border-color:#2f7a51!important;
  color:#fff!important
}
#v4525Approve.done{
  background:#e7f7ed!important;
  border-color:#a9d8b9!important;
  color:#246440!important
}
.v4525-status{
  flex:1;
  min-width:180px;
  color:#708399;
  font-size:8.5px
}
.v4525-status.ok{color:#276a46;font-weight:900}
.v4525-warning{
  margin-top:9px;
  padding:8px 10px;
  border-radius:9px;
  background:#fff8e9;
  color:#80611f;
  font-size:8px;
  line-height:1.35
}
@media(max-width:780px){
  .v4525-meta{grid-template-columns:1fr}
  .v4525-types{grid-template-columns:1fr}
}
"""

V4525_JS = r"""
;(()=>{
  if(window.__v4525BendoHotfix)return;
  window.__v4525BendoHotfix=true;

  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const money=n=>'$'+Number(n||0).toFixed(2);

  const state={
    active:false,
    type:'',
    operation:'',
    noOperation:false,
    brand:'',
    last4:'',
    approvedKey:''
  };

  function total(){
    try{
      return Math.round(Number(window.__v4504PaymentTest?.total?.()||0)*100)/100;
    }catch(_e){return 0}
  }
  function cleanOp(v){
    return String(v||'').toUpperCase().replace(/[^A-Z0-9._-]/g,'').slice(0,18)
  }
  function cleanLast4(v){
    return String(v||'').replace(/\D/g,'').slice(0,4)
  }
  function key(){
    return [
      total().toFixed(2),
      state.type,
      state.noOperation?'SIN-OPERACION':cleanOp(state.operation),
      String(state.brand||'').toUpperCase(),
      cleanLast4(state.last4)
    ].join('|')
  }
  function reference(){
    const bits=[];
    bits.push(state.noOperation?'SIN-OPERACION':cleanOp(state.operation));
    if(state.brand)bits.push(String(state.brand).toUpperCase().slice(0,10));
    if(state.last4)bits.push(cleanLast4(state.last4));
    return bits.filter(Boolean).join('/').slice(0,32)
  }
  function host(){
    return q('.attention-form-modal #v4504Payment')
  }
  function markCard(){
    const h=host(); if(!h)return;
    const card=q('[data-mode="TARJETA"],[data-v4507-card="1"]',h);
    if(!card)return;
    const title=q('b',card),small=q('small',card);
    if(title)title.textContent='Tarjeta';
    if(small)small.textContent='Bendo Smart · manual';
    card.classList.toggle('selected',state.active);
    qa('.v4504-pay-option',h).forEach(b=>{
      if(state.active && b!==card)b.classList.remove('selected');
    });
    const st=q('.v4504-pay-state',h);
    if(st&&state.active){
      st.textContent=state.approvedKey===key()
        ?'✓ Tarjeta · Bendo aprobado'
        :'Tarjeta · pendiente de cobro';
    }
  }
  function invalidate(){
    state.approvedKey='';
  }
  function render(){
    const h=host(); if(!h)return;
    markCard();
    let panel=q('#v4525Bendo',h);
    if(!state.active){panel?.remove();return}
    if(!panel){
      panel=document.createElement('div');
      panel.id='v4525Bendo';
      panel.className='v4525-bendo';
      const opts=q('.v4504-pay-options',h);
      if(opts)opts.insertAdjacentElement('afterend',panel);
      else h.appendChild(panel);
    }
    const amt=total();
    const approved=state.approvedKey && state.approvedKey===key();
    panel.innerHTML=
      '<div class="v4525-head">'
      +'<div><small>COBRO CON TARJETA</small><strong>Bendo Smart · operación manual</strong></div>'
      +'<div class="v4525-amount"><span>DIGITAR EN BENDO</span><b>'+money(amt)+'</b></div>'
      +'</div><div class="v4525-body">'
      +'<div class="v4525-types">'
      +'<button type="button" data-v4525-type="DEBITO" class="'+(state.type==='DEBITO'?'selected':'')+'">Débito · SRI 16</button>'
      +'<button type="button" data-v4525-type="CREDITO" class="'+(state.type==='CREDITO'?'selected':'')+'">Crédito · SRI 19</button>'
      +'</div>'
      +'<div class="v4525-meta">'
      +'<div><label>N.º de operación Bendo</label><input id="v4525Operation" maxlength="18" value="'+String(state.operation||'')+'" '+(state.noOperation?'disabled':'')+' placeholder="Ej. 123456"></div>'
      +'<div><label>Marca</label><select id="v4525Brand"><option value="">Opcional</option><option>VISA</option><option>MASTERCARD</option><option>DINERS</option><option>AMEX</option><option>OTRA</option></select></div>'
      +'<div><label>Últimos 4</label><input id="v4525Last4" maxlength="4" inputmode="numeric" value="'+String(state.last4||'')+'" placeholder="1234"></div>'
      +'</div>'
      +'<label class="v4525-noop"><input id="v4525NoOperation" type="checkbox" '+(state.noOperation?'checked':'')+'> N.º de operación no disponible</label>'
      +'<div class="v4525-actions">'
      +'<button type="button" id="v4525Approve" class="'+(approved?'done':'')+'">'+(approved?'✓ PAGO EXITOSO confirmado':'Confirmar PAGO EXITOSO')+'</button>'
      +'<button type="button" id="v4525Cancel">Cambiar forma de pago</button>'
      +'<span class="v4525-status '+(approved?'ok':'')+'">'+(approved?'✓ Listo para guardar':'Esperando confirmación del Bendo Smart')+'</span>'
      +'</div>'
      +'<div class="v4525-warning">Confirma únicamente después de ver <b>PAGO EXITOSO</b> en el Bendo. Recepción no controla el terminal y no guarda PAN ni CVV.</div>'
      +'</div>';

    const brand=q('#v4525Brand',panel);
    if(brand)brand.value=state.brand||'';

    qa('[data-v4525-type]',panel).forEach(b=>b.addEventListener('click',()=>{
      state.type=b.dataset.v4525Type||'';
      invalidate();render();
    }));
    q('#v4525Operation',panel)?.addEventListener('input',e=>{
      state.operation=cleanOp(e.target.value);invalidate();
    });
    brand?.addEventListener('change',e=>{
      state.brand=e.target.value||'';invalidate();
    });
    q('#v4525Last4',panel)?.addEventListener('input',e=>{
      state.last4=cleanLast4(e.target.value);invalidate();
    });
    q('#v4525NoOperation',panel)?.addEventListener('change',e=>{
      state.noOperation=!!e.target.checked;
      if(state.noOperation)state.operation='';
      invalidate();render();
    });
    q('#v4525Approve',panel)?.addEventListener('click',()=>{
      if(amt<=0){alert('Selecciona primero una consulta o procedimiento.');return}
      if(!state.type){alert('Selecciona Débito o Crédito.');return}
      if(!state.noOperation&&!cleanOp(state.operation)){
        alert('Ingresa el N.º de operación Bendo o marca “N.º de operación no disponible”.');
        return
      }
      if(state.last4&&cleanLast4(state.last4).length!==4){
        alert('Los últimos 4 dígitos deben tener 4 números o quedar vacíos.');
        return
      }
      if(!confirm(
        'CONFIRMAR COBRO BENDO\\n\\nMonto: '+money(amt)
        +'\\nTipo: '+(state.type==='CREDITO'?'Crédito':'Débito')
        +'\\n'+(state.noOperation?'N.º operación: no disponible':'N.º operación: '+cleanOp(state.operation))
        +'\\n\\nConfirma únicamente si Bendo muestra PAGO EXITOSO.'
      ))return;
      state.approvedKey=key();render();
    });
    q('#v4525Cancel',panel)?.addEventListener('click',()=>{
      state.active=false;state.type='';state.approvedKey='';
      render();
    });
  }

  // Enganche principal: funciona aunque el modal se haya creado después.
  document.addEventListener('click',event=>{
    const card=event.target?.closest?.(
      '.attention-form-modal [data-mode="TARJETA"],'
      +'.attention-form-modal [data-v4507-card="1"]'
    );
    if(card){
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      state.active=true;
      invalidate();
      render();
      return;
    }

    const other=event.target?.closest?.(
      '.attention-form-modal [data-mode="EFECTIVO"],'
      +'.attention-form-modal [data-mode="TRANSFERENCIA"],'
      +'.attention-form-modal [data-mode="MIXTO"]'
    );
    if(other&&state.active){
      state.active=false;
      state.approvedKey='';
      q('#v4525Bendo')?.remove();
    }

    if(state.active&&event.target?.closest?.('.attention-form-modal .service-card')){
      invalidate();
      requestAnimationFrame(render);
    }
  },true);

  const stableSave=window.saveAttention;
  if(typeof stableSave==='function'&&!stableSave.__v4525){
    const wrapped=async function(){
      if(!state.active)return await stableSave.apply(this,arguments);

      const amt=total();
      if(amt<=0){alert('Selecciona primero una consulta o procedimiento.');return}
      if(!state.type){alert('Selecciona Débito o Crédito.');return}
      if(!state.noOperation&&!cleanOp(state.operation)){
        alert('Ingresa el N.º de operación Bendo o marca que no está disponible.');return
      }
      if(!state.approvedKey||state.approvedKey!==key()){
        alert('Primero confirma que Bendo mostró PAGO EXITOSO.');return
      }

      const cash=q('.attention-form-modal [data-mode="EFECTIVO"]');
      if(!cash){alert('No se pudo preparar el guardado. Cierra y vuelve a abrir Nueva atención.');return}

      // Selección interna compatible con la capa base, sin abandonar Bendo.
      const wasActive=state.active;
      state.active=false;
      cash.click();
      state.active=wasActive;

      const replacement={
        payment_method:state.type==='CREDITO'?'TARJETA_CREDITO':'TARJETA_DEBITO',
        card_plan:state.type==='CREDITO'?'CORRIENTE':null,
        installments:state.type==='CREDITO'?1:null,
        voucher:reference()
      };

      const previousWindowApi=window.api;
      const previousApi=typeof api!=='undefined'?api:null;
      const downstream=previousWindowApi||previousApi;
      if(typeof downstream!=='function'){
        alert('No se pudo preparar el guardado de tarjeta.');return
      }
      const intercept=async function(url,opt={}){
        if(String(url)==='/api/visits/batch-payment'){
          let body={};
          try{body=JSON.parse(opt?.body||'{}')}catch(_e){}
          Object.assign(body,replacement);
          return downstream(url,{...opt,body:JSON.stringify(body)});
        }
        return downstream(url,opt);
      };
      try{
        window.api=intercept;
        try{api=intercept}catch(_e){}
        return await stableSave.apply(this,arguments);
      }finally{
        window.api=previousWindowApi;
        try{api=previousApi}catch(_e){}
      }
    };
    wrapped.__v4525=true;
    window.saveAttention=wrapped;
  }

  // Corrige el texto viejo si el modal ya estaba abierto al cargar este script.
  function repairVisibleCard(){
    const h=host(); if(!h)return;
    const card=q('[data-mode="TARJETA"],[data-v4507-card="1"]',h);
    if(!card)return;
    const title=q('b',card),small=q('small',card);
    if(title)title.textContent='Tarjeta';
    if(small)small.textContent='Bendo Smart · manual';
  }
  repairVisibleCard();
  window.addEventListener('focus',repairVisibleCard);
})();
"""

core.V460_OVERLAY_CSS=(getattr(core,"V460_OVERLAY_CSS","") or "")+"\n"+V4525_CSS
core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4525_JS

@app.get("/api/v4525/health")
def v4525_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "card_click_direct_mount": True,
        "mutation_observer": False,
        "timing_dependency": False,
        "bendo_manual_assisted": True,
        "operation_reference": True,
        "brand_optional": True,
        "last4_optional": True,
        "approved_confirmation_required": True,
        "database_schema_changes": False,
        "historia_changes": False,
    }

PATCH_BOOT_OK = True
