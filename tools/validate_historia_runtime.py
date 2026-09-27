from __future__ import annotations

import json
from pathlib import Path


def validate_runtime(root: Path) -> str:
    root = Path(root)
    version_path = root / "historia-version.json"
    manifest_path = root / "update_manifest.json"
    assert version_path.is_file(), version_path
    assert manifest_path.is_file(), manifest_path

    version = str(json.loads(version_path.read_text(encoding="utf-8-sig"))["version"]).strip()
    assert version, "historia-version.json no contiene una versión válida"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    assert manifest.get("product") == "historia-clinica-dr-revelo"
    for key in ("version", "app_version", "runtime_version"):
        assert str(manifest.get(key, "")).strip() == version, (key, manifest.get(key), version)
    assert manifest.get("version_source") == "historia-version.json"
    assert manifest.get("mandatory") is True

    copy = [str(x).replace("\\", "/") for x in (manifest.get("copy") or [])]
    deps = [str(x).replace("\\", "/") for x in (manifest.get("required_dependencies") or [])]
    assert copy and len(copy) == len(set(copy)), "copy vacío o duplicado"
    assert set(deps) <= set(copy), "required_dependencies fuera de copy"
    assert {"historia-version.json", "update_manifest.json"} <= set(copy)

    protected_prefixes = ("data/", "backups/", "update_backups/")
    protected_suffixes = (".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".xls", ".xlsx")
    protected_exact = {
        ".env",
        "historiaclinicalauncher.exe",
        "historialauncherupdater.exe",
        "desinstalar_historia_clinica_dr_revelo.exe",
        "abrir_historia_clinica.py",
        "iniciar.bat",
    }

    for rel in copy:
        low = rel.lower()
        assert rel and not rel.startswith("/") and ".." not in rel.split("/"), rel
        assert not low.startswith(protected_prefixes), rel
        assert low not in protected_exact, rel
        assert not low.endswith(protected_suffixes), rel
        path = root / rel
        assert path.is_file(), f"Archivo faltante: {rel}"
        if rel.endswith(".py"):
            compile(path.read_text(encoding="utf-8-sig"), rel, "exec")

    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert actual == set(copy), ("runtime fuera del manifiesto", sorted(actual - set(copy)), sorted(set(copy) - actual))

    app = (root / "app.py").read_text(encoding="utf-8-sig")
    cloud = (root / "cloud_sync.py").read_text(encoding="utf-8-sig")
    docs = (root / "documentos_clinicos.py").read_text(encoding="utf-8-sig")
    assert 'VERSION_PATH = ROOT / "historia-version.json"' in app
    assert "HISTORIA_DATABASE_URL" in cloud
    assert 'HISTORIA_NEON_ENDPOINT_ID = "ep-sweet-mud-arlsk7qa"' in cloud
    assert 'HISTORIA_CLOUD_IDENTITY = "historia-clinica-dr-revelo"' in cloud
    assert 'CLOUD_SCHEMA = "public"' in cloud
    assert "ON CONFLICT DO NOTHING" in cloud
    assert "conn.commit()" in app
    assert "cleanup_cancelled_queue_drafts" in app
    assert "merge_safe_duplicate_patients" in app
    assert "_ensure_official_doctor_logo" in docs

    css = root / "static/style.css"
    if css.is_file():
        text = css.read_text(encoding="utf-8-sig")
        assert text.count("/*") == text.count("*/")
        assert text.count("{") == text.count("}")

    notes = manifest.get("notes") or {}
    assert notes.get("runtime_consolidated") is True
    assert notes.get("self_contained_update") is True
    assert notes.get("external_historical_parts_required") is False
    assert notes.get("patient_data_destructive_changes") is False
    assert notes.get("signed_history_protected") is True
    assert notes.get("rollback") is True

    return version


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("historia-clinica/app")
    resolved = validate_runtime(target)
    print("HISTORIA_RUNTIME_OK", resolved, target)
