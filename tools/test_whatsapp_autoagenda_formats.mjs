import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

// Solo lectura del Worker, ejecución de parser con datos inventados.
// Nunca usa red, Neon, autorización real, pacientes ni envía mensajes.
const src=readFileSync(new URL("../cloudflare/whatsapp_worker.js", import.meta.url),"utf8");
const start=src.indexOf("const AUTOAGENDA_WEEKDAYS =");
const end=src.indexOf("function autoagendaReply(parsed, status) {",start);
assert.ok(start>0&&end>start);
const FakeDate=class extends Date {
  constructor(...args){super(...(args.length?args:["2026-10-14T22:40:00Z"]));}
  static now(){return Date.parse("2026-10-14T22:40:00Z");}
};
const ctx={
  Date:FakeDate, Intl,
  normalizePhone: p=>String(p||""),
  bookingDateObj: iso=>{
    if(!/^\d{4}-\d{2}-\d{2}$/.test(iso))return null;
    return new Date(iso+"T00:00:00Z");
  },
  bookingCleanName: name=>String(name||"").trim().toUpperCase(),
  bookingCleanPhone: phone=> /^09\d{8}$/.test(String(phone).trim()) ? String(phone).trim() : "",
  bookingValidDay: iso=>[3,4,5,6].includes(new Date(iso+"T00:00:00Z").getUTCDay()),
  bookingDateWithinHorizon: iso=>iso>="2026-10-14"&&iso<="2026-12-13",
  bookingTimeWithinSchedule: (iso,hour)=>/^(09:00|09:20)$/.test(hour),
};
vm.runInNewContext(src.slice(start,end)+
  "\nglobalThis.isCommand=autoagendaLooksLikeCommand;globalThis.parse= parseAutoagendaForward;",ctx);
const phone="0982676851",patient="PACIENTE DE PRUEBA";
function check(msg,date){
  assert.equal(ctx.isCommand(msg),true, "Debe reconocer el comando");
  const r=ctx.parse(msg);
  assert.equal(r.ok,true,r.error);
  assert.equal(r.date,date);
  assert.equal(r.time,"09:00");
  assert.equal(r.phone,phone);
}
check("Viernes 9am\n"+patient+"\n"+phone,"2026-10-16");
check("Viernes\n"+patient+"\n9am\n"+phone,"2026-10-16");
check("Viernes 23 oct\n"+patient+"\n9am\n"+phone,"2026-10-23");
check("Viernes 23 octubre 2026\n"+patient+"\n9am\n"+phone,"2026-10-23");
check("Viernes 23/10\n"+patient+"\n9am\n"+phone,"2026-10-23");
check("Viernes 23/10/2026\n"+patient+"\n9am\n"+phone,"2026-10-23");
assert.match(ctx.parse("Jueves 23 oct\n"+patient+"\n9am\n"+phone).error,/no coincide/);
assert.match(ctx.parse("Viernes 31 feb\n"+patient+"\n9am\n"+phone).error,/no existe|no coincide/);
assert.match(ctx.parse("Viernes 23 oct\n"+patient+"\n"+phone).error,/hora/);
assert.equal(ctx.isCommand("Hola, buenos días"),false);
assert.equal(ctx.isCommand("Viernes 23 oct\n"+patient+"\n9am"),false); // Sin teléfono no crear cita.
assert.equal(ctx.parse("Viernes 23 oct\n"+patient+"\n9am\n0981111111").ok,true);
console.log("AUTOAGENDA_3_4_LINES_EXPLICIT_DATE_NO_SEND_OK");