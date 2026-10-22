/* 4.8.47: isolated Azure v2 authorized XML thermal receipt controls. */
(function(){
"use strict";
if(window.__rpPos80UI4847)return;
window.__rpPos80UI4847=true;
var busy=false;
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(k){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[k];});}
function notice(t,title){if(typeof window.rpNotice==="function")window.rpNotice(t,title||"Factura 80 mm");else alert(t);}
function selected(){
  var row=document.querySelector("#billingList .v4842-row.selected");
  if(!row || !row.dataset || !row.dataset.key){alert("Selecciona una factura autorizada en Emitidas.");return null;}
  var groups=typeof billingGroupsCache!=="undefined" && Array.isArray(billingGroupsCache)?billingGroupsCache:[];
  var g=groups.find(function(x){return String(x.patient.id)+"|"+String(x.fecha).slice(0,10)===row.dataset.key;});
  if(!g){alert("No se encuentra la factura seleccionada. Actualiza la lista.");return null;}
  var azur=(g.items||[]).map(function(x){return x.azur;}).find(Boolean);
  var number=(g.items||[]).map(function(x){return x.billing && x.billing.numero_factura;}).find(Boolean) || (azur && azur.numero_factura);
  if(!azur || String(azur.estado||"").toUpperCase()!=="AUTORIZADA" || !number){
    alert("Solo se pueden imprimir facturas autorizadas por SRI y con numeración confirmada.");
    return null;
  }
  return {patient_id:Number(g.patient.id),fecha:String(g.fecha).slice(0,10),numero_factura:String(number)};
}
function fail(e){alert("No se pudo preparar o imprimir el RIDE de 80 mm: "+String(e && e.message || e)+"\n\nLa factura electrónica permanece intacta. Puedes utilizar AZUR como alternativa.");}
window.rpPos80PreviewSelected=async function(){
 if(busy)return;var payload=selected();if(!payload)return;busy=true;
 try{
  var response=await api("/api/azur/readonly/pos80-preview",{method:"POST",body:JSON.stringify(payload)});
  var t=response.ticket||{};
  var detail=(t.servicios||[]).map(function(x){
    return '<tr><td>'+esc(x.cantidad)+'</td><td>'+esc(x.descripcion)+'</td><td>'+esc(x.total)+'</td></tr>'+
      '<tr class="v4854-azur-prices"><td></td><td colspan="2">P.V.P: '+esc(x.unitario)+' &nbsp; Descto: '+esc(x.descuento||'0.00')+'</td></tr>';
  }).join('');
  var extras=(t.adicional||[]).filter(function(x){
    return !/^(tel[eé]fono|celular|correo|correo electr[oó]nico|email|e-mail)$/i.test(String(x.nombre||''));
  }).map(function(x){return '<div>'+esc(x.nombre)+': '+esc(x.valor)+'</div>';}).join('');
  var payments=(t.pagos||[]).map(function(x){
    return '<div>Forma de pago: '+esc(x.tipo==='01'?'SIN UTILIZACIÓN DEL SISTEMA FINANCIERO':'Código '+x.tipo)+'</div>'+
      '<div>Valor: '+esc(x.total)+' · Plazo: '+esc(x.plazo||'0')+' '+esc(x.unidad_tiempo||'')+'</div>';
  }).join('');
  var taxes=(t.impuestos||[]).filter(function(x){return Number(x.valor||0)!==0 && x.codigo!=='3';}).map(function(x){
    return '<div><span>'+esc(x.codigo==='2'?'IVA ('+x.porcentaje+')':'Impuesto '+x.codigo+' ('+x.porcentaje+')')+'</span><b>'+esc(x.valor)+'</b></div>';
  }).join('');
  var ice=(t.impuestos||[]).filter(function(x){return x.codigo==='3';}).reduce(function(n,x){return n+Number(x.valor||0);},0);
  var body='<div class="v4847-preview"><div class="modal-form-heading"><h2>Factura 80 mm · Estilo AZUR</h2>'+
    '<p>Vista previa obtenida del XML AUTORIZADO del SRI. No se ha impreso nada.</p></div>'+
    '<div class="v4847-paper v4851-azur-paper">'+
    '<div class="v4851-azur-head"><b class="v4851-azur-title">FACTURA</b>'+
    '<b>RUC: '+esc(t.ruc)+'</b><strong>'+esc(t.emisor)+'</strong>'+
    (t.nombre_comercial&&t.nombre_comercial!==t.emisor?'<strong>'+esc(t.nombre_comercial)+'</strong>':'')+
    (t.direccion_matriz?'<span>Matriz: '+esc(t.direccion_matriz)+'</span>':'')+
    (t.obligado_contabilidad?'<span>Obligado a llevar contabilidad: '+esc(t.obligado_contabilidad)+'</span>':'')+
    '<span>Fecha emisión: '+esc(t.fecha_emision)+'</span><b>No. '+esc(t.numero)+'</b>'+
    '<span>Ambiente: '+esc(t.ambiente||'PRODUCCION')+'</span>'+
    '<span>Autorización: '+esc(t.autorizacion||t.clave)+'</span>'+
    (t.fecha_autorizacion?'<span>Fecha y Hora Autorización: '+esc(t.fecha_autorizacion)+'</span>':'')+
    '<span>Clave de acceso: '+esc(t.clave)+'</span></div>'+
    '<div class="v4851-azur-client"><div>Razón social / nombres: '+esc(t.cliente)+'</div>'+
    '<div>Identificación: '+esc(t.identificacion)+'</div>'+
    (t.direccion_cliente?'<div>Dirección: '+esc(t.direccion_cliente)+'</div>':'')+
    (t.telefono_cliente?'<div>Teléfono: '+esc(t.telefono_cliente)+'</div>':'')+
    (t.correo_cliente?'<div>Correo: '+esc(t.correo_cliente)+'</div>':'')+'</div>'+
    '<table class="v4851-azur-detail v4854-azur-detail"><thead><tr><th>Cant</th><th>Descripción</th><th>Subtotal</th></tr></thead><tbody>'+detail+'</tbody></table>'+
    '<div class="v4851-azur-totals"><div><span>Total sin impuestos</span><b>'+esc(t.subtotal)+'</b></div>'+
    '<div><span>Descuento</span><b>'+esc(t.total_descuento||'0.00')+'</b></div>'+
    '<div><span>Valor ICE</span><b>'+esc(ice.toFixed(2))+'</b></div>'+
    taxes+(t.propina&&Number(t.propina)?'<div><span>Propina</span><b>'+esc(t.propina)+'</b></div>':'')+
    '<div class="v4851-azur-grand"><span>VALOR TOTAL</span><b>'+esc(t.total)+'</b></div></div>'+
    (extras||payments?'<div class="v4851-azur-add"><b>Información adicional</b>'+extras+payments+'</div>':'')+
    '</div><p class="muted">Impresora: '+esc(response.printer||'No configurada en Windows')+
    '. La impresión utiliza el XML autorizado y conserva exactamente los datos tributarios.</p>'+
    '<div class="actions"><button onclick="closeModal()">Cerrar sin imprimir</button>'+
    '<button class="primary" onclick="closeModal();rpPos80PrintSelected()">Imprimir 80 mm</button></div></div>';
  if(typeof openModal==="function")openModal(body);else notice("La factura está validada, pero no se pudo abrir la vista previa.");
 }catch(e){fail(e);}finally{busy=false;}
};
window.rpPos80PrintSelected=async function(){
 if(busy)return;var payload=selected();if(!payload)return;
 var printerStatus;
 try {printerStatus=await api("/api/printing/status");}
 catch(e){fail(e);return;}
 var printerName=String(printerStatus && printerStatus.selected_printer || "").trim();
 var available=Array.isArray(printerStatus && printerStatus.printers)?printerStatus.printers:[];
 if(!printerStatus || printerStatus.supported===false || !printerName ||
    (available.length && !available.includes(printerName))){
   alert("No hay una impresora disponible para el ticket. Entra en Configuración → Recepción → Recibos e impresora y selecciona tu impresora térmica de 80 mm.");
   return;
 }
 var message="¿IMPRIMIR FACTURA ELECTRONICA EN PAPEL DE 80 MM?\n\nNumero: "+payload.numero_factura+
   "\nImpresora de Windows: "+printerName+
   "\n\nConfirma que este dispositivo tiene papel térmico de 80 mm. No se emitirá otra factura.";
 var yes=typeof window.rpConfirm==="function"?await window.rpConfirm(message,"Impresión térmica AZUR"):window.confirm(message);
 if(!yes)return;busy=true;
 try{
  var execute=function(){return api("/api/azur/readonly/pos80-print",{method:"POST",body:JSON.stringify(payload)});};
  var result=typeof singleFlightMutation==="function"
    ?await singleFlightMutation("azur:pos80:"+payload.numero_factura,execute,"Imprimiendo RIDE 80 mm...")
    :await execute();
  notice((result.message||"Factura enviada a impresión.")+"\nImpresora: "+(result.printer||"Windows"),"Factura impresa");
 }catch(e){fail(e);}finally{busy=false;}
};
})();
