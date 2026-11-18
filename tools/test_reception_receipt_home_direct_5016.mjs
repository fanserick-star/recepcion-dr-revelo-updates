// 5.0.16: receipt print actions must be accessible after saving and from Inicio.
// Synthetic source contract only: no Windows printer, visits, patients or Neon.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const app=read('recepcion/app/static/app.js');
const home=read('recepcion/app/static/reception_home_reference_504.js');
const css=read('recepcion/app/static/reception_home_reference_504.css');
const index=read('recepcion/app/static/index.html');
const ver=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
assert.equal(manifest.version,ver);
assert.equal(manifest.app_version,ver);
assert.equal(manifest.runtime_version,ver);
for(const name of ['app.js','reception_home_reference_504.js','reception_home_reference_504.css']){
  assert.ok(index.includes(name+'?v='+ver),name+' must bust cached UI');
}
// Show direct thermal print in the visible row, outside the overflow menu.
assert.match(home,/const directPrint=hasConsultation&&pid\?/);
assert.match(home,/printReceiptDirectFromHome/);
const actionRow=home.slice(home.indexOf('const directPrint='),home.indexOf("target.innerHTML='<table class=",home.indexOf('const directPrint=')));
assert.ok(actionRow.indexOf('directPrint+')>=0,'rendered row needs native print button');
assert.ok(actionRow.indexOf('directPrint+')<actionRow.indexOf('<details class=\\"v504-actions'),'print must precede the hidden action menu');
assert.match(css,/\.v504-print-direct\{/);
assert.match(css,/\.v504-attentions-table th:nth-child\(5\)\{width:28%!important\}/);

// The auto print happens exactly once after a *successful* confirmed save,
// and only in the Direct mode, never merely while selecting services.
const save=app.slice(app.indexOf('async function saveAttention(id){'),app.indexOf('function receiptNameLines('));
assert.ok(save.indexOf("const saved=await api('/api/visits/batch'")>=0);
assert.ok(save.indexOf('void directPrintAttentionSlip(')>save.indexOf("const saved=await api('/api/visits/batch'"));
assert.match(save,/serviceNames\.includes\('CONSULTA'\)/);
assert.match(save,/appPreferences\.print_mode\|\|'PREVIEW'/);
assert.match(save,/===?'DIRECT'/);
assert.match(save,/\.catch\(err=>\{/);
assert.match(save,/Atención guardada correctamente, pero el recibo no se imprimió/);

// A user can always send an existing consultation receipt to Windows even
// when the app default is preview, while a separate preview button remains.
assert.match(app,/async function printReceiptDirectFromHome\(patientId,fecha,button\)/);
assert.match(app,/async function printAttentionSlipDirect\(button\)/);
assert.match(app,/await directPrintAttentionSlip\(data.visit,data.patient,data.dayNumber\)/);
assert.match(app,/\/api\/printing\/receipt/);
assert.match(app,/Vista previa/);
assert.match(app,/role="status" aria-live="polite"/);
assert.ok(app.includes('No se pudo enviar el recibo a la impresora'));
console.log('RECEPTION_RECEIPT_HOME_DIRECT_5016_OK');
