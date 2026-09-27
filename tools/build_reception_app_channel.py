from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

PROTECTED_PREFIXES = ("data/", "backups/", "update_backups/")
PROTECTED_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".xls", ".xlsx")
PROTECTED_EXACT = {
    ".env", "recepcionlauncher.exe", "launcherupdater.exe",
    "desinstalar_recepcion_dr_revelo.exe", "abrir_recepcion.py",
    "abrir_recepcion.pyw", "autoactualizar.py", "iniciar.bat",
}
FORBIDDEN_RUNTIME_PREFIXES = ("app_patch_", "app_prev_", "app_base_")


def _git_blob(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"])


def _safe_payload_path(value: object) -> str:
    path = str(value or "").replace("\\", "/").strip()
    assert path and not path.startswith("/") and ".." not in path.split("/"), path
    low = path.lower()
    assert not low.startswith(PROTECTED_PREFIXES), path
    assert low not in PROTECTED_EXACT, path
    assert not low.endswith(PROTECTED_SUFFIXES), path
    base = PurePosixPath(low).name
    assert not (
        base.endswith(".py") and base.startswith(FORBIDDEN_RUNTIME_PREFIXES)
    ), f"Runtime histórico prohibido: {path}"
    return path


def build(source_file: Path, output_file: Path, commit: str, repository: str) -> dict:
    src = json.loads(source_file.read_text(encoding="utf-8-sig"))
    root = str(src.get("sourceRoot") or "").replace("\\", "/").strip().rstrip("/")
    assert root == "recepcion/app", f"sourceRoot no canónico: {root!r}"

    manifest_path = f"{root}/update_manifest.json"
    version_path = f"{root}/recepcion-version.json"
    manifest_bytes = _git_blob(commit, manifest_path)
    version_bytes = _git_blob(commit, version_path)
    manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    version_doc = json.loads(version_bytes.decode("utf-8-sig"))

    version = str(version_doc.get("version") or "").strip()
    assert version, "recepcion-version.json sin versión"
    for key in ("version", "app_version", "runtime_version"):
        assert str(manifest.get(key) or "").strip() == version, (
            key, manifest.get(key), version
        )
    assert manifest.get("version_source") == "recepcion-version.json"
    assert manifest.get("compatibility_version_aliases") is True
    assert manifest.get("mandatory") is True

    payload_paths = [_safe_payload_path(x) for x in manifest.get("copy", [])]
    assert payload_paths and len(payload_paths) == len(set(payload_paths)), "manifest.copy inválido"
    assert "recepcion-version.json" in payload_paths
    assert "update_manifest.json" in payload_paths
    required = {_safe_payload_path(x) for x in manifest.get("required_dependencies", [])}
    assert required.issubset(set(payload_paths)), sorted(required - set(payload_paths))

    files = []
    for rel in payload_paths:
        source = f"{root}/{rel}"
        payload = _git_blob(commit, source)
        if rel.lower().endswith(".py"):
            compile(payload.decode("utf-8-sig"), rel, "exec")
        digest = hashlib.sha256(payload).hexdigest()
        files.append({
            "path": rel,
            "sha256": digest,
            "url": f"https://raw.githubusercontent.com/{repository}/{commit}/{source}",
        })
        print(f"{rel}: bytes={len(payload)} sha256={digest}")

    launcher_minimum = str(manifest.get("launcher_minimum") or "").strip()
    assert launcher_minimum, "update_manifest.json sin launcher_minimum"

    channel = {
        "schema": 3,
        "product": str(src.get("product") or "recepcion-dr-revelo"),
        "status": str(src.get("status") or "stable"),
        "appVersion": version,
        "mandatory": bool(src.get("mandatory", True)),
        "minimumLauncher": launcher_minimum,
        "notes": f"Recepción {version}: {str(src.get('notes') or '').strip()} Canal generado automáticamente desde blobs Git exactos; SHA-256 no se edita a mano.",
        "generatedFromCommit": commit,
        "files": files,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(channel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return channel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("launcher-v1/app-channel-source.json"))
    parser.add_argument("--output", type=Path, default=Path("launcher-v1/app-channel.json"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    result = build(args.source, args.output, args.commit, args.repository)
    print("CHANNEL GENERATED", result["appVersion"], len(result["files"]))


if __name__ == "__main__":
    main()
