// Agenda 4.8.148: only synthetic data. No APIs, Neon, WhatsApp or patients.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const file=new URL('../recepcion/app/static/app.js',import.meta.url);
const js=readFileSync(file,'utf8');
const html=readFileSync(new URL('../recepcion/app/static/index.html',import.meta.url),'utf8');
const css=readFileSync(new URL('../recepcion/app/static/style.css',import.meta.url),'utf8');
const appPy=readFileSync(new URL('../recepcion/app/app.py',import.meta.url),'utf8');
const manifest=JSON.parse(readFileSync(new URL('../recepcion/app/update_manifest.json',import.meta.url),'utf8'));
const version=JSON.parse(readFileSync(new URL('../recepcion/app/recepcion-version.json',import.meta.url),'utf8')).version;
assert.equal(version,'4.8.149');
assert.equal(manifest.version,version);
assert.equal(manifest.app_version,version);
assert.equal(manifest.runtime_version,version);
assert.ok(html.includes('/static/app.js?v='+version));
assert.ok(html.includes('/static/style.css?v='+version));
assert.ok(appPy.includes("async def _rp48149_no_stale_assets"));
assert.ok(appPy.includes("path.startswith('/static/')"));
assert.ok(appPy.includes("response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'"));
function cut(a,b){
 const i=js.indexOf(a),j=js.indexOf(b,i);
 assert.ok(i>=0&&j>i,'missing '+a);
 return js.slice(i,j);
}
assert.match(html,/<strong>Jornada completa<\/strong>/);
assert.doesNotMatch(html,/data-agenda-range=/);
assert.match(html,/Pausa 12:30–2:00 p\. m\./);
assert.match(css,/grid-template-columns:98px repeat\(4,minmax\(205px,1fr\)\)/);
assert.match(js,/agendaRemasterRange='all'/);
assert.doesNotMatch(js,/agendaRemasterRange='morning'/);
const slots=[];
for(let minute=8*60;minute<=17*60;minute+=20){
 if(minute<14*60&&minute+20>12*60+30)continue;
 slots.push(String(Math.floor(minute/60)).padStart(2,'0')+':'+String(minute%60).padStart(2,'0'));
}
let innerHTML='';
const box={get innerHTML(){return innerHTML},set innerHTML(v){innerHTML=v}};
const ctx={
 AGENDA_SLOT_TIMES:slots, agendaNativeWeek:null,
 $:selector=>selector==='#agendaNativeGrid'?box:selector==='#agendaFocusSummary'?{textContent:''}:null,
 esc:s=>String(s), fmtDate:s=>s,
 agendaStatusInfo:()=>({cls:'pending',label:'Pendiente'}),
 agendaWhatsappBadgeHtml:()=>({html:'',cls:''}),
 parseISO:s=>{const [y,m,d]=s.split('-').map(Number);return new Date(y,m-1,d);}
};
vm.runInNewContext(
 cut('function agendaTime12(','function fmtDateTime(')+
 cut('// Vista canónica de Recepción:','function agendaStatusInfo(')+
 cut('function agendaSlotOpenForDay(','const agendaRecentPickerCache=')+
 'globalThis.testApi={agendaTime12,agendaVisibleSlotTimes,renderNativeAgenda,nativeAgendaRowCell,setAgendaTimeRange};',ctx);
const {agendaTime12,agendaVisibleSlotTimes,renderNativeAgenda,nativeAgendaRowCell,setAgendaTimeRange}=ctx.testApi;
assert.equal(agendaTime12('08:00'),'8:00 a. m.');
assert.equal(agendaTime12('12:00'),'12:00 p. m.');
assert.equal(agendaTime12('14:20'),'2:20 p. m.');
assert.equal(agendaTime12('17:00'),'5:00 p. m.');
assert.equal(agendaTime12('00:00'),'12:00 a. m.');
assert.equal(agendaTime12('24:00'),'24:00');
const dates=['2026-11-18','2026-11-19','2026-11-20','2026-11-21'];
const days=dates.map((date,i)=>({date,label:['Miércoles','Jueves','Viernes','Sábado'][i],appointments:[]}));
setAgendaTimeRange('morning'); // even a legacy invocation cannot hide the afternoon
assert.equal(agendaVisibleSlotTimes().length,slots.length);
assert.ok(agendaVisibleSlotTimes().includes('08:00'));
assert.ok(agendaVisibleSlotTimes().includes('14:00'));
assert.ok(agendaVisibleSlotTimes().includes('17:00'));
renderNativeAgenda({days});
assert.match(innerHTML,/>8:00 a\. m\.<\/div>/);
assert.match(innerHTML,/>2:00 p\. m\.<\/div>/);
assert.match(innerHTML,/>5:00 p\. m\.<\/div>/);
assert.match(innerHTML,/PAUSA · 12:30–2:00 p\. m\./);
assert.ok(innerHTML.indexOf('8:00 a. m.')<innerHTML.indexOf('PAUSA · 12:30'));
assert.ok(innerHTML.indexOf('PAUSA · 12:30')<innerHTML.indexOf('<div class="native-time">2:00 p. m.</div>'));
const free=nativeAgendaRowCell(null,'2026-11-19','14:00');
assert.match(free,/Agendar a las 2:00 p\. m\./);
assert.match(free,/openAgendaSlotPicker\('2026-11-19','14:00'\)/);
assert.match(free,/＋ 2:00 p\. m\./);
const closed=nativeAgendaRowCell(null,'2026-11-18','08:00');
assert.match(closed,/Cerrado/);
assert.doesNotMatch(closed,/openAgendaSlotPicker/);
console.log('RECEPTION_AGENDA_48148_FULL_DAY_12H_DISPLAY_ONLY_OK');
