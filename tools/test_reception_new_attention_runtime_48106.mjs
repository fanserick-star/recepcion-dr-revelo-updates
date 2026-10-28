// Reproduce real load order: app.js -> V477 adapter -> V478 legacy overlay.
// No patient records, network, Python server or Neon are used.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app=fs.readFileSync('recepcion/app/static/app.js','utf8');
const core=fs.readFileSync('recepcion/app/core_runtime.py','utf8');

function extract(name){
  const marker=name+' = r"""';
  const a=core.indexOf(marker);
  assert(a>=0, name+' missing');
  const start=a+marker.length;
  const end=core.indexOf('"""',start);
  assert(end>start,name+' not terminated');
  return core.slice(start,end);
}
const a=app.indexOf('function newAttention(){');
const b=app.indexOf('function procedureByName(',a);
assert(a>=0&&b>a,'canonical newAttention function missing');
const canonical=app.slice(a,b);
const v477=extract('V477_ATTENTION_JS');
const v478=extract('V478_REMIX_JS');
assert(!v478.includes('window.newAttention='),'V478 must never overwrite Nueva atención');
const totalOverrides=[...core.matchAll(/window\.newAttention\s*=\s*(?:async\s+)?function\s*\(/g)];
assert.equal(totalOverrides.length,1,'only V477 may wrap canonical newAttention');

let rendered='',focusCount=0,modalStyled=false;
const modal={classList:{add:name=>{if(name==='v477-attention-modalbox')modalStyled=true}}};
const document={
  querySelector:selector=>{
    if(selector==='#modal .modalbox')return modal;
    if(selector==='#aSearch')return {focus:()=>{focusCount++}};
    return null;
  }
};
const sandbox={
  window:{},document,
  currentPatientSource:'other',
  attentionSearchSeq:0,attentionSearchTimer:1,
  clearTimeout:()=>{},
  setTimeout:fn=>fn(),
  openModal:html=>{rendered=html},
  console,
};
const context=vm.createContext(sandbox);
vm.runInContext(canonical,context);
assert.equal(typeof context.newAttention,'function');
context.window.newAttention=context.newAttention;
vm.runInContext(v477,context);
const adapted=context.window.newAttention;
assert.equal(typeof adapted,'function');
vm.runInContext(v478,context);
assert.strictEqual(context.window.newAttention,adapted,'home remix must not overwrite attention flow');
assert.equal(typeof context.window.renderWeekCards,'function','home remix must remain active');
assert.equal(typeof context.window.renderHomeDayPayload,'function','home table must remain active');
context.window.newAttention();
assert.match(rendered,/attention-search-only/);
assert.match(rendered,/id="aSearch"/);
assert.match(rendered,/id="aResults"/);
assert.match(rendered,/newPatient\(true\)/);
assert.doesNotMatch(rendered,/attentionWeekBlock|attentionWeekCalendar|Agenda de hoy|v478-agenda/);
assert.equal(context.currentPatientSource,'general');
assert.equal(context.attentionSearchSeq,1);
assert.equal(focusCount,1);
assert(modalStyled,'modal visual adapter preserved');
console.log('RECEPTION_NEW_ATTENTION_RUNTIME_48106_OK');
