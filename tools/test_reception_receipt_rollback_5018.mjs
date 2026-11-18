// Recepción 5.0.18: undo only the unwanted 5.0.16 printer changes.
// Source-only checks; no real patients, printer, invoices, databases or Neon.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url),'utf8');
const app=read('recepcion/app/static/app.js');
const home=read('recepcion/app/static/reception_home_reference_504.js');
const css=read('recepcion/app/static/reception_home_reference_504.css');
const html=read('recepcion/app/static/index.html');
const payment=read('recepcion/app/reception_payment_terminal.py');
const version=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
assert.equal(version,'5.0.18');
assert.equal(manifest.version,version);
assert.equal(manifest.app_version,version);
assert.equal(manifest.runtime_version,version);
for(const name of ['app.js','reception_home_reference_504.js','reception_home_reference_504.css'])
  assert.ok(html.includes(name+'?v='+version),name+' cache version');

// Original receipt action and the user's existing configured print preference.
assert.match(app,/function showAttentionSlip\(visit,patient,dayNumber=null,justSaved=false\)/);
assert.match(app,/<button class="primary" onclick="printAttentionSlip\(\)">🖨 Imprimir 80 mm<\/button>/);
assert.match(app,/async function directPrintAttentionSlip\(visit,patient,dayNumber=null\)/);
assert.doesNotMatch(app,/function printAttentionSlipDirect\(/);
assert.doesNotMatch(app,/function printReceiptDirectFromHome\(/);
assert.doesNotMatch(app,/Atención guardada correctamente, pero el recibo no se imprimió/);
const save=app.slice(app.indexOf('async function saveAttention(id){'),app.indexOf('function receiptNameLines('));
assert.ok(save.includes("serviceNames.includes('CONSULTA')"));
assert.ok(save.includes("if(receipt)showAttentionSlip("));
assert.doesNotMatch(save,/void directPrintAttentionSlip/,'no duplicate automatic direct printing');
assert.match(home,/homeReceiptButtons\(/);
assert.doesNotMatch(home,/v504-print-direct|printReceiptDirectFromHome|directPrint\+/);
assert.doesNotMatch(css,/\.v504-print-direct/);

// Critical: preserve the distinct 5.0.17 fix that unblocks saving a consultation.
assert.match(payment,/selectedServiceOrder\(\)/);
assert.match(payment,/attentionServiceValues\[name\]/);
assert.match(payment,/#atencion\.has-patient #r507VisitSlot:not\(\.hidden\)/);
assert.equal(manifest.notes.printing_changes,false);
assert.equal(manifest.notes.receipt_reverted_to_pre_5016,true);
console.log('RECEPTION_5018_RECEIPT_ROLLBACK_PRESERVE_PAYMENT_FIX_OK');
