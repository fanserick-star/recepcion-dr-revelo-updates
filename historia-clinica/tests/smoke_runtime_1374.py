from __future__ import annotations

import importlib
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
SRC = REPO / "historia-clinica/app"
ROOT = pathlib.Path(tempfile.gettempdir()) / "hc_runtime_smoke_1374"
if ROOT.exists():
    shutil.rmtree(ROOT)
shutil.copytree(SRC, ROOT)

os.environ["HISTORIA_SYNC_ENABLED"] = "0"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
app = importlib.import_module("app")
cloud_sync = importlib.import_module("cloud_sync")

assert app.APP_VERSION == "1.3.74", app.APP_VERSION
assert hasattr(app, "app")
assert "/api/encounters/save" in {getattr(r, "path", "") for r in app.app.router.routes}

# La recuperación debe consultar el esquema canónico actual.
app_text = (ROOT / "app.py").read_text(encoding="utf-8-sig")
assert "FROM public.{table}" in app_text
assert "FROM historia.{table}" not in app_text

# Documentos: una sola familia física, A4.
docs_text = (ROOT / "documentos_clinicos.py").read_text(encoding="utf-8-sig")
assert "Letter portrait" not in docs_text
assert "Carta vertical" not in docs_text
assert docs_text.count("size:A4 portrait") >= 3

# El ciclo de nube debe subir cambios locales antes del pull.
cloud_text = (ROOT / "cloud_sync.py").read_text(encoding="utf-8-sig")
cycle = cloud_text.split("    def _cycle(self):", 1)[1].split("    def _register_device", 1)[0]
assert cycle.index("pushed = self._push(pg)") < cycle.index("pulled = self._pull(pg, remote_now)")
assert "pull_skipped_local_dirty" in cloud_text
assert "remote_changed_before_local_push" in cloud_text

# La tabla de conflictos debe existir y aceptar snapshots de ambas versiones.
cloud_sync.ensure_local_sync_schema(ROOT / "data" / "historia_clinica.db")
service = cloud_sync.CloudSyncService(ROOT, ROOT / "data" / "historia_clinica.db")
with sqlite3.connect(ROOT / "data" / "historia_clinica.db") as conn:
    conn.row_factory = sqlite3.Row
    service._record_conflict(
        conn, "encounters", "enc-test",
        {"id": "enc-test", "clinical_note": "LOCAL"},
        {"id": "enc-test", "clinical_note": "REMOTO"},
        "smoke",
    )
    row = conn.execute("SELECT local_json,remote_json FROM sync_conflicts WHERE row_key='enc-test'").fetchone()
    assert row and "LOCAL" in row[0] and "REMOTO" in row[1]

# Fecha clínica: sólo se mueve si cruzó medianoche y seguía automática.
with app.db() as conn:
    conn.execute(
        """INSERT OR REPLACE INTO patients(id,name,name_search,source,created_at,updated_at)
           VALUES(?,?,?,?,?,?)""",
        ("p-1374","PACIENTE PRUEBA","PACIENTE PRUEBA","smoke","2026-09-28T23:50:00","2026-09-28T23:50:00"),
    )
    conn.execute(
        """INSERT INTO encounters(
             id,patient_id,encounter_date,encounter_time,clinical_note,diagnosis,treatment,
             source,source_record_hash,is_legacy_locked,created_at,updated_at,deleted_at,
             note_status,signed_at,signed_by,copied_from_encounter_id,queue_id,created_by
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("enc-auto","p-1374","2026-09-28","23:55","CONTROL","","","historia_clinica","h1",0,
         "2026-09-28T23:55:00","2026-09-28T23:55:00",None,"draft",None,None,None,None,"Dr. Armando Revelo"),
    )
    conn.execute(
        """INSERT INTO encounters(
             id,patient_id,encounter_date,encounter_time,clinical_note,diagnosis,treatment,
             source,source_record_hash,is_legacy_locked,created_at,updated_at,deleted_at,
             note_status,signed_at,signed_by,copied_from_encounter_id,queue_id,created_by
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("enc-manual","p-1374","2026-09-20","09:30","CONTROL MANUAL","","","historia_clinica","h2",0,
         "2026-09-28T23:56:00","2026-09-28T23:56:00",None,"draft",None,None,None,None,"Dr. Armando Revelo"),
    )
    conn.commit()

original_now = app.now_iso
app.now_iso = lambda: "2026-09-29T00:04:00"
try:
    r1 = app.sign_encounter("enc-auto")
    r2 = app.sign_encounter("enc-manual")
finally:
    app.now_iso = original_now
assert r1.status_code == 200 and r2.status_code == 200
with app.db() as conn:
    auto = conn.execute("SELECT encounter_date,encounter_time,note_status FROM encounters WHERE id='enc-auto'").fetchone()
    manual = conn.execute("SELECT encounter_date,encounter_time,note_status FROM encounters WHERE id='enc-manual'").fetchone()
assert tuple(auto) == ("2026-09-29", "00:04", "signed"), tuple(auto)
assert tuple(manual) == ("2026-09-20", "09:30", "signed"), tuple(manual)

manifest = json.loads((ROOT / "update_manifest.json").read_text(encoding="utf-8-sig"))
assert manifest["version"] == "1.3.74"
assert manifest["notes"]["sync_conflict_guard"] is True
assert manifest["notes"]["documents_a4_unified"] is True

print("HISTORIA_1374_SMOKE_OK", app.APP_VERSION, "SYNC_CONFLICT_GUARD_OK", "MIDNIGHT_DATE_OK", "A4_OK", "RECOVERY_SCHEMA_OK")
