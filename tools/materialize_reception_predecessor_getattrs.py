from __future__ import annotations

"""Materialize legacy getattr(module, 'previous') references as direct imports.

Run after remove_reception_legacy_layer_chain.py. Some historical patches used
`getattr(previous, 'previous', None)` instead of the syntactic
`previous.previous` form. The runtime linked list is gone, so resolve those
known predecessor hops at build time to the semantic module that old code
actually reached.
"""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "refactor_build" / "reception_flat_466"
META = OUT / "refactor_meta.json"


def runtime_maps(meta: dict) -> tuple[dict[str, str], dict[str, str]]:
    hist_to_module = {"app_base_4428": "core_runtime"}
    hist_to_module.update({str(k): str(v) for k, v in (meta.get("feature_modules") or {}).items()})
    aliases = {str(k): str(v) for k, v in (meta.get("removed_release_only_layers") or {}).items()}
    for key in aliases:
        target = aliases[key]
        seen = {key}
        while target in aliases and target not in seen:
            seen.add(target)
            target = aliases[target]
        if target not in hist_to_module:
            raise RuntimeError(f"Alias histórico sin destino: {key} -> {target}")
        hist_to_module[key] = hist_to_module[target]
    previous_by_module = {
        str(k): str(v)
        for k, v in (meta.get("semantic_previous_targets_materialized") or {}).items()
    }
    return hist_to_module, previous_by_module


class MaterializeGetattrPrevious(ast.NodeTransformer):
    def __init__(
        self,
        alias_modules: dict[str, str],
        hist_to_module: dict[str, str],
        previous_by_module: dict[str, str],
        new_imports: dict[str, str],
    ):
        self.alias_modules = alias_modules
        self.hist_to_module = hist_to_module
        self.previous_by_module = previous_by_module
        self.new_imports = new_imports
        self.replacements = 0

    def visit_Call(self, node: ast.Call):
        node = self.generic_visit(node)
        if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            return node
        if len(node.args) < 2:
            return node
        attr = node.args[1]
        if not isinstance(attr, ast.Constant) or attr.value != "previous":
            return node
        base = node.args[0]
        if not isinstance(base, ast.Name) or base.id not in self.alias_modules:
            return node

        current_module = self.alias_modules[base.id]
        previous_hist = self.previous_by_module.get(current_module)
        if not previous_hist:
            raise RuntimeError(
                f"No se puede materializar getattr({base.id}, 'previous'): "
                f"{current_module} no tiene predecesor auditado"
            )
        target_module = self.hist_to_module.get(previous_hist)
        if not target_module:
            raise RuntimeError(
                f"Predecesor histórico {previous_hist} de {current_module} no tiene módulo semántico"
            )

        alias = "_dep_chain_" + re.sub(r"\W+", "_", target_module.removeprefix("reception_"))
        self.new_imports[alias] = target_module
        self.alias_modules[alias] = target_module
        self.replacements += 1
        return ast.copy_location(ast.Name(id=alias, ctx=ast.Load()), node)


def import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for item in node.names:
            if item.name == "core_runtime" or item.name.startswith("reception_"):
                aliases[item.asname or item.name] = item.name
    return aliases


def rewrite(path: Path, hist_to_module: dict[str, str], previous_by_module: dict[str, str]) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    aliases = import_aliases(tree)
    new_imports: dict[str, str] = {}
    tx = MaterializeGetattrPrevious(aliases, hist_to_module, previous_by_module, new_imports)
    tree = tx.visit(tree)
    ast.fix_missing_locations(tree)
    if not tx.replacements:
        return 0

    imports = [
        ast.Import(names=[ast.alias(name=module, asname=None if alias == module else alias)])
        for alias, module in sorted(new_imports.items())
        if alias not in import_aliases(tree)
    ]
    insert_at = 0
    while insert_at < len(tree.body):
        node = tree.body[insert_at]
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_at += 1
            continue
        if isinstance(node, ast.Import):
            insert_at += 1
            continue
        break
    tree.body[insert_at:insert_at] = imports
    ast.fix_missing_locations(tree)

    output = ast.unparse(tree).rstrip() + "\n"
    compile(output, str(path), "exec")
    path.write_text(output, encoding="utf-8", newline="\n")
    return tx.replacements


def unresolved_semantic_previous(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    aliases = import_aliases(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            continue
        if len(node.args) < 2:
            continue
        base, attr = node.args[0], node.args[1]
        if (
            isinstance(base, ast.Name)
            and base.id in aliases
            and isinstance(attr, ast.Constant)
            and attr.value == "previous"
        ):
            out.append(ast.unparse(node))
    return out


def main() -> None:
    if not META.is_file():
        raise SystemExit("Falta refactor_meta.json; ejecute primero la consolidación semántica")
    meta = json.loads(META.read_text(encoding="utf-8-sig"))
    hist_to_module, previous_by_module = runtime_maps(meta)
    total = 0
    files_changed = 0
    targets = [OUT / "app.py", *sorted(OUT.glob("reception_*.py"))]
    for path in targets:
        count = rewrite(path, hist_to_module, previous_by_module)
        if count:
            total += count
            files_changed += 1

    unresolved: list[str] = []
    for path in targets:
        unresolved.extend(f"{path.name}: {item}" for item in unresolved_semantic_previous(path))
    if unresolved:
        raise SystemExit("Persisten navegaciones previous semánticas:\n" + "\n".join(unresolved[:60]))

    meta["semantic_getattr_previous_materialized"] = total
    meta["semantic_getattr_previous_files"] = files_changed
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("PREDECESSOR GETATTRS MATERIALIZED")
    print("replacements", total)
    print("files changed", files_changed)
    print("unresolved semantic previous getattr", 0)


if __name__ == "__main__":
    main()
