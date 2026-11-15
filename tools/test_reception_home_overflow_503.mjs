/* Recepción 5.0.3: independent contract verifying the exact 4.8.94 scroll conflict is gone. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const src=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const legacy=src('recepcion/app/static/home_remaster_4886.css');
const home=src('recepcion/app/static/reception_home_focus_502.css');
const html=src('recepcion/app/static/index.html');
const manifest=JSON.parse(src('recepcion/app/update_manifest.json'));
const v=JSON.parse(src('recepcion/app/recepcion-version.json')).version;
assert.equal(v,'5.0.4');
assert.ok(html.includes('reception_home_focus_502.css?v='+v));
assert.ok(html.includes('home_remaster_4886.css?v='+v));
// Regression observed in the user's actual screenshot: older CSS was MORE SPECIFIC,
// so 5.0.2 couldn't override its max-height:59vh and overflow-y:auto.
assert.match(legacy,/body\.r486-ui:not\(\.v50-ui\) #inicio \.r494-attentions-primary #todayTable\{/);
assert.match(legacy,/@media\(max-width:900px\)\{\s*body\.r486-ui:not\(\.v50-ui\) #inicio \.r494-attentions-primary #todayTable/);
assert.doesNotMatch(legacy,/body\.r486-ui #inicio \.r494-attentions-primary #todayTable\{/);
assert.match(home,/body\.v50-ui\.r486-ui #inicio \.r494-attentions-primary #todayTable\{/);
const start=home.indexOf('body.v50-ui.r486-ui #inicio .r494-attentions-primary #todayTable{');
assert.ok(start>=0);
const fixed=home.slice(start,home.indexOf('}',start)+1);
assert.match(fixed,/max-height:none!important/);
assert.match(fixed,/overflow-y:visible!important/);
assert.match(home,/tbody td\{\s*height:auto!important;min-height:0!important;\s*padding:6px 10px!important/);
assert.match(home,/\.patient-name-button\{\s*font-size:12px!important/);
assert.match(home,/\.home-delete-visit\{\s*min-height:25px!important/);
for(const f of ['patient_data_changes','database_schema_changes','billing_logic_changes','history_logic_changes','tv_turn_logic_changes'])assert.equal(manifest.notes[f],false);
for(const f of ['static/home_remaster_4886.css','static/reception_home_focus_502.css'])assert.ok(manifest.copy.includes(f));
console.log('RECEPTION_503_LEGACY_59VH_SCROLL_FIXED_COMPACT_ROWS_OK');