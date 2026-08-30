from pathlib import Path

app=Path('updates/v4_4_13_patient_profile/app.py').read_text(encoding='utf-8-sig')
js=Path('updates/v4_4_13_patient_profile/static/app.js').read_text(encoding='utf-8-sig')
index=Path('updates/v4_4_13_patient_profile/static/index.html').read_text(encoding='utf-8-sig')

assert 'APP_VERSION = "4.4.13"' in app
assert '/api/patients/{pid}/profile' in app
assert 'select(Appointment)' in app
assert 'select(BillingRecord, Visit)' in app
assert 'select(AzurEmission)' in app
assert "billingScope.querySelectorAll('span,b,strong,small')" in app
assert "document.querySelectorAll('span,b,strong,small')" not in app
assert 'RP_PORT' in app and 'pg8000' in app

assert 'data-v4413-profile-card="1"' in js
assert 'Última atención:' in js
assert '⚠ Datos incompletos' in js
assert 'Completar datos' in js
assert 'Historial de atenciones' in js
assert 'Historial de Agenda' in js
assert 'Historial de Facturación' in js
assert "openPatient(${Number(p.id)},'attention-search')" in js
# El bloque específico de Nueva atención ya no debe tener el botón directo Atender.
start=js.index('box.innerHTML=usable.length?usable.map(p=>{')
end=js.index("}).join(''):'<div class=\"panel muted\">No encontramos coincidencias.", start)
attention_block=js[start:end]
assert '>Atender</button>' not in attention_block
assert "openHistoricalPatientProfile" in attention_block

assert '/static/app.js?v=4.4.13' in index
assert 'v4413-patient-profile-css' in index
print('V4413_SCOPE_OK')
