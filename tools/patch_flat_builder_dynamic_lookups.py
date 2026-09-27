from pathlib import Path

p = Path(__file__).resolve().parent / "build_reception_flat_prototype.py"
s = p.read_text(encoding="utf-8")

old = '''        self.layer_expr_prefix = layer_expr_prefix
        self.alias_map: dict[str, str] = {}

    def _unique(self, alias: str) -> str:
'''
new = '''        self.layer_expr_prefix = layer_expr_prefix
        self.alias_map: dict[str, str] = {}

    def _layer_expr(self):
        # Support both `_rf_layers` and `_rf_legacy._rf_layers` safely.
        return ast.parse(self.layer_expr_prefix, mode="eval").body

    def _unique(self, alias: str) -> str:
'''
assert old in s
s = s.replace(old, new, 1)

old_name = 'value=ast.Name(id=self.layer_expr_prefix, ctx=ast.Load()),'
assert s.count(old_name) == 2, s.count(old_name)
s = s.replace(old_name, 'value=self._layer_expr(),')

needle = '''    def visit_Name(self, node: ast.Name):
        if node.id in self.alias_map:
            node.id = self.alias_map[node.id]
        return node
'''
replacement = '''    def visit_Call(self, node: ast.Call):
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
'''
assert needle in s
s = s.replace(needle, replacement, 1)
p.write_text(s, encoding="utf-8", newline="\n")
print("patched dynamic historical lookups")
