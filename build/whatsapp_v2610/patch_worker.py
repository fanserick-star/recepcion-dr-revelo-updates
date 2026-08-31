from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

s=s.replace('worker_version:"2.6.9"','worker_version:"2.6.10"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.9','Dr-Revelo-WhatsApp-Worker/2.6.10',1)
s=s.replace('👋 *Hola.*\\n\\n','*Hola.*\\n\\n',1)
s=s.replace('\\n📞 *${doctorPhone}*\\n\\n','\\n*${doctorPhone}*\\n\\n',1)

assert 'worker_version:"2.6.10"' in s
assert '*Hola.*\\n\\n' in s
assert '*${doctorPhone}*' in s
assert '👋' not in s
assert '📞' not in s
assert 'comuníquese directamente con el Doctor:' in s
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V2610_NO_EMOJIS_OK')
