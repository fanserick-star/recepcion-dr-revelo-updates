(()=>{
'use strict';
if(window.__receptionConfigConsolidated)return;
window.__receptionConfigConsolidated=true;
const q=(s,r=document)=>r.querySelector(s);
const qa=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const call=async(url,opt={})=>{if(typeof window.api==='function')return window.api(url,opt);const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.message||'Error');return d};
let dpCache=null;
let waCloudTest=null;
let waPoll=null;

window.confirmDeletion=message=>window.confirm(message);

function cleanLegacyConfigArtifacts(){
  const config=q('#config');if(!config)return;
  for(const name of ['services','maintenance','dataphone','actualizaciones']){
    q(`[data-config-tab="${name}"]`,config)?.remove();
    q(`[data-config-section="${name}"]`,config)?.remove();
  }
}

async function loadRealVersion(){
  try{
    const d=await call('/api/version?t='+Date.now());
    const version=String(d.version||'').trim();
    if(!version)return;
    const chip=q('#currentVersionBadge');if(chip)chip.textContent='Recepción v'+version;
    const anchor=q('#historiaDoctorBadge')||q('#connectionBadge');
    if(anchor){let badge=q('#sidebarRealVersion');if(!badge){badge=document.createElement('div');badge.id='sidebarRealVersion';anchor.insertAdjacentElement('afterend',badge)}badge.textContent='Recepción v'+version}
  }catch{}
}

function renderWhatsappTemplates(d={}){
  const host=q('#configWhatsappTemplates');if(!host)return;
  const defs=[['recordatorio_cita','Confirmación de cita'],['cita_agendada','Cita agendada'],['recordatorio_hoy','Recordatorio del día']];
  host.innerHTML=defs.map(([key,label])=>{const x=d.templates?.[key]||{},ok=!!x.approved;return `<div class="config-template-card"><b>${esc(label)}</b><small>${esc(x.name||key)} · ${esc(x.language||'')}</small><span class="config-template-state ${ok?'ready':''}">${ok?'APROBADA':'EN ESPERA'}</span></div>`}).join('');
  const select=q('#waTestTemplate');if(select){let first='';for(const option of select.options){const x=d.templates?.[option.value]||{};option.disabled=!x.approved;if(x.approved&&!first)first=option.value}if(select.selectedOptions[0]?.disabled)select.value=first||'recordatorio_cita'}
}

async function loadWhatsappConsolidated(){
  try{const d=await call('/api/whatsapp/status');renderWhatsappTemplates(d)}catch{}
  if(typeof window.loadWhatsappStatus==='function')await window.loadWhatsappStatus();
  if(typeof window.loadWhatsappCloudStatus==='function')await window.loadWhatsappCloudStatus(false);
}

function waTestResult(text){const el=q('#whatsappTestResult');if(el)el.textContent=text}
async function pollWaCloudTest(){
  if(!waCloudTest)return;
  try{
    const d=await call(`/api/whatsapp/cloud-test/${waCloudTest.id}?token=${encodeURIComponent(waCloudTest.token)}`);
    const extra=d.timestamp?' · '+String(d.timestamp):'';
    waTestResult(`${d.status_label||d.status||'Procesando'}${extra}${d.error?' · '+d.error:''}`);
    if(d.terminal){clearInterval(waPoll);waPoll=null;q('#configFinishWaTest')?.classList.remove('hidden')}
  }catch(e){waTestResult('No se pudo consultar la prueba: '+(e.message||e))}
}
window.sendWhatsappTest=async function(){
  const phone=(q('#waTestPhone')?.value||'').trim(),name=(q('#waTestName')?.value||'Prueba').trim(),date=q('#waTestDate')?.value||'',time=q('#waTestTime')?.value||'',template=q('#waTestTemplate')?.value||'recordatorio_cita',btn=q('#waTestSendBtn');
  if(!phone){alert('Ingresa el número que recibirá la prueba.');return}if(!date||!time){alert('Selecciona fecha y hora.');return}
  if(!confirm(`¿Enviar UNA prueba Cloud a ${phone}?\n\nNo se tocará ningún paciente ni cita real.`))return;
  try{if(btn)btn.disabled=true;waTestResult('Registrando prueba técnica en Neon…');const d=await call('/api/whatsapp/cloud-test',{method:'POST',body:JSON.stringify({phone,name,date,time,template})});waCloudTest={id:d.test_id,token:d.token};q('#configFinishWaTest')?.classList.add('hidden');waTestResult('Solicitud registrada. Esperando al Worker Cloud…');clearInterval(waPoll);waPoll=setInterval(pollWaCloudTest,5000);pollWaCloudTest()}catch(e){waTestResult('❌ '+(e.message||e))}finally{if(btn)btn.disabled=false}
};
window.configFinishWhatsappTest=async function(){if(!waCloudTest)return;try{await call(`/api/whatsapp/cloud-test/${waCloudTest.id}?token=${encodeURIComponent(waCloudTest.token)}`,{method:'DELETE'});waCloudTest=null;clearInterval(waPoll);waPoll=null;q('#configFinishWaTest')?.classList.add('hidden');waTestResult('Prueba finalizada y retirada de la agenda técnica.')}catch(e){alert(e.message||e)}};

function dpField(id,label,value='',type='text',extra=''){return `<label class="${extra.includes('full')?'full':''}"><span>${esc(label)}</span><input id="${id}" type="${type}" value="${esc(value)}" ${extra.replace('full','')}></label>`}
function renderDataphone(d={}){
  dpCache=d;
  const ready=!!d.automatic_charge_ready,pill=q('#configDataphonePill'),summary=q('#configDataphoneSummary'),host=q('#configDataphoneBody');
  if(pill){pill.textContent=ready?'LISTO':'PENDIENTE';pill.classList.toggle('ready',ready)}
  if(summary)summary.textContent=ready?'Credenciales, terminal y contrato técnico completos.':'La estructura está preparada; faltan uno o más datos oficiales de Bendo.';
  if(!host)return;
  host.innerHTML=`<div class="config-dp-grid">${dpField('cfgDpProvider','Proveedor',d.provider||'BENDO')}${dpField('cfgDpModel','Modelo',d.model||'Bendo Smart')}${dpField('cfgDpBase','API base URL',d.api_base_url||'','url','full placeholder="https://..."')}${dpField('cfgDpKey','API key / token','','password',`placeholder="${d.api_key_saved?'Ya guardada · deja vacío para conservarla':'Pendiente'}"`)}${dpField('cfgDpMerchant','Merchant ID',d.merchant_id||'')}${dpField('cfgDpTerminal','Terminal ID',d.terminal_id||'')}</div><details class="config-advanced"><summary>Contrato técnico de Bendo</summary><div class="config-advanced-body"><div class="config-dp-grid">${dpField('cfgDpHealth','Ruta de prueba',d.health_path||'','text','full')}${dpField('cfgDpCreate','Ruta crear cobro',d.create_payment_path||'')}${dpField('cfgDpStatus','Ruta consultar estado',d.status_path_template||'')}${dpField('cfgDpAuthHeader','Header',d.auth_header||'Authorization')}${dpField('cfgDpAuthScheme','Esquema',d.auth_scheme||'Bearer')}${dpField('cfgDpRespId','Campo ID',d.response_id_field||'id')}${dpField('cfgDpRespStatus','Campo estado',d.response_status_field||'status')}${dpField('cfgDpWebhook','Webhook público',d.webhook_public_url||'','url','full')}${dpField('cfgDpWebhookSecret','Webhook secret','','password',`full placeholder="${d.webhook_secret_saved?'Ya guardado · deja vacío para conservarlo':'Opcional'}"`)}<label class="full"><span>Plantilla JSON de creación</span><textarea id="cfgDpTemplate">${esc(d.create_body_template||'')}</textarea></label></div></div></details><div id="configDataphoneDetail" class="desktop-runtime-status">${esc(d.api_key_saved?'Credencial API guardada.':'Aún no hay credencial API guardada.')}</div><div class="actions"><button class="primary-soft" onclick="configSaveDataphone()">Guardar Bendo</button></div>`;
}
window.loadConsolidatedDataphone=async function(){try{renderDataphone(await call('/api/v4506/dataphone/config'))}catch(e){const x=q('#configDataphoneSummary');if(x)x.textContent=e.message||e}};
window.configSaveDataphone=async function(){
  try{const d=dpCache||{};const body={provider:q('#cfgDpProvider')?.value||'BENDO',model:q('#cfgDpModel')?.value||'Bendo Smart',environment:d.environment||'PRODUCCION',api_base_url:q('#cfgDpBase')?.value||'',api_key:q('#cfgDpKey')?.value||null,merchant_id:q('#cfgDpMerchant')?.value||'',terminal_id:q('#cfgDpTerminal')?.value||'',auth_header:q('#cfgDpAuthHeader')?.value||d.auth_header||'Authorization',auth_scheme:q('#cfgDpAuthScheme')?.value||d.auth_scheme||'Bearer',health_path:q('#cfgDpHealth')?.value||'',create_payment_path:q('#cfgDpCreate')?.value||'',status_path_template:q('#cfgDpStatus')?.value||'',create_body_template:q('#cfgDpTemplate')?.value||d.create_body_template||'',response_id_field:q('#cfgDpRespId')?.value||d.response_id_field||'id',response_status_field:q('#cfgDpRespStatus')?.value||d.response_status_field||'status',approved_values:d.approved_values||'APPROVED,COMPLETED,SUCCESS',declined_values:d.declined_values||'DECLINED,FAILED,REJECTED,CANCELLED',webhook_public_url:q('#cfgDpWebhook')?.value||'',webhook_secret:q('#cfgDpWebhookSecret')?.value||null};const out=await call('/api/v4506/dataphone/config',{method:'POST',body:JSON.stringify(body)});renderDataphone(out);alert('Configuración de Bendo guardada en esta PC.')}catch(e){alert(e.message||e)}};
window.configValidateDataphone=async function(){try{const d=await call('/api/v4506/dataphone/validate',{method:'POST',body:'{}'});await window.loadConsolidatedDataphone();const target=q('#configDataphoneDetail')||q('#configDataphoneSummary');if(target)target.textContent=d.message||''}catch(e){alert(e.message||e)}};
window.configTestDataphone=async function(){try{const d=await call('/api/v4506/dataphone/test',{method:'POST',body:'{}'});const target=q('#configDataphoneSummary');if(target)target.textContent=d.message||'Prueba terminada.'}catch(e){alert(e.message||e)}};

function fmtBytes(value){let n=Number(value||0);if(n<1024)return n+' B';if(n<1024*1024)return(n/1024).toFixed(1)+' KB';return(n/(1024*1024)).toFixed(1)+' MB'}
function renderSystem(d={}){
  const host=q('#systemStatusGrid');if(!host)return;
  const local=d.local||{},neon=d.neon||{},printer=d.printer||{},backup=d.backup||{},updater=d.updater||{};
  host.innerHTML=`<div><span>Copia local</span><b>${local.ok?'✓ Lista':'⚠ Revisar'}</b><small>${local.pending_sync??0} cambio(s) pendientes</small></div><div><span>Neon</span><b>${esc(neon.status||'SIN COMPROBAR')}</b><small>${esc(neon.detail||'')}</small></div><div><span>Impresora</span><b>${printer.ok?'✓ '+esc(printer.selected||printer.default||'Lista'):'⚠ Revisar'}</b><small>${printer.available_count??0} detectada(s)</small></div><div><span>Último respaldo</span><b>${backup.ok?'✓ Disponible':'Aún no creado'}</b><small>${backup.count??0} copia(s)</small></div><div><span>Actualizador</span><b>${updater.ok===false?'⚠ Revisar':'✓ Preparado'}</b><small>${esc(updater.latest?'Última: '+updater.latest:'Canal estable')}</small></div><div><span>Temporales</span><b>${Number(d.cleanup?.candidates||0)}</b><small>candidato(s) a limpieza</small></div>`;
}
window.loadConsolidatedSystem=async function(deep=false){try{const d=await call('/api/v4501/system-status?deep='+(deep?'true':'false'));renderSystem(d);const note=q('#configMaintenanceNote');if(note)note.textContent=deep?'Revisión completa terminada.':'Estado local actualizado.';await loadRealVersion()}catch(e){const note=q('#configMaintenanceNote');if(note)note.textContent=e.message||e}};
window.configPrintTest=async function(){try{const d=await call('/api/v4501/printing/test',{method:'POST',body:'{}'});alert('Prueba enviada a '+(d.printer||'la impresora')+'.')}catch(e){alert(e.message||e)}};
window.configCleanupTemps=async function(){if(!confirm('¿Limpiar temporales antiguos y conservar intactos pacientes, bases y respaldos recientes?'))return;try{const d=await call('/api/v4501/maintenance/cleanup',{method:'POST',body:'{}'});alert(`Limpieza terminada. ${d.removed_files||0} archivo(s), ${d.removed_dirs||0} carpeta(s), ${fmtBytes(d.freed_bytes||0)} liberados.`);await window.loadConsolidatedSystem(false)}catch(e){alert(e.message||e)}};
window.configLaunchUpdater=async function(){const status=q('#updateStatus');try{if(status)status.textContent='Abriendo launcher oficial…';let d;try{d=await call('/api/v4483/launch-updater',{method:'POST',body:'{}'})}catch(_e){d=await call('/api/app/restart',{method:'POST',body:'{}'})}if(status)status.textContent=d.message||'Launcher abierto. Si existe una actualización obligatoria, se instalará antes de continuar.'}catch(e){if(status)status.textContent=e.message||e;alert(e.message||e)}};

window.openAzurConfig=function(){
  if(typeof window.show==='function')window.show('config');
  const btn=q('[data-config-tab="facturacion"]');
  window.showConfigTab?.('facturacion',btn);
  const panel=q('#azurConfigPanel');if(panel){panel.open=true;setTimeout(()=>panel.scrollIntoView({behavior:'smooth',block:'start'}),60)}
};
window.openDataphoneConfig=function(){
  if(typeof window.show==='function')window.show('config');
  const btn=q('[data-config-tab="facturacion"]');
  window.showConfigTab?.('facturacion',btn);
  const body=q('#configDataphoneBody');const details=body?.closest('details');if(details){details.open=true;setTimeout(()=>details.scrollIntoView({behavior:'smooth',block:'start'}),60)}
};
window.configOpenAgenda=async function(){
  let btn=q('#cloudAgendaLinks .cloud-single-actions button');
  if(!btn&&typeof window.loadMobileConfigLinks==='function'){await window.loadMobileConfigLinks(false);btn=q('#cloudAgendaLinks .cloud-single-actions button')}
  if(btn)btn.click();
};

const originalShow=window.showConfigTab;
window.showConfigTab=function(tab='general',button=null){
  const out=typeof originalShow==='function'?originalShow(tab,button):undefined;
  cleanLegacyConfigArtifacts();
  if(tab==='agenda')loadWhatsappConsolidated();
  if(tab==='facturacion'){window.loadConsolidatedDataphone();if(typeof window.loadAzurStatus==='function')window.loadAzurStatus()}
  if(tab==='sistema'){window.loadConsolidatedSystem(false);if(typeof window.loadWindowModeInfo==='function')window.loadWindowModeInfo();if(typeof window.loadUpdateInfo==='function')window.loadUpdateInfo()}
  return out;
};

function boot(){
  cleanLegacyConfigArtifacts();
  loadRealVersion();
  const date=q('#waTestDate');if(date&&!date.value){const x=new Date();x.setDate(x.getDate()+1);date.value=x.toISOString().slice(0,10)}
  const phone=q('#waTestPhone');if(phone&&!phone.value){try{phone.value=localStorage.getItem('revelo_wa_test_phone')||''}catch{}}
  phone?.addEventListener('input',()=>{try{localStorage.setItem('revelo_wa_test_phone',phone.value.trim())}catch{}});
  if(!q('#config')?.classList.contains('hidden'))window.showConfigTab('general',q('[data-config-tab="general"]'));
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
