from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2621_BUILDER = ROOT / "build" / "whatsapp_v2621_ampm_parser" / "build_worker_v2621.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_21_AMPM_PARSER_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_23_AUTOAGENDA_RECOVERY_STANDALONE.js"

RECOVERY_TOKEN_SHA256 = "50cb4ec7de8362197ab5accb0681a26a2410179d1953694fa162f7c6d202a480"
RECOVERY_EXPIRES_UTC = "2026-10-03T05:00:00Z"
RECOVERY_SOURCE = "recovery_20260929_v1"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


RECOVERY_JS = rf'''
// v2.6.23 — recuperación privada de la autorización de autoagenda.
// El código real nunca se publica: solo se guarda su SHA-256 y el primer uso gana.
const AUTOAGENDA_RECOVERY_TOKEN_SHA256 = "{RECOVERY_TOKEN_SHA256}";
const AUTOAGENDA_RECOVERY_EXPIRES_UTC = "{RECOVERY_EXPIRES_UTC}";
const AUTOAGENDA_RECOVERY_PREFIX = "RECUPERAR AGENDA ";
const AUTOAGENDA_RECOVERY_SOURCE = "{RECOVERY_SOURCE}";

async function handleAutoagendaRecovery(env, message) {{
  if (message?.type !== "text") return false;
  const body = String(message?.text?.body || "").trim();
  if (!body.toUpperCase().startsWith(AUTOAGENDA_RECOVERY_PREFIX)) return false;

  const sender = String(message?.from || "");
  const normalized = normalizePhone(sender);
  if (!normalized) return true;

  const code = body.slice(AUTOAGENDA_RECOVERY_PREFIX.length).trim();
  if (Date.now() > Date.parse(AUTOAGENDA_RECOVERY_EXPIRES_UTC)) {{
    try {{ await sendTextMeta(sender, "RECUPERACIÓN CERRADA\\n\\nEl código de recuperación ya venció.", env, String(message?.id || "")); }} catch {{}}
    return true;
  }}

  if (await sha256(code) !== AUTOAGENDA_RECOVERY_TOKEN_SHA256) {{
    try {{ await sendTextMeta(sender, "RECUPERACIÓN RECHAZADA\\n\\nEl código no es válido.", env, String(message?.id || "")); }} catch {{}}
    return true;
  }}

  try {{
    const result = await withClient(env, async client => {{
      await client.query(`CREATE TABLE IF NOT EXISTS public.whatsapp_autoagenda_authorized (
        phone text PRIMARY KEY,
        authorized_at timestamptz NOT NULL DEFAULT now(),
        source text NOT NULL DEFAULT 'one_time_code'
      )`);

      await client.query("BEGIN");
      try {{
        await client.query("SELECT pg_advisory_xact_lock(hashtext('whatsapp_autoagenda_recovery_20260929'))");

        const used = await client.query(
          `SELECT phone FROM public.whatsapp_autoagenda_authorized WHERE source=$1 ORDER BY authorized_at ASC LIMIT 1`,
          [AUTOAGENDA_RECOVERY_SOURCE]
        );
        if (used.rows?.length) {{
          const same = normalizePhone(used.rows[0]?.phone || "") === normalized;
          await client.query("ROLLBACK");
          return same ? "ALREADY" : "CLOSED";
        }}

        // La recuperación reemplaza únicamente la autorización administrativa de autoagenda.
        // No modifica pacientes, citas, agenda, mensajes ni historiales.
        await client.query(`DELETE FROM public.whatsapp_autoagenda_authorized`);
        await client.query(
          `INSERT INTO public.whatsapp_autoagenda_authorized(phone,source)
           VALUES($1,$2)
           ON CONFLICT(phone) DO UPDATE SET authorized_at=now(), source=excluded.source`,
          [normalized, AUTOAGENDA_RECOVERY_SOURCE]
        );

        await client.query("COMMIT");
        return "RECOVERED";
      }} catch (e) {{
        try {{ await client.query("ROLLBACK"); }} catch {{}}
        throw e;
      }}
    }});

    const reply = result === "RECOVERED"
      ? "✅ AUTOAGENDA RECUPERADA\\n\\nEste WhatsApp volvió a quedar autorizado para reenviar citas al sistema."
      : result === "ALREADY"
        ? "✅ AUTOAGENDA YA RECUPERADA\\n\\nEste WhatsApp ya quedó autorizado."
        : "RECUPERACIÓN CERRADA\\n\\nEl código de recuperación ya fue utilizado.";

    try {{ await sendTextMeta(sender, reply, env, String(message?.id || "")); }}
    catch (e) {{ console.error("autoagenda_recovery_reply_failed", e); }}
    return true;
  }} catch (e) {{
    console.error("autoagenda_recovery_failed", e);
    try {{
      await sendTextMeta(sender, "RECUPERACIÓN NO COMPLETADA\\n\\nNo pude guardar la autorización. Intente nuevamente.", env, String(message?.id || ""));
    }} catch {{}}
    return true;
  }}
}}
'''


def main() -> None:
    subprocess.run([sys.executable, str(V2621_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")

    require('worker_version: "2.6.21"' in text, "Fuente no es Worker 2.6.21")
    require('autoagenda_forward: "authorized_v1"' in text, "Falta autoagenda privada")
    require('autoagenda_enrollment: "one_time_v1"' in text, "Falta enrolamiento persistente")
    require('autoagenda_time_parser: "ampm_v2"' in text, "Falta parser AM/PM")
    require('autoagenda_week_guard: "monday_sunday_v1"' in text, "Falta guardia semanal")
    require('diagnostics_export: "cf_token_aesgcm_v1"' in text, "Falta diagnóstico cifrado")

    require("b.created_at AT TIME ZONE 'UTC'" in text, "El scheduler no interpreta created_at como UTC")
    require("((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date" in text,
            "Falta conversión de fecha local Ecuador")

    grace_old = "CASE WHEN kind='cita_agendada' THEN interval '1 hour' ELSE interval '4 hours' END"
    grace_new = "CASE WHEN kind='cita_agendada' THEN interval '12 hours' ELSE interval '4 hours' END"
    require(text.count(grace_old) == 1, "Ventana de recuperación de cita_agendada cambió")
    text = text.replace(grace_old, grace_new, 1)

    forward_anchor = "async function handleAutoagendaForward(env, message, ctx) {"
    require(text.count(forward_anchor) == 1, "handleAutoagendaForward ambiguo")
    text = text.replace(forward_anchor, RECOVERY_JS + "\n" + forward_anchor, 1)

    inbound_anchor = (
        '    if (m2?.type === "text") {\n'
        '      try { if (await handleAutoagendaEnrollment(env, m2)) continue; }\n'
        '      catch (e) { console.error("whatsapp_autoagenda_enrollment_failed", e); }\n'
        '      try { if (await handleAutoagendaForward(env, m2, ctx)) continue; }'
    )
    inbound_patch = (
        '    if (m2?.type === "text") {\n'
        '      try { if (await handleAutoagendaRecovery(env, m2)) continue; }\n'
        '      catch (e) { console.error("whatsapp_autoagenda_recovery_failed", e); }\n'
        '      try { if (await handleAutoagendaEnrollment(env, m2)) continue; }\n'
        '      catch (e) { console.error("whatsapp_autoagenda_enrollment_failed", e); }\n'
        '      try { if (await handleAutoagendaForward(env, m2, ctx)) continue; }'
    )
    require(text.count(inbound_anchor) == 1, "Entrada de texto cambió")
    text = text.replace(inbound_anchor, inbound_patch, 1)

    health_anchor = (
        'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", '
        'autoagenda_week_guard: "monday_sunday_v1", autoagenda_time_parser: "ampm_v2", '
        'autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0'
    )
    require(text.count(health_anchor) == 1, "Health v2.6.21 cambió")
    text = text.replace(
        health_anchor,
        'autoagenda_enrollment: "one_time_v1", autoagenda_ui: "emoji_v1", '
        'autoagenda_week_guard: "monday_sunday_v1", autoagenda_time_parser: "ampm_v2", '
        'scheduler_created_at_timezone: "utc_storage_v1", '
        'scheduler_booking_grace: "12h_v1", '
        'autoagenda_recovery: "one_time_reclaim_v1", '
        'autoagenda_authorization_mode: "env_or_db_v2", '
        'autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0',
        1,
    )

    require(text.count('worker_version: "2.6.21"') == 1, "Versión v2.6.21 ambigua")
    text = text.replace('worker_version: "2.6.21"', 'worker_version: "2.6.23"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.21"', '"Dr-Revelo-WhatsApp-Worker/2.6.23"')

    for needle in [
        'worker_version: "2.6.23"',
        'scheduler_created_at_timezone: "utc_storage_v1"',
        'scheduler_booking_grace: "12h_v1"',
        'autoagenda_recovery: "one_time_reclaim_v1"',
        'autoagenda_authorization_mode: "env_or_db_v2"',
        'AUTOAGENDA_RECOVERY_TOKEN_SHA256',
        'handleAutoagendaRecovery',
        RECOVERY_SOURCE,
        'autoagenda_forward: "authorized_v1"',
        'autoagenda_enrollment: "one_time_v1"',
        'autoagenda_time_parser: "ampm_v2"',
        'autoagenda_week_guard: "monday_sunday_v1"',
        'diagnostics_export: "cf_token_aesgcm_v1"',
        "b.created_at AT TIME ZONE 'UTC'",
    ]:
        require(needle in text, f"Falta validación: {needle}")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2623_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
