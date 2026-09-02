from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2620_BUILDER = ROOT / "build" / "whatsapp_v2620_weekly_appointment_guard" / "build_worker_v2620.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_20_WEEKLY_APPOINTMENT_GUARD_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_21_AMPM_PARSER_STANDALONE.js"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PARSER_V2621 = r'''function parseAutoagendaForward(raw) {
  const lines = String(raw || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  if (lines.length !== 3) return { ok: false, error: "El mensaje debe tener exactamente 3 líneas: día/hora, paciente y celular." };
  const first = autoagendaNormalizeText(lines[0]).toLowerCase().replace(/\s+/g, " ");
  // Acepta los formatos históricos (9y20, 9:20, 9.20) y también AM/PM:
  // 11am, 11 am, 11a.m., 11:00am, 3pm, 3:20 pm, etc.
  const m = /^(domingo|lunes|martes|miercoles|jueves|viernes|sabado)\s+(\d{1,2})(?:\s*(?:y|:|\.)\s*(\d{1,2}))?\s*(?:(a|p)\s*\.?\s*m\.?)?$/.exec(first);
  if (!m) return { ok: false, error: "No pude entender el día y la hora. Ejemplos: Jueves 9y20 o Jueves 11am." };
  const dow = AUTOAGENDA_WEEKDAYS.get(m[1]);
  let hour = Number(m[2]);
  const minute = m[3] == null ? 0 : Number(m[3]);
  const meridiem = m[4] || "";
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || minute < 0 || minute > 59) return { ok: false, error: "La hora no es válida." };
  if (meridiem) {
    if (hour < 1 || hour > 12) return { ok: false, error: "La hora con AM/PM debe estar entre 1 y 12." };
    if (meridiem === "a") hour = hour === 12 ? 0 : hour;
    else hour = hour === 12 ? 12 : hour + 12;
  } else {
    // Conserva exactamente el comportamiento anterior para mensajes sin AM/PM.
    if (hour >= 1 && hour <= 5) hour += 12;
  }
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
'''


def main() -> None:
    subprocess.run([sys.executable, str(V2620_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    require('worker_version: "2.6.20"' in text, "Fuente no es Worker 2.6.20")
    require('autoagenda_week_guard: "monday_sunday_v1"' in text, "Falta guardia semanal v2.6.20")
    require('autoagenda_ui: "emoji_v1"' in text, "Falta UI con emojis")
    require('autoagenda_enrollment: "one_time_v1"' in text, "Falta autorización privada")

    start = text.index("function parseAutoagendaForward(raw) {")
    end = text.index("function autoagendaReply(parsed, status) {", start)
    require(start >= 0 and end > start, "Parser autoagenda ambiguo")
    old = text[start:end]
    require("(?:\\s*(?:y|:|\\.)\\s*(\\d{1,2}))?$" in old, "Parser histórico cambió inesperadamente")
    text = text[:start] + PARSER_V2621 + text[end:]

    health_anchor = 'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_week_guard: "monday_sunday_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0'
    require(text.count(health_anchor) == 1, "Health v2.6.20 cambió")
    text = text.replace(
        health_anchor,
        'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_week_guard: "monday_sunday_v1", autoagenda_time_parser: "ampm_v2", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0',
        1,
    )

    require(text.count('worker_version: "2.6.20"') == 1, "Versión v2.6.20 ambigua")
    text = text.replace('worker_version: "2.6.20"', 'worker_version: "2.6.21"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.20"', '"Dr-Revelo-WhatsApp-Worker/2.6.21"')

    for needle in [
        'worker_version: "2.6.21"',
        'autoagenda_time_parser: "ampm_v2"',
        'autoagenda_week_guard: "monday_sunday_v1"',
        'autoagenda_enrollment: "one_time_v1"',
        'autoagenda_ui: "emoji_v1"',
        'const meridiem = m[4] || "";',
        'hour = hour === 12 ? 0 : hour',
        'hour = hour === 12 ? 12 : hour + 12',
        'Jueves 9y20 o Jueves 11am',
        'SAME_WEEK_APPOINTMENT',
        '📅 YA TIENE CITA ESTA SEMANA',
        '✅ CITA AGENDADA',
        'diagnostics_export: "cf_token_aesgcm_v1"',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2621_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
