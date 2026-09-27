from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "refactor_build" / "reception_flat_466"
MANIFEST = CANDIDATE / "update_manifest.json"

if not MANIFEST.is_file():
    raise SystemExit("Candidato no generado/finalizado")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
copy_files = [str(x).replace("\\", "/") for x in manifest.get("copy", [])]
required = [str(x).replace("\\", "/") for x in manifest.get("required_dependencies", [])]

assert copy_files, "Manifest copy vacío"
assert len(copy_files) == len(set(copy_files)), "Manifest copy tiene rutas duplicadas"
assert set(required).issubset(set(copy_files)), (
    "required_dependencies fuera del payload", sorted(set(required) - set(copy_files))
)

protected_prefixes = ("data/", "backups/", "update_backups/")
protected_suffixes = (".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".xls", ".xlsx")
protected_exact = {".env", "recepcionlauncher.exe", "launcherupdater.exe"}
for rel in copy_files:
    low = rel.lower()
    assert rel and not rel.startswith("/") and ".." not in rel.split("/"), rel
    assert not low.startswith(protected_prefixes), rel
    assert not low.endswith(protected_suffixes), rel
    assert low not in protected_exact, rel
    assert (CANDIDATE / rel).is_file(), f"Archivo del payload ausente: {rel}"

staging = Path(tempfile.mkdtemp(prefix="rp-flat-staging-"))
try:
    for rel in copy_files:
        src = CANDIDATE / rel
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for rel in required:
        assert (staging / rel).is_file(), f"Dependencia requerida ausente en staging: {rel}"

    probe_out = staging / "_packaged_probe.json"
    data_dir = Path(tempfile.mkdtemp(prefix="rp-flat-staging-data-"))
    code = r'''
import hashlib, json, os, re, sys
from pathlib import Path
root = Path(os.getcwd()).resolve()
# The packaged candidate must be self-contained. Keep the staging directory as
# the only project path; third-party site-packages remain available normally.
sys.path[:] = [p for p in sys.path if not p or 'recepcion-dr-revelo-updates' not in p.lower()]
sys.path.insert(0, str(root))
import app
schema = app.app.openapi()
blob = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(',',':'))
rows = []
for route in app.app.router.routes:
    rows.append((getattr(route,'path',None), sorted(getattr(route,'methods',set()) or set()), getattr(getattr(route,'endpoint',None),'__name__',None)))
out = {
    'version': str(getattr(app,'APP_VERSION','')),
    'routes': len(rows),
    'duplicate_routes': len(rows) - len({(p,tuple(m)) for p,m,_ in rows}),
    'openapi_paths': len(schema.get('paths') or {}),
    'openapi_schemas': len(((schema.get('components') or {}).get('schemas') or {})),
    'openapi_sha': hashlib.sha256(blob.encode('utf-8')).hexdigest(),
    'historical_modules_loaded': sorted(k for k in sys.modules if re.match(r'^app_(?:base|prev|patch)_\d+$', k)),
}
Path(os.environ['PACKAGED_PROBE_OUT']).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
'''
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
            "PYTHONPATH": str(staging),
            "PYTHONIOENCODING": "utf-8",
            "PACKAGED_PROBE_OUT": str(probe_out),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=staging,
        env=env,
        text=True,
        capture_output=True,
        timeout=75,
    )
    if result.returncode:
        print("--- PACKAGED STDOUT ---")
        print(result.stdout)
        print("--- PACKAGED STDERR ---")
        print(result.stderr)
        raise SystemExit(f"Packaged staging import failed rc={result.returncode}")

    probe = json.loads(probe_out.read_text(encoding="utf-8"))
    assert probe["version"] == "4.6.6", probe
    assert probe["routes"] == 243, probe
    assert probe["duplicate_routes"] == 0, probe
    assert probe["openapi_paths"] == 220, probe
    assert probe["openapi_schemas"] == 36, probe
    assert probe["historical_modules_loaded"] == [], probe["historical_modules_loaded"]

    contract_path = CANDIDATE / "CANDIDATE_CONTRACT.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
        contract["packaged_staging_import"] = "ok"
        contract["packaged_staging_files"] = len(copy_files)
        contract["packaged_openapi_sha"] = probe["openapi_sha"]
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("PACKAGED STAGING OK")
    print("files", len(copy_files), "required", len(required))
    print("routes", probe["routes"], "openapi", probe["openapi_paths"], probe["openapi_schemas"])
    print("openapi sha", probe["openapi_sha"])
finally:
    shutil.rmtree(staging, ignore_errors=True)
