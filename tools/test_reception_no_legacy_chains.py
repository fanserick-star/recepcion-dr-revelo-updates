from __future__ import annotations

"""Structural gate: the refactored candidate must not emulate release layers."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "refactor_build" / "reception_flat_466"

if not OUT.is_dir():
    raise SystemExit("Candidate missing; build it first")


def module_level_name_assignment(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return True
    return False


problems: list[str] = []
python_files = sorted(OUT.glob("*.py"))

for path in python_files:
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if re.match(r"app_(?:base|prev|patch)_\d+$", alias.name):
                    problems.append(f"{path.name}: imports historical module {alias.name}")
                if alias.name == "runtime_registry":
                    problems.append(f"{path.name}: imports runtime_registry")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if re.match(r"app_(?:base|prev|patch)_\d+$", module):
                problems.append(f"{path.name}: imports historical module {module}")
            if module == "runtime_registry":
                problems.append(f"{path.name}: imports runtime_registry")
        elif isinstance(node, ast.Name) and node.id in {
            "_rf_layers",
            "_rf_module_lookup",
            "_rf_legacy",
        }:
            problems.append(f"{path.name}: legacy runtime symbol {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if path.name != "runtime_registry.py" and re.fullmatch(
                r"app_(?:base|prev|patch)_\d+", node.value
            ):
                problems.append(f"{path.name}: historical runtime key {node.value}")

    if path.name != "runtime_registry.py":
        if module_level_name_assignment(tree, "previous"):
            problems.append(f"{path.name}: module-level previous release alias")
        if "getattr(_mod, 'previous'" in text or 'getattr(_mod, "previous"' in text:
            problems.append(f"{path.name}: walks previous release chain")

features = (OUT / "features_runtime.py").read_text(encoding="utf-8-sig")
if "_rf_layers" in features or "app_patch_" in features or "app_prev_" in features:
    problems.append("features_runtime.py: historical startup registry remains")

app = (OUT / "app.py").read_text(encoding="utf-8-sig")
if "_rf_layers" in app or "_rf_legacy" in app:
    problems.append("app.py: legacy layer bootstrap remains")

if problems:
    raise SystemExit("LEGACY CHAIN GATE FAILED\n" + "\n".join(problems[:80]))

print("NO LEGACY RELEASE CHAIN OK")
print("python files", len(python_files))
print("historical executable module imports", 0)
print("layer registry lookups", 0)
print("module-level previous release aliases", 0)
print("previous-chain walks", 0)
