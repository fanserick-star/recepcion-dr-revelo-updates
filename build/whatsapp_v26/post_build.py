from pathlib import Path

p=Path('cloudflare/whatsapp_worker_v2_6_responses.js')
s=p.read_text(encoding='utf-8-sig')
old='''  if(hasAny(t,uncertain))return {interpretation:"REVISAR",confidence:25,reason:"incertidumbre"};\n  if(pos&&neg)return {interpretation:"REVISAR",confidence:20,reason:"contradictorio"};\n  if(neg)return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};'''
new='''  if(hasAny(t,uncertain))return {interpretation:"REVISAR",confidence:25,reason:"incertidumbre"};\n  if(pos&&neg){\n    const strongPositive=words.has("si")||hasAny(t,["confirmo","confirmado","ahi estare","alli estare","cuente conmigo"]);\n    if(strongPositive)return {interpretation:"REVISAR",confidence:20,reason:"contradictorio"};\n    return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};\n  }\n  if(neg)return {interpretation:"NO_ASISTIRA",confidence:97,reason:"negacion_clara"};'''
if old not in s: raise SystemExit('No encontré el bloque de clasificación a corregir')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
print('WHATSAPP_V26_POST_BUILD_OK')
