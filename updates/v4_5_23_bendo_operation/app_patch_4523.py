from __future__ import annotations

import app_patch_4522 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.23"

_mod = previous
_seen = set()
for _ in range(620):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

V4523_CSS = r"""
.v4523-bendo-extra{
  grid-column:1/-1;
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(0,1fr);
  gap:8px
}
.v4523-bendo-extra label{
  display:block;
  margin-bottom:4px;
  color:#73869a;
  font-size:7.5px;
  font-weight:900;
  text-transform:uppercase
}
.v4523-bendo-extra input,
.v4523-bendo-extra select{
  width:100%;
  height:34px!important;
  border:1px solid #d1dde8!important;
  border-radius:8px!important;
  background:#fff!important;
  color:#344d66!important;
  font-size:9px!important;
  box-sizing:border-box!important
}
.v4523-no-operation{
  grid-column:1/-1;
  display:flex;
  align-items:center;
  gap:7px;
  min-height:30px;
  padding:5px 8px;
  border:1px dashed #d6e0e8;
  border-radius:8px;
  background:#fbfcfe;
  color:#61758a;
  font-size:8px;
  font-weight:800
}
.v4523-no-operation input{
  width:14px!important;
  height:14px!important;
  margin:0!important
}
.v4523-bendo-summary{
  margin-top:9px;
  padding:9px 10px;
  border:1px solid #b8dfc6;
  border-radius:10px;
  background:#f1faf4;
  color:#285f40
}
.v4523-bendo-summary strong{
  display:block;
  font-size:9px;
  font-weight:950
}
.v4523-bendo-summary span{
  display:block;
  margin-top:3px;
  font-size:8.5px;
  line-height:1.35
}
.v4507-bendo-actions .approve:disabled{
  opacity:.45!important;
  cursor:not-allowed!important
}
.v4523-reconfirm{
  background:#fff4df!important;
  border-color:#e7c780!important;
  color:#7d5a16!important
}
@media(max-width:780px){
  .v4523-bendo-extra{grid-template-columns:1fr}
}
"""

V4523_JS = r"""
;(()=>{
  if(window.__v4523BendoOperation)return;
  window.__v4523BendoOperation=true;

  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const money=n=>'$'+Number(n||0).toFixed(2);

  const ui=window.__v4523BendoUiState||{
    operation:'',
    noOperation:false,
    brand:'',
    last4:'',
    approvedSnapshot:''
  };
  window.__v4523BendoUiState=ui;

  function total(){
    try{
      return Math.round(Number(window.__v4504PaymentTest?.total?.()||0)*100)/100;
    }catch(_e){return 0}
  }

  function flow(){
    return q('.attention-form-modal #v4507BendoFlow');
  }

  function active(){
    return !!flow();
  }

  function cardType(){
    const selected=q('#v4507BendoFlow [data-v4507-cardtype].selected');
    return String(selected?.dataset?.v4507Cardtype||'').toUpperCase();
  }

  function cardTypeLabel(){
    const type=cardType();
    return type==='CREDITO'?'Crédito':type==='DEBITO'?'Débito':'Tarjeta';
  }

  function cleanOperation(value){
    return String(value||'')
      .toUpperCase()
      .replace(/[^A-Z0-9._-]/g,'')
      .slice(0,18);
  }

  function cleanLast4(value){
    return String(value||'').replace(/\D/g,'').slice(0,4);
  }

  function referenceValue(){
    const parts=[];
    if(ui.noOperation) parts.push('SIN-OPERACION');
    else if(cleanOperation(ui.operation)) parts.push(cleanOperation(ui.operation));
    if(ui.brand) parts.push(String(ui.brand).toUpperCase().slice(0,10));
    if(ui.last4) parts.push(cleanLast4(ui.last4));
    return parts.join('/').slice(0,32);
  }

  function snapshot(){
    return [
      Number(total()).toFixed(2),
      cardType(),
      ui.noOperation?'SIN-OPERACION':cleanOperation(ui.operation),
      String(ui.brand||'').toUpperCase(),
      cleanLast4(ui.last4)
    ].join('|');
  }

  function invalidateApproval(){
    ui.approvedSnapshot='';
    const button=q('#v4507Approve');
    if(button?.classList.contains('done')){
      button.textContent='⚠ Volver a confirmar PAGO EXITOSO';
      button.classList.add('v4523-reconfirm');
    }
    const result=q('#v4507BendoFlow .v4507-bendo-result');
    if(result){
      result.classList.remove('ok');
      result.textContent='Los datos cambiaron. Confirma nuevamente el pago en Bendo.';
    }
    q('#v4523BendoSummary')?.remove();
  }

  function validateMeta(show=true){
    const amount=total();
    if(amount<=0){
      if(show) alert('Selecciona primero la consulta o procedimiento.');
      return false;
    }
    if(!cardType()){
      if(show) alert('Selecciona primero Débito o Crédito.');
      return false;
    }
    if(!ui.noOperation && !cleanOperation(ui.operation)){
      if(show) alert('Ingresa el N.º de operación que muestra Bendo o marca “N.º no disponible”.');
      return false;
    }
    if(ui.last4 && cleanLast4(ui.last4).length!==4){
      if(show) alert('Los últimos 4 dígitos deben tener exactamente 4 números o quedar vacíos.');
      return false;
    }
    return true;
  }

  function summaryText(){
    const bits=[money(total()),cardTypeLabel()];
    bits.push(ui.noOperation?'Op. no disponible':'Op. '+cleanOperation(ui.operation));
    if(ui.brand) bits.push(String(ui.brand).toUpperCase());
    if(ui.last4) bits.push('••••'+cleanLast4(ui.last4));
    return bits.join(' · ');
  }

  function approvalQuestion(){
    return 'CONFIRMAR COBRO BENDO\n\n'
      +'Monto: '+money(total())+'\n'
      +'Tipo: '+cardTypeLabel()+'\n'
      +(ui.noOperation?'N.º operación: no disponible':'N.º operación: '+cleanOperation(ui.operation))+'\n'
      +(ui.brand?'Marca: '+String(ui.brand).toUpperCase()+'\n':'')
      +(ui.last4?'Tarjeta: ••••'+cleanLast4(ui.last4)+'\n':'')
      +'\nConfirma únicamente si el Bendo muestra PAGO EXITOSO.';
  }

  function patchConfig(){
    const section=q('[data-config-section="dataphone"]');
    if(!section)return;

    qa('.v4507-config-row',section).forEach(row=>{
      const left=row.querySelector('span');
      const right=row.querySelector('b');
      const text=String(left?.textContent||'').trim().toLowerCase();
      if(text.includes('voucher')||text.includes('autorización')){
        if(left) left.textContent='N.º de operación Bendo';
        if(right) right.textContent='Sí · preferido';
      }
    });

    const registerCard=qa('.v4507-config-card',section).find(card=>
      String(card.querySelector('h4')?.textContent||'').includes('Qué registra Recepción')
    );
    if(registerCard && !q('[data-v4523-meta-row]',registerCard)){
      const list=q('.v4507-config-list',registerCard);
      if(list){
        const row=document.createElement('div');
        row.className='v4507-config-row';
        row.dataset.v4523MetaRow='1';
        row.innerHTML='<span>Marca / últimos 4</span><b>Opcional</b>';
        const sensitive=qa('.v4507-config-row',list).find(x=>
          String(x.textContent||'').includes('Número de tarjeta')
        );
        if(sensitive) sensitive.insertAdjacentElement('beforebegin',row);
        else list.appendChild(row);
      }
    }

    const future=q('.v4507-future',section);
    if(future && future.dataset.v4523Done!=='1'){
      future.dataset.v4523Done='1';
      future.innerHTML='<b>Estado confirmado:</b> Bendo Smart trabaja actualmente con protocolo cerrado. '
        +'Recepción mantiene el paso manual y queda preparada para una integración futura si Bendo habilita API/ECR/SDK.';
    }
  }

  function patchFlow(){
    const host=flow();
    if(!host)return;

    const amount=total();
    const op=q('#v4507Voucher',host);
    if(op){
      const label=op.closest('.v4507-bendo-field')?.querySelector('label');
      if(label) label.textContent='N.º de operación Bendo';
      op.placeholder=ui.noOperation?'Marcado como no disponible':'Ej. 535650';
      op.inputMode='numeric';
      op.autocomplete='off';
      op.disabled=!!ui.noOperation;

      if(!op.dataset.v4523Bound){
        op.dataset.v4523Bound='1';
        if(!ui.operation && op.value) ui.operation=cleanOperation(op.value);
        op.addEventListener('input',()=>{
          const cleaned=cleanOperation(op.value);
          if(op.value!==cleaned) op.value=cleaned;
          ui.operation=cleaned;
          invalidateApproval();
        });
      }

      if(document.activeElement!==op && !ui.noOperation && op.value!==ui.operation){
        op.value=ui.operation;
        op.dispatchEvent(new Event('input',{bubbles:true}));
      }
    }

    const fields=q('.v4507-bendo-fields',host);
    if(fields && !q('#v4523BendoExtra',fields)){
      const extra=document.createElement('div');
      extra.id='v4523BendoExtra';
      extra.className='v4523-bendo-extra';
      extra.innerHTML=
        '<div><label for="v4523Brand">Marca (opcional)</label>'
        +'<select id="v4523Brand">'
        +'<option value="">—</option>'
        +'<option value="VISA">Visa</option>'
        +'<option value="MASTERCARD">Mastercard</option>'
        +'<option value="DINERS">Diners</option>'
        +'<option value="AMEX">American Express</option>'
        +'<option value="DISCOVER">Discover</option>'
        +'<option value="OTRA">Otra</option>'
        +'</select></div>'
        +'<div><label for="v4523Last4">Últimos 4 (opcional)</label>'
        +'<input id="v4523Last4" type="text" inputmode="numeric" maxlength="4" placeholder="4545"></div>'
        +'<label class="v4523-no-operation"><input id="v4523NoOperation" type="checkbox"> '
        +'N.º de operación no disponible</label>';
      fields.appendChild(extra);

      const brand=q('#v4523Brand',extra);
      const last4=q('#v4523Last4',extra);
      const noOp=q('#v4523NoOperation',extra);
      if(brand){
        brand.value=ui.brand||'';
        brand.addEventListener('change',()=>{
          ui.brand=String(brand.value||'').toUpperCase();
          invalidateApproval();
        });
      }
      if(last4){
        last4.value=ui.last4||'';
        last4.addEventListener('input',()=>{
          const cleaned=cleanLast4(last4.value);
          if(last4.value!==cleaned)last4.value=cleaned;
          ui.last4=cleaned;
          invalidateApproval();
        });
      }
      if(noOp){
        noOp.checked=!!ui.noOperation;
        noOp.addEventListener('change',()=>{
          ui.noOperation=!!noOp.checked;
          const backing=q('#v4507Voucher',host);
          if(ui.noOperation && backing){
            backing.value='';
            backing.dispatchEvent(new Event('input',{bubbles:true}));
          }
          invalidateApproval();
          patchFlow();
        });
      }
    }else{
      const brand=q('#v4523Brand',host);
      const last4=q('#v4523Last4',host);
      const noOp=q('#v4523NoOperation',host);
      if(brand && brand.value!==(ui.brand||'')) brand.value=ui.brand||'';
      if(last4 && document.activeElement!==last4 && last4.value!==(ui.last4||'')) last4.value=ui.last4||'';
      if(noOp) noOp.checked=!!ui.noOperation;
    }

    const step3=qa('.v4507-bendo-step',host).find(x=>
      String(x.querySelector('span')?.textContent||'').includes('3')
    );
    if(step3){
      const b=step3.querySelector('b');
      if(b)b.textContent='Cuando Bendo muestre PAGO EXITOSO, confirma aquí.';
    }

    const approve=q('#v4507Approve',host);
    if(approve){
      approve.disabled=amount<=0;
      approve.title=amount<=0?'Selecciona primero una consulta o procedimiento.':'Confirma solo después de ver PAGO EXITOSO en Bendo.';

      if(!approve.dataset.v4523Guard){
        approve.dataset.v4523Guard='1';
        approve.addEventListener('click',event=>{
          if(!validateMeta(true)){
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            return;
          }
          if(!window.confirm(approvalQuestion())){
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            return;
          }
          ui.approvedSnapshot=snapshot();
          setTimeout(patchFlow,0);
          setTimeout(patchFlow,80);
        },true);
      }

      if(approve.classList.contains('done')){
        if(ui.approvedSnapshot===snapshot()){
          approve.classList.remove('v4523-reconfirm');
          approve.textContent='✓ BENDO: PAGO APROBADO';
        }else{
          approve.classList.add('v4523-reconfirm');
          approve.textContent='⚠ Volver a confirmar PAGO EXITOSO';
        }
      }
    }

    const result=q('.v4507-bendo-result',host);
    if(result){
      if(approve?.classList.contains('done') && ui.approvedSnapshot===snapshot()){
        result.classList.add('ok');
        result.textContent='✓ Pago verificado · listo para guardar';
      }else if(amount<=0){
        result.classList.remove('ok');
        result.textContent='Selecciona una consulta o procedimiento para continuar.';
      }else{
        result.classList.remove('ok');
        result.textContent='Cuando Bendo muestre PAGO EXITOSO, confirma aquí.';
      }
    }

    q('#v4523BendoSummary',host)?.remove();
    if(approve?.classList.contains('done') && ui.approvedSnapshot===snapshot()){
      const summary=document.createElement('div');
      summary.id='v4523BendoSummary';
      summary.className='v4523-bendo-summary';
      summary.innerHTML='<strong>✓ COBRO BENDO VERIFICADO</strong><span></span>';
      q('span',summary).textContent=summaryText();
      const warning=q('.v4507-bendo-warning',host);
      if(warning) warning.insertAdjacentElement('beforebegin',summary);
      else q('.v4507-bendo-body',host)?.appendChild(summary);
    }
  }

  document.addEventListener('click',event=>{
    if(event.target?.closest?.(
      '#v4507BendoFlow [data-v4507-cardtype],'
      +'#v4507BendoFlow [data-v4507-plan],'
      +'.attention-form-modal .service-card'
    )){
      ui.approvedSnapshot='';
      setTimeout(patchFlow,40);
      setTimeout(patchFlow,180);
    }
  },true);

  const stableSave=window.saveAttention;
  if(typeof stableSave==='function' && !stableSave.__v4523){
    const wrapped=async function(){
      if(!active()){
        return await stableSave.apply(this,arguments);
      }

      if(!validateMeta(true)){
        patchFlow();
        return;
      }
      if(ui.approvedSnapshot!==snapshot()){
        alert('Confirma nuevamente el PAGO EXITOSO en Bendo antes de guardar.');
        patchFlow();
        return;
      }

      const previousWindowApi=window.api;
      let previousApi=null;
      try{previousApi=api}catch(_e){}
      const downstream=previousWindowApi||previousApi;

      if(typeof downstream!=='function'){
        alert('No se pudo preparar el registro del cobro. Cierra y vuelve a abrir Nueva atención.');
        return;
      }

      const intercept=async function(url,opt={}){
        if(String(url)==='/api/visits/batch-payment'){
          let body={};
          try{body=JSON.parse(opt?.body||'{}')}catch(_e){body={}}
          body.card_reference=referenceValue();
          delete body.voucher;
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
    wrapped.__v4523=true;
    window.saveAttention=wrapped;
  }

  function boot(){
    patchFlow();
    patchConfig();
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',boot,{once:true});
  }else{
    boot();
  }

  const observer=new MutationObserver(()=>{
    requestAnimationFrame(()=>{
      patchFlow();
      patchConfig();
    });
  });
  const root=document.body||document.documentElement;
  if(root)observer.observe(root,{subtree:true,childList:true});

  window.addEventListener('focus',boot);
  setTimeout(boot,250);
  setTimeout(boot,900);
})();
"""

core.V460_OVERLAY_CSS=(getattr(core,"V460_OVERLAY_CSS","") or "")+"\n"+V4523_CSS
core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+V4523_JS

@app.get("/api/v4523/health")
def v4523_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "bendo_manual_flow": True,
        "bendo_operation_reference": True,
        "bendo_brand_optional": True,
        "bendo_last4_optional": True,
        "bendo_operation_unavailable_explicit": True,
        "bendo_payment_success_confirmation": True,
        "zero_amount_approval_blocked": True,
        "card_reference_mapping_fixed": True,
        "stores_pan": False,
        "stores_cvv": False,
        "database_schema_changes": False,
        "azur_contract_changes": False,
        "neon_schema_changes": False,
    }

PATCH_BOOT_OK = True
