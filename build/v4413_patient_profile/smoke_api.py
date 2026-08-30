import json
import os
import urllib.request

base=os.environ.get('V4413_BASE_URL','http://127.0.0.1:8766').rstrip('/')

def call(path,method='GET',body=None):
    data=None if body is None else json.dumps(body).encode('utf-8')
    req=urllib.request.Request(base+path,data=data,method=method,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as r:
        return json.loads(r.read().decode('utf-8'))

p=call('/api/patients','POST',{
    'nombre':'MANUEL PRUEBA PERFIL',
    'celular':'0999999999',
    'correo':'manuel.prueba@example.com',
})
pid=int(p['id'])
call('/api/visits','POST',{
    'patient_id':pid,
    'fecha':'2026-08-30',
    'tipo':'S',
    'procedimiento':None,
    'valor':40,
})
call('/api/agenda/appointments','POST',{
    'patient_id':pid,
    'fecha':'2026-09-03',
    'hora':'08:00',
    'nota':'CITA SMOKE PERFIL',
})
rows=call('/api/patients?q=MANUEL%20PRUEBA&limit=8')
hit=next(x for x in rows if int(x.get('id') or 0)==pid)
assert str(hit.get('ultima_atencion'))[:10]=='2026-08-30',hit
profile=call(f'/api/patients/{pid}/profile')
assert len(profile.get('visits') or [])==1,profile
assert len(profile.get('appointments') or [])==1,profile
assert isinstance(profile.get('billing'),list),profile
assert isinstance(profile.get('emissions'),list),profile
assert profile['appointments'][0]['nota']=='CITA SMOKE PERFIL',profile
assert profile.get('correo')=='manuel.prueba@example.com',profile
print('PATIENT_PROFILE_API_OK',pid)
