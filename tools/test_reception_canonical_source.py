from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "recepcion" / "app"
SOURCE = ROOT / "launcher-v1" / "app-channel-source.json"
FROZEN_UPDATES_TREE = "5f933c6a4a94bd5a10f8f005e1cfe51df4b559f4"
ROLLBACK_466_TREE = "09b32778d10dec3017651d99e36918d07e510ce7"
ACTIVE_FILES = (
    ROOT / ".github" / "workflows" / "publish-reception-app-channel.yml",
    ROOT / ".github" / "workflows" / "audit-active-reception-channel-bytes.yml",
    ROOT / "tools" / "build_reception_app_channel.py",
)


def git_tree(path: str) -> str:
    return subprocess.check_output(["git", "rev-parse", f"HEAD:{path}"], cwd=ROOT, text=True).strip()


def main() -> None:
    assert CANONICAL.is_dir(), CANONICAL
    source = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    assert source.get("sourceRoot") == "recepcion/app", source.get("sourceRoot")
    assert "files" not in source, "El payload debe derivarse del update_manifest.json canónico"
    assert "appVersion" not in source, "La versión no debe duplicarse en app-channel-source.json"
    assert "minimumLauncher" not in source, "El launcher mínimo debe venir del manifiesto canónico"

    stale_runtime_files = {
        "RELEASE_INFO.txt",
        "VERIFICATION.json",
        "reception_deleted_visit_guard.py",
        "reception_history_identity_authority.py",
    }
    present_stale = sorted(name for name in stale_runtime_files if (CANONICAL / name).exists())
    assert not present_stale, "Residuos runtime obsoletos: " + ", ".join(present_stale)

    frontend = (CANONICAL / "static" / "app.js").read_text(encoding="utf-8-sig")
    assert "function syncEditedPatientIntoClientState" in frontend, "Falta sincronizar una ficha editada con Inicio"
    assert "syncEditedPatientIntoClientState(data)" in frontend, "PUT de paciente no refresca el estado visual"
    assert "invalidateAttentionWeekCache()" in frontend, "Editar paciente no invalida la caché de agenda"
    assert "renderHomeDayFromCache(selectedHomeDate)" in frontend, "Inicio no se redibuja con el nombre actualizado"

    version = json.loads((CANONICAL / "recepcion-version.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((CANONICAL / "update_manifest.json").read_text(encoding="utf-8-sig"))
    canonical_version = str(version.get("version") or "").strip()
    assert canonical_version
    for key in ("version", "app_version", "runtime_version"):
        assert str(manifest.get(key) or "").strip() == canonical_version, key

    payload = [str(x).replace("\\", "/") for x in manifest.get("copy", [])]
    assert payload and len(payload) == len(set(payload))
    for rel in payload:
        assert (CANONICAL / rel).is_file(), f"Falta en fuente canónica: {rel}"

    for path in ACTIVE_FILES:
        text = path.read_text(encoding="utf-8-sig")
        assert "updates/v4_6_" not in text, f"Dependencia activa a updates/: {path}"
        assert "v4_6_7_consolidated_runtime" not in text, f"Fuente versionada activa: {path}"

    updates_tree = git_tree("updates")
    assert updates_tree == FROZEN_UPDATES_TREE, (
        "updates/ dejó de ser el marcador histórico congelado",
        updates_tree,
        FROZEN_UPDATES_TREE,
    )
    archive_readme = (ROOT / "updates" / "README.md").read_text(encoding="utf-8-sig")
    assert "congelado" in archive_readme.lower()

    rollback = ROOT / "releases" / "reception" / "4.6.6"
    assert rollback.is_dir(), "Falta snapshot de rollback 4.6.6"
    rollback_tree = git_tree("releases/reception/4.6.6")
    assert rollback_tree == ROLLBACK_466_TREE, (
        "El rollback 4.6.6 no coincide con los bytes exactos publicados",
        rollback_tree,
        ROLLBACK_466_TREE,
    )
    rollback_version = json.loads((rollback / "recepcion-version.json").read_text(encoding="utf-8-sig"))
    rollback_manifest = json.loads((rollback / "update_manifest.json").read_text(encoding="utf-8-sig"))
    assert str(rollback_version.get("version") or "").strip() == "4.6.6"
    for key in ("version", "app_version", "runtime_version"):
        assert str(rollback_manifest.get(key) or "").strip() == "4.6.6", key

    print("RECEPTION CANONICAL SOURCE OK")
    print("version", canonical_version)
    print("payload_files", len(payload))
    print("source_root", source["sourceRoot"])
    print("historical_updates_tree", updates_tree)
    print("rollback_4_6_6_exact_tree", rollback_tree)


if __name__ == "__main__":
    main()
