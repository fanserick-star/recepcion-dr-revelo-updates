// Recepción 5.0.1 — visual contract test, purely static and synthetic.
// All patient, clinical, billing, agenda and TV operations remain on existing modules.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const html=read('recepcion/app/static/index.html');
const css=read('recepcion/app/static/reception_layout_501.css');
const js=read('recepcion/app/static/reception_layout_501.js');
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
const version=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
assert.equal(version,'5.0.8');
for(const p of ['static/reception_layout_501.css','static/reception_layout_501.js']){
 assert.ok(manifest.copy.includes(p),p+' missing from installer payload');
 assert.ok(manifest.required_dependencies.includes(p),p+' missing from mandatory payload');
 assert.ok(html.includes('/'+p+'?v='+version),p+' missing from actual index');
}
assert.ok(html.indexOf('reception_layout_501.css')>html.indexOf('reception_modern_500.css'),'CSS must override previous visual layer');
assert.ok(html.indexOf('reception_layout_501.js')>html.indexOf('reception_modern_500.js'),'JS must load after previous visual layer');
assert.ok(html.includes('src="/static/app.js?v='+version+'"'));
assert.match(html,/id="agendaNativeGrid"/);
assert.match(html,/id="todayTable"/);
assert.match(css,/#inicio:not\(\.hidden\)/);
assert.match(css,/#pacientes:not\(\.hidden\)/);
assert.match(css,/#modal\.v501-docked-profile/);
assert.match(css,/#modal\.v501-workspace-open/);
assert.match(css,/#agenda \.native-slot/);
assert.match(css,/pointer-events:none!important/);
assert.match(js,/new MutationObserver\(update\)/);
assert.match(js,/const attention=visible/);
assert.match(js,/const dossier=visible/);
assert.match(js,/document\.querySelectorAll\('#app>main>section'\)/);
assert.match(js,/previousAttention=attention/);
new vm.Script(js,{filename:'reception_layout_501.js'});
assert.equal((css.match(/\{/g)||[]).length,(css.match(/\}/g)||[]).length,'CSS braces');
assert.doesNotMatch(js,/fetch\(|XMLHttpRequest|localStorage|indexedDB|\.post\(|\.put\(/i,'design adapter must not write data');
assert.match(js,/30\*60\*1000/,'agenda summary must throttle its local reads');
assert.match(js,/\/api\/agenda\/week\?anchor=/,'use the existing local-first weekly agenda');
assert.equal((js.match(/api\('\/api\//g)||[]).length,1,'exactly one local-first read, no extra endpoints');
for(const key of ['database_schema_changes','patient_data_changes','billing_logic_changes','history_logic_changes','tv_turn_logic_changes'])assert.equal(manifest.notes[key],false,key+' must remain false');
console.log('RECEPTION_501_COMPACT_LAYOUT_CANONICAL_SAFE_OK');