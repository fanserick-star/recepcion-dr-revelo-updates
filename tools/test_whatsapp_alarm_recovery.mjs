import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// Pruebas totalmente aisladas: ni Meta, ni Cloudflare ni datos de pacientes.
const src = readFileSync(new URL("../cloudflare/whatsapp_worker.js", import.meta.url), "utf8");
const between = (start, end) => {
  const a = src.indexOf(start);
  const b = src.indexOf(end, a);
  assert.ok(a > 0 && b > a, "No se encontró la función a comprobar");
  return src.slice(a, b);
};

// Fallos de Meta: reintentos cortos SOLAMENTE dentro de la ventana inicial.
// El registro único por event_key sigue evitando reenvíos duplicados.
let statement = "", params = [];
const context = {
  sha256: async () => "sha-de-prueba",
  console: { error() {} },
};
vm.runInNewContext(between("async function claim(client, c) {", "async function markSent(client, c)") +
  "\nglobalThis.probarClaim = claim;", context);
const client = { query: async (sql, values) => {
  statement = sql;
  params = values;
  return { rows: [{ event_key: "sha-de-prueba" }] };
}};
const candidate = {
  kind: "cita_agendada",
  source_type: "appointment", source_id: 1,
  template_name: "cita_agendada", appointment_date: "2026-12-10",
  appointment_time: "15:00", due_at: "2026-10-14T21:00:00Z",
  phone: "593990000000", patient_name: "PACIENTE FICTICIO"
};
assert.equal(await context.probarClaim(client, candidate), true);
assert.match(statement, /ON CONFLICT\(event_key\)/);
assert.match(statement, /status='ERROR'/);
assert.match(statement, /attempts<5/);
assert.match(statement, /CASE WHEN \$10::boolean THEN interval '30 seconds' ELSE interval '5 minutes' END/);
assert.equal(params.length, 10);
assert.equal(params[9], true);

await context.probarClaim(client, { ...candidate, kind: "recordatorio_cita" });
assert.equal(params[9], false);

// La siguiente alarma utiliza idéntica ventana de reintento. Sin enviar nada.
let nextQuery = "", nextArgs = [];
const ctx2 = {
  enabled: () => true,
  withClient: async (_env, fn) => fn({query: async (q, args) => {
    nextQuery = q;
    nextArgs = args;
    return { rows: [{ next_due: "2026-11-17T13:00:00Z" }] };
  }}),
  Date,
};
vm.runInNewContext(between("async function nextWhatsappReminderTimestamp(env) {",
  "export class WhatsappAlarmCoordinator") +
  "\nglobalThis.probarAlarma = nextWhatsappReminderTimestamp;", ctx2);
const at = await ctx2.probarAlarma({DATABASE_URL:"fake"});
assert.equal(at, Date.parse("2026-11-17T13:00:00Z"));
assert.match(nextQuery, /WHEN kind='cita_agendada' THEN interval '30 seconds'/);
assert.match(nextQuery, /WHEN ev.kind='cita_agendada' THEN interval '3 minutes'/);
assert.match(nextQuery, /AND NOT \(coalesce\(status,''\)='ERROR' AND coalesce\(attempts,0\)>=5\)/);
assert.equal(nextArgs.length, 8);
assert.doesNotMatch(src, /async scheduled\(/);

const reception = readFileSync(new URL("../recepcion/app/core_runtime.py",import.meta.url),"utf8");
assert.match(reception, /"next_alarm_utc" not in payload/);
assert.match(reception, /_wa_alarm_hint_defer_once\(failed_generation\)/);
assert.match(reception, /_wa_alarm_deferred_count >= 2/);
assert.match(reception, /timer = threading.Timer\(delay, resume\)/);
console.log("WHATSAPP_ALARM_RECOVERY_NO_SEND_OK");
