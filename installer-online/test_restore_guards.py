"""Non-destructive first-boot restore guard smoke-tests. Fake local DB only."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).with_name("restore_historia_initial.py").resolve()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def scenario(name, create_db, expected):
    with tempfile.TemporaryDirectory(prefix="restore-guard-") as temp:
        root = Path(temp)
        (root / "app.py").write_text("raise AssertionError('app import must not occur')\n")
        path = root / "data" / "historia_clinica.db"
        path.parent.mkdir(parents=True)
        create_db(path)
        before = digest(path)
        env = dict(os.environ, DR_REVELO_HISTORIA_ROOT=str(root))
        p = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                           text=True, env=env, timeout=10)
        assert p.returncode != 0, (name, p.stdout, p.stderr)
        assert expected in p.stdout + p.stderr, (name, p.stdout, p.stderr)
        assert digest(path) == before, (name, "Clinical database was modified")
        assert not any(x in p.stdout + p.stderr for x in
                       ("SECRET_PLAINTEXT", "PATIENT_PRIVATE_NAME"))
        print("PASS: protected local clinical rows unchanged ->", name)

def corrupt(path):
    path.write_bytes(b"fake sqlite DB bytes not a valid database")

def pending_edits(path):
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE patients(id TEXT, name TEXT)")
        c.execute("CREATE TABLE encounters(id TEXT)")
        c.execute("CREATE TABLE sync_dirty(table_name TEXT)")
        c.execute("INSERT INTO patients VALUES ('patient-1', 'PATIENT_PRIVATE_NAME')")
        c.execute("INSERT INTO sync_dirty VALUES ('patients')")
    (path.parent / ".instalador_restauracion_pendiente").write_text("restauracion-segura-v1\n")

scenario("corrupt legacy DB", corrupt, "CLINICAL_DATABASE_PRESENT_UNREADABLE")
scenario("unsynced clinician edits", pending_edits, "LOCAL_CLINICAL_EDITS_DETECTED_RESTORE_ABORTED")
print("ALL_NONDESTRUCTIVE_RESTORE_GUARDS_OK")
