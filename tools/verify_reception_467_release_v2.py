from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import verify_reception_467_release as base


def normalized_overlay(runtime: Path, label: str) -> dict[str, object]:
    root = Path(tempfile.mkdtemp(prefix=f"rp467-overlay-{label}-"))
    try:
        out = root / "overlay.json"
        code = r'''
import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,os.getcwd())
import app
core=app.core
version=str(app.APP_VERSION)
js=str(getattr(core,'V460_OVERLAY_JS',''))
css=str(getattr(core,'V460_OVERLAY_CSS',''))
def norm(text):
    return text.replace(version,'__APP_VERSION__')
Path(os.environ['OVERLAY_OUT']).write_text(json.dumps({
 'version':version,
 'js_raw':hashlib.sha256(js.encode()).hexdigest(),
 'css_raw':hashlib.sha256(css.encode()).hexdigest(),
 'js_normalized':hashlib.sha256(norm(js).encode()).hexdigest(),
 'css_normalized':hashlib.sha256(norm(css).encode()).hexdigest(),
 'js_version_occurrences':js.count(version),
 'css_version_occurrences':css.count(version),
}),encoding='utf-8')
'''
        env = base.offline_env(root / "data")
        env["OVERLAY_OUT"] = str(out)
        p = subprocess.run([sys.executable, "-c", code], cwd=runtime, env=env, text=True, capture_output=True, timeout=90)
        if p.returncode:
            raise RuntimeError(p.stdout + p.stderr)
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    base.structural_gate()
    old = base.probe(base.OLD, "old")
    new = base.probe(base.NEW, "new")
    assert old["version"] == "4.6.6" and new["version"] == "4.6.7"
    assert old["routes"] == new["routes"]
    assert old["tables"] == new["tables"]
    assert old["openapi"] == new["openapi"], (old["openapi"], new["openapi"])
    assert new["openapi_paths"] == 220 and new["openapi_schemas"] == 36
    assert new["historical"] == []
    assert new["empty_billing_group"] == []
    assert new["endpoint_versions"] and set(new["endpoint_versions"]) == {"4.6.7"}

    old_overlay = normalized_overlay(base.OLD, "old")
    new_overlay = normalized_overlay(base.NEW, "new")
    assert old_overlay["js_normalized"] == new_overlay["js_normalized"], (old_overlay, new_overlay)
    assert old_overlay["css_normalized"] == new_overlay["css_normalized"], (old_overlay, new_overlay)
    if old_overlay["js_raw"] != new_overlay["js_raw"]:
        assert old_overlay["js_version_occurrences"] or new_overlay["js_version_occurrences"], (old_overlay, new_overlay)
    if old_overlay["css_raw"] != new_overlay["css_raw"]:
        assert old_overlay["css_version_occurrences"] or new_overlay["css_version_occurrences"], (old_overlay, new_overlay)

    base.functional_flow()
    base.packaged_staging()
    base.update_rollback()
    print("RECEPTION 4.6.7 RELEASE VERIFIED")
    print("routes", len(new["routes"]), "tables", len(new["tables"]), "openapi", new["openapi_paths"], new["openapi_schemas"])
    print("overlay differences limited to canonical app version")
    print("historical modules", len(new["historical"]), "endpoint versions", len(new["endpoint_versions"]))
    print("upgrade 4.6.6 -> 4.6.7 -> rollback 4.6.6 OK")


if __name__ == "__main__":
    main()
