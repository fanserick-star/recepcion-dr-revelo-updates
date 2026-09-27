from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "updates" / "v4_6_6_fast_attention_save" / "app.py"
OUT = ROOT / "refactor" / "reception_alias_mutations.json"
text = APP.read_text(encoding="utf-8-sig")
tree = ast.parse(text)
embedded = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "_EMBEDDED_RUNTIME_SOURCES":
                embedded = ast.literal_eval(node.value)
if not isinstance(embedded, dict):
    raise SystemExit("missing embedded")
names = set(embedded)
rows = []
for modname, source in embedded.items():
    if not modname.startswith("app_"):
        continue
    tree2 = ast.parse(source)
    aliases = {}
    for node in tree2.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split('.')[0]
                if base in names:
                    aliases[a.asname or base] = base
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split('.')[0]
            if base in names:
                for a in node.names:
                    if a.name != '*':
                        aliases[a.asname or a.name] = base
    mutations = []
    for node in ast.walk(tree2):
        targets = []
        if isinstance(node, ast.Assign): targets = node.targets
        elif isinstance(node, ast.AnnAssign): targets = [node.target]
        elif isinstance(node, ast.AugAssign): targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id in aliases:
                mutations.append({
                    "alias": target.value.id,
                    "target_module": aliases[target.value.id],
                    "attribute": target.attr,
                    "statement": ast.get_source_segment(source, node) or ast.unparse(node),
                })
    if mutations:
        rows.append({"module": modname, "mutations": mutations})
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))
