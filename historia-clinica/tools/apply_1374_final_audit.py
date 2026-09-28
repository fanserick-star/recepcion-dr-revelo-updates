from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "historia-clinica/app/app.py"
CLOUD = REPO / "historia-clinica/app/cloud_sync.py"
DOCS = REPO / "historia-clinica/app/documentos_clinicos.py"
VERSION = REPO / "historia-clinica/app/historia-version.json"
MANIFEST = REPO / "historia-clinica/app/update_manifest.json"
TEST = REPO / "historia-clinica/tests/smoke_runtime_1374.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        if new in text:
            return text
        raise SystemExit(f"No encontré ancla para {label}")
    if count != 1:
        raise SystemExit(f"Ancla ambigua para {label}: {count}")
    return text.replace(old, new, 1)


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8-sig")

    # Recuperación de borradores: public.* es el esquema canónico de Historia.
    text = text.replace("FROM historia.{table}", "FROM public.{table}")

    helper_anchor = '''@app.post("/api/encounters/{encounter_id}/sign")\ndef sign_encounter(encounter_id: str):\n'''
    helper = '''def _v1374_effective_sign_values(row, stamp: str) -> tuple[str, str]:\n    \"\"\"Ajusta fecha/hora sólo cuando cruzó medianoche y siguen automáticas.\n\n    Si el doctor cambió la fecha o la hora manualmente, se respeta. En una\n    consulta normal del mismo día no se altera la hora de inicio.\n    \"\"\"\n    encounter_date = str(row[\"encounter_date\"] or \"\").strip()\n    encounter_time = str(row[\"encounter_time\"] or \"\").strip()\n    created_at = str(row[\"created_at\"] or \"\").strip()\n    created_date = created_at[:10] if len(created_at) >= 10 else \"\"\n    created_time = created_at[11:16] if len(created_at) >= 16 else \"\"\n    sign_date = str(stamp or \"\")[:10]\n    sign_time = str(stamp or \"\")[11:16]\n\n    if created_date and sign_date and created_date != sign_date:\n        date_is_auto = (not encounter_date) or encounter_date == created_date\n        time_is_auto = (not encounter_time) or encounter_time[:5] == created_time\n        if date_is_auto:\n            encounter_date = sign_date\n            if time_is_auto and sign_time:\n                encounter_time = sign_time\n    return encounter_date, encounter_time\n\n\n@app.post("/api/encounters/{encounter_id}/sign")\ndef sign_encounter(encounter_id: str):\n'''
    text = replace_once(text, helper_anchor, helper, "helper fecha clínica")

    old_sign = '''            # Primero cerramos y confirmamos el registro clínico.\n            conn.execute(\n                "UPDATE encounters SET note_status='signed',signed_at=?,signed_by=?,updated_at=? WHERE id=?",\n                (stamp, DOCTOR_NAME, stamp, encounter_id),\n            )\n'''
    new_sign = '''            # Primero cerramos y confirmamos el registro clínico.\n            # Si la consulta quedó abierta al cruzar medianoche, actualizamos\n            # únicamente los valores automáticos; una fecha/hora editada por el\n            # doctor se conserva exactamente.\n            effective_date, effective_time = _v1374_effective_sign_values(h, stamp)\n            conn.execute(\n                \"\"\"UPDATE encounters\n                   SET note_status='signed',signed_at=?,signed_by=?,\n                       encounter_date=?,encounter_time=?,updated_at=?\n                   WHERE id=?\"\"\",\n                (stamp, DOCTOR_NAME, effective_date, effective_time, stamp, encounter_id),\n            )\n'''
    text = replace_once(text, old_sign, new_sign, "firma con fecha efectiva")

    old_doc_only = '''                conn.execute(\n                    \"\"\"UPDATE encounters\n                       SET note_status='signed',signed_at=?,signed_by=?,deleted_at=NULL,updated_at=?\n                       WHERE id=? AND note_status='draft'\"\"\",\n                    (stamp, DOCTOR_NAME, stamp, row[\"id\"]),\n                )\n'''
    new_doc_only = '''                effective_date, effective_time = _v1374_effective_sign_values(row, stamp)\n                conn.execute(\n                    \"\"\"UPDATE encounters\n                       SET note_status='signed',signed_at=?,signed_by=?,deleted_at=NULL,\n                           encounter_date=?,encounter_time=?,updated_at=?\n                       WHERE id=? AND note_status='draft'\"\"\",\n                    (stamp, DOCTOR_NAME, effective_date, effective_time, stamp, row[\"id\"]),\n                )\n'''
    text = replace_once(text, old_doc_only, new_doc_only, "documento sin texto con fecha efectiva")

    APP.write_text(text, encoding="utf-8")


def patch_cloud() -> None:
    text = CLOUD.read_text(encoding="utf-8-sig")

    old_schema = '''        conn.execute("CREATE TABLE IF NOT EXISTS sync_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")\n        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('sync_applying_remote','0')")\n'''
    new_schema = '''        conn.execute("CREATE TABLE IF NOT EXISTS sync_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)")\n        conn.execute(\"\"\"CREATE TABLE IF NOT EXISTS sync_conflicts(\n            id TEXT PRIMARY KEY, table_name TEXT NOT NULL, row_key TEXT NOT NULL,\n            detected_at TEXT NOT NULL, reason TEXT NOT NULL,\n            local_json TEXT, remote_json TEXT, resolved_at TEXT\n        )\"\"\")\n        conn.execute(\"CREATE INDEX IF NOT EXISTS idx_sync_conflicts_open ON sync_conflicts(resolved_at,detected_at)\")\n        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('sync_applying_remote','0')")\n'''
    text = replace_once(text, old_schema, new_schema, "tabla de conflictos")

    method_anchor = '''    def _set_state(self, conn: sqlite3.Connection, key: str, value: str):\n        conn.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)", (key, str(value)))\n\n    def _run(self):\n'''
    method_new = '''    def _set_state(self, conn: sqlite3.Connection, key: str, value: str):\n        conn.execute("INSERT OR REPLACE INTO sync_state(key,value) VALUES(?,?)", (key, str(value)))\n\n    def _record_conflict(self, conn: sqlite3.Connection, table: str, row_key: str, local_row, remote_row, reason: str) -> None:\n        \"\"\"Conserva ambas versiones antes de cualquier resolución local-wins.\"\"\"\n        try:\n            local_data = dict(local_row) if local_row is not None else None\n        except Exception:\n            local_data = local_row\n        try:\n            remote_data = dict(remote_row) if remote_row is not None else None\n        except Exception:\n            remote_data = remote_row\n        stamp = _now_iso()\n        raw = f\"{table}|{row_key}|{stamp}|{reason}\"\n        conflict_id = hashlib.sha256(raw.encode(\"utf-8\")).hexdigest()\n        conn.execute(\n            \"\"\"INSERT OR IGNORE INTO sync_conflicts(\n                 id,table_name,row_key,detected_at,reason,local_json,remote_json,resolved_at\n               ) VALUES(?,?,?,?,?,?,?,NULL)\"\"\",\n            (\n                conflict_id, table, str(row_key), stamp, reason,\n                json.dumps(local_data, ensure_ascii=False, default=str) if local_data is not None else None,\n                json.dumps(remote_data, ensure_ascii=False, default=str) if remote_data is not None else None,\n            ),\n        )\n        conn.commit()\n\n    def _run(self):\n'''
    text = replace_once(text, method_anchor, method_new, "registrador de conflictos")

    old_order = '''            pulled = self._pull(pg, remote_now) if pull_due else 0\n            pushed = self._push(pg)\n            self._register_device(pg)\n'''
    new_order = '''            # v1.3.74: nunca permitimos que un pull pise primero un cambio\n            # local pendiente. Se sube lo local y después se incorporan cambios\n            # remotos. Los choques simultáneos se preservan en sync_conflicts.\n            pushed = self._push(pg)\n            pulled = self._pull(pg, remote_now) if pull_due else 0\n            self._register_device(pg)\n'''
    text = replace_once(text, old_order, new_order, "orden push antes de pull")

    old_after = '''                local_encounters_after = int(\n                    sconn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]\n                )\n            finally:\n                sconn.close()\n'''
    new_after = '''                local_encounters_after = int(\n                    sconn.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]\n                )\n                sync_conflicts_open = int(\n                    sconn.execute("SELECT COUNT(*) FROM sync_conflicts WHERE resolved_at IS NULL").fetchone()[0]\n                )\n            finally:\n                sconn.close()\n'''
    text = replace_once(text, old_after, new_after, "conteo de conflictos")

    old_status = '''                bootstrap_recovery_incomplete=recovery_incomplete,\n                last_error="",\n            )\n'''
    new_status = '''                bootstrap_recovery_incomplete=recovery_incomplete,\n                sync_conflicts_open=sync_conflicts_open,\n                last_error="",\n            )\n'''
    text = replace_once(text, old_status, new_status, "estado de conflictos")

    old_push_row = '''                pk = ALL_SYNC_TABLES[table]\n                row = sconn.execute(f"SELECT * FROM {table} WHERE CAST({pk} AS TEXT)=?", (key,)).fetchone()\n                cur = pg.cursor()\n'''
    new_push_row = '''                pk = ALL_SYNC_TABLES[table]\n                row = sconn.execute(f"SELECT * FROM {table} WHERE CAST({pk} AS TEXT)=?", (key,)).fetchone()\n                cur = pg.cursor()\n\n                # Si otra PC cambió la misma fila después de nuestro último pull,\n                # guardamos la versión remota antes de aplicar el cambio local.\n                # Esto evita pérdida silenciosa aun cuando la política final sea\n                # local-wins para no borrar lo que el doctor acaba de escribir.\n                if (\n                    row is not None\n                    and table in BIDIRECTIONAL_TABLES\n                    and self._get_state(sconn, "cloud_bootstrap_complete", "0") == "1"\n                ):\n                    last_pull = self._get_state(sconn, "last_pull", "1970-01-01T00:00:00+00:00")\n                    check = pg.cursor()\n                    check.execute(\n                        f\"SELECT * FROM {table} WHERE CAST({pk} AS TEXT)=%s \"\n                        \"AND cloud_updated_at>%s::timestamptz LIMIT 1\",\n                        (str(key), last_pull),\n                    )\n                    remote_rows = _dict_rows(check)\n                    if remote_rows:\n                        self._record_conflict(\n                            sconn, table, str(key), row, remote_rows[0],\n                            "remote_changed_before_local_push",\n                        )\n'''
    text = replace_once(text, old_push_row, new_push_row, "protección push simultáneo")

    old_pull_key = '''                        if remote.get("deleted_at"):\n                            if table in {\n'''
    new_pull_key = '''                        local_dirty = sconn.execute(\n                            "SELECT 1 FROM sync_dirty WHERE table_name=? AND row_key=? LIMIT 1",\n                            (table, str(key)),\n                        ).fetchone()\n                        if local_dirty:\n                            local_row = sconn.execute(\n                                f"SELECT * FROM {table} WHERE CAST({pk} AS TEXT)=? LIMIT 1",\n                                (str(key),),\n                            ).fetchone()\n                            self._record_conflict(\n                                sconn, table, str(key), local_row, remote,\n                                "pull_skipped_local_dirty",\n                            )\n                            continue\n\n                        if remote.get("deleted_at"):\n                            if table in {\n'''
    text = replace_once(text, old_pull_key, new_pull_key, "protección pull sobre dirty")

    CLOUD.write_text(text, encoding="utf-8")


def patch_documents() -> None:
    text = DOCS.read_text(encoding="utf-8-sig")
    text = text.replace("Carta vertical", "A4 vertical")
    text = text.replace("size:Letter portrait", "size:A4 portrait")
    text = text.replace("width:216mm;min-height:279mm;height:279mm", "width:210mm;min-height:297mm;height:297mm")
    text = text.replace("width:216mm;height:279mm", "width:210mm;height:297mm")
    text = text.replace("width:210mm;height:279mm", "width:210mm;height:297mm")
    text = text.replace("min-height:279mm;height:279mm", "min-height:297mm;height:297mm")
    if "Letter portrait" in text or "Carta vertical" in text:
        raise SystemExit("Quedó un formato Letter/Carta activo")
    DOCS.write_text(text, encoding="utf-8")


def patch_metadata() -> None:
    VERSION.write_text(json.dumps({"version": "1.3.74"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    data["version"] = "1.3.74"
    data["app_version"] = "1.3.74"
    data["runtime_version"] = "1.3.74"
    notes = data.setdefault("notes", {})
    notes.update({
        "purpose": "Cierre funcional: conflictos multi-PC protegidos, fecha clínica al cruzar medianoche, recuperación canónica y documentos A4.",
        "previous_version": "1.3.73",
        "sync_conflict_guard": True,
        "sync_push_before_pull": True,
        "sync_conflict_snapshot_local": True,
        "sync_conflict_policy": "local_wins_after_remote_snapshot",
        "clinical_midnight_rollover_guard": True,
        "manual_clinical_datetime_preserved": True,
        "recovery_public_schema_canonical": True,
        "documents_a4_unified": True,
        "functional_smoke_1374": True,
        "cloud_logic_unchanged_from_1_3_72": False,
    })
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


SMOKE = r'''from __future__ import annotations

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
'''


def write_smoke() -> None:
    TEST.write_text(SMOKE, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_cloud()
    patch_documents()
    patch_metadata()
    write_smoke()
    print("Historia 1.3.74 aplicada correctamente")


if __name__ == "__main__":
    main()
