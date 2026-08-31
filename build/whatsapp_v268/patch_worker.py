from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8')

s=s.replace('// v2.6.7 — ventana de confirmación de 2 horas y cierre al resolver.','// v2.6.8 — mensaje institucional del asistente virtual.',1)
s=s.replace('worker_version:"2.6.7"','worker_version:"2.6.8"',1)
s=s.replace('Dr-Revelo-WhatsApp-Worker/2.6.7','Dr-Revelo-WhatsApp-Worker/2.6.8',1)

old='''function automaticAssistantNotice(env={}){\n  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";\n  return `Hola. Este número corresponde a un asistente automático (IA) del consultorio del Dr. Armando Revelo y se utiliza únicamente para confirmaciones de citas. Para cualquier otra consulta, por favor comuníquese directamente con el consultorio al ${doctorPhone}.`;\n}'''
new='''function automaticAssistantNotice(env={}){\n  const doctorPhone=String(env.DOCTOR_CONTACT_PHONE||"0968840690").trim()||"0968840690";\n  return `👋 *Hola.*\\n\\nEste es el *Asistente Virtual de Confirmaciones* del consultorio del *Dr. Armando Revelo*.\\n\\nEste número se utiliza *exclusivamente para confirmar o informar que no podrá asistir a una cita médica.*\\n\\nPara agendar, reagendar o realizar cualquier otra consulta, por favor comuníquese directamente con el consultorio:\\n📞 *${doctorPhone}*\\n\\nGracias por su comprensión.`;\n}'''
assert old in s, 'No se encontró automaticAssistantNotice esperado'
s=s.replace(old,new,1)

assert 'worker_version:"2.6.8"' in s
assert '*Asistente Virtual de Confirmaciones*' in s
assert '📞 *${doctorPhone}*' in s
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V268_PATCHED')
