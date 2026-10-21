import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const root='recepcion/app/';
const src=fs.readFileSync(root+'static/billing_advanced.js','utf8');
const backend=fs.readFileSync(root+'reception_billing_discard.py','utf8');
const version=JSON.parse(fs.readFileSync(root+'recepcion-version.json','utf8')).version;
assert.ok(['4.8.45','4.8.46'].includes(version));
// Existing audited server action is reused. Nothing is deleted from the database.
assert.match(backend,/@app.post\('\/api\/v4477\/billing\/discard'\)/);
assert.match(backend,/billing\.estado = 'DESCARTADA'/);
assert.match(backend,/core\.audit\(db, user, 'descartar_factura_pendiente'/);
assert.match(backend,/str\(getattr\(emission, 'clave_acceso'/);
assert.doesNotMatch(backend,/db\.delete\(/);
assert.match(src,/\/api\/v4477\/billing\/discard/);
assert.match(src,/\/api\/open-external\/azur/);
assert.doesNotMatch(src.split('window.rpBillingOpenAzurPos =')[1].split('window.rpBillingSelect =')[0],/\/api\/billing\/azur\/emit/);
const detail={innerHTML:''},calls=[],notices=[],confirms=[],alerts=[];
let dataset=[];
const pending={patient:{id:7,nombre:'PACIENTE PRUEBA',cedula:''},fecha:'2026-10-21',items:[{billing:{estado:'PENDIENTE'},visit:{procedimiento:'CONSULTA',valor:40},azur:null}]};
const authorized={patient:{id:8,nombre:'PACIENTE AUTORIZADO',cedula:'0102030405'},fecha:'2026-10-21',items:[{billing:{estado:'EMITIDA',numero_factura:'001-001-000000123'},visit:{procedimiento:'CONSULTA',valor:40},azur:{estado:'AUTORIZADA',has_clave_acceso:true,numero_factura:'001-001-000000123'}}]};
dataset=[pending,authorized];
const ctx={
  window:{
    rpConfirm:async(message,title)=>{confirms.push({message,title});return true;},
    rpNotice:(message,title)=>notices.push({message,title}),
    loadBilling:async()=>{},
  },
  document:{
    readyState:'loading',addEventListener(){},
    getElementById: id=>id==='v4842Detail'?detail:null,
    querySelectorAll:()=>[],
  },
  api:async(url,opts={})=>{calls.push({url,opts});return {ok:true,message:'Descartada'};},
  billingGroupsCache:dataset,
  billingTotal:g=>g.items.reduce((n,i)=>n+i.visit.valor,0),
  fmtDate:v=>v,money:n=>'$'+Number(n).toFixed(2),
  billingRecipientDraft:()=>null,
  alert:msg=>alerts.push(msg),
  setTimeout(){},console,
};
vm.runInNewContext(src,ctx,{filename:'billing_advanced.js'});
assert.equal(typeof ctx.window.rpBillingDiscardPending,'function');
assert.equal(typeof ctx.window.rpBillingOpenAzurPos,'function');
ctx.window.rpBillingSelect(7,'2026-10-21');
assert.match(detail.innerHTML,/Quitar de Por emitir/);
assert.doesNotMatch(detail.innerHTML,/Imprimir en AZUR/);
await ctx.window.rpBillingDiscardPending(7,'2026-10-21');
assert.equal(calls.length,1);
assert.equal(calls[0].url,'/api/v4477/billing/discard');
assert.equal(calls[0].opts.method,'POST');
assert.deepEqual(JSON.parse(calls[0].opts.body),{patient_id:7,fecha:'2026-10-21'});
assert.match(confirms[0].message,/atención y el paciente SE CONSERVAN/);
calls.length=0;
ctx.window.rpBillingSelect(8,'2026-10-21');
assert.doesNotMatch(detail.innerHTML,/Quitar de Por emitir/);
assert.match(detail.innerHTML,/Imprimir en AZUR · POS 80 mm/);
await ctx.window.rpBillingOpenAzurPos(8,'2026-10-21');
assert.equal(calls.length,1);
assert.equal(calls[0].url,'/api/open-external/azur');
assert.equal(calls[0].opts.method,'POST');
assert.match(confirms[1].message,/Imprimir en POS/);
assert.match(confirms[1].message,/NO envía la factura directamente a la impresora/);
calls.length=0;
await ctx.window.rpBillingDiscardPending(8,'2026-10-21');
assert.equal(calls.length,0,'Never discard already emitted fiscal records');
assert.match(alerts[0],/ya no es una pendiente descartable/);
assert.ok(notices.length>=1);
console.log('RECEPTION_BILLING_DISCARD_AND_OFFICIAL_POS_HANDOFF_4845_OK');
