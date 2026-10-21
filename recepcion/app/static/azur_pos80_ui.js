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
  var items=(t.servicios||[]).map(function(x){return '<div class="v4847-preview-line"><span>'+esc(x.descripcion)+'<small>'+esc(x.cantidad)+' x '+esc(x.unitario)+'</small></span><b>'+esc(x.total)+'</b></div>';}).join("");
  var taxes=(t.impuestos||[]).map(function(x){return '<div class="v4847-preview-line"><span>Impuesto '+esc(x.codigo)+' ('+esc(x.porcentaje)+')</span><b>'+esc(x.valor)+'</b></div>';}).join("");
  var body='<div class="v4847-preview"><div class="modal-form-heading"><h2>Vista previa de factura 80 mm</h2><p>Obtenida del XML AUTORIZADO del SRI. No se ha impreso nada.</p></div>'+
    '<div class="v4847-paper"><strong>'+esc(t.emisor)+'</strong><span>RUC '+esc(t.ruc)+'</span><hr>'+
    '<b>FACTURA ELECTRONICA</b><b>'+esc(t.numero)+'</b><span>AUTORIZADA POR SRI</span><hr>'+
    '<span>Fecha '+esc(t.fecha_emision)+'</span><span>Cliente '+esc(t.cliente)+'</span><span>ID '+esc(t.identificacion)+'</span><hr>'+
    items+'<hr><div class="v4847-preview-line"><span>Subtotal</span><b>'+esc(t.subtotal)+'</b></div>'+
    taxes+'<div class="v4847-preview-total">TOTAL '+esc(t.total)+'</div><hr>'+
    '<small>CLAVE DE ACCESO</small><code>'+esc(t.clave)+'</code>'+
    '<small>Representacion impresa desde XML SRI</small></div>'+
    '<p class="muted">Impresora: '+esc(response.printer||"No configurada en Windows")+
      (response.printer_source?' · '+esc(response.printer_source):'')+
      '. La impresion real incluye campos adicionales del XML autorizado. Puede diferir del POS del portal AZUR.</p>'+
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
