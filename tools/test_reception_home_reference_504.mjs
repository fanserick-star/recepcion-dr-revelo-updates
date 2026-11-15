// Recepción v5.0.4: only Inicio may change; screenshot layout/data-integrity contract.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const html=read('recepcion/app/static/index.html');
const css=read('recepcion/app/static/reception_home_reference_504.css');
const js=read('recepcion/app/static/reception_home_reference_504.js');
const oldJs=read('recepcion/app/static/app.js');
const old500=read('recepcion/app/static/reception_modern_500.js');
const old501=read('recepcion/app/static/reception_layout_501.js');
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
const version=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
assert.equal(version,'5.0.4');
assert.equal(manifest.version,version);
assert.equal(manifest.runtime_version,version);
for(const path of ['static/reception_home_reference_504.css','static/reception_home_reference_504.js']){
 assert.ok(manifest.copy.includes(path),path+' missing in launcher');
 assert.ok(manifest.required_dependencies.includes(path),path+' missing mandatory dependency');
 assert.ok(html.includes('/'+path+'?v='+version),path+' missing cache-busted reference');
}
assert.ok(html.indexOf('reception_home_reference_504.css')>html.indexOf('reception_home_focus_502.css'));
assert.ok(html.indexOf('reception_home_reference_504.js')>html.indexOf('reception_layout_501.js'));
// Real DOM, not a large legacy table re-skinned.
const start=html.indexOf('<section id="inicio">'),end=html.indexOf('<section id="tv"',start);
assert.ok(start>=0&&end>start);
const home=html.slice(start,end);
for(const id of ['r486Metrics','homePendingStrip','homeWhatsappReviewStrip','homeWeekNav','selectedDayTitle','todayTable','weekCards','weekSummary','v504HomeRail','v504AgendaList','v504ActivityList','v504DayFooter']){
 assert.ok(home.includes('id="'+id+'"'),'missing trusted controller or new home ID '+id);
}
assert.match(home,/Bienvenido a <span>Recepción 5\.0<\/span>/);
assert.match(home,/Atenciones del día/);
assert.match(home,/Agenda de hoy/);
assert.match(home,/Actividad reciente/);
assert.match(home,/onclick="newAttention\(\)"/);
assert.match(home,/onclick="newPatient\(\)"/);
assert.match(home,/onclick="show\('agenda'\)"/);
// Real source remains the only controller of deletes, prints, agenda and patients.
for(const fn of ['homeReceiptButtons','homeDeleteButton','groupHomeVisits','renderHomeDayPayload']){
 assert.ok(js.includes(fn),fn+' must bind to existing app.js');
 assert.ok(oldJs.includes('function '+fn+'('),fn+' missing from original controller');
}
assert.match(js,/window\.renderHomeDayPayload=function\(date,payload\)/);
assert.match(js,/home\.classList\.add\('v504-home'\)/);
assert.match(js,/originalRender\.apply\(this,arguments\)/);
assert.match(js,/homeReceiptButtons\(g,dateIso,dayTurn\)/);
assert.match(js,/homeDeleteButton\(v\)/);
assert.match(js,/openPatient\(/);
assert.match(js,/appointmentForPatient\(dateIso,pid\)/);
assert.match(js,/Sin una hora de cita vinculada/);
// User-visible status is sourced from Visit.estado, not comments or fictional queue events.
assert.match(js,/const state=String\(primary.estado\|\|'ACTIVA'\)\.toUpperCase\(\)/);
assert.match(js,/const status=cancelled\?'Cancelada':'Registrada'/);
assert.match(js,/selectedAgendaEntries\(date\)/);
assert.match(js,/const CACHE_MS=120000/);
assert.equal((js.match(/api\('\/api\//g)||[]).length,1,'only one local-first agenda endpoint allowed');
assert.doesNotMatch(js,/setInterval\s*\(|setTimeout\s*\(|XMLHttpRequest|indexedDB|localStorage|method:'(POST|PUT|DELETE)'/i,'read-only home');
assert.match(css,/grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
assert.match(css,/grid-template-columns:minmax\(0,1\.76fr\) minmax\(290px,\.97fr\)/);
assert.match(css,/grid-template-columns:1fr!important/); // responsive
assert.match(css,/max-height:none!important/);
assert.match(css,/\.v504-actions/);
assert.equal((css.match(/\{/g)||[]).length,(css.match(/\}/g)||[]).length,'CSS braces balanced');
assert.match(old500,/if\(byId\('v504HomeDashboard'\)\)return;/);
assert.match(old501,/if\(by\('v504HomeDashboard'\)\)return;/);
new vm.Script(js,{filename:'reception_home_reference_504.js'});
for(const flag of ['patient_data_changes','database_schema_changes','history_logic_changes','billing_logic_changes','tv_turn_logic_changes','agenda_booking_logic_changes']){
 assert.equal(manifest.notes[flag],false,flag+' must remain false');
}
console.log('RECEPTION_504_HOME_REFERENCE_REAL_DATA_SAFE_OK');
