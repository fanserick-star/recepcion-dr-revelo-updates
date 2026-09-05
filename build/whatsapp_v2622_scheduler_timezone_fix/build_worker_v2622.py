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


def scheduler_excerpt(text: str) -> str:
    start = text.find("async function dueCandidates")
    if start >= 0:
        end = text.find("function materializeCandidate", start)
        if end < 0:
            end = min(len(text), start + 7000)
        return text[start:end]
    i = text.find("cita_agendada")
    if i >= 0:
        return text[max(0, i - 3000):min(len(text), i + 5000)]
    return "SCHEDULER_EXCERPT_NOT_FOUND"


def main() -> None:
    subprocess.run([sys.executable, str(V2621_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")

    require('worker_version: "2.6.21"' in text, "Fuente no es Worker 2.6.21")
    require('autoagenda_time_parser: "ampm_v2"' in text, "Falta parser AM/PM v2.6.21")
    require('autoagenda_week_guard: "monday_sunday_v1"' in text, "Falta guardia semanal")
    require('diagnostics_export: "cf_token_aesgcm_v1"' in text, "Falta diagnóstico cifrado")

    legacy = "b.created_at AT TIME ZONE 'America/Guayaquil'"
    legacy_count = text.count(legacy)
    if legacy_count != 3:
        print("=== SCHEDULER_SQL_DIAGNOSTIC_BEGIN ===")
        print(scheduler_excerpt(text))
        print("=== SCHEDULER_SQL_DIAGNOSTIC_END ===")
    require(legacy_count == 3, f"created_at legacy esperado 3 veces, encontrado {legacy_count}")

    legacy_local_date = f"({legacy})::date"
    fixed_local_date = "((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date"
    require(text.count(legacy_local_date) == 1, "regla de fecha local cambió inesperadamente")
    text = text.replace(legacy_local_date, fixed_local_date, 1)
    require(text.count(legacy) == 2, "due_at/anticipación no quedaron identificados de forma única")
    text = text.replace(legacy, "b.created_at AT TIME ZONE 'UTC'")

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
        fixed_local_date,
        'autoagenda_time_parser: "ampm_v2"',
        'autoagenda_week_guard: "monday_sunday_v1"',
        'autoagenda_enrollment: "one_time_v1"',
        'autoagenda_ui: "emoji_v1"',
        'SAME_WEEK_APPOINTMENT',
        'diagnostics_export: "cf_token_aesgcm_v1"',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    require(legacy not in text, "Quedó una interpretación incorrecta de created_at")
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2622_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
