"""4.8.17 — Integrity-check de copias SQLite: sin escrituras ni restauraciones."""
from __future__ import annotations
import ast
import sqlite3
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
src = (ROOT/"recepcion/app/reception_system_status.py").read_text(encoding="utf-8")
front = (ROOT/"recepcion/app/static/app.js").read_text(encoding="utf-8")
tree = ast.parse(src)
node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == "_verify_backup_file_4817")
scope={"Path": Path}
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),"backup_check_unit","exec"),scope)
verify=scope["_verify_backup_file_4817"]
with tempfile.TemporaryDirectory() as folder:
    good=Path(folder)/"recepcion_backup_good.db"
    db=sqlite3.connect(good)
    db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)")
    db.execute("INSERT INTO messages(content) VALUES (?)", ("dummy",))
    db.commit();db.close()
    before=good.read_bytes()
    assert verify(good)["valid"] and verify(good)["checked"]
    assert verify(good,deep=True)["valid"]
    assert good.read_bytes()==before, "Backup contents modified"
    broken=Path(folder)/"recepcion_backup_broken.db"
    broken.write_bytes(b"this is not a sqlite database")
    assert not verify(broken)["valid"]
    assert not verify(Path(folder)/"missing.db")["valid"]
assert "@app.get('/api/ops/backup-integrity')" in src
section=src.split("# 4.8.17",1)[1].split("@app.get('/api/v4501/health')",1)[0]
assert "mode=ro" in section and "PRAGMA query_only=ON" in section
assert "sqlite3.connect(uri, uri=True" in section
assert "'restored': False" in section and "'no_cloud_queries': True" in section
assert all(s not in section for s in ("CloudSessionLocal", "sendMeta", "_upsert_link", "db.delete(", "os.remove(", "unlink(", "INSERT INTO", "UPDATE public."))
assert "async function openBackupIntegrityReview(deep=false)" in front
fn=front.split("async function openBackupIntegrityReview(deep=false)",1)[1].split("async function goHomeToday()",1)[0]
assert "setInterval(" not in fn and "setTimeout(" not in fn
assert "No restaura datos" in front
print("RECEPTION_BACKUP_INTEGRITY_4817_READ_ONLY_NO_RESTORE_OK")
