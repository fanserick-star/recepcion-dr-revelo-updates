from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2619_BUILDER = ROOT / "build" / "whatsapp_v2619_autoagenda_emojis" / "build_worker_v2619.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_19_AUTOAGENDA_EMOJIS_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_20_WEEKLY_APPOINTMENT_GUARD_STANDALONE.js"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


AUTOAGENDA_WEEKLY = r'''function autoagendaReply(parsed, status) {
  const detail = `${parsed.name}\n${dateLabel(parsed.date)}\n${timeLabel(parsed.time)}\n${parsed.phone}`;
  if (status && typeof status === "object" && status.status === "SAME_WEEK_APPOINTMENT") {
    const existing = status.existing || {};
    return `📅 YA TIENE CITA ESTA SEMANA\n\n${parsed.name}\n${dateLabel(existing.date)}\n${timeLabel(existing.time)}\n\nNo se creó ninguna cita.`;
  }
  if (status === "CREATED") return `✅ CITA AGENDADA\n\n${detail}\n\nLa cita se registró correctamente.`;
  if (status === "ALREADY_EXISTS") return `♻️ CITA YA REGISTRADA\n\n${detail}\n\nEsa cita ya estaba en la agenda. No se creó un duplicado.`;
  if (status === "DUPLICATE_MESSAGE") return `🔁 MENSAJE YA PROCESADO\n\n${detail}\n\nNo se creó un duplicado.`;
  return `⚠️ HORARIO OCUPADO\n\n${dateLabel(parsed.date)}\n${timeLabel(parsed.time)}\n\nNo se creó ninguna cita.`;
}
function autoagendaWeekBounds(dateIso) {
  const d = bookingDateObj(dateIso);
  if (!d) return { start: "", end: "" };
  const delta = (d.getUTCDay() + 6) % 7;
  const monday = new Date(d.getTime() - delta * 86400000);
  const sunday = new Date(monday.getTime() + 6 * 86400000);
  return { start: autoagendaIsoDate(monday), end: autoagendaIsoDate(sunday) };
}
async function autoagendaApply(env, parsed, messageId) {
  const digest = await sha256(String(messageId || `${parsed.date}|${parsed.time}|${parsed.phone}|${parsed.name}`));
  const sourceHash = AUTOAGENDA_SOURCE_PREFIX + digest.slice(0, 32);
  const week = autoagendaWeekBounds(parsed.date);
  if (!week.start || !week.end) throw new Error("invalid_autoagenda_week");
  return withClient(env, async client => {
    await client.query("BEGIN");
    try {
      // Serializa citas simultáneas del mismo paciente/semana y conserva el
      // bloqueo existente del horario exacto. No crea tablas ni índices nuevos.
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`autoagenda-week|${week.start}|${parsed.phone}`]);
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`${parsed.date}|${parsed.time}`]);

      const repeated = await client.query(`SELECT id FROM public.confirmafy_agenda_items WHERE source_hash=$1 LIMIT 1`, [sourceHash]);
      if (repeated.rows?.length) {
        await client.query("ROLLBACK");
        return "DUPLICATE_MESSAGE";
      }

      // Mantiene la precedencia actual: si el bloque exacto está ocupado,
      // primero informa cita ya registrada u horario ocupado.
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

      const weekRows = await client.query(`SELECT kind,id,nombre,celular,fecha,hora FROM (
        SELECT 'appointment'::text kind,a.id,p.nombre,p.celular,a.fecha::text AS fecha,a.hora
        FROM public.appointments a JOIN public.patients p ON p.id=a.patient_id
        WHERE a.fecha BETWEEN $1::date AND $2::date
          AND upper(coalesce(a.estado,'')) NOT IN ('CANCELADA','CANCELADO','NO_ASISTIRA','NO_ASISTIRÁ','REAGENDADA')
          AND coalesce(a.origen,'') <> 'CONFIRMAFY_ATENDIDO'
        UNION ALL
        SELECT 'staged'::text kind,c.id,c.nombre,c.celular,c.fecha::text AS fecha,c.hora
        FROM public.confirmafy_agenda_items c
        WHERE c.fecha BETWEEN $1::date AND $2::date
      ) q ORDER BY fecha,hora,id`, [week.start, week.end]);
      const existing = (weekRows.rows || []).find(x => bookingCleanPhone(x.celular || "") === parsed.phone);
      if (existing) {
        await client.query("ROLLBACK");
        return {
          status: "SAME_WEEK_APPOINTMENT",
          existing: {
            date: String(existing.fecha || "").slice(0, 10),
            time: String(existing.hora || "").slice(0, 5),
            name: String(existing.nombre || parsed.name)
          }
        };
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
'''


def main() -> None:
    subprocess.run([sys.executable, str(V2619_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    require('worker_version: "2.6.19"' in text, "Fuente no es Worker 2.6.19")
    require('autoagenda_ui: "emoji_v1"' in text, "Falta UI v2.6.19")
    require('autoagenda_enrollment: "one_time_v1"' in text, "Falta enrolamiento privado")
    require('async function autoagendaApply(env, parsed, messageId)' in text, "Falta autoagendaApply")

    start = text.index("function autoagendaReply(parsed, status) {")
    end = text.index("async function handleAutoagendaForward", start)
    require(start >= 0 and end > start, "Bloque autoagenda ambiguo")
    text = text[:start] + AUTOAGENDA_WEEKLY + text[end:]

    health_anchor = 'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0'
    require(text.count(health_anchor) == 1, "Health v2.6.19 cambió")
    text = text.replace(
        health_anchor,
        'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_week_guard: "monday_sunday_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0',
        1,
    )

    require(text.count('worker_version: "2.6.19"') == 1, "Versión v2.6.19 ambigua")
    text = text.replace('worker_version: "2.6.19"', 'worker_version: "2.6.20"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.19"', '"Dr-Revelo-WhatsApp-Worker/2.6.20"')

    for needle in [
        'worker_version: "2.6.20"',
        'autoagenda_week_guard: "monday_sunday_v1"',
        'autoagendaWeekBounds',
        'autoagenda-week|${week.start}|${parsed.phone}',
        'SAME_WEEK_APPOINTMENT',
        '📅 YA TIENE CITA ESTA SEMANA',
        "a.fecha BETWEEN $1::date AND $2::date",
        "c.fecha BETWEEN $1::date AND $2::date",
        'autoagenda_enrollment: "one_time_v1"',
        'autoagenda_ui: "emoji_v1"',
        'diagnostics_export: "cf_token_aesgcm_v1"',
        '✅ CITA AGENDADA',
        '♻️ CITA YA REGISTRADA',
        '🔁 MENSAJE YA PROCESADO',
        '⚠️ HORARIO OCUPADO',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2620_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
