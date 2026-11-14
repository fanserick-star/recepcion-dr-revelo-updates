// Prueba sintética sin datos de pacientes, Neon ni mensajes.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const core=readFileSync(new URL('../recepcion/app/core_runtime.py',import.meta.url),'utf8');
const match=/RP_AGENDA_12H_INLINE = r"""([\s\S]*?)"""/.exec(core);
assert.ok(match,'guardia visual integrada en backend ausente');
assert.match(core,/result = result\.replace\("<\/body>", "<script>" \+ RP_AGENDA_12H_INLINE/);
new vm.Script(match[1]);

function node(s){return {nodeType:3,nodeValue:s}}
function el(type,values,occupied=false){
  const nodes=values.map(node);
  return {
    type,nodes,
    classList:{contains:x=>x===type},
    querySelector:()=>occupied?{}:null
  };
}
// Replica la captura real: la hora y "Disponible" son nodos diferentes,
// con HTML antiguo que puede no usar .native-slot.free.
const time=el('native-time',['14:00']);
const freeSplit=el('native-cell',['14:20','Disponible']);
const freeJoined=el('native-cell',['15:00Disponible']);
const freePrefix=el('native-cell',['＋ 17:00']);
const freeNoon=el('native-cell',['12:00']);
const freeAlready12=el('native-cell',['2:40 p. m.']);
const freeWithNote=el('native-cell',['Hora 16:20 disponible']);
const occupied=el('native-cell',['Paciente','14:00'],true);
const grid={
  querySelectorAll(selector){
    assert.equal(selector,'.native-time, .native-cell');
    return [time,freeSplit,freeJoined,freePrefix,freeNoon,freeAlready12,freeWithNote,occupied];
  }
};
let observer;
const doc={
  readyState:'complete',
  documentElement:{dataset:{}},
  getElementById(id){if(id==='agendaNativeGrid')return grid;if(id==='agenda')return {section:true};return null},
  createTreeWalker(target){
    let i=0;
    return {nextNode(){return target.nodes[i++]||null}}
  }
};
const ctx={
  window:{},document:doc,NodeFilter:{SHOW_TEXT:4},queueMicrotask,
  MutationObserver:class{constructor(cb){observer=this;this.cb=cb}observe(target,config){assert.deepEqual(Object.keys(config).sort(),['characterData','childList','subtree']);assert.ok(target.section)}}
};
vm.runInNewContext(match[1],ctx);
assert.equal(doc.documentElement.dataset.rpAgenda12h,'4.8.151');
assert.equal(time.nodes[0].nodeValue,'2:00 p. m.');
assert.equal(freeSplit.nodes[0].nodeValue,'2:20 p. m.');
assert.equal(freeSplit.nodes[1].nodeValue,'Disponible');
assert.equal(freeJoined.nodes[0].nodeValue,'3:00 p. m. Disponible');
assert.equal(freePrefix.nodes[0].nodeValue,'＋ 5:00 p. m.');
assert.equal(freeNoon.nodes[0].nodeValue,'12:00 p. m.');
assert.equal(freeAlready12.nodes[0].nodeValue,'2:40 p. m.');
assert.equal(freeWithNote.nodes[0].nodeValue,'Hora 4:20 p. m. disponible');
assert.equal(occupied.nodes[1].nodeValue,'14:00'); // No alterar citas existentes.
freeSplit.nodes[0].nodeValue='16:40';
observer.cb();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(freeSplit.nodes[0].nodeValue,'4:40 p. m.');
observer.cb();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(freeSplit.nodes[0].nodeValue,'4:40 p. m.');
console.log('RECEPTION_AGENDA_48151_12H_FREE_CELLS_OK');