from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

assert 'worker_version:"2.6.11"' in s, 'Se esperaba Worker v2.6.11 como base'
assert 'BOOKING_SOURCE_PREFIX="mobile:autoagenda:"' in s

old="""  WHERE $3::boolean
    AND coalesce(b.source_hash,'') NOT LIKE 'mobile:whatsapp-cloud-test:%'
    AND (b.source_type='appointment' OR coalesce(b.source_hash,'') LIKE 'mobile:%')
    AND ((b.fecha + b.hora::time) AT TIME ZONE 'America/Guayaquil')
          - (b.created_at AT TIME ZONE 'UTC') >= interval '24 hours'
    AND ((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date < (b.fecha - 1)
"""
new="""  WHERE $3::boolean
    AND coalesce(b.source_hash,'') NOT LIKE 'mobile:whatsapp-cloud-test:%'
    AND (b.source_type='appointment' OR coalesce(b.source_hash,'') LIKE 'mobile:%')
    AND (
      coalesce(b.source_hash,'') LIKE 'mobile:autoagenda:%'
      OR (
        ((b.fecha + b.hora::time) AT TIME ZONE 'America/Guayaquil')
              - (b.created_at AT TIME ZONE 'UTC') >= interval '24 hours'
        AND ((b.created_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Guayaquil')::date < (b.fecha - 1)
      )
    )
"""
assert old in s, 'No se encontró la regla antigua de cita_agendada'
s=s.replace(old,new,1)
s=s.replace('worker_version:"2.6.11"','worker_version:"2.6.12"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.11','Dr-Revelo-WhatsApp-Worker/2.6.12',1)
s=s.replace('booking:"public_v1",booking_cache_seconds:60','booking:"public_v1",booking_cache_seconds:60,booking_confirmation:"cita_agendada_within_5m"',1)

for marker in [
    'worker_version:"2.6.12"',
    'booking_confirmation:"cita_agendada_within_5m"',
    "coalesce(b.source_hash,'') LIKE 'mobile:autoagenda:%'",
    'BOOKING_SOURCE_PREFIX="mobile:autoagenda:"'
]:
    assert marker in s,marker
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V2612_AUTOBOOK_CONFIRMATION_PATCHED')
