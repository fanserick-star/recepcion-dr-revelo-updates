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
        # Several historical layers inspect earlier patches through
        # sys.modules.get("app_patch_..."). In the definitive runtime those
        # modules no longer exist in sys.modules; route the lookup to the
        # static consolidated layer registry instead.
        node = self.generic_visit(node)
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr == "get"
            and isinstance(fn.value, ast.Attribute)
            and fn.value.attr == "modules"
            and isinstance(fn.value.value, ast.Name)
            and fn.value.value.id == "sys"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value in HIST
        ):
            node.func = ast.Attribute(value=self._layer_expr(), attr="get", ctx=ast.Load())
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
shutil.copytree(SOURCE_DIR, OUT)

# Physical audited helpers.
for helper in sorted(HELPERS):
    (OUT / f"{helper}.py").write_text(embedded[helper], encoding="utf-8", newline="\n")

# Stable base becomes a real module, no import hook and no source string.
(OUT / "core_runtime.py").write_text(embedded[BASE], encoding="utf-8", newline="\n")

parts = [
    "from __future__ import annotations",
    "import types as _rf_types",
    "import core_runtime as _rf_core_runtime",
    "",
    "# Consolidated historical feature runtime. No import hooks, no embedded source strings.",
    "_rf_layers = {'app_base_4428': _rf_core_runtime}",
    "",
]

for modname in order:
    if modname == BASE:
        continue
    flat, exports, alias_map = transform_module(modname, embedded[modname])
    parts += [f"# ---- {modname} ----", flat, ""]
    snapvar = f"_rf_snapshot_{safe(modname)}"
    parts.append(f"{snapvar} = _rf_types.SimpleNamespace()")
    parts.append(f"setattr({snapvar}, '__name__', {modname!r})")
    for original, expr in sorted(exports.items()):
        parts.append(f"if {expr!r} in globals(): setattr({snapvar}, {original!r}, globals()[{expr!r}])")
    parts.append(f"_rf_layers[{modname!r}] = {snapvar}")
    parts.append("")

features_text = "\n".join(parts) + "\n"
(OUT / "features_runtime.py").write_text(features_text, encoding="utf-8", newline="\n")

app_text = "from __future__ import annotations\nimport features_runtime as _rf_legacy\n\n" + outer_flat + "\n"
(OUT / "app.py").write_text(app_text, encoding="utf-8", newline="\n")

# Candidate remains 4.6.6 during equivalence testing; no channel is modified.
meta = {
    "historical_modules": len(HIST),
    "order": order,
    "outer_aliases": outer_transform.alias_map,
    "generated_files": ["app.py", "core_runtime.py", "features_runtime.py"] + [f"{h}.py" for h in sorted(HELPERS)],
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
