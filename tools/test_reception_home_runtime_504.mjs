// Real JS execution smoke: 11 patients + 1 additional service, no fabricated states.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../recepcion/app/static/reception_home_reference_504.js',import.meta.url),'utf8');
class FakeNode{
 constructor(tag='div'){this.tagName=tag;this.textContent='';this.innerHTML='';this.children=[];this.dataset={};this.className='';this.states=new Set();this.classList={contains:c=>this.states.has(c),add:c=>this.states.add(c),remove:c=>this.states.delete(c)};}
 replaceChildren(...children){this.children=children;}
 append(...children){this.children.push(...children);}
 addEventListener(){}
 querySelector(){return null;}
 querySelectorAll(){return [];}
}
const elements={
 inicio:new FakeNode('section'),todayTable:new FakeNode(),v504DayFooter:new FakeNode(),
 v504ActivityList:new FakeNode(),v504AgendaList:new FakeNode(),app:new FakeNode()
};
elements.app.states.add('hidden'); // Auth gate: no endpoints should run during isolated smoke.
let originalCalled=0,networkCalls=0;
const win={renderHomeDayPayload(){originalCalled+=1;return 'original-pass';}};
const visits=[];
for(let n=1;n<=11;n++)visits.push({
 id:n, patient_id:n,patient:{id:n,nombre:'Paciente de prueba '+n},
 tipo:n%2?'N':'S',fecha:'2026-11-14',procedimiento:'',
 valor:40,estado:'ACTIVA'
});
visits.push({id:12,patient_id:2,patient:{id:2,nombre:'Paciente de prueba 2'},tipo:'S',
 fecha:'2026-11-14',procedimiento:'ECOGRAFIA',valor:30,estado:'ACTIVA'});
const groups=rows=>{
 const map=new Map();
 for(const v of rows){
  const id=v.patient.id;
  if(!map.has(id))map.set(id,{patient:v.patient,visits:[],isNew:v.tipo==='N'});
  const g=map.get(id);g.visits.push(v);if(v.tipo==='N')g.isNew=true;
 }
 return [...map.values()];
};
const document={
 getElementById:id=>elements[id]||null,
 createElement:tag=>new FakeNode(tag),
 addEventListener(){}
};
const sandbox={window:win,document,MutationObserver:class{observe(){}},
 queueMicrotask:cb=>cb(),
 console,groupHomeVisits:groups,homeReceiptButtons:()=>'<button class="home-print-receipt" onclick="reprintReceiptFromHome(1)">Reimprimir</button>',
 homeDeleteButton:v=>'<button class="home-delete-visit" onclick="deleteVisitFromHome('+v.id+')">Borrar</button>',
 money:n=>'$'+Number(n).toFixed(2),serviceLabel:s=>s,api:()=>{networkCalls++;throw Error('No expected network calls');},
 toISO:()=> '2026-11-14',agendaTime12:t=>t
};
vm.runInNewContext(source,sandbox,{filename:'reception_home_reference_504.js'});
const result=win.renderHomeDayPayload('2026-11-14',{visits});
assert.equal(result,'original-pass');
assert.equal(originalCalled,1,'original business renderer should run exactly once');
const output=elements.todayTable.innerHTML;
assert.equal((output.match(/<tr data-v504-patient=/g)||[]).length,11,'all 11 distinct patients must appear');
assert.match(output,/Paciente de prueba 11/);
assert.match(output,/Paciente de prueba 1/);
assert.match(output,/servicio\(s\) adicional\(es\)/);
assert.match(output,/Reimprimir/,'receipt action preserved');
assert.match(output,/Borrar/,'delete action preserved');
assert.match(output,/openPatient\(/,'open patient preserved');
assert.match(output,/Registrada/);
assert.doesNotMatch(output,/Finalizado|En consulta|En espera/,'must not invent clinical state');
assert.match(elements.v504DayFooter.textContent,/Mostrando 11 de 11/);
assert.equal(networkCalls,0,'no extra network calls while auth gate is hidden');
assert.equal(elements.v504ActivityList.children.length,4,'recent activity limited to four real visit groups');
console.log('RECEPTION_504_11_PATIENTS_RENDERED_REAL_ACTIONS_OK');
