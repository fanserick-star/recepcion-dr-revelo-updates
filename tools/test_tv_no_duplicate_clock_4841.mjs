import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const html=readFileSync("recepcion/app/tv_display.html","utf8");
const js=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(js,"TV script missing");
new vm.Script(js,{filename:"tv_display.html"});
const part=(start,end)=>{
  const i=js.indexOf(start),j=js.indexOf(end,i+start.length);
  assert.ok(i>=0&&j>i,start);
  return js.slice(i,j);
};
assert.match(html,/\.idle-clock-face\{[^}]*width:min\(65vh,46vw\)/);
assert.match(html,/\.idle-clock-face\{[^}]*height:min\(65vh,46vw\)/);
assert.match(html,/@media\(max-height:540px\)/);
assert.doesNotMatch(js,/id="idleClockDigital"|id="idleClockDate"/);
assert.doesNotMatch(js,/e\('idleClockDigital'\)|e\('idleClockDate'\)/);
assert.match(html,/class="time" id="time"/);
assert.match(html,/class="date" id="date"/);

const elements={center:{classList:{add:()=>{}}}};
let markup="",dial=false;
elements.stage={};
Object.defineProperty(elements.stage,"innerHTML",{
  get(){return markup},
  set(value){markup=value;dial=value.includes('id="idleClockFace"')}
});
elements.idleClockFace={};
for(const id of ["idleHourHand","idleMinuteHand","idleSecondHand"]){
  elements[id]={setAttribute(k,v){this[k]=v}};
}
const ctx={
  e:id=>id==="idleClockFace"&&!dial?null:elements[id]||null,
  state:{mode:"idle",waiting_count:0},
  stopVideo:()=>{},displayTurn:n=>String(n),Date
};
vm.runInNewContext(part("function idleClockMarks()","function displayTurn(v)")+part("function idle(force)","function render(s)"),ctx);
ctx.idle(true);
assert.match(markup,/idleClockFace/);
assert.doesNotMatch(markup,/idleClockDigital|idleClockDate|--:--/);
assert.equal((markup.match(/<svg /g)||[]).length,1);
const saved=markup;
ctx.updateIdleClock(new Date(2026,9,16,14,39,8));
assert.match(elements.idleHourHand.transform,/rotate\(79\./);
ctx.idle(false);
assert.equal(markup,saved,"No repaint every poll");
ctx.state={next_waiting_turn:9,next_waiting_exam_review:false};
ctx.idle(false);
assert.match(markup,/PRÓXIMO TURNO/);
assert.doesNotMatch(markup,/idleClockFace/);
ctx.state={next_waiting_turn:null,waiting_count:0};
ctx.idle(false);
assert.match(markup,/idleClockFace/);
assert.match(js,/if\(s.mode==='calling'&&s.turn\)/);
assert.match(js,/else if\(s.mode==='attending'&&s.turn\)/);
assert.match(js,/function announceTurn\(turn\)/);
assert.match(js,/function startVideo\(turn\)/);
assert.match(js,/if\(source==='live'&&!s.history_online/);
console.log("TV_4841_LARGER_WHITE_CLOCK_NO_DUPLICATE_DATE_TIME_WAITING_CALLS_PRESERVED_OK");
