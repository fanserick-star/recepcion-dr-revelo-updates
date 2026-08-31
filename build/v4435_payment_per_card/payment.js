;(()=>{
  if(window.__v4435BillingPayment)return;
  window.__v4435BillingPayment=true;
  window.__v4431BillingPayment=true;

  const VERSION='4.4.35';
  let paymentMap=new Map();
  let refreshBusy=false;
  let decorateTimer=0;
  let listObserver=null;

  const key=(pid,fecha)=>`${Number(pid)}|${String(fecha||'').slice(0,10)}`;

  function cachedGroups(){
    try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}
    catch(_e){return []}
  }

  function parseIdentityFromActions(card){
    const attrs=[...card.querySelectorAll('button[onclick],a[onclick]')]
      .map(el=>String(el.getAttribute('onclick')||''));
    // La interfaz puede cambiar previewAzurInvoice por “Revisar y emitir”.
    // También sirven acciones hermanas como openBillingRecipientEditor(id, fecha).
    for(const raw of attrs){
      const m=/\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]/.exec(raw);
      if(m)return {patient_id:Number(m[1]),fecha:m[2]};
    }
    return null;
  }

  function identityFromCache(card){
    const cards=[...document.querySelectorAll('#billingList .billing-card')];
    const idx=cards.indexOf(card);
    if(idx<0)return null;
    const g=cachedGroups()[idx];
    const patientId=Number(g?.patient?.id||0);
    const fecha=String(g?.fecha||'').slice(0,10);
    return patientId&&/^\d{4}-\d{2}-\d{2}$/.test(fecha)
      ?{patient_id:patientId,fecha,group:g}:null;
  }

  function identifyCard(card){
    if(!card)return null;
    const dsPid=Number(card.dataset.patientId||0);
    const dsFecha=String(card.dataset.fecha||'').slice(0,10);
    let id=(dsPid&&/^\d{4}-\d{2}-\d{2}$/.test(dsFecha))
      ?{patient_id:dsPid,fecha:dsFecha}:parseIdentityFromActions(card);
    const cached=identityFromCache(card);
    if(!id&&cached)id=cached;
    if(!id)return null;
    if(!id.group&&cached&&Number(cached.patient_id)===Number(id.patient_id)&&cached.fecha===id.fecha)id.group=cached.group;
    card.dataset.patientId=String(id.patient_id);
    card.dataset.fecha=id.fecha;
    return id;
  }

  function findEmitButton(card){
    const buttons=[...card.querySelectorAll('button')];
    let btn=buttons.find(b=>String(b.getAttribute('onclick')||'').includes('previewAzurInvoice'));
    if(btn)return btn;
    btn=buttons.find(b=>{
      const t=String(b.textContent||'').toLowerCase();
      return (t.includes('revisar')&&t.includes('emitir'))||t.includes('emitir en azur');
    });
    return btn||null;
  }

  function groupState(id,card){
    try{
      if(id?.group&&typeof billingGroupStatus==='function')return String(billingGroupStatus(id.group)||'').toUpperCase();
    }catch(_e){}
    if(card?.classList?.contains('aprobada'))return 'APROBADA';
    return findEmitButton(card)?'APROBADA':'';
  }

  function isEmissionCard(card,id){
    if(!id)return false;
    return groupState(id,card)==='APROBADA'||!!findEmitButton(card);
  }

  function setEmitLock(card,selected){
    const emit=findEmitButton(card);if(!emit)return;
    const locked=!selected;
    emit.disabled=locked;
    emit.classList.toggle('v4435-pay-locked',locked);
    emit.setAttribute('aria-disabled',locked?'true':'false');
    emit.title=locked?'Selecciona Efectivo o Transferencia antes de revisar y emitir':'';
  }

  function renderPicker(card){
    const id=identifyCard(card);if(!isEmissionCard(card,id))return;
    const selected=paymentMap.get(key(id.patient_id,id.fecha))||'';
    let wrap=card.querySelector('.v4431-pay-wrap');
    if(!wrap){
      wrap=document.createElement('div');
      wrap.className='v4431-pay-wrap';
      const foot=card.querySelector('.billing-card-foot');
      const actions=card.querySelector('.billing-actions');
      if(foot&&actions&&actions.parentElement===foot)foot.insertBefore(wrap,actions);
      else if(actions)actions.insertAdjacentElement('beforebegin',wrap);
      else if(foot)foot.appendChild(wrap);
      else card.appendChild(wrap);
    }
    wrap.dataset.patientId=String(id.patient_id);
    wrap.dataset.fecha=id.fecha;
    wrap.innerHTML=`
      <span class="v4431-pay-label">Forma de pago</span>
      <button type="button" class="v4431-pay-choice ${selected==='EFECTIVO'?'selected':''}" data-pay="EFECTIVO">
        <span class="v4431-check">✓</span><span>💵 Efectivo</span>
      </button>
      <button type="button" class="v4431-pay-choice ${selected==='TRANSFERENCIA'?'selected':''}" data-pay="TRANSFERENCIA">
        <span class="v4431-check">✓</span><span>🏦 Transferencia</span>
      </button>`;
    wrap.querySelectorAll('.v4431-pay-choice').forEach(btn=>{
      btn.addEventListener('click',()=>saveChoice(wrap,String(btn.dataset.pay||'')));
    });
    setEmitLock(card,selected);
  }

  async function saveChoice(wrap,method){
    if(!['EFECTIVO','TRANSFERENCIA'].includes(method))return;
    const patient_id=Number(wrap.dataset.patientId||0);
    const fecha=String(wrap.dataset.fecha||'');
    if(!patient_id||!fecha)return;
    wrap.classList.add('v4431-pay-saving');
    try{
      const d=await api('/api/billing/payment-method',{
        method:'POST',body:JSON.stringify({patient_id,fecha,payment_method:method})
      });
      paymentMap.set(key(patient_id,fecha),String(d.payment_method||method));
      wrap.classList.remove('required');
      const card=wrap.closest('.billing-card');
      if(card)renderPicker(card);
    }catch(e){alert(e.message||'No se pudo guardar la forma de pago.')}
    finally{wrap.classList.remove('v4431-pay-saving')}
  }

  async function refreshPaymentMap(redecorate=true){
    if(refreshBusy)return;
    refreshBusy=true;
    try{
      const d=await api('/api/billing/payment-methods');
      paymentMap=new Map((d?.items||[]).map(x=>[
        key(x.patient_id,x.fecha),String(x.payment_method||'')
      ]));
      if(redecorate)decorate();
    }catch(_e){}
    finally{refreshBusy=false}
  }

  function cardMissingPayment(card){
    const id=identifyCard(card);
    if(!isEmissionCard(card,id))return false;
    return !paymentMap.get(key(id.patient_id,id.fecha));
  }

  async function batchPreflight(){
    await refreshPaymentMap(false);
    const cards=[...document.querySelectorAll('#billingList .billing-card')]
      .filter(card=>isEmissionCard(card,identifyCard(card)));
    const missing=cards.filter(card=>cardMissingPayment(card));
    if(missing.length){
      missing.forEach(card=>card.querySelector('.v4431-pay-wrap')?.classList.add('required'));
      try{missing[0]?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      alert(`Antes de emitir por lotes, selecciona Efectivo o Transferencia individualmente en ${missing.length} factura${missing.length===1?'':'s'}.`);
      return;
    }
    if(typeof window.emitAllPendingInvoices==='function')return window.emitAllPendingInvoices();
    alert('La emisión por lotes no está disponible en esta instalación.');
  }

  function ensureBatchButton(){
    let btn=document.getElementById('btnEmitAll')||document.getElementById('v4435EmitAll');
    if(!btn){
      const host=document.querySelector('#facturacion .billing-title-actions')
        ||document.querySelector('#facturacion .page-title-actions')
        ||document.querySelector('#facturacion .section-title-actions');
      if(!host)return;
      btn=document.createElement('button');
      btn.id='v4435EmitAll';
      btn.className='btn small secondary';
      host.appendChild(btn);
    }
    btn.hidden=false;
    btn.classList.add('v4435-batch-button');
    btn.textContent='📦 Emitir por lotes';
    btn.removeAttribute('onclick');
    if(!btn.__v4435BatchHook){
      btn.__v4435BatchHook=true;
      btn.addEventListener('click',batchPreflight);
    }
  }

  function decorate(){
    document.querySelectorAll('#billingList .billing-card').forEach(card=>renderPicker(card));
    ensureBatchButton();
  }

  function scheduleDecorate(){
    clearTimeout(decorateTimer);
    decorateTimer=setTimeout(decorate,20);
  }

  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('button');if(!btn)return;
    const card=btn.closest('.billing-card');if(!card)return;
    const emit=findEmitButton(card);if(btn!==emit)return;
    const id=identifyCard(card);if(!id)return;
    if(!paymentMap.get(key(id.patient_id,id.fecha))){
      e.preventDefault();e.stopImmediatePropagation();
      const wrap=card.querySelector('.v4431-pay-wrap');
      wrap?.classList.add('required');
      try{wrap?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      wrap?.querySelector('.v4431-pay-choice')?.focus();
      alert('Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.');
    }
  },true);

  function hookBilling(){
    const fn=window.loadBilling;
    if(typeof fn!=='function')return false;
    if(fn.__v4435Hook)return true;
    const wrapped=async function(){
      const result=await fn.apply(this,arguments);
      await refreshPaymentMap(false);
      scheduleDecorate();
      return result;
    };
    wrapped.__v4435Hook=true;
    window.loadBilling=wrapped;
    return true;
  }

  function observeBillingList(){
    const list=document.querySelector('#billingList');
    if(!list||list.__v4435Observed)return;
    list.__v4435Observed=true;
    listObserver=new MutationObserver(mutations=>{
      if(mutations.some(m=>[...m.addedNodes].some(n=>n?.nodeType===1&&(n.matches?.('.billing-card')||n.querySelector?.('.billing-card'))))){
        refreshPaymentMap(false).finally(scheduleDecorate);
      }
    });
    listObserver.observe(list,{childList:true,subtree:false});
  }

  async function boot(){
    hookBilling();
    observeBillingList();
    ensureBatchButton();
    await refreshPaymentMap(false);
    decorate();
  }

  window.__v4435BillingPaymentTest={decorate,identifyCard,ensureBatchButton,batchPreflight};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
