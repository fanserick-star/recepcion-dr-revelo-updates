/* Recepción 4.8.46 — AZUR consultation credential stored only on the local PC. */
(function(){
'use strict';
if(window.__azurReadonly4846)return;window.__azurReadonly4846=true;
const q=(s,r=document)=>r.querySelector(s);
function msg(value,good){
  const out=q('#azurReadResult');if(!out)return;
  out.textContent=String(value||'');out.className='desktop-runtime-status azur-read-result'+(good?' is-ok':'');
}
function render(status){
  const badge=q('#azurReadPill');if(!badge)return;
  badge.textContent=status.configured?'Guardada · '+(status.environment||''):'No configurada';
  badge.classList.toggle('ready',Boolean(status.configured));
  const tenant=q('#azurReadTenant');
  if(tenant)tenant.textContent=status.tenant?'Cuenta AZUR: '+status.tenant:'Configura primero AZUR para emitir facturas.';
}
window.loadAzurReadStatus=async function(){
  try {render(await api('/api/azur/readonly/status'));}
  catch(err){msg(err && err.message || 'No se pudo consultar la configuración.',false);}
};
window.saveAzurReadKey=async function(){
  const el=q('#azurReadKey'),save=q('#azurReadSave');
  const token=String(el && el.value || '').trim();
  if(!token){msg('Pega aquí la nueva credencial de CONSULTA. No uses la clave de emisión.',false);return;}
  if(save)save.disabled=true;
  try {
    const response=await api('/api/azur/readonly/config',{method:'POST',body:JSON.stringify({api_key:token})});
    if(el)el.value='';
    render(response);msg('Credencial de consulta guardada solo en esta computadora. Pulsa «Probar consulta».',true);
  }catch(err){msg(err && err.message || 'No se pudo guardar la credencial.',false);}
  finally{if(save)save.disabled=false;}
};
window.testAzurReadKey=async function(){
  const button=q('#azurReadTest');if(button)button.disabled=true;
  msg('Probando acceso de solo lectura a AZUR. No se emitirá ni imprimirá nada.',false);
  try {
    const response=await api('/api/azur/readonly/test',{method:'POST',body:'{}'});
    msg('✓ '+(response.message||'Consulta disponible')+' Ambiente: '+(response.environment||'sin indicar'),true);
    await window.loadAzurReadStatus();
  }catch(err){msg(err && err.message || 'Error al probar la conexión.',false);}
  finally{if(button)button.disabled=false;}
};
window.verifyAzurPosInvoice=async function(patientId,fecha,number){
  if(!number){alert('La factura debe tener un número autorizado antes de verificarla.');return;}
  const message='¿Comprobar esta factura en AZUR sin imprimir ni modificarla?\n\nFactura: '+number;
  const ok=typeof window.rpConfirm==='function'?await window.rpConfirm(message,'Verificación de factura'):window.confirm(message);
  if(!ok)return;
  try {
    const result=await api('/api/azur/readonly/verify-invoice',{method:'POST',body:JSON.stringify({
      patient_id:Number(patientId),fecha:String(fecha||'').slice(0,10),numero_factura:String(number)
    })});
    const note='✓ '+result.message+' (AZUR #'+result.azur_id+'). No se imprimió nada.';
    if(typeof window.rpNotice==='function')window.rpNotice(note,'Consulta autorizada');
    else alert(note);
  }catch(err){alert('La verificación de AZUR no terminó: '+String(err && err.message || err)+'\nNo se imprimió ninguna factura.');}
};
function install(){
  if(q('#azurReadPanel'))return;
  const original=q('#azurConfigPanel');if(!original)return;
  const panel=document.createElement('details');
  panel.id='azurReadPanel';panel.className='panel compact-config-panel config-advanced';
  panel.innerHTML='<summary>Impresión 80 mm · conexión de consulta AZUR <span id="azurReadPill" class="performance-pill">Comprobando</span></summary>'+
  '<div class="config-advanced-body"><p class="muted">Esta credencial es diferente de la que emite facturas. Permite CONSULTAR comprobantes existentes. Nunca se usa para emitir, anular o modificar.</p>'+
  '<div class="azur-settings-grid"><label><span>Credencial API v2 · Consultar comprobantes</span><input id="azurReadKey" type="password" autocomplete="new-password" spellcheck="false" placeholder="sk_live_… · dejar vacío para conservar la guardada"></label></div>'+
  '<small id="azurReadTenant" class="muted"></small>'+
  '<div class="actions"><button type="button" class="primary-soft" id="azurReadSave" onclick="saveAzurReadKey()">Guardar credencial de consulta</button>'+
  '<button type="button" id="azurReadTest" onclick="testAzurReadKey()">Probar consulta (sin imprimir)</button></div>'+
  '<div id="azurReadResult" class="desktop-runtime-status azur-read-result">Esta prueba no imprime ni envía facturas al SRI.</div>'+
  '<p class="muted">Siguiente etapa: validar el XML de una factura autorizada y probar el formato de 80 mm antes de habilitar impresión directa.</p></div>';
  original.insertAdjacentElement('afterend',panel);
  window.loadAzurReadStatus();
}
document.addEventListener('click',function(e){
  const b=e.target && e.target.closest('[data-config-tab="facturacion"]');
  if(b)setTimeout(function(){install();window.loadAzurReadStatus();},0);
},true);
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
else install();
})();
