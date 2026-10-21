import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const bill=fs.readFileSync('recepcion/app/static/billing_advanced.js','utf8');
const src=fs.readFileSync('recepcion/app/static/azur_pos80_ui.js','utf8');
const html=fs.readFileSync('recepcion/app/static/index.html','utf8');
assert.match(html,/azur_pos80_ui\.js\?v=4\.8\.4[78]/);
assert.ok(html.indexOf('billing_advanced.js?v=4.8.48')<html.indexOf('azur_pos80_ui.js?v=4.8.48'));
assert.match(bill,/rpPos80PrintSelected/);
assert.match(bill,/rpPos80PreviewSelected/);
assert.doesNotMatch(src,/\/api\/billing\/(approve|emit)/);
assert.doesNotMatch(src,/setInterval\s*\(/);

const calls=[],dialog=[],notices=[],alerts=[];
let selectedKey='7|2026-10-21';
const authorized={
 patient:{id:8,nombre:'PACIENTE DEMO'},
 fecha:'2026-10-21',
 items:[{billing:{estado:'EMITIDA',numero_factura:'001-001-000000123'},
         azur:{estado:'AUTORIZADA',has_clave_acceso:true,numero_factura:'001-001-000000123'}}]
};
const pending={
 patient:{id:7,nombre:'PENDIENTE'},fecha:'2026-10-21',
 items:[{billing:{estado:'PENDIENTE'}}]
};
const ticket={
 emisor:'EMISOR FICTICIO',ruc:'0999999999001',numero:'001-001-000000123',
 fecha_emision:'21/10/2026',cliente:'CLIENTE DEMO',identificacion:'0102030405',
 subtotal:'40.00',total:'40.00',clave:'1'.repeat(49),
 servicios:[{descripcion:'CONSULTA',cantidad:'1.00',unitario:'40.00',total:'40.00'}],
 impuestos:[{codigo:'2',porcentaje:'0',valor:'0.00'}]
};
const context={
 window:{rpConfirm:async()=>true,rpNotice:(message,title)=>notices.push({message,title})},
 document:{querySelector:s=>s==='#billingList .v4842-row.selected'?{dataset:{key:selectedKey}}:null},
 billingGroupsCache:[pending,authorized],
 api:async(url,options={})=>{
  calls.push({url,options});
  if(url==='/api/printing/status')return {supported:true,selected_printer:'IMPRESORA DEMO',default_printer:'IMPRESORA DEMO',printers:['IMPRESORA DEMO']};
  if(url.endsWith('/pos80-preview'))return {ok:true,printed:false,ticket};
  if(url.endsWith('/pos80-print'))return {ok:true,printed:true,numero_factura:ticket.numero,printer:'IMPRESORA DEMO'};
  throw Error('Unexpected endpoint '+url);
 },
 singleFlightMutation:async(_key,fn)=>fn(),
 openModal:html=>dialog.push(html),
 alert:message=>alerts.push(message),
 console
};
vm.runInNewContext(src,context,{filename:'azur_pos80_ui.js'});
assert.equal(typeof context.window.rpPos80PreviewSelected,'function');
assert.equal(typeof context.window.rpPos80PrintSelected,'function');
await context.window.rpPos80PrintSelected();
assert.equal(calls.length,0,'Pending invoice must never print');
selectedKey='8|2026-10-21';
await context.window.rpPos80PreviewSelected();
assert.equal(calls.length,1);
assert.equal(calls[0].url,'/api/azur/readonly/pos80-preview');
assert.equal(dialog.length,1);
assert.match(dialog[0],/XML AUTORIZADO/);
assert.match(dialog[0],/EMISOR FICTICIO/);
assert.match(dialog[0],/Cerrar sin imprimir/);
assert.match(dialog[0],/Imprimir 80 mm/);
calls.length=0;
await context.window.rpPos80PrintSelected();
assert.equal(calls.length,2);
assert.equal(calls[0].url,'/api/printing/status');
assert.equal(calls[1].url,'/api/azur/readonly/pos80-print');
assert.equal(calls[1].options.method,'POST');
assert.deepEqual(JSON.parse(calls[1].options.body),{
 patient_id:8,fecha:'2026-10-21',numero_factura:'001-001-000000123'
});
assert.ok(notices.length>=1);
assert.match(alerts[0],/Solo se pueden imprimir facturas autorizadas/);
console.log('AZUR_DIRECT_POS_80MM_UI_CONFIRM_AND_PREVIEW_4847_OK');
