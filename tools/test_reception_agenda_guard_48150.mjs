// Synthetic-only test: no patient records, Neon, WhatsApp, Cloudflare.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const core=readFileSync(new URL('../recepcion/app/core_runtime.py',import.meta.url),'utf8');
const m=/RP_AGENDA_12H_INLINE = r"""([\s\S]*?)"""/.exec(core);
assert.ok(m,'backend inline guard missing');
assert.match(core,/result = result\.replace\("<\/body>", "<script>" \+ RP_AGENDA_12H_INLINE/);
new vm.Script(m[1]);
const samples=['14:00','11:40Disponible','＋ 17:00','12:00','2:20 p. m.','MIGUEL CHAVEZ','14:20 Disponible','00:00','24:00'];
const nodes=samples.map(nodeValue=>({nodeType:3,nodeValue}));
const targets=nodes.map(node=>({node}));
const grid={querySelectorAll:()=>targets};
let observer;
const doc={
  readyState:'complete',
  documentElement:{dataset:{}},
  getElementById(id){return id==='agendaNativeGrid'?grid:null},
  createTreeWalker(el){let used=false;return {nextNode(){if(used)return null;used=true;return el.node}}}
};
const ctx={
  window:{},document:doc,NodeFilter:{SHOW_TEXT:4},queueMicrotask,
  MutationObserver:class{constructor(cb){this.cb=cb;observer=this}observe(){}}
};
vm.runInNewContext(m[1],ctx);
const expected=['2:00 p. m.','11:40 a. m. Disponible','＋ 5:00 p. m.','12:00 p. m.','2:20 p. m.','MIGUEL CHAVEZ','2:20 p. m. Disponible','12:00 a. m.','24:00'];
assert.deepEqual(nodes.map(n=>n.nodeValue),expected);
assert.equal(doc.documentElement.dataset.rpAgenda12h,'4.8.150');
nodes[0].nodeValue='16:40';observer.cb();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(nodes[0].nodeValue,'4:40 p. m.');
console.log('RECEPTION_AGENDA_48150_INLINE_GUARD_OK');
