from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "updates" / "v4_6_6_fast_attention_save"
SOURCE_APP = SOURCE_DIR / "app.py"
OUT = ROOT / "refactor_build" / "reception_flat_466"

text = SOURCE_APP.read_text(encoding="utf-8-sig")
tree = ast.parse(text, filename=str(SOURCE_APP))
embedded = None
embedded_node = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_EMBEDDED_RUNTIME_SOURCES":
                embedded = ast.literal_eval(node.value)
                embedded_node = node
                break
if not isinstance(embedded, dict):
    raise SystemExit("No se encontró _EMBEDDED_RUNTIME_SOURCES")
embedded = {str(k): str(v) for k, v in embedded.items()}

HELPERS = {"azur_client", "remote_agenda", "whatsapp_client"}
HIST = {name for name in embedded if name.startswith("app_")}
BASE = "app_base_4428"
assert BASE in HIST


def hist_imports(source: str) -> set[str]:
    out = set()
    parsed = ast.parse(source)
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split('.')[0]
                if base in HIST:
                    out.add(base)
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split('.')[0]
            if base in HIST:
                out.add(base)
    return out


deps = {name: hist_imports(embedded[name]) for name in HIST}
order = []
pending = set(HIST)
while pending:
    ready = sorted(name for name in pending if deps[name] <= set(order))
    if not ready:
        raise RuntimeError(f"Dependencias históricas cíclicas/no resueltas: {pending}")
    order.extend(ready)
    pending -= set(ready)
assert order[0] == BASE, order[:3]


def target_names(target):
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        result = set()
        for elt in target.elts:
            result |= target_names(elt)
        return result
    return set()


def module_bound_names(parsed: ast.Module) -> set[str]:
    names = set()
    def walk_stmt(node):
        nonlocal names
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            return
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split('.')[0])
            return
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != '*':
                    names.add(a.asname or a.name)
            return
        if isinstance(node, ast.Assign):
            for t in node.targets:
                names |= target_names(t)
        elif isinstance(node, ast.AnnAssign):
            names |= target_names(node.target)
        elif isinstance(node, ast.AugAssign):
            names |= target_names(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            names |= target_names(node.target)
            for s in node.body + node.orelse: walk_stmt(s)
            return
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars: names |= target_names(item.optional_vars)
            for s in node.body: walk_stmt(s)
            return
        elif isinstance(node, ast.Try):
            for s in node.body + node.orelse + node.finalbody: walk_stmt(s)
            for h in node.handlers:
                if h.name: names.add(h.name)
                for s in h.body: walk_stmt(s)
            return
        elif isinstance(node, ast.If):
            for s in node.body + node.orelse: walk_stmt(s)
            return
        elif isinstance(node, ast.Match):
            for case in node.cases:
                for s in case.body: walk_stmt(s)
            return
        # No descend into expressions or nested scopes.
    for stmt in parsed.body:
        walk_stmt(stmt)
    return names


def safe(s: str) -> str:
    return re.sub(r"\W+", "_", s)


class EmbeddedImportTransformer(ast.NodeTransformer):
    def __init__(self, module_name: str, layer_expr_prefix: str):
        self.module_name = module_name
        self.layer_expr_prefix = layer_expr_prefix
        self.alias_map: dict[str, str] = {}

    def _layer_expr(self):
        # Support both `_rf_layers` and `_rf_legacy._rf_layers` safely.
        return ast.parse(self.layer_expr_prefix, mode="eval").body

    def _unique(self, alias: str) -> str:
        if self.module_name != "outer_current":
            # Real modules preserve public aliases and their live globals.
            return alias
        return f"_rf_alias_{safe(self.module_name)}__{safe(alias)}"

    def visit_Import(self, node: ast.Import):
        keep = []
        generated = []
        for a in node.names:
            base = a.name.split('.')[0]
            if base in HIST:
                original = a.asname or base
                unique = self._unique(original)
                self.alias_map[original] = unique
                generated.append(ast.Assign(
                    targets=[ast.Name(id=unique, ctx=ast.Store())],
                    value=ast.Subscript(
                        value=self._layer_expr(),
                        slice=ast.Constant(base), ctx=ast.Load(),
                    ),
                ))
            else:
                keep.append(a)
        nodes = []
        if keep:
            nodes.append(ast.Import(names=keep))
        nodes.extend(generated)
        return nodes or None

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module.split('.')[0] in HIST:
            base = node.module.split('.')[0]
            generated = []
            for a in node.names:
                if a.name == '*':
                    raise RuntimeError(f"Star import histórico no soportado en {self.module_name}")
                original = a.asname or a.name
                unique = self._unique(original)
                self.alias_map[original] = unique
                generated.append(ast.Assign(
                    targets=[ast.Name(id=unique, ctx=ast.Store())],
                    value=ast.Call(
                        func=ast.Name(id="getattr", ctx=ast.Load()),
                        args=[
                            ast.Subscript(value=self._layer_expr(), slice=ast.Constant(base), ctx=ast.Load()),
                            ast.Constant(a.name),
                        ],
                        keywords=[],
                    ),
                ))
            return generated or None
        return node

    def visit_Call(self, node: ast.Call):
        # Historical layers sometimes resolve another layer through a VARIABLE:
        # sys.modules.get(module_name). Route every such lookup through a helper
        # that prefers the static consolidated registry and falls back to the
        # real sys.modules for ordinary third-party/runtime modules.
        node = self.generic_visit(node)
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr == "get"
            and isinstance(fn.value, ast.Attribute)
            and fn.value.attr == "modules"
            and isinstance(fn.value.value, ast.Name)
            and fn.value.value.id == "sys"
        ):
            lookup_expr = (
                "_rf_module_lookup"
                if self.layer_expr_prefix == "_rf_layers"
                else "_rf_legacy._rf_module_lookup"
            )
            node.func = ast.parse(lookup_expr, mode="eval").body
        return node

    def visit_Name(self, node: ast.Name):
        if node.id in self.alias_map:
            node.id = self.alias_map[node.id]
        return node


def transform_module(modname: str, source: str):
    parsed = ast.parse(source, filename=f"<{modname}>")
    bound = module_bound_names(parsed)
    # Future imports are only legal at file start; the generated file already has one.
    parsed.body = [
        n for n in parsed.body
        if not (isinstance(n, ast.ImportFrom) and n.module == "__future__")
    ]
    transformer = EmbeddedImportTransformer(modname, "_rf_layers")
    # Imports must be transformed before generic Name references know alias map.
    new_body = []
    for node in parsed.body:
        transformed = transformer.visit(node)
        if transformed is None:
            continue
        if isinstance(transformed, list): new_body.extend(transformed)
        else: new_body.append(transformed)
    parsed.body = new_body
    ast.fix_missing_locations(parsed)
    export_expr = {}
    for name in sorted(bound):
        export_expr[name] = transformer.alias_map.get(name, name)
    return ast.unparse(parsed), export_expr, transformer.alias_map


# Outer source begins after the embedded loader. The same comment text also
# exists inside serialized historical sources, so use the LAST occurrence.
MARKER = "# Capa final vigente de Recepción (derivada de 4.5.48)"
pos = text.rfind(MARKER)
if pos < 0:
    raise RuntimeError("No se encontró marcador de capa final")
assert embedded_node is not None
embedded_end_char = sum(len(line) for line in text.splitlines(True)[: embedded_node.end_lineno])
assert pos >= embedded_end_char, "El marcador externo quedó dentro del diccionario embebido"
outer_source = text[pos:]
outer_ast = ast.parse(outer_source, filename="<outer-current>")
outer_transform = EmbeddedImportTransformer("outer_current", "_rf_legacy._rf_layers")
outer_body = []
for node in outer_ast.body:
    transformed = outer_transform.visit(node)
    if transformed is None: continue
    if isinstance(transformed, list): outer_body.extend(transformed)
    else: outer_body.append(transformed)
outer_ast.body = outer_body
ast.fix_missing_locations(outer_ast)
outer_flat = ast.unparse(outer_ast)

# Diagnostics from 4.6.2 described the old embedded loader. They must describe
# the physical definitive runtime truthfully after the refactor.
outer_flat = outer_flat.replace(
    "RUNTIME_CONSOLIDATED_EMBEDDED_MODULE_COUNT = len(_EMBEDDED_RUNTIME_SOURCES)",
    "RUNTIME_CONSOLIDATED_EMBEDDED_MODULE_COUNT = 0",
)
outer_flat = outer_flat.replace("RUNTIME_AZUR_HELPER_EMBEDDED = True", "RUNTIME_AZUR_HELPER_EMBEDDED = False")
outer_flat = outer_flat.replace("RUNTIME_WHATSAPP_HELPER_EMBEDDED = True", "RUNTIME_WHATSAPP_HELPER_EMBEDDED = False")
outer_flat = outer_flat.replace(
    "RUNTIME_EXTERNAL_FUNCTIONAL_HELPERS_REQUIRED = False",
    "RUNTIME_EXTERNAL_FUNCTIONAL_HELPERS_REQUIRED = True",
)

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
# Only declared program files belong in a reproducible candidate. Test-created
# databases, user data and bytecode must never leak from a working directory.
source_manifest = json.loads((SOURCE_DIR / "update_manifest.json").read_text(encoding="utf-8-sig"))
for rel in source_manifest["copy"]:
    rel = str(rel).replace("\\", "/")
    low = rel.lower()
    if (Path(rel).is_absolute() or ".." in rel.split("/") or ":" in rel
            or low.startswith(("data/", "backups/", "update_backups/"))
            or low == ".env" or low.endswith((".db", ".sqlite", ".xlsx", ".xls", ".mdb"))):
        raise ValueError(f"Source manifest includes a protected or invalid path: {rel}")
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_DIR / rel, target)

# Physical audited helpers.
for helper in sorted(HELPERS):
    (OUT / f"{helper}.py").write_text(embedded[helper], encoding="utf-8", newline="\n")

# Stable base becomes a real module, no import hook and no source string.
(OUT / "core_runtime.py").write_text(embedded[BASE], encoding="utf-8", newline="\n")

# Each feature keeps a real Python module dictionary. Flattening all feature
# bodies into one dictionary silently redirects earlier functions to later
# globals (billing recursion, stale print renderers and version drift).
# The registry preserves audited cross-feature mutations without import hooks.
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
    "app_patch_4509": "history_bridge_release",
    "app_patch_4510": "update_recovery",
    "app_patch_4511": "desktop_identity",
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
assert set(FEATURE_NAMES) == HIST - {BASE}
assert len(set(FEATURE_NAMES.values())) == len(FEATURE_NAMES)
registry_text = """import sys
import core_runtime

layers = {'app_base_4428': core_runtime}

def module_lookup(name, default=None):
    return layers.get(name, sys.modules.get(name, default))
"""
(OUT / "runtime_registry.py").write_text(registry_text, encoding="utf-8")
parts = [
    "from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup",
    "# Explicit deterministic startup; all feature globals remain isolated.",
]
feature_files = []
# These three releases only changed the version, traversed `previous`, and set
# PATCH_BOOT_OK. Final app.py already sets the canonical version for every
# feature. Keep compatibility keys, but stop executing those obsolete layers.
release_only_aliases = {
    "app_patch_4509": "app_patch_4508",
    "app_patch_4510": "app_patch_4509",
    "app_patch_4511": "app_patch_4510",
}
for modname in order:
    if modname == BASE:
        continue
    if modname in release_only_aliases:
        parts.append(f"_rf_layers[{modname!r}] = _rf_layers[{release_only_aliases[modname]!r}]")
        continue
    module_name = "reception_" + FEATURE_NAMES[modname]
    flat, exports, alias_map = transform_module(modname, embedded[modname])
    feature_text = (
        "from __future__ import annotations\n"
        "from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup\n\n"
        + flat + "\n"
    )
    compile(feature_text, module_name + ".py", "exec")
    (OUT / (module_name + ".py")).write_text(feature_text, encoding="utf-8", newline="\n")
    feature_files.append(module_name + ".py")
    parts.append(f"import {module_name}")
    parts.append(f"_rf_layers[{modname!r}] = {module_name}")
features_text = "\n".join(parts) + "\n"
(OUT / "features_runtime.py").write_text(features_text, encoding="utf-8", newline="\n")

app_text = "from __future__ import annotations\nimport features_runtime as _rf_legacy\n\n" + outer_flat + "\n"
(OUT / "app.py").write_text(app_text, encoding="utf-8", newline="\n")

# Candidate remains 4.6.6 during equivalence testing; no channel is modified.
meta = {
    "historical_modules": len(HIST),
    "order": order,
    "outer_aliases": outer_transform.alias_map,
    "generated_files": ["app.py", "core_runtime.py", "features_runtime.py", "runtime_registry.py"] + feature_files + [f"{h}.py" for h in sorted(HELPERS)],
    "feature_modules": {k: "reception_" + v for k, v in FEATURE_NAMES.items()},
    "isolated_feature_globals": True,
    "removed_release_only_layers": release_only_aliases,
}
(OUT / "refactor_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Hard structural gates.
all_text = app_text + features_text
assert "_EMBEDDED_RUNTIME_SOURCES" not in all_text
assert "MetaPathFinder" not in all_text
assert "exec(code" not in all_text
for py in (OUT / "app.py", OUT / "core_runtime.py", OUT / "features_runtime.py"):
    compile(py.read_text(encoding="utf-8-sig"), str(py), "exec")
print("FLAT PROTOTYPE GENERATED", OUT)
print("historical layers", len(HIST), "order", len(order))
print("app bytes", (OUT/'app.py').stat().st_size, "features bytes", (OUT/'features_runtime.py').stat().st_size)
