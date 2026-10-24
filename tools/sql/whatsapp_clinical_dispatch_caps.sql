-- Independent, one-use WhatsApp clinical dispatch capability store.
-- Only random 256-bit capability hashes and SHA-256(token|recipient) are retained;
-- a stolen table cannot brute-force Ecuadorian phone numbers without the random token.
-- NEVER store patient names, phone numbers, signed URLs or clinical files.
-- This is separate from whatsapp_cloud.reception_alarm_requests (appointments).
CREATE TABLE IF NOT EXISTS whatsapp_cloud.clinical_delivery_caps (
  token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  recipient_hash text NOT NULL CHECK (recipient_hash ~ '^[0-9a-f]{64}$'),
  mode text NOT NULL CHECK (mode IN ('test','patient')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  claimed_at timestamptz,
  CHECK (expires_at > created_at)
);
REVOKE ALL ON whatsapp_cloud.clinical_delivery_caps FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_cloud.clinical_delivery_caps TO neondb_owner, neon_service;
-- Any future cleanup must be event-driven and bounded, never cron polling.
