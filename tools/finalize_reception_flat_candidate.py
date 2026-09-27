from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "updates" / "v4_6_6_fast_attention_save"
OUT = ROOT / "refactor_build" / "reception_flat_466"
MANIFEST = OUT / "update_manifest.json"

RUNTIME_FILES = [
    "app.py",
    "core_runtime.py",
    "features_runtime.py",
    "azur_client.py",
    "remote_agenda.py",
    "whatsapp_client.py",
    "historia_bridge.py",
    "historia_lan_transport.py",
    "recepcion-version.json",
    "update_manifest.json",
    "static/runtime_keep.txt",
]

REQUIRED_DEPENDENCIES = [
    "core_runtime.py",
    "features_runtime.py",
    "azur_client.py",
    "remote_agenda.py",
    "whatsapp_client.py",
    "historia_bridge.py",
    "historia_lan_transport.py",
]

if not OUT.is_dir():
    raise SystemExit("Primero ejecute tools/build_reception_flat_prototype.py")

for rel in RUNTIME_FILES:
    path = OUT / rel
    if not path.exists():
        raise SystemExit(f"Falta archivo requerido del candidato: {rel}")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
manifest["required_dependencies"] = REQUIRED_DEPENDENCIES
manifest["copy"] = RUNTIME_FILES

notes = dict(manifest.get("notes") or {})
notes.update(
    {
        "candidate_only": True,
        "production_status": "refactor-verified-not-published",
        "consolidated_runtime": True,
        "external_patch_chain_required": False,
        "flat_runtime_physical_files": [
            "app.py",
            "core_runtime.py",
            "features_runtime.py",
            "azur_client.py",
            "remote_agenda.py",
            "whatsapp_client.py",
        ],
        "embedded_runtime_sources": False,
        "runtime_import_hook": False,
        "manifest_rebuilt_for_flat_candidate": True,
        "runtime_smoke_test": "validated by tools/test_reception_flat_prototype.py",
        "release_channel_modified": False,
    }
)
manifest["notes"] = notes
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Structural candidate gate. Historical names may remain in comments/registry
# metadata, but never as executable imports or embedded source loaders.
app_text = (OUT / "app.py").read_text(encoding="utf-8-sig")
features_text = (OUT / "features_runtime.py").read_text(encoding="utf-8-sig")
combined = app_text + "\n" + features_text
for forbidden in ("_EMBEDDED_RUNTIME_SOURCES", "MetaPathFinder", "exec(code"):
    if forbidden in combined:
        raise SystemExit(f"Residuo estructural prohibido: {forbidden}")
if re.search(r"^\s*(?:import|from)\s+app_(?:base|prev|patch)_\d+", combined, re.M):
    raise SystemExit("Persisten imports ejecutables hacia capas históricas")

if (OUT / "app.py").stat().st_size >= 100_000:
    raise SystemExit("app.py del candidato volvió a crecer por encima de 100 KB")

for py_name in (
    "app.py",
    "core_runtime.py",
    "features_runtime.py",
    "azur_client.py",
    "remote_agenda.py",
    "whatsapp_client.py",
    "historia_bridge.py",
    "historia_lan_transport.py",
):
    py = OUT / py_name
    compile(py.read_text(encoding="utf-8-sig"), str(py), "exec")

contract = {
    "status": "candidate",
    "production_published": False,
    "version": str(manifest.get("version") or ""),
    "source_app_bytes": (SOURCE / "app.py").stat().st_size,
    "candidate_app_bytes": (OUT / "app.py").stat().st_size,
    "core_runtime_bytes": (OUT / "core_runtime.py").stat().st_size,
    "features_runtime_bytes": (OUT / "features_runtime.py").stat().st_size,
    "runtime_files": RUNTIME_FILES,
    "required_dependencies": REQUIRED_DEPENDENCIES,
    "forbidden_loader_residues": 0,
    "historical_executable_imports": 0,
}
(OUT / "CANDIDATE_CONTRACT.json").write_text(
    json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

print("FLAT CANDIDATE PACKAGING CONTRACT OK")
print("source app bytes", contract["source_app_bytes"])
print("candidate app bytes", contract["candidate_app_bytes"])
print("manifest copy files", len(RUNTIME_FILES))
