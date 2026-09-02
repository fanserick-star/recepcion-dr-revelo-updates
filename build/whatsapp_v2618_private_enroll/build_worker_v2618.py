from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2617_BUILDER = ROOT / "build" / "whatsapp_v2617_forward_autoagenda" / "build_worker_v2617.py"
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_17_FORWARD_AUTOAGENDA_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_18_PRIVATE_ENROLL_STANDALONE.js"

ENROLL_TOKEN_SHA256 = "5c530fb52e16fff4888e798f15c9503dd581be9169153a16d9801398659112c5"
ENROLL_EXPIRES_UTC = "2026-09-03T04:00:00Z"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


PRIVATE_ENROLL = rf'''
// v2.6.18 — enrolamiento privado de un número administrador sin publicarlo en GitHub.
const AUTOAGENDA_ENROLL_TOKEN_SHA256 = "{ENROLL_TOKEN_SHA256}";
const AUTOAGENDA_ENROLL_EXPIRES_UTC = "{ENROLL_EXPIRES_UTC}";
const AUTOAGENDA_ENROLL_PREFIX = "AUTORIZAR AGENDA ";
async function autoagendaEnsureAuthTable(env) {{
  return withClient(env, async client => {{
    await client.query(`CREATE TABLE IF NOT EXISTS public.whatsapp_autoagenda_authorized (
      phone text PRIMARY KEY,
      authorized_at timestamptz NOT NULL DEFAULT now(),
      source text NOT NULL DEFAULT 'one_time_code'
    )`);
    return true;
  }});
}}
async function autoagendaDbAuthorized(env, phone) {{
  const normalized = normalizePhone(phone);
  if (!normalized || !env.DATABASE_URL) return false;
  try {{
    return await withClient(env, async client => {{
      await client.query(`CREATE TABLE IF NOT EXISTS public.whatsapp_autoagenda_authorized (
        phone text PRIMARY KEY,
        authorized_at timestamptz NOT NULL DEFAULT now(),
        source text NOT NULL DEFAULT 'one_time_code'
      )`);
      const r = await client.query(`SELECT 1 FROM public.whatsapp_autoagenda_authorized WHERE phone=$1 LIMIT 1`, [normalized]);
      return Boolean(r.rows?.length);
    }});
  }} catch (e) {{
    console.error("autoagenda_auth_lookup_failed", String(e?.name || "Error"));
    return false;
  }}
}}
async function handleAutoagendaEnrollment(env, message) {{
  if (message?.type !== "text") return false;
  const body = String(message?.text?.body || "").trim();
  if (!body.toUpperCase().startsWith(AUTOAGENDA_ENROLL_PREFIX)) return false;
  const sender = String(message?.from || "");
  const normalized = normalizePhone(sender);
  if (!normalized) return true;
  const code = body.slice(AUTOAGENDA_ENROLL_PREFIX.length).trim();
  if (Date.now() > Date.parse(AUTOAGENDA_ENROLL_EXPIRES_UTC)) {{
    try {{ await sendTextMeta(sender, "AUTORIZACIÓN CERRADA\n\nEl código de autorización ya venció.", env, String(message?.id || "")); }} catch {{}}
    return true;
  }}
  if (await sha256(code) !== AUTOAGENDA_ENROLL_TOKEN_SHA256) {{
    try {{ await sendTextMeta(sender, "AUTORIZACIÓN RECHAZADA\n\nEl código no es válido.", env, String(message?.id || "")); }} catch {{}}
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
        await client.query("SELECT pg_advisory_xact_lock(hashtext('whatsapp_autoagenda_authorized_enroll'))");
        const all = await client.query(`SELECT phone FROM public.whatsapp_autoagenda_authorized ORDER BY authorized_at ASC LIMIT 2`);
        if (all.rows?.length) {{
          const same = all.rows.some(x => normalizePhone(x.phone || "") === normalized);
          await client.query("ROLLBACK");
          return same ? "ALREADY" : "CLOSED";
        }}
        await client.query(`INSERT INTO public.whatsapp_autoagenda_authorized(phone,source) VALUES($1,'one_time_code')`, [normalized]);
        await client.query("COMMIT");
        return "AUTHORIZED";
      }} catch (e) {{
        try {{ await client.query("ROLLBACK"); }} catch {{}}
        throw e;
      }}
    }});
    const text = result === "AUTHORIZED"
      ? "AUTOAGENDA AUTORIZADA\n\nEste WhatsApp ya puede reenviar citas al sistema."
      : result === "ALREADY"
        ? "AUTOAGENDA YA AUTORIZADA\n\nEste WhatsApp ya estaba habilitado."
        : "AUTORIZACIÓN CERRADA\n\nYa existe un WhatsApp administrador autorizado.";
    try {{ await sendTextMeta(sender, text, env, String(message?.id || "")); }} catch (e) {{ console.error("autoagenda_enroll_reply_failed", e); }}
    return true;
  }} catch (e) {{
    console.error("autoagenda_enroll_failed", e);
    try {{ await sendTextMeta(sender, "AUTORIZACIÓN NO COMPLETADA\n\nNo pude guardar la autorización. Intente nuevamente.", env, String(message?.id || "")); }} catch {{}}
    return true;
  }}
}}
'''


def main() -> None:
    subprocess.run([sys.executable, str(V2617_BUILDER)], cwd=ROOT, check=True)
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    require('worker_version: "2.6.17"' in text, "Fuente no es Worker 2.6.17")
    require('autoagenda_forward: "authorized_v1"' in text, "Falta autoagenda v2.6.17")

    marker = "var whatsapp_worker_v2_6_responses_default = {\n"
    require(text.count(marker) == 1, "Objeto principal ambiguo")
    text = text.replace(marker, PRIVATE_ENROLL + "\n" + marker, 1)

    auth_anchor = "  if (!autoagendaSenderAuthorized(env, sender)) return false;"
    require(text.count(auth_anchor) == 1, "Control de autorización v2.6.17 cambió")
    text = text.replace(auth_anchor, "  if (!autoagendaSenderAuthorized(env, sender) && !await autoagendaDbAuthorized(env, sender)) return false;", 1)

    inbound_anchor = '    if (m2?.type === "text") {\n      try { if (await handleAutoagendaForward(env, m2, ctx)) continue; }'
    inbound_patch = '    if (m2?.type === "text") {\n      try { if (await handleAutoagendaEnrollment(env, m2)) continue; }\n      catch (e) { console.error("whatsapp_autoagenda_enrollment_failed", e); }\n      try { if (await handleAutoagendaForward(env, m2, ctx)) continue; }'
    require(text.count(inbound_anchor) == 1, "Entrada de texto v2.6.17 cambió")
    text = text.replace(inbound_anchor, inbound_patch, 1)

    health_anchor = 'autoagenda_forward: "authorized_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0'
    require(text.count(health_anchor) == 1, "Health autoagenda ambiguo")
    text = text.replace(health_anchor, 'autoagenda_forward: "authorized_v1", autoagenda_enrollment: "one_time_v1", autoagenda_configured: autoagendaAuthorizedPhones(env).size > 0', 1)

    text = text.replace('worker_version: "2.6.17"', 'worker_version: "2.6.18"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.17"', '"Dr-Revelo-WhatsApp-Worker/2.6.18"', 1)

    for needle in [
        'worker_version: "2.6.18"',
        'autoagenda_enrollment: "one_time_v1"',
        'handleAutoagendaEnrollment',
        'whatsapp_autoagenda_authorized',
        'AUTOAGENDA_ENROLL_TOKEN_SHA256',
        'autoagendaDbAuthorized',
        'CITA YA REGISTRADA',
        'diagnostics_export: "cf_token_aesgcm_v1"',
    ]:
        require(needle in text, f"Falta validación: {needle}")

    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2618_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
