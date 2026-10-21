import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const src=fs.readFileSync('recepcion/app/static/billing_advanced.js','utf8');
const detail={innerHTML:''},calls=[],dialog=[],notices=[],alerts=[];
const authorized={patient:{id:8,nombre:'PACIENTE PRUEBA AUTORIZADA',cedula:'0102030405'},fecha:'2026-10-21',
 items:[{billing:{estado:'EMITIDA',numero_factura:'001-001-000000123'},
          visit:{procedimiento:'CONSULTA',valor:40},azur:{estado:'AUTORIZADA',has_clave_acceso:true,numero_factura:'001-001-000000123'}}]};
const pending={patient:{id:7,nombre:'PENDIENTE',cedula:'0102030405'},fecha:'2026-10-21',
 items:[{billing:{estado:'PENDIENTE'},visit:{procedimiento:'CONSULTA',valor:40}}]};
let cache=[authorized,pending];
const ticket={
  estado:'AUTORIZADA',emisor:'EMISOR FICTICIO',ruc:'0999999999001',numero:'001-001-000000123',
  fecha_emision:'21/10/2026',cliente:'CLIENTE FICTICIO',identificacion:'0102030405',
  subtotal:'40.00',total:'40.00',clave:'1'.repeat(49),
  servicios:[{descripcion:'CONSULTA',cantidad:'1.00',unitario:'40.00',total:'40.00'}],
  impuestos:[{codigo:'2',porcentaje:'0',valor:'0.00'}]
};
const context={
 window:{rpConfirm:async()=>true,rpNotice:(msg,title)=>notices.push({msg,title})},
 document:{readyState:'loading',addEventListener(){},getElementById:id=>id==='v4842Detail'?detail:null,querySelectorAll:()=>[]},
 billingGroupsCache:cache,
 billingTotal:g=>g.items.reduce((sum,x)=>sum+x.visit.valor,0),
 money:n=>'$'+Number(n).toFixed(2),fmtDate:s=>s,billingRecipientDraft:()=>null,
 api:async(url,options={})=>{
   calls.push({url,options});
   if(url.endsWith('pos80-preview'))return {ok:true,printed:false,ticket};
   if(url.endsWith('pos80-print'))return {ok:true,printed:true,numero_factura:ticket.numero,printer:'TEST THERMAL'};
   throw Error('Unexpected API call: '+url);
 },
 singleFlightMutation:async(k,fn)=>fn(),
 openModal:x=>dialog.push(x),
 alert:x=>alerts.push(x),
 setTimeout(){},console,
};
vm.runInNewContext(src,context,{filename:'billing_advanced.js'});
assert.equal(typeof context.window.rpBillingPosPreview,'function');
assert.equal(typeof context.window.rpBillingDirectPrint,'function');
context.window.rpBillingSelect(7,'2026-10-21');
assert.doesNotMatch(detail.innerHTML,/Imprimir factura 80 mm/);
await context.window.rpBillingDirectPrint();
assert.equal(calls.length,0,'Pending invoice must never print');
context.window.rpBillingSelect(8,'2026-10-21');
assert.match(detail.innerHTML,/Imprimir factura 80 mm/);
assert.match(detail.innerHTML,/Vista previa térmica/);
await context.window.rpBillingPosPreview();
assert.equal(calls.length,1);
assert.equal(calls[0].url,'/api/azur/readonly/pos80-preview');
assert.equal(dialog.length,1);
assert.match(dialog[0],/XML autorizado/);
assert.match(dialog[0],/EMISOR FICTICIO/);
assert.match(dialog[0],/Cerrar sin imprimir/);
assert.match(dialog[0],/Imprimir 80 mm/);
calls.length=0;
await context.window.rpBillingDirectPrint();
assert.equal(calls.length,1);
assert.equal(calls[0].url,'/api/azur/readonly/pos80-print');
assert.equal(calls[0].options.method,'POST');
assert.deepEqual(JSON.parse(calls[0].options.body),{patient_id:8,fecha:'2026-10-21',numero_factura:'001-001-000000123'});
assert.ok(notices.length>=1);
assert.doesNotMatch(src.split('window.rpBillingDirectPrint=')[1].split('window.rpBillingSelect =')[0],/\/api\/billing\/(emit|approve)/);
console.log('AZUR_DIRECT_POS_80MM_UI_CONFIRM_AND_PREVIEW_4847_OK');
