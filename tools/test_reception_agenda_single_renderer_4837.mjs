// Real production renderer + legacy overlay bridge in a synthetic VM.
// This test performs NO networking, database access, billing or WhatsApp sends.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
const py=readFileSync(new URL("../recepcion/app/core_runtime.py",import.meta.url),"utf8");
const app=readFileSync(new URL("../recepcion/app/static/app.js",import.meta.url),"utf8");
const cut=(src,a,b)=>{const i=src.indexOf(a),j=src.indexOf(b,i);assert.ok(i>=0&&j>i,a);return src.slice(i,j)};
const overlay=cut(py,'V473_HOTFIX_JS = r"""','"""\nV460_OVERLAY_JS = (V460_OVERLAY_JS');
const mid=cut(overlay,'  const baseAgendaStatusInfo=window.agendaStatusInfo;','  // El detalle usa la misma regla de fecha');
const js=cut(app,'function agendaSlotOpenForDay(','function renderNativeAgenda(');
const status=cut(app,'function agendaStatusInfo(','function agendaWeekLabel(');
const ctx={
 parseISO:s=>{const [y,m,d]=String(s).slice(0,10).split("-").map(Number);return new Date(y,m-1,d);},
 fmtTime:s=>s,esc:s=>String(s).replaceAll("<","&lt;"),
 agendaWhatsappBadgeHtml:a=>({html:a?.__wa?'<small class="agenda-wa-chip confirmed">Confirmó WA</small>':"",cls:a?.__wa?'confirmed':''})
};ctx.window=ctx;
vm.runInNewContext(status+js+mid,ctx);
const row=(state="PENDIENTE",wa=false)=>({appointment:{id:1,estado:state,__wa:wa},patient:{id:5,nombre:"PACIENTE FICTICIO"}});
const wed=ctx.nativeAgendaRowCell(null,'2026-10-14','08:00');
assert.match(wed,/class="native-slot closed"/);assert.match(wed,/Cerrado/);
assert.doesNotMatch(wed,/Disponible|openAgendaSlotPicker/);
const th=ctx.nativeAgendaRowCell(null,'2026-10-15','08:00');
assert.match(th,/＋ 08:00/);assert.match(th,/openAgendaSlotPicker/);assert.doesNotMatch(th,/Disponible/);
const future=ctx.nativeAgendaRowCell(row('PENDIENTE',true),'2099-10-21','10:00');
assert.match(future,/Agendada/);assert.match(future,/Confirmó WA/);
assert.match(future,/native-status-label pending/);
const confirmed=ctx.nativeAgendaRowCell(row('CONFIRMADA',true),'2099-10-21','10:00');
assert.match(confirmed,/Confirmada/);assert.match(confirmed,/Confirmó WA/);
assert.doesNotMatch(confirmed,/Agendada/);
assert.match(py,/lambda m: f"\{m\.group\(1\)\}\?v=\{APP_VERSION\}"/);
assert.match(py,/no-store, no-cache, must-revalidate/);
assert.ok(!mid.includes('<span>Disponible</span>'));
console.log("AGENDA_4837_SINGLE_RENDERER_CLOSED_HOURS_WA_AND_VERSIONED_ASSETS_OK");
