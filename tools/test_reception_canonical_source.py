from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "recepcion" / "app"
SOURCE = ROOT / "launcher-v1" / "app-channel-source.json"
ACTIVE_FILES = (
    ROOT / ".github" / "workflows" / "publish-reception-app-channel.yml",
    ROOT / ".github" / "workflows" / "audit-active-reception-channel-bytes.yml",
    ROOT / "tools" / "build_reception_app_channel.py",
)


def main() -> None:
    assert CANONICAL.is_dir(), CANONICAL
    source = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    assert source.get("sourceRoot") == "recepcion/app", source.get("sourceRoot")
    assert "files" not in source, "El payload debe derivarse del update_manifest.json canónico"
    assert "appVersion" not in source, "La versión no debe duplicarse en app-channel-source.json"
    assert "minimumLauncher" not in source, "El launcher mínimo debe venir del manifiesto canónico"

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

    archive_readme = (ROOT / "updates" / "README.md").read_text(encoding="utf-8-sig")
    assert "congelado" in archive_readme.lower()
    rollback = ROOT / "releases" / "reception" / "4.6.6"
    assert rollback.is_dir(), "Falta snapshot de rollback 4.6.6"

    print("RECEPTION CANONICAL SOURCE OK")
    print("version", canonical_version)
    print("payload_files", len(payload))
    print("source_root", source["sourceRoot"])
    print("historical_updates", "archive-only")
    print("rollback_4_6_6", "present")


if __name__ == "__main__":
    main()
