from __future__ import annotations

"""Turn the flat Reception candidate into a semantic runtime.

The first flattening pass already extracts the embedded releases into physical
feature modules.  This second pass removes the remaining executable release
registry (`app_patch_*`, `_rf_layers` and `.previous` walks) and replaces it with
ordinary imports between modules named by function.

Only refactor_build/reception_flat_466 is changed.  Production is never touched.
"""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "refactor_build" / "reception_flat_466"
META = OUT / "refactor_meta.json"


def _load_runtime_map() -> tuple[dict[str, str], dict]:
    meta = json.loads(META.read_text(encoding="utf-8-sig"))
    mapping = {"app_base_4428": "core_runtime"}
    mapping.update({str(k): str(v) for k, v in (meta.get("feature_modules") or {}).items()})

    # Three historical releases were already proven to be version-only aliases
    # and therefore have no generated physical module. Resolve them to the real
    # semantic implementation they alias.
    aliases = {str(k): str(v) for k, v in (meta.get("removed_release_only_layers") or {}).items()}
    for key in aliases:
        target = aliases[key]
        seen = {key}
        while target in aliases and target not in seen:
            seen.add(target)
            target = aliases[target]
        if target not in mapping:
            raise RuntimeError(f"Alias histórico sin implementación semántica: {key} -> {target}")
        mapping[key] = mapping[target]
    return mapping, meta


HIST_TO_MODULE, BUILD_META = _load_runtime_map()
STABLE_MODULES = set(HIST_TO_MODULE.values())


def _layer_key(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    value = node.value
    is_layers = isinstance(value, ast.Name) and value.id == "_rf_layers"
    is_layers = is_layers or (isinstance(value, ast.Attribute) and value.attr == "_rf_layers")
    if not is_layers:
        return None
    key = node.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in HIST_TO_MODULE:
        return key.value
    return None


def _historical_getattr(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "getattr":
        return None
    if len(node.args) < 2:
        return None
    hist = _layer_key(node.args[0])
    attr = node.args[1]
    if hist and isinstance(attr, ast.Constant) and isinstance(attr.value, str):
        return hist, attr.value
    return None


def _contains_previous_walk(node: ast.AST) -> bool:
    for item in ast.walk(node):
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name) or item.func.id != "getattr":
            continue
        if len(item.args) >= 2 and isinstance(item.args[1], ast.Constant) and item.args[1].value == "previous":
            return True
    return False


def _semantic_alias(old: str, module: str) -> str:
    if old == "core":
        return "core"
    if old == "previous" or old.startswith("_rf_alias_"):
        return "_dep_" + re.sub(r"\W+", "_", module.removeprefix("reception_"))
    return old


class RenameNames(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name):
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        return node


class ReplaceLegacyRuntime(ast.NodeTransformer):
    """Rewrite dynamic registry lookups to ordinary sys.modules lookups."""

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str) and node.value in HIST_TO_MODULE:
            return ast.copy_location(ast.Constant(HIST_TO_MODULE[node.value]), node)
        return node

    def visit_Call(self, node: ast.Call):
        node = self.generic_visit(node)
        fn = node.func
        is_lookup = isinstance(fn, ast.Name) and fn.id == "_rf_module_lookup"
        is_lookup = is_lookup or (isinstance(fn, ast.Attribute) and fn.attr == "_rf_module_lookup")
        if is_lookup:
            node.func = ast.Attribute(
                value=ast.Attribute(value=ast.Name(id="sys", ctx=ast.Load()), attr="modules", ctx=ast.Load()),
                attr="get",
                ctx=ast.Load(),
            )
        return node


def _strip_chain_bootstrap(body: list[ast.stmt]) -> list[ast.stmt]:
    """Remove only the known APP_VERSION traversal through `.previous`."""
    out: list[ast.stmt] = []
    i = 0
    while i < len(body):
        if (
            i + 2 < len(body)
            and isinstance(body[i], ast.Assign)
            and len(body[i].targets) == 1
            and isinstance(body[i].targets[0], ast.Name)
            and body[i].targets[0].id == "_mod"
            and isinstance(body[i + 1], ast.Assign)
            and len(body[i + 1].targets) == 1
            and isinstance(body[i + 1].targets[0], ast.Name)
            and body[i + 1].targets[0].id == "_seen"
            and isinstance(body[i + 2], (ast.For, ast.While))
            and _contains_previous_walk(body[i + 2])
        ):
            i += 3
            continue
        out.append(body[i])
        i += 1
    return out


def _rewrite_python(path: Path) -> dict:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))

    alias_renames: dict[str, str] = {}
    direct_imports: dict[str, str] = {}
    body: list[ast.stmt] = []

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "runtime_registry":
            continue

        if isinstance(node, ast.Import):
            kept = []
            for item in node.names:
                if item.name == "runtime_registry":
                    continue
                if item.name == "features_runtime" and item.asname == "_rf_legacy":
                    kept.append(ast.alias(name="features_runtime", asname=None))
                else:
                    kept.append(item)
            if kept:
                node.names = kept
                body.append(node)
            continue

        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            hist = _layer_key(node.value)
            if hist:
                module = HIST_TO_MODULE[hist]
                alias = _semantic_alias(target, module)
                alias_renames[target] = alias
                direct_imports[alias] = module
                continue

            imported_attr = _historical_getattr(node.value)
            if imported_attr:
                hist, attr = imported_attr
                module = HIST_TO_MODULE[hist]
                body.append(
                    ast.copy_location(
                        ast.ImportFrom(
                            module=module,
                            names=[ast.alias(name=attr, asname=None if target == attr else target)],
                            level=0,
                        ),
                        node,
                    )
                )
                continue

        body.append(node)

    tree.body = body
    if alias_renames:
        tree = RenameNames(alias_renames).visit(tree)
        ast.fix_missing_locations(tree)

    tree = ReplaceLegacyRuntime().visit(tree)
    ast.fix_missing_locations(tree)
    tree.body = _strip_chain_bootstrap(tree.body)

    imports = [
        ast.Import(names=[ast.alias(name=module, asname=None if alias == module else alias)])
        for alias, module in sorted(direct_imports.items())
    ]
    insert_at = 0
    while insert_at < len(tree.body):
        node = tree.body[insert_at]
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_at += 1
            continue
        break
    tree.body[insert_at:insert_at] = imports
    ast.fix_missing_locations(tree)

    output = ast.unparse(tree).rstrip() + "\n"
    compile(output, str(path), "exec")
    path.write_text(output, encoding="utf-8", newline="\n")
    return {
        "file": path.name,
        "semantic_imports": sorted(set(direct_imports.values())),
        "renamed_aliases": alias_renames,
    }


def _rewrite_features_runtime() -> list[str]:
    path = OUT / "features_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    modules: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for item in node.names:
            if item.name.startswith("reception_") and item.name not in modules:
                modules.append(item.name)

    text = [
        "from __future__ import annotations",
        "",
        "# Deterministic current runtime. No historical release registry.",
        *[f"import {name}" for name in modules],
        "",
        "FEATURE_MODULES = (",
        *[f"    {name}," for name in modules],
        ")",
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8", newline="\n")
    return modules


def _rewrite_registry_stub() -> None:
    # The packaging contract still lists this filename during the transition.
    # It is inert, imported nowhere, and contains no release aliases.
    (OUT / "runtime_registry.py").write_text(
        '"""Compatibility filename only; no runtime layer registry remains."""\n'
        "SEMANTIC_RUNTIME = True\n",
        encoding="utf-8",
        newline="\n",
    )


def _assert_no_legacy_runtime() -> None:
    failures: list[str] = []
    for path in sorted(OUT.glob("*.py")):
        text = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "runtime_registry" or alias.name in HIST_TO_MODULE:
                        failures.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") == "runtime_registry" or (node.module or "") in HIST_TO_MODULE:
                    failures.append(f"{path.name}: from {node.module}")
            elif isinstance(node, ast.Name) and node.id in {"_rf_layers", "_rf_module_lookup", "_rf_legacy"}:
                failures.append(f"{path.name}: legacy symbol {node.id}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in HIST_TO_MODULE:
                failures.append(f"{path.name}: historical runtime key {node.value}")
        if path.name != "runtime_registry.py" and re.search(r"\bprevious\s*=\s*", text):
            failures.append(f"{path.name}: previous assignment")
        if "getattr(_mod, 'previous'" in text or 'getattr(_mod, "previous"' in text:
            failures.append(f"{path.name}: previous-chain walk")
    if failures:
        raise SystemExit("Legacy runtime chain remains:\n" + "\n".join(failures[:80]))


def main() -> None:
    if not OUT.is_dir() or not META.is_file():
        raise SystemExit("Primero ejecute tools/build_reception_flat_prototype.py")

    reports = []
    for path in [OUT / "app.py", *sorted(OUT.glob("reception_*.py"))]:
        reports.append(_rewrite_python(path))

    modules = _rewrite_features_runtime()
    _rewrite_registry_stub()
    _assert_no_legacy_runtime()

    meta = dict(BUILD_META)
    meta.update(
        {
            "semantic_runtime": True,
            "historical_runtime_registry": False,
            "historical_runtime_layer_count": 0,
            "previous_release_chain": False,
            "semantic_startup_modules": modules,
            "semantic_rewrite_files": reports,
        }
    )
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("SEMANTIC RUNTIME GENERATED")
    print("feature modules", len(modules))
    print("legacy executable layers", 0)
    print("previous release chain", False)


if __name__ == "__main__":
    main()
