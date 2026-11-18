// Recepción 5.0.19: a today KPI is distinct from a selected-day patient list.
// Synthetic patients only; no Neon, API writes, documents, printer or billing.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const read=p=>readFileSync(new URL('../'+p,import.meta.url),'utf8');
const source=read('recepcion/app/static/reception_home_reference_504.js');
const css=read('recepcion/app/static/reception_home_reference_504.css');
const native=read('recepcion/app/static/app.js');
const oldMetrics=read('recepcion/app/static/home_remaster_4886.js');
const manifest=JSON.parse(read('recepcion/app/update_manifest.json'));
const version=JSON.parse(read('recepcion/app/recepcion-version.json')).version;
const index=read('recepcion/app/static/index.html');
assert.equal(version,'5.0.19');
assert.equal(manifest.version,version);
for(const path of ['reception_home_reference_504.css','reception_home_reference_504.js'])
 assert.ok(index.includes(path+'?v='+version));
assert.match(css,/#selectedDayTitle\{\s*display:block!important/);
assert.doesNotMatch(css,/#selectedDayTitle\{\s*display:none!important/);
assert.match(source,/Atenciones de hoy/);
assert.match(source,/Pacientes registrados hoy/);
assert.match(oldMetrics,/const key=typeof toISO/);
assert.match(oldMetrics,/metric\('✓','Atenciones hoy',countOrDash\(local\?\.count\)/);
assert.match(native,/function homeThisWeek\(\)\{\s*return goHomeToday\(\)/);
assert.match(native,/const groups=groupHomeVisits\(rows\)/);

class N {
 constructor(tag='div'){this.tagName=tag;this.innerHTML='';this.textContent='';this.children=[];this.listeners={};this.dataset={};this.className='';this.classes=new Set();this.classList={contains:n=>this.classes.has(n),add:n=>this.classes.add(n),remove:n=>this.classes.delete(n)};this.row=null;this.title=null;}
 querySelector(s){return s==='div'?this.row:s==='h2'?this.title:null;}
 querySelectorAll(){return [];}
 append(...n){this.children.push(...n);}
 replaceChildren(...n){this.children=n;}
 addEventListener(event,fn){this.listeners[event]=fn;}
}
const caption=new N();caption.row=new N();caption.title=new N();
const all={inicio:new N(),app:new N(),selectedDayTitle:caption,todayTable:new N(),v504DayFooter:new N()};
all.app.classList.add('hidden');
const document={
 getElementById:id=>all[id]||null,
 createElement:tag=>new N(tag),
 addEventListener(){}
};
const groupHomeVisits=rows=>[...new Map(rows.map(x=>[x.patient.id,x])).values()].map(x=>({patient:x.patient,visits:[x],firstVisitId:x.id}));
const visits=(n,fecha)=>Array.from({length:n},(_,i)=>({id:i+1,patient_id:i+1,patient:{id:i+1,nombre:'Paciente sintético '+(i+1)},fecha,valor:40,tipo:'N',estado:'ACTIVA'}));
let backToToday=0;
const win={};let calls=0;
vm.runInNewContext(source,{window:win,document,MutationObserver:class{observe(){}},
 queueMicrotask:cb=>cb(),toISO:()=> '2026-11-18',homeThisWeek:()=>{backToToday++;},
 groupHomeVisits,homeReceiptButtons:()=>'',homeDeleteButton:()=>'',money:x=>'$'+Number(x||0).toFixed(2),
 serviceLabel:x=>x,api:()=>{calls++;throw Error('Unexpected API call');},console}, {filename:'home-reference.js'});
caption.title.textContent='Sábado 14/11/2026';
win.__r504PaintHome('2026-11-14',{count:4,visits:visits(4,'2026-11-14')});
assert.match(caption.title.textContent,/FECHA SELECCIONADA · Sábado 14\/11\/2026/);
assert.match(all.todayTable.innerHTML,/Paciente sintético 4/);
assert.equal((all.todayTable.innerHTML.match(/data-v504-patient=/g)||[]).length,4);
assert.equal(caption.row.children.length,1);
assert.equal(caption.row.children[0].textContent,'Ver hoy');
caption.row.children[0].listeners.click();
assert.equal(backToToday,1);
assert.equal(calls,0);
caption.title.textContent='Miércoles 18/11/2026';caption.row.children=[];
win.__r504PaintHome('2026-11-18',{count:8,visits:visits(8,'2026-11-18')});
assert.match(caption.title.textContent,/HOY · Miércoles 18\/11\/2026/);
assert.equal((all.todayTable.innerHTML.match(/data-v504-patient=/g)||[]).length,8);
assert.equal(caption.row.children.length,0);
assert.equal(calls,0);
console.log('RECEPTION_5019_TODAY_VS_SELECTED_4_TO_8_PATIENTS_OK');
