"""Historia 1.4.96: offline regression of unified patient profile and quick sex edit.

Only synthetic in-memory SQLite. No existing clinical records, Neon or real calls.
"""
from __future__ import annotations
import ast
import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
app=(root/"historia-clinica/app/app.py").read_text(encoding="utf-8")
style=(root/"historia-clinica/app/static/style.css").read_text(encoding="utf-8")
consent=(root/"historia-clinica/app/consentimiento_informado.py").read_text(encoding="utf-8")
manifest=json.loads((root/"historia-clinica/app/update_manifest.json").read_text(encoding="utf-8"))
version=json.loads((root/"historia-clinica/app/historia-version.json").read_text(encoding="utf-8"))
assert manifest["version"]==manifest["app_version"]==manifest["runtime_version"]==version["version"]
assert tuple(map(int, version["version"].split("."))) >= (1, 4, 96)
tree=ast.parse(app)
route=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="patient_quick_sex")
patient=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="patient")
assert any("/paciente/{patient_id}/sexo" in ast.unparse(d) for d in route.decorator_list)
assert "cp-profile-unified" in ast.get_source_segment(app,patient)
assert "Información del paciente" in ast.get_source_segment(app,patient)
section=app.split('<section class="cp-patient-card cp-profile-unified">',1)[1].split('<!--not-existing-marker-->',1)[0]
assert section.index('Nombre completo')<section.index('Cédula')<section.index('Edad</label>')<section.index('for="cp-quick-sex"')
assert section.index('<div class="cp-patient-grid">')<section.index('<div class="cp-profile-actions"')
assert section.index('cp-patient-primary-action">{consult_action}')>section.index('<div class="cp-profile-actions"')
assert "ID Num:" not in section.split("</section>",1)[0]
assert "Editar datos</a>" in app and "Receta médica</a>" in app
assert "Certificado médico</a>" in app and "Informes médicos</a>" in app
assert "cp-patient-secondary-actions" in app
assert "cp-consent" in consent and "cp-certificate" in consent
assert "cp-profile-actions .cp-consent::before" in style
assert "cp-profile-actions .cp-edit-patient::before" in style
assert "cp-profile-actions .cp-prescription::before" in style
assert "cp-profile-actions .cp-certificate::before" in style
assert "cp-profile-actions .cp-reports::before" in style
assert 'select id="cp-quick-sex"' in app
assert "'X-Historia-Quick-Sex':'1'" in app
assert 'sexPicker.value=committed;' in app
assert "UPDATE patients SET sex=?,updated_at=? WHERE id=?" in ast.get_source_segment(app,route)
assert "SYNC_SERVICE.mark_activity()" in ast.get_source_segment(app,route)
assert "SYNC_SERVICE.wake()" in ast.get_source_segment(app,route)
assert "UPDATE waiting_queue" not in ast.get_source_segment(app,route)
assert "encounters" not in ast.get_source_segment(app,route).split('    with db() as conn:',1)[1]
# In-memory database: no change except sex and its updated_at; no new records
conn=sqlite3.connect(":memory:")
conn.row_factory=sqlite3.Row
conn.execute("CREATE TABLE patients(id TEXT PRIMARY KEY,sex TEXT,merged_into_patient_id TEXT,updated_at TEXT,name TEXT,ident TEXT)")
conn.execute("INSERT INTO patients VALUES('demo-1',NULL,NULL,'initial','PRUEBA','fake-id')")
conn.execute("INSERT INTO patients VALUES('merged-1',NULL,'demo-1','initial','FUSIONADO','fake-id2')")
conn.commit()
audits=[];wake=[]
class HTTPException(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code;self.detail=detail
class JSONResponse(dict):
    def __init__(self,data):super().__init__(data)
class Request:
    def __init__(self,sex,headers=None,origin=""):
        self.sex=sex
        self.headers={"X-Historia-Quick-Sex":"1",**(headers or {})}
        if origin:self.headers["origin"]=origin
        self.base_url="http://127.0.0.1:8000/"
    async def json(self):return {"sex":self.sex}
class Sync:
    def mark_activity(self):wake.append("activity")
    def wake(self):wake.append("wake")
ns={
    "Request":Request,"HTTPException":HTTPException,"JSONResponse":JSONResponse,
    "re":__import__("re"),"db":lambda:conn,
    "now_iso":lambda:"2026-11-14T10:00:00",
    "audit":lambda c,action,table,ident,detail:audits.append((action,table,ident,detail)),
    "SYNC_SERVICE":Sync(),
}
route.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=[route],type_ignores=[])),"synthetic-route","exec"),ns)
save=ns["patient_quick_sex"]
def run(value,patient_id="demo-1",headers=None,origin=""):
    return asyncio.run(save(patient_id,Request(value,headers,origin)))
assert run("F")=={"ok":True,"sex":"F","changed":True}
row=conn.execute("SELECT * FROM patients WHERE id='demo-1'").fetchone()
assert row["sex"]=="F" and row["name"]=="PRUEBA" and row["ident"]=="fake-id"
assert len(audits)==1 and audits[0][3]=={"fields":["sex"]}
assert wake==["activity","wake"]
assert run("F")=={"ok":True,"sex":"F","changed":False}
assert len(audits)==1 and len(wake)==2
assert run("M")=={"ok":True,"sex":"M","changed":True}
assert run("")=={"ok":True,"sex":"","changed":True}
assert conn.execute("SELECT sex FROM patients WHERE id='demo-1'").fetchone()[0] is None
for bad,code in [("X",400),("Masculino",400),("m",400)]:
    try:run(bad)
    except HTTPException as ex:assert ex.status_code==code
    else:raise AssertionError(bad)
for kwargs in [
    {"headers":{"X-Historia-Quick-Sex":"0"}},
    {"headers":{"sec-fetch-site":"cross-site"}},
    {"origin":"https://attacker.example"},
]:
    try:run("M",**kwargs)
    except HTTPException as ex:assert ex.status_code==403
    else:raise AssertionError("Unauthorized patient sex edit accepted")
try:run("M","merged-1")
except HTTPException as ex:assert ex.status_code==409
else:raise AssertionError("Merged patient was editable")
try:run("M","not-in-db")
except HTTPException as ex:assert ex.status_code==404
else:raise AssertionError("Unknown patient was editable")
assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]==2
print("HISTORIA_PATIENT_PROFILE_1496_UNIFIED_QUICK_SEX_LOCAL_AUDIT_SYNC_OK")
