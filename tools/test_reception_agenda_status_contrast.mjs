// No network/Neon/Meta: render synthetic appointment cards using production JS.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const js=readFileSync(new URL("../recepcion/app/static/app.js",import.meta.url),"utf8");
const css=readFileSync(new URL("../recepcion/app/static/style.css",import.meta.url),"utf8");
const isolate=(start,end)=>{let a=js.indexOf(start),b=js.indexOf(end,a);assert.ok(a>=0&&b>a,start);return js.slice(a,b)};
const ctx={
 esc: s=>String(s).replaceAll("&","&amp;").replaceAll("<","&lt;"),
 fmtTime:s=>String(s),agendaSlotOpenForDay:()=>true,
 agendaWhatsappStateForAppointment:a=>({kind:a.__waKind||"none",latest:{message_type:"text"}})
};
vm.runInNewContext(
 isolate("function agendaStatusInfo(","function agendaWeekLabel(")+
 isolate("function agendaWhatsappBadgeHtml(","function agendaWhatsappWeekKeyFor(")+
 isolate("function nativeAgendaRowCell(","function renderNativeAgenda(")+
 "globalThis.render=nativeAgendaRowCell;",ctx);
const render=(state,wa="none")=>ctx.render({appointment:{id:1,estado:state,__waKind:wa},
 patient:{id:2,nombre:"PACIENTE SINTETICO"}},"2026-10-22","10:00");
for (const [state,cls,label,mark] of [
 ["PENDIENTE","pending","Pendiente","◷"],["CONFIRMADA","confirmed","Confirmada","✓"],
 ["REAGENDADA","rescheduled","Reagendada","↻"],["NO_ASISTIRA","cancelled","No asistirá","✕"]
]) {
 let html=render(state);
 assert.ok(html.includes("occupied "+cls),state);
 assert.ok(html.includes("native-status-label "+cls),state);
 assert.ok(html.includes(label)&&html.includes(mark),state);
}
const yes=render("PENDIENTE","confirmed"),no=render("PENDIENTE","no-show");
assert.ok(yes.includes("wa-confirmed")&&yes.includes("Confirmó WA"));
assert.ok(no.includes("wa-no-show")&&no.includes("Rechazó WA"));
assert.ok(yes.includes("Pendiente")&&no.includes("Pendiente"),"Business status unchanged");
for(const state of ["confirmed","wa-confirmed","pending","cancelled","wa-no-show","rescheduled"]){
 assert.ok(css.includes(state),state);
}
assert.match(css,/\.native-slot\.occupied\.wa-no-show/);
assert.match(css,/\.native-slot\.occupied\.wa-confirmed/);
assert.match(js,/function agendaVisibleSlotTimes\(\)/);
assert.match(js,/function saveAgendaAppointment\(/);
console.log("RECEPTION_AGENDA_4835_CONTRAST_CONFIRMED_REJECTED_NO_META_NO_DB_OK");
