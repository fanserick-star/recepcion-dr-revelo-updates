from pathlib import Path

p = Path(__file__).with_name("build_historia_1370.py")
s = p.read_text(encoding="utf-8")
old = """docs = rep(\n    docs,\n    '        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};\\n',\n    '        const patientId={json.dumps(patient_id)}, queueId={json.dumps(queue_id)}, encounterDate={json.dumps(encounter_date)}, encounterTime={json.dumps(encounter_time)}, fromConsultation={\"true\" if from_consultation else \"false\"};\\n        let encounterId={json.dumps(encounter_id)}, prescriptionId=null;\\n',\n    label=\"recipe context js\",\n)\n"""
new = """docs = rep(\n    docs,\n    '        const patientId={json.dumps(patient_id)}, encounterId={json.dumps(encounter_id)};\\n        function addRow()',\n    '        const patientId={json.dumps(patient_id)}, queueId={json.dumps(queue_id)}, encounterDate={json.dumps(encounter_date)}, encounterTime={json.dumps(encounter_time)}, fromConsultation={\"true\" if from_consultation else \"false\"};\\n        let encounterId={json.dumps(encounter_id)}, prescriptionId=null;\\n        function addRow()',\n    label=\"recipe context js\",\n)\n"""
if old not in s:
    raise RuntimeError("No encontré el bloque recipe context js esperado")
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("Generator selector patched")
