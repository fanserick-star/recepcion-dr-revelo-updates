// Recepción 5.0.2: patient-first home visibility / no new I/O regression.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const css=read('recepcion/app/static/reception_home_focus_502.css');
const shell=read('recepcion/app/static/reception_layout_501.js');
const app=read('recepcion/app/static/app.js');
const html=read('recepcion/app/static/index.html');
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
const version=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
assert.match(version,/^5[.]0[.][1-9][0-9]*$/,'Supported Reception 5.0.x release');
const path='static/reception_home_focus_502.css';
assert.ok(manifest.copy.includes(path));
assert.ok(manifest.required_dependencies.includes(path));
assert.ok(html.includes('/'+path+'?v='+version));
assert.ok(html.indexOf('reception_home_focus_502.css')>html.indexOf('reception_layout_501.css'),
 'Patient-first CSS must run after previous layout rules');
assert.equal((css.match(/\{/g)||[]).length,(css.match(/\}/g)||[]).length,'CSS braces must balance');
// No height cap and no nested vertical scroll on the day table.
const block=css.slice(css.indexOf('body.v50-ui #inicio #todayTable{'),css.indexOf('body.v50-ui #inicio #todayTable table.home-patient-table{'));
assert.match(block,/max-height:none!important/);
assert.match(block,/height:auto!important/);
assert.match(block,/overflow:visible!important/);
assert.match(css,/\.r494-attentions-primary\{/);
assert.match(css,/grid-template-columns:minmax\(0,1fr\)!important/);
// No deletion of patients / alert actions to gain space.
assert.match(css,/#inicio #r486Metrics\{display:none!important\}/);
assert.match(css,/#inicio \.v50-home-rail\{display:none!important\}/);
assert.match(css,/#homeSmartAlertsButton\{/);
assert.match(css,/\.home-reminder-card\{/);
assert.match(app,/groups\.map\(\(g,index\)=>/);
assert.match(app,/renderHomeDayPayload\(iso,d\)/);
assert.match(shell,/heading\.textContent='Atenciones del día'/);
assert.match(shell,/redundantRail\.hidden=true/);
assert.doesNotMatch(shell.slice(shell.indexOf('function boot(){')),/watchHomeAgenda\(\)/,'hidden rail must not request duplicated week data');
new vm.Script(shell);
for(const flag of ['database_schema_changes','patient_data_changes','history_logic_changes','billing_logic_changes','tv_turn_logic_changes']){
 assert.equal(manifest.notes[flag],false,flag);
}
console.log('RECEPTION_502_ALL_DAY_PATIENTS_VISIBLE_ALERTS_SAFE_OK');