/* Recepción 5.0.7: information panels for native Nueva atención.
 * No new writes or periodic reads. All POST/printing/clinical validation remain
 * in original app.js; this module only renders verified/local-first data. */
;(()=>{
'use strict';
if(window.__r507NativeAttention)return;window.__r507NativeAttention=true;
const by=id=>document.getElementById(id);
const escapeText=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const selected=()=>typeof attentionContext==='undefined'?null:attentionContext;
const setHTML=(id,html)=>{const el=by(id);if(el)el.innerHTML=html};
const current=()=>Number(selected()?.patient?.id||0);
let historyRequest=0;
function clearPanels(){
  historyRequest++;
  setHTML('r507BillingSummary','<div class="r507-empty-rail">Selecciona un servicio para consultar su valor.</div>');
  setHTML('r507HistoryList','<div class="r507-empty-rail">Selecciona un paciente para consultar su historial.</div>');
  setHTML('r507ClinicalPanel','<div class="r507-empty-rail">La vinculación se comprobará al seleccionar el paciente.</div>');
}
function billing(){
  if(!current())return;
  const host=by('r507BillingSummary');if(!host)return;
  if(typeof captureProcedureValues==='function')captureProcedureValues();
  const names=typeof selectedServiceOrder==='function'?selectedServiceOrder():[];
  if(!names.length){
    host.innerHTML='<div class="r507-empty-rail">Selecciona una consulta o procedimiento a la izquierda. No hay cobro marcado por defecto.</div>';
    return;
  }
  let total=0,known=true;
  const rows=names.map(name=>{
    let value;
    if(name==='CONSULTA')value=40;
    else {
      const raw=attentionServiceValues[name];
      if(raw!==undefined&&raw!==null&&String(raw).trim()!==''&&Number.isFinite(Number(raw))&&Number(raw)>=0)value=Number(raw);
      else known=false;
    }
    if(value!==undefined)total+=value;
    const label=typeof serviceLabel==='function'?serviceLabel(name):name;
    return '<div class="r507-billing-item"><span>'+escapeText(label)+'</span><strong>'+(value===undefined?'Pendiente':'$ '+value.toFixed(2))+'</strong></div>';
  }).join('');
  host.innerHTML='<div class="r507-billing-caption">Servicios seleccionados</div>'+rows+
    '<div class="r507-billing-total"><span>Total estimado</span><b>'+(known?'$ '+total.toFixed(2):'Por completar')+'</b></div>'+
    '<small>La facturación y la forma de pago se procesan con las reglas actuales de Recepción.</small>';
}
function clinical(){
  const state=selected();
  if(!state?.patient)return;
  const linked=state.clinicalLink;
  const kind=typeof currentDetectedStatus==='function'?currentDetectedStatus():'N';
  let tone='checking',heading='Comprobando vinculación…',text='Consultando el estado actual de la ficha en Historia Clínica.';
  if(linked===true){
    tone='ready';heading='Ficha de Historia vinculada';text='Identidad verificada. La entrega se realizará por la cola clínica al guardar la atención.';
  }else if(linked===false){
    tone='warning';heading='Vinculación pendiente';text='Se requiere confirmar la ficha médica antes de entregar al doctor.';
  }
  const linkAction=linked===false
    ?'<button type="button" class="r507-link-chart" onclick="r507LinkClinical()">Vincular con Historia Clínica</button>'
    :'';
  setHTML('r507ClinicalPanel','<div class="r507-clinical-state '+tone+'"><span class="r507-clinical-mark">'+(linked===true?'✓':linked===false?'!':'…')+'</span><div><b>'+escapeText(heading)+'</b><small>'+escapeText(text)+'</small></div></div>'+
    '<div class="r507-clinical-kind">Paciente: <strong>'+(kind==='S'?'Subsecuente':'Nuevo / por confirmar')+'</strong></div>'+linkAction);
}
async function history(patientId){
  const seq=++historyRequest;
  setHTML('r507HistoryList','<span class="r509-last-text">Consultando última atención…</span>');
  try{
    const result=await api('/api/patients/'+Number(patientId)+'/profile');
    if(seq!==historyRequest||current()!==patientId)return;
    const visits=Array.isArray(result?.visits)?result.visits:[];
    const sorted=[...visits].sort((a,b)=>{
      const byDate=String(b.fecha||'').localeCompare(String(a.fecha||''));
      return byDate||Number(b.id||0)-Number(a.id||0);
    });
    const v=sorted[0];
    if(!v){
      setHTML('r507HistoryList','<span class="r509-last-text">Sin atenciones anteriores.</span>');
      return;
    }
    const type=v.exam_review_no_charge?'Revisión de exámenes':
      (v.procedimiento?(typeof serviceLabel==='function'?serviceLabel(v.procedimiento):v.procedimiento):'Consulta');
    const date=typeof fmtDate==='function'?fmtDate(v.fecha):String(v.fecha||'');
    setHTML('r507HistoryList','<span class="r509-last-date">'+escapeText(date)+'</span><span class="r509-last-type">'+escapeText(type)+'</span>');
  }catch(error){
    if(seq===historyRequest)setHTML('r507HistoryList','<span class="r509-last-text">No disponible temporalmente.</span>');
  }
}
// Reuses the official v4613 manual linking/creation dialog. Never creates
// a medical chart automatically on a visual click and never fakes verification.
window.r507LinkClinical=()=>{
  const pid=current();if(!pid)return;
  const name=String(selected()?.patient?.nombre||'');
  if(typeof window.openRegistrationHistoryLink!=='function'){
    alert('No está disponible el módulo de vinculación. Cierra y abre Recepción para actualizarlo.');
    return;
  }
  return window.openRegistrationHistoryLink(pid,name,()=>{
    if(current()===pid&&typeof refreshAttentionClinicalHistory==='function'){
      void refreshAttentionClinicalHistory(pid);
    }
  });
};
window.r507AttentionReset=clearPanels;
window.r507AttentionPriceChanged=billing;
window.r507ClinicalStatusChanged=clinical;
window.r507AttentionSelected=(patient)=>{
  const id=Number(patient?.id||0);
  if(!id)return;
  billing();
  clinical();
  void history(id);
};
// Updates the amount as prices are edited: no automatic saves / billing changes.
const page=by('atencion');
if(page){
  page.addEventListener('input',event=>{
    if(event.target?.matches?.('.procedure-value-input'))billing();
  });

}
}
 // 5.0.12: independent native modal for choosing services and editing their values.
 // All selections remain a *draft* until the original saveAttention API executes.
 // Cancelling restores the original selection and prices; there are no writes here.
 let servicePicker=null;
 const pickerNames=()=>typeof selectedServiceOrder==='function'?selectedServiceOrder():[];
 function pickerPreview(){
   const host=by('r512SelectionPreview');if(!host)return;
   const names=pickerNames();
   if(!names.length){
     host.innerHTML='<span class="r512-preview-empty">Todavía no hay consulta ni procedimiento seleccionado.</span>';
     return;
   }
   host.innerHTML=names.slice(0,5).map(name=>{
     const consultation=name==='CONSULTA',raw=consultation?40:attentionServiceValues[name];
     const valid=raw!==undefined&&raw!==null&&String(raw).trim()!==''&&Number.isFinite(Number(raw))&&Number(raw)>=0;
     const label=typeof serviceLabel==='function'?serviceLabel(name):name;
     return '<span class="r512-preview-chip '+(consultation?'consultation':'procedure')+'">'
       +escapeText(label)+' <b>'+(valid?'$'+Number(raw).toFixed(2):'Valor pendiente')+'</b></span>';
   }).join('')+(names.length>5?'<span class="r512-preview-extra">+'+(names.length-5)+' más</span>':'');
 }
 function pickerTotals(){
   const names=pickerNames();let total=0,valid=true;
   for(const name of names){
     const raw=name==='CONSULTA'?40:attentionServiceValues[name];
     if(raw===undefined||raw===null||String(raw).trim()===''||!Number.isFinite(Number(raw))||Number(raw)<0){valid=false;continue}
     total+=Number(raw);
   }
   const counter=by('r512PickerCount'),amount=by('r512PickerTotal');
   if(counter)counter.textContent=names.length+' seleccionado'+(names.length===1?'':'s');
   if(amount)amount.textContent=names.length&&valid?'$ '+total.toFixed(2):'Por completar';
 }
 function pickerEditor(){
   const host=by('r512PickerPrices');if(!host)return;
   const names=pickerNames().filter(n=>n!=='CONSULTA');
   host.innerHTML=names.length
     ?'<h3>Valores de procedimientos seleccionados</h3><div class="r512-price-list">'+names.map(name=>{
       const value=attentionServiceValues[name];
       return '<label class="r512-price-row"><span>'+escapeText(typeof serviceLabel==='function'?serviceLabel(name):name)+'</span>'
         +'<span class="r512-money"><b>$</b><input class="r512-price-input" data-service="'+escapeText(name)+'" type="number" inputmode="decimal" min="0" step="0.01" value="'+escapeText(value??'')+'" placeholder="Valor" aria-label="Precio de '+escapeText(name)+'"></span></label>';
     }).join('')+'</div>'
     :'<div class="r512-price-empty">Los valores editables aparecerán aquí al seleccionar un procedimiento. La consulta mantiene su valor habitual de $40,00.</div>';
   pickerTotals();
 }
 function dismissPicker(revert=false){
   if(!servicePicker)return;
   const state=servicePicker;
   servicePicker=null;
   document.removeEventListener('keydown',state.onKey,true);
   state.overlay.remove();
   document.body.classList.remove('r512-picker-open');
   if(revert){
     selectedServices=new Set(state.originalServices);
     attentionServiceValues={...state.originalValues};
     const hidden=by('procedureValuesBox');
     if(hidden){hidden.innerHTML='';hidden.classList.add('hidden')}
     if(typeof renderSelectedServiceValues==='function')renderSelectedServiceValues();
     if(typeof window.r507AttentionPriceChanged==='function')window.r507AttentionPriceChanged();
   }
   pickerPreview();
   if(by('r512ServiceButton')&&by('r512ServiceButton').isConnected)by('r512ServiceButton').focus();
 }
 window.r512DismissServicePicker=dismissPicker;
 window.r512AttentionSummaryChanged=pickerPreview;
 window.r512OpenServicePicker=()=>{
   if(servicePicker||!current()||!by('r512ServiceButton'))return;
   if(typeof captureProcedureValues==='function')captureProcedureValues();
   const originalServices=[...selectedServices],originalValues={...attentionServiceValues};
   const overlay=document.createElement('div');
   overlay.id='r512ServiceOverlay';
   overlay.className='r512-overlay';
   overlay.innerHTML='<section class="r512-dialog" role="dialog" aria-modal="true" aria-labelledby="r512PickerTitle">'
     +'<header class="r512-dialog-header"><div><span class="r512-eyebrow">NUEVA ATENCIÓN</span><h2 id="r512PickerTitle">Seleccionar servicios y precios</h2><p>Consulta y procedimientos por separado. Puedes elegir varios.</p></div>'
     +'<button class="r512-close" type="button" data-picker-cancel="1" aria-label="Cerrar selección">×</button></header>'
     +'<div class="r512-dialog-main"><div class="r512-catalog">'+serviceCardsHtml()+'</div>'
     +'<section id="r512PickerPrices" class="r512-editor" aria-label="Precios de procedimientos"></section></div>'
     +'<footer class="r512-dialog-footer"><div class="r512-total"><small id="r512PickerCount">0 seleccionados</small><strong id="r512PickerTotal">Por completar</strong></div>'
     +'<div class="r512-dialog-actions"><button type="button" class="r512-cancel" data-picker-cancel="1">Cancelar</button><button type="button" class="r512-apply" id="r512Apply">✓ Aplicar selección</button></div>'
     +'<div class="r512-error" id="r512PickerError" role="alert" aria-live="polite"></div></footer></section>';
   const onKey=event=>{
     if(event.key==='Escape'){event.preventDefault();event.stopPropagation();dismissPicker(true);return}
     if(event.key!=='Tab')return;
     const controls=[...overlay.querySelectorAll('button:not(:disabled),input:not(:disabled)')].filter(e=>e.getClientRects().length);
     if(!controls.length)return;
     const first=controls[0],last=controls[controls.length-1];
     if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
     else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
   };
   servicePicker={overlay,patientId:current(),originalServices,originalValues,onKey};
   document.body.appendChild(overlay);
   document.body.classList.add('r512-picker-open');
   document.addEventListener('keydown',onKey,true);
   overlay.addEventListener('click',event=>{
     if(event.target===overlay||event.target.closest('[data-picker-cancel]')){dismissPicker(true);return}
     if(event.target.closest('.service-card')){
       const err=by('r512PickerError');if(err)err.textContent='';
       pickerEditor();
     }
     if(event.target.closest('#r512Apply')){
       const err=by('r512PickerError');
       if(current()!==servicePicker?.patientId){dismissPicker(true);return}
       const names=pickerNames();
       if(!names.length){if(err)err.textContent='Selecciona al menos una consulta o procedimiento.';return}
       for(const name of names.filter(n=>n!=='CONSULTA')){
         const raw=attentionServiceValues[name];
         if(raw===undefined||raw===null||String(raw).trim()===''||!Number.isFinite(Number(raw))||Number(raw)<0){
           if(err)err.textContent='Ingresa un valor válido para '+(typeof serviceLabel==='function'?serviceLabel(name):name)+'.';
           const input=[...overlay.querySelectorAll('.r512-price-input')].find(x=>x.dataset.service===name);
           input?.focus();return;
         }
       }
       if(typeof captureProcedureValues==='function')captureProcedureValues();
       if(typeof window.r507AttentionPriceChanged==='function')window.r507AttentionPriceChanged();
       dismissPicker(false);
     }
   });
   overlay.addEventListener('input',event=>{
     const input=event.target.closest('.r512-price-input');if(!input)return;
     const key=typeof serviceKey==='function'?serviceKey(input.dataset.service):String(input.dataset.service||'');
     attentionServiceValues[key]=input.value;
     const original=[...document.querySelectorAll('#procedureValuesBox .procedure-value-input')].find(x=>x.dataset.service===key);
     if(original)original.value=input.value;
     if(typeof window.r507AttentionPriceChanged==='function')window.r507AttentionPriceChanged();
     pickerTotals();pickerPreview();
     const err=by('r512PickerError');if(err)err.textContent='';
   });
   pickerEditor();
   overlay.querySelector('.r512-close')?.focus();
 };
})();
