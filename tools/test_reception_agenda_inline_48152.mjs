// Test independent of the old runtime: run the exact inline script in index.html.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync(new URL('../recepcion/app/static/index.html',import.meta.url),'utf8');
const m=/<script id="rp48152-agenda-clock-guard">([\s\S]*?)<\/script>/.exec(html);
assert.ok(m,'Missing standalone agenda guard in actual static HTML');
assert.ok(html.indexOf('id="rp48152-agenda-clock-guard"')>html.indexOf('src="/static/app.js?v=4.8.152"'),'Guard must run after main scripts');
new vm.Script(m[1]);

const labels=[
 {textContent:'14:00'}, {textContent:'＋ 14:20'}, {textContent:'17:00'},
 {textContent:'12:00'}, {textContent:'11:40'}, {textContent:'2:20 p. m.'}
];
// DOM inspection showed: <button class="native-slot free"><b class="native-free-time">14:00</b><span>Disponible</span></button>
const free={onclick:"openAgendaSlotPicker('2026-11-11','14:00')",span:{textContent:'Disponible'}};
let observer;
const root={
 querySelectorAll(selector){
   assert.equal(selector,'.native-time, .native-slot.free .native-free-time');
   return labels;
 }
};
const document={
 readyState:'complete', documentElement:{dataset:{}},
 getElementById(id){return id==='agendaNativeGrid'?root:null}
};
const ctx={
 window:{},document,queueMicrotask,
 MutationObserver:class{
   constructor(callback){observer=this;this.cb=callback}
   observe(r,opts){assert.equal(r,root);assert.deepEqual(Object.keys(opts).sort(),['characterData','childList','subtree'])}
 }
};
vm.runInNewContext(m[1],ctx);
assert.deepEqual(labels.map(x=>x.textContent),[
 '2:00 p. m.','＋ 2:20 p. m.','5:00 p. m.','12:00 p. m.',
 '11:40 a. m.','2:20 p. m.'
]);
assert.equal(free.span.textContent,'Disponible');
assert.equal(free.onclick,"openAgendaSlotPicker('2026-11-11','14:00')");
labels[0].textContent='16:40';
observer.cb();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(labels[0].textContent,'4:40 p. m.');
observer.cb();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(labels[0].textContent,'4:40 p. m.');
assert.equal(document.documentElement.dataset.rpAgendaClockGuard,'4.8.152');
console.log('RECEPTION_AGENDA_INLINE_48152_OK');
