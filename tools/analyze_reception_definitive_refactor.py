from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "updates" / "v4_6_6_fast_attention_save"
APP_PATH = APP_DIR / "app.py"
OUT_DIR = ROOT / "refactor"
OUT_DIR.mkdir(exist_ok=True)
JSON_OUT = OUT_DIR / "reception_definitive_inventory.json"
MD_OUT = OUT_DIR / "reception_definitive_inventory.md"

text = APP_PATH.read_text(encoding="utf-8-sig")
tree = ast.parse(text, filename=str(APP_PATH))

embedded: dict[str, str] = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_EMBEDDED_RUNTIME_SOURCES":
                value = ast.literal_eval(node.value)
                if not isinstance(value, dict):
                    raise SystemExit("_EMBEDDED_RUNTIME_SOURCES no es dict")
                embedded = {str(k): str(v) for k, v in value.items()}
                break
if not embedded:
    raise SystemExit("No se encontró _EMBEDDED_RUNTIME_SOURCES")

module_names = set(embedded)
import_graph: dict[str, list[str]] = {}
route_defs: list[dict] = []
module_stats: list[dict] = []
name_defs: dict[str, list[str]] = defaultdict(list)

HTTP_DECORATORS = {"get", "post", "put", "delete", "patch", "options", "head", "api_route"}

for name, source in embedded.items():
    parsed = ast.parse(source, filename=f"<{name}>")
    imports: set[str] = set()
    defs = []
    assigns = []
    routes = []
    for node in parsed.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in module_names:
                    imports.add(base)
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".")[0]
            if base in module_names:
                imports.add(base)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.append(node.name)
            name_defs[node.name].append(name)
            for dec in getattr(node, "decorator_list", []):
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    method = dec.func.attr
                    if method in HTTP_DECORATORS and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app":
                        path = None
                        if dec.args and isinstance(dec.args[0], ast.Constant):
                            path = dec.args[0].value
                        routes.append({"module": name, "endpoint": node.name, "method": method.upper(), "path": path})
                        route_defs.append(routes[-1])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    assigns.append(target.id)
                    name_defs[target.id].append(name)
    import_graph[name] = sorted(imports)
    module_stats.append({
        "name": name,
        "bytes": len(source.encode("utf-8")),
        "lines": source.count("\n") + 1,
        "imports_embedded": sorted(imports),
        "top_level_defs": len(defs),
        "top_level_assigns": len(assigns),
        "decorated_routes": len(routes),
    })

# Root modules are embedded modules not imported by any other embedded module.
imported_by: dict[str, list[str]] = defaultdict(list)
for src, deps in import_graph.items():
    for dep in deps:
        imported_by[dep].append(src)
roots = sorted(name for name in module_names if not imported_by.get(name))
leaves = sorted(name for name, deps in import_graph.items() if not deps)

# Detect simple chain depth from each root.
def walk_chain(root: str) -> list[str]:
    chain = [root]
    seen = {root}
    cur = root
    while True:
        deps = [d for d in import_graph.get(cur, []) if d not in seen]
        if len(deps) != 1:
            break
        cur = deps[0]
        chain.append(cur)
        seen.add(cur)
    return chain

chains = {root: walk_chain(root) for root in roots}

# Outer source after embedded dictionary: useful to see final non-embedded overrides.
outer_defs = []
outer_routes = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        outer_defs.append(node.name)
        for dec in getattr(node, "decorator_list", []):
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app" and dec.func.attr in HTTP_DECORATORS:
                    path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else None
                    outer_routes.append({"module": "__outer__", "endpoint": node.name, "method": dec.func.attr.upper(), "path": path})

# Runtime import under an isolated local-only data directory.
os.environ.setdefault("RP_DATA_DIR", tempfile.mkdtemp(prefix="rp-refactor-inventory-"))
os.environ["RP_FORCE_OFFLINE"] = "1"
os.environ["DATABASE_URL"] = ""
os.environ["HISTORIA_DATABASE_URL"] = ""
os.environ["REMOTE_AGENDA_AUTOSTART"] = "0"
os.environ["WHATSAPP_ENABLED"] = "0"

runtime_routes = []
runtime_error = None
try:
    old_cwd = os.getcwd()
    os.chdir(APP_DIR)
    sys.path.insert(0, str(APP_DIR))
    spec = importlib.util.spec_from_file_location("reception_466_inventory_runtime", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    for route in mod.app.router.routes:
        methods = sorted(getattr(route, "methods", set()) or set())
        endpoint = getattr(route, "endpoint", None)
        runtime_routes.append({
            "path": getattr(route, "path", None),
            "methods": methods,
            "endpoint": getattr(endpoint, "__name__", None),
            "endpoint_module": getattr(endpoint, "__module__", None),
        })
finally:
    try:
        os.chdir(old_cwd)
    except Exception:
        pass

route_key_counts = Counter((r["path"], tuple(r["methods"])) for r in runtime_routes)
duplicate_runtime_routes = [
    {"path": k[0], "methods": list(k[1]), "count": v}
    for k, v in route_key_counts.items() if v > 1
]

historical_rx = re.compile(r"^(?:app_(?:patch|prev|base)_\d+)$")
historical_modules = sorted(x for x in module_names if historical_rx.match(x))
helper_modules = sorted(module_names - set(historical_modules))

overridden_names = sorted(
    ({"name": name, "modules": mods, "count": len(mods)} for name, mods in name_defs.items() if len(set(mods)) > 1),
    key=lambda x: (-x["count"], x["name"]),
)

report = {
    "source": "updates/v4_6_6_fast_attention_save/app.py",
    "embedded_module_count": len(embedded),
    "historical_module_count": len(historical_modules),
    "helper_module_count": len(helper_modules),
    "historical_modules": historical_modules,
    "helper_modules": helper_modules,
    "roots": roots,
    "leaves": leaves,
    "chains": chains,
    "module_stats": sorted(module_stats, key=lambda x: x["name"]),
    "import_graph": import_graph,
    "embedded_decorated_route_defs": route_defs,
    "outer_top_level_defs": outer_defs,
    "outer_decorated_routes": outer_routes,
    "runtime_route_count": len(runtime_routes),
    "runtime_routes": runtime_routes,
    "duplicate_runtime_routes": duplicate_runtime_routes,
    "overridden_top_level_names_top100": overridden_names[:100],
}
JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

lines = [
    "# Inventario para refactor definitivo de Recepción 4.6.6",
    "",
    f"- Módulos embebidos totales: **{len(embedded)}**",
    f"- Capas históricas app_base/app_patch/app_prev: **{len(historical_modules)}**",
    f"- Helpers embebidos: **{len(helper_modules)}** — {', '.join(helper_modules) if helper_modules else 'ninguno'}",
    f"- Raíces del grafo embebido: **{', '.join(roots) if roots else 'ninguna'}**",
    f"- Hojas del grafo embebido: **{', '.join(leaves) if leaves else 'ninguna'}**",
    f"- Rutas FastAPI activas en runtime: **{len(runtime_routes)}**",
    f"- Rutas runtime duplicadas por path+método: **{len(duplicate_runtime_routes)}**",
    "",
    "## Cadenas simples detectadas",
]
for root, chain in chains.items():
    lines.append(f"- `{root}` → " + " → ".join(f"`{x}`" for x in chain[1:]))
lines += ["", "## Módulos más grandes"]
for item in sorted(module_stats, key=lambda x: x["bytes"], reverse=True)[:20]:
    lines.append(
        f"- `{item['name']}`: {item['lines']} líneas, {item['bytes']} bytes, "
        f"{item['decorated_routes']} rutas decoradas, importa {item['imports_embedded']}"
    )
lines += ["", "## Rutas activas por módulo de endpoint"]
for module, count in Counter(r["endpoint_module"] for r in runtime_routes).most_common():
    lines.append(f"- `{module}`: {count}")
lines += ["", "## Duplicados activos"]
if duplicate_runtime_routes:
    for item in duplicate_runtime_routes:
        lines.append(f"- `{','.join(item['methods'])} {item['path']}` × {item['count']}")
else:
    lines.append("- Ninguno")
MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Inventory written: {JSON_OUT}")
print(f"Inventory written: {MD_OUT}")
print(f"Embedded modules={len(embedded)} historical={len(historical_modules)} runtime_routes={len(runtime_routes)} duplicate_routes={len(duplicate_runtime_routes)}")
