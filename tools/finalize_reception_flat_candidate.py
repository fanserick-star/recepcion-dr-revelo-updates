from __future__ import annotations

import ast
import hashlib
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

FEATURE_FILES = sorted(p.name for p in OUT.glob("reception_*.py"))
RUNTIME_FILES += ["runtime_registry.py"] + FEATURE_FILES
REQUIRED_DEPENDENCIES += ["runtime_registry.py"] + FEATURE_FILES

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
        "flat_runtime_physical_files": [name for name in RUNTIME_FILES if name.endswith(".py")],
        "isolated_feature_globals": True,
        "embedded_runtime_sources": False,
        "runtime_import_hook": False,
        "manifest_rebuilt_for_flat_candidate": True,
        "runtime_smoke_test": "required: equivalence, bindings, packaged staging and update/rollback",
        "release_channel_modified": False,
    }
)
manifest["notes"] = notes
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Structural candidate gate. Historical names may remain in comments/registry
# metadata, but never as executable imports or embedded source loaders.
app_text = (OUT / "app.py").read_text(encoding="utf-8-sig")
features_text = (OUT / "features_runtime.py").read_text(encoding="utf-8-sig")
combined = app_text + "\n" + features_text + "\n" + "\n".join(
    (OUT / name).read_text(encoding="utf-8-sig") for name in FEATURE_FILES
)
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

# Byte/source integrity gate: physical helper modules must be exactly the same
# audited source that production 4.6.6 embeds. Bridge/LAN files are copied
# byte-for-byte from the audited 4.6.6 package.
def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

source_app = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
source_tree = ast.parse(source_app, filename=str(SOURCE / "app.py"))
embedded = None
for node in source_tree.body:
    if not isinstance(node, ast.Assign):
        continue
    if any(isinstance(t, ast.Name) and t.id == "_EMBEDDED_RUNTIME_SOURCES" for t in node.targets):
        embedded = ast.literal_eval(node.value)
        break
if not isinstance(embedded, dict):
    raise SystemExit("No se pudo leer _EMBEDDED_RUNTIME_SOURCES de Recepción 4.6.6")

helper_source_sha256 = {}
for helper in ("azur_client", "remote_agenda", "whatsapp_client"):
    source = embedded.get(helper)
    if not isinstance(source, str) or not source:
        raise SystemExit(f"Helper embebido ausente en 4.6.6: {helper}")
    expected = sha_bytes(source.lstrip("\ufeff").encode("utf-8"))
    got = sha_bytes((OUT / f"{helper}.py").read_bytes())
    if got != expected:
        raise SystemExit(f"Deriva de helper {helper}: {got} != {expected}")
    helper_source_sha256[helper] = got

for helper, note_key in (
    ("azur_client", "azur_source_sha256"),
    ("whatsapp_client", "whatsapp_source_sha256"),
):
    declared = str(notes.get(note_key) or "").strip().lower()
    if declared and declared != helper_source_sha256[helper]:
        raise SystemExit(
            f"Hash contractual de {helper} cambió: {helper_source_sha256[helper]} != {declared}"
        )

copied_runtime_sha256 = {}
for rel in ("historia_bridge.py", "historia_lan_transport.py", "recepcion-version.json"):
    expected = sha_bytes((SOURCE / rel).read_bytes())
    got = sha_bytes((OUT / rel).read_bytes())
    if got != expected:
        raise SystemExit(f"Archivo copiado cambió durante refactor: {rel}")
    copied_runtime_sha256[rel] = got

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
    "isolated_feature_modules": len(FEATURE_FILES),
    "historical_executable_imports": 0,
    "helper_source_sha256": helper_source_sha256,
    "copied_runtime_sha256": copied_runtime_sha256,
}
(OUT / "CANDIDATE_CONTRACT.json").write_text(
    json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

print("FLAT CANDIDATE PACKAGING CONTRACT OK")
print("source app bytes", contract["source_app_bytes"])
print("candidate app bytes", contract["candidate_app_bytes"])
print("manifest copy files", len(RUNTIME_FILES))
print("helper source hashes", len(helper_source_sha256), "exact")
print("copied runtime hashes", len(copied_runtime_sha256), "exact")
