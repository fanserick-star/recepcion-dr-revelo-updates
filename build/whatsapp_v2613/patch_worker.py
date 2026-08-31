from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

assert 'worker_version:"2.6.12"' in s, 'Se esperaba Worker v2.6.12 como base'
assert 'function automaticAssistantNotice(env={}){' in s
assert 'Este número se utiliza *exclusivamente para confirmar o informar que no podrá asistir a una cita médica.*' in s

old='''function automaticAssistantNotice(env={}){\n  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";\n  return `*Hola.*\\n\\nEste es el *Asistente Virtual de Confirmaciones* del consultorio del *Dr. Armando Revelo*.\\n\\nEste número se utiliza *exclusivamente para confirmar o informar que no podrá asistir a una cita médica.*\\n\\nPara agendar, reagendar o realizar cualquier otra consulta, por favor comuníquese directamente con el Doctor:\\n*${doctorPhone}*\\n\\nGracias por su comprensión.`;\n}'''
new='''function automaticAssistantNotice(env={}){\n  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";\n  const bookingUrl=String(env.PUBLIC_BOOKING_URL||"https://fanserick-star.github.io/recepcion-dr-revelo-updates/agendar.html").trim()||"https://fanserick-star.github.io/recepcion-dr-revelo-updates/agendar.html";\n  return `*Hola.*\\n\\nEste es el *Asistente Virtual de Confirmaciones* del consultorio del *Dr. Armando Revelo*.\\n\\nEste número se utiliza principalmente para la gestión y confirmación de citas médicas.\\n\\n*Para agendar una nueva cita en línea:*\\n${bookingUrl}\\n\\nSi necesita *reagendar, cancelar o realizar otra consulta*, por favor comuníquese directamente con el Doctor:\\n*${doctorPhone}*\\n\\nGracias por su comprensión.`;\n}'''
assert old in s, 'No se encontró el mensaje automático esperado'
s=s.replace(old,new,1)
s=s.replace('worker_version:"2.6.12"','worker_version:"2.6.13"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.12','Dr-Revelo-WhatsApp-Worker/2.6.13',1)
s=s.replace('booking_confirmation:"cita_agendada_within_5m"','booking_confirmation:"cita_agendada_within_5m",assistant_booking_link:"enabled"',1)

for marker in [
    'worker_version:"2.6.13"',
    'assistant_booking_link:"enabled"',
    'PUBLIC_BOOKING_URL',
    '*Para agendar una nueva cita en línea:*',
    'https://fanserick-star.github.io/recepcion-dr-revelo-updates/agendar.html',
    'Si necesita *reagendar, cancelar o realizar otra consulta*'
]:
    assert marker in s, marker

p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V2613_BOOKING_LINK_PATCHED')
