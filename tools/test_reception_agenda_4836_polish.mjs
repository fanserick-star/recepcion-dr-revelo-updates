// Render real production source with fictitious rows; no requests, Neon, Meta or mutations.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const js=readFileSync(new URL("../recepcion/app/static/app.js",import.meta.url),"utf8");
const css=readFileSync(new URL("../recepcion/app/static/style.css",import.meta.url),"utf8");
function snippet(a,b){let i=js.indexOf(a),j=js.indexOf(b,i);assert.ok(i>=0&&j>i,a);return js.slice(i,j)}
const ctx={
 parseISO:s=>{const [y,m,d]=String(s).slice(0,10).split("-").map(Number);return new Date(y,m-1,d)},
 fmtTime:s=>s,esc:s=>String(s).replaceAll("&","&amp;").replaceAll("<","&lt;"),
 agendaStatusInfo:s=>({label:"Pendiente",cls:"pending"}),
 agendaWhatsappBadgeHtml:()=>({html:"",cls:""})
};
vm.runInNewContext(
 snippet("function agendaSlotOpenForDay(","function renderNativeAgenda(")
 +"globalThis.allowed=agendaSlotOpenForDay;globalThis.cell=nativeAgendaRowCell;",ctx);
assert.equal(ctx.allowed("2026-10-14","08:00"),false);
assert.equal(ctx.allowed("2026-10-14","09:40"),false);
assert.equal(ctx.allowed("2026-10-14","10:00"),true);
assert.equal(ctx.allowed("2026-10-15","08:00"),true);
assert.equal(ctx.allowed("2026-10-15","12:20"),false);
assert.equal(ctx.allowed("2026-10-15","14:00"),true);
assert.equal(ctx.allowed("2026-10-15","17:00"),true);
let closed=ctx.cell(null,"2026-10-14","08:00");
assert.match(closed,/class="native-slot closed"/);assert.match(closed,/Cerrado/);
assert.doesNotMatch(closed,/openAgendaSlotPicker|Disponible/);
let open=ctx.cell(null,"2026-10-15","08:00");
assert.match(open,/class="native-slot free"/);assert.match(open,/openAgendaSlotPicker/);
assert.match(open,/＋ 08:00/);assert.match(open,/aria-label="Agendar/);
assert.doesNotMatch(open,/Disponible|08:00Disponible/);
let historic=ctx.cell({appointment:{id:1,estado:"PENDIENTE"},patient:{id:5,nombre:"HISTÓRICO FICTICIO"}},"2026-10-14","09:00");
assert.match(historic,/class="native-slot occupied/);assert.match(historic,/HISTÓRICO FICTICIO/);
assert.ok(css.includes("v4.8.36 — pulido grafito"));
assert.ok(css.includes(".native-unlinked"));
console.log("AGENDA_4836_POLISH_WEDNESDAY_CLIENT_AND_HISTORIC_APPOINTMENTS_OK");
