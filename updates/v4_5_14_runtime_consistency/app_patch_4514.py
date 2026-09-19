from __future__ import annotations

# v4.5.14 — el estado del actualizador distingue paquete instalado y runtime real.
# Corrige el caso visible en consultorio: manifest 4.5.11 pero programa ejecutándose 4.5.7.

import json
from pathlib import Path
import app_patch_4513 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.14"

_mod = previous
_seen = set()
for _ in range(280):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

# Sustituye únicamente el endpoint de comprobación visual del canal.
_old_update_now = None
for _route in list(app.router.routes):
    if getattr(_route, "path", None) == "/api/program/update-now" and "POST" in set(getattr(_route, "methods", set()) or set()):
        _old_update_now = getattr(_route, "endpoint", None)
        app.router.routes.remove(_route)
        break

@app.post("/api/program/update-now")
def v4514_program_update_now():
    root = Path(str(core.BASE_DIR))
    package = {}
    try:
        package = json.loads((root / "update_manifest.json").read_text(encoding="utf-8-sig"))
    except Exception:
        package = {}
    package_version = str(package.get("version") or "").strip()
    expected_runtime = str(package.get("app_version") or package.get("runtime_version") or "").strip()
    actual_runtime = str(APP_VERSION)

    # Nunca llamar "actualizado" a un paquete cuyo motor real no coincide.
    if expected_runtime and expected_runtime != actual_runtime:
        return {
            "ok": True,
            "update": True,
            "runtime_mismatch": True,
            "current": actual_runtime,
            "package": package_version,
            "latest": package_version,
            "message": (
                f"Actualización incompleta: el paquete {package_version or 'local'} está registrado, "
                f"pero el programa activo es v{actual_runtime}. Cierra y vuelve a abrir Recepción; "
                "el launcher completará el runtime automáticamente."
            ),
        }

    try:
        info = core._read_update_channel_status()
        latest = str(info.get("latest") or "").strip()
        local = str(info.get("local") or package_version or actual_runtime).strip()
        if bool(info.get("update_available")):
            return {
                "ok": True, "update": True, "current": actual_runtime,
                "package": package_version or local, "latest": latest,
                "message": f"Hay una actualización {latest} disponible. Cierra y vuelve a abrir Recepción para instalarla automáticamente.",
            }
        return {
            "ok": True, "update": False, "current": actual_runtime,
            "package": package_version or local, "latest": latest or package_version or actual_runtime,
            "message": f"Programa v{actual_runtime} actualizado y coherente con el paquete {package_version or actual_runtime}.",
        }
    except Exception as exc:
        return {
            "ok": False, "update": False, "current": actual_runtime,
            "package": package_version, "message": f"No se pudo consultar el canal: {str(exc)[:200]}"
        }

PATCH_BOOT_OK = True
