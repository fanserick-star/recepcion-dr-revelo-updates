/* Recepción 4.8.42 — Facturación avanzada. Solo interfaz: sin escritura fiscal automática. */
(function () {
  'use strict';
  if (window.__rpBilling4842) return;
  window.__rpBilling4842 = true;
  var selectedKey = '';
  var query = '';
  var installing = false;
  var renderCard = null;
  var initialLoad = null;
  var bulkBusy = false;
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (x) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x];
    });
  }
  function norm(value) {
    return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  }
  function groupKey(g) {
    return String(Number(g.patient.id)) + '|' + String(g.fecha).slice(0, 10);
  }
  function azur(g) {
    return (g.items || []).map(function (item) {return item.azur;}).find(Boolean) || null;
  }
  function invoice(g) {
    var fromLines = (g.items || []).map(function (item) {return item.billing && item.billing.numero_factura;}).find(Boolean);
    return fromLines || (azur(g) && azur(g).numero_factura) || '';
  }
  function status(g) {
    var emission = azur(g), state = norm(emission && emission.estado).toUpperCase();
    if (state === 'AUTORIZADA') return {name:'Autorizada por SRI',tone:'ok'};
    if (state === 'RECHAZADA' || state === 'DEVUELTA') return {name:'Requiere revisión',tone:'bad'};
    if (state === 'EN_PROCESO' || state === 'CONSULTADA') return {name:'En proceso SRI',tone:'wait'};
    var states = (g.items || []).map(function (item) {return String((item.billing || {}).estado || '').toUpperCase();});
    if (states.indexOf('EMITIDA') >= 0) return {name:'Emitida · verificar SRI',tone:'wait'};
    return {name:'Por emitir',tone:'pending'};
  }
  function pending(g) {
    return (g.items || []).some(function (item) {return ['PENDIENTE','APROBADA'].indexOf(String((item.billing || {}).estado || '').toUpperCase()) >= 0;});
  }
  function groups() {
    try {return typeof billingGroupsCache !== 'undefined' && Array.isArray(billingGroupsCache) ? billingGroupsCache : [];} catch (e) {return [];}
  }
  function active() {return String(document.querySelector('#bEstado')?.value || 'PENDIENTE').toUpperCase();}
  function renderRow(g) {
    var key = groupKey(g), st = status(g), num = invoice(g), total = typeof billingTotal === 'function' ? billingTotal(g) : 0;
    var name = String(g.patient.nombre || 'PACIENTE');
    var id = String(g.patient.cedula || '');
    var service = (g.items || []).map(function (x) {return x.visit && (x.visit.procedimiento || 'Consulta médica');}).filter(Boolean).join(' · ');
    var amount = typeof money === 'function' ? money(total) : '$' + Number(total || 0).toFixed(2);
    var date = typeof fmtDate === 'function' ? fmtDate(g.fecha) : g.fecha;
    var selected = key === selectedKey ? ' selected' : '';
    return '<button type="button" class="v4842-row' + selected + '" data-key="' + esc(key) +
      '" data-search="' + esc(norm([name,id,num,service,g.fecha].join(' '))) +
      '" onclick="rpBillingSelect(' + Number(g.patient.id) + ',\'' + esc(g.fecha) + '\')">' +
      '<span class="v4842-row-main"><b>' + esc(name) + '</b><small>' + esc(date) + ' · ' + esc(id || 'Sin identificación') + '</small>' +
      '<small class="v4842-service">' + esc(service || 'Atención médica') + '</small></span>' +
      '<span class="v4842-row-end"><b>' + esc(amount) + '</b><small class="v4842-pill ' + st.tone + '">' + esc(st.name) + '</small></span>' +
      '<span class="v4842-chevron" aria-hidden="true">›</span></button>';
  }
  renderCard = renderRow;
  function blankDetail(text) {
    var target = document.getElementById('v4842Detail');
    if (target) target.innerHTML = '<div class="v4842-empty-detail"><span class="v4842-empty-icon" aria-hidden="true">▤</span><h3>Detalle de factura</h3><p>' +
      esc(text || 'Selecciona un paciente para consultar su facturación.') + '</p></div>';
  }
  function renderDetail(g) {
    var target = document.getElementById('v4842Detail');
    if (!target) return;
    var st = status(g), a = azur(g), number = invoice(g), amt = typeof money === 'function' ? money(billingTotal(g)) : '$' + Number(billingTotal(g)).toFixed(2);
    var alt = typeof billingRecipientDraft === 'function' ? billingRecipientDraft(g.patient.id,g.fecha) : null;
    var recipient = alt && alt.alternate ? (alt.nombre || 'Otros datos') : (g.patient.nombre || 'Paciente');
    var id = alt && alt.alternate ? alt.identificacion : g.patient.cedula;
    var lines = (g.items || []).map(function (x) {
      var v = x.visit || {};
      return '<div class="v4842-line"><span>' + esc(v.procedimiento || 'Consulta médica') + '</span><b>' + esc(typeof money === 'function' ? money(v.valor) : '$' + Number(v.valor || 0).toFixed(2)) + '</b></div>';
    }).join('');
    var canEmit = pending(g) && !(a && a.has_clave_acceso);
    var actions = '';
    if (canEmit) actions = '<button type="button" class="primary v4842-primary" onclick="rpBillingReview()">Revisar antes de emitir →</button>' +
      '<button type="button" class="v4842-secondary" onclick="openBillingRecipientEditor(' + Number(g.patient.id) + ',\'' + esc(g.fecha) + '\')">Facturar con otros datos</button>';
    else if (a && a.has_clave_acceso && st.tone !== 'ok') actions = '<button type="button" class="primary v4842-primary" onclick="checkAzurInvoiceStatus(' + Number(g.patient.id) + ',\'' + esc(g.fecha) + '\')">Consultar estado AZUR/SRI</button>';
    else actions = '<button type="button" class="v4842-secondary" onclick="copyBillingData(' + Number(g.patient.id) + ',\'' + esc(g.fecha) + '\')">Ver datos del comprobante</button>';
    target.innerHTML =
      '<div class="v4842-detail-title"><small>DETALLE DE FACTURACIÓN</small><h3>' + esc(g.patient.nombre) + '</h3>' +
      '<span class="v4842-pill ' + st.tone + '">' + esc(st.name) + '</span></div>' +
      '<div class="v4842-detail-block"><small>FECHA DE ATENCIÓN</small><b>' + esc(typeof fmtDate === 'function' ? fmtDate(g.fecha) : g.fecha) + '</b></div>' +
      '<div class="v4842-detail-block"><small>FACTURAR A</small><b>' + esc(recipient) + '</b><span>' + esc(id || 'Sin identificación') + '</span></div>' +
      '<div class="v4842-detail-block"><small>SERVICIOS</small>' + lines + '</div>' +
      '<div class="v4842-detail-total"><span>Total</span><strong>' + esc(amt) + '</strong></div>' +
      (number ? '<div class="v4842-detail-block"><small>NÚMERO DE FACTURA</small><b>' + esc(number) + '</b></div>' : '') +
      '<div class="v4842-detail-actions">' + actions + '</div>' +
      (st.tone === 'wait' ? '<p class="v4842-detail-tip">Una factura enviada no equivale a una factura autorizada por el SRI. No vuelvas a enviarla sin verificar el estado.</p>' : '');
  }
  window.rpBillingSelect = function (patientId, fecha) {
    selectedKey = String(Number(patientId)) + '|' + String(fecha).slice(0, 10);
    document.querySelectorAll('#billingList .v4842-row').forEach(function (row) {
      row.classList.toggle('selected',row.dataset.key === selectedKey);
    });
    var group = groups().find(function (g) {return groupKey(g) === selectedKey;});
    if (group) renderDetail(group);
    else blankDetail('Esta factura ya no está en la lista. Actualiza para consultar su estado.');
  };
  function filterRows() {
    var shown = 0;
    document.querySelectorAll('#billingList .v4842-row').forEach(function (row) {
      var visible = !query || String(row.dataset.search || '').indexOf(query) >= 0;
      row.hidden = !visible;
      if (visible) shown++;
    });
    var counter = document.querySelector('#v4842Visible');
    if (counter) counter.textContent = shown + (shown === 1 ? ' resultado visible' : ' resultados visibles');
  }
  window.rpBillingExportVisible = function () {
    var rows = [['Paciente','Identificación','Fecha','Número de factura','Estado','Total']];
    groups().forEach(function (g) {
      var key = groupKey(g), element = Array.from(document.querySelectorAll('#billingList .v4842-row')).find(function (x) {return x.dataset.key === key;});
      if (!element || element.hidden) return;
      rows.push([g.patient.nombre,g.patient.cedula || '',g.fecha,invoice(g),status(g).name,Number(billingTotal(g)).toFixed(2)]);
    });
    function csvCell(x) {
      var value = String(x == null ? '' : x);
      if (/^[\s]*[=+\-@]/.test(value)) value = "'" + value;
      return '"' + value.replace(/"/g,'""') + '"';
    }
    var csv = '\ufeff' + rows.map(function (r) {return r.map(csvCell).join(';');}).join('\r\n');
    var url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
    var a = document.createElement('a');a.href = url;a.download = 'facturacion-vista-' + new Date().toISOString().slice(0,10) + '.csv';a.click();
    setTimeout(function () {URL.revokeObjectURL(url);}, 1000);
  };
  function inject() {
    var section = document.getElementById('facturacion'), list = document.getElementById('billingList');
    if (!section || !list) return;
    section.classList.add('v4842-advanced-billing');
    if (!document.getElementById('v4842Bar')) {
      var bar = document.createElement('div');bar.id='v4842Bar';bar.className='v4842-bar';
      bar.innerHTML = '<div><b>Centro de facturación</b><small>Revisa, emite y consulta comprobantes sin salir de Recepción</small></div>' +
        '<div class="v4842-bar-actions"><label class="v4842-search"><span aria-hidden="true">⌕</span><input id="v4842Search" type="search" placeholder="Buscar en la lista visible" aria-label="Buscar facturas visibles"></label>' +
        '<button type="button" id="v4842Reload">↻ Actualizar</button><button type="button" id="v4842Csv">Exportar vista CSV</button></div>';
      section.insertBefore(bar,document.getElementById('billingSummary'));
      document.getElementById('v4842Search').addEventListener('input',function (e) {query=norm(e.target.value);filterRows();});
      document.getElementById('v4842Reload').addEventListener('click',function () {window.loadBilling();});
      document.getElementById('v4842Csv').addEventListener('click',window.rpBillingExportVisible);
    }
    if (!document.getElementById('v4842Workspace')) {
      var work = document.createElement('div');work.id='v4842Workspace';work.className='v4842-workspace';
      work.innerHTML='<div id="v4842ListArea" class="v4842-list-area"><div class="v4842-list-label"><b>Comprobantes</b><small id="v4842Visible">0 resultados visibles</small></div></div><aside id="v4842Detail" class="v4842-detail"></aside>';
      list.parentNode.insertBefore(work,list);
      work.querySelector('#v4842ListArea').appendChild(list);
      blankDetail();
    }
  }
  function afterLoad() {
    inject();
    var rows = document.querySelectorAll('#billingList .v4842-row');
    if (!rows.length) {
      var list = document.getElementById('billingList');
      if (list && !list.querySelector('.err') && !list.querySelector('.issued-billing-toolbar')) {
        list.innerHTML='<div class="v4842-empty-list"><b>No hay facturas en esta sección</b><span>Selecciona otra categoría o actualiza cuando registres una nueva atención.</span></div>';
      }
    }
    if (rows.length) {
      if (!groups().some(function (g) {return groupKey(g) === selectedKey;})) selectedKey = groupKey(groups()[0]);
      window.rpBillingSelect.apply(null, selectedKey.split('|'));
    } else blankDetail();
    var search = document.getElementById('v4842Search');if(search && search.value !== query)search.value=query;
    var hint = document.getElementById('v4842Bar');
    if(hint)hint.dataset.mode = active();
    filterRows();
  }
  window.rpBillingReview = async function () {
    var parts = selectedKey.split('|'), id = Number(parts[0]), fecha = parts[1];
    var group=groups().find(function (g) {return groupKey(g) === selectedKey;});
    if (!group || !pending(group)) return;
    var target=document.getElementById('v4842Detail');
    if (!target) return;
    var raw = target.innerHTML;
    target.innerHTML='<div class="v4842-progress" role="status">Validando datos de la factura…</div>';
    try {
      var data = await api('/api/billing/azur/preview',{method:'POST',body:JSON.stringify(Object.assign({patient_id:id,fecha:fecha},billingRecipientPayload(id,fecha)))});
      if(data.already_sent) throw new Error('Ya existe un envío a AZUR. Consulta el estado; nunca se enviará una segunda vez.');
      if(!data.configured || !data.live_enabled) throw new Error('AZUR no está listo para emisión real. Revisa su configuración.');
      var p=data.payload || {}, buyer=p.comprador || {};
      var items=(p.items || []).map(function (x) {return '<div class="v4842-line"><span>' + esc(x.descripcion) + '</span><b>' + esc(typeof money==='function'?money(x.precio_unitario):Number(x.precio_unitario).toFixed(2)) + '</b></div>';}).join('');
      var expected=(p.pagos || []).reduce(function (sum,x) {return sum+Number(x.total || 0);},0);
      target.innerHTML='<div class="v4842-detail-title"><small>REVISIÓN FINAL</small><h3>Confirmar factura real</h3></div>' +
        '<div class="v4842-detail-block"><small>FACTURAR A</small><b>' + esc(buyer.razon_social) + '</b><span>' + esc(buyer.identificacion) + '</span><span>Correo: ' + esc(buyer.correo || 'Opcional, no registrado') + '</span></div>' +
        '<div class="v4842-detail-block"><small>DETALLE</small>' + items + '</div>' +
        '<div class="v4842-detail-total"><span>Total a emitir</span><strong>' + esc(typeof money==='function'?money(expected):expected.toFixed(2)) + '</strong></div>' +
        '<p class="v4842-detail-tip">Esta operación emite una factura REAL en AZUR. Después se debe verificar su autorización en el SRI.</p>' +
        '<div class="v4842-detail-actions"><button type="button" class="primary v4842-primary" id="v4842Confirm">Confirmar emisión real</button><button type="button" class="v4842-secondary" id="v4842Back">Volver a revisar</button></div>';
      document.getElementById('v4842Confirm').addEventListener('click',window.rpBillingConfirm);
      document.getElementById('v4842Back').addEventListener('click',function(){renderDetail(group);});
    } catch(err) {
      target.innerHTML=raw+'<p class="v4842-error" role="alert">'+esc(err && err.message || err)+'</p>';
    }
  };
  window.rpBillingConfirm = async function () {
    var parts=selectedKey.split('|'),id=Number(parts[0]),fecha=parts[1],button=document.getElementById('v4842Confirm');
    if (!button || button.disabled) return;
    var yes = typeof window.rpConfirm === 'function' ?
      await window.rpConfirm('¿Confirmas la emisión REAL de esta factura en AZUR? Revisa el receptor, los servicios y el total.','Emitir factura') :
      window.confirm('¿Emitir esta factura REAL en AZUR?');
    if (!yes) return;
    button.disabled=true;button.textContent='Enviando a AZUR…';
    try {
      await singleFlightMutation('billing:approve:'+id+':'+fecha,function() {
        return api('/api/billing/approve',{method:'POST',body:JSON.stringify(Object.assign({patient_id:id,fecha:fecha},billingRecipientPayload(id,fecha)))});
      },'Emitiendo…');
      await window.loadBilling();if(typeof refreshPendingBadges==='function')refreshPendingBadges();
      if(typeof window.rpNotice==='function')window.rpNotice('Factura enviada a AZUR. Consulta su estado hasta que el SRI confirme la autorización.','Envío realizado');
    } catch(err) {
      button.textContent='No se pudo confirmar el envío';
      var target=document.getElementById('v4842Detail');
      if(target)target.insertAdjacentHTML('beforeend','<p class="v4842-error" role="alert">'+esc((err && err.message) || err)+'<br>Si hubo un fallo de conexión, verifica en AZUR antes de intentar nuevamente.</p>');
    }
  };
  function install() {
    if(installing || typeof window.billingCardHtml !== 'function' || typeof window.loadBilling !== 'function')return;
    installing = true;
    window.billingCardHtml = renderCard;
    window.emitAllPendingInvoices = async function () {
      if (bulkBusy) return;
      bulkBusy = true;
      try {
        var pre = await api('/api/billing/azur/batch-preview');
        if (!pre.unlocked) {
          alert('Por seguridad, la emisión masiva requiere al menos una factura AUTORIZADA por el SRI. Primero comprueba una emisión individual.');
          return;
        }
        var ready = pre.ready || [], skipped = pre.skipped || [];
        if (!ready.length) {alert('No hay facturas completas listas para emitir. Omitidas: ' + skipped.length);return;}
        var examples = ready.slice(0,5).map(function(x) {return String(x.nombre || 'Paciente') + ' · $' + Number(x.total || 0).toFixed(2);}).join('\n');
        var message = '¿EMITIR ' + ready.length + ' FACTURAS REALES EN AZUR?\n\n' + examples +
          '\n\nOmitidas: ' + skipped.length + '. Comprueba los destinatarios y valores antes de confirmar.';
        var yes = typeof window.rpConfirm === 'function' ? await window.rpConfirm(message, 'Emisión por lotes') : window.confirm(message);
        if (!yes) return;
        var result = await singleFlightMutation('billing:azur:emit-all',function () {
          return api('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}'});
        },'Emitiendo facturas…');
        var counts = result.counts || {};
        var info = 'Enviadas a AZUR: ' + Number(counts.sent || 0) + ', omitidas: ' +
          Number(counts.skipped || 0) + ', fallidas: ' + Number(counts.failed || 0) +
          '. Consulta posteriormente las autorizaciones del SRI.';
        if (typeof window.rpNotice === 'function') window.rpNotice(info,'Facturación');else alert(info);
        await window.loadBilling();
        if (typeof refreshPendingBadges === 'function') refreshPendingBadges();
      } catch(error) {
        var msg = String(error && error.message || error);
        if(typeof window.rpNotice === 'function')window.rpNotice(msg,'Facturación');else alert(msg);
      } finally {bulkBusy = false;}
    };
    if(window.loadBilling.__v4842 !== true) {
      var old = window.loadBilling;
      var wrapped=async function () {var response=await old.apply(this,arguments);afterLoad();return response;};
      wrapped.__v4842=true;
      window.loadBilling=wrapped;
    }
    inject();
    if (document.querySelector('#billingList .billing-card')) window.loadBilling();
    else afterLoad();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){setTimeout(install,70);},{once:true});
  else setTimeout(install,70);
  setTimeout(install,450);
})();
