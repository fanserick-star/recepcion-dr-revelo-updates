from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

HISTORICAL_RE = re.compile(r"^app_(?:base|prev|patch)_\d+$")
PROTECTED_PREFIXES = ("data/", "backups/", "update_backups/")
PROTECTED_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".xls", ".xlsx")
PROTECTED_EXACT = {
    ".env",
    "recepcionlauncher.exe",
    "launcherupdater.exe",
    "desinstalar_recepcion_dr_revelo.exe",
    "abrir_recepcion.py",
    "abrir_recepcion.pyw",
    "autoactualizar.py",
    "iniciar.bat",
}
FLAT_REQUIRED = {
    "core_runtime.py",
    "features_runtime.py",
    "azur_client.py",
    "remote_agenda.py",
    "whatsapp_client.py",
}


def embedded_sources(tree: ast.AST) -> dict[str, str]:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == "_EMBEDDED_RUNTIME_SOURCES" for t in node.targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict):
                raise AssertionError("_EMBEDDED_RUNTIME_SOURCES no es dict")
            return value
    return {}


def imports_from(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def ver_tuple(value: object) -> tuple[int, int, int]:
    parts = re.findall(r"\d+", str(value))
    return tuple(int(x) for x in (parts + ["0", "0", "0"])[:3])  # type: ignore[return-value]


def validate(runtime: Path, baseline_app: Path | None = None) -> dict[str, object]:
    runtime = runtime.resolve()
    assert runtime.is_dir(), runtime
    app_path = runtime / "app.py"
    version_path = runtime / "recepcion-version.json"
    manifest_path = runtime / "update_manifest.json"
    for path in (app_path, version_path, manifest_path):
        assert path.is_file(), path

    version_doc = json.loads(version_path.read_text(encoding="utf-8-sig"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    version = str(version_doc.get("version") or "").strip()
    assert version
    for key in ("version", "app_version", "runtime_version"):
        if key in manifest:
            assert str(manifest.get(key) or "").strip() == version, (key, manifest.get(key), version)
    assert manifest.get("version_source") == "recepcion-version.json"
    assert manifest.get("compatibility_version_aliases") is True

    payload = [str(x).replace("\\", "/") for x in manifest.get("copy", [])]
    required = [str(x).replace("\\", "/") for x in manifest.get("required_dependencies", [])]
    assert payload, "manifest.copy vacío"
    assert len(payload) == len(set(payload)), "manifest.copy duplicado"
    assert set(required).issubset(set(payload)), sorted(set(required) - set(payload))

    for rel in payload:
        low = rel.lower()
        assert rel and not rel.startswith("/") and ".." not in rel.split("/"), rel
        assert not low.startswith(PROTECTED_PREFIXES), rel
        assert not low.endswith(PROTECTED_SUFFIXES), rel
        assert low not in PROTECTED_EXACT, rel
        assert (runtime / rel).is_file(), f"payload faltante: {rel}"

    py_files = sorted(runtime / rel for rel in payload if rel.endswith(".py"))
    trees: dict[str, ast.AST] = {}
    for path in py_files:
        text = path.read_text(encoding="utf-8-sig")
        compile(text, str(path), "exec")
        trees[path.name] = ast.parse(text, filename=str(path))

    app_text = app_path.read_text(encoding="utf-8-sig")
    app_tree = trees.get("app.py") or ast.parse(app_text, filename=str(app_path))
    embedded = embedded_sources(app_tree)
    embedded_names = set(embedded)
    physical_modules = {Path(rel).stem for rel in payload if rel.endswith(".py")}
    historical_physical = sorted(name for name in physical_modules if HISTORICAL_RE.match(name))
    assert not historical_physical, historical_physical

    mode = "embedded" if embedded else "flat"
    all_imports: dict[str, set[str]] = {name: imports_from(tree) for name, tree in trees.items()}

    if mode == "embedded":
        historical_embedded = {name for name in embedded_names if HISTORICAL_RE.match(name)}
        if baseline_app is not None:
            base_tree = ast.parse(baseline_app.read_text(encoding="utf-8-sig"), filename=str(baseline_app))
            baseline_hist = {name for name in embedded_sources(base_tree) if HISTORICAL_RE.match(name)}
            unexpected = historical_embedded - baseline_hist
            assert not unexpected, "nuevas capas históricas: " + ", ".join(sorted(unexpected))

        unresolved = set()
        for source_name, names in all_imports.items():
            for name in names:
                if HISTORICAL_RE.match(name) and name not in embedded_names:
                    unresolved.add(f"{source_name}->{name}")
        assert not unresolved, sorted(unresolved)

        if ver_tuple(version) >= (4, 6, 2):
            helper_names = {"remote_agenda", "azur_client", "whatsapp_client"}
            missing = helper_names - embedded_names
            assert not missing, "helpers embebidos faltantes: " + ", ".join(sorted(missing))

        result = {
            "mode": mode,
            "version": version,
            "payload_files": len(payload),
            "required_dependencies": len(required),
            "historical_layers": len(historical_embedded),
            "embedded_helpers": len({"remote_agenda", "azur_client", "whatsapp_client"} & embedded_names),
        }
    else:
        assert "_EMBEDDED_RUNTIME_SOURCES" not in app_text
        assert "MetaPathFinder" not in app_text
        missing = FLAT_REQUIRED - set(payload)
        assert not missing, "runtime físico incompleto: " + ", ".join(sorted(missing))
        missing_required = FLAT_REQUIRED - set(required)
        assert not missing_required, "helpers físicos no declarados como requeridos: " + ", ".join(sorted(missing_required))

        historical_imports = set()
        for source_name, names in all_imports.items():
            for name in names:
                if HISTORICAL_RE.match(name):
                    historical_imports.add(f"{source_name}->{name}")
        assert not historical_imports, sorted(historical_imports)

        # Local runtime imports must resolve inside the declared payload.
        known_local = {
            "core_runtime",
            "features_runtime",
            "azur_client",
            "remote_agenda",
            "whatsapp_client",
            "historia_bridge",
            "historia_lan_transport",
        }
        unresolved_local = set()
        for source_name, names in all_imports.items():
            for name in names & known_local:
                if name not in physical_modules:
                    unresolved_local.add(f"{source_name}->{name}.py")
        assert not unresolved_local, sorted(unresolved_local)

        result = {
            "mode": mode,
            "version": version,
            "payload_files": len(payload),
            "required_dependencies": len(required),
            "historical_layers": 0,
            "physical_helpers": len(FLAT_REQUIRED & set(payload)),
        }

    assert 'Path(__file__).with_name("recepcion-version.json")' in app_text
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--baseline-app", type=Path, default=None)
    args = parser.parse_args()
    result = validate(args.runtime, args.baseline_app)
    print("RUNTIME LAYOUT OK")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
