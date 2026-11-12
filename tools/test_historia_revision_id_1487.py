"""Safety regression for emergency revision id NOT NULL error (SQLSTATE 23502)."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"historia-clinica"/"app"))
from cloud_sync import _revision_insert_statement,HISTORIA_NEON_ENDPOINT_ID,HISTORIA_NEON_EMERGENCY_ENDPOINT_ID

sample={
    "id":733, "encounter_id":"encounter-test-123","revision_no":2,
    "saved_at":"2026-11-12T08:40:00","actor":"test-actor",
    "clinical_note":"TEST ONLY","diagnosis":"TEST ONLY","treatment":"",
    "reason":"test"
}
device="device-test-xyz"
sql,params=_revision_insert_statement(sample,device,HISTORIA_NEON_EMERGENCY_ENDPOINT_ID)
columns=sql.split("INSERT INTO encounter_revisions(",1)[1].split(")",1)[0].split(",")
assert columns.count("id")==1,columns
assert columns.count("source_key")==1,columns
assert len(columns)==len(params)
assert params[columns.index("id")] == "733"
assert params[columns.index("source_key")] == "device-test-xyz:733"
assert sql.endswith("ON CONFLICT DO NOTHING")
assert "VALUES(" + ",".join(["%s"]*len(params)) + ")" in sql
sql2,params2=_revision_insert_statement(sample,device,HISTORIA_NEON_ENDPOINT_ID)
cols2=sql2.split("INSERT INTO encounter_revisions(",1)[1].split(")",1)[0].split(",")
assert "id" not in cols2,cols2
assert len(cols2)==len(params2)
assert params2[cols2.index("source_key")] == "device-test-xyz:733"
assert sql2.endswith("ON CONFLICT DO NOTHING")
for missing in [None,""]:
    try:
        _revision_insert_statement({**sample,"id":missing},device,HISTORIA_NEON_EMERGENCY_ENDPOINT_ID)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing revision id must not be sent")
try:
    _revision_insert_statement(sample,device,"unexpected-endpoint")
except ValueError:
    pass
else:
    raise AssertionError("Wrong project must not be used")
print("HISTORIA_REVISION_ID_23502_REGRESSION_OK")
