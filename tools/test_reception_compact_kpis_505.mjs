// v5.0.6: visual-only regression guard for compact KPIs + left Activity shortcut.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const css=read('recepcion/app/static/reception_home_reference_504.css');
const js=read('recepcion/app/static/reception_modern_500.js');
const html=read('recepcion/app/static/index.html');
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
const version=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
assert.equal(version,'5.0.6');
assert.equal(manifest.version,version);
assert.ok(html.includes('reception_home_reference_504.css?v='+version));
assert.ok(html.includes('reception_modern_500.js?v='+version));
const metricBlock=css.slice(css.indexOf('body.v50-ui #inicio.v504-home #r486Metrics .r486-metric{'),css.indexOf('body.v50-ui #inicio.v504-home #r486Metrics .r486-metric:nth-child(1)'));
assert.match(metricBlock,/min-height:105px!important/,'compact metric height');
assert.doesNotMatch(metricBlock,/min-height:118px!important/,'not as tall as the rejected 5.0.4 UI');
assert.match(metricBlock,/padding:12px 13px 12px 68px!important/,'reduced internal padding');
assert.match(css,/width:40px!important;height:40px!important/,'smaller icon');
assert.match(css,/font-size:27px!important;line-height:1\.05!important/,'smaller numerical value');
assert.match(css,/font-size:9\.5px!important;font-weight:660!important/,'compact caption');
assert.match(css,/grid-template-columns:repeat\(4,minmax\(0,1fr\)\)!important/,'keep four-column KPI order');
for(const caption of ['Atenciones del día','Agenda de hoy','Actividad reciente']){
 assert.ok(html.includes(caption),'preserve header/agenda/activity: '+caption);
}
assert.match(html,/id="configActivityAccess"/,'audit history still under Settings');
assert.match(html,/onclick="show\('actividad'\)"/,'audit register remains accessible');
assert.match(css,/\.nav-btn\[data-section="actividad"\]\{display:none!important\}/,'hide only left Activity shortcut');
assert.match(js,/removeSidebarActivity/);
assert.match(js,/nav\.dataset\.v505ActivityGuard/,'handle dynamically inserted old sidebar shortcut');
assert.match(js,/label==='actividad'\|\|label==='actividades'/);
assert.match(js,/button\.remove\(\)/);
new vm.Script(js,{filename:'reception_modern_500.js'});
assert.equal((css.match(/\{/g)||[]).length,(css.match(/\}/g)||[]).length);
for(const key of ['patient_data_changes','database_schema_changes','history_logic_changes','billing_logic_changes','tv_turn_logic_changes'])assert.equal(manifest.notes[key],false);
console.log('RECEPTION_505_KPI_COMPACT_LEFT_ACTIVITY_REMOVED_OK');
