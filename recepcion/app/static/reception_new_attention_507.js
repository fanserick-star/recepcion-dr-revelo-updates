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
})();
