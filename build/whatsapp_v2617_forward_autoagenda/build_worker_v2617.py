from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2616_BUILDER = ROOT / "build" / "v4441_diag_reader" / "build_worker_v2616_export.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_16_DIAGNOSTICS_EXPORT_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_17_FORWARD_AUTOAGENDA_STANDALONE.js"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


AUTOAGENDA = r'''
// v2.6.17 — autoagenda privada por mensaje reenviado a WhatsApp.
// Formato esperado (3 líneas):
//   Jueves 9y20
//   Segundo Aroca
//   0968483776
// Solo números expresamente autorizados pueden escribir en la agenda.
const AUTOAGENDA_SOURCE_PREFIX = "mobile:autoagenda:wa:";
const AUTOAGENDA_WEEKDAYS = new Map([
  ["domingo", 0], ["lunes", 1], ["martes", 2], ["miercoles", 3],
  ["jueves", 4], ["viernes", 5], ["sabado", 6]
]);
function autoagendaNormalizeText(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
}
function autoagendaAuthorizedPhones(env) {
  const raw = [
    env.AUTOAGENDA_AUTHORIZED_PHONES,
    env.AUTOAGENDA_TEST_PHONE,
    env.WHATSAPP_TEST_PHONE,
    env.RECEPTION_PHONE,
    env.ADMIN_PHONE
  ].filter(Boolean).join(",");
  const out = new Set();
  for (const item of raw.split(/[\s,;]+/)) {
    const p = normalizePhone(item);
    if (p) out.add(p);
  }
  return out;
}
function autoagendaSenderAuthorized(env, phone) {
  const normalized = normalizePhone(phone);
  return Boolean(normalized && autoagendaAuthorizedPhones(env).has(normalized));
}
function autoagendaLooksLikeCommand(raw) {
  const lines = String(raw || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  if (lines.length !== 3) return false;
  const first = autoagendaNormalizeText(lines[0]).toLowerCase();
  const startsDay = [...AUTOAGENDA_WEEKDAYS.keys()].some(d => first.startsWith(d + " "));
  const digits = String(lines[2] || "").replace(/\D/g, "");
  return startsDay && digits.length >= 9;
}
function autoagendaClockParts() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Guayaquil", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  }).formatToParts(new Date());
  const x = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return {
    today: `${x.year}-${x.month}-${x.day}`,
    time: `${x.hour}:${x.minute}`
  };
}
function autoagendaIsoDate(d) {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}
function autoagendaNextDate(targetDow, time) {
  const now = autoagendaClockParts();
  const base = bookingDateObj(now.today);
  if (!base) return "";
  let delta = (targetDow - base.getUTCDay() + 7) % 7;
  if (delta === 0 && time <= now.time) delta = 7;
  const next = new Date(base.getTime() + delta * 86400000);
  return autoagendaIsoDate(next);
}
function parseAutoagendaForward(raw) {
  const lines = String(raw || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  if (lines.length !== 3) return { ok: false, error: "El mensaje debe tener exactamente 3 líneas: día/hora, paciente y celular." };
  const first = autoagendaNormalizeText(lines[0]).toLowerCase().replace(/\s+/g, " ");
  const m = /^(domingo|lunes|martes|miercoles|jueves|viernes|sabado)\s+(\d{1,2})(?:\s*(?:y|:|\.)\s*(\d{1,2}))?$/.exec(first);
  if (!m) return { ok: false, error: "No pude entender el día y la hora. Ejemplo: Jueves 9y20." };
  const dow = AUTOAGENDA_WEEKDAYS.get(m[1]);
  let hour = Number(m[2]);
  const minute = m[3] == null ? 0 : Number(m[3]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || minute < 0 || minute > 59) return { ok: false, error: "La hora no es válida." };
  if (hour >= 1 && hour <= 5) hour += 12;
  if (hour < 0 || hour > 23) return { ok: false, error: "La hora no es válida." };
  const time = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  const date = autoagendaNextDate(dow, time);
  const name = bookingCleanName(lines[1]);
  const phone = bookingCleanPhone(lines[2]);
  if (name.length < 5) return { ok: false, error: "No pude identificar correctamente el nombre del paciente." };
  if (!phone) return { ok: false, error: "El celular del paciente debe tener 10 dígitos y comenzar con 09." };
  if (!date || !bookingValidDay(date) || !bookingDateWithinHorizon(date) || !BOOKING_TIMES.has(time)) {
    return { ok: false, error: `El horario ${m[1]} ${time} no está habilitado en la agenda.` };
  }
  return { ok: true, weekday: m[1], name, phone, date, time };
}
function autoagendaReply(parsed, status) {
  const detail = `${parsed.name}\n${dateLabel(parsed.date)}\n${timeLabel(parsed.time)}\n${parsed.phone}`;
  if (status === "CREATED") return `CITA AGENDADA\n\n${detail}\n\nLa cita se registró correctamente.`;
  if (status === "ALREADY_EXISTS") return `CITA YA REGISTRADA\n\n${detail}\n\nEsa cita ya estaba en la agenda. No se creó un duplicado.`;
  if (status === "DUPLICATE_MESSAGE") return `MENSAJE YA PROCESADO\n\n${detail}\n\nNo se creó un duplicado.`;
  return `HORARIO OCUPADO\n\n${dateLabel(parsed.date)}\n${timeLabel(parsed.time)}\n\nNo se creó ninguna cita.`;
}
async function autoagendaApply(env, parsed, messageId) {
  const digest = await sha256(String(messageId || `${parsed.date}|${parsed.time}|${parsed.phone}|${parsed.name}`));
  const sourceHash = AUTOAGENDA_SOURCE_PREFIX + digest.slice(0, 32);
  return withClient(env, async client => {
    await client.query("BEGIN");
    try {
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`${parsed.date}|${parsed.time}`]);
      const repeated = await client.query(`SELECT id FROM public.confirmafy_agenda_items WHERE source_hash=$1 LIMIT 1`, [sourceHash]);
      if (repeated.rows?.length) {
        await client.query("ROLLBACK");
        return "DUPLICATE_MESSAGE";
      }
      const occ = await client.query(`SELECT kind,id,nombre,celular FROM (
        SELECT 'appointment'::text kind,a.id,p.nombre,p.celular
        FROM public.appointments a JOIN public.patients p ON p.id=a.patient_id
        WHERE a.fecha=$1::date AND a.hora=$2 AND upper(coalesce(a.estado,'')) NOT IN ('CANCELADA','CANCELADO') AND coalesce(a.origen,'') <> 'CONFIRMAFY_ATENDIDO'
        UNION ALL
        SELECT 'staged'::text kind,c.id,c.nombre,c.celular
        FROM public.confirmafy_agenda_items c
        WHERE c.fecha=$1::date AND c.hora=$2
      ) q`, [parsed.date, parsed.time]);
      if (occ.rows?.length) {
        const same = occ.rows.some(x => bookingCleanPhone(x.celular || "") === parsed.phone);
        await client.query("ROLLBACK");
        return same ? "ALREADY_EXISTS" : "SLOT_TAKEN";
      }
      await client.query(`INSERT INTO public.confirmafy_agenda_items(nombre,celular,fecha,hora,duracion,source_hash,created_at)
        VALUES($1,$2,$3::date,$4,20,$5,now())`, [parsed.name, parsed.phone, parsed.date, parsed.time, sourceHash]);
      await client.query("COMMIT");
      return "CREATED";
    } catch (e) {
      try { await client.query("ROLLBACK"); } catch {}
      throw e;
    }
  });
}
async function handleAutoagendaForward(env, message, ctx) {
  if (message?.type !== "text") return false;
  const body = String(message?.text?.body || "").trim();
  if (!autoagendaLooksLikeCommand(body)) return false;
  const sender = String(message?.from || "");
  if (!autoagendaSenderAuthorized(env, sender)) return false;
  const parsed = parseAutoagendaForward(body);
  if (!parsed.ok) {
    try {
      await sendTextMeta(sender, `NO SE AGENDÓ\n\n${parsed.error}\n\nFormato esperado:\nJueves 9y20\nApellidos y nombres\n09XXXXXXXX`, env, String(message?.id || ""));
    } catch (e) { console.error("autoagenda_parse_reply_failed", e); }
    return true;
  }
  let status = "";
  try {
    status = await autoagendaApply(env, parsed, String(message?.id || ""));
  } catch (e) {
    console.error("autoagenda_apply_failed", e);
    try { await sendTextMeta(sender, "NO SE AGENDÓ\n\nOcurrió un problema al consultar la agenda. No se creó ninguna cita.", env, String(message?.id || "")); } catch {}
    return true;
  }
  try { await sendTextMeta(sender, autoagendaReply(parsed, status), env, String(message?.id || "")); }
  catch (e) { console.error("autoagenda_reply_failed", e); }
  if (status === "CREATED" && ctx?.waitUntil) ctx.waitUntil(runScheduler(env).catch(e => console.error("autoagenda_confirmation_background_failed", e)));
  return true;
}
'''


def main() -> None:
    subprocess.run([sys.executable, str(V2616_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    require('worker_version: "2.6.16"' in text, "Fuente no es Worker 2.6.16")
    require('diagnostics_export: "cf_token_aesgcm_v1"' in text, "Falta exportador diagnóstico v2.6.16")

    marker = "var whatsapp_worker_v2_6_responses_default = {\n"
    require(text.count(marker) == 1, "Objeto principal ambiguo")
    text = text.replace(marker, AUTOAGENDA + "\n" + marker, 1)

    require(text.count("async function receiveWebhook(request, env) {") == 1, "Firma de webhook inesperada")
    text = text.replace("async function receiveWebhook(request, env) {", "async function receiveWebhook(request, env, ctx) {", 1)

    loop_anchor = "  for (const m2 of messages) {\n    const p2 = parseActionPayload(extractPayload(m2));"
    loop_patch = "  for (const m2 of messages) {\n    if (m2?.type === \"text\") {\n      try { if (await handleAutoagendaForward(env, m2, ctx)) continue; }\n      catch (e) { console.error(\"whatsapp_autoagenda_forward_failed\", e); }\n    }\n    const p2 = parseActionPayload(extractPayload(m2));"
    require(text.count(loop_anchor) == 1, "Bucle de mensajes cambió")
    text = text.replace(loop_anchor, loop_patch, 1)

    call_anchor = 'if (request.method === "POST") return receiveWebhook(request, env);'
    require(text.count(call_anchor) == 1, "Llamada webhook cambió")
    text = text.replace(call_anchor, 'if (request.method === "POST") return receiveWebhook(request, env, ctx);', 1)

    text = text.replace('worker_version: "2.6.16"', 'worker_version: "2.6.17"', 1)
    health_anchor = 'diagnostics_export: "cf_token_aesgcm_v1"'
    require(text.count(health_anchor) == 1, "Health diagnóstico ambiguo")
    text = text.replace(health_anchor, 'diagnostics_export: "cf_token_aesgcm_v1", autoagenda_forward: "authorized_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.16"', '"Dr-Revelo-WhatsApp-Worker/2.6.17"', 1)

    for needle in [
        "AUTOAGENDA_SOURCE_PREFIX",
        "handleAutoagendaForward",
        "autoagendaSenderAuthorized",
        "CITA YA REGISTRADA",
        "pg_advisory_xact_lock",
        'autoagenda_forward: "authorized_v1"',
        'worker_version: "2.6.17"',
        'diagnostics_export: "cf_token_aesgcm_v1"',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2617_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
