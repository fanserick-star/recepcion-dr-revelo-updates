"""No-regression check: Neon sleep-safe Reception, agenda and Cloudflare scheduler.

These assertions check the deployment and runtime contracts without touching
real patients, invoices, or sending WhatsApp messages.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
agenda = (ROOT / "recepcion/app/reception_payments_and_agenda.py").read_text(encoding="utf-8")
worker = (ROOT / "cloudflare/whatsapp_worker.js").read_text(encoding="utf-8")
schedule = json.loads((ROOT / "cloudflare/wrangler.whatsapp.jsonc").read_text(encoding="utf-8"))
deploy = (ROOT / ".github/workflows/deploy-whatsapp.yml").read_text(encoding="utf-8")
front = (ROOT / "recepcion/app/static/app.js").read_text(encoding="utf-8")

# No periodic Neon wakeups; tests cannot contact Meta or send WhatsApp.
assert "triggers" not in schedule or not schedule["triggers"].get("crons")
assert schedule["durable_objects"]["bindings"][0]["name"] == "WHATSAPP_ALARMS"
assert "assert crons == [], crons" in deploy
assert "Verificar que NO quedan cron triggers" in deploy
assert "async scheduled(_controller, env, ctx)" not in worker
assert "refreshWhatsappAlarm(env)" in worker
assert "async function runScheduler(env)" in worker
assert "return withClient(env, async (client) => {" in worker.split("async function runScheduler(env)", 1)[1][:350]
assert "finally" in worker.split("async function withClient(env, fn)", 1)[1][:350]
assert "await c.end();" in worker.split("async function withClient(env, fn)", 1)[1][:350]

# Booking confirmations are event-driven immediately, NOT delayed 30 minutes.
assert "ctx.waitUntil(refreshWhatsappAlarm(env).catch(e => console.error(\"booking_alarm_registration_failed\", e)))" in worker
assert "ctx.waitUntil(refreshWhatsappAlarm(env).catch(e => console.error(\"autoagenda_alarm_registration_failed\", e)))" in worker
assert "when kind='cita_agendada'" not in worker.lower() or "interval '12 hours'" in worker
assert "interval '4 hours'" in worker  # missed cron window cannot lose reminders
assert "case when kind='cita_agendada'" in worker.lower() or "CASE WHEN kind='cita_agendada'" in worker
assert 'booking_cache_seconds: 60' in worker  # public booking still cached
assert '"worker_cycle_minutes": 0' in source  # tests wake an alarm, not a cron

# Both agenda fetchers are throttled; do not revert either to 5 seconds.
assert "def _v4445_sync_cloud_agenda_for_dates(dates, min_interval: float=60.0)" in agenda
assert "def _v4449_cloud_sync_background(dates, min_interval: float=60.0)" in agenda
assert "last < max(1.0, float(min_interval or 60.0))" in agenda
assert "def _sync_agenda_states_from_cloud(db: Session, dates: list[date], min_interval: float = 60.0)" in source
assert "_v4445_cloud_agenda_at[key] = core.time.time()" in agenda
assert "if key in _v4449_cloud_bg_keys:" in agenda
assert "if now - last < float(min_interval):" in source
assert "core.mirror_appointment_to_local(appointment)" in agenda
assert "core.mirror_patient_to_local(patient)" in agenda
assert "_kick_agenda_status_sync(dates)" in source  # don't lose confirmation state

# Never trade durability or LAN queue for cost optimization.
assert "CACHE_REFRESH_SECONDS = 12 * 60 * 60" in source
assert "CLOUD_CHECK_SECONDS = 600.0" in source
assert "pool_size=1" in source and "max_overflow=1" in source
assert 'cloud_engine.dispose()' in source
assert '"/api/power/idle"' in source and '"/api/power/wake"' in source
assert "if(method==='GET' && inflightGets.has(url))" in front
assert "connectivityTimer=setInterval(()=>updateConnectivity(false),PASSIVE_CONNECTIVITY_MS)" in front
assert "if configured and force:" in source  # passive status never polls Neon
assert "if queue_count() > 0:" in source
assert "def process_offline_queue(" in source
assert "_schedule_clinical_chart_retry()" in source
assert '"/api/billing"' in source
assert '"/api/agenda/week"' in source

# Runtime and manifests still parse; no patch import chain reintroduced.
ast.parse(source)
ast.parse(agenda)
version = json.loads((ROOT / "recepcion/app/recepcion-version.json").read_text(encoding="utf-8"))
manifest = json.loads((ROOT / "recepcion/app/update_manifest.json").read_text(encoding="utf-8"))
assert version["version"] == manifest["version"] == "4.8.15"
print("RECEPTION_NEON_EFFICIENCY_SLEEP_SAFE_OK", version["version"])
