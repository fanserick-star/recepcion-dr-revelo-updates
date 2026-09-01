from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "cloudflare" / "whatsapp_worker_v2_6_STANDALONE.js"
OUT = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_15_DIAGNOSTICS_STANDALONE.js"
EXPECTED_SOURCE_BLOB = "f8290214e6f3500de082e54aba5b7722354397de"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


BRIDGE = r'''
// v2.6.15 — puente privado de diagnóstico por código de capacidad.
// No existe listado ni endpoint "latest". Solo se puede leer un incidente
// conociendo exactamente su INC. Los IDs nuevos tienen 128 bits aleatorios.
var DIAGNOSTIC_LONG_ID_RE = /^INC-\d{8}-\d{6}-[A-F0-9]{32}$/;
var DIAGNOSTIC_LEGACY_ID_RE = /^INC-\d{8}-\d{6}-[A-F0-9]{6}$/;
var DIAGNOSTIC_LEGACY_DEADLINE = Date.parse("2026-09-03T00:00:00Z");
function diagnosticIdAllowed(value) {
  const id = String(value || "").trim().toUpperCase();
  if (DIAGNOSTIC_LONG_ID_RE.test(id)) return true;
  return Date.now() < DIAGNOSTIC_LEGACY_DEADLINE && DIAGNOSTIC_LEGACY_ID_RE.test(id);
}
function diagnosticJson(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, max-age=0",
      "x-robots-tag": "noindex, nofollow, noarchive"
    }
  });
}
async function serveDiagnosticRead(request, env, u) {
  if (request.method !== "GET") return diagnosticJson({ ok: false, error: "not_found" }, 404);
  const prefix = "/diagnostics/";
  let id = "";
  try { id = decodeURIComponent(u.pathname.slice(prefix.length)).trim().toUpperCase(); }
  catch { return diagnosticJson({ ok: false, error: "not_found" }, 404); }
  if (!diagnosticIdAllowed(id)) return diagnosticJson({ ok: false, error: "not_found" }, 404);
  if (!env.DATABASE_URL) return diagnosticJson({ ok: false, error: "diagnostic_unavailable" }, 503);
  try {
    return await withClient(env, async (client) => {
      const r = await client.query(`SELECT
          incident_id,
          received_at,
          source_created_epoch,
          package_version,
          app_version,
          launcher_version,
          stage,
          error_class,
          error_message,
          launcher_log,
          backend_log,
          update_state
        FROM public.rp_diagnostics_incidents
        WHERE incident_id=$1
          AND received_at > now() - interval '30 days'
        LIMIT 1`, [id]);
      if (!r.rows?.length) return diagnosticJson({ ok: false, error: "not_found" }, 404);
      const row = r.rows[0];
      return diagnosticJson({
        ok: true,
        incident: {
          incident_id: String(row.incident_id || ""),
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
        }
      });
    });
  } catch (e) {
    console.error("diagnostic_read_failed", String(e?.name || "Error"));
    return diagnosticJson({ ok: false, error: "diagnostic_unavailable" }, 503);
  }
}
'''


def build() -> None:
    actual_blob = subprocess.check_output(["git", "rev-parse", "HEAD:cloudflare/whatsapp_worker_v2_6_STANDALONE.js"], cwd=ROOT, text=True).strip()
    require(actual_blob == EXPECTED_SOURCE_BLOB, "El Worker fuente 2.6.14 cambió; revisar antes de parchear")
    raw = SOURCE.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    marker = "var whatsapp_worker_v2_6_responses_default = {\n"
    require(text.count(marker) == 1, "No se encontró el objeto principal del Worker")
    text = text.replace(marker, BRIDGE + "\n" + marker, 1)

    route_marker = "    const u = new URL(request.url);\n"
    route = '    if (u.pathname.startsWith("/diagnostics/")) return serveDiagnosticRead(request, env, u);\n'
    require(text.count(route_marker) == 1, "No se encontró el inicio de fetch")
    text = text.replace(route_marker, route_marker + route, 1)

    require(text.count('worker_version: "2.6.14"') == 1, "Versión health inesperada")
    text = text.replace('worker_version: "2.6.14"', 'worker_version: "2.6.15"', 1)
    text = text.replace('"Dr-Revelo-WhatsApp-Worker/2.6.14"', '"Dr-Revelo-WhatsApp-Worker/2.6.15"', 1)
    text = text.replace('assistant_booking_link: "enabled", automation:', 'assistant_booking_link: "enabled", diagnostics_read: "capability_v1", automation:', 1)

    require("/diagnostics/latest" not in text, "Está prohibido listar el último diagnóstico")
    require("DIAGNOSTIC_LONG_ID_RE" in text and "{32}" in text, "Falta código largo de 128 bits")
    require("DIAGNOSTIC_LEGACY_DEADLINE" in text, "Falta compatibilidad temporal controlada")
    require("public.rp_diagnostics_incidents" in text, "Falta lectura desde tabla privada")
    require("machine_hash" not in BRIDGE and "metadata_json" not in BRIDGE and "signature" not in BRIDGE, "El puente expone campos innecesarios")
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("BUILD_WORKER_DIAG_READER_OK")
    print("WORKER_SHA", sha(OUT.read_bytes()))


if __name__ == "__main__":
    build()
