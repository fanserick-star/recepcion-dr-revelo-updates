from __future__ import annotations

"""Remove the last executable version-layer chain from the flat Reception candidate.

The first refactor made historical sources physical modules, but kept a registry
with keys such as app_patch_4525 and assignments such as
``previous = _rf_layers[...]``.  That still models the old release chain at
runtime.  This pass converts those references into ordinary imports between
semantic feature modules and leaves startup as a deterministic list of current
features.

It intentionally runs only on refactor_build/reception_flat_466.  Production
packages and release channels are never touched by this tool.
"""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "refactor_build" / "reception_flat_466"
META = OUT / "refactor_meta.json"

FEATURE_NAMES = {
    "app_prev_4458": "payments_and_agenda",
    "app_patch_4459": "billing_non_billable",
    "app_patch_4461": "receipt_thermal_layout",
    "app_patch_4462": "receipt_classification",
    "app_patch_4463": "receipt_preview",
    "app_patch_4464": "receipt_margins",
    "app_patch_4465": "receipt_unified_layout",
    "app_patch_4466": "receipt_raster",
    "app_patch_4467": "receipt_readability",
    "app_patch_4468": "receipt_size",
    "app_patch_4469": "receipt_width",
    "app_patch_4470": "attention_identity",
    "app_patch_4473": "interface_recovery",
    "app_patch_4474": "printing_queue",
    "app_patch_4475": "attention_transaction",
    "app_patch_4476": "billing_history",
    "app_patch_4477": "billing_discard",
    "app_patch_4478": "billing_actions",
    "app_patch_4479": "interface_cleanup",
    "app_patch_4480": "billing_issued_filters",
    "app_patch_4481": "billing_modal_cleanup",
    "app_patch_4482": "update_restart",
    "app_patch_4483": "update_launcher",
    "app_patch_4484": "billing_optional_email",
    "app_patch_4485": "payment_proof",
    "app_patch_4486": "printing_menu",
    "app_patch_4487": "payment_proof_margins",
    "app_patch_4488": "payment_proof_layout",
    "app_patch_4489": "billing_data_form",
    "app_patch_4490": "billing_data_form_compact",
    "app_patch_4491": "billing_data_form_layout",
    "app_patch_4501": "system_status",
    "app_patch_4502": "consultation_discount",
    "app_patch_4504": "payment_terminal",
    "app_patch_4505": "payment_terminal_interface",
    "app_patch_4506": "payment_terminal_config",
    "app_patch_4507": "payment_terminal_manual",
    "app_patch_4508": "history_bridge",
    "app_patch_4509": "history_bridge",
    "app_patch_4510": "history_bridge",
    "app_patch_4511": "history_bridge",
    "app_patch_4517": "launcher_status",
    "app_patch_4518": "version_display",
    "app_patch_4519": "version_sidebar",
    "app_patch_4520": "history_transport",
    "app_patch_4521": "history_attention_type",
    "app_patch_4522": "history_cancellation",
    "app_patch_4523": "payment_terminal_feedback",
    "app_patch_4524": "history_patient_details",
    "app_patch_4525": "payment_terminal_panel",
}
HIST_TO_MODULE = {"app_base_4428": "core_runtime"}
HIST_TO_MODULE.update({key: "reception_" + value for key, value in FEATURE_NAMES.items()})


def _layer_key(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    value = node.value
    is_layers = isinstance(value, ast.Name) and value.id == "_rf_layers"
    is_layers = is_layers or (isinstance(value, ast.Attribute) and value.attr == "_rf_layers")
    if not is_layers:
        return None
    key = node.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        return key.value if key.value in HIST_TO_MODULE else None
    return None


def _historical_getattr(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "getattr":
        return None
    if len(node.args) < 2:
        return None
    key = _layer_key(node.args[0])
    attr = node.args[1]
    if key and isinstance(attr, ast.Constant) and isinstance(attr.value, str):
        return key, attr.value
    return None


def _contains_previous_walk(node: ast.AST) -> bool:
    for item in ast.walk(node):
        if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name) or item.func.id != "getattr":
            continue
        if len(item.args) >= 2 and isinstance(item.args[1], ast.Constant) and item.args[1].value == "previous":
            return True
    return False


def _semantic_alias(old: str, module: str) -> str:
    short = module.removeprefix("reception_")
    if old == "previous" or old.startswith("_rf_alias_"):
        return "_dep_" + re.sub(r"\W+", "_", short)
    return old


class RenameNames(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name):
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        return node


class ReplaceLegacyLookups(ast.NodeTransformer):
    def __init__(self, imports: dict[str, str]):
        self.imports = imports
        self.unresolved_runtime_lookups: list[str] = []

    def visit_Call(self, node: ast.Call):
        node = self.generic_visit(node)
        fn = node.func
        is_lookup = isinstance(fn, ast.Name) and fn.id == "_rf_module_lookup"
        is_lookup = is_lookup or (
            isinstance(fn, ast.Attribute)
            and fn.attr == "_rf_module_lookup"
        )
        if not is_lookup:
            return node
        if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in HIST_TO_MODULE:
            hist = str(node.args[0].value)
            module = HIST_TO_MODULE[hist]
            alias = "_dep_lookup_" + module.removeprefix("reception_")
            self.imports[alias] = module
            return ast.copy_location(ast.Name(id=alias, ctx=ast.Load()), node)
        self.unresolved_runtime_lookups.append(ast.unparse(node))
        return node


def _strip_chain_bootstrap(body: list[ast.stmt]) -> list[ast.stmt]:
    """Remove only the known APP_VERSION walk through `.previous` links."""
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
    new_body: list[ast.stmt] = []

    for node in tree.body:
        # Remove the compatibility-registry imports.  features_runtime is kept
        # only as the startup side-effect import in app.py.
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
                new_body.append(node)
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
            got = _historical_getattr(node.value)
            if got:
                hist, attr = got
                module = HIST_TO_MODULE[hist]
                imported = ast.ImportFrom(
                    module=module,
                    names=[ast.alias(name=attr, asname=None if target == attr else target)],
                    level=0,
                )
                new_body.append(ast.copy_location(imported, node))
                continue

        new_body.append(node)

    tree.body = new_body
    if alias_renames:
        tree = RenameNames(alias_renames).visit(tree)
        ast.fix_missing_locations(tree)

    lookup_imports: dict[str, str] = {}
    lookup_rewriter = ReplaceLegacyLookups(lookup_imports)
    tree = lookup_rewriter.visit(tree)
    ast.fix_missing_locations(tree)
    if lookup_rewriter.unresolved_runtime_lookups:
        raise RuntimeError(
            f"{path.name}: dynamic legacy module lookup still unresolved: "
            + "; ".join(lookup_rewriter.unresolved_runtime_lookups[:5])
        )
    direct_imports.update(lookup_imports)

    tree.body = _strip_chain_bootstrap(tree.body)

    # Prepend ordinary semantic imports after future imports.  Importing the
    # semantic module object preserves real module globals without a release
    # registry or a synthetic previous-chain.
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

    lines = [
        "from __future__ import annotations",
        "",
        "# Current functional runtime. No historical release registry is used.",
    ]
    lines.extend(f"import {name}" for name in modules)
    lines += [
        "",
        "FEATURE_MODULES = (",
        *[f"    {name}," for name in modules],
        ")",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return modules


def _rewrite_registry_stub() -> None:
    # Kept temporarily because the packaging contract in this branch still
    # lists the filename.  It is deliberately inert and contains no aliases.
    (OUT / "runtime_registry.py").write_text(
        '"""Compatibility filename only; the runtime no longer uses a layer registry."""\n'
        "SEMANTIC_RUNTIME = True\n",
        encoding="utf-8",
        newline="\n",
    )


def _assert_no_legacy_runtime() -> None:
    failures: list[str] = []
    for path in sorted(OUT.glob("*.py")):
        text = path.read_text(encoding="utf-8-sig")
        parsed = ast.parse(text, filename=str(path))
        for node in ast.walk(parsed):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                rendered = ast.unparse(node)
                if "app_patch_" in rendered or "app_prev_" in rendered or "app_base_" in rendered:
                    failures.append(f"{path.name}: {rendered}")
            if isinstance(node, ast.Name) and node.id in {"_rf_layers", "_rf_module_lookup", "_rf_legacy"}:
                failures.append(f"{path.name}: legacy name {node.id}")
            if isinstance(node, ast.Subscript) and _layer_key(node):
                failures.append(f"{path.name}: legacy layer lookup {ast.unparse(node)}")
        if re.search(r"\bprevious\s*=\s*", text):
            failures.append(f"{path.name}: previous assignment remains")
    if failures:
        raise SystemExit("Legacy runtime chain remains:\n" + "\n".join(failures[:40]))


def main() -> None:
    if not OUT.is_dir():
        raise SystemExit("Primero ejecute tools/build_reception_flat_prototype.py")

    reports = []
    targets = [OUT / "app.py"] + sorted(OUT.glob("reception_*.py"))
    for path in targets:
        reports.append(_rewrite_python(path))

    modules = _rewrite_features_runtime()
    _rewrite_registry_stub()
    _assert_no_legacy_runtime()

    meta = json.loads(META.read_text(encoding="utf-8-sig")) if META.exists() else {}
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
