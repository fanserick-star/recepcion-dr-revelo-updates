// America/Guayaquil (continental Ecuador) is UTC-05:00 all year.
// No automatic outbound WhatsApp messages during quiet hours 20:00–08:00.
// Scheduling an alarm is NOT the same as sending a message.
export const ECUADOR_OFFSET_MS = 5 * 60 * 60 * 1000;
export const ALARM_OPEN_HOUR = 8;
export const ALARM_CLOSE_HOUR = 20;

export function deliveryWindowTimestamp(timestamp) {
  const due = Number(timestamp);
  if (!Number.isFinite(due)) throw new Error("Invalid alarm timestamp");
  const ec = new Date(due - ECUADOR_OFFSET_MS);
  const hour = ec.getUTCHours();
  if (hour >= ALARM_OPEN_HOUR && hour < ALARM_CLOSE_HOUR) return Math.ceil(due);
  // Move to 08:00 the same local day (if early) or following day (if late).
  const localMidnight = Date.UTC(ec.getUTCFullYear(), ec.getUTCMonth(), ec.getUTCDate());
  return localMidnight + (hour >= ALARM_CLOSE_HOUR ? 86400000 : 0)
    + ALARM_OPEN_HOUR * 3600000 + ECUADOR_OFFSET_MS;
}

export function canSendAutomaticMessages(now = Date.now()) {
  return deliveryWindowTimestamp(now) === Math.ceil(now);
}

export function alarmAtLeastNow(timestamp, now = Date.now()) {
  return deliveryWindowTimestamp(Math.max(Number(timestamp), now + 1500));
}
