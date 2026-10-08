// Cloudflare Durable Object alarms only. This module never sends WhatsApp.
// Keep the original 24/7 appointment-confirmation behaviour: a new booking
// schedules its alarm as soon as it is committed to Neon.
export function alarmAtLeastNow(timestamp, now = Date.now()) {
  const due = Number(timestamp);
  if (!Number.isFinite(due) || !Number.isFinite(Number(now))) {
    throw new Error("Invalid reminder alarm timestamp");
  }
  return Math.max(Math.ceil(due), Math.ceil(Number(now) + 1500));
}
