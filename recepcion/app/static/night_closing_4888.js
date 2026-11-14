/* Recepción 4.8.88: cierre fiscal controlado; inactivo hasta opt-in. */
;(()=>{
  'use strict';
  if(window.__rpNightClose4888)return;
  window.__rpNightClose4888=true;
  const css=document.createElement('style');
  css.textContent='.rp-night-close{margin:12px 0 16px;padding:15px 17px;border:1px solid #dce8ec;background:#f8fcfd;border-radius:16px;color:#273e52}' +
    '.rp-night-close-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}' +
    '.rp-night-close h3{margin:0;font-size:15px;font-weight:900}.rp-night-close small,.rp-night-close p{display:block;font-size:11px;color:#607487;line-height:1.5}' +
    '.rp-night-close p{margin:6px 0 10px}.rp-night-close-status{border-radius:12px;padding:9px 11px;background:#ebf3f8;font-weight:750;font-size:11px}' +
    '.rp-night-close-status.active{background:#fff0d3;color:#86591a}.rp-night-close-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}' +
    '.rp-night-close-actions button{min-height:38px;border-radius:9px;padding:8px 12px;font-weight:850;border:1px solid #b9cdd9;background:white;color:#2c587a;cursor:pointer}' +
    '.rp-night-close-actions button.danger{background:#fff4ee;border-color:#edbe9f;color:#8d4828}.rp-night-close-actions button:disabled{opacity:.5;cursor:default}';
  document.head.appendChild(css);
  let panel=null,busy=false;
  async function req(url,options={}){
    const response=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(data.detail||'No se pudo consultar el cierre fiscal');
    return data;
  }
  function setText(id,value){const target=panel?.querySelector('#'+id);if(target)target.textContent=String(value)}
  let financePanel=null,financeBusy=false,financeDate='';
  function fmtCents(cents){
    const value=Number(cents||0)/100;
    return Number.isFinite(value)
      ?new Intl.NumberFormat('es-EC',{style:'currency',currency:'USD'}).format(value)
      :'—';
  }
  function financialRow(name,data){
    const row=document.createElement('div');row.className='rp-night-finance-row';
    const title=document.createElement('strong');title.textContent=name;
    const subtotal=document.createElement('b');
    subtotal.textContent=fmtCents(data.authorized_value_cents);
    const detail=document.createElement('small');
    detail.textContent=(data.count||0)+' comprobante(s) · '+(data.authorized||0)+
      ' autorizados SRI · '+(data.in_process||0)+' en proceso · '+
      (data.needs_review||0)+' para revisión';
    row.append(title,subtotal,detail);
    if(data.in_process){
      const pending=document.createElement('small');
      pending.textContent='En proceso, sin sumar al autorizado: '+fmtCents(data.in_process_value_cents);
      row.appendChild(pending);
    }
    if(data.unknown_amount){
      const notice=document.createElement('small');
      notice.textContent=data.unknown_amount+' comprobante(s) sin importe verificable en Recepción';
      row.appendChild(notice);
    }
    return row;
  }
  function mountFinancial(){
    const section=document.getElementById('facturacion');
    if(!section||financePanel)return;
    financePanel=document.createElement('section');
    financePanel.id='rpNightFinancialReport';financePanel.className='rp-night-finance';
    financePanel.hidden=true;
    financePanel.innerHTML='<div class="rp-night-finance-head"><div><small>CIERRE FISCAL · MIÉRCOLES A SÁBADO · 19:00 ECUADOR</small><h3>Informe financiero diario</h3></div><button type="button" id="rpFinanceRefresh">↻ Actualizar cifras</button></div>'+
      '<p id="rpFinancePeriod"></p><div id="rpFinanceRows" class="rp-night-finance-grid"></div>'+
      '<p id="rpFinanceSummary" class="rp-night-finance-total"></p>'+
      '<small id="rpFinanceFoot"></small>';
    const anchor=document.getElementById('billingSummary');
    section.insertBefore(financePanel,anchor||section.firstChild);
    financePanel.querySelector('#rpFinanceRefresh').addEventListener('click',()=>refreshFinancial(true));
    new MutationObserver(()=>{
      if(!section.classList.contains('hidden'))refreshFinancial(false);
    }).observe(section,{attributes:true,attributeFilter:['class']});
    // Abrir Inicio no debe despertar Neon solo por tener un reporte pendiente.
    if(!section.classList.contains('hidden'))refreshFinancial(false);
  }
  async function refreshFinancial(force){
    if(financeBusy||!financePanel)return;
    financeBusy=true;
    try{
      const state=await req('/api/night-close/status');
      if(!state.last_date||state.last_result?.status==='started'){
        financePanel.hidden=true;financeDate='';return;
      }
      if(!force&&financeDate===state.last_date)return;
      financePanel.hidden=false;
      financePanel.querySelector('#rpFinancePeriod').textContent='Verificando facturas del cierre…';
      const r=await req('/api/night-close/financial-report');
      if(!r.available){financePanel.hidden=true;financeDate='';return;}
      financeDate=r.date;
      financePanel.querySelector('#rpFinancePeriod').textContent=
        'Facturas registradas el '+r.date+' (hora de Ecuador). Disponible durante el cierre y el día siguiente, aunque sea domingo.';
      const container=financePanel.querySelector('#rpFinanceRows');
      container.replaceChildren(financialRow('Emitidas manualmente',r.financial.manual),
                                financialRow('Cierre automático de las 19:00',r.financial.automatic));
      const total=r.financial.total;
      financePanel.querySelector('#rpFinanceSummary').textContent=
        'TOTAL AUTORIZADO POR SRI: '+fmtCents(total.authorized_value_cents)+
        ' · '+total.authorized+' factura(s) · '+total.in_process+
        ' en proceso · '+total.needs_review+' requieren revisión.';
      financePanel.querySelector('#rpFinanceFoot').textContent=
        'Valores basados en atenciones vinculadas a facturas AZUR de Recepción; no reemplazan el XML tributario. '+
        'No incluye facturas creadas fuera de Recepción. Las pendientes no se cuentan como autorizadas. '+
        'Estado consultado: '+r.generated_at+'.';
    }catch(err){
      financeDate='';
      financePanel.hidden=false;
      financePanel.querySelector('#rpFinancePeriod').textContent=
        'No se pudo verificar el informe: '+String(err.message||err);
      financePanel.querySelector('#rpFinanceRows').replaceChildren();
      financePanel.querySelector('#rpFinanceSummary').textContent='Sin cifras no verificadas.';
      financePanel.querySelector('#rpFinanceFoot').textContent='Pulsa «Actualizar cifras» cuando vuelva la conexión.';
    }finally{financeBusy=false;}
  }
  function mount(){
    mountFinancial();
    if(panel?.isConnected)return;
    const slot=document.getElementById('nightFiscalConfigSlot');
    const disclosure=document.getElementById('nightFiscalSettings');
    if(!slot||!disclosure)return;
    panel=document.createElement('div');
    panel.className='rp-night-close';
    panel.innerHTML='<div class="rp-night-close-head"><h3>🌙 Cierre fiscal inteligente · 19:00</h3><small>Ecuador · uso opcional</small></div>' +
      '<p>Al activarlo, Recepción intentará emitir <strong>solo las facturas elegibles del día, de miércoles a sábado</strong>, desde las 19:00 cuando esté inactiva. No reenvía intentos con resultado incierto. Debes dejar la PC y Recepción encendidas.</p>' +
      '<div class="rp-night-close-status" id="rpNightState">Consultando configuración…</div>' +
      '<small id="rpNightPending"></small><small id="rpNightLast"></small>' +
      '<small id="rpNightOpenPolicy">Recepción e Historia Clínica permanecerán abiertas toda la noche.</small>' +
      '<div class="rp-night-close-actions"><button id="rpNightToggle" type="button" disabled>Configurando…</button><button id="rpNightRefresh" type="button">↻ Revisar estado</button></div>' +
      '<small>Solo el administrador puede habilitar la emisión real ante AZUR/SRI. Antes de activarlo, verifica que los datos de facturación alternativa estén guardados en Preferencias y que la forma de pago predeterminada de AZUR sea correcta. Se omiten revisiones gratuitas, grupos incompletos y envíos anteriores. No hay cierre automático de Recepción, Historia Clínica, Windows o el servidor LAN.</small>';
    slot.appendChild(panel);
    panel.querySelector('#rpNightRefresh')?.addEventListener('click',refresh);
    panel.querySelector('#rpNightToggle')?.addEventListener('click',toggle);
    disclosure.addEventListener('toggle',()=>{
      if(disclosure.open && !document.getElementById('config')?.classList.contains('hidden'))refresh();
    });
    if(disclosure.open && !document.getElementById('config')?.classList.contains('hidden'))refresh();
  }
  async function refresh(){
    if(!panel||busy)return;
    try{
      const d=await req('/api/night-close/status');
      panel.dataset.enabled=d.enabled?'1':'0';
      setText('rpNightOpenPolicy',d.programs_remain_open===true && d.auto_close_programs===false
        ? '✓ Recepción e Historia Clínica permanecen abiertas. El descanso no apaga ni cierra programas.'
        : '⚠ No se pudo comprobar la política de no cerrar programas; revisa la actualización.');
      panel.querySelector('#rpNightState')?.classList.toggle('active',!!d.enabled);
      setText('rpNightState',d.enabled?'ACTIVADO · miércoles a sábado, desde las 19:00':'DESACTIVADO · ninguna emisión automática');
      setText('rpNightPending','Hoy: '+(d.local_groups_to_review||0)+' grupo(s) por revisar · '+(d.pending_local_sync||0)+' cambio(s) pendientes de sincronización');
      const run=d.last_result||{};
      setText('rpNightLast',run.date?'Último cierre '+run.date+': '+(run.sent||0)+' enviados a AZUR, '+(run.skipped||0)+' omitidos, '+(run.uncertain||0)+' para revisión ('+(run.status||'—')+').':'No se ha ejecutado ningún cierre automático.');
      const btn=panel.querySelector('#rpNightToggle');
      if(btn){btn.disabled=false;btn.textContent=d.enabled?'Desactivar emisión nocturna':'Activar emisión nocturna';btn.classList.toggle('danger',!!d.enabled)}
    }catch(e){setText('rpNightState','No se pudo consultar el cierre fiscal: '+e.message)}
  }
  async function toggle(){
    if(!panel||busy)return;
    const enabled=panel.dataset.enabled==='1';
    let confirmation='';
    if(!enabled){
      if(!window.confirm('Esto habilitará la EMISIÓN REAL automática de facturas electrónicas hacia AZUR/SRI, sin pedir permiso por cada factura.\n\nSolo se procesan las facturas elegibles del mismo día, con Recepción abierta y sin actividad. Se usa el receptor guardado y la forma de pago de AZUR configurada; compruébalos antes de activar. No se reenvían intentos inciertos.\n\n¿Deseas habilitarlo?'))return;
      confirmation=window.prompt('Para activarlo escribe exactamente: FACTURAR AUTOMATICAMENTE')||'';
      if(confirmation.trim().toUpperCase()!=='FACTURAR AUTOMATICAMENTE'){
        window.alert('No se activó. La frase de confirmación no coincide.');
        return;
      }
    }
    busy=true;
    const btn=panel.querySelector('#rpNightToggle');
    if(btn)btn.disabled=true;
    try{
      await req('/api/night-close/config',{method:'POST',body:JSON.stringify({enabled:!enabled,confirmation})});
      panel.dataset.enabled=enabled?'0':'1';
      window.alert(enabled?'La emisión automática quedó desactivada.':'Emisión fiscal nocturna activada. Recepción debe permanecer abierta.');
    }catch(e){window.alert(e.message)}
    finally{busy=false;await refresh()}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
  else mount();
  setInterval(()=>{
    if(financePanel&&!document.getElementById('facturacion')?.classList.contains('hidden'))refreshFinancial(false);
    if(panel&&document.getElementById('nightFiscalSettings')?.open
      &&!document.getElementById('config')?.classList.contains('hidden')
      &&!document.querySelector('[data-config-section="facturacion"]')?.classList.contains('hidden'))refresh();
  },120000);
})();