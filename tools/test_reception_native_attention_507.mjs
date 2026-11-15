// Recepción 5.0.7 - full page Nueva atención regression contract.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const html=read('recepcion/app/static/index.html');
const app=read('recepcion/app/static/app.js');
const ui=read('recepcion/app/static/reception_new_attention_507.js');
const css=read('recepcion/app/static/reception_new_attention_507.css');
const m=JSON.parse(read('recepcion/app/update_manifest.json'));
const v=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
assert.equal(v,'5.0.7');assert.equal(m.version,v);
for(const x of ['static/reception_new_attention_507.js','static/reception_new_attention_507.css']){
 assert.ok(m.copy.includes(x)&&m.required_dependencies.includes(x),x+' required for launcher');
 assert.ok(html.includes('/'+x+'?v=5.0.7'),x+' cache-busted reference');
}
const start=html.indexOf('<section id="atencion"'),end=html.indexOf('<section id="tv"',start);
assert.ok(start>=0&&end>start,'native page must exist separately from tv and other modules');
const page=html.slice(start,end);
for(const id of ['aSearch','aResults','r507PickedPatient','r507VisitSlot','r507BillingSummary','r507HistoryList','r507ClinicalPanel','r507AgendaList']){
 assert.ok(page.includes('id="'+id+'"'),id);
}
assert.match(page,/Identificación del paciente/);
assert.match(page,/Facturación rápida/);
assert.match(page,/Historial breve/);
assert.match(page,/Estado de envío a Historia/);
assert.match(page,/Agenda del día/);
assert.match(page,/newPatient\(true\)/);
const first=app.slice(app.indexOf('function newAttention(){'),app.indexOf('\nfunction procedureByName('));
assert.match(first,/show\('atencion'\)/);
assert.doesNotMatch(first,/openModal\(/);
const search=app.slice(app.indexOf('function attentionSearch(immediate=false)'),app.indexOf('\nfunction attentionWeekKey('));
assert.match(search,/attentionFor\(\$\{Number\(p\.id\)\}\)/);
assert.doesNotMatch(search,/openPatient\(\$\{Number\(p\.id\)\},'attention-search'\)/);
const form=app.slice(app.indexOf('async function attentionFor('),app.indexOf('async function refreshAttentionClinicalHistory('));
assert.match(form,/show\('atencion'\)/);
assert.match(form,/r507VisitSlot/);
assert.match(form,/serviceCardsHtml\(\)/);
assert.match(form,/id="aFecha"/);
assert.match(form,/id="aObs"/);
assert.match(form,/id="attentionStatus"/);
assert.match(form,/id="procedureValuesBox"/);
assert.match(form,/id="saveAttentionBtn"/);
assert.match(form,/saveAttention\(\$\{id\}\)/);
assert.match(form,/saveExamReviewTurn\(\$\{id\}\)/);
assert.doesNotMatch(form,/openModal\(/);
const save=app.slice(app.indexOf('async function saveAttention('),app.indexOf('\nfunction ',app.indexOf('async function saveAttention(')+8));
assert.match(save,/\/api\/visits\/batch/);
assert.match(save,/selectedServiceOrder\(\)/);
assert.match(save,/clinicalLink===true/);
assert.match(save,/type|tipo/);
assert.match(save,/showAttentionSlip/);
assert.match(app,/\/api\/visits\/exam-review/);
assert.match(ui,/r507AttentionSelected/);
assert.match(ui,/r507ClinicalStatusChanged/);
assert.match(ui,/r507AttentionPriceChanged/);
assert.match(ui,/r507AttentionReset/);
assert.match(ui,/\/api\/patients\/'?\+Number\(patientId\)\+'?\/profile/);
assert.match(ui,/\/api\/agenda\/week/);
assert.doesNotMatch(ui,/method:\s*['"](?:POST|PUT|DELETE)['"]|setInterval\s*\(/);
assert.match(css,/grid-template-columns:minmax\(0,1\.75fr\) minmax\(335px,\.97fr\)/);
assert.match(css,/#atencion\.r507-new-attention/);
assert.equal((css.match(/\{/g)||[]).length,(css.match(/\}/g)||[]).length);
new vm.Script(ui,{filename:'reception_new_attention_507.js'});
for(const key of ['patient_data_changes','database_schema_changes','history_logic_changes','billing_logic_changes','tv_turn_logic_changes'])
 assert.equal(m.notes[key],false,key);
console.log('RECEPTION_507_NATIVE_NEW_ATTENTION_CLINICAL_CONTRACT_OK');
