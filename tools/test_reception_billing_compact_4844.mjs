import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const root='recepcion/app/';
const manifest=JSON.parse(readFileSync(root+'update_manifest.json','utf8'));
const version=JSON.parse(readFileSync(root+'recepcion-version.json','utf8')).version;
assert.ok(['4.8.44','4.8.45','4.8.46','4.8.47','4.8.48','4.8.49','4.8.50','4.8.51','4.8.52','4.8.53','4.8.54','4.8.55'].includes(version));
assert.equal(manifest.version,version);
assert.equal(manifest.app_version,version);
assert.equal(manifest.runtime_version,version);
const html=readFileSync(root+'static/index.html','utf8');
assert.match(html,/billing_advanced\.css\?v=4\.8\.(?:4[4-9]|5[0-5])/);
assert.match(html,/billing_advanced\.js\?v=4\.8\.(?:4[4-9]|5[0-5])/);
const css=readFileSync(root+'static/billing_advanced.css','utf8');
assert.match(css,/\.v4844-detail-meta\s*\{\s*display:grid!important/);
assert.match(css,/align-content:start!important/);
assert.match(css,/height:max-content!important/);
assert.match(css,/min-height:0!important/);
assert.match(css,/grid-auto-rows:max-content!important/);
assert.match(css,/overflow-y:auto!important/);
assert.match(css,/grid-template-columns:minmax\(95px,\.75fr\) minmax\(0,1\.65fr\)/);
const src=readFileSync(root+'static/billing_advanced.js','utf8');
const detail={innerHTML:''};
const groups=[{
  patient:{id:7,nombre:'PACIENTE DE PRUEBA',cedula:'0102030405'},
  fecha:'2026-10-21',
  items:[{billing:{estado:'EMITIDA',numero_factura:'001-002-000000127'},
          visit:{procedimiento:'CONSULTA',valor:40.0},
          azur:{estado:'AUTORIZADA',has_clave_acceso:true,numero_factura:'001-002-000000127'}}]
}];
const ctx={
  window:{},
  document:{
    readyState:'loading',
    addEventListener(){},
    getElementById(id){return id==='v4842Detail'?detail:null;},
    querySelectorAll(){return [];},
  },
  billingGroupsCache:groups,
  billingTotal:g=>g.items.reduce((n,i)=>n+i.visit.valor,0),
  money:n=>'$'+Number(n).toFixed(2),
  fmtDate:s=>s,
  billingRecipientDraft:()=>null,
  setTimeout(){}, console,
};
vm.runInNewContext(src,ctx,{filename:'billing_advanced.js'});
assert.equal(typeof ctx.window.rpBillingSelect,'function');
ctx.window.rpBillingSelect(7,'2026-10-21');
assert.match(detail.innerHTML,/v4844-detail-meta/);
assert.match(detail.innerHTML,/v4844-meta-date/);
assert.match(detail.innerHTML,/v4844-meta-recipient/);
assert.match(detail.innerHTML,/v4844-services/);
assert.match(detail.innerHTML,/v4844-invoice-number/);
assert.match(detail.innerHTML,/Autorizada por SRI/);
assert.match(detail.innerHTML,/\$40\.00/);
assert.ok(detail.innerHTML.indexOf('v4844-detail-meta')<detail.innerHTML.indexOf('v4844-services'));
assert.ok(detail.innerHTML.indexOf('v4844-services')<detail.innerHTML.indexOf('v4842-detail-total'));
assert.doesNotMatch(src,/setInterval\s*\(/,'No background polling');
assert.doesNotMatch(src,/api\/billing\/azur\/check-all-status/,'Never block opening issued history');
console.log('RECEPTION_BILLING_COMPACT_B_4844_VISUAL_ONLY_OK');
