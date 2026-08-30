-- WhatsApp inbound review queue — v2.6.0
-- Idempotent. The Worker also creates this table lazily on the first inbound reply.
CREATE SCHEMA IF NOT EXISTS whatsapp_cloud;

CREATE TABLE IF NOT EXISTS whatsapp_cloud.inbound_responses (
  id bigserial PRIMARY KEY,
  message_id text NOT NULL UNIQUE,
  phone text NOT NULL,
  message_type text NOT NULL,
  raw_text text,
  transcription text,
  media_id text,
  media_mime_type text,
  interpretation text NOT NULL DEFAULT 'REVISAR',
  confidence integer NOT NULL DEFAULT 0,
  source_type text,
  source_id bigint,
  appointment_date date,
  appointment_time time,
  patient_name text,
  match_method text,
  apply_result text,
  received_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by text,
  resolution text,
  raw_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS inbound_responses_review_idx
  ON whatsapp_cloud.inbound_responses (received_at DESC)
  WHERE resolved_at IS NULL AND interpretation='REVISAR';

CREATE INDEX IF NOT EXISTS inbound_responses_phone_idx
  ON whatsapp_cloud.inbound_responses (phone, received_at DESC);
