from __future__ import annotations

# v4.5.10 — release automática de recuperación.
# Conserva el puente Recepción -> Historia Clínica validado y eleva la
# versión/fingerprint para salir de cualquier cuarentena vieja del updater.

import app_patch_4509 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.10"

_mod = previous
_seen = set()
for _ in range(220):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)

core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = True
