from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"])


def git_files(commit: str, root: str) -> set[str]:
    out = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit, root], text=True
    )
    prefix = root.rstrip("/") + "/"
    return {
        line[len(prefix):]
        for line in out.splitlines()
        if line.startswith(prefix)
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    source_path = "historia-clinica/launcher-v1/app-channel-source.json"
    src = json.loads(git_bytes(args.commit, source_path).decode("utf-8-sig"))
    assert src.get("product") == "historia-clinica-dr-revelo"
    assert src.get("sourceRoot") == "historia-clinica/app"
    assert src.get("mandatory") is True
    assert "appVersion" not in src
    assert "files" not in src

    root = str(src["sourceRoot"]).strip().rstrip("/")
    version_doc = json.loads(git_bytes(args.commit, f"{root}/historia-version.json").decode("utf-8-sig"))
    version = str(version_doc["version"]).strip()
    assert version

    manifest = json.loads(git_bytes(args.commit, f"{root}/update_manifest.json").decode("utf-8-sig"))
    for key in ("version", "app_version", "runtime_version"):
        assert str(manifest.get(key, "")).strip() == version, (key, manifest.get(key), version)
    assert manifest.get("product") == "historia-clinica-dr-revelo"
    assert manifest.get("mandatory") is True
    assert manifest.get("version_source") == "historia-version.json"

    files = [str(x).replace("\\", "/") for x in (manifest.get("copy") or [])]
    assert files and len(files) == len(set(files))
    assert {"historia-version.json", "update_manifest.json"} <= set(files)
    assert set(manifest.get("required_dependencies") or []) <= set(files)

    actual = git_files(args.commit, root)
    assert actual == set(files), ("runtime fuera del manifiesto", sorted(actual - set(files)), sorted(set(files) - actual))

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

    generated = []
    for rel in files:
        low = rel.lower()
        assert rel and not rel.startswith("/") and ".." not in rel.split("/"), rel
        assert not low.startswith(protected_prefixes), rel
        assert low not in protected_exact, rel
        assert not low.endswith(protected_suffixes), rel
        payload = git_bytes(args.commit, f"{root}/{rel}")
        if rel.endswith(".py"):
            compile(payload.decode("utf-8-sig"), rel, "exec")
        generated.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "url": f"https://raw.githubusercontent.com/{args.repository}/{args.commit}/{root}/{rel}",
            }
        )

    purpose = str((manifest.get("notes") or {}).get("purpose") or "runtime clínico consolidado").strip()
    channel = {
        "schema": 3,
        "product": src["product"],
        "status": src.get("status", "stable"),
        "appVersion": version,
        "mandatory": True,
        "minimumLauncher": str(manifest.get("launcher_minimum") or "1.0.8"),
        "notes": f"Historia Clínica {version}: {purpose} Fuente canónica única en historia-clinica/app; canal generado desde blobs Git exactos; SHA-256 no se edita a mano.",
        "generatedFromCommit": args.commit,
        "files": generated,
    }

    output = Path("historia-clinica/launcher-v1/app-channel.json")
    output.write_text(json.dumps(channel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Generated", output, "version", version, "files", len(generated))


if __name__ == "__main__":
    main()
