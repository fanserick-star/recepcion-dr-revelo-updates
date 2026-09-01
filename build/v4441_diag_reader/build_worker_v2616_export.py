from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_15_DIAGNOSTICS_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_16_DIAGNOSTICS_EXPORT_STANDALONE.js"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


INTERNAL = r'''
// v2.6.16 — exportador interno cifrado de diagnósticos.
// Solo acepta un Cloudflare API Token con acceso al Worker de ESTA cuenta.
// Nunca devuelve incidentes en claro: cada registro se cifra AES-GCM con una
// clave derivada del INC de 128 bits. El artifact público solo contiene ciphertext.
const DIAGNOSTIC_CF_ACCOUNT_ID = "__CF_ACCOUNT_ID__";
const DIAGNOSTIC_CF_WORKER_NAME = "dr-revelo-whatsapp-cloud";
function bytesToBase64(bytes) {
  let s = "";
  const a = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (let i = 0; i < a.length; i += 0x8000) s += String.fromCharCode(...a.subarray(i, i + 0x8000));
  return btoa(s);
}
async function diagnosticInternalAuthorized(request) {
  const auth = String(request.headers.get("authorization") || "").trim();
  if (!auth.startsWith("Bearer ") || auth.length < 30) return false;
  if (!/^[0-9a-f]{32}$/i.test(DIAGNOSTIC_CF_ACCOUNT_ID)) return false;
  try {
    const r = await fetch(`https://api.cloudflare.com/client/v4/accounts/${DIAGNOSTIC_CF_ACCOUNT_ID}/workers/scripts/${DIAGNOSTIC_CF_WORKER_NAME}/settings`, {
      headers: { Authorization: auth, Accept: "application/json" }
    });
    return r.ok;
  } catch {
    return false;
  }
}
async function encryptDiagnosticRow(row) {
  const incidentId = String(row.incident_id || "").trim().toUpperCase();
  if (!DIAGNOSTIC_LONG_ID_RE.test(incidentId)) return null;
  const keyBytes = await crypto.subtle.digest("SHA-256", encoder.encode(incidentId));
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plain = encoder.encode(JSON.stringify({
    incident_id: incidentId,
    received_at: row.received_at || null,
    source_created_epoch: Number(row.source_created_epoch || 0),
    package_version: String(row.package_version || ""),
    app_version: String(row.app_version || ""),
    launcher_version: String(row.launcher_version || ""),
    stage: String(row.stage || ""),
    error_class: String(row.error_class || ""),
    error_message: String(row.error_message || "").slice(0, 6000),
    launcher_log: String(row.launcher_log || "").slice(-48000),
    backend_log: String(row.backend_log || "").slice(-48000),
    update_state: String(row.update_state || "").slice(-16000)
  }));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plain);
  return {
    incident_hash: await sha256(incidentId),
    iv_b64: bytesToBase64(iv),
    ciphertext_b64: bytesToBase64(new Uint8Array(encrypted))
  };
}
async function serveDiagnosticInternalExport(request, env) {
  if (request.method !== "GET") return diagnosticJson({ ok: false, error: "not_found" }, 404);
  if (!await diagnosticInternalAuthorized(request)) return diagnosticJson({ ok: false, error: "not_found" }, 404);
  if (!env.DATABASE_URL) return diagnosticJson({ ok: false, error: "diagnostic_unavailable" }, 503);
  try {
    return await withClient(env, async (client) => {
      const r = await client.query(`SELECT
          incident_id, received_at, source_created_epoch, package_version, app_version,
          launcher_version, stage, error_class, error_message, launcher_log,
          backend_log, update_state
        FROM public.rp_diagnostics_incidents
        WHERE received_at > now() - interval '24 hours'
          AND incident_id ~ '^INC-[0-9]{8}-[0-9]{6}-[A-F0-9]{32}$'
        ORDER BY received_at DESC
        LIMIT 5`);
      const entries = [];
      for (const row of r.rows || []) {
        const item = await encryptDiagnosticRow(row);
        if (item) entries.push(item);
      }
      return diagnosticJson({ ok: true, format: "rp_diag_aesgcm_v1", entries });
    });
  } catch (e) {
    console.error("diagnostic_internal_export_failed", String(e?.name || "Error"));
    return diagnosticJson({ ok: false, error: "diagnostic_unavailable" }, 503);
  }
}
'''


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n")
    require('worker_version: "2.6.15"' in text, "Fuente no es Worker 2.6.15")
    marker = "var whatsapp_worker_v2_6_responses_default = {\n"
    require(text.count(marker) == 1, "Objeto principal ambiguo")
    text = text.replace(marker, INTERNAL + "\n" + marker, 1)
    route = '    if (u.pathname === "/diagnostics/internal/export") return serveDiagnosticInternalExport(request, env);\n'
    anchor = '    if (u.pathname.startsWith("/diagnostics/")) return serveDiagnosticRead(request, env, u);\n'
    require(text.count(anchor) == 1, "Ruta diagnóstica 2.6.15 cambió")
    text = text.replace(anchor, route + anchor, 1)
    text = text.replace('worker_version: "2.6.15"', 'worker_version: "2.6.16"', 1)
    text = text.replace('diagnostics_read: "capability_v1"', 'diagnostics_read: "capability_v1", diagnostics_export: "cf_token_aesgcm_v1"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.15"', '"Dr-Revelo-WhatsApp-Worker/2.6.16"', 1)

    require("__CF_ACCOUNT_ID__" in text, "Falta placeholder de cuenta")
    require("AES-GCM" in text and "rp_diag_aesgcm_v1" in text, "Falta cifrado")
    require("LIMIT 5" in text and "24 hours" in text, "Exportación no está acotada")
    require("incident_hash" in text and "ciphertext_b64" in text, "Formato cifrado incompleto")
    require("serveDiagnosticInternalExport" in text, "Falta endpoint interno")
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_V2616_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    main()
