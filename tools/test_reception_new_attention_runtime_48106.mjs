// Historical V477/V478 overlays must never replace native Nueva atención 5.0.7.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const app=fs.readFileSync('recepcion/app/static/app.js','utf8');
const core=fs.readFileSync('recepcion/app/core_runtime.py','utf8');
const html=fs.readFileSync('recepcion/app/static/index.html','utf8');
function extract(name){
 const marker=name+' = r"""';
 const a=core.indexOf(marker);assert(a>=0,name);
 const st=a+marker.length,en=core.indexOf('"""',st);assert(en>st);
 return core.slice(st,en);
}
const start=app.indexOf('function newAttention(){'),end=app.indexOf('function procedureByName(',start);
assert(start>=0&&end>start);
const canonical=app.slice(start,end);
const v477=extract('V477_ATTENTION_JS'),v478=extract('V478_REMIX_JS');
assert(!v478.includes('window.newAttention='));
assert.equal([...core.matchAll(/window\.newAttention\s*=\s*(?:async\s+)?function\s*\(/g)].length,1);
assert(html.includes('<section id="atencion" class="hidden r507-new-attention"'));
let focus=0,shown='',closed=0;
const elements={aSearch:{value:'OLD',placeholder:'',focus:()=>focus++},
 aResults:{innerHTML:'',classList:{remove(){} }},
 r507PickedPatient:{innerHTML:'',classList:{add(){} }},
 r507VisitSlot:{innerHTML:'',classList:{add(){} }}};
const document={querySelector:s=>s==='#modal .modalbox'?null:elements[s.slice(1)]||null};
const sandbox={window:{},document,console,currentPatientSource:'general',
 attentionSearchSeq:0,attentionSearchTimer:1,
 clearTimeout:()=>{},setTimeout:fn=>fn(),closeModal:()=>closed++,
 show:id=>{shown=id}};
const context=vm.createContext(sandbox);
vm.runInContext(canonical,context);
context.window.newAttention=context.newAttention;
vm.runInContext(v477,context);
const adapted=context.window.newAttention;
vm.runInContext(v478,context);
assert.strictEqual(context.window.newAttention,adapted);
context.window.newAttention();
assert.equal(shown,'atencion');
assert.equal(closed,1);
assert.equal(focus,1);
assert.equal(context.currentPatientSource,'attention-search');
assert.equal(context.attentionSearchSeq,1);
assert.match(elements.aResults.innerHTML,/No se abrirá el expediente completo/);
assert.equal(elements.aSearch.value,'');
assert.equal(typeof context.window.renderWeekCards,'function');
console.log('RECEPTION_NATIVE_NEW_ATTENTION_OLD_OVERLAY_SAFE_OK');
