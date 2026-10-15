-- One-time non-destructive provisioning of the WhatsApp Reception HMAC key.
-- Execute on the existing Recepcion Pacientes Neon DB before deploying 4.8.28.
-- Only an owner of the dedicated private table may read the random key.
-- Never print/export the secret, never embed it in the app or GitHub.
CREATE TABLE IF NOT EXISTS whatsapp_cloud.reception_signing_key (
  id smallint PRIMARY KEY CHECK(id=1),
  secret bytea NOT NULL CHECK(octet_length(secret)=32),
  created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON TABLE whatsapp_cloud.reception_signing_key FROM PUBLIC;
INSERT INTO whatsapp_cloud.reception_signing_key(id,secret)
VALUES(1,gen_random_bytes(32)) ON CONFLICT(id) DO NOTHING;

-- Safe verification: only cardinality and size, never the secret.
SELECT count(*) AS keys, min(octet_length(secret)) AS bytes
FROM whatsapp_cloud.reception_signing_key WHERE id=1;
