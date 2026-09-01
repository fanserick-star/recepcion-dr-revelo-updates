from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v4438_validator_base", HERE / "validate_v4438.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("No se pudo cargar validate_v4438.py")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def main():
    subprocess.run([sys.executable, str(HERE / "build_v4438_v2.py")], check=True)
    candidate, payload = v.payloads()
    required = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    v.require(candidate.get("version") == "4.4.38", "Versión candidato incorrecta")
    v.require(candidate.get("app_version") == "4.4.36", "App runtime cambió sin necesidad")
    v.require([x["path"] for x in candidate["files"]] == required, "Release dejó de ser acumulativo")
    v.require(v.sha(payload["app.py"]) == "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e", "app.py funcional fue alterado")
    v.require(v.sha(payload["app_base_4428.py"]) == "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba", "base estable fue alterada")
    text = payload["ABRIR_RECEPCION.py"].decode("utf-8-sig")
    compile(text, "ABRIR_RECEPCION.py", "exec")
    markers = ["_rp_diag_report", "_rp_diag_flush_outbox", "rp_diagnostics_incidents", "privacy filter revision 2", "_rp_v4437_required_files", "_choose_app_port", 'env["RP_PORT"] = str(APP_PORT)']
    v.require(all(x in text for x in markers), "Faltan contratos de diagnóstico/privacidad/puerto/dependencia")
    forbidden = ["import AUTOACTUALIZAR", "import _AUTOACTUALIZAR_31", "import _ABRIR_RECEPCION_451"]
    v.require(not any(x in text for x in forbidden), "Regresó dependencia de launcher viejo")
    print("V4438_V2_STATIC_CONTRACT_OK")
    v.update_from_4437(candidate, payload)
    v.diagnostics_privacy_and_queue(candidate, payload)
    print("VALIDATE_V4438_V2_OK")


if __name__ == "__main__":
    main()
