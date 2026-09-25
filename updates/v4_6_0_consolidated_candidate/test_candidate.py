from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[2]
WORK = REPO / "_audit_460"
STABLE = WORK / "stable"
CANDIDATE = WORK / "candidate"


def build_runtime_dirs() -> None:
    shutil.rmtree(WORK, ignore_errors=True)
    STABLE.mkdir(parents=True)
    CANDIDATE.mkdir(parents=True)

    source = json.loads(
        (REPO / "launcher-v1/app-channel-source.json").read_text(encoding="utf-8-sig")
    )
    if source.get("appVersion") != "4.5.48":
        raise AssertionError(f"Se esperaba estable 4.5.48; canal={source.get('appVersion')}")

    for item in source["files"]:
        src = REPO / item["sourcePath"]
        dst = STABLE / item["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    croot = REPO / "updates/v4_6_0_consolidated_candidate"
    for rel in (
        "app.py",
        "recepcion-version.json",
        "update_manifest.json",
        "static/runtime_keep.txt",
    ):
        src = croot / rel
        dst = CANDIDATE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for rel in ("historia_bridge.py", "historia_lan_transport.py"):
        item = next(x for x in source["files"] if x["path"] == rel)
        src = REPO / item["sourcePath"]
        shutil.copy2(src, STABLE / rel)
        shutil.copy2(src, CANDIDATE / rel)

    azur = """
class AzurError(Exception): pass
def emit_invoice(*a, **k): return {}
def query_comprobante(*a, **k): return {}
def mask_api_key(v=''): return '***' if v else ''
def normalize_base_url(v=''): return str(v or '').rstrip('/')
def test_connection(*a, **k): return {'ok': True}
"""
    whatsapp = """
class WhatsAppError(Exception): pass
def build_template_payload(*a, **k): return {}
def send_template(*a, **k): return {'ok': True}
"""
    remote = """
def normalize_public_base_url(v=''): return str(v or '').rstrip('/')
def start_quick_tunnel(*a, **k): return {}
def start_named_tunnel(*a, **k): return {}
def start_named_tunnel_background(*a, **k): return None
def stop_managed_tunnel(*a, **k): return None
def tunnel_status(*a, **k):
    return {'running': False, 'mode': 'off', 'public_base_url': ''}
"""
    for root in (STABLE, CANDIDATE):
        (root / "azur_client.py").write_text(azur, encoding="utf-8")
        (root / "whatsapp_client.py").write_text(whatsapp, encoding="utf-8")
        (root / "remote_agenda.py").write_text(remote, encoding="utf-8")
        (root / "static").mkdir(exist_ok=True)
        (root / "static/index.html").write_text(
            "<!doctype html><title>audit</title>", encoding="utf-8"
        )

    forbidden = (
        list(CANDIDATE.glob("app_patch_*.py"))
        + list(CANDIDATE.glob("app_prev_*.py"))
        + list(CANDIDATE.glob("app_base_*.py"))
    )
    if forbidden:
        raise AssertionError(f"La candidata recibió módulos externos: {forbidden}")


PROBE = r'''
import hashlib
import inspect
import json
import os
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1]).resolve()
out_path = pathlib.Path(sys.argv[2]).resolve()
os.chdir(root)
os.environ["RP_DATA_DIR"] = str(root / "_data")
os.environ["DATABASE_URL"] = ""
os.environ["RP_FORCE_OFFLINE"] = "1"
os.environ["WHATSAPP_ENABLED"] = "0"
os.environ["WHATSAPP_CLOUD_MODE"] = "1"
os.environ["REMOTE_AGENDA_AUTOSTART"] = "0"
sys.path.insert(0, str(root))

import app

def normalize(text):
    text = str(text or "")
    return re.sub(r"(?<!\d)4\.\d+\.\d+(?!\d)", "<VER>", text)

def digest(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()

routes = []
for route in app.app.router.routes:
    methods = sorted(getattr(route, "methods", set()) or set())
    path = str(getattr(route, "path", ""))
    if not path:
        continue
    endpoint = getattr(route, "endpoint", None)
    try:
        sig = str(inspect.signature(endpoint)) if endpoint else ""
    except Exception:
        sig = ""
    routes.append({
        "path": path,
        "methods": methods,
        "signature": normalize(sig),
    })
routes.sort(key=lambda x: (x["path"], ",".join(x["methods"]), x["signature"]))

core = app.core
historical = sorted(
    name
    for name in sys.modules
    if re.fullmatch(r"(?:app_base_4428|app_prev_4458|app_patch_\d+)", name)
)
result = {
    "version": app.APP_VERSION,
    "routes": routes,
    "route_count": len(routes),
    "overlay_js_sha": digest(getattr(core, "V460_OVERLAY_JS", "")),
    "overlay_css_sha": digest(getattr(core, "V460_OVERLAY_CSS", "")),
    "embedded_runtime_flag": bool(getattr(app, "RUNTIME_CONSOLIDATED", False)),
    "external_patch_required": getattr(
        app, "RUNTIME_CONSOLIDATED_EXTERNAL_PATCH_FILES_REQUIRED", None
    ),
    "embedded_declared_count": int(
        getattr(app, "RUNTIME_CONSOLIDATED_EMBEDDED_MODULE_COUNT", 0) or 0
    ),
    "historical_modules": historical,
    "critical_routes": {
        p: any(x["path"] == p for x in routes)
        for p in (
            "/api/visits/batch-payment",
            "/api/historical/{hid}/activate",
            "/api/v4470/print-visit/{visit_id}",
            "/api/program/update-now",
            "/api/version",
        )
    },
    "critical_core": {
        "billing_group_records": hasattr(core, "billing_group_records"),
        "get_db": hasattr(core, "get_db"),
        "Patient": hasattr(core, "Patient"),
        "Visit": hasattr(core, "Visit"),
    },
}
out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "routes"}, ensure_ascii=False, indent=2))
'''


def probe(root: pathlib.Path, out_name: str) -> dict:
    probe_path = WORK / "probe_runtime.py"
    probe_path.write_text(PROBE, encoding="utf-8")
    out = WORK / out_name
    subprocess.run(
        [sys.executable, str(probe_path), str(root), str(out)],
        check=True,
        cwd=REPO,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def validate_manifest() -> None:
    root = REPO / "updates/v4_6_0_consolidated_candidate"
    compile((root / "app.py").read_text(encoding="utf-8-sig"), "app.py", "exec")
    manifest = json.loads((root / "update_manifest.json").read_text(encoding="utf-8-sig"))
    version = json.loads(
        (root / "recepcion-version.json").read_text(encoding="utf-8-sig")
    )["version"]
    assert version == "4.6.0"
    assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == version
    assert manifest["notes"]["external_patch_chain_required"] is False
    assert manifest["notes"]["embedded_historical_modules"] == 51


def main() -> None:
    validate_manifest()
    build_runtime_dirs()
    stable = probe(STABLE, "stable.json")
    candidate = probe(CANDIDATE, "candidate.json")

    assert stable["version"] == "4.5.48", stable["version"]
    assert candidate["version"] == "4.6.0", candidate["version"]
    assert stable["routes"] == candidate["routes"], "Cambió la superficie de rutas o firmas"
    assert stable["overlay_js_sha"] == candidate["overlay_js_sha"], "Cambió V460_OVERLAY_JS"
    assert stable["overlay_css_sha"] == candidate["overlay_css_sha"], "Cambió V460_OVERLAY_CSS"
    assert candidate["embedded_runtime_flag"] is True
    assert candidate["external_patch_required"] is False
    assert candidate["embedded_declared_count"] == 51, candidate["embedded_declared_count"]
    assert all(candidate["critical_routes"].values()), candidate["critical_routes"]
    assert all(candidate["critical_core"].values()), candidate["critical_core"]
    assert len(candidate["historical_modules"]) >= 45, len(candidate["historical_modules"])

    print()
    print("OK: Recepción 4.6.0 consolidada conserva la superficie funcional de 4.5.48.")
    print("OK: arranca sin app_patch_*.py, app_prev_*.py ni app_base_*.py externos.")
    print("OK: los 51 módulos históricos activos están autocontenidos dentro de app.py.")


if __name__ == "__main__":
    main()
