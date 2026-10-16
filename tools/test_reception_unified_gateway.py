"""Recepción / WhatsApp Cloud unified alarm gateway: source-only checks.
No Neon, HTTP, Meta, patient, or schedule mutations.
"""
from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
core=(ROOT/"recepcion/app/core_runtime.py").read_text(encoding="utf-8")
guard=(ROOT/"recepcion/app/reception_messaging_runtime_guard.py").read_text(encoding="utf-8")
worker=(ROOT/"cloudflare/whatsapp_worker.js").read_text(encoding="utf-8")
ast.parse(core)

assert "def _wa_gateway_issue(" in core
assert "def _wa_gateway_signal_async(" in core
assert "def _whatsapp_alarm_notify_async(" in core
assert "purpose=\"auth_check\"" in core
assert "purpose=\"manual\"" in core
assert "secrets.token_urlsafe(32)" in core
assert "now()+interval '120 seconds'" in core
assert "if pending is not None: return" in core
assert "threading.Thread(target=notify" in core
assert "time.sleep(4)" in core
assert "CloudSessionLocal" in core
assert "def process_offline_queue(" in core
assert "if alarm_relevant_change:" in core
assert '_whatsapp_alarm_notify_async(source_type=source_type, source_id=source_id)' in core
assert '"alarm_notification": dict(_wa_gateway_diag)' in core
assert "_wa_alarm_hint_resume" not in core
assert "_wa_push_fresh_reception_booking_async" not in core
assert "_wa_alarm_signal_state" not in core
assert "_wa_shared_signing_key" not in core
assert "whatsapp_alarm_signal" not in core
assert "reception_gateway_refresh_failed" in worker
assert 'const alarm=await registerUnifiedAgendaAlarm(env, "reception")' in worker
assert 'registerUnifiedAgendaAlarm(env, "public_web").catch(e => console.error("booking_alarm_registration_failed", e))' in worker
assert "async function runScheduler(env)" in worker
assert '"/alarms/notify"' not in worker
assert "serveFreshReceptionBookingNotice" not in worker
assert "verifyReceptionSignedPayload" not in worker
assert "_wa_alarm_signal_state" not in guard
assert "async scheduled(" not in worker

# Read-only configuration route: panel and server must agree; never regenerate
# or reactivate access tokens simply because a configuration screen was opened.
frontend=(ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
configuration=(ROOT/"recepcion/app/static/configuration.js").read_text(encoding="utf-8")
html=(ROOT/"recepcion/app/static/index.html").read_text(encoding="utf-8")
assert "api('/api/mobile/config'" in frontend
assert '@app.get("/api/mobile/config")' in core
route=core.split('@app.get("/api/mobile/config")',1)[1].split('@app.post("/api/mobile/links/rotate")',1)[0]
assert "_is_loopback_client(request)" in route
assert "agenda_private.web_keys" in route
assert "active IS TRUE" in route
assert "force=bool(force_cloud)" in route
assert not any(x in route for x in ("_ensure_mobile_tokens(", "_upsert_local_env(", "_write_cloud_agenda_keys(", "_agenda_cloud_payload(", "INSERT INTO", "UPDATE agenda_private", "DELETE FROM"))
assert 'id="whatsappGatewayAuthBtn"' in html
assert "window.checkWhatsappGatewayAuth" in configuration
assert "call('/api/whatsapp/auth-check')" in configuration

# A cancellation has already deleted its source: a source-bound gateway
# refresh would return 409 and retain the old alarm. Recompute without ID.
for start,end in [
    ('@app.delete("/api/mobile/unlinked/{item_id}")','@app.put("/api/mobile/appointments/{appointment_id}")'),
    ('@app.delete("/api/mobile/appointments/{appointment_id}")','@app.get("/api/whatsapp/outbox")'),
    ('@app.delete("/api/agenda/appointments/{appointment_id}")','def _decode_confirmafy_csv('),
]:
    assert start in core and end in core, (start, end)
    segment=core.split(start,1)[1].split(end,1)[0]
    assert "_whatsapp_alarm_notify_async()" in segment, start
    assert '_whatsapp_alarm_notify_async(source_type=' not in segment, start

schedule=core.split("def schedule_whatsapp_for_contact(",1)[1].split("def _whatsapp_rebase_pending_schedule(",1)[0]
assert 'if WHATSAPP_CLOUD_MODE:' in schedule
assert 'return {"queued": 0, "cloud_mode": True}' in schedule
assert schedule.index('return {"queued": 0, "cloud_mode": True}') < schedule.index('_whatsapp_queue_one(')
legacy=core.split("def start_whatsapp_worker_if_enabled()",1)[1].split("def mirror_patient_to_local(",1)[0]
assert "threading.Thread(" not in legacy
assert "return" in legacy
assert "reason = \"edge_or_unknown_rejection\"" in core
assert '"expired_or_invalid_capability"' in core
assert "exc.read(1024)" in core
assert 'reason = candidate' in core
assert '"reason": reason' in core
assert "token" not in core.split('def whatsapp_auth_check(',1)[1].split('@app.get("/api/whatsapp/status")',1)[0]
# Cloudflare returned error 1010 to urllib's default User-Agent from the PC,
# while the same no-token route succeeded using curl. Do not loosen capability
# validation; only switch the User-Agent on the existing single gateway path.
assert '_WA_GATEWAY_USER_AGENT = "curl/8.10.1"' in core
http_call = core.split('def _wa_gateway_request(',1)[1].split('def _wa_gateway_signal_async(',1)[0]
assert '"User-Agent": _WA_GATEWAY_USER_AGENT' in http_call
assert '"Accept": "application/json"' in http_call
assert '"Content-Type": "application/json"' in http_call
assert '_wa_gateway_issue(purpose=purpose,source_type=source_type,source_id=source_id)' in http_call
assert 'data=json.dumps({"token": token}).encode("utf-8")' in http_call
assert 'method="POST"' in http_call
assert 'urllib.request.urlopen(request, timeout=12)' in http_call
print("RECEPTION_CF_1010_CLIENT_FIX_LEAVES_CAPABILITY_CHECK_INTACT_OK")

print("RECEPTION_CF_403_DIAGNOSTIC_NO_TOKEN_LEAK_NO_WA_SEND_OK")

print("RECEPTION_WEB_AGENDA_READONLY_CANCEL_AND_SINGLE_SENDER_NO_META_OK")

print("RECEPTION_UNIFIED_WA_CLOUD_ALARMS_SAFE_NO_OLD_HMAC_OR_CRON_OK")
