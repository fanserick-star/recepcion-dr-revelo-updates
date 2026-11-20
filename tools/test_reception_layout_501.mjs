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
assert.match(version,/^5[.]0[.][1-9][0-9]*$/,'Release version must stay in supported 5.0.x channel');
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

const dossierJS=read('recepcion/app/static/app.js');
const modernSection=css.slice(css.indexOf('Recepción 5.0.21 — Expediente Moderno Profesional'));
assert.ok(modernSection.length>5000,'approved dossier design override was not installed');
assert.match(modernSection,/#pacientes:not\(\.hidden\)/,'patient workspace layout');
assert.match(modernSection,/\.patient-compact-row\.v5021-selected/,'active patient highlighted');
assert.match(modernSection,/\.v501-avatar\s*\{\s*display:none!important/,'approved design has no initials avatar');
assert.match(modernSection,/\.v4413-profile-kpis/,'compact visible indicators');
assert.match(modernSection,/\.v4413-profile-tabs/,'five original tabs stay visible');
assert.match(modernSection,/#modal\.v50-dossier-open:not\(\.v501-docked-profile\):not\(\.hidden\)/,'Home uses a special centered modal');
assert.match(modernSection,/place-items:center!important/,'Home modal must be vertically and horizontally centered');
assert.match(modernSection,/backdrop-filter:blur\(3px\)/,'Home dims the background');
assert.match(modernSection,/#modal\.v50-dossier-open\.v501-docked-profile/,'Patients retains a right-side dossier at 1600');
assert.match(modernSection,/@media\(max-width:1259px\)/,'narrow screens keep a readable modal');
assert.match(dossierJS,/v5021-dossier/,'original patient profile markup is retained');
assert.match(dossierJS,/data-patient-id="\$\{Number\(p.id\)\}"/,'patient selection is purely visual');
assert.match(dossierJS,/row\.classList\.toggle\('v5021-selected'/,'selected row indicator');
assert.match(dossierJS,/v5021-more-menu/,'destructive action is kept in More menu');
for(const tab of ['resumen','atenciones','agenda','facturacion','documentos'])
 assert.ok(dossierJS.includes('data-profile-tab="'+tab+'"'),'missing patient tab: '+tab);
assert.match(dossierJS,/window\.loadClinicalDelivery/,'clinical LAN panel unchanged');
assert.match(dossierJS,/deletePatient/,'patient deletion handler must still exist');

assert.doesNotMatch(js,/fetch\(|XMLHttpRequest|localStorage|indexedDB|\.post\(|\.put\(/i,'design adapter must not write data');
assert.match(js,/30\*60\*1000/,'agenda summary must throttle its local reads');
assert.match(js,/\/api\/agenda\/week\?anchor=/,'use the existing local-first weekly agenda');
assert.equal((js.match(/api\('\/api\//g)||[]).length,1,'exactly one local-first read, no extra endpoints');
for(const key of ['database_schema_changes','patient_data_changes','billing_logic_changes','history_logic_changes','tv_turn_logic_changes'])assert.equal(manifest.notes[key],false,key+' must remain false');
console.log('RECEPTION_501_COMPACT_LAYOUT_CANONICAL_SAFE_OK');