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
print("RECEPTION_UNIFIED_WA_CLOUD_ALARMS_SAFE_NO_OLD_HMAC_OR_CRON_OK")
