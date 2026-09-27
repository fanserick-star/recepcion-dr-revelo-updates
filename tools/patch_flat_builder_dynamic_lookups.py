from pathlib import Path

p = Path(__file__).resolve().parent / "build_reception_flat_prototype.py"
s = p.read_text(encoding="utf-8")

old_call = '''    def visit_Call(self, node: ast.Call):
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
'''
new_call = '''    def visit_Call(self, node: ast.Call):
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
'''
assert old_call in s
s = s.replace(old_call, new_call, 1)

old_parts = '''parts = [
    "from __future__ import annotations",
    "import types as _rf_types",
    "import core_runtime as _rf_core_runtime",
    "",
    "# Consolidated historical feature runtime. No import hooks, no embedded source strings.",
    "_rf_layers = {'app_base_4428': _rf_core_runtime}",
    "",
]
'''
new_parts = '''parts = [
    "from __future__ import annotations",
    "import sys as _rf_sys",
    "import types as _rf_types",
    "import core_runtime as _rf_core_runtime",
    "",
    "# Consolidated historical feature runtime. No import hooks, no embedded source strings.",
    "_rf_layers = {'app_base_4428': _rf_core_runtime}",
    "",
    "def _rf_module_lookup(name, default=None):",
    "    if name in _rf_layers:",
    "        return _rf_layers[name]",
    "    return _rf_sys.modules.get(name, default)",
    "",
]
'''
assert old_parts in s
s = s.replace(old_parts, new_parts, 1)

p.write_text(s, encoding="utf-8", newline="\n")
print("patched variable dynamic historical lookups")
