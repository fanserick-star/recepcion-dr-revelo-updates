from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "updates" / "v4_6_6_fast_attention_save" / "app.py"
OUT = ROOT / "refactor" / "reception_patch_patterns.json"

text = APP.read_text(encoding="utf-8-sig")
tree = ast.parse(text)
embedded = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_EMBEDDED_RUNTIME_SOURCES":
                embedded = ast.literal_eval(node.value)
                break
if not isinstance(embedded, dict):
    raise SystemExit("embedded dict missing")

names = set(embedded)
rows = []
for name, source in embedded.items():
    if not (name.startswith("app_") and name not in {"azur_client", "remote_agenda", "whatsapp_client"}):
        continue
    mod = ast.parse(source, filename=f"<{name}>")
    imports = []
    alias_to_module = {}
    star_imports = []
    for node in mod.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split('.')[0]
                if base in names:
                    imports.append(ast.unparse(node))
                    alias_to_module[a.asname or base] = base
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split('.')[0]
            if base in names:
                imports.append(ast.unparse(node))
                if any(a.name == '*' for a in node.names):
                    star_imports.append(base)
                for a in node.names:
                    if a.name != '*':
                        alias_to_module[a.asname or a.name] = base

    alias_refs = {alias: 0 for alias in alias_to_module}
    for node in ast.walk(mod):
        if isinstance(node, ast.Name) and node.id in alias_refs:
            alias_refs[node.id] += 1

    # Top-level statements that manipulate globals or copy previous-module attrs.
    special = []
    for node in mod.body:
        src = ast.get_source_segment(source, node) or ""
        low = src.lower()
        if any(token in low for token in ("globals()", "dir(", ".__dict__", "setattr(", "getattr(")):
            special.append(src[:1200])

    header = "\n".join(source.splitlines()[:40])
    rows.append({
        "name": name,
        "embedded_imports": imports,
        "star_imports": star_imports,
        "alias_to_module": alias_to_module,
        "alias_reference_counts": alias_refs,
        "special_top_level": special[:10],
        "header_first_40_lines": header,
    })

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} modules={len(rows)}")
