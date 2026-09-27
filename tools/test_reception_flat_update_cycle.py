from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "updates" / "v4_6_6_fast_attention_save"
CANDIDATE = ROOT / "refactor_build" / "reception_flat_466"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def import_probe(runtime: Path, expected: str = "4.6.6") -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="rp-update-cycle-data-"))
    try:
        code = (
            "import os,sys;"
            f"sys.path.insert(0,r'{runtime}');"
            "import app;"
            "print(getattr(app,'APP_VERSION',''));"
            "print(len(app.app.router.routes))"
        )
        env = os.environ.copy()
        env.update(
            {
                "RP_DATA_DIR": str(data_dir),
                "RP_FORCE_OFFLINE": "1",
                "DATABASE_URL": "",
                "NEON_DATABASE_URL": "",
                "HISTORIA_DATABASE_URL": "",
                "REMOTE_AGENDA_AUTOSTART": "0",
                "WHATSAPP_ENABLED": "0",
                "PYTHONPATH": str(runtime),
                "PYTHONIOENCODING": "utf-8",
            }
        )
        p = subprocess.run(
            [sys.executable, "-c", code],
            cwd=runtime,
            env=env,
            text=True,
            capture_output=True,
            timeout=75,
        )
        if p.returncode:
            print(p.stdout)
            print(p.stderr)
            raise SystemExit(f"candidate import failed rc={p.returncode}")
        lines = [x.strip() for x in p.stdout.splitlines() if x.strip()]
        assert expected in lines, lines
        assert "243" in lines, lines
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


manifest = json.loads((CANDIDATE / "update_manifest.json").read_text(encoding="utf-8-sig"))
payload = [str(x).replace("\\", "/") for x in manifest.get("copy", [])]
assert payload and len(payload) == len(set(payload))

# Reconstruct the currently installed 4.6.6 payload exactly as the stable
# app-channel currently delivers it. These files are the pre-refactor baseline.
old_payload = [
    "app.py",
    "recepcion-version.json",
    "update_manifest.json",
    "static/runtime_keep.txt",
    "historia_bridge.py",
    "historia_lan_transport.py",
]

install = Path(tempfile.mkdtemp(prefix="rp-update-cycle-install-"))
backup = Path(tempfile.mkdtemp(prefix="rp-update-cycle-backup-"))
try:
    for rel in old_payload:
        copy_file(SOURCE / rel, install / rel)

    # Protected/user data that an update must never modify or delete. The local
    # DB sentinel is a real SQLite file because production boot may use it as a
    # seed for a fresh RP_DATA_DIR; using arbitrary bytes would test corruption,
    # not update/rollback behavior.
    protected_bytes = {
        ".env": b"DATABASE_URL=postgresql://protected\nSECRET=keep-me\n",
        "BASE DE DATOS 2026.xlsx": b"excel-user-data-sentinel",
        "backups/keep.txt": b"backup-user-data-sentinel",
    }
    for year in range(2020, 2026):
        protected_bytes[f"historico/BASE DE DATOS {year}.xlsx"] = f"historico-{year}-keep".encode()
    for rel, content in protected_bytes.items():
        path = install / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    protected_db = install / "data" / "recepcion.db"
    protected_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(protected_db) as conn:
        conn.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO sentinel(value) VALUES (?)", ("keep-me",))
        conn.commit()

    protected = list(protected_bytes) + ["data/recepcion.db"]
    protected_hashes = {rel: sha(install / rel) for rel in protected}

    baseline = {
        rel: sha(install / rel)
        for rel in old_payload
        if (install / rel).is_file()
    }

    # Match the launcher's backup semantics: remember whether each candidate
    # target existed; only existing targets are copied to the backup.
    entries = []
    for rel in payload:
        current = install / rel
        existed = current.is_file()
        entries.append({"path": rel, "existed": existed})
        if existed:
            copy_file(current, backup / rel)

    # Apply the candidate atomically at file granularity (same end state as
    # launcher File.Copy(temp) + File.Move(temp,dest,true)).
    for rel in payload:
        src = CANDIDATE / rel
        assert src.is_file(), rel
        dest = install / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".launcher_v1_new")
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)

    for rel in payload:
        assert sha(install / rel) == sha(CANDIDATE / rel), rel
    for rel, expected_hash in protected_hashes.items():
        assert sha(install / rel) == expected_hash, f"protected file changed after apply: {rel}"

    # Candidate must really import from the upgraded installation.
    import_probe(install)

    # Roll back exactly like Launcher 1.0.12: restore previous bytes for files
    # that existed and delete candidate-only files that did not exist before.
    for entry in entries:
        rel = entry["path"]
        dest = install / rel
        src = backup / rel
        if entry["existed"] and src.is_file():
            copy_file(src, dest)
        elif not entry["existed"] and dest.is_file():
            dest.unlink()

    for rel, expected_hash in baseline.items():
        assert (install / rel).is_file(), f"baseline file missing after rollback: {rel}"
        assert sha(install / rel) == expected_hash, f"baseline bytes drifted after rollback: {rel}"

    candidate_only = sorted(set(payload) - set(old_payload))
    leftovers = [rel for rel in candidate_only if (install / rel).exists()]
    assert not leftovers, f"candidate-only leftovers after rollback: {leftovers}"

    for rel, expected_hash in protected_hashes.items():
        assert sha(install / rel) == expected_hash, f"protected file changed after rollback: {rel}"

    # The restored production package must still import after rollback.
    import_probe(install)

    contract_path = CANDIDATE / "CANDIDATE_CONTRACT.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        contract["update_cycle"] = "ok"
        contract["rollback_cycle"] = "ok"
        contract["candidate_only_files_removed_on_rollback"] = candidate_only
        contract["protected_files_unchanged"] = protected
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("UPDATE + ROLLBACK CYCLE OK")
    print("old payload", len(old_payload), "candidate payload", len(payload))
    print("candidate-only removed", len(candidate_only))
    print("protected unchanged", len(protected))
finally:
    shutil.rmtree(install, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
