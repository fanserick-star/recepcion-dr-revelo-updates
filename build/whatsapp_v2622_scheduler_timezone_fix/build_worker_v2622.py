from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2621_BUILDER = ROOT / "build" / "whatsapp_v2621_ampm_parser" / "build_worker_v2621.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_21_AMPM_PARSER_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_22_SCHEDULER_TIMEZONE_FIX_STANDALONE.js"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    subprocess.run([sys.executable, str(V2621_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")

    require('worker_version: "2.6.21"' in text, "Fuente no es Worker 2.6.21")
    require('autoagenda_time_parser: "ampm_v2"' in text, "Falta parser AM/PM v2.6.21")
    require('autoagenda_week_guard: "monday_sunday_v1"' in text, "Falta guardia semanal")
    require('diagnostics_export: "cf_token_aesgcm_v1"' in text, "Falta diagnóstico cifrado")

    # public.appointments.created_at es timestamp WITHOUT time zone y la app lo
    # guarda en UTC. El scheduler anterior lo interpretaba directamente como
    # America/Guayaquil, desplazando el envío inmediato +5 horas.
    old_due = "         b.created_at AT TIME ZONE 'America/Guayaquil',"
    new_due = "         b.created_at AT TIME ZONE 'UTC',"
    require(text.count(old_due) == 1, "due_at de cita_agendada cambió inesperadamente")
    text = text.replace(old_due, new_due, 1)

    old_lead = "          - (b.created_at AT TIME ZONE 'America/Guayaquil') >= interval '24 hours'"
    new_lead = "          - (b.created_at AT TIME ZONE 'UTC') >= interval '24 hours'"
    require(text.count(old_lead) == 1, "cálculo de anticipación cambió inesperadamente")
    text = text.replace(old_lead, new_lead, 1)

    old_date = "    AND (b.created_at AT TIME ZONE 'America/Guayaquil')::date < (b.fecha - 1)"
    new_date = "    AND ((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date < (b.fecha - 1)"
    require(text.count(old_date) == 1, "regla de fecha local cambió inesperadamente")
    text = text.replace(old_date, new_date, 1)

    health_anchor = 'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_week_guard: "monday_sunday_v1", autoagenda_time_parser: "ampm_v2", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0'
    require(text.count(health_anchor) == 1, "Health v2.6.21 cambió")
    text = text.replace(
        health_anchor,
        'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", autoagenda_week_guard: "monday_sunday_v1", autoagenda_time_parser: "ampm_v2", scheduler_created_at_timezone: "utc_storage_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0',
        1,
    )

    require(text.count('worker_version: "2.6.21"') == 1, "Versión v2.6.21 ambigua")
    text = text.replace('worker_version: "2.6.21"', 'worker_version: "2.6.22"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.21"', '"Dr-Revelo-WhatsApp-Worker/2.6.22"')

    for needle in [
        'worker_version: "2.6.22"',
        'scheduler_created_at_timezone: "utc_storage_v1"',
        "b.created_at AT TIME ZONE 'UTC'",
        "((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date",
        'autoagenda_time_parser: "ampm_v2"',
        'autoagenda_week_guard: "monday_sunday_v1"',
        'autoagenda_enrollment: "one_time_v1"',
        'autoagenda_ui: "emoji_v1"',
        'SAME_WEEK_APPOINTMENT',
        'diagnostics_export: "cf_token_aesgcm_v1"',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    require("b.created_at AT TIME ZONE 'America/Guayaquil'," not in text, "Quedó due_at con zona incorrecta")
    require("- (b.created_at AT TIME ZONE 'America/Guayaquil') >= interval '24 hours'" not in text, "Quedó anticipación con zona incorrecta")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2622_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
