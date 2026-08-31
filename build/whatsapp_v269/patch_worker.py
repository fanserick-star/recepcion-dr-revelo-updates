from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

s=s.replace('// v2.6.8 — mensaje institucional del asistente virtual.','// v2.6.9 — mensaje institucional con contacto directo al Doctor.',1)
s=s.replace('worker_version:"2.6.8"','worker_version:"2.6.9"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.8','Dr-Revelo-WhatsApp-Worker/2.6.9',1)
s=s.replace('Para agendar, reagendar o realizar cualquier otra consulta, por favor comuníquese directamente con el consultorio:','Para agendar, reagendar o realizar cualquier otra consulta, por favor comuníquese directamente con el Doctor:',1)

assert 'worker_version:"2.6.9"' in s
assert 'comuníquese directamente con el Doctor:' in s
assert 'comuníquese directamente con el consultorio:' not in s
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V269_PATCHED')
